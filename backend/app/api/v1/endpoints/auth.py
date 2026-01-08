

import asyncio
import logging
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Cookie
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.core.database import db
from app.core.redis import redis_manager
from app.core.security import create_access_token, verify_password, get_password_hash, verify_token, user_is_super, get_user_permissions_cached, decode_token, get_disabled_permission_codes_cached
from app.core.config import settings
from app.services.rbac_service import RbacService
import json

router = APIRouter()
logger = logging.getLogger(__name__)

#登录表单
class LoginForm(BaseModel):
    username: str
    password: str

class RegisterForm(BaseModel):
    username: str
    password: str
    nickname: Optional[str] = None
    email: Optional[str] = None

def _normalize_permissions(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if x is not None]
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(x) for x in parsed if x is not None]
        except Exception:
            return []
    return []

def _looks_like_bcrypt_hash(value: str) -> bool:
    s = str(value or "")
    return s.startswith("$2a$") or s.startswith("$2b$") or s.startswith("$2y$")

def _verify_password_compat(plain_password: str, stored_password: str) -> bool:
    if stored_password is None:
        return False
    stored = str(stored_password)
    if _looks_like_bcrypt_hash(stored):
        try:
            return bool(verify_password(plain_password, stored))
        except Exception:
            return False
    return stored == str(plain_password)

async def _get_or_init_perm_ver(user_id: int) -> int:
    redis_client = redis_manager.get_client()
    key = f"authz:ver:user:{int(user_id)}"
    raw = await redis_client.get(key)
    if raw is None:
        await redis_client.set(key, "1")
        return 1
    try:
        v = int(raw)
        return v if v > 0 else 1
    except Exception:
        await redis_client.set(key, "1")
        return 1

