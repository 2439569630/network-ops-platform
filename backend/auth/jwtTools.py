# app/jwtTools.py
import os
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException
from fastapi.params import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from typing import Dict, Any

from starlette import status

from auth import security

# 从环境变量获取配置（生产环境推荐）
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "fallback-secret-key-change-in-production")
ALGORITHM = "HS256"
# token过期时间 （单位：分钟）
ACCESS_TOKEN_EXPIRE_MINUTES = 60


def create_access_token(data: Dict[str, Any], expires_delta: timedelta = None) -> str:
    """
    创建访问令牌

    Args:
        data: 要编码到 token 中的数据
        expires_delta: 可选的过期时间间隔，默认为 ACCESS_TOKEN_EXPIRE_MINUTES

    Returns:
        JWT token 字符串
    """
    to_encode = data.copy()

    # 设置过期时间
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    # 构建 payload
    to_encode.update({
        "exp": expire,  # 过期时间
        "iat": datetime.now(timezone.utc),  # 签发时间
        # 可以添加其他标准声明
        # "iss": "your-app-name",  # 签发者
        # "sub": "user-auth",      # 主题
    })

    # 编码 token
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Dict[str, Any]:
    """
    验证并解码 JWT token

    Args:
        token: JWT token 字符串

    Returns:
        解码后的 payload 数据

    Raises:
        jwt.JWTError: 如果 token 无效或过期
    """
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )
        return payload
    except jwt.ExpiredSignatureError:
        return {
            "code": 401,
            "status": "error",
            "message": "Token 已过期"
        }
    except jwt.JWTError as e:
        return {
            "code": 404,
            "status": "error",
            "message": "无效的token"
        }


# 测试代码
if __name__ == "__main__":
    # 测试数据
    test_data = {
        'user_id': 12345,
        'username': 'john_doe',
        'role': 'admin'
    }

    try:
        # 创建 token
        token = create_access_token(data=test_data)
        print(f"生成的 Token: {token}")
        print(f"Token 长度: {len(token)} 字符")

        # 验证 token
        decoded_data = verify_token(token)
        print(f"解码后的数据: {decoded_data}")

        # 测试自定义过期时间
        custom_token = create_access_token(
            data=test_data,
            expires_delta=timedelta(hours=2)
        )
        print(f"\n自定义过期时间的 Token: {custom_token}")

    except Exception as e:
        print(f"错误: {e}")