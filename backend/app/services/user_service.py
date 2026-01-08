import json
from typing import List, Optional
from datetime import datetime, timezone
import hashlib
import re
import secrets
from datetime import timedelta
from app.core.database import db
from app.core.security import get_password_hash
from app.schemas.user import UserCreate, UserUpdate, RoleUpdate
from app.core.redis import redis_manager
from app.core.system_config import SystemConfig
from app.utils.notification_sender import send_email

class UserService:
    _email_verify_table_ready: bool = False

    @staticmethod
    async def get_user_list() -> List[dict]:
        sql = "SELECT id, username, nickname, email, is_approved, permissions, created_at FROM users ORDER BY id"
        users = await db.fetch_all(sql)
        # Ensure permissions is a list (JSON deserialization might be automatic in asyncpg, but let's be safe)
        result = []
        for u in users:
            u_dict = dict(u)
            if isinstance(u_dict.get('permissions'), str):
                try:
                    u_dict['permissions'] = json.loads(u_dict['permissions'])
                except:
                    u_dict['permissions'] = []
            result.append(u_dict)
        return result

    @staticmethod
    async def get_user_by_id(user_id: int) -> Optional[dict]:
        sql = "SELECT id, username, nickname, email, is_approved, permissions, created_at FROM users WHERE id = $1"
        user = await db.fetch_one(sql, user_id)
        if user:
            u_dict = dict(user)
            if isinstance(u_dict.get('permissions'), str):
                try:
                    u_dict['permissions'] = json.loads(u_dict['permissions'])
                except:
                    u_dict['permissions'] = []
            return u_dict
        return None

    @staticmethod
    async def get_user_by_username(username: str) -> Optional[dict]:
        sql = "SELECT id FROM users WHERE username = $1"
        return await db.fetch_one(sql, username)

    @staticmethod
    async def create_user(data: UserCreate) -> int:
        # Check exists
        if await UserService.get_user_by_username(data.username):
            raise ValueError("用户名已存在")

        hashed_pw = get_password_hash(data.password)
        nickname = data.nickname or data.username
        
        perms = data.permissions
        if perms is None:
            perms = ["sys:monitor:view"]

        sql = """
            INSERT INTO users (username, password, nickname, email, is_approved, permissions)
            VALUES ($1, $2, $3, $4, true, $5::jsonb)
            RETURNING id
        """
        user_id = await db.fetch_val(sql, data.username, hashed_pw, nickname, data.email, perms)

        default_role_id = await db.fetch_val("SELECT id FROM roles WHERE is_default = TRUE LIMIT 1")
        if default_role_id:
            await db.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                int(user_id),
                int(default_role_id),
            )
        return user_id

    @staticmethod
    async def update_user_role(user_id: int, data: RoleUpdate):
        if data.permissions is not None:
             await db.execute("UPDATE users SET permissions = $1::jsonb WHERE id = $2", data.permissions, user_id)
             try:
                 from app.services.rbac_service import RbacService
                 await RbacService.bump_user_perm_version(int(user_id))
             except Exception:
                  pass

    @staticmethod
    async def delete_user(user_id: int):
        await db.execute("DELETE FROM users WHERE id = $1", user_id)

    @staticmethod
    async def update_status(user_id: int, is_approved: bool):
        await db.execute("UPDATE users SET is_approved = $1 WHERE id = $2", is_approved, user_id)

    @staticmethod
    async def update_profile(user_id: int, data: UserUpdate):
        # Password update handled separately usually, but here included
        if data.new_password:
             if not data.old_password:
                 raise ValueError("修改密码需要提供旧密码")
             
             # Verify old password
             # This requires fetching the current password hash, which isn't in get_user_by_id usually for security
             # But we need it here.
             sql = "SELECT password FROM users WHERE id = $1"
             stored_pw = await db.fetch_val(sql, user_id)
             from app.core.security import verify_password
             if not stored_pw or not verify_password(data.old_password, stored_pw):
                 raise ValueError("旧密码错误")
             
             new_hash = get_password_hash(data.new_password)
             await db.execute("UPDATE users SET password = $1 WHERE id = $2", new_hash, user_id)

        updates = []
        values = []
        idx = 1
        
        if data.nickname is not None:
            updates.append(f"nickname = ${idx}")
            values.append(data.nickname)
            idx += 1
            
        if data.email is not None:
            raise ValueError("邮箱需通过验证邮件绑定")
            
        if updates:
            values.append(user_id)
            sql = f"UPDATE users SET {', '.join(updates)} WHERE id = ${idx}"
            await db.execute(sql, *values)

    @staticmethod
    async def get_profile_summary(user_id: int, username: str) -> dict:
        created_at = await db.fetch_val("SELECT created_at FROM users WHERE id = $1", user_id)
        register_days = 1
        if created_at:
            if isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at)
                except Exception:
                    created_at = None
            if isinstance(created_at, datetime):
                now = datetime.now(tz=timezone.utc) if created_at.tzinfo else datetime.now()
                delta = now.date() - created_at.date()
                register_days = max(delta.days + 1, 1)

        device_count = await db.fetch_val(
            "SELECT COUNT(*) FROM network_devices WHERE created_by = $1 OR created_by = $2",
            username,
            str(user_id),
        )

        order_total = await db.fetch_val(
            "SELECT COUNT(*) FROM repair_orders WHERE submitter_id = $1",
            user_id,
        )
        order_open = await db.fetch_val(
            "SELECT COUNT(*) FROM repair_orders WHERE submitter_id = $1 AND status IN ('pending','processing','need_info')",
            user_id,
        )
        order_done = await db.fetch_val(
            "SELECT COUNT(*) FROM repair_orders WHERE submitter_id = $1 AND status IN ('completed','closed')",
            user_id,
        )

        return {
            "register_days": int(register_days),
            "device_count": int(device_count or 0),
            "order_total": int(order_total or 0),
            "order_open": int(order_open or 0),
            "order_done": int(order_done or 0),
        }

    @staticmethod
    async def _ensure_email_verify_table():
        if UserService._email_verify_table_ready:
            return

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_email_verifications (
                id BIGSERIAL PRIMARY KEY,
                user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                email TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                used_at TIMESTAMPTZ NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                request_ip TEXT NULL
            )
            """
        )
        await db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_email_verifications_token_hash ON user_email_verifications(token_hash)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_email_verifications_user_created ON user_email_verifications(user_id, created_at DESC)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_email_verifications_ip_created ON user_email_verifications(request_ip, created_at DESC)"
        )
        UserService._email_verify_table_ready = True

    @staticmethod
    def _is_valid_email(email: str) -> bool:
        return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", str(email or "")))

    @staticmethod
    async def request_email_verification(
        *,
        user_id: int,
        email: str,
        request_ip: Optional[str] = None,
        token_ttl_minutes: int = 15,
        cooldown_seconds: int = 60,
        max_per_hour_user: int = 5,
        max_per_hour_ip: int = 30,
        confirm_base_url: str,
    ) -> dict:
        await UserService._ensure_email_verify_table()

        email = str(email or "").strip()
        if not UserService._is_valid_email(email):
            raise ValueError("邮箱格式不正确")

        current_email = await db.fetch_val("SELECT email FROM users WHERE id = $1", user_id)
        if current_email and str(current_email).strip().lower() == email.lower():
            raise ValueError("该邮箱已绑定，无需重复验证")

        exists_other = await db.fetch_val("SELECT id FROM users WHERE lower(email) = lower($1) AND id <> $2", email, user_id)
        if exists_other:
            raise ValueError("该邮箱已被其他账号绑定")

        hour_count_user = await db.fetch_val(
            "SELECT COUNT(*) FROM user_email_verifications WHERE user_id = $1 AND created_at > NOW() - INTERVAL '1 hour'",
            user_id,
        )
        if int(hour_count_user or 0) >= max_per_hour_user:
            raise ValueError("发送过于频繁，请稍后再试")

        if request_ip:
            hour_count_ip = await db.fetch_val(
                "SELECT COUNT(*) FROM user_email_verifications WHERE request_ip = $1 AND created_at > NOW() - INTERVAL '1 hour'",
                request_ip,
            )
            if int(hour_count_ip or 0) >= max_per_hour_ip:
                raise ValueError("发送过于频繁，请稍后再试")

        redis_client = redis_manager.get_client()
        cooldown_key = f"email_verify:cooldown:user:{user_id}"
        if await redis_client.exists(cooldown_key):
            raise ValueError("操作过于频繁，请稍后再试")
        await redis_client.set(cooldown_key, "1", ex=int(cooldown_seconds))

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        expires_at = datetime.now(tz=timezone.utc) + timedelta(minutes=int(token_ttl_minutes))

        verify_id = await db.fetch_val(
            """
            INSERT INTO user_email_verifications (user_id, email, token_hash, expires_at, request_ip)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            user_id,
            email,
            token_hash,
            expires_at,
            request_ip,
        )

        host = SystemConfig.get("email_host")
        port = SystemConfig.get("email_port")
        username = SystemConfig.get("email_username")
        password = SystemConfig.get("email_password")

        if not all([host, port, username, password]):
            await SystemConfig.load()
            host = SystemConfig.get("email_host")
            port = SystemConfig.get("email_port")
            username = SystemConfig.get("email_username")
            password = SystemConfig.get("email_password")

        if not all([host, port, username, password]):
            await db.execute("DELETE FROM user_email_verifications WHERE id = $1", int(verify_id))
            raise ValueError("系统未配置邮箱服务，无法发送验证邮件")

        confirm_url = f"{confirm_base_url.rstrip('/')}/api/v1/users/profile/email/confirm?token={raw_token}"
        subject = "邮箱验证"
        content = (
            "你正在绑定/修改账号邮箱。\n\n"
            f"请点击以下链接完成验证（{token_ttl_minutes} 分钟内有效，仅可使用一次）：\n"
            f"{confirm_url}\n\n"
            "如非本人操作，请忽略本邮件。"
        )

        ok, msg = await send_email(host, port, username, password, email, subject, content)
        if not ok:
            await db.execute("DELETE FROM user_email_verifications WHERE id = $1", int(verify_id))
            raise ValueError(f"验证邮件发送失败: {msg}")

        return {"cooldown_seconds": int(cooldown_seconds), "expires_in_minutes": int(token_ttl_minutes)}

    @staticmethod
    async def confirm_email_verification(token: str) -> dict:
        await UserService._ensure_email_verify_table()

        token = str(token or "").strip()
        if not token:
            raise ValueError("缺少 token")

        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        row = await db.fetch_one(
            """
            SELECT id, user_id, email, expires_at, used_at
            FROM user_email_verifications
            WHERE token_hash = $1
            """,
            token_hash,
        )
        if not row:
            raise ValueError("链接无效或已失效")

        if row.get("used_at"):
            raise ValueError("链接已使用")

        expires_at = row.get("expires_at")
        if expires_at and isinstance(expires_at, datetime):
            now_utc = datetime.now(tz=timezone.utc)
            if expires_at < now_utc:
                raise ValueError("链接已过期")

        user_id = int(row["user_id"])
        email = str(row["email"] or "").strip()
        if not UserService._is_valid_email(email):
            raise ValueError("邮箱格式不正确")

        exists_other = await db.fetch_val("SELECT id FROM users WHERE lower(email) = lower($1) AND id <> $2", email, user_id)
        if exists_other:
            raise ValueError("该邮箱已被其他账号绑定")

        await db.execute("UPDATE users SET email = $1 WHERE id = $2", email, user_id)
        await db.execute("UPDATE user_email_verifications SET used_at = NOW() WHERE id = $1", int(row["id"]))

        return {"user_id": user_id, "email": email}

    @staticmethod
    async def get_pending_email_verification(user_id: int) -> Optional[dict]:
        await UserService._ensure_email_verify_table()

        row = await db.fetch_one(
            """
            SELECT email, expires_at, created_at
            FROM user_email_verifications
            WHERE user_id = $1
              AND used_at IS NULL
              AND expires_at > NOW()
            ORDER BY created_at DESC
            LIMIT 1
            """,
            user_id,
        )
        if not row:
            return None

        return {
            "email": str(row.get("email") or "").strip(),
            "expires_at": row.get("expires_at").isoformat() if row.get("expires_at") else None,
        }
