import csv
import io
import json
import secrets
import time
import os
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Body, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from typing import List, Optional, Any
from app.schemas.user import UserCreate, UserResponse, RoleUpdate, UserUpdate, UserStatusUpdate
from app.services.user_service import UserService
from app.api import deps
from app.core.security import PermissionChecker, user_is_super, get_disabled_permission_codes_cached, get_password_hash
from app.core.redis import redis_manager
from app.core.database import db
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

_HASH_MAX_WORKERS = max(4, min(32, int(os.cpu_count() or 4)))
_HASH_EXECUTOR = ThreadPoolExecutor(max_workers=_HASH_MAX_WORKERS)
_IMPORT_TTL_SECONDS = 1800

def _import_data_key(token: str) -> str:
    return f"user_import:{token}"

def _import_progress_key(token: str) -> str:
    return f"user_import_progress:{token}"

def _import_cancel_key(token: str) -> str:
    return f"user_import_cancel:{token}"

def _import_result_key(token: str) -> str:
    return f"user_import_result:{token}"

async def _is_user_import_cancelled(redis_client: Any, token: str) -> bool:
    try:
        return bool(await redis_client.exists(_import_cancel_key(token)))
    except Exception:
        return False

async def _set_user_import_cancel(redis_client: Any, token: str) -> None:
    await redis_client.set(_import_cancel_key(token), "1", ex=_IMPORT_TTL_SECONDS)

async def _clear_user_import_cancel(redis_client: Any, token: str) -> None:
    try:
        await redis_client.delete(_import_cancel_key(token))
    except Exception:
        pass

async def _set_user_import_result(redis_client: Any, token: str, data: dict) -> None:
    await redis_client.set(_import_result_key(token), json.dumps(data, ensure_ascii=False), ex=_IMPORT_TTL_SECONDS)

async def _get_user_import_result(redis_client: Any, token: str) -> Optional[dict]:
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

def check_admin(user: dict):
    if user_is_super(user):
        return
    raise HTTPException(status_code=403, detail="权限不足")

@router.post("/add", response_model=dict)
async def create_user(
    user_in: UserCreate, 
    current_user: dict = Depends(deps.get_current_user),
    _: dict = Depends(PermissionChecker(["sys:auth:register", "sys:user:manage"]))
):
    """创建新用户 (仅管理员)"""
    check_admin(current_user)
    try:
        user_id = await UserService.create_user(user_in)
        return {"code": 200, "message": "用户创建成功", "data": {"id": user_id}}
    except ValueError as e:
        return {"code": 400, "message": str(e)}
    except Exception as e:
        return {"code": 500, "message": f"创建用户失败: {str(e)}"}

@router.delete("/delete", response_model=dict)
async def delete_user(
    user_id: int = Body(..., embed=True), # Accept user_id from body to match old style or query? Old style was body.
    current_user: dict = Depends(deps.get_current_user),
    _: dict = Depends(PermissionChecker(["sys:user:manage"]))
):
    """删除用户 (仅管理员)"""
    check_admin(current_user)
    if user_id == current_user.get("id"):
        return {"code": 400, "message": "不能删除自己"}
        
    try:
        await UserService.delete_user(user_id)
        return {"code": 200, "message": "用户删除成功"}
    except Exception as e:
        return {"code": 500, "message": f"删除用户失败: {str(e)}"}


@router.post("/batch/delete", response_model=dict)
async def delete_users_batch(
    user_ids: List[int] = Body(..., embed=True),
    current_user: dict = Depends(deps.get_current_user),
    _: dict = Depends(PermissionChecker(["sys:user:manage"]))
):
    """批量删除用户 (仅管理员)"""
    check_admin(current_user)
    if current_user.get("id") in user_ids:
        return {"code": 400, "message": "不能删除自己"}
        
    try:
        await UserService.delete_users(user_ids)
        return {"code": 200, "message": "批量删除成功"}
    except Exception as e:
        return {"code": 500, "message": f"批量删除失败: {str(e)}"}


@router.put("/{user_id}/password", response_model=dict)
async def reset_user_password(
    user_id: int,
    password: str = Body(..., embed=True),
    current_user: dict = Depends(deps.get_current_user),
    _: dict = Depends(PermissionChecker(["sys:user:manage"]))
):
    """管理员重置用户密码"""
    check_admin(current_user)
    try:
        await UserService.reset_password(user_id, password)
        return {"code": 200, "message": "密码重置成功"}
    except ValueError as e:
        return {"code": 400, "message": str(e)}
    except Exception as e:
        return {"code": 500, "message": f"密码重置失败: {str(e)}"}

@router.post("/update_perms", response_model=dict)
async def update_user_perms(
    user_id: int = Body(...),
    permissions: List[str] = Body(...),
    current_user: dict = Depends(deps.get_current_user),
    _: dict = Depends(PermissionChecker(["sys:user:manage"]))
):
    """更新用户细粒度权限 (仅管理员)"""
    check_admin(current_user)
    try:
        data = RoleUpdate(permissions=permissions)
        await UserService.update_user_role(user_id, data)
        return {"code": 200, "message": "权限修改成功"}
    except Exception as e:
        return {"code": 500, "message": f"修改权限失败: {str(e)}"}

