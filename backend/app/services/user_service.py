import json
from typing import List, Optional
from datetime import datetime, timezone
import hashlib
import re
import secrets
from datetime import timedelta
from app.core.database import db
from app.core.security import get_password_hash
from app.schemas.user import UserCreate, UserUpdate, RoleUpdate, AdminUserUpdate
from app.core.redis import redis_manager
from app.core.system_config import SystemConfig
from app.utils.notification_sender import send_email
from app.core.security import bump_user_auth_version

# ORM Imports
from app.models.orm.user import User
from app.models.orm.device import NetworkDevice
from app.models.orm.repair import RepairOrder
from tortoise.functions import Count
from tortoise.expressions import Q

class UserService:
    """
    用户服务类
    处理用户账户管理、注册、认证、个人资料更新等业务逻辑。
    """
    _email_verify_table_ready: bool = False

    @staticmethod
    async def get_user_list() -> List[dict]:
        """
        获取用户列表
        """
        users = await User.all().order_by("id")
        result = []
        for u in users:
            u_dict = {
                "id": u.id,
                "username": u.username,
                "nickname": u.nickname,
                "email": u.email,
                "avatar_url": getattr(u, "avatar_url", None),
                "is_approved": u.is_approved,
                "permissions": u.permissions if isinstance(u.permissions, list) else [],
                "created_at": u.created_at
            }
            # Permissions is already JSONField, so it's a list or dict
            result.append(u_dict)
        return result

    @staticmethod
    async def admin_list_users(
        *,
        q: str = "",
        is_approved: Optional[bool] = None,
        include_deleted: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        query = User.all()
        if not bool(include_deleted):
            query = query.filter(is_deleted=False)
        if is_approved is not None:
            query = query.filter(is_approved=bool(is_approved))
        qn = str(q or "").strip()
        if qn:
            query = query.filter(
                Q(username__icontains=qn) | Q(nickname__icontains=qn) | Q(email__icontains=qn)
            )
        total = await query.count()
        rows = (
            await query.order_by("id")
            .offset((int(page) - 1) * int(page_size))
            .limit(int(page_size))
        )
        items: list[dict] = []
        for u in rows:
            items.append(
                {
                    "id": u.id,
                    "username": u.username,
                    "nickname": u.nickname,
                    "email": u.email,
                    "avatar_url": getattr(u, "avatar_url", None),
                    "is_email_notify": getattr(u, "is_email_notify", False),
                    "is_approved": u.is_approved,
                    "permissions": u.permissions if isinstance(u.permissions, list) else [],
                    "created_at": u.created_at,
                    "updated_at": u.updated_at,
                }
            )
        return {"items": items, "total": int(total or 0), "q": qn}

    @staticmethod
    async def _get_user_roles(user_id: int) -> list[dict]:
        rows = await db.fetch_all(
            """
            SELECT r.id, r.name, r.code
            FROM roles r
            INNER JOIN user_roles ur ON ur.role_id = r.id
            WHERE ur.user_id = $1
            ORDER BY r.id
            """,
            int(user_id),
        )
        roles: list[dict] = []
        for r in rows or []:
            if not r or r.get("id") is None:
                continue
            roles.append({"id": int(r["id"]), "name": r.get("name"), "code": r.get("code")})
        return roles

    @staticmethod
    async def admin_get_user_detail(user_id: int) -> Optional[dict]:
        user = await User.filter(id=int(user_id)).first()
        if not user:
            return None
        roles = await UserService._get_user_roles(int(user_id))
        return {
            "id": user.id,
            "username": user.username,
            "nickname": user.nickname,
            "email": user.email,
            "avatar_url": getattr(user, "avatar_url", None),
            "is_email_notify": getattr(user, "is_email_notify", False),
            "is_approved": user.is_approved,
            "is_deleted": getattr(user, "is_deleted", False),
            "deleted_at": getattr(user, "deleted_at", None),
            "deleted_by": getattr(user, "deleted_by", None),
            "permissions": user.permissions if isinstance(user.permissions, list) else [],
            "roles": roles,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }

    @staticmethod
    async def admin_update_user(user_id: int, data: AdminUserUpdate) -> dict:
        uid = int(user_id)
        updates: dict = {}
        if data.nickname is not None:
            updates["nickname"] = data.nickname
        if data.avatar_url is not None:
            updates["avatar_url"] = data.avatar_url
        if data.is_email_notify is not None:
            updates["is_email_notify"] = bool(data.is_email_notify)
        if data.is_approved is not None:
            updates["is_approved"] = bool(data.is_approved)
        if data.email is not None:
            email = str(data.email or "").strip()
            if email:
                exists_other = await User.filter(email__iexact=email).exclude(id=uid).exists()
                if exists_other:
                    raise ValueError("该邮箱已被其他账号绑定")
                updates["email"] = email
            else:
                updates["email"] = None
        if not updates:
            return {"updated": False, "reason": "empty"}
        updated = await User.filter(id=uid).update(**updates)
        if updated and updates.get("is_approved") is False:
            try:
                await bump_user_auth_version(int(uid))
            except Exception:
                pass
        return {"updated": bool(updated)}

    @staticmethod
    async def admin_delete_user(user_id: int, *, actor_id: Optional[int] = None) -> bool:
        uid = int(user_id)
        user = await User.filter(id=uid).first()
        if not user:
            return False
        if bool(getattr(user, "is_deleted", False)):
            try:
                await bump_user_auth_version(int(uid))
            except Exception:
                pass
            return True

        now = datetime.now(tz=timezone.utc)
        suffix = secrets.token_hex(4)
        new_username = f"deleted_{uid}_{suffix}"
        updates = {
            "username": new_username,
            "nickname": "已注销用户",
            "email": None,
            "avatar_url": None,
            "is_email_notify": False,
            "is_approved": False,
            "is_deleted": True,
            "deleted_at": now,
            "deleted_by": int(actor_id) if actor_id is not None else None,
            "permissions": [],
        }
        await User.filter(id=uid).update(**updates)
        try:
            await bump_user_auth_version(int(uid))
        except Exception:
            pass
        return True

    @staticmethod
    async def admin_delete_users(user_ids: List[int], *, actor_id: Optional[int] = None) -> int:
        ids = [int(uid) for uid in (user_ids or []) if uid is not None]
        ids = sorted(list(set(ids)))
        if not ids:
            return 0
        deleted = 0
        for uid in ids:
            ok = await UserService.admin_delete_user(int(uid), actor_id=actor_id)
            if ok:
                deleted += 1
        return int(deleted)

    @staticmethod
    async def get_user_by_id(user_id: int) -> Optional[dict]:
        user = await User.filter(id=user_id).first()
        if user:
            return {
                "id": user.id,
                "username": user.username,
                "nickname": user.nickname,
                "email": user.email,
                "avatar_url": getattr(user, "avatar_url", None),
                "is_approved": user.is_approved,
                "permissions": user.permissions if isinstance(user.permissions, list) else [],
                "created_at": user.created_at
            }
        return None

    @staticmethod
    async def get_user_by_username(username: str) -> Optional[dict]:
        user = await User.filter(username=username).first()
        if user:
             return {"id": user.id}
        return None

    @staticmethod
    async def create_user(data: UserCreate) -> int:
        """
        创建新用户 (注册)
        自动分配默认角色
        """
        # Check exists
        if await UserService.get_user_by_username(data.username):
            raise ValueError("用户名已存在")

        hashed_pw = get_password_hash(data.password)
        nickname = data.nickname or data.username
        
        perms = data.permissions
        if perms is None:
            perms = ["sys:monitor:view"]

        user = await User.create(
            username=data.username,
            password=hashed_pw,
            nickname=nickname,
            email=data.email,
            is_approved=True,
            permissions=perms
        )

        default_role_id = await db.fetch_val("SELECT id FROM roles WHERE is_default = TRUE LIMIT 1")
        if default_role_id:
            await db.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                int(user.id),
                int(default_role_id),
            )
        return user.id

    @staticmethod
    async def update_user_role(user_id: int, data: RoleUpdate):
        """
        更新用户角色/权限
        并触发权限版本更新
        """
        if data.permissions is not None:
            from app.services.rbac_service import RbacService
            from app.core.security import get_disabled_permission_codes_cached

            raw = [str(p).strip() for p in (data.permissions or []) if str(p).strip()]
            all_codes = await RbacService.get_all_permission_codes()
            existing = {str(c).strip() for c in (all_codes or []) if str(c).strip()}

            disabled_raw = await get_disabled_permission_codes_cached()
            disabled = {str(c).strip() for c in (disabled_raw or []) if str(c).strip()}

            selected = [p for p in raw if p in existing and p not in disabled]
            expanded = RbacService.expand_permission_codes(selected)
            expanded = [c for c in expanded if c in existing and c not in disabled]

            await User.filter(id=int(user_id)).update(permissions=expanded)
            try:
                await RbacService.bump_user_perm_version(int(user_id))
            except Exception:
                pass

    @staticmethod
    async def delete_user(user_id: int):
        await User.filter(id=user_id).delete()

    @staticmethod
    async def reset_password(user_id: int, new_password: str):
        """
        管理员重置用户密码
        """
        if not new_password:
            raise ValueError("新密码不能为空")
        
        new_hash = get_password_hash(new_password)
        await User.filter(id=user_id).update(password=new_hash)
        try:
            await bump_user_auth_version(int(user_id))
        except Exception:
            pass

    @staticmethod
    async def delete_users(user_ids: List[int]):
        """
        批量删除用户
        """
        if not user_ids:
            return
        await User.filter(id__in=user_ids).delete()

    @staticmethod
    async def update_status(user_id: int, is_approved: bool):
        await User.filter(id=int(user_id)).update(is_approved=bool(is_approved))
        if bool(is_approved) is False:
            try:
                await bump_user_auth_version(int(user_id))
            except Exception:
                pass

    @staticmethod
    async def update_profile(user_id: int, data: UserUpdate):
        """
        更新个人资料 (密码、昵称等)
        """
        # Password update handled separately usually, but here included
        if data.new_password:
             if not data.old_password:
                 raise ValueError("修改密码需要提供旧密码")
             
             # Verify old password
             user = await User.filter(id=user_id).first()
             stored_pw = user.password if user else None
             
             from app.core.security import verify_password
             if not stored_pw or not verify_password(data.old_password, stored_pw):
                 raise ValueError("旧密码错误")
             
             new_hash = get_password_hash(data.new_password)
             await User.filter(id=user_id).update(password=new_hash)
             try:
                 await bump_user_auth_version(int(user_id))
             except Exception:
                 pass

        updates = {}
        
        if data.nickname is not None:
            updates['nickname'] = data.nickname
            
        if data.email is not None:
            raise ValueError("邮箱需通过验证邮件绑定")

        if updates:
            await User.filter(id=user_id).update(**updates)

    @staticmethod
    async def get_profile_summary(user_id: int, username: str) -> dict:
        # 1. 计算注册天数
        user = await User.filter(id=user_id).first()
        created_at = user.created_at if user else None
        
        register_days = 1
        if created_at:
            # 使用 UTC 时间进行计算，避免时区带来的日期差异
            now = datetime.now(tz=timezone.utc) if created_at.tzinfo else datetime.now()
            delta = now.date() - created_at.date()
            register_days = max(delta.days + 1, 1)

        # 2. 统计设备 (匹配用户名或ID)
        device_count = await NetworkDevice.filter(
            Q(created_by=str(username)) | Q(created_by=str(user_id))
        ).count()

        # 3. 统计工单 (使用 ORM 替代原生 SQL，提高稳定性)
        order_total = await RepairOrder.filter(submitter_id=user_id).count()
        
        order_open = await RepairOrder.filter(
            submitter_id=user_id, 
            status__in=['pending', 'processing', 'need_info']
        ).count()
        
        order_done = await RepairOrder.filter(
            submitter_id=user_id, 
            status__in=['completed', 'closed']
        ).count()

        return {
            "register_days": int(register_days),
            "device_count": device_count,
            "order_total": order_total,
            "order_open": order_open,
            "order_done": order_done
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
        nickname = SystemConfig.get("email_nickname")

        if not all([host, port, username, password]):
            await SystemConfig.load()
            host = SystemConfig.get("email_host")
            port = SystemConfig.get("email_port")
            username = SystemConfig.get("email_username")
            password = SystemConfig.get("email_password")
            nickname = SystemConfig.get("email_nickname")

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

        ok, msg = await send_email(host, port, username, password, email, subject, content, nickname=nickname)
        if not ok:
            await db.execute("DELETE FROM user_email_verifications WHERE id = $1", int(verify_id))
            raise ValueError(f"验证邮件发送失败: {msg}")

        return {"cooldown_seconds": int(cooldown_seconds), "expires_in_minutes": int(token_ttl_minutes)}

    @staticmethod
    async def confirm_email_verification(token: str) -> dict:
        """
        确认邮箱验证
        """
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
