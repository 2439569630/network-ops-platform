from datetime import datetime, timedelta, timezone
from typing import Optional, Union, Any
import logging
import json
from jose import jwt
from passlib.context import CryptContext
from fastapi import Request, WebSocket, Query, Cookie, Depends
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.database import db
from app.core.redis import redis_manager
from app.services.rbac_service import RbacService

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DISABLED_PERMISSIONS_CONFIG_KEY = "rbac:disabled_permissions"
DISABLED_PERMISSIONS_REDIS_KEY = "authz:disabled_permissions"
USER_AUTH_VERSION_REDIS_KEY_PREFIX = "auth:ver:user:"
USER_AUTH_SESSION_REDIS_KEY_PREFIX = "auth:session:user:"


def _normalize_permission_codes(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            s = str(item).strip()
            if s:
                out.append(s)
        return out
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return _normalize_permission_codes(parsed)
        except Exception:
            return []
        return []
    return []


async def get_disabled_permission_codes_cached() -> list[str]:
    redis_client = redis_manager.get_client()
    cached = None
    try:
        cached = await redis_client.get(DISABLED_PERMISSIONS_REDIS_KEY)
    except Exception:
        cached = None
    if cached:
        try:
            parsed = json.loads(cached)
            codes = _normalize_permission_codes(parsed)
            return sorted(list(set(codes)))
        except Exception:
            pass

    row = await db.fetch_one(
        "SELECT value FROM system_settings WHERE key = $1",
        DISABLED_PERMISSIONS_CONFIG_KEY,
    )
    codes = _normalize_permission_codes(row.get("value") if row else None)
    codes = sorted(list(set(codes)))
    try:
        await redis_client.set(DISABLED_PERMISSIONS_REDIS_KEY, json.dumps(codes), ex=60)
    except Exception:
        pass
    return codes


async def apply_disabled_permissions(perms: list[str]) -> list[str]:
    disabled = await get_disabled_permission_codes_cached()
    if not disabled:
        return perms
    disabled_set = {str(c) for c in disabled}
    return [str(p) for p in (perms or []) if str(p) not in disabled_set]

class UnicornException(Exception):
    def __init__(self, code: int, message: str, error_code: Optional[str] = None, data: Optional[dict] = None):
        self.code = code
        self.message = message
        self.error_code = error_code
        self.data = data
        self.status = "error"

def unicorn_exception_handler(request: Request, exc: UnicornException):
    return JSONResponse(
        status_code=exc.code,
        content={
            "code": exc.code,
            "status": exc.status,
            "message": exc.message,
            **({"error": exc.error_code} if getattr(exc, "error_code", None) else {}),
            **({"data": exc.data} if getattr(exc, "data", None) is not None else {}),
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
    
    sub: str
    if isinstance(subject, dict):
        sub = str(subject.get("id") or subject.get("username") or "")
    else:
        sub = str(subject)

    to_encode = {"exp": expire, "sub": sub}
    if isinstance(subject, dict):
        to_encode.update(subject)
        
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def _normalize_role_codes(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, dict):
                code = item.get("code")
                if code is None:
                    continue
                out.append(str(code))
            else:
                out.append(str(item))
        return out
    if isinstance(value, str):
        s = value.strip()
        return [s] if s else []
    return []

def user_has_role(user: dict, role_code: str) -> bool:
    target = str(role_code or "").strip().lower()
    if not target:
        return False
    roles = {str(c).strip().lower() for c in _normalize_role_codes(user.get("roles")) if str(c).strip()}
    return target in roles

def user_is_super(user: dict) -> bool:
    if user.get("is_super") is True:
        return True
    roles = {str(c).strip().lower() for c in _normalize_role_codes(user.get("roles")) if str(c).strip()}
    if roles & {"admin", "superadmin", "super_admin", "super-admin"}:
        return True
    return False

def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except Exception as e:
        logger.error(f"Decode token failed: {e}", exc_info=True)
        return None

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

async def _get_or_init_user_perm_version(user_id: int) -> int:
    redis_client = redis_manager.get_client()
    key = f"authz:ver:user:{int(user_id)}"
    raw = await redis_client.get(key)
    if raw is None:
        await redis_client.set(key, "1")
        return 1
    try:
        v = int(raw)
        if v > 0:
            return v
    except Exception:
        pass
    await redis_client.set(key, "1")
    return 1

async def get_or_init_user_auth_version(user_id: int) -> int:
    redis_client = redis_manager.get_client()
    key = f"{USER_AUTH_VERSION_REDIS_KEY_PREFIX}{int(user_id)}"
    raw = await redis_client.get(key)
    if raw is None:
        await redis_client.set(key, "1")
        return 1
    try:
        v = int(raw)
        if v > 0:
            return v
    except Exception:
        pass
    await redis_client.set(key, "1")
    return 1

async def bump_user_auth_version(user_id: int) -> int:
    redis_client = redis_manager.get_client()
    key = f"{USER_AUTH_VERSION_REDIS_KEY_PREFIX}{int(user_id)}"
    try:
        v = await redis_client.incr(key)
        if int(v) > 0:
            return int(v)
    except Exception:
        pass
    await redis_client.set(key, "1")
    return 1

async def set_user_auth_session_info(user_id: int, *, auth_ver: int, ip: Optional[str] = None, user_agent: Optional[str] = None, device: Optional[str] = None) -> None:
    redis_client = redis_manager.get_client()
    key = f"{USER_AUTH_SESSION_REDIS_KEY_PREFIX}{int(user_id)}"
    payload = {
        "auth_ver": int(auth_ver),
        "ip": (str(ip).strip() if ip else None),
        "device": (str(device).strip() if device else None),
        "user_agent": (str(user_agent).strip() if user_agent else None),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await redis_client.set(key, json.dumps(payload, ensure_ascii=False), ex=60 * 60 * 24 * 30)
    except Exception:
        pass

async def get_user_auth_session_info(user_id: int) -> Optional[dict]:
    redis_client = redis_manager.get_client()
    key = f"{USER_AUTH_SESSION_REDIS_KEY_PREFIX}{int(user_id)}"
    try:
        raw = await redis_client.get(key)
    except Exception:
        raw = None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data

async def get_user_permissions_cached(user_id: int, perm_ver: Optional[int] = None) -> list[str]:
    uid = int(user_id)
    ver = perm_ver
    if ver is None:
        ver = await _get_or_init_user_perm_version(uid)
    try:
        ver = int(ver)
        if ver <= 0:
            ver = await _get_or_init_user_perm_version(uid)
    except Exception:
        ver = await _get_or_init_user_perm_version(uid)

    redis_client = redis_manager.get_client()
    cache_key = f"authz:perms:user:{uid}:v{int(ver)}"
    cached = await redis_client.get(cache_key)
    if cached:
        try:
            parsed = json.loads(cached)
            if isinstance(parsed, list):
                perms = [str(x) for x in parsed if x is not None]
                return await apply_disabled_permissions(perms)
        except Exception:
            cached = None

    user_row = await db.fetch_one("SELECT permissions FROM users WHERE id = $1", uid)
    direct_perms = _normalize_permissions(user_row.get("permissions") if user_row else None)
    role_perms = await RbacService.get_user_permission_codes(uid)
    merged = sorted(list({str(p) for p in (direct_perms + role_perms) if str(p).strip()}))
    merged = RbacService.expand_permission_codes(merged)

    try:
        await redis_client.set(cache_key, json.dumps(merged), ex=3600)
    except Exception:
        pass
    return await apply_disabled_permissions(merged)

async def user_has_permission(user: dict, perm: str) -> bool:
    if user_is_super(user):
        return True
    user_id = user.get("id")
    if user_id is None:
        return False
    perms = await get_user_permissions_cached(int(user_id), perm_ver=user.get("perm_ver"))
    return str(perm) in {str(p) for p in (perms or [])}

async def verify_token(token: str = Cookie(None)):
    if token is None:
        raise UnicornException(401, "未登录", error_code="AUTH_NOT_LOGGED_IN")

    try:
        payload = decode_token(token)
        if not payload:
            raise UnicornException(401, "Token无效", error_code="AUTH_TOKEN_INVALID")

        user_id = payload.get("id")
        if user_id is not None:
            uid = int(user_id)
            redis_auth_ver = await get_or_init_user_auth_version(uid)
            token_auth_ver = payload.get("auth_ver")
            if token_auth_ver is None:
                raise UnicornException(401, "Token版本过旧，请重新登录", error_code="AUTH_TOKEN_TOO_OLD")
            try:
                token_auth_ver_int = int(token_auth_ver)
            except Exception:
                raise UnicornException(401, "Token无效", error_code="AUTH_TOKEN_INVALID")
            if token_auth_ver_int != int(redis_auth_ver):
                new_login = await get_user_auth_session_info(uid)
                raise UnicornException(401, "会话已失效，请重新登录", error_code="AUTH_SESSION_REVOKED", data={"new_login": new_login})

            redis_ver = await _get_or_init_user_perm_version(uid)
            token_ver = payload.get("perm_ver")
            if token_ver is None:
                raise UnicornException(401, "Token版本过旧，请重新登录", error_code="AUTH_TOKEN_TOO_OLD")
            try:
                token_ver_int = int(token_ver)
            except Exception:
                raise UnicornException(401, "Token无效", error_code="AUTH_TOKEN_INVALID")
            if token_ver_int != int(redis_ver):
                raise UnicornException(401, "权限已更新，请重新登录", error_code="AUTHZ_VERSION_MISMATCH")

        return payload
    except UnicornException:
        raise
    except Exception as e:
        logger.error(f"Token验证异常: {e}", exc_info=True)
        raise UnicornException(401, "身份验证失败", error_code="AUTH_VERIFY_FAILED")

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

        user_id = payload.get("id")
        if user_id is not None:
            uid = int(user_id)
            redis_auth_ver = await get_or_init_user_auth_version(uid)
            token_auth_ver = payload.get("auth_ver")
            if token_auth_ver is None:
                await websocket.close(code=4001, reason="Token版本过旧，请重新登录")
                return None
            try:
                token_auth_ver_int = int(token_auth_ver)
            except Exception:
                await websocket.close(code=4001, reason="Token无效")
                return None
            if token_auth_ver_int != int(redis_auth_ver):
                await websocket.close(code=4001, reason="会话已失效，请重新登录")
                return None

            redis_ver = await _get_or_init_user_perm_version(uid)
            token_ver = payload.get("perm_ver")
            if token_ver is None:
                await websocket.close(code=4001, reason="Token版本过旧，请重新登录")
                return None
            try:
                token_ver_int = int(token_ver)
            except Exception:
                await websocket.close(code=4001, reason="Token无效")
                return None
            if token_ver_int != int(redis_ver):
                await websocket.close(code=4001, reason="权限已更新，请重新登录")
                return None

        logger.info(f"WS Auth: Success for user {payload.get('id', 'unknown')}")
        return payload
    except Exception as e:
        logger.error(f"WS Token验证异常: {e}", exc_info=True)
        await websocket.close(code=4001, reason="身份验证失败")
        return None

class RoleChecker:
    def __init__(self, allowed_roles: list):
        self.allowed_roles = {str(r).strip().lower() for r in (allowed_roles or []) if str(r).strip()}

    def __call__(self, user: dict = Depends(verify_token)):
        if user_is_super(user):
            return user
        roles = {str(c).strip().lower() for c in _normalize_role_codes(user.get("roles")) if str(c).strip()}
        if roles & self.allowed_roles:
            return user
        raise UnicornException(403, "权限不足")

class PermissionChecker:
    def __init__(self, required_permissions: Union[str, list], require_all: bool = False):
        if isinstance(required_permissions, str):
            self.required_permissions = [required_permissions]
        else:
            self.required_permissions = [str(p) for p in (required_permissions or [])]
        self.require_all = bool(require_all)

    async def __call__(self, user: dict = Depends(verify_token)):
        if user_is_super(user):
            return user

        user_id = user.get("id")
        if user_id is None:
            raise UnicornException(401, "未登录", error_code="AUTH_NOT_LOGGED_IN")
        perms = await get_user_permissions_cached(int(user_id), perm_ver=user.get("perm_ver"))
        perms_set = {str(p) for p in (perms or [])}

        required = [str(p) for p in self.required_permissions if str(p).strip()]
        if not required:
            return user

        allowed = all(p in perms_set for p in required) if self.require_all else any(p in perms_set for p in required)
        if not allowed:
            raise UnicornException(403, "权限不足")
        return user

allow_admin = RoleChecker(["admin"])
