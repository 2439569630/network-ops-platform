"""
用户管理模块
处理用户增删改查、批量导入、个人资料管理、头像上传、邮箱验证等业务逻辑。
"""

import csv
import io
import json
import secrets
import time
import os
import asyncio
import logging
import re
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Body, Request, UploadFile, File, Query
from fastapi.responses import HTMLResponse
from typing import List, Optional, Any
from app.schemas.user import UserCreate, UserResponse, RoleUpdate, UserUpdate, UserStatusUpdate, AdminUserUpdate
from app.services.avatar_service import AvatarService
from app.services.user_service import UserService
from app.services.user_admin_audit_service import UserAdminAuditService
from app.api import deps
from app.core.security import PermissionChecker, user_is_super, get_disabled_permission_codes_cached, get_password_hash
from app.services.image_storage_service import ImageStorageService
from app.core.redis import redis_manager
from app.core.database import db
from app.models.orm.user import User
from app.models.orm.rbac import Role
from tortoise.expressions import Q
from app.utils.remote_image_api import RemoteImageApiError
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

# 密码哈希线程池配置
# 用于批量导入时并行计算哈希，避免阻塞主线程
_HASH_MAX_WORKERS = max(4, min(32, int(os.cpu_count() or 4)))
_HASH_EXECUTOR = ThreadPoolExecutor(max_workers=_HASH_MAX_WORKERS)

# 导入任务数据的 Redis 过期时间 (30分钟)
_IMPORT_TTL_SECONDS = 1800

# --- Redis Key 辅助函数 ---

def _import_data_key(token: str) -> str:
    """导入文件解析后的临时存储 Key"""
    return f"user_import:{token}"

def _import_progress_key(token: str) -> str:
    """导入进度信息的 Key"""
    return f"user_import_progress:{token}"

def _import_cancel_key(token: str) -> str:
    """导入取消信号的 Key"""
    return f"user_import_cancel:{token}"

def _import_result_key(token: str) -> str:
    """导入最终结果的 Key"""
    return f"user_import_result:{token}"

# --- 导入任务辅助函数 ---

async def _is_user_import_cancelled(redis_client: Any, token: str) -> bool:
    """检查是否有取消导入的信号"""
    try:
        return bool(await redis_client.exists(_import_cancel_key(token)))
    except Exception:
        return False

async def _set_user_import_cancel(redis_client: Any, token: str) -> None:
    """设置取消信号"""
    await redis_client.set(_import_cancel_key(token), "1", ex=_IMPORT_TTL_SECONDS)

async def _clear_user_import_cancel(redis_client: Any, token: str) -> None:
    """清除取消信号"""
    try:
        await redis_client.delete(_import_cancel_key(token))
    except Exception:
        pass

async def _set_user_import_result(redis_client: Any, token: str, data: dict) -> None:
    """保存导入结果"""
    await redis_client.set(_import_result_key(token), json.dumps(data, ensure_ascii=False), ex=_IMPORT_TTL_SECONDS)

async def _get_user_import_result(redis_client: Any, token: str) -> Optional[dict]:
    """获取导入结果"""
    raw = await redis_client.get(_import_result_key(token))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None

