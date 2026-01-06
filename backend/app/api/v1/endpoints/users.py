from fastapi import APIRouter, Depends, HTTPException, Body, Request
from fastapi.responses import HTMLResponse
from typing import List
from app.schemas.user import UserCreate, UserResponse, RoleUpdate, UserUpdate, UserStatusUpdate
from app.services.user_service import UserService
from app.api import deps
from app.core.security import PermissionChecker, user_is_super
from pydantic import BaseModel

router = APIRouter()

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
