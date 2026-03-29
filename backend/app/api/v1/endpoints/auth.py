"""
认证模块
处理用户登录、注册、密码重置、Token 刷新等认证相关逻辑。
"""

import asyncio
import base64
import logging
from datetime import timedelta, datetime
import hashlib
import hmac
from io import BytesIO
import math
import random
import re
import secrets
import time
from typing import Optional
import json

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Cookie, Query
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.core.database import db
from app.core.redis import redis_manager
from app.core.security import (
    create_access_token, 
    create_refresh_token, 
    verify_password, 
    get_password_hash, 
    verify_token, 
    user_is_super, 
    get_user_permissions_cached, 
    decode_access_token, 
    decode_refresh_token, 
    get_or_init_user_auth_version, 
    bump_user_auth_version, 
    set_user_auth_session_info, 
    get_user_auth_session_info
)
from app.core.config import settings
from app.core.system_config import SystemConfig
from app.services.rbac_service import RbacService
from app.services.notification_service import NotificationService
from app.utils.notification_sender import send_email

router = APIRouter()
logger = logging.getLogger(__name__)

# Redis Key 前缀定义
REFRESH_JTI_REDIS_KEY_PREFIX = "auth:refresh:jti:"

def _refresh_jti_key(jti: str) -> str:
    """生成 Refresh Token JTI 的 Redis Key"""
    return f"{REFRESH_JTI_REDIS_KEY_PREFIX}{str(jti or '').strip()}"

def _refresh_ttl_seconds() -> int:
    """获取 Refresh Token 的过期时间 (秒)，默认 30 天"""
    # 优先使用配置中的过期时间，如果没有配置则默认 30 天
    minutes = int(getattr(settings, "REFRESH_TOKEN_EXPIRE_MINUTES", 60 * 24 * 30) or (60 * 24 * 30))
    return max(60, minutes * 60)

# --- Pydantic 模型定义 ---

class LoginForm(BaseModel):
    """登录表单数据"""
    username: str
    password: str
    captcha_id: Optional[str] = None
    captcha_code: Optional[str] = None

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
    captcha_code: str

class PasswordResetConfirmForm(BaseModel):
    """密码重置确认表单"""
    token: str
    new_password: str

class UpdateSecurityForm(BaseModel):
    """更新安全设置表单"""
    is_email_notify: Optional[bool] = None
    is_login_email_notify: Optional[bool] = None


# --- 辅助函数 ---

def _is_valid_email(email: str) -> bool:
    """验证邮箱格式是否合法"""
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", str(email or "")))

def _get_request_ip(request: Request) -> Optional[str]:
    """获取请求 IP 地址，优先尝试 X-Forwarded-For (用于反向代理后的真实 IP)"""
    xff = request.headers.get("x-forwarded-for")
    # 如果有 XFF 头，取第一个 IP，否则取直连 IP
    return (xff.split(",")[0].strip() if xff else None) or (request.client.host if request.client else None)

def _captcha_key(captcha_id: str) -> str:
    """获取验证码 Redis Key"""
    return f"captcha:{str(captcha_id or '').strip()}"

def _captcha_issue_rate_key(ip: Optional[str]) -> str:
    ip_s = str(ip or "").strip()
    return f"auth:captcha:issue:ip:{ip_s or 'unknown'}"

def _hash_text(value: str) -> str:
    """计算文本的 SHA256 哈希"""
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()

def _captcha_invalid_response() -> tuple[bool, str, str]:
    return False, "AUTH_CAPTCHA_INVALID", "验证码错误或已失效"

def _captcha_normalize(value: str) -> str:
    return str(value or "").strip().upper()

def _captcha_text_length() -> int:
    return 4

def _captcha_max_failures() -> int:
    raw = SystemConfig.get_int("auth:captcha:max_failures", 5)
    try:
        v = int(raw or 5)
    except Exception:
        v = 5
    return min(10, max(1, v))

def _generate_captcha_text() -> str:
    charset = "23456789"
    length = _captcha_text_length()
    return "".join(secrets.choice(charset) for _ in range(length))

def _build_captcha_base64(captcha_text: str) -> str:
    width, height = 240, 96
    image = Image.new("RGB", (width, height), (250, 252, 255))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 64)
    except Exception:
        font = ImageFont.load_default()

    for _ in range(1):
        x1 = random.randint(0, width - 1)
        y1 = random.randint(0, height - 1)
        x2 = random.randint(0, width - 1)
        y2 = random.randint(0, height - 1)
        draw.line(
            [(x1, y1), (x2, y2)],
            fill=(random.randint(160, 195), random.randint(160, 195), random.randint(160, 195)),
            width=1,
        )

    for _ in range(60):
        x = random.randint(0, width - 1)
        y = random.randint(0, height - 1)
        draw.point(
            (x, y),
            fill=(random.randint(170, 215), random.randint(170, 215), random.randint(170, 215)),
        )

    char_width = width / max(1, len(captcha_text))
    for idx, ch in enumerate(captcha_text):
        bbox = draw.textbbox((0, 0), ch, font=font)
        char_w = max(1, int(bbox[2] - bbox[0]))
        char_h = max(1, int(bbox[3] - bbox[1]))
        tx = int(idx * char_width + (char_width - char_w) / 2 + random.randint(-2, 2))
        ty = int((height - char_h) / 2 + random.randint(-2, 2))
        draw.text(
            (tx, ty),
            ch,
            font=font,
            fill=(random.randint(25, 70), random.randint(25, 70), random.randint(25, 70)),
        )

    for x in range(width):
        offset = int(0.8 * math.sin(2 * math.pi * x / 120))
        for y in range(height):
            ny = y + offset
            if 0 <= ny < height:
                image.putpixel((x, y), image.getpixel((x, ny)))

    image = image.filter(ImageFilter.SMOOTH)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