async def _set_user_import_progress(
    redis_client: Any,
    token: str,
    percent: int,
    status: str,
    message: Optional[str] = None,
    detail: Optional[dict] = None,
):
    """更新导入进度"""
    payload = {
        "token": token,
        "percent": max(0, min(100, int(percent))),
        "status": str(status or ""),
        "message": str(message or ""),
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    if detail is not None:
        payload["detail"] = detail
    await redis_client.set(_import_progress_key(token), json.dumps(payload, ensure_ascii=False), ex=_IMPORT_TTL_SECONDS)

# 受保护的角色代码 (不可随意操作)
_PROTECTED_ROLE_CODES = {"superadmin", "super_admin", "super-admin"}


async def _get_user_role_codes(user_id: int) -> list[str]:
    """获取用户的角色代码列表"""
    codes = await Role.filter(user_roles__user_id=int(user_id)).values_list("code", flat=True)
    return [str(c) for c in codes if c]


async def _require_actor_superadmin_when_target_protected(target_user_id: int, actor: dict) -> None:
    """
    安全检查：如果目标用户是超级管理员，则要求操作者也必须是超级管理员。
    防止普通管理员篡改超级管理员账号。
    """
    if user_is_super(actor):
        return
    codes = {str(c).strip().lower() for c in (await _get_user_role_codes(int(target_user_id))) if str(c).strip()}
    # 检查目标用户是否拥有受保护的角色
    if codes & _PROTECTED_ROLE_CODES:
        raise HTTPException(status_code=403, detail="仅超级管理员可操作该用户")


def _get_request_ip(request: Request) -> Optional[str]:
    """获取请求 IP，支持 X-Forwarded-For"""
    try:
        xff = request.headers.get("x-forwarded-for") if request else None
        ip = (xff.split(",")[0].strip() if xff else None) or (request.client.host if request and request.client else None)
        return str(ip).strip() or None
    except Exception:
        return None

# --- API 路由 ---

@router.post("/batch/delete", response_model=dict)
async def delete_users_batch(
    request: Request,
    user_ids: List[int] = Body(..., embed=True),
    current_user: dict = Depends(deps.get_current_user),
    _: dict = Depends(PermissionChecker(["sys:user:manage"]))
):
    """
    批量删除用户 (仅管理员)
    
    一次性删除多个用户。
    会自动跳过超级管理员或受保护的用户。
    
    Args:
        user_ids: 用户 ID 列表
    """
    # 1. 自我保护检查
    if current_user.get("id") in user_ids:
        return {"code": 400, "message": "不能删除自己"}
        
    try:
        # 2. 权限检查：确保操作者有权删除每一个目标用户
        for uid in user_ids or []:
            await _require_actor_superadmin_when_target_protected(int(uid), current_user)
            
        # 3. 执行批量删除
        await UserService.admin_delete_users(user_ids, actor_id=current_user.get("id"))
        
        # 4. 记录审计日志
        await UserAdminAuditService.log(
            action="user.batch_delete",
            actor=current_user,
            request_ip=_get_request_ip(request) if request else None,
            detail={"count": len(user_ids or []), "user_ids": user_ids or []},
        )
        return {"code": 200, "message": "批量删除成功"}
    except Exception as e:
        return {"code": 500, "message": f"批量删除失败: {str(e)}"}


@router.put("/{user_id}/password", response_model=dict)
async def reset_user_password(
    user_id: int,
    request: Request,
    password: str = Body(..., embed=True),
    current_user: dict = Depends(deps.get_current_user),
    _: dict = Depends(PermissionChecker(["sys:user:manage"]))
):
    """
    管理员重置用户密码
    
    强制修改指定用户的密码。
    无需旧密码验证。
    """
    try:
        # 1. 权限检查
        await _require_actor_superadmin_when_target_protected(int(user_id), current_user)
        
        # 2. 执行重置
        await UserService.reset_password(user_id, password)
        
        # 3. 记录审计日志
        await UserAdminAuditService.log(
            action="user.reset_password",
            actor=current_user,
            target_user_id=int(user_id),
            request_ip=_get_request_ip(request) if request else None,
        )
        return {"code": 200, "message": "密码重置成功"}
    except ValueError as e:
        return {"code": 400, "message": str(e)}
    except Exception as e:
        return {"code": 500, "message": f"密码重置失败: {str(e)}"}

@router.post("/update_perms", response_model=dict)
async def update_user_perms(
    request: Request,
    user_id: int = Body(...),
    permissions: List[str] = Body(...),
    current_user: dict = Depends(deps.get_current_user),
    _: dict = Depends(PermissionChecker(["sys:user:manage"]))
):
    return {"code": 501, "message": "此功能已停用。请通过角色管理用户权限。"}

@router.post("/status", response_model=dict)
async def update_user_status(
    request: Request,
    user_id: int = Body(...),
    is_approved: bool = Body(...),
    current_user: dict = Depends(deps.get_current_user),
    _: dict = Depends(PermissionChecker(["sys:user:manage"]))
):
    """
    封禁/解封用户 (仅管理员)
    
    修改用户的审核状态 (is_approved)。
    如果设为 False，用户将无法登录。
    """
    if user_id == current_user.get("id"):
        return {"code": 400, "message": "不能封禁自己"}
        
    try:
        # 1. 权限检查
        await _require_actor_superadmin_when_target_protected(int(user_id), current_user)
        
        # 2. 更新状态
        await UserService.update_status(user_id, is_approved)
        
        # 3. 记录审计日志
        await UserAdminAuditService.log(
            action="user.update_status",
            actor=current_user,
            target_user_id=int(user_id),
            request_ip=_get_request_ip(request) if request else None,
            detail={"is_approved": bool(is_approved)},
        )
        return {"code": 200, "message": "状态更新成功"}
    except Exception as e:
        return {"code": 500, "message": f"更新状态失败: {str(e)}"}

# --- Profile routes (个人中心相关) ---

@router.get("/profile", response_model=dict)
async def get_profile(current_user: dict = Depends(deps.get_current_user)):
    """
    获取个人信息
    
    获取当前登录用户的完整资料。
    """
    try:
        user = await UserService.get_user_by_id(current_user.get("id"))
        if not user:
            return {"code": 404, "message": "用户不存在"}
        return {"code": 200, "data": user}
    except Exception as e:
        return {"code": 500, "message": f"获取信息失败: {str(e)}"}

@router.post("/profile/update", response_model=dict)
async def update_profile(
    data: UserUpdate,
    request: Request,
    current_user: dict = Depends(deps.get_current_user)
):
    """
    更新个人信息
    
    用户自助修改昵称、密码、邮箱等。
    """
    try:
        # Exclude password from audit log
        log_detail = data.model_dump(exclude_none=True)
        if "password" in log_detail:
            del log_detail["password"]

        await UserService.update_profile(current_user.get("id"), data)

        await UserAdminAuditService.log(
            action="user.profile_update",
            actor=current_user,
            target_user_id=current_user.get("id"),
            request_ip=_get_request_ip(request),
            detail=log_detail,
        )

        return {"code": 200, "message": "更新成功"}
    except ValueError as e:
        return {"code": 400, "message": str(e)}
    except Exception as e:
        return {"code": 500, "message": f"更新失败: {str(e)}"}


@router.post("/avatar/upload", response_model=dict)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: dict = Depends(deps.get_current_user),
):
    """
    上传头像
    
    上传并更新用户头像。
    支持图片格式校验，会调用远程图片存储服务。
    """
    try:
        uid = int(current_user.get("id"))
        existing = await User.filter(id=uid).first()
        old_key = str(getattr(existing, "avatar_key", "") or "").strip() if existing else ""
        if not old_key:
            old_url = str(getattr(existing, "avatar_url", "") or "").strip() if existing else ""
            if old_url:
                try:
                    parsed = urlparse(old_url)
                    candidate = str(parsed.path or "").lstrip("/")
                    if candidate:
                        old_key = candidate
                except Exception:
                    pass

        # 1. 调用头像服务处理上传 (包含格式校验、压缩、转存)
        result = await AvatarService.upload_avatar(file)
        avatar_url = str(result.url or "").strip()
        avatar_key = str(getattr(result, "key", "") or "").strip()
        if not avatar_url:
            return {"code": 500, "message": "头像上传失败: 返回链接为空"}
            
        # 2. 更新数据库记录
        await User.filter(id=uid).update(avatar_url=avatar_url, avatar_key=avatar_key or None)

        if old_key and old_key != avatar_key:
            try:
                await ImageStorageService.delete_remote(old_key)
            except Exception:
                logger.exception("delete old avatar failed")
        return {"code": 200, "data": {"avatar_url": avatar_url}}
    except ValueError as e:
        return {"code": 400, "message": str(e)}
    except RemoteImageApiError as e:
        # 处理远程图片 API 的特定错误
        http_status = getattr(e, "status_code", None)
        if http_status == 429:
            return {"code": 429, "message": str(e)}
        if http_status in (401, 403):
            return {"code": 401, "message": str(e)}
        return {"code": 500, "message": str(e)}
    except Exception as e:
        return {"code": 500, "message": f"上传失败: {str(e)}"}

@router.get("/profile/summary", response_model=dict)
async def get_profile_summary(current_user: dict = Depends(deps.get_current_user)):
    """
    获取个人概况
    
    返回用户的工单统计、消息未读数等摘要信息。
    用于首页展示。
    """
    try:
        user_id = current_user.get("id")
        username = current_user.get("username") or ""
        if not user_id:
            return {"code": 401, "message": "无法获取用户信息"}
        data = await UserService.get_profile_summary(int(user_id), username)
        return {"code": 200, "data": data}
    except Exception as e:
        return {"code": 500, "message": f"获取统计失败: {str(e)}"}

class EmailVerifyRequest(BaseModel):
    email: str

@router.get("/profile/email/pending", response_model=dict)
async def get_email_verify_pending(current_user: dict = Depends(deps.get_current_user)):
    """
    获取待验证的邮箱
    
    查询当前用户是否发起了邮箱验证请求。
    """
    try:
        try:
            disabled = await get_disabled_permission_codes_cached()
            if "sys:email:verify" in {str(c) for c in (disabled or [])}:
                return {"code": 403, "message": "邮箱验证权限已关闭"}
        except Exception:
            pass
        data = await UserService.get_pending_email_verification(int(current_user.get("id")))
        return {"code": 200, "data": data}
    except Exception as e:
        return {"code": 500, "message": f"获取失败: {str(e)}"}

@router.post("/profile/email/request", response_model=dict)
async def request_email_verify(
    data: EmailVerifyRequest,
    request: Request,
    current_user: dict = Depends(deps.get_current_user),
):
    """
    发起邮箱验证
    
    发送验证邮件到指定邮箱。
    """
    try:
        # 1. 功能开关检查
        try:
            disabled = await get_disabled_permission_codes_cached()
            if "sys:email:verify" in {str(c) for c in (disabled or [])}:
                return {"code": 403, "message": "邮箱验证权限已关闭"}
        except Exception:
            pass
            
        # 2. 获取客户端信息
        xff = request.headers.get("x-forwarded-for")
        ip = (xff.split(",")[0].strip() if xff else None) or (request.client.host if request.client else None)
        base_url = str(request.base_url).rstrip("/")
        
        # 3. 发送验证邮件
        payload = await UserService.request_email_verification(
            user_id=int(current_user.get("id")),
            email=data.email,
            request_ip=ip,
            confirm_base_url=base_url,
        )
        return {"code": 200, "message": "验证邮件已发送", "data": payload}
    except ValueError as e:
        return {"code": 400, "message": str(e)}
    except Exception as e:
        return {"code": 500, "message": f"发送失败: {str(e)}"}

