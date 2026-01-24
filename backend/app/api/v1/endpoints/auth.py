

import asyncio
import logging
from datetime import timedelta, datetime
import hashlib
import hmac
import re
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Cookie
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.core.database import db
from app.core.redis import redis_manager
from app.core.security import create_access_token, verify_password, get_password_hash, verify_token, user_is_super, get_user_permissions_cached, decode_token, get_disabled_permission_codes_cached, get_or_init_user_auth_version, bump_user_auth_version, set_user_auth_session_info, get_user_auth_session_info
from app.core.config import settings
from app.core.system_config import SystemConfig
from app.services.rbac_service import RbacService
from app.services.notification_service import NotificationService
from app.utils.notification_sender import send_email
import json

router = APIRouter()
logger = logging.getLogger(__name__)

#登录表单
class LoginForm(BaseModel):
    """登录表单数据"""
    username: str
    password: str

class RegisterForm(BaseModel):
    """注册表单数据"""
    username: str
    password: str
    nickname: Optional[str] = None
    email: Optional[str] = None

class PasswordResetRequestForm(BaseModel):
    """密码重置请求表单"""
    email: str
    captcha_id: str
    captcha_answer: str

class PasswordResetConfirmForm(BaseModel):
    """密码重置确认表单"""
    token: str
    new_password: str

class UpdateSecurityForm(BaseModel):
    is_email_notify: Optional[bool] = None


def _is_valid_email(email: str) -> bool:
    """验证邮箱格式"""
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", str(email or "")))

def _get_request_ip(request: Request) -> Optional[str]:
    """获取请求 IP"""
    xff = request.headers.get("x-forwarded-for")
    return (xff.split(",")[0].strip() if xff else None) or (request.client.host if request.client else None)

def _captcha_key(captcha_id: str) -> str:
    """获取验证码 Redis Key"""
    return f"captcha:{str(captcha_id or '').strip()}"

def _hash_text(value: str) -> str:
    """计算文本哈希"""
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()

def _infer_device_label(user_agent: Optional[str]) -> str:
    """根据 User-Agent 推断设备类型"""
    ua = str(user_agent or "").strip()
    if not ua:
        return "未知设备"
    u = ua.lower()

    os_name = "未知系统"
    if "windows" in u:
        os_name = "Windows"
    elif "android" in u:
        os_name = "Android"
    elif "iphone" in u or "ipad" in u or "ios" in u:
        os_name = "iOS"
    elif "mac os x" in u or "macintosh" in u:
        os_name = "macOS"
    elif "linux" in u:
        os_name = "Linux"

    browser = "未知浏览器"
    if "edg/" in u:
        browser = "Edge"
    elif "chrome/" in u and "chromium" not in u and "edg/" not in u:
        browser = "Chrome"
    elif "firefox/" in u:
        browser = "Firefox"
    elif "safari/" in u and "chrome/" not in u:
        browser = "Safari"

    return f"{os_name} · {browser}"

async def _send_login_notification_task(email: str, username: str, ip: str, device: str):
    try:
        host = SystemConfig.get("email_host")
        port = SystemConfig.get("email_port")
        username_smtp = SystemConfig.get("email_username")
        password = SystemConfig.get("email_password")
        nickname = SystemConfig.get("email_nickname")
        
        if not all([host, port, username_smtp, password]):
            logger.info("Email config not found in memory, reloading from DB...")
            await SystemConfig.load()
            host = SystemConfig.get("email_host")
            port = SystemConfig.get("email_port")
            username_smtp = SystemConfig.get("email_username")
            password = SystemConfig.get("email_password")
            nickname = SystemConfig.get("email_nickname")
            
        if not all([host, port, username_smtp, password]):
            logger.error("Missing email configuration, cannot send notification.")
            return

        subject = "登录提醒"
        content = (
            f"你好，{username}：\n\n"
            f"你的账号刚刚登录了系统。\n"
            f"登录 IP：{ip}\n"
            f"设备信息：{device}\n"
            f"登录时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            "如果这不是你的操作，请立即修改密码。"
        )
        logger.info(f"Sending email to {email} via {host}:{port}...")
        ok, msg = await send_email(host, port, username_smtp, password, email, subject, content, nickname=nickname)
        if ok:
            logger.info(f"Email sent successfully to {email}")
        else:
            logger.error(f"Failed to send email to {email}: {msg}")
            
    except Exception as e:
        logger.error(f"Failed to send login notification task: {e}")

