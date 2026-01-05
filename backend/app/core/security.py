from datetime import datetime, timedelta, timezone
from typing import Optional, Union, Any
import logging
from jose import jwt
from passlib.context import CryptContext
from fastapi import Request, WebSocket, Query, Cookie, Depends
from fastapi.responses import JSONResponse
from app.core.config import settings

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class UnicornException(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        self.status = "error"

def unicorn_exception_handler(request: Request, exc: UnicornException):
    return JSONResponse(
        status_code=exc.code,
        content={
            "code": exc.code,
            "status": exc.status,
            "message": exc.message
        }
    )

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {"exp": expire, "sub": str(subject)}
    if isinstance(subject, dict):
        to_encode.update(subject)
        
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> dict:
    try:
        # 增加日志：打印使用的密钥前几位，确保密钥加载正确
        masked_key = settings.SECRET_KEY[:3] + "***" if settings.SECRET_KEY else "None"
        logger.info(f"Decoding token with key prefix: {masked_key}, alg: {settings.ALGORITHM}")
        
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except Exception as e:
        logger.error(f"Decode token failed: {e}", exc_info=True)
        return None

def verify_token(token: str = Cookie(None)):
    if token is None:
        raise UnicornException(401, "未登录")

    try:
        payload = decode_token(token)
        if not payload:
             raise UnicornException(401, "Token无效")
        return payload
    except Exception as e:
        logger.error(f"Token验证异常: {e}")
        raise UnicornException(401, "身份验证失败")

async def verify_token_ws(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """
    WebSocket 鉴权依赖
    """
    logger.info(f"WS Auth: Verifying token (len={len(token) if token else 0})")
    if token is None:
        # 尝试从 Cookie 获取
        token = websocket.cookies.get("token")
        logger.info(f"WS Auth: Token from cookie (len={len(token) if token else 0})")

    if token is None:
        logger.warning("WS Auth: No token found")
        await websocket.close(code=4001, reason="未登录")
        return None

    try:
        payload = decode_token(token)
        if not payload:
             logger.warning("WS Auth: Decode failed or expired")
             await websocket.close(code=4001, reason="Token无效")
             return None
        logger.info(f"WS Auth: Success for user {payload.get('id', 'unknown')}")
        return payload
    except Exception as e:
        logger.error(f"WS Token验证异常: {e}", exc_info=True)
        await websocket.close(code=4001, reason="身份验证失败")
        return None

class RoleChecker:
    def __init__(self, allowed_roles: list):
        self.allowed_roles = allowed_roles

    def __call__(self, user: dict = Depends(verify_token)):
        # permission_level: 0=SuperAdmin, 1=Admin, 2=User
        user_role = user.get("permission_level")
        if user_role not in self.allowed_roles:
             raise UnicornException(403, "权限不足")
        return user

allow_admin = RoleChecker([0, 1]) # 允许超级管理员和管理员
