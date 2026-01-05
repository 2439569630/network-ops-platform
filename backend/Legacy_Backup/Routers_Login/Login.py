

from fastapi import APIRouter, Depends, Response
import asyncio
from pydantic import BaseModel


from DataBase import PostgreSQL


from auth import jwtTools as jwt

from  auth.security import verify_token

router = APIRouter()

#登录表单
class LoginForm(BaseModel):
    username: str
    password: str

@router.post("/login")
async def read_users(loginForm: LoginForm, response: Response):
    # 获取用户名和密码
    sql = query = "SELECT id, username, password, permission_level, is_approved, permissions FROM users WHERE username = $1"
    rule = await PostgreSQL.execute(sql, loginForm.username, fetch_row=True)
    print(rule)
    if not rule:
      response.status_code = 401
      return {
          "code": 401,
          "status": "error",
          "message": "用户名或密码错误"
      }

    # 检查账户是否被封禁
    if rule['is_approved'] is False:
        response.status_code = 403
        return {
            "code": 403,
            "status": "error",
            "message": "账户已被封禁，请联系管理员"
        }

    # 验证密码是否正确
    if rule['password'] != loginForm.password:
        response.status_code = 401
        return {
            "code": 401,
            "status": "error",
            "message": "用户名或密码错误"
        }

    test_data = {
        'id': rule['id'],
        'username': rule['username'],
        'permission_level': rule['permission_level'],
        'permissions': rule['permissions'] if rule['permissions'] else []
    }

    date = jwt.create_access_token(test_data)

    # 设置安全Cookie
    response.set_cookie(
        key= 'token',  # Cookie名称
        value= date,  # 存储JWT令牌
        httponly=False,  # 防XSS
        secure=False,  # 仅HTTPS传输
        samesite="lax",  # 防CSRF
        max_age= 60 * 60,  # 与token过期时间一致
    )
    return {
        "status": "success",
        "message": "登录成功"

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