@router.get("/captcha")
async def get_captcha():
    """获取图形验证码"""
    redis_client = redis_manager.get_client()
    ttl_seconds = SystemConfig.get_int("auth:captcha:ttl_seconds", 300)
    a = secrets.randbelow(9) + 1
    b = secrets.randbelow(9) + 1
    captcha_id = secrets.token_urlsafe(16)
    await redis_client.set(_captcha_key(captcha_id), _hash_text(str(a + b)), ex=int(ttl_seconds))
    return {
        "code": 200,
        "data": {
            "captcha_id": captcha_id,
            "question": f"{a} + {b} = ?",
            "ttl_seconds": int(ttl_seconds),
        },
    }

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

async def _get_or_init_auth_ver(user_id: int) -> int:
    try:
        return await get_or_init_user_auth_version(int(user_id))
    except Exception:
        redis_client = redis_manager.get_client()
        key = f"auth:ver:user:{int(user_id)}"
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
async def login(data: LoginForm, response: Response, request: Request):
    """
    用户登录
    
    验证用户名和密码，返回访问令牌
    """
    # 1. 查询用户
    sql = "SELECT id, username, password, is_approved, permissions, email, is_email_notify FROM users WHERE username = $1"
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

    stored_pw = user.get("password")
    if stored_pw and not _looks_like_bcrypt_hash(stored_pw):
        try:
            hashed_pw = get_password_hash(str(data.password or ""))
            await db.execute("UPDATE users SET password = $1 WHERE id = $2", hashed_pw, int(user["id"]))
        except Exception:
            pass
        
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
    try:
        auth_ver = await bump_user_auth_version(int(user["id"]))
    except Exception:
        auth_ver = await _get_or_init_auth_ver(user["id"])

    ip = _get_request_ip(request)
    ua = request.headers.get("user-agent")
    device = _infer_device_label(ua)
    try:
        await set_user_auth_session_info(int(user["id"]), auth_ver=int(auth_ver), ip=ip, user_agent=ua, device=device)
    except Exception:
        pass
    
    # 记录登录日志
    try:
        await db.execute(
            "INSERT INTO login_logs (user_id, ip, user_agent, device) VALUES ($1, $2, $3, $4)",
            int(user["id"]), ip, ua, device
        )
    except Exception as e:
        logger.error(f"Failed to record login log: {e}")

    # 发送登录提醒邮件
    # Check global email switch AND user preference
    email_enabled = SystemConfig.get("email_enabled")
    if (email_enabled == "1" or email_enabled == "true") and user.get("is_email_notify") and user.get("email"):
        # 调试日志
        logger.info(f"Preparing to send login notification to {user['email']} for user {user['username']}")
        asyncio.create_task(_send_login_notification_task(
            str(user["email"]), str(user["username"]), str(ip or "Unknown"), str(device)
        ))
    else:
        logger.info(f"Skip login notification: global email_enabled={email_enabled}, is_email_notify={user.get('is_email_notify')}, email={user.get('email')}")

    # 发送站内信通知 (始终发送，不依赖邮件开关)
    try:
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        site_msg_content = f"你的账号于 {current_time} 在 {ip or '未知IP'} ({device}) 登录。如非本人操作，请立即修改密码。"
        await NotificationService.create_site_message(
            sender_id=None,  # 系统发送
            sender_name="安全中心",
            title="登录提醒",
            content=site_msg_content,
            source="安全中心",
            target_user_id=int(user["id"]),
            is_global=False
        )
    except Exception as e:
        logger.error(f"发送站内信失败: {e}")

    token_data = {
        "id": user['id'],
        "username": user['username'],
        "roles": user_roles,
        "is_super": bool(is_super),
        "perm_ver": int(perm_ver),
        "auth_ver": int(auth_ver),
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

@router.post("/password/reset/request")
async def password_reset_request(data: PasswordResetRequestForm, request: Request):
    """
    请求重置密码
    
    验证邮箱和验证码，发送重置邮件
    """
    email = str(data.email or "").strip()
    if not _is_valid_email(email):
        return JSONResponse(status_code=400, content={"code": 400, "message": "邮箱格式不正确"})

    captcha_id = str(data.captcha_id or "").strip()
    captcha_answer = str(data.captcha_answer or "").strip()
    if not captcha_id or not captcha_answer:
        return JSONResponse(status_code=400, content={"code": 400, "message": "请完成验证码校验"})

    email_norm = email.strip().lower()
    redis_client = redis_manager.get_client()

    captcha_raw = await redis_client.get(_captcha_key(captcha_id))
    if not captcha_raw:
        return JSONResponse(status_code=400, content={"code": 400, "message": "验证码已过期，请刷新"})
    if not hmac.compare_digest(str(captcha_raw), _hash_text(captcha_answer)):
        return JSONResponse(status_code=400, content={"code": 400, "message": "验证码不正确"})
    await redis_client.delete(_captcha_key(captcha_id))

    cooldown_seconds = SystemConfig.get_int("auth:pwdreset:cooldown_seconds", 60)
    email_hour_limit = SystemConfig.get_int("auth:pwdreset:email_hour_limit", 5)
    ip_hour_limit = SystemConfig.get_int("auth:pwdreset:ip_hour_limit", 30)
    token_ttl_minutes = SystemConfig.get_int("auth:pwdreset:token_ttl_minutes", 30)

    cooldown_key = f"pwdreset:cooldown:{email_norm}"
    hour_email_key = f"pwdreset:email:{email_norm}:h"

    if await redis_client.exists(cooldown_key):
        return JSONResponse(status_code=429, content={"code": 429, "message": "发送过于频繁，请稍后再试"})

    raw_hour_email = await redis_client.get(hour_email_key)
    try:
        hour_email_cnt = int(raw_hour_email or 0)
    except Exception:
        hour_email_cnt = 0
    if hour_email_cnt >= int(email_hour_limit):
        return JSONResponse(status_code=429, content={"code": 429, "message": "发送过于频繁，请稍后再试"})

    ip = _get_request_ip(request)
    if ip:
        hour_ip_key = f"pwdreset:ip:{ip}:h"
        raw_hour_ip = await redis_client.get(hour_ip_key)
        try:
            hour_ip_cnt = int(raw_hour_ip or 0)
        except Exception:
            hour_ip_cnt = 0
        if hour_ip_cnt >= int(ip_hour_limit):
            return JSONResponse(status_code=429, content={"code": 429, "message": "发送过于频繁，请稍后再试"})
        ip_next = await redis_client.incr(hour_ip_key)
        if int(ip_next) == 1:
            await redis_client.expire(hour_ip_key, 3600)

    email_next = await redis_client.incr(hour_email_key)
    if int(email_next) == 1:
        await redis_client.expire(hour_email_key, 3600)

    await redis_client.set(cooldown_key, "1", ex=int(cooldown_seconds))

    user = await db.fetch_one("SELECT id, is_approved FROM users WHERE lower(email) = lower($1)", email_norm)
    if not user or user.get("is_approved") is False:
        return {"code": 200, "message": "如果邮箱已绑定，将发送重置链接", "data": {"cooldown_seconds": int(cooldown_seconds)}}

    host = SystemConfig.get("email_host")
    port = SystemConfig.get("email_port")
    username = SystemConfig.get("email_username")
    password = SystemConfig.get("email_password")
    nickname = SystemConfig.get("email_nickname")
    if not all([host, port, username, password]):
        await SystemConfig.load()
        host = SystemConfig.get("email_host")
        port = SystemConfig.get("email_port")
        username = SystemConfig.get("email_username")
        password = SystemConfig.get("email_password")
        nickname = SystemConfig.get("email_nickname")
    if not all([host, port, username, password]):
        return JSONResponse(status_code=500, content={"code": 500, "message": "系统未配置邮箱服务，无法发送邮件"})

    origin = request.headers.get("origin")
    base_url = (str(origin).rstrip("/") if origin else str(request.base_url).rstrip("/"))
    token = secrets.token_urlsafe(32)
    token_key = f"pwdreset:token:{token}"
    token_payload = {"user_id": int(user["id"]), "email": email_norm}
    await redis_client.set(token_key, json.dumps(token_payload, ensure_ascii=False), ex=int(token_ttl_minutes) * 60)

    reset_url = f"{base_url}/forgot-password?token={token}"
    subject = "重置密码链接"
    content = (
        "你正在重置账号密码。\n\n"
        f"请点击以下链接继续（{int(token_ttl_minutes)} 分钟内有效，仅可使用一次）：\n"
        f"{reset_url}\n\n"
        "如非本人操作，请忽略本邮件。"
    )
    ok, msg = await send_email(host, port, username, password, email_norm, subject, content, nickname=nickname)
    if not ok:
        await redis_client.delete(token_key)
        return JSONResponse(status_code=500, content={"code": 500, "message": f"邮件发送失败: {msg}"})

    return {"code": 200, "message": "如果邮箱已绑定，将发送重置链接", "data": {"cooldown_seconds": int(cooldown_seconds)}}

@router.post("/password/reset/confirm")
async def password_reset_confirm(data: PasswordResetConfirmForm):
    """
    确认重置密码
    
    使用邮件中的令牌重置密码
    """
    token = str(data.token or "").strip()
    new_password = str(data.new_password or "")

    if not token:
        return JSONResponse(status_code=400, content={"code": 400, "message": "链接无效或已过期"})
    if len(new_password) < 6:
        return JSONResponse(status_code=400, content={"code": 400, "message": "密码长度至少 6 位"})

    redis_client = redis_manager.get_client()
    token_key = f"pwdreset:token:{token}"
    raw = await redis_client.get(token_key)
    if not raw:
        return JSONResponse(status_code=400, content={"code": 400, "message": "链接无效或已过期"})

    try:
        payload = json.loads(raw)
    except Exception:
        await redis_client.delete(token_key)
        return JSONResponse(status_code=400, content={"code": 400, "message": "链接无效或已过期"})

    user_id = payload.get("user_id")
    email_norm = str(payload.get("email") or "").strip().lower()
    if not user_id:
        await redis_client.delete(token_key)
        return JSONResponse(status_code=400, content={"code": 400, "message": "链接无效或已过期"})

    user = await db.fetch_one("SELECT id FROM users WHERE id = $1 AND lower(email) = lower($2)", int(user_id), email_norm)
    if not user:
        await redis_client.delete(token_key)
        return JSONResponse(status_code=400, content={"code": 400, "message": "链接无效或已过期"})

    hashed_pw = get_password_hash(new_password)
    await db.execute("UPDATE users SET password = $1 WHERE id = $2", hashed_pw, int(user_id))
    try:
        await bump_user_auth_version(int(user_id))
    except Exception:
        pass
    await redis_client.delete(token_key)
    return {"code": 200, "message": "密码已重置"}

@router.post("/refresh")
async def refresh_token(response: Response, token: Optional[str] = Cookie(None)):
    """刷新访问令牌"""
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

    token_auth_ver = token_payload.get("auth_ver")
    if token_auth_ver is None:
        response.delete_cookie(key="token")
        return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "Token版本过旧，请重新登录", "status": "error", "error": "AUTH_TOKEN_TOO_OLD"},
        )
    try:
        token_auth_ver_int = int(token_auth_ver)
    except Exception:
        response.delete_cookie(key="token")
        return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "Token无效", "status": "error", "error": "AUTH_TOKEN_INVALID"},
        )
    try:
        redis_auth_ver = await get_or_init_user_auth_version(int(user_id))
    except Exception:
        redis_auth_ver = 1
    if int(token_auth_ver_int) != int(redis_auth_ver):
        response.delete_cookie(key="token")
        new_login = None
        try:
            new_login = await get_user_auth_session_info(int(user_id))
        except Exception:
            new_login = None
        return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "会话已失效，请重新登录", "status": "error", "error": "AUTH_SESSION_REVOKED", "data": {"new_login": new_login}},
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
    auth_ver = await _get_or_init_auth_ver(user["id"])
    token_data = {
        "id": user["id"],
        "username": user["username"],
        "roles": user_roles,
        "is_super": bool(is_super),
        "perm_ver": int(perm_ver),
        "auth_ver": int(auth_ver),
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
    """用户注册"""
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
    """获取当前用户的权限列表"""
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
    """获取当前用户信息（测试用）"""
    print(token.get('code'))
    if token.get('code') != 200:
        response.status_code = token.get('code')
        return token


    return {
        "code": 200,
        "status": "success",
    }

@router.get("/users/me/security")
async def get_my_security_settings(token_payload: dict = Depends(verify_token)):
    """
    获取用户安全设置
    """
    user_id = token_payload.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    row = await db.fetch_one("SELECT email, password, is_email_notify FROM users WHERE id = $1", int(user_id))
    if not row:
         raise HTTPException(status_code=404, detail="用户不存在")
         
    return {
        "code": 200,
        "data": {
            "email": row.get("email"),
            "has_password": bool(row.get("password")),
            "is_email_notify": bool(row.get("is_email_notify") or False)
        }
    }

class UserSecurityUpdate(BaseModel):
    email: Optional[str] = None
    old_password: Optional[str] = None
    new_password: Optional[str] = None
    is_email_notify: Optional[bool] = None

@router.put("/users/me/security")
async def update_my_security_settings(
    settings: UserSecurityUpdate,
    token_payload: dict = Depends(verify_token)
):
    """
    更新用户安全设置 (邮箱、密码、通知)
    """
    user_id = token_payload.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")

    user = await db.fetch_one("SELECT id, password, email FROM users WHERE id = $1", int(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # Update email
    if settings.email is not None:
        # Check if email is used by other users
        if settings.email:
            exists = await db.fetch_val("SELECT id FROM users WHERE email = $1 AND id != $2", settings.email, int(user_id))
            if exists:
                return {"code": 400, "message": "该邮箱已被其他用户使用"}
        await db.execute("UPDATE users SET email = $1 WHERE id = $2", settings.email, int(user_id))
    
    # Update notification setting
    if settings.is_email_notify is not None:
        await db.execute("UPDATE users SET is_email_notify = $1 WHERE id = $2", settings.is_email_notify, int(user_id))
        
    # Update password
    if settings.new_password:
        if not _verify_password_compat(str(settings.old_password or ""), user.get("password")):
             return {"code": 400, "message": "原密码错误"}
        hashed_pw = get_password_hash(settings.new_password)
        await db.execute("UPDATE users SET password = $1 WHERE id = $2", hashed_pw, int(user_id))
    
    return {"code": 200, "message": "设置更新成功"}

@router.get("/users/me/login-logs")
async def get_my_login_logs(
    page: int = 1, 
    page_size: int = 10, 
    token_payload: dict = Depends(verify_token)
):
    user_id = token_payload.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    offset = (page - 1) * page_size
    limit = page_size
    
    total = await db.fetch_val(
        "SELECT COUNT(*) FROM login_logs WHERE user_id = $1", 
        int(user_id)
    )
    
    rows = await db.fetch_all(
        "SELECT id, ip, device, created_at FROM login_logs WHERE user_id = $1 ORDER BY id DESC OFFSET $2 LIMIT $3",
        int(user_id), offset, limit
    )
    
    items = []
    for r in rows:
        items.append({
            "id": r["id"],
            "ip": r["ip"],
            "device": r["device"],
            "created_at": r["created_at"].strftime("%Y-%m-%d %H:%M:%S") if r["created_at"] else None
        })
        
    return {
        "code": 200, 
        "status": "success", 
        "data": {
            "total": total,
            "items": items,
            "page": page,
            "page_size": page_size
        }
    }