@router.get("/profile/email/confirm", response_class=HTMLResponse)
async def confirm_email_verify(token: str):
    """
    确认邮箱验证 (HTML)
    
    处理验证链接点击，返回 HTML 页面展示结果。
    """
    try:
        # 1. 功能开关检查
        try:
            disabled = await get_disabled_permission_codes_cached()
            if "sys:email:verify" in {str(c) for c in (disabled or [])}:
                # 返回 HTML 错误页
                html = """
                <!doctype html>
                <html lang="zh-CN">
                <head>
                  <meta charset="utf-8" />
                  <meta name="viewport" content="width=device-width, initial-scale=1" />
                  <title>邮箱验证不可用</title>
                  <style>
                    body { font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,'Noto Sans','Liberation Sans',sans-serif; padding: 24px; }
                    .card { max-width: 560px; margin: 10vh auto; border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px; }
                    h1 { font-size: 18px; margin: 0 0 8px; }
                    p { margin: 0; color: #374151; line-height: 1.6; }
                  </style>
                </head>
                <body>
                  <div class="card">
                    <h1>邮箱验证不可用</h1>
                    <p>当前系统已关闭邮箱验证功能，请联系管理员。</p>
                  </div>
                </body>
                </html>
                """
                return HTMLResponse(content=html, status_code=403)
        except Exception:
            pass
            
        # 2. 执行验证
        result = await UserService.confirm_email_verification(token)
        email = result.get("email") or ""
        
        # 3. 返回成功 HTML
        html = f"""
        <!doctype html>
        <html lang="zh-CN">
        <head>
          <meta charset="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <title>邮箱验证成功</title>
          <style>
            body {{ font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,'Noto Sans','Liberation Sans',sans-serif; padding: 24px; }}
            .card {{ max-width: 560px; margin: 10vh auto; border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px; }}
            h1 {{ font-size: 18px; margin: 0 0 8px; }}
            p {{ margin: 0; color: #374151; line-height: 1.6; }}
            .muted {{ color: #6b7280; font-size: 13px; margin-top: 10px; }}
          </style>
        </head>
        <body>
          <div class="card">
            <h1>邮箱验证成功</h1>
            <p>邮箱 <b>{email}</b> 已绑定到你的账号。</p>
            <p class="muted">你可以返回系统个人中心刷新查看当前邮箱。</p>
          </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html, status_code=200)
    except ValueError as e:
        # 返回业务错误 HTML
        html = f"""
        <!doctype html>
        <html lang="zh-CN">
        <head>
          <meta charset="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <title>邮箱验证失败</title>
          <style>
            body {{ font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,'Noto Sans','Liberation Sans',sans-serif; padding: 24px; }}
            .card {{ max-width: 560px; margin: 10vh auto; border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px; }}
            h1 {{ font-size: 18px; margin: 0 0 8px; }}
            p {{ margin: 0; color: #374151; line-height: 1.6; }}
          </style>
        </head>
        <body>
          <div class="card">
            <h1>邮箱验证失败</h1>
            <p>{str(e)}</p>
          </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html, status_code=400)
    except Exception as e:
        # 返回系统错误 HTML
        html = f"""
        <!doctype html>
        <html lang="zh-CN">
        <head>
          <meta charset="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <title>邮箱验证失败</title>
          <style>
            body {{ font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,'Noto Sans','Liberation Sans',sans-serif; padding: 24px; }}
            .card {{ max-width: 560px; margin: 10vh auto; border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px; }}
            h1 {{ font-size: 18px; margin: 0 0 8px; }}
            p {{ margin: 0; color: #374151; line-height: 1.6; }}
          </style>
        </head>
        <body>
          <div class="card">
            <h1>邮箱验证失败</h1>
            <p>服务器错误：{str(e)}</p>
          </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html, status_code=500)


# --- 批量导入相关模型 ---

class UserImportParseResponse(BaseModel):
    token: str
    columns: list[str]
    preview_rows: list[dict]
    total_rows: int
    filename: str


class UserImportCommitOptions(BaseModel):
    default_password: Optional[str] = None
    default_role_code: Optional[str] = None
    approve_users: bool = True
    on_duplicate: str = "skip"
    password_is_hashed: bool = False


class UserImportCommitRequest(BaseModel):
    token: str
    mapping: dict[str, Optional[str]]
    options: Optional[UserImportCommitOptions] = None


class UserImportCommitResponse(BaseModel):
    created: int
    skipped: int
    failed: int
    errors: list[dict]
    timing_ms: Optional[dict] = None


class UserImportCancelRequest(BaseModel):
    token: str


def _normalize_cell_value(v: Any) -> Optional[str]:
    """标准化单元格值 (去空、转字符串)"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v)
    s = str(v).strip()
    return s if s else None

def _looks_like_password_hash(s: str) -> bool:
    """检查字符串是否已经是哈希值"""
    v = str(s or "").strip()
    if not v:
        return False
    if v.startswith("$2a$") or v.startswith("$2b$") or v.startswith("$2y$"):
        return True
    if v.startswith("$bcrypt-sha256$"):
        return True
    if v.startswith("$pbkdf2-"):
        return True
    if v.startswith("$argon2"):
        return True
    return False


def _normalize_headers(raw_headers: list[Any]) -> list[str]:
    """标准化表头 (处理重复列名)"""
    headers: list[str] = []
    seen: dict[str, int] = {}
    for h in raw_headers:
        name = _normalize_cell_value(h) or ""
        if not name:
            name = "未命名列"
        base = name
        idx = seen.get(base, 0)
        if idx > 0:
            name = f"{base}_{idx + 1}"
        seen[base] = idx + 1
        headers.append(name)
    return headers


async def _read_import_rows_from_file(file: UploadFile) -> tuple[list[str], list[dict[str, Any]]]:
    """读取上传文件 (CSV/Excel) 并返回行数据"""
    filename = str(file.filename or "")
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    raw = await file.read()
    if raw is None:
        raw = b""
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError("文件过大（最大 10MB）")

    # 处理 CSV
    if ext in {"csv"}:
        text = None
        # 尝试多种编码
        for enc in ("utf-8-sig", "utf-8", "gbk"):
            try:
                text = raw.decode(enc)
                break
            except Exception:
                continue
        if text is None:
            text = raw.decode("latin1", errors="ignore")
        reader = csv.reader(io.StringIO(text))
        rows = [r for r in reader if any(str(c).strip() for c in r)]
        if not rows:
            raise ValueError("文件内容为空")
        headers = _normalize_headers(rows[0])
        data_rows = []
        for r in rows[1:]:
            obj = {}
            for i, col in enumerate(headers):
                obj[col] = r[i] if i < len(r) else None
            data_rows.append(obj)
        return headers, data_rows

    # 处理 Excel
    if ext in {"xlsx"}:
        try:
            from openpyxl import load_workbook  # type: ignore
        except Exception:
            raise ValueError("当前后端未安装 xlsx 解析依赖，请改用 CSV 文件")
        wb = load_workbook(filename=io.BytesIO(raw), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        all_rows = []
        for row in ws.iter_rows(values_only=True):
            all_rows.append(list(row))
        all_rows = [r for r in all_rows if any(_normalize_cell_value(c) for c in r)]
        if not all_rows:
            raise ValueError("文件内容为空")
        headers = _normalize_headers(all_rows[0])
        data_rows = []
        for r in all_rows[1:]:
            obj = {}
            for i, col in enumerate(headers):
                obj[col] = r[i] if i < len(r) else None
            data_rows.append(obj)
        return headers, data_rows

    raise ValueError("仅支持 .csv 或 .xlsx 文件")


@router.post("/import/parse", response_model=dict)
async def parse_user_import_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(deps.get_current_user),
    _: dict = Depends(PermissionChecker(["sys:user:import"])),
):
    """
    解析用户导入文件
    
    上传 CSV 或 Excel 文件，解析并预览数据。
    返回导入 Token，用于后续的进度查询和确认导入。
    
    Args:
        file: 用户数据文件 (.csv 或 .xlsx)
    """
    try:
        # 1. 解析文件
        columns, rows = await _read_import_rows_from_file(file)
        # 限制预览行数，防止 Redis 爆炸
        limited_rows = rows[:5000]
        
        # 2. 生成 Token 并缓存解析结果
        token = secrets.token_urlsafe(16)
        redis_client = redis_manager.get_client()
        payload = {
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "filename": str(file.filename or ""),
            "columns": columns,
            "rows": limited_rows,
        }
        await redis_client.set(_import_data_key(token), json.dumps(payload, ensure_ascii=False), ex=_IMPORT_TTL_SECONDS)
        
        # 3. 初始化状态
        await _clear_user_import_cancel(redis_client, token)
        try:
            await redis_client.delete(_import_result_key(token))
        except Exception:
            pass
            
        # 4. 设置初始进度
        await _set_user_import_progress(
            redis_client,
            token,
            100,
            "ready",
            "解析完成，等待导入",
            detail={
                "phase": "ready",
                "total": len(limited_rows),
                "processed": 0,
                "created": 0,
                "skipped": 0,
                "failed": 0,
            },
        )
        
        # 5. 返回预览数据 (前 20 行)
        preview = []
        for r in limited_rows[:20]:
            preview.append({k: _normalize_cell_value(v) for k, v in r.items()})
        return {
            "code": 200,
            "data": UserImportParseResponse(
                token=token,
                columns=columns,
                preview_rows=preview,
                total_rows=len(limited_rows),
                filename=str(file.filename or ""),
            ).model_dump(),
        }
    except ValueError as e:
        return {"code": 400, "message": str(e)}
    except Exception as e:
        return {"code": 500, "message": f"解析失败: {str(e)}"}

@router.get("/import/progress", response_model=dict)
async def get_user_import_progress(
    token: str,
    current_user: dict = Depends(deps.get_current_user),
    _: dict = Depends(PermissionChecker(["sys:user:import"])),
):
    """
    获取导入进度
    
    根据 Token 查询当前的导入状态和进度百分比。
    """
    try:
        t = str(token or "").strip()
        if not t:
            return {"code": 400, "message": "缺少 token"}
        redis_client = redis_manager.get_client()
        raw = await redis_client.get(_import_progress_key(t))
        if not raw:
            return {"code": 404, "message": "暂无进度或已过期"}
        try:
            data = json.loads(raw)
        except Exception:
            return {"code": 500, "message": "进度数据损坏"}
        return {"code": 200, "data": data}
    except Exception as e:
        return {"code": 500, "message": f"获取进度失败: {str(e)}"}

@router.post("/import/cancel", response_model=dict)
async def cancel_user_import(
    data: UserImportCancelRequest,
    current_user: dict = Depends(deps.get_current_user),
    _: dict = Depends(PermissionChecker(["sys:user:import"])),
):
    """
    取消导入任务
    
    中断正在进行的导入过程。
    """
    try:
        t = str(data.token or "").strip()
        if not t:
            return {"code": 400, "message": "缺少 token"}
        redis_client = redis_manager.get_client()
        raw = await redis_client.get(_import_progress_key(t))
        if raw:
            try:
                p = json.loads(raw)
                st = str((p or {}).get("status") or "").lower()
                if st in {"done"}:
                    return {"code": 200, "message": "导入已完成，无需停止"}
                if st in {"canceled", "cancelled"}:
                    return {"code": 200, "message": "导入已停止"}
            except Exception:
                pass
        
        # 设置取消标志
        await _set_user_import_cancel(redis_client, t)
        
        # 更新状态为 canceled
        await _set_user_import_progress(
            redis_client,
            t,
            100,
            "canceled",
            "已请求停止导入",
            detail={"phase": "canceled"},
        )
        try:
            await UserAdminAuditService.log(
                action="user.import_cancel",
                actor=current_user,
                request_ip=_get_request_ip(None),
                detail={"token": t},
            )
        except Exception:
            logger.exception("audit log for user.import_cancel failed")
        return {"code": 200, "message": "已请求停止导入"}
    except Exception as e:
        return {"code": 500, "message": f"停止失败: {str(e)}"}

@router.get("/import/result", response_model=dict)
async def get_user_import_result(
    token: str,
    current_user: dict = Depends(deps.get_current_user),
    _: dict = Depends(PermissionChecker(["sys:user:import"])),
):
    """
    获取导入结果
    
    导入完成后，获取详细的统计信息 (成功数、失败数、错误详情等)。
    """
    try:
        t = str(token or "").strip()
        if not t:
            return {"code": 400, "message": "缺少 token"}
        redis_client = redis_manager.get_client()
        data = await _get_user_import_result(redis_client, t)
        if not data:
            return {"code": 404, "message": "暂无结果或已过期"}
        return {"code": 200, "data": data}
    except Exception as e:
        return {"code": 500, "message": f"获取结果失败: {str(e)}"}


@router.post("/import/commit", response_model=dict)
async def commit_user_import(
    data: UserImportCommitRequest,
    current_user: dict = Depends(deps.get_current_user),
    _: dict = Depends(PermissionChecker(["sys:user:import"])),
):
    """
    提交导入任务
    
    确认字段映射关系，开始执行后台导入任务。
    这是一个长耗时操作，建议配合进度接口轮询。
    
    Process:
    1. 检查任务状态和取消信号
    2. 加载解析后的临时数据
    3. 加载系统角色列表
    4. 遍历数据行，校验字段，构建候选数据
    5. 检查数据库中已存在的用户名 (查重)
    6. 并行计算密码哈希 (耗时操作)
    7. 批量写入用户数据 (事务保护)
    8. 批量绑定用户角色
    """
    token_for_progress = ""
    phase_for_log = ""
    timing_ms: dict[str, int] = {}
    t_total_start = time.perf_counter()
    last_sql = ""
    last_sql_params: dict[str, Any] = {}
    try:
        # --- 阶段 1: 初始化检查 ---
        phase_for_log = "parse_request"
        token = str(data.token or "").strip()
        token_for_progress = token
        if not token:
            return {"code": 400, "message": "缺少 token"}

        redis_client = redis_manager.get_client()
        # 如果已有结果，直接返回
        existing_result = await _get_user_import_result(redis_client, token)
        if existing_result:
            return {"code": 200, "data": existing_result}

        phase_for_log = "check_cancelled"
        if await _is_user_import_cancelled(redis_client, token):
            timing_ms["total"] = int((time.perf_counter() - t_total_start) * 1000)
            result = UserImportCommitResponse(
                created=0,
                skipped=0,
                failed=0,
                errors=[{"reason": "已请求停止导入"}],
                timing_ms=timing_ms,
            ).model_dump()
            await _set_user_import_result(redis_client, token, result)
            await _set_user_import_progress(
                redis_client,
                token,
                100,
                "canceled",
                "已停止导入",
                detail={"phase": "canceled"},
            )
            return {"code": 200, "message": "已停止导入", "data": result}
        
        phase_for_log = "prepare"
        await _set_user_import_progress(
            redis_client,
            token,
            3,
            "importing",
            "准备导入",
            detail={"phase": "prepare"},
        )

        # 解析字段映射
        mapping = {str(k): (str(v).strip() if v is not None and str(v).strip() else None) for k, v in (data.mapping or {}).items()}
        username_col = mapping.get("username")
        if not username_col:
            await _set_user_import_progress(redis_client, token, 100, "error", "必须映射用户名字段")
            return {"code": 400, "message": "必须映射用户名字段"}

        password_col = mapping.get("password")
        nickname_col = mapping.get("nickname")
        email_col = mapping.get("email")
        role_col = mapping.get("role_code")

        options = data.options or UserImportCommitOptions()
        default_password = (options.default_password or "").strip() or None
        default_role_code = (options.default_role_code or "").strip().lower() or None
        approve_users = bool(options.approve_users)
        on_duplicate = (options.on_duplicate or "skip").strip().lower()
        if on_duplicate not in {"skip"}:
            on_duplicate = "skip"

        # --- 阶段 2: 加载数据 ---
        phase_for_log = "load_rows"
        raw = await redis_client.get(_import_data_key(token))
        if not raw:
            await _set_user_import_progress(redis_client, token, 100, "error", "导入 token 已过期，请重新上传")
            return {"code": 400, "message": "导入 token 已过期，请重新上传"}
        try:
            parsed = json.loads(raw)
        except Exception:
            await _set_user_import_progress(redis_client, token, 100, "error", "导入数据损坏，请重新上传")
            return {"code": 400, "message": "导入数据损坏，请重新上传"}

        rows = parsed.get("rows") or []
        total_rows = len(rows) if isinstance(rows, list) else 0
        if not isinstance(rows, list) or len(rows) == 0:
            await _set_user_import_progress(redis_client, token, 100, "error", "导入数据为空")
            return {"code": 400, "message": "导入数据为空"}

        # --- 阶段 3: 加载角色 ---
        phase_for_log = "load_roles"
        await _set_user_import_progress(
            redis_client,
            token,
            10,
            "importing",
            "读取角色信息",
            detail={"phase": "load_roles", "total": total_rows, "processed": 0, "created": 0, "skipped": 0, "failed": 0},
        )
        t_roles_start = time.perf_counter()
        roles_rows = await db.fetch_all("SELECT id, code, is_default FROM roles")
        timing_ms["load_roles"] = int((time.perf_counter() - t_roles_start) * 1000)
        
        # 建立角色代码到 ID 的映射
        role_id_by_code = {str(r["code"]).strip().lower(): int(r["id"]) for r in (roles_rows or []) if r and r.get("code")}
        protected = {"superadmin", "super_admin", "super-admin"}
        role_id_fallback = role_id_by_code.get(default_role_code) if default_role_code and default_role_code not in protected else None
        system_default_role_id = None
        for r in roles_rows or []:
            try:
                code = str(r.get("code") or "").strip().lower()
                if bool(r.get("is_default")) and code and code not in protected:
                    system_default_role_id = int(r.get("id") or 0) or None
                    break
            except Exception:
                continue

        created = 0
        skipped = 0
        failed = 0
        errors: list[dict] = []

        candidates: list[dict] = []
        seen_usernames: set[str] = set()

        # --- 阶段 4: 校验并构建数据 ---
        phase_for_log = "validate"
        await _set_user_import_progress(
            redis_client,
            token,
            18,
            "importing",
            "校验并生成导入数据",
            detail={"phase": "validate", "total": total_rows, "processed": 0, "created": 0, "skipped": skipped, "failed": failed},
        )
        t_build_start = time.perf_counter()
        for idx, r in enumerate(rows, start=1):
            if not isinstance(r, dict):
                failed += 1
                errors.append({"row": idx, "reason": "行数据格式错误"})
                continue

            username = _normalize_cell_value(r.get(username_col))
            if not username:
                failed += 1
                errors.append({"row": idx, "reason": "用户名为空"})
                continue

            # 文件内查重
            if username in seen_usernames:
                skipped += 1
                errors.append({"row": idx, "username": username, "reason": "文件内用户名重复"})
                continue
            seen_usernames.add(username)

            password = _normalize_cell_value(r.get(password_col)) if password_col else None
            if not password:
                password = default_password
            if not password:
                failed += 1
                errors.append({"row": idx, "username": username, "reason": "缺少密码且未设置默认密码"})
                continue

            nickname = _normalize_cell_value(r.get(nickname_col)) if nickname_col else None
            email = _normalize_cell_value(r.get(email_col)) if email_col else None

            # 确定角色
            target_role_code = _normalize_cell_value(r.get(role_col)).lower() if role_col else None
            role_id = role_id_by_code.get(target_role_code) if target_role_code else None
            if role_id is None:
                role_id = role_id_fallback
            if role_id is None:
                role_id = system_default_role_id

            candidates.append(
                {
                    "row": idx,
                    "username": username,
                    "password": password,
                    "nickname": nickname,
                    "email": email,
                    "role_id": role_id,
                }
            )
            # 定期更新进度
            if idx % 200 == 0 or idx == total_rows:
                if await _is_user_import_cancelled(redis_client, token):
                    timing_ms["total"] = int((time.perf_counter() - t_total_start) * 1000)
                    result = UserImportCommitResponse(
                        created=created,
                        skipped=skipped,
                        failed=failed,
                        errors=errors,
                        timing_ms=timing_ms,
                    ).model_dump()
                    await _set_user_import_result(redis_client, token, result)
                    await _set_user_import_progress(
                        redis_client,
                        token,
                        100,
                        "canceled",
                        "已停止导入",
                        detail={"phase": "canceled", "total": total_rows, "processed": idx, "created": created, "skipped": skipped, "failed": failed},
                    )
                    return {"code": 200, "message": "已停止导入", "data": result}
                pct = 18 + int(12 * (idx / max(1, total_rows)))
                await _set_user_import_progress(
                    redis_client,
                    token,
                    pct,
                    "importing",
                    "正在校验数据",
                    detail={"phase": "validate", "total": total_rows, "processed": idx, "created": created, "skipped": skipped, "failed": failed},
                )
        timing_ms["build_candidates"] = int((time.perf_counter() - t_build_start) * 1000)

        if not candidates:
            # 没有有效数据
            timing_ms["total"] = int((time.perf_counter() - t_total_start) * 1000)
            result = UserImportCommitResponse(
                created=created,
                skipped=skipped,
                failed=failed,
                errors=errors,
                timing_ms=timing_ms,
            ).model_dump()
            await _set_user_import_result(redis_client, token, result)
            await _set_user_import_progress(
                redis_client,
                token,
                100,
                "done",
                "导入完成",
                detail={"phase": "done", "total": total_rows, "processed": total_rows, "created": created, "skipped": skipped, "failed": failed, "timing_ms": timing_ms},
            )
            return {
                "code": 200,
                "data": result,
            }

        # --- 阶段 5: 数据库查重 ---
        phase_for_log = "check_existing"
        await _set_user_import_progress(
            redis_client,
            token,
            40,
            "importing",
            "检查重复用户名",
            detail={"phase": "check_existing", "total": len(candidates), "processed": 0, "created": created, "skipped": skipped, "failed": failed},
        )
        t_dup_start = time.perf_counter()
        usernames = [c["username"] for c in candidates]
        # 批量查询已存在的用户
        existing_rows = await db.fetch_all(
            "SELECT username FROM users WHERE username = ANY($1::text[])",
            usernames,
        )
        existing = {str(r["username"]) for r in (existing_rows or []) if r and r.get("username")}
        timing_ms["check_existing"] = int((time.perf_counter() - t_dup_start) * 1000)

        to_insert: list[dict] = []
        for c in candidates:
            if c["username"] in existing:
                skipped += 1
                # 目前仅支持跳过，未来可支持 overwrite
                continue
            to_insert.append(c)

        if not to_insert:
            # 全部重复
            await _set_user_import_progress(redis_client, token, 100, "done", "导入完成")
            timing_ms["total"] = int((time.perf_counter() - t_total_start) * 1000)
            result = UserImportCommitResponse(
                created=created,
                skipped=skipped,
                failed=failed,
                errors=errors,
                timing_ms=timing_ms,
            ).model_dump()
            await _set_user_import_result(redis_client, token, result)
            return {
                "code": 200,
                "data": result,
            }

        # --- 阶段 6: 密码哈希 (CPU 密集型) ---
        phase_for_log = "hash_passwords"
        await _set_user_import_progress(redis_client, token, 55, "importing", "生成密码")
        t_hash_start = time.perf_counter()

        usernames_ins: list[str] = []
        passwords_ins: list[str] = []
        nicknames_ins: list[str] = []
        emails_ins: list[Optional[str]] = []
        approved_ins: list[bool] = []
        perms_ins: list[str] = []
        role_by_username: dict[str, Optional[int]] = {}

        default_perms_json = ["sys:monitor:view"]
        default_perms_text = json.dumps(default_perms_json, ensure_ascii=False)
        password_is_hashed = bool(getattr(options, "password_is_hashed", False))
        total_items = max(1, len(to_insert))
        batch_size = 200

        loop = asyncio.get_running_loop()
        # 分批处理，避免长时间占用 CPU
        for start in range(0, len(to_insert), batch_size):
            if await _is_user_import_cancelled(redis_client, token):
                timing_ms["total"] = int((time.perf_counter() - t_total_start) * 1000)
                result = UserImportCommitResponse(
                    created=created,
                    skipped=skipped,
                    failed=failed,
                    errors=errors,
                    timing_ms=timing_ms,
                ).model_dump()
                await _set_user_import_result(redis_client, token, result)
                await _set_user_import_progress(
                    redis_client,
                    token,
                    100,
                    "canceled",
                    "已停止导入",
                    detail={"phase": "canceled", "total": len(to_insert), "processed": len(usernames_ins) + failed, "created": created, "skipped": skipped, "failed": failed},
                )
                return {"code": 200, "message": "已停止导入", "data": result}
            batch = to_insert[start : start + batch_size]

            # 筛选需要计算哈希的密码
            needs_hash: list[str] = []
            needs_hash_idx: list[int] = []
            for i, c in enumerate(batch):
                pw = str(c["password"] or "")
                if password_is_hashed:
                    continue
                if _looks_like_password_hash(pw):
                    continue
                needs_hash.append(pw)
                needs_hash_idx.append(i)

            # 使用线程池并行计算哈希
            hashed_results: list[Any] = []
            if needs_hash:
                futures = [loop.run_in_executor(_HASH_EXECUTOR, get_password_hash, pw) for pw in needs_hash]
                hashed_results = await asyncio.gather(*futures, return_exceptions=True)

            hashed_by_i: dict[int, Any] = {}
            for pos, i in enumerate(needs_hash_idx):
                hashed_by_i[i] = hashed_results[pos]

            # 组装最终写入数据
            for i, c in enumerate(batch):
                pw_raw = str(c["password"] or "")
                if password_is_hashed:
                    if not _looks_like_password_hash(pw_raw):
                        failed += 1
                        errors.append(
                            {
                                "row": int(c["row"]),
                                "username": c["username"],
                                "reason": "密码不符合哈希格式，请关闭“已加密”或提供标准哈希",
                            }
                        )
                        continue
                    hashed_pw = pw_raw
                else:
                    if _looks_like_password_hash(pw_raw):
                        hashed_pw = pw_raw
                    else:
                        hashed_val = hashed_by_i.get(i)
                        if isinstance(hashed_val, Exception):
                            failed += 1
                            errors.append({"row": int(c["row"]), "username": c["username"], "reason": str(hashed_val)})
                            continue
                        hashed_pw = str(hashed_val)

                usernames_ins.append(c["username"])
                passwords_ins.append(hashed_pw)
                nicknames_ins.append(c["nickname"] or c["username"])
                emails_ins.append(c["email"])
                approved_ins.append(bool(approve_users))
                perms_ins.append(default_perms_text)
                role_by_username[c["username"]] = c.get("role_id")

            done_hash = len(usernames_ins) + failed
            pct = 55 + int(35 * (done_hash / total_items))
            await _set_user_import_progress(
                redis_client,
                token,
                pct,
                "importing",
                "生成密码与写入数据",
                detail={"phase": "hash_passwords", "total": len(to_insert), "processed": done_hash, "created": created, "skipped": skipped, "failed": failed},
            )

        timing_ms["hash_passwords"] = int((time.perf_counter() - t_hash_start) * 1000)

        if not usernames_ins:
            await _set_user_import_progress(redis_client, token, 100, "done", "导入完成")
            timing_ms["total"] = int((time.perf_counter() - t_total_start) * 1000)
            result = UserImportCommitResponse(
                created=created,
                skipped=skipped,
                failed=failed,
                errors=errors,
                timing_ms=timing_ms,
            ).model_dump()
            await _set_user_import_result(redis_client, token, result)
            return {
                "code": 200,
                "data": result,
            }

        # --- 阶段 7: 批量写入数据库 ---
        phase_for_log = "db_insert"
        await _set_user_import_progress(
            redis_client,
            token,
            92,
            "importing",
            "写入用户数据",
            detail={"phase": "db_insert", "total": len(usernames_ins), "processed": 0, "created": created, "skipped": skipped, "failed": failed},
        )
        t_insert_start = time.perf_counter()
        pool = db.get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                total_ins = len(usernames_ins)
                chunk_size = 500
                processed_ins = 0
                for start in range(0, total_ins, chunk_size):
                    phase_for_log = "db_insert"
                    if await _is_user_import_cancelled(redis_client, token):
                        # 处理事务中的取消
                        timing_ms["db_insert_and_roles"] = int((time.perf_counter() - t_insert_start) * 1000)
                        timing_ms["total"] = int((time.perf_counter() - t_total_start) * 1000)
                        result = UserImportCommitResponse(
                            created=created,
                            skipped=skipped,
                            failed=failed,
                            errors=errors,
                            timing_ms=timing_ms,
                        ).model_dump()
                        await _set_user_import_result(redis_client, token, result)
                        await _set_user_import_progress(
                            redis_client,
                            token,
                            100,
                            "canceled",
                            "已停止导入",
                            detail={"phase": "canceled", "total": total_rows, "processed": processed_ins, "created": created, "skipped": skipped, "failed": failed},
                        )
                        return {"code": 200, "message": "已停止导入", "data": result}

                    end = min(total_ins, start + chunk_size)
                    chunk_usernames = usernames_ins[start:end]
                    chunk_passwords = passwords_ins[start:end]
                    chunk_nicknames = nicknames_ins[start:end]
                    chunk_emails = emails_ins[start:end]
                    chunk_approved = approved_ins[start:end]
                    chunk_perms = perms_ins[start:end]

                    # 记录最后执行的 SQL 用于错误诊断
                    last_sql = """
                        INSERT INTO users (username, password, nickname, email, is_approved, permissions)
                        SELECT x.username, x.password, x.nickname, x.email, x.is_approved, x.permissions::jsonb
                        FROM UNNEST(
                            $1::text[],
                            $2::text[],
                            $3::text[],
                            $4::text[],
                            $5::bool[],
                            $6::text[]
                        ) AS x(username, password, nickname, email, is_approved, permissions)
                        ON CONFLICT (username) DO NOTHING
                        RETURNING id, username
                    """
                    sample_perm = chunk_perms[0] if chunk_perms else None
                    sample_perm_type = type(sample_perm).__name__ if sample_perm is not None else None
                    parsed_perm_kind: Optional[str] = None
                    try:
                        if isinstance(sample_perm, str) and sample_perm.strip():
                            parsed = json.loads(sample_perm)
                            parsed_perm_kind = type(parsed).__name__
                    except Exception:
                        parsed_perm_kind = "invalid_json"
                    last_sql_params = {
                        "chunk_range": [int(start), int(end)],
                        "chunk_len": int(len(chunk_usernames)),
                        "approved_sample": bool(chunk_approved[0]) if chunk_approved else None,
                        "permissions_sample_type": sample_perm_type,
                        "permissions_sample_parsed_kind": parsed_perm_kind,
                        "permissions_sample_len": int(len(sample_perm)) if isinstance(sample_perm, str) else None,
                    }
                    
                    # 执行批量插入
                    inserted = await conn.fetch(
                        """
                        INSERT INTO users (username, password, nickname, email, is_approved, permissions)
                        SELECT x.username, x.password, x.nickname, x.email, x.is_approved, x.permissions::jsonb
                        FROM UNNEST(
                            $1::text[],
                            $2::text[],
                            $3::text[],
                            $4::text[],
                            $5::bool[],
                            $6::text[]
                        ) AS x(username, password, nickname, email, is_approved, permissions)
                        ON CONFLICT (username) DO NOTHING
                        RETURNING id, username
                        """,
                        chunk_usernames,
                        chunk_passwords,
                        chunk_nicknames,
                        chunk_emails,
                        chunk_approved,
                        chunk_perms,
                    )

                    inserted_map = {str(r["username"]): int(r["id"]) for r in (inserted or []) if r and r.get("username")}
                    created += len(inserted_map)
                    skipped += max(0, len(chunk_usernames) - len(inserted_map))
                    processed_ins = end

                    pct = 92 + int(4 * (processed_ins / max(1, total_ins)))
                    await _set_user_import_progress(
                        redis_client,
                        token,
                        pct,
                        "importing",
                        "写入用户数据",
                        detail={"phase": "db_insert", "total": total_ins, "processed": processed_ins, "created": created, "skipped": skipped, "failed": failed},
                    )

                    # --- 阶段 8: 绑定角色 ---
                    role_pairs: list[tuple[int, int]] = []
                    for uname, uid in inserted_map.items():
                        rid = role_by_username.get(uname)
                        if rid:
                            role_pairs.append((int(uid), int(rid)))

                    if role_pairs:
                        phase_for_log = "bind_roles"
                        await _set_user_import_progress(
                            redis_client,
                            token,
                            max(pct, 93),
                            "importing",
                            "绑定用户角色",
                            detail={"phase": "bind_roles", "total": total_ins, "processed": processed_ins, "created": created, "skipped": skipped, "failed": failed},
                        )
                        await conn.executemany(
                            "INSERT INTO user_roles (user_id, role_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                            role_pairs,
                        )
        timing_ms["db_insert_and_roles"] = int((time.perf_counter() - t_insert_start) * 1000)

        timing_ms["total"] = int((time.perf_counter() - t_total_start) * 1000)
        result = UserImportCommitResponse(
            created=created,
            skipped=skipped,
            failed=failed,
            errors=errors,
            timing_ms=timing_ms,
        ).model_dump()
        
        # 9. 导入完成，保存结果
        await _set_user_import_result(redis_client, token, result)
        await _set_user_import_progress(
            redis_client,
            token,
            100,
            "done",
            "导入完成",
            detail={"phase": "done", "total": total_rows, "processed": total_rows, "created": created, "skipped": skipped, "failed": failed, "timing_ms": timing_ms},
        )
        try:
            await UserAdminAuditService.log(
                action="user.import_commit",
                actor=current_user,
                request_ip=_get_request_ip(None),  # No request object here
                detail={
                    "token": token,
                    "filename": parsed.get("filename", ""),
                    "total_rows": total_rows,
                    "created": created,
                    "skipped": skipped,
                    "failed": failed,
                    "errors_count": len(errors),
                    "on_duplicate": on_duplicate,
                    "default_role_code": default_role_code,
                    "approve_users": approve_users,
                },
            )
        except Exception:
            logger.exception("audit log for user.import_commit failed")
        return {
            "code": 200,
            "data": result,
        }
    except Exception as e:
        # 异常处理：记录日志并保存错误状态
        try:
            logger.exception(
                "user_import commit failed token=%s phase=%s err=%s",
                token_for_progress,
                phase_for_log,
                repr(e),
            )
        except Exception:
            pass
        try:
            if token_for_progress:
                redis_client = redis_manager.get_client()
                timing_ms["total"] = int((time.perf_counter() - t_total_start) * 1000)
                pg_info = {
                    "sqlstate": getattr(e, "sqlstate", None),
                    "detail": getattr(e, "detail", None),
                    "hint": getattr(e, "hint", None),
                    "position": getattr(e, "position", None),
                    "schema_name": getattr(e, "schema_name", None),
                    "table_name": getattr(e, "table_name", None),
                    "column_name": getattr(e, "column_name", None),
                    "constraint_name": getattr(e, "constraint_name", None),
                }
                pg_info = {k: v for k, v in pg_info.items() if v is not None}
                sql_snippet = None
                try:
                    raw = " ".join(str(last_sql or "").split())
                    if raw:
                        sql_snippet = raw[:600]
                except Exception:
                    sql_snippet = None
                extra = {
                    "phase": "error",
                    "phase_for_log": phase_for_log,
                    "timing_ms": timing_ms,
                    "last_sql_present": bool(last_sql.strip()),
                    "last_sql_snippet": sql_snippet,
                    "last_sql_params": last_sql_params or None,
                    "pg": pg_info or None,
                }
                await _set_user_import_progress(
                    redis_client,
                    token_for_progress,
                    100,
                    "error",
                    f"导入失败({phase_for_log}): {type(e).__name__}: {str(e)}",
                    detail=extra,
                )
        except Exception:
            pass
        return {"code": 500, "message": f"导入失败({phase_for_log}): {type(e).__name__}: {str(e)}"}


def _is_valid_email(email: str) -> bool:
    """验证邮箱格式"""
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", str(email or "").strip()))


@router.get("", response_model=dict)
@router.get("/", response_model=dict)
async def admin_list_users(
    q: str = Query("", max_length=200),
    is_approved: Optional[bool] = Query(None),
    include_deleted: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: dict = Depends(deps.get_current_user),
    _: dict = Depends(PermissionChecker(["sys:user:view"])),
):
    """
    用户列表管理
    
    管理员查看系统用户列表。
    支持按用户名/昵称/邮箱搜索，按状态筛选。
    
    Args:
        q: 搜索关键字
        is_approved: 审核状态筛选 (True/False)
        include_deleted: 是否包含已删除用户 (默认 False)
        page: 页码
        page_size: 每页数量
    """
    try:
        result = await UserService.admin_list_users(
            q=str(q or ""),
            is_approved=is_approved,
            include_deleted=bool(include_deleted),
            page=int(page),
            page_size=int(page_size),
        )
        return {
            "code": 200,
            "data": result.get("items") or [],
            "meta": {"total": int(result.get("total") or 0), "page": int(page), "page_size": int(page_size), "q": str(result.get("q") or "").strip()},
        }
    except Exception as e:
        return {"code": 500, "message": f"获取用户列表失败: {str(e)}"}


@router.get("/{user_id}", response_model=dict)
async def admin_get_user_detail(
    user_id: int,
    current_user: dict = Depends(deps.get_current_user),
    _: dict = Depends(PermissionChecker(["sys:user:view"])),
):
    """
    获取用户详情 (管理端)
    
    管理员获取指定用户的完整信息，包括角色、权限等。
    """
    try:
        data = await UserService.admin_get_user_detail(int(user_id))
        if not data:
            return {"code": 404, "message": "用户不存在"}
        return {"code": 200, "data": data}
    except Exception as e:
        return {"code": 500, "message": f"获取用户详情失败: {str(e)}"}


@router.post("", response_model=dict)
@router.post("/", response_model=dict)
async def admin_create_user(
    user_in: UserCreate,
    request: Request,
    current_user: dict = Depends(deps.get_current_user),
    _: dict = Depends(PermissionChecker(["sys:user:manage"])),
):
    """
    创建用户 (管理端)
    
    管理员手动创建用户。
    可设置用户名、密码、昵称、邮箱等信息。
    """
    try:
        user_id = await UserService.create_user(user_in)
        if user_in.role_ids:
            await UserService.update_user_roles(user_id, user_in.role_ids)
        await UserAdminAuditService.log(
            action="user.create",
            actor=current_user,
            target_user_id=int(user_id),
            request_ip=_get_request_ip(request),
            detail={"username": user_in.username, "email": user_in.email, "nickname": user_in.nickname},
        )
        return {"code": 200, "message": "用户创建成功", "data": {"id": user_id}}
    except ValueError as e:
        return {"code": 400, "message": str(e)}
    except Exception as e:
        return {"code": 500, "message": f"创建用户失败: {str(e)}"}


@router.put("/{user_id}", response_model=dict)
async def admin_update_user(
    user_id: int,
    data: AdminUserUpdate,
    request: Request,
    current_user: dict = Depends(deps.get_current_user),
    _: dict = Depends(PermissionChecker(["sys:user:manage"])),
):
    """
    更新用户信息 (管理端)
    
    管理员更新用户的基本信息、封禁状态、密码等。
    """
    try:
        uid = int(user_id)
        # 1. 安全检查：防止越权修改
        await _require_actor_superadmin_when_target_protected(uid, current_user)
        
        # 2. 自我保护：不能封禁自己
        if uid == int(current_user.get("id") or 0) and data.is_approved is False:
            return {"code": 400, "message": "不能封禁自己"}

        # 3. 校验邮箱
        if data.email is not None:
            email = str(data.email or "").strip()
            if email and not _is_valid_email(email):
                return {"code": 400, "message": "邮箱格式不正确"}

        # 4. 执行更新
        result = await UserService.admin_update_user(uid, data)
        if data.role_ids is not None:
            await UserService.update_user_roles(uid, data.role_ids)
        if not result.get("updated") and result.get("reason") == "empty":
            return {"code": 200, "message": "无更新内容"}
        if not result.get("updated"):
            return {"code": 404, "message": "用户不存在"}
            
        # 5. 记录审计日志
        await UserAdminAuditService.log(
            action="user.update",
            actor=current_user,
            target_user_id=int(uid),
            request_ip=_get_request_ip(request),
            detail=data.model_dump(exclude_none=True),
        )
        return {"code": 200, "message": "更新成功"}
    except ValueError as e:
        return {"code": 400, "message": str(e)}
    except Exception as e:
        return {"code": 500, "message": f"更新失败: {str(e)}"}


@router.delete("/{user_id}", response_model=dict)
async def admin_delete_user(
    user_id: int,
    request: Request,
    current_user: dict = Depends(deps.get_current_user),
    _: dict = Depends(PermissionChecker(["sys:user:manage"])),
):
    """
    删除用户 (管理端)
    
    管理员删除用户。
    注意：通常是软删除，保留数据记录但不可登录。
    """
    if int(user_id) == int(current_user.get("id") or 0):
        return {"code": 400, "message": "不能删除自己"}
    try:
        await _require_actor_superadmin_when_target_protected(int(user_id), current_user)
        ok = await UserService.admin_delete_user(int(user_id), actor_id=current_user.get("id"))
        if not ok:
            return {"code": 404, "message": "用户不存在"}
        await UserAdminAuditService.log(
            action="user.delete",
            actor=current_user,
            target_user_id=int(user_id),
            request_ip=_get_request_ip(request),
        )
        return {"code": 200, "message": "用户删除成功"}
    except Exception as e:
        return {"code": 500, "message": f"删除用户失败: {str(e)}"}