@router.post("/login")
async def login(data: LoginForm, response: Response):
    # 1. 查询用户
    sql = "SELECT id, username, password, is_approved, permissions FROM users WHERE username = $1"
    user = await db.fetch_one(sql, data.username)

    if not user:
        return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "用户名或密码错误", "status": "error"}
        )

    # 检查账户是否被封禁
    if user['is_approved'] is False:
        return JSONResponse(
            status_code=403,
            content={"code": 403, "message": "账户未审核或已封禁，请联系管理员", "status": "error"}
        )

    if not _verify_password_compat(data.password, user.get("password")):
         return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "用户名或密码错误", "status": "error"}
        )
        
    # 3. 生成 Token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    user_permissions = _normalize_permissions(user.get("permissions"))
    user_roles: list[str] = []
    try:
        role_permissions = await RbacService.get_user_permission_codes(user["id"])
        user_roles = await RbacService.get_user_role_codes(user["id"])
        merged = set(user_permissions) | set(role_permissions)
        user_permissions = sorted(list(merged))
    except Exception:
        pass
    
    is_super = user_is_super({"roles": user_roles})
    if not is_super:
        try:
            disabled = await get_disabled_permission_codes_cached()
            if "sys:auth:login" in {str(c) for c in (disabled or [])}:
                return JSONResponse(
                    status_code=403,
                    content={"code": 403, "message": "登录权限已关闭", "status": "error"},
                )
        except Exception:
            pass

    perm_ver = await _get_or_init_perm_ver(user["id"])
    token_data = {
        "id": user['id'],
        "username": user['username'],
        "roles": user_roles,
        "is_super": bool(is_super),
        "perm_ver": int(perm_ver),
    }
    
    access_token = create_access_token(
        subject=token_data,
        expires_delta=access_token_expires
    )
    
    # 设置 Cookie
    response.set_cookie(
        key='token',
        value=access_token,
        httponly=False,
        secure=False,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    
    return {
        "status": "success",
        "message": "登录成功",
        "token": access_token 
    }

@router.post("/refresh")
async def refresh_token(response: Response, token: str = Cookie(None)):
    if token is None:
        return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "未登录", "status": "error"},
        )
    token_payload = decode_token(token)
    if not token_payload:
        return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "Token无效", "status": "error"},
        )

    user_id = token_payload.get("id")
    if not user_id:
        return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "未登录", "status": "error"},
        )

    user = await db.fetch_one(
        "SELECT id, username, permissions, is_approved FROM users WHERE id = $1",
        int(user_id),
    )
    if not user:
        return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "用户不存在", "status": "error"},
        )
    if user.get("is_approved") is False:
        return JSONResponse(
            status_code=403,
            content={"code": 403, "message": "账户未审核或已封禁，请联系管理员", "status": "error"},
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    user_permissions = _normalize_permissions(user.get("permissions"))
    user_roles: list[str] = []
    try:
        role_permissions = await RbacService.get_user_permission_codes(user["id"])
        user_roles = await RbacService.get_user_role_codes(user["id"])
        merged = set(user_permissions) | set(role_permissions)
        user_permissions = sorted(list(merged))
    except Exception:
        pass
    
    is_super = user_is_super(token_payload) or user_is_super({"roles": user_roles})
    if not is_super:
        try:
            disabled = await get_disabled_permission_codes_cached()
            if "sys:auth:login" in {str(c) for c in (disabled or [])}:
                response.delete_cookie(key="token")
                return JSONResponse(
                    status_code=403,
                    content={"code": 403, "message": "登录权限已关闭", "status": "error"},
                )
        except Exception:
            pass

    perm_ver = await _get_or_init_perm_ver(user["id"])
    token_data = {
        "id": user["id"],
        "username": user["username"],
        "roles": user_roles,
        "is_super": bool(is_super),
        "perm_ver": int(perm_ver),
    }

    access_token = create_access_token(subject=token_data, expires_delta=access_token_expires)
    response.set_cookie(
        key="token",
        value=access_token,
        httponly=False,
        secure=False,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return {"code": 200, "status": "success", "token": access_token}

@router.post("/register")
async def register(data: RegisterForm):
    try:
        disabled = await get_disabled_permission_codes_cached()
        if "sys:auth:register" in {str(c) for c in (disabled or [])}:
            return JSONResponse(
                status_code=403,
                content={"code": 403, "status": "error", "message": "注册权限已关闭"},
            )
    except Exception:
        pass
    username = (data.username or "").strip()
    password = str(data.password or "")
    if not username or not password:
        return JSONResponse(
            status_code=400,
            content={"code": 400, "status": "error", "message": "用户名与密码不能为空"},
        )

    exists = await db.fetch_val("SELECT id FROM users WHERE username = $1", username)
    if exists:
        return JSONResponse(
            status_code=400,
            content={"code": 400, "status": "error", "message": "用户名已存在"},
        )

    nickname = (data.nickname or "").strip() or username
    email = (data.email or "").strip() or None
    hashed_pw = get_password_hash(password)
    perms_json = ["sys:monitor:view"]

    user_id = await db.fetch_val(
        """
        INSERT INTO users (username, password, nickname, email, is_approved, permissions)
        VALUES ($1, $2, $3, $4, false, $5::jsonb)
        RETURNING id
        """,
        username,
        hashed_pw,
        nickname,
        email,
        perms_json,
    )

    role_id: Optional[int] = None
    try:
        role_id = await db.fetch_val("SELECT id FROM roles WHERE is_default = TRUE LIMIT 1")
    except Exception:
        role_id = None

    if role_id is None:
        try:
            role_id = await db.fetch_val("SELECT id FROM roles WHERE lower(code) = 'shisheng' LIMIT 1")
        except Exception:
            role_id = None

    if role_id is not None:
        try:
            await db.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                int(user_id),
                int(role_id),
            )
        except Exception:
            pass

    try:
        await _get_or_init_perm_ver(int(user_id))
    except Exception:
        pass

    return {"code": 200, "status": "success", "message": "注册成功，请等待管理员审核", "data": {"id": user_id}}

@router.get("/permissions")
async def get_my_permissions(token_payload: dict = Depends(verify_token)):
    user_id = token_payload.get("id")
    if user_id is None:
        return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "未登录", "status": "error"},
        )
    perms = await get_user_permissions_cached(int(user_id), perm_ver=token_payload.get("perm_ver"))
    return {"code": 200, "status": "success", "data": {"perm_ver": token_payload.get("perm_ver"), "permissions": perms}}

@router.post("/users/me")
async def read_current_user(response: Response, token = Depends(verify_token)):
    print(token.get('code'))
    if token.get('code') != 200:
        response.status_code = token.get('code')
        return token


    return {
        "code": 200,
        "status": "success",
    }