async def _is_captcha_issue_rate_limited(redis_client, *, ip: Optional[str]) -> bool:
    window_seconds = SystemConfig.get_int("auth:captcha:issue:window_seconds", 60)
    max_requests = SystemConfig.get_int("auth:captcha:issue:max_requests", 30)
    try:
        window_seconds = int(window_seconds or 60)
    except Exception:
        window_seconds = 60
    try:
        max_requests = int(max_requests or 30)
    except Exception:
        max_requests = 30
    window_seconds = min(300, max(10, window_seconds))
    max_requests = min(120, max(1, max_requests))

    key = _captcha_issue_rate_key(ip)
    current = await redis_client.incr(key)
    if int(current) == 1:
        await redis_client.expire(key, window_seconds)
    return int(current) > max_requests

async def _save_captcha(redis_client, *, captcha_id: str, answer_hash: str, ttl_seconds: int) -> None:
    key = _captcha_key(captcha_id)
    await redis_client.hset(
        key,
        mapping={
            "answer_hash": str(answer_hash),
            "fail_count": "0",
        },
    )
    await redis_client.expire(key, int(ttl_seconds))

def _login_fail_key_ip(ip: Optional[str]) -> Optional[str]:
    ip_s = str(ip or "").strip()
    if not ip_s:
        return None
    return f"auth:login:fail:ip:{ip_s}"

def _login_fail_key_user(username: str) -> str:
    u = str(username or "").strip().lower()
    return f"auth:login:fail:user:{u}"

async def _get_login_fail_counts(redis_client, *, ip: Optional[str], username: str) -> tuple[int, int]:
    window_seconds = SystemConfig.get_int("auth:login:rate:window_seconds", 300)
    window_seconds = max(10, int(window_seconds or 300))
    window_ms = window_seconds * 1000
    expire_seconds = window_seconds * 2
    now_ms = int(time.time() * 1000)
    window_start = now_ms - window_ms

    ip_key = _login_fail_key_ip(ip)
    user_key = _login_fail_key_user(username)

    pipe = redis_client.pipeline(transaction=False)
    if ip_key:
        pipe.zremrangebyscore(ip_key, 0, window_start)
        pipe.zcard(ip_key)
        pipe.expire(ip_key, expire_seconds)
    pipe.zremrangebyscore(user_key, 0, window_start)
    pipe.zcard(user_key)
    pipe.expire(user_key, expire_seconds)
    res = await pipe.execute()

    ip_cnt = 0
    user_cnt = 0
    idx = 0
    if ip_key:
        try:
            ip_cnt = int(res[idx + 1] or 0)
        except Exception:
            ip_cnt = 0
        idx += 3
    try:
        user_cnt = int(res[idx + 1] or 0)
    except Exception:
        user_cnt = 0
    return ip_cnt, user_cnt

async def _record_login_fail(redis_client, *, ip: Optional[str], username: str) -> None:
    window_seconds = SystemConfig.get_int("auth:login:rate:window_seconds", 300)
    window_seconds = max(10, int(window_seconds or 300))
    expire_seconds = window_seconds * 2
    now_ms = int(time.time() * 1000)
    member = f"{now_ms}:{secrets.token_urlsafe(8)}"

    ip_key = _login_fail_key_ip(ip)
    user_key = _login_fail_key_user(username)

    pipe = redis_client.pipeline(transaction=False)
    if ip_key:
        pipe.zadd(ip_key, {member: now_ms})
        pipe.expire(ip_key, expire_seconds)
    pipe.zadd(user_key, {member: now_ms})
    pipe.expire(user_key, expire_seconds)
    await pipe.execute()

async def _should_require_login_captcha(redis_client, *, ip: Optional[str], username: str) -> bool:
    ip_cnt, user_cnt = await _get_login_fail_counts(redis_client, ip=ip, username=username)
    ip_threshold = SystemConfig.get_int("auth:login:captcha:ip_threshold", 5)
    user_threshold = SystemConfig.get_int("auth:login:captcha:user_threshold", 5)
    try:
        ip_threshold = int(ip_threshold or 5)
    except Exception:
        ip_threshold = 5
    try:
        user_threshold = int(user_threshold or 5)
    except Exception:
        user_threshold = 5
    ip_threshold = max(0, ip_threshold)
    user_threshold = max(0, user_threshold)
    if ip_threshold == 0 or user_threshold == 0:
        return True
    if ip_cnt >= ip_threshold:
        return True
    if user_cnt >= user_threshold:
        return True
    return False

async def _is_login_rate_limited(redis_client, *, ip: Optional[str], username: str) -> bool:
    ip_cnt, user_cnt = await _get_login_fail_counts(redis_client, ip=ip, username=username)
    ip_max = SystemConfig.get_int("auth:login:rate:ip_max_fails", 30)
    user_max = SystemConfig.get_int("auth:login:rate:user_max_fails", 15)
    try:
        ip_max = int(ip_max or 30)
    except Exception:
        ip_max = 30
    try:
        user_max = int(user_max or 15)
    except Exception:
        user_max = 15
    ip_max = max(1, ip_max)
    user_max = max(1, user_max)
    if ip_cnt >= ip_max:
        return True
    if user_cnt >= user_max:
        return True
    return False

async def _verify_login_captcha(redis_client, *, captcha_id: str, captcha_code: str) -> tuple[bool, str, str]:
    cid = str(captcha_id or "").strip()
    ans = _captcha_normalize(captcha_code)
    if not cid or not ans:
        return _captcha_invalid_response()

    key = _captcha_key(cid)
    payload = await redis_client.hgetall(key)
    if not payload:
        return _captcha_invalid_response()

    answer_hash = str(payload.get("answer_hash") or "")
    if not answer_hash:
        await redis_client.delete(key)
        return _captcha_invalid_response()

    if not hmac.compare_digest(answer_hash, _hash_text(ans)):
        fail_count = await redis_client.hincrby(key, "fail_count", 1)
        if int(fail_count) >= _captcha_max_failures():
            await redis_client.delete(key)
        return _captcha_invalid_response()

    await redis_client.delete(key)
    return True, "", ""