@router.post("/status", response_model=dict)
async def update_user_status(
    user_id: int = Body(...),
    is_approved: bool = Body(...),
    current_user: dict = Depends(deps.get_current_user),
    _: dict = Depends(PermissionChecker(["sys:user:manage"]))
):
    """封禁/解封用户 (仅管理员)"""
    check_admin(current_user)
    if user_id == current_user.get("id"):
        return {"code": 400, "message": "不能封禁自己"}
        
    try:
        await UserService.update_status(user_id, is_approved)
        return {"code": 200, "message": "状态更新成功"}
    except Exception as e:
        return {"code": 500, "message": f"更新状态失败: {str(e)}"}

@router.get("/roleList", response_model=dict)
async def list_roles(
    current_user: dict = Depends(deps.get_current_user),
    _: dict = Depends(PermissionChecker(["sys:user:view"]))
):
    """获取用户角色列表 (仅管理员，复用 list 逻辑但适配前端路径)"""
    check_admin(current_user)
    try:
        users = await UserService.get_user_list()
        return {"code": 200, "data": users}
    except Exception as e:
        return {"code": 500, "message": f"获取用户列表失败: {str(e)}"}

# Profile routes (Merged from profile.py)

@router.get("/profile", response_model=dict)
async def get_profile(current_user: dict = Depends(deps.get_current_user)):
    """获取个人信息"""
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
    current_user: dict = Depends(deps.get_current_user)
):
    """更新个人信息"""
    try:
        await UserService.update_profile(current_user.get("id"), data)
        return {"code": 200, "message": "更新成功"}
    except ValueError as e:
        return {"code": 400, "message": str(e)}
    except Exception as e:
        return {"code": 500, "message": f"更新失败: {str(e)}"}

@router.get("/profile/summary", response_model=dict)
async def get_profile_summary(current_user: dict = Depends(deps.get_current_user)):
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
    try:
        try:
            disabled = await get_disabled_permission_codes_cached()
            if "sys:email:verify" in {str(c) for c in (disabled or [])}:
                return {"code": 403, "message": "邮箱验证权限已关闭"}
        except Exception:
            pass
        xff = request.headers.get("x-forwarded-for")
        ip = (xff.split(",")[0].strip() if xff else None) or (request.client.host if request.client else None)
        base_url = str(request.base_url).rstrip("/")
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
    try:
        try:
            disabled = await get_disabled_permission_codes_cached()
            if "sys:email:verify" in {str(c) for c in (disabled or [])}:
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
        result = await UserService.confirm_email_verification(token)
        email = result.get("email") or ""
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
    if v is None:
        return None
    if isinstance(v, (int, float)):
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v)
    s = str(v).strip()
    return s if s else None

def _looks_like_password_hash(s: str) -> bool:
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
    filename = str(file.filename or "")
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    raw = await file.read()
    if raw is None:
        raw = b""
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError("文件过大（最大 10MB）")

    if ext in {"csv"}:
        text = None
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
    check_admin(current_user)
    try:
        columns, rows = await _read_import_rows_from_file(file)
        limited_rows = rows[:5000]
        token = secrets.token_urlsafe(16)
        redis_client = redis_manager.get_client()
        payload = {
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "filename": str(file.filename or ""),
            "columns": columns,
            "rows": limited_rows,
        }
        await redis_client.set(_import_data_key(token), json.dumps(payload, ensure_ascii=False), ex=_IMPORT_TTL_SECONDS)
        await _clear_user_import_cancel(redis_client, token)
        try:
            await redis_client.delete(_import_result_key(token))
        except Exception:
            pass
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
    check_admin(current_user)
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
    check_admin(current_user)
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
        await _set_user_import_cancel(redis_client, t)
        await _set_user_import_progress(
            redis_client,
            t,
            100,
            "canceled",
            "已请求停止导入",
            detail={"phase": "canceled"},
        )
        return {"code": 200, "message": "已请求停止导入"}
    except Exception as e:
        return {"code": 500, "message": f"停止失败: {str(e)}"}

@router.get("/import/result", response_model=dict)
async def get_user_import_result(
    token: str,
    current_user: dict = Depends(deps.get_current_user),
    _: dict = Depends(PermissionChecker(["sys:user:import"])),
):
    check_admin(current_user)
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
    check_admin(current_user)
    token_for_progress = ""
    phase_for_log = ""
    timing_ms: dict[str, int] = {}
    t_total_start = time.perf_counter()
    last_sql = ""
    last_sql_params: dict[str, Any] = {}
    try:
        phase_for_log = "parse_request"
        token = str(data.token or "").strip()
        token_for_progress = token
        if not token:
            return {"code": 400, "message": "缺少 token"}

        redis_client = redis_manager.get_client()
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
        role_id_by_code = {str(r["code"]).strip().lower(): int(r["id"]) for r in (roles_rows or []) if r and r.get("code")}
        role_id_fallback = role_id_by_code.get(default_role_code) if default_role_code else None
        system_default_role_id = None
        for r in roles_rows or []:
            try:
                if bool(r.get("is_default")):
                    system_default_role_id = int(r["id"])
                    break
            except Exception:
                continue

        created = 0
        skipped = 0
        failed = 0
        errors: list[dict] = []

        candidates: list[dict] = []
        seen_usernames: set[str] = set()

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
                continue
            to_insert.append(c)

        if not to_insert:
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

            hashed_results: list[Any] = []
            if needs_hash:
                futures = [loop.run_in_executor(_HASH_EXECUTOR, get_password_hash, pw) for pw in needs_hash]
                hashed_results = await asyncio.gather(*futures, return_exceptions=True)

            hashed_by_i: dict[int, Any] = {}
            for pos, i in enumerate(needs_hash_idx):
                hashed_by_i[i] = hashed_results[pos]

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
    except Exception as e:
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
