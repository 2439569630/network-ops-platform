

import asyncio
import logging
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.core.database import db
from app.core.redis import redis_manager
from app.core.security import create_access_token, verify_password, get_password_hash, verify_token
from app.core.config import settings
from app.services.rbac_service import RbacService

router = APIRouter()
logger = logging.getLogger(__name__)

#登录表单
class LoginForm(BaseModel):
    username: str
    password: str

@router.post("/login")
async def login(data: LoginForm, response: Response):
    # 1. 查询用户
    sql = "SELECT id, username, password, permission_level, is_approved, permissions FROM users WHERE username = $1"
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
            content={"code": 403, "message": "账户已被封禁，请联系管理员", "status": "error"}
        )

    # 2. 验证密码 (这里假设数据库是明文，如果需要哈希验证，请改用 verify_password)
    # 注意：原始代码是明文比较 if rule['password'] != loginForm.password:
    # 如果要保持一致：
    if user['password'] != data.password:
         return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "用户名或密码错误", "status": "error"}
        )
        
    # 3. 生成 Token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    user_permissions = user["permissions"] if user["permissions"] else []
    if not isinstance(user_permissions, list):
        user_permissions = []
    try:
        role_permissions = await RbacService.get_user_permission_codes(user["id"])
        merged = set(user_permissions) | set(role_permissions)
        user_permissions = list(merged)
    except Exception:
        pass

    token_data = {
        "id": user['id'],
        "username": user['username'],
        "permission_level": user['permission_level'],
        "permissions": user_permissions
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