def _infer_device_label(user_agent: Optional[str]) -> str:
    """根据 User-Agent 推断设备类型和浏览器"""
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

def _normalize_login_notice_value(value: Optional[str]) -> Optional[str]:
    text = str(value or "").strip()
    return text or None

def _should_send_login_change_notice(previous_login: Optional[dict], *, ip: Optional[str], device: Optional[str]) -> bool:
    """
    仅在相较上一次登录的 IP 或设备发生变化时，才发送登录提醒。
    """
    if not previous_login:
        return False

    previous_ip = _normalize_login_notice_value(previous_login.get("ip"))
    previous_device = _normalize_login_notice_value(previous_login.get("device"))
    current_ip = _normalize_login_notice_value(ip)
    current_device = _normalize_login_notice_value(device)
    return previous_ip != current_ip or previous_device != current_device

async def _send_login_notification_task(email: str, username: str, ip: str, device: str):
    """
    后台任务：发送登录提醒邮件
    """
    try:
        # 获取邮件配置
        host = SystemConfig.get("email_host")
        port = SystemConfig.get("email_port")
        username_smtp = SystemConfig.get("email_username")
        password = SystemConfig.get("email_password")
        nickname = SystemConfig.get("email_nickname")
        
        # 如果内存中没有配置，尝试从数据库重新加载 (防止配置更新后未生效)
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

        subject = "账号登录提醒"
        content = (
            f"{username}，你好：\n\n"
            "检测到你的账号发生了一次新的登录，登录信息如下：\n"
            f"登录时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"登录 IP：{ip}\n"
            f"登录设备：{device}\n\n"
            "如果这是你本人操作，无需处理。\n"
            "如果不是你本人登录，请尽快修改密码，并检查账号安全设置。"
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
async def get_captcha(request: Request, prev_captcha_id: Optional[str] = Query(default=None)):
    """
    获取图形验证码
    """
    redis_client = redis_manager.get_client()
    old_captcha_id = str(prev_captcha_id or "").strip()
    if old_captcha_id:
        await redis_client.delete(_captcha_key(old_captcha_id))
    ip = _get_request_ip(request)
    if await _is_captcha_issue_rate_limited(redis_client, ip=ip):
        return JSONResponse(
            status_code=429,
            content={
                "code": 429,
                "message": "请求过于频繁，请稍后再试",
                "status": "error",
                "error": "AUTH_CAPTCHA_RATE_LIMITED",
            },
        )
    ttl_seconds = SystemConfig.get_int("auth:captcha:ttl_seconds", 300)
    try:
        ttl_seconds = int(ttl_seconds or 300)
    except Exception:
        ttl_seconds = 300
    ttl_seconds = min(600, max(120, ttl_seconds))

    captcha_text = _generate_captcha_text()
    captcha_image_base64 = _build_captcha_base64(captcha_text)
    captcha_id = secrets.token_urlsafe(16)

    await _save_captcha(
        redis_client,
        captcha_id=captcha_id,
        answer_hash=_hash_text(captcha_text),
        ttl_seconds=int(ttl_seconds),
    )

    return {
        "code": 200,
        "data": {
            "captcha_id": captcha_id,
            "image_base64": captcha_image_base64,
            "image_mime": "image/png",
            "ttl_seconds": int(ttl_seconds),
        },
    }

def _normalize_permissions(value) -> list[str]:
    """标准化权限字段，确保返回字符串列表"""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if x is not None]
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        try:
            # 尝试解析 JSON 字符串
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(x) for x in parsed if x is not None]
        except Exception:
            return []
    return []

def _looks_like_bcrypt_hash(value: str) -> bool:
    """检查字符串是否看起来像 bcrypt 哈希"""
    s = str(value or "")
    return s.startswith("$2a$") or s.startswith("$2b$") or s.startswith("$2y$")

def _verify_password_compat(plain_password: str, stored_password: str) -> bool:
    """验证密码 (兼容明文和哈希)"""
    if stored_password is None:
        return False
    stored = str(stored_password)
    
    # 如果是 bcrypt 哈希，使用 passlib 验证
    if _looks_like_bcrypt_hash(stored):
        try:
            return bool(verify_password(plain_password, stored))
        except Exception:
            return False
            
    # 如果不是 bcrypt 哈希，尝试明文比较 (旧数据兼容)
    # 注意：这只是为了兼容老旧数据，登录成功后应立即升级为哈希
    return stored == str(plain_password)

async def _get_or_init_perm_ver(user_id: int) -> int:
    """获取或初始化用户权限版本号 (用于强制刷新权限)"""
    redis_client = redis_manager.get_client()
    key = f"authz:ver:user:{int(user_id)}"
    raw = await redis_client.get(key)
    
    # 如果没有版本号，初始化为 1
    if raw is None:
        await redis_client.set(key, "1", ex=60 * 60 * 24 * 30)
        return 1
    try:
        v = int(raw)
        # 延长有效期
        await redis_client.expire(key, 60 * 60 * 24 * 30)
        return v if v > 0 else 1
    except Exception:
        # 解析失败重置为 1
        await redis_client.set(key, "1", ex=60 * 60 * 24 * 30)
        return 1

async def _get_or_init_auth_ver(user_id: int) -> int:
    """获取或初始化用户认证版本号 (用于单点登录控制)"""
    try:
        return await get_or_init_user_auth_version(int(user_id))
    except Exception:
        # 降级处理：直接操作 Redis
        redis_client = redis_manager.get_client()
        key = f"auth:ver:user:{int(user_id)}"
        raw = await redis_client.get(key)
        if raw is None:
            await redis_client.set(key, "1", ex=60 * 60 * 24 * 30)
            return 1
        try:
            v = int(raw)
            await redis_client.expire(key, 60 * 60 * 24 * 30)
            return v if v > 0 else 1
        except Exception:
            await redis_client.set(key, "1", ex=60 * 60 * 24 * 30)
            return 1

# --- API 路由 ---

@router.post("/login")
async def login(data: LoginForm, response: Response, request: Request):
    """
    用户登录
    
    验证用户名和密码，返回访问令牌 (Token)。
    如果密码是明文，会自动升级为哈希存储。
    会记录登录日志，并根据设置发送登录提醒。
    """
    ip = _get_request_ip(request)
    username_input = str(data.username or "").strip()
    username_norm = username_input.lower()

    try:
        redis_client = redis_manager.get_client()
        if await _is_login_rate_limited(redis_client, ip=ip, username=username_norm):
            return JSONResponse(
                status_code=429,
                content={
                    "code": 429,
                    "message": "尝试过于频繁，请稍后再试",
                    "status": "error",
                    "error": "AUTH_RATE_LIMITED",
                    "data": {"captcha_required": True},
                },
            )

        captcha_required = await _should_require_login_captcha(redis_client, ip=ip, username=username_norm)
        if captcha_required:
            ok, err_code, err_msg = await _verify_login_captcha(
                redis_client,
                captcha_id=str(data.captcha_id or ""),
                captcha_code=str(data.captcha_code or ""),
            )
            if not ok:
                try:
                    await _record_login_fail(redis_client, ip=ip, username=username_norm)
                except Exception:
                    pass
                return JSONResponse(
                    status_code=400,
                    content={
                        "code": 400,
                        "message": err_msg,
                        "status": "error",
                        "error": err_code,
                        "data": {"captcha_required": True},
                    },
                )
    except Exception:
        pass

    # 1. 查询用户基础信息
    sql = "SELECT id, username, password, is_approved, email, is_email_notify, is_login_email_notify FROM users WHERE username = $1"
    user = await db.fetch_one(sql, username_input)

    if not user:
        # 用户不存在，返回统一的错误提示，防止用户名枚举
        try:
            redis_client = redis_manager.get_client()
            await _record_login_fail(redis_client, ip=ip, username=username_norm)
        except Exception:
            pass
        return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "用户名或密码错误", "status": "error"}
        )

    # 检查账户是否被封禁或未审核
    if user['is_approved'] is False:
        try:
            redis_client = redis_manager.get_client()
            await _record_login_fail(redis_client, ip=ip, username=username_norm)
        except Exception:
            pass
        return JSONResponse(
            status_code=403,
            content={"code": 403, "message": "账户未审核或已封禁，请联系管理员", "status": "error"}
        )

    # 2. 验证密码 (兼容明文和哈希)
    if not _verify_password_compat(data.password, user.get("password")):
        try:
            redis_client = redis_manager.get_client()
            await _record_login_fail(redis_client, ip=ip, username=username_norm)
        except Exception:
            pass
        return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "用户名或密码错误", "status": "error"}
        )

    try:
        redis_client = redis_manager.get_client()
        await redis_client.delete(_login_fail_key_user(username_norm))
    except Exception:
        pass

    # 如果数据库中存储的是明文密码，自动升级为 bcrypt 哈希
    # 这是一个渐进式迁移策略，用户登录一次即可自动升级安全性
    stored_pw = user.get("password")
    if stored_pw and not _looks_like_bcrypt_hash(stored_pw):
        try:
            hashed_pw = get_password_hash(str(data.password or ""))
            await db.execute("UPDATE users SET password = $1 WHERE id = $2", hashed_pw, int(user["id"]))
        except Exception:
            pass
        
    # 3. 生成 Token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    user_permissions = []
    user_roles: list[str] = []
    try:
        # 获取角色权限和角色列表
        user_permissions = await RbacService.get_user_permission_codes(user["id"])
        user_roles = await RbacService.get_user_role_codes(user["id"])
    except Exception:
        pass
    
    # 3.2 超级管理员判断
    is_super = user_is_super({"roles": user_roles})

    # 3.4 获取权限版本和认证版本
    perm_ver = await _get_or_init_perm_ver(user["id"])
    try:
        # 增加认证版本号 (auth_ver)，使该用户之前的 Token 全部失效
        # 实现了单点登录 (SSO) 的效果：新登录踢掉旧登录
        auth_ver = await bump_user_auth_version(int(user["id"]))
    except Exception:
        auth_ver = await _get_or_init_auth_ver(user["id"])

    # 4. 记录日志和会话信息
    ua = request.headers.get("user-agent")
    device = _infer_device_label(ua)

    previous_login = None
    try:
        previous_login = await db.fetch_one(
            """
            SELECT ip, device
            FROM login_logs
            WHERE user_id = $1
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            int(user["id"]),
        )
    except Exception as e:
        logger.error(f"Failed to query previous login log: {e}")

    should_send_login_notice = _should_send_login_change_notice(previous_login, ip=ip, device=device)
    
    # 记录当前会话信息到 Redis (用于展示"当前在线设备")
    try:
        await set_user_auth_session_info(int(user["id"]), auth_ver=int(auth_ver), ip=ip, user_agent=ua, device=device)
    except Exception:
        pass
    
    # 记录持久化登录日志到数据库
    try:
        await db.execute(
            "INSERT INTO login_logs (user_id, ip, user_agent, device) VALUES ($1, $2, $3, $4)",
            int(user["id"]), ip, ua, device
        )
    except Exception as e:
        logger.error(f"Failed to record login log: {e}")

    # 5. 发送通知
    if should_send_login_notice:
        # 5.1 发送邮件提醒 (如果开启了邮件通知)
        enabled, reason = await NotificationService._is_login_email_globally_enabled()
        email_notify_enabled = bool(user.get("is_email_notify", False))
        login_email_notify_enabled = bool(user.get("is_login_email_notify", user.get("is_email_notify", False)))
        if enabled and user.get("email") and email_notify_enabled and login_email_notify_enabled:
            logger.info(f"Preparing to send login notification to {user['email']} for user {user['username']}")
            # 异步发送邮件，不阻塞登录响应
            asyncio.create_task(_send_login_notification_task(
                str(user["email"]), str(user["username"]), str(ip or "Unknown"), str(device)
            ))
        else:
            logger.info(
                "Skip login notification: "
                f"global_email_enabled={enabled} reason={reason}, "
                f"email={user.get('email')}, "
                f"email_notify_enabled={email_notify_enabled}, "
                f"login_email_notify_enabled={login_email_notify_enabled}"
            )

        # 5.2 发送站内信通知
        try:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            site_msg_content = (
                f"检测到你的账号于 {current_time} 登录。\n"
                f"登录 IP：{ip or '未知IP'}\n"
                f"登录设备：{device}\n"
                "如为本人操作，可忽略；如非本人操作，请尽快修改密码。"
            )
            await NotificationService.create_site_message(
                sender_id=None,  # None 表示系统发送
                sender_name="安全中心",
                title="账号登录提醒",
                content=site_msg_content,
                source="安全中心",
                target_user_id=int(user["id"]),
                is_global=False
            )
        except Exception as e:
            logger.error(f"发送站内信失败: {e}")
    else:
        logger.info(
            "Skip login change notice: previous login unchanged or unavailable, "
            f"user_id={int(user['id'])}, ip={ip}, device={device}"
        )

    # 6. 构建并返回 Token
    token_data = {
        "id": user['id'],
        "username": user['username'],
        "roles": user_roles,
        "is_super": bool(is_super),
        "perm_ver": int(perm_ver), # 权限版本，变更时 Token 失效
        "auth_ver": int(auth_ver), # 认证版本，重新登录时 Token 失效
    }
    
    # 创建 JWT Access Token
    access_token = create_access_token(
        subject=token_data,
        expires_delta=access_token_expires
    )

    # 创建 Refresh Token (用于获取新的 Access Token)
    refresh_jti = secrets.token_urlsafe(32)
    refresh_token = create_refresh_token(
        subject={"id": user["id"], "auth_ver": int(auth_ver)},
        expires_delta=timedelta(seconds=_refresh_ttl_seconds()),
        jti=refresh_jti,
    )

    # 存储 Refresh Token 的 JTI 到 Redis，用于撤销和验证
    try:
        redis_client = redis_manager.get_client()
        await redis_client.set(_refresh_jti_key(refresh_jti), str(int(user["id"])), ex=_refresh_ttl_seconds())
    except Exception:
        pass
    
    # 设置 HTTP Only Cookie，防止 XSS 攻击窃取 Token
    response.set_cookie(
        key='token',
        value=access_token,
        httponly=True,
        secure=False, # 生产环境建议为 True
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=_refresh_ttl_seconds(),
    )
    
    return {
        "status": "success",
        "message": "登录成功",
    }

@router.post("/password/reset/request")
async def password_reset_request(data: PasswordResetRequestForm, request: Request):
    """
    请求重置密码
    
    验证邮箱和验证码，发送重置邮件。
    包含多重防刷机制 (冷却时间、每小时邮箱限制、每小时IP限制)。
    """
    email = str(data.email or "").strip()
    if not _is_valid_email(email):
        return JSONResponse(status_code=400, content={"code": 400, "message": "邮箱格式不正确"})

    captcha_id = str(data.captcha_id or "").strip()
    captcha_code = str(data.captcha_code or "").strip()
    if not captcha_id or not captcha_code:
        return JSONResponse(status_code=400, content={"code": 400, "message": "请完成验证码校验"})

    email_norm = email.strip().lower()
    redis_client = redis_manager.get_client()

    # 1. 校验图形验证码
    ok, _, _ = await _verify_login_captcha(
        redis_client,
        captcha_id=captcha_id,
        captcha_code=captcha_code,
    )
    if not ok:
        return JSONResponse(status_code=400, content={"code": 400, "message": "验证码错误或已失效"})

    # 2. 频率限制检查 (Rate Limiting)
    cooldown_seconds = SystemConfig.get_int("auth:pwdreset:cooldown_seconds", 60)
    email_hour_limit = SystemConfig.get_int("auth:pwdreset:email_hour_limit", 5)
    ip_hour_limit = SystemConfig.get_int("auth:pwdreset:ip_hour_limit", 30)
    token_ttl_minutes = SystemConfig.get_int("auth:pwdreset:token_ttl_minutes", 30)

    cooldown_key = f"pwdreset:cooldown:{email_norm}"
    hour_email_key = f"pwdreset:email:{email_norm}:h"

    # 2.1 检查单邮箱冷却时间
    if await redis_client.exists(cooldown_key):
        return JSONResponse(status_code=429, content={"code": 429, "message": "发送过于频繁，请稍后再试"})

    # 2.2 检查单邮箱每小时发送次数
    raw_hour_email = await redis_client.get(hour_email_key)
    try:
        hour_email_cnt = int(raw_hour_email or 0)
    except Exception:
        hour_email_cnt = 0
    if hour_email_cnt >= int(email_hour_limit):
        return JSONResponse(status_code=429, content={"code": 429, "message": "发送过于频繁，请稍后再试"})

    # 2.3 检查单 IP 每小时发送次数 (防止 IP 滥用)
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
        # 计数 +1
        ip_next = await redis_client.incr(hour_ip_key)
        if int(ip_next) == 1:
            await redis_client.expire(hour_ip_key, 3600)

    # 增加邮箱计数
    email_next = await redis_client.incr(hour_email_key)
    if int(email_next) == 1:
        await redis_client.expire(hour_email_key, 3600)

    # 设置冷却时间
    await redis_client.set(cooldown_key, "1", ex=int(cooldown_seconds))

    # 3. 检查用户是否存在
    user = await db.fetch_one("SELECT id, is_approved FROM users WHERE lower(email) = lower($1)", email_norm)
    if not user or user.get("is_approved") is False:
        # 安全策略：即使邮箱不存在，也返回成功提示。
        # 这样可以防止恶意用户通过接口响应差异来枚举已注册的邮箱地址。
        return {"code": 200, "message": "如果邮箱已绑定，将发送重置链接", "data": {"cooldown_seconds": int(cooldown_seconds)}}

    # 4. 获取邮件配置
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

    # 5. 生成重置 Token 和链接
    origin = request.headers.get("origin")
    base_url = (str(origin).rstrip("/") if origin else str(request.base_url).rstrip("/"))
    token = secrets.token_urlsafe(32)
    token_key = f"pwdreset:token:{token}"
    token_payload = {"user_id": int(user["id"]), "email": email_norm}
    
    # 将 Token 存储到 Redis，设置过期时间
    await redis_client.set(token_key, json.dumps(token_payload, ensure_ascii=False), ex=int(token_ttl_minutes) * 60)

    reset_url = f"{base_url}/forgot-password?token={token}"
    subject = "重置密码链接"
    content = (
        "你正在重置账号密码。\n\n"
        f"请点击以下链接继续（{int(token_ttl_minutes)} 分钟内有效，仅可使用一次）：\n"
        f"{reset_url}\n\n"
        "如非本人操作，请忽略本邮件。"
    )
    
    # 6. 发送邮件
    ok, msg = await send_email(host, port, username, password, email_norm, subject, content, nickname=nickname)
    if not ok:
        # 发送失败则删除 Token，允许用户重试
        await redis_client.delete(token_key)
        return JSONResponse(status_code=500, content={"code": 500, "message": f"邮件发送失败: {msg}"})

    return {"code": 200, "message": "如果邮箱已绑定，将发送重置链接", "data": {"cooldown_seconds": int(cooldown_seconds)}}

@router.post("/password/reset/confirm")
async def password_reset_confirm(data: PasswordResetConfirmForm):
    """
    确认重置密码
    
    验证邮件中的 Token，并更新用户密码。
    更新后会使该用户所有已登录的设备失效 (SSO 登出)。
    """
    token = str(data.token or "").strip()
    new_password = str(data.new_password or "")

    if not token:
        return JSONResponse(status_code=400, content={"code": 400, "message": "链接无效或已过期"})
    if len(new_password) < 6:
        return JSONResponse(status_code=400, content={"code": 400, "message": "密码长度至少 6 位"})

    redis_client = redis_manager.get_client()
    token_key = f"pwdreset:token:{token}"
    
    # 1. 验证 Token 是否存在
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

    # 2. 再次确认用户一致性
    user = await db.fetch_one("SELECT id FROM users WHERE id = $1 AND lower(email) = lower($2)", int(user_id), email_norm)
    if not user:
        await redis_client.delete(token_key)
        return JSONResponse(status_code=400, content={"code": 400, "message": "链接无效或已过期"})

    # 3. 更新密码
    hashed_pw = get_password_hash(new_password)
    await db.execute("UPDATE users SET password = $1 WHERE id = $2", hashed_pw, int(user_id))
    
    # 4. 强制下线所有设备
    try:
        # 增加认证版本号，之前的 Token 将全部失效
        await bump_user_auth_version(int(user_id))
    except Exception:
        pass
    
    # 5. 销毁 Token (一次性使用)
    await redis_client.delete(token_key)

    # 6. 记录审计日志
    try:
        user_snapshot = {"id": user_id, "email": email_norm}
        await UserAdminAuditService.log(
            action="auth.password_reset",
            actor=user_snapshot, # Use a snapshot as actor, since no user is logged in
            target_user_id=int(user_id),
            request_ip=None, # Cannot get IP here
            detail={"source": "forgot_password"},
        )
    except Exception:
        logger.exception("audit log for auth.password_reset failed")
    
    return {"code": 200, "message": "密码已重置"}

@router.post("/refresh")
async def refresh_token(response: Response, refresh_token: Optional[str] = Cookie(None)):
    """
    刷新 Access Token
    
    使用 Refresh Token 换取新的 Access Token 和 Refresh Token (Token 轮换)。
    检查 Token 有效性、版本号一致性以及 JTI 是否有效。
    """
    if refresh_token is None:
        return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "未登录", "status": "error", "error": "AUTH_NOT_LOGGED_IN"},
        )

    # 1. 解析 Refresh Token (校验签名和过期时间)
    token_payload = decode_refresh_token(refresh_token)
    if not token_payload:
        # Token 无效，清除 Cookie
        response.delete_cookie(key="token")
        response.delete_cookie(key="refresh_token")
        return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "Token无效", "status": "error", "error": "AUTH_TOKEN_INVALID"},
        )

    user_id = token_payload.get("id") or token_payload.get("sub")
    if not user_id:
        response.delete_cookie(key="token")
        response.delete_cookie(key="refresh_token")
        return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "未登录", "status": "error", "error": "AUTH_NOT_LOGGED_IN"},
        )

    try:
        uid = int(user_id)
    except Exception:
        response.delete_cookie(key="token")
        response.delete_cookie(key="refresh_token")
        return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "Token无效", "status": "error", "error": "AUTH_TOKEN_INVALID"},
        )

    # 2. 验证 Auth Version (单点登录检查)
    # 检查 Token 中的 auth_ver 是否与 Redis 中的一致。如果不一致，说明用户已重新登录或修改密码。
    token_auth_ver = token_payload.get("auth_ver")
    if token_auth_ver is None:
        response.delete_cookie(key="token")
        response.delete_cookie(key="refresh_token")
        return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "Token无效", "status": "error", "error": "AUTH_TOKEN_INVALID"},
        )
    try:
        token_auth_ver_int = int(token_auth_ver)
    except Exception:
        response.delete_cookie(key="token")
        response.delete_cookie(key="refresh_token")
        return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "Token无效", "status": "error", "error": "AUTH_TOKEN_INVALID"},
        )

    try:
        redis_auth_ver = await get_or_init_user_auth_version(uid)
    except Exception:
        redis_auth_ver = 1
    
    if int(token_auth_ver_int) != int(redis_auth_ver):
        # 版本不一致，强制登出
        response.delete_cookie(key="token")
        response.delete_cookie(key="refresh_token")
        new_login = None
        try:
            new_login = await get_user_auth_session_info(uid)
        except Exception:
            new_login = None
        return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "会话已失效，请重新登录", "status": "error", "error": "AUTH_SESSION_REVOKED", "data": {"new_login": new_login}},
        )

    # 3. 验证 JTI (Token 撤销检查)
    # Refresh Token 是有状态的，其 ID (JTI) 存储在 Redis 中。如果 Redis 中没有该 JTI，说明 Token 已失效或被轮换。
    jti = str(token_payload.get("jti") or "").strip()
    if not jti:
        response.delete_cookie(key="token")
        response.delete_cookie(key="refresh_token")
        return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "Token无效", "status": "error", "error": "AUTH_TOKEN_INVALID"},
        )

    redis_client = redis_manager.get_client()
    try:
        bound_uid = await redis_client.get(_refresh_jti_key(jti))
    except Exception:
        bound_uid = None
    if not bound_uid or str(bound_uid).strip() != str(uid):
        response.delete_cookie(key="token")
        response.delete_cookie(key="refresh_token")
        return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "会话已失效，请重新登录", "status": "error", "error": "AUTH_SESSION_REVOKED"},
        )

    # 4. 检查用户状态 (二次确认用户未被封禁)
    user = await db.fetch_one(
        "SELECT id, username, is_approved, COALESCE(is_deleted, FALSE) AS is_deleted FROM users WHERE id = $1",
        uid,
    )
    if not user:
        response.delete_cookie(key="token")
        response.delete_cookie(key="refresh_token")
        return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "用户不存在", "status": "error", "error": "AUTH_ACCOUNT_DISABLED"},
        )
    if user.get("is_approved") is False or user.get("is_deleted") is True:
        response.delete_cookie(key="token")
        response.delete_cookie(key="refresh_token")
        try:
            await redis_client.delete(_refresh_jti_key(jti))
        except Exception:
            pass
        return JSONResponse(
            status_code=401,
            content={"code": 401, "message": "账户未审核或已封禁，请联系管理员", "status": "error", "error": "AUTH_ACCOUNT_DISABLED"},
        )

    # 5. 权限检查 (是否允许登录)
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    user_permissions = []
    user_roles: list[str] = []
    try:
        role_permissions = await RbacService.get_user_permission_codes(user["id"])
        user_roles = await RbacService.get_user_role_codes(user["id"])
        merged = set(user_permissions) | set(role_permissions)
        user_permissions = sorted(list(merged))
    except Exception:
        pass

    is_super = user_is_super({"roles": user_roles})

    # 6. 生成新 Token (Token 轮换)
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

    # 生成新的 Refresh Token
    next_refresh_jti = secrets.token_urlsafe(32)
    next_refresh_token = create_refresh_token(
        subject={"id": uid, "auth_ver": int(auth_ver)},
        expires_delta=timedelta(seconds=_refresh_ttl_seconds()),
        jti=next_refresh_jti,
    )

    # 7. 更新 Redis 状态 (删除旧 JTI，保存新 JTI)
    try:
        await redis_client.delete(_refresh_jti_key(jti))
    except Exception:
        pass
    try:
        await redis_client.set(_refresh_jti_key(next_refresh_jti), str(uid), ex=_refresh_ttl_seconds())
    except Exception:
        pass

    # 8. 更新 Cookie
    response.set_cookie(
        key="token",
        value=access_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=next_refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=_refresh_ttl_seconds(),
    )

    return {"code": 200, "status": "success"}

@router.post("/logout")
async def logout(response: Response, refresh_token: Optional[str] = Cookie(None)):
    """
    用户登出
    
    清除 Redis 中的 refresh_token 记录，并删除浏览器中的 token 和 refresh_token Cookie
    """
    # 如果存在 refresh_token，尝试解析并清除对应的 Redis 记录
    if refresh_token:
        payload = decode_refresh_token(refresh_token)
        if payload:
            jti = str(payload.get("jti") or "").strip()
            if jti:
                try:
                    redis_client = redis_manager.get_client()
                    # 删除 Redis 中保存的 refresh_token 映射，防止被再次使用
                    await redis_client.delete(_refresh_jti_key(jti))
                except Exception:
                    # Redis 操作失败时静默处理，不影响登出主流程
                    pass
    # 清除浏览器中的 token 和 refresh_token Cookie
    response.delete_cookie(key="token")
    response.delete_cookie(key="refresh_token")
    return {"code": 200, "status": "success"}

@router.post("/register")
async def register(data: RegisterForm):
    """
    用户注册
    
    创建新用户，默认需要管理员审核。
    会赋予默认角色。
    """
    # 1. 检查注册权限
    
    username = (data.username or "").strip()
    password = str(data.password or "")
    if not username or not password:
        return JSONResponse(
            status_code=400,
            content={"code": 400, "status": "error", "message": "用户名与密码不能为空"},
        )

    # 2. 检查用户名是否已存在   
    exists = await db.fetch_val("SELECT id FROM users WHERE username = $1", username)
    if exists:
        return JSONResponse(
            status_code=400,
            content={"code": 400, "status": "error", "message": "用户名已存在"},
        )

    nickname = (data.nickname or "").strip() or username
    email = (data.email or "").strip() or None
    hashed_pw = get_password_hash(password)

    # 3. 创建用户记录
    # is_approved 默认值由系统配置决定 (auth_register_approval_enabled)
    # 默认为 true (不需要审核)
    try:
        require_approval_str = SystemConfig.get("auth_register_approval_enabled", "false")
        require_approval = str(require_approval_str).lower() in ("true", "1", "yes", "on")
    except Exception:
        require_approval = False

    is_approved = not require_approval

    user_id = await db.fetch_val(
        """
        INSERT INTO users (username, password, nickname, email, is_approved)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
        """,
        username,
        hashed_pw,
        nickname,
        email,
        is_approved
    )

    # 4. 赋予默认角色
    role_id: Optional[int] = None
    try:
        # 优先使用标记为 'is_default' 的角色
        role_id = await db.fetch_val("SELECT id FROM roles WHERE is_default = TRUE LIMIT 1")
    except Exception:
        role_id = None

    # 如果没有默认角色，尝试使用 'shisheng' (师生)
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

    # 5. 初始化权限版本
    try:
        await _get_or_init_perm_ver(int(user_id))
    except Exception:
        pass

    # 6. 记录审计日志
    try:
        await UserAdminAuditService.log(
            action="auth.register",
            actor=None, # Public registration, no actor
            target_user_id=int(user_id),
            request_ip=None, # Cannot get request object here
            detail={"username": username, "email": email, "nickname": nickname},
        )
    except Exception:
        logger.exception("audit log for auth.register failed")

    return {"code": 200, "status": "success", "message": "注册成功，请等待管理员审核" if not is_approved else "注册成功", "data": {"id": user_id}}

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

@router.get("/me")
async def get_my_session(token_payload: dict = Depends(verify_token)):
    """获取当前会话信息 (Token Payload)"""
    data = {
        "id": token_payload.get("id"),
        "username": token_payload.get("username"),
        "roles": token_payload.get("roles") or [],
        "is_super": bool(token_payload.get("is_super") or False),
        "perm_ver": token_payload.get("perm_ver"),
        "auth_ver": token_payload.get("auth_ver"),
    }
    return {"code": 200, "status": "success", "data": data}

@router.post("/users/me")
async def read_current_user(token_payload: dict = Depends(verify_token)):
    """获取当前用户详细信息 (同 /me)"""
    return {"code": 200, "status": "success", "data": token_payload}

@router.get("/users/me/security")
async def get_my_security_settings(token_payload: dict = Depends(verify_token)):
    """
    获取用户安全设置 (邮箱、密码存在状态、通知设置)
    """
    user_id = token_payload.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    row = await db.fetch_one(
        "SELECT email, password, is_email_notify, is_login_email_notify FROM users WHERE id = $1",
        int(user_id),
    )
    if not row:
         raise HTTPException(status_code=404, detail="用户不存在")

    email_notify_enabled = bool(row.get("is_email_notify") or False)
    login_email_notify_enabled = bool(row.get("is_login_email_notify") or False)
         
    return {
        "code": 200,
        "data": {
            "email": row.get("email"),
            "has_password": bool(row.get("password")),
            "is_email_notify": email_notify_enabled,
            "is_login_email_notify": login_email_notify_enabled,
        }
    }

@router.put("/users/me/security")
async def update_my_security_settings(form: UpdateSecurityForm, token_payload: dict = Depends(verify_token)):
    """
    更新用户安全设置
    """
    user_id = token_payload.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")

    if form.is_email_notify is None and form.is_login_email_notify is None:
        return JSONResponse(
            status_code=400,
            content={"code": 400, "message": "缺少安全设置参数", "status": "error"},
        )

    current = await db.fetch_one(
        "SELECT is_email_notify, is_login_email_notify FROM users WHERE id = $1",
        int(user_id),
    )
    if not current:
        raise HTTPException(status_code=404, detail="用户不存在")

    next_email_notify_enabled = bool(current.get("is_email_notify") or False)
    next_login_email_notify_enabled = bool(current.get("is_login_email_notify") or False)
    if form.is_email_notify is not None:
        next_email_notify_enabled = bool(form.is_email_notify)
    if form.is_login_email_notify is not None:
        next_login_email_notify_enabled = bool(form.is_login_email_notify)

    await db.execute(
        "UPDATE users SET is_email_notify = $1, is_login_email_notify = $2 WHERE id = $3",
        next_email_notify_enabled,
        next_login_email_notify_enabled,
        int(user_id),
    )
    return {
        "code": 200,
        "status": "success",
        "message": "设置已更新",
        "data": {
            "is_email_notify": next_email_notify_enabled,
            "is_login_email_notify": next_login_email_notify_enabled,
        },
    }


@router.get("/users/me/login-logs")
async def get_my_login_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    token_payload: dict = Depends(verify_token),
):
    user_id = token_payload.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")

    limit = int(page_size)
    offset = (int(page) - 1) * int(page_size)

    total = await db.fetch_val("SELECT COUNT(1) FROM login_logs WHERE user_id = $1", int(user_id))
    rows = await db.fetch_all(
        """
        SELECT id, ip, user_agent, device, created_at
        FROM login_logs
        WHERE user_id = $1
        ORDER BY created_at DESC, id DESC
        LIMIT $2 OFFSET $3
        """,
        int(user_id),
        limit,
        offset,
    )
    items = [dict(r) for r in (rows or [])]
    return {"code": 200, "data": items, "meta": {"total": int(total or 0), "page": int(page), "page_size": int(page_size)}}
