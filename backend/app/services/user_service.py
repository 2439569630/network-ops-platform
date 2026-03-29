import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Body, Request, UploadFile, File, Query
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
from app.services.notification_service import NotificationService

# ORM Imports
from app.models.orm.user import User
from app.models.orm.device import NetworkDevice
from app.models.orm.repair import RepairOrder
from app.models.orm.rbac import Role, UserRole
from tortoise.functions import Count
from tortoise.expressions import Q

logger = logging.getLogger(__name__)

class UserService:
    """
    用户服务类
    处理用户账户管理、注册、认证、个人资料更新等业务逻辑。
    """
    _email_verify_table_ready: bool = False

    @staticmethod
    def _mask_email(email: Optional[str]) -> str:
        raw = str(email or "").strip()
        if "@" not in raw:
            return raw
        local, domain = raw.split("@", 1)
        if len(local) <= 2:
            masked_local = local[:1] + "*"
        else:
            masked_local = local[:2] + "*" * max(1, len(local) - 2)
        return f"{masked_local}@{domain}"

    @staticmethod
    def _hash_verification_code(code: str) -> str:
        return hashlib.sha256(str(code or "").strip().encode("utf-8")).hexdigest()

    @staticmethod
    def _infer_device_label(user_agent: Optional[str]) -> str:
        ua = str(user_agent or "").strip().lower()
        if not ua:
            return "未知设备"

        os_name = "未知系统"
        if "windows" in ua:
            os_name = "Windows"
        elif "android" in ua:
            os_name = "Android"
        elif "iphone" in ua or "ipad" in ua or "ios" in ua:
            os_name = "iOS"
        elif "mac os x" in ua or "macintosh" in ua:
            os_name = "macOS"
        elif "linux" in ua:
            os_name = "Linux"

        browser = "未知浏览器"
        if "edg/" in ua:
            browser = "Edge"
        elif "chrome/" in ua and "chromium" not in ua and "edg/" not in ua:
            browser = "Chrome"
        elif "firefox/" in ua:
            browser = "Firefox"
        elif "safari/" in ua and "chrome/" not in ua:
            browser = "Safari"

        return f"{os_name} · {browser}"

    @staticmethod
    async def request_password_change_email_code(user_id: int, request_ip: Optional[str] = None) -> dict:
        user = await User.filter(id=int(user_id)).first()
        if not user:
            raise ValueError("用户不存在")

        email = str(getattr(user, "email", "") or "").strip()
        if not UserService._is_valid_email(email):
            raise ValueError("请先绑定邮箱后再修改密码")

        redis_client = redis_manager.get_client()
        cooldown_seconds = SystemConfig.get_int("auth:pwdchange:cooldown_seconds", 60)
        ttl_minutes = SystemConfig.get_int("auth:pwdchange:code_ttl_minutes", 10)
        user_hour_limit = SystemConfig.get_int("auth:pwdchange:user_hour_limit", 5)
        ip_hour_limit = SystemConfig.get_int("auth:pwdchange:ip_hour_limit", 20)

        cooldown_key = f"pwdchange:code:cooldown:user:{int(user_id)}"
        verify_key = f"pwdchange:code:user:{int(user_id)}"
        user_hour_key = f"pwdchange:code:user:{int(user_id)}:h"

        if await redis_client.exists(cooldown_key):
            raise ValueError("发送过于频繁，请稍后再试")

        raw_user_hour = await redis_client.get(user_hour_key)
        try:
            user_hour_count = int(raw_user_hour or 0)
        except Exception:
            user_hour_count = 0
        if user_hour_count >= int(user_hour_limit):
            raise ValueError("发送过于频繁，请稍后再试")

        if request_ip:
            ip_hour_key = f"pwdchange:code:ip:{request_ip}:h"
            raw_ip_hour = await redis_client.get(ip_hour_key)
            try:
                ip_hour_count = int(raw_ip_hour or 0)
            except Exception:
                ip_hour_count = 0
            if ip_hour_count >= int(ip_hour_limit):
                raise ValueError("发送过于频繁，请稍后再试")
            next_ip_hour = await redis_client.incr(ip_hour_key)
            if int(next_ip_hour) == 1:
                await redis_client.expire(ip_hour_key, 3600)

        next_user_hour = await redis_client.incr(user_hour_key)
        if int(next_user_hour) == 1:
            await redis_client.expire(user_hour_key, 3600)

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
            raise ValueError("系统未配置邮箱服务，无法发送验证码")

        code = f"{secrets.randbelow(1000000):06d}"
        payload = {
            "code_hash": UserService._hash_verification_code(code),
            "email": email,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        await redis_client.set(verify_key, json.dumps(payload, ensure_ascii=False), ex=int(ttl_minutes) * 60)
        await redis_client.set(cooldown_key, "1", ex=int(cooldown_seconds))

        subject = "修改密码验证码"
        content = (
            f"{getattr(user, 'nickname', None) or getattr(user, 'username', None) or '用户'}，你好：\n\n"
            "你正在进行账号密码修改操作。\n"
            f"本次验证码为：{code}\n"
            f"验证码 {int(ttl_minutes)} 分钟内有效，仅可使用一次。\n\n"
            "如非本人操作，请尽快检查账号安全。"
        )

        ok, msg = await send_email(host, port, username, password, email, subject, content, nickname=nickname)
        if not ok:
            await redis_client.delete(verify_key)
            await redis_client.delete(cooldown_key)
            raise ValueError(f"验证码发送失败: {msg}")

        return {
            "cooldown_seconds": int(cooldown_seconds),
            "expires_in_minutes": int(ttl_minutes),
            "masked_email": UserService._mask_email(email),
        }

    @staticmethod
    async def consume_password_change_email_code(user_id: int, email_code: str) -> None:
        code = str(email_code or "").strip()
        if not code:
            raise ValueError("请输入邮箱验证码")

        redis_client = redis_manager.get_client()
        verify_key = f"pwdchange:code:user:{int(user_id)}"
        raw = await redis_client.get(verify_key)
        if not raw:
            raise ValueError("邮箱验证码错误或已失效")

        try:
            payload = json.loads(raw)
        except Exception:
            await redis_client.delete(verify_key)
            raise ValueError("邮箱验证码错误或已失效")

        expected_hash = str(payload.get("code_hash") or "").strip()
        if not expected_hash or expected_hash != UserService._hash_verification_code(code):
            raise ValueError("邮箱验证码错误或已失效")

        await redis_client.delete(verify_key)

    @staticmethod
    async def send_password_changed_notification(
        user_id: int,
        *,
        request_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        user = await User.filter(id=int(user_id)).first()
        if not user:
            return

        username = str(getattr(user, "username", "") or "").strip() or "账号"
        display_name = str(getattr(user, "nickname", "") or "").strip() or username
        email = str(getattr(user, "email", "") or "").strip()
        device = UserService._infer_device_label(user_agent)
        changed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ip_text = str(request_ip or "").strip() or "未知"

        await NotificationService.create_site_message(
            sender_id=None,
            sender_name=None,
            source="系统安全通知",
            title="密码修改提醒",
            content=(
                f"你的账号密码已于 {changed_at} 完成修改。\n"
                f"操作 IP：{ip_text}\n"
                f"操作设备：{device}\n"
                "如为本人操作，可忽略；如非本人操作，请立即重置密码并联系管理员。"
            ),
            target_user_id=int(user_id),
            is_global=False,
        )

        if not UserService._is_valid_email(email):
            return

        host = SystemConfig.get("email_host")
        port = SystemConfig.get("email_port")
        username_smtp = SystemConfig.get("email_username")
        password = SystemConfig.get("email_password")
        nickname = SystemConfig.get("email_nickname")

        if not all([host, port, username_smtp, password]):
            await SystemConfig.load()
            host = SystemConfig.get("email_host")
            port = SystemConfig.get("email_port")
            username_smtp = SystemConfig.get("email_username")
            password = SystemConfig.get("email_password")
            nickname = SystemConfig.get("email_nickname")

        if not all([host, port, username_smtp, password]):
            logger.warning("skip password changed email: email config missing")
            return

        ok, msg = await send_email(
            host,
            port,
            username_smtp,
            password,
            email,
            "账号密码修改提醒",
            (
                f"{display_name}，你好：\n\n"
                "检测到你的账号密码已完成修改，操作信息如下：\n"
                f"操作时间：{changed_at}\n"
                f"操作 IP：{ip_text}\n"
                f"操作设备：{device}\n\n"
                "如果这是你本人操作，无需处理。\n"
                "如果不是你本人操作，请立即使用找回密码功能重置密码，并尽快联系管理员。"
            ),
            nickname=nickname,
        )
        if not ok:
            logger.error("send password changed email failed: user_id=%s; msg=%s", int(user_id), msg)

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

                "created_at": u.created_at
            }
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
        user_ids = [user.id for user in rows]
        user_roles = await db.fetch_all("SELECT ur.user_id, r.id, r.name, r.code FROM user_roles ur JOIN roles r ON ur.role_id = r.id WHERE ur.user_id = ANY($1::int[])", user_ids)
        roles_by_user = {}
        for r in user_roles:
            if r['user_id'] not in roles_by_user:
                roles_by_user[r['user_id']] = []
            roles_by_user[r['user_id']].append({"id": r['id'], "name": r['name'], "code": r['code']})

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
                    "roles": roles_by_user.get(u.id, []),
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
            "deleted_by_id": getattr(user, "deleted_by_id", None),
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
        try:
            await bump_user_auth_version(int(uid))
        except Exception:
            pass
        try:
            from app.services.rbac_service import RbacService

            await RbacService.bump_user_perm_version(int(uid))
        except Exception:
            pass
        try:
            from app.models.orm.rbac import UserRole

            await UserRole.filter(user_id=int(uid)).delete()
        except Exception:
            pass
        try:
            from app.models.orm.location import LocationNodeUser

            await LocationNodeUser.filter(user_id=int(uid)).delete()
        except Exception:
            pass
        try:
            from app.models.orm.alert import AlertSubscription

            await AlertSubscription.filter(subscriber_user_id=int(uid)).delete()
        except Exception:
            pass
        try:
            from app.models.orm.notification import SiteMessageRead, UserEmailVerification

            await SiteMessageRead.filter(user_id=int(uid)).delete()
            await UserEmailVerification.filter(user_id=int(uid)).delete()
        except Exception:
            pass
        await User.filter(id=uid).delete()
        return True

    @staticmethod
    async def admin_delete_users(user_ids: List[int], *, actor_id: Optional[int] = None) -> int:
        ids = [int(uid) for uid in (user_ids or []) if uid is not None]
        ids = sorted(list(set(ids)))
        if not ids:
            return 0

        for uid in ids:
            try:
                await bump_user_auth_version(int(uid))
            except Exception:
                pass
            try:
                from app.services.rbac_service import RbacService
                await RbacService.bump_user_perm_version(int(uid))
            except Exception:
                pass

        from app.models.orm.rbac import UserRole
        from app.models.orm.location import LocationNodeUser
        from app.models.orm.alert import AlertSubscription
        from app.models.orm.notification import SiteMessageRead, UserEmailVerification

        await UserRole.filter(user_id__in=ids).delete()
        await LocationNodeUser.filter(user_id__in=ids).delete()
        await AlertSubscription.filter(subscriber_user_id__in=ids).delete()
        await SiteMessageRead.filter(user_id__in=ids).delete()
        await UserEmailVerification.filter(user_id__in=ids).delete()
        
        deleted_count = await User.filter(id__in=ids).delete()
        return deleted_count

    @staticmethod
    async def get_user_by_id(user_id: int) -> Optional[dict]:
        user = await User.filter(id=user_id).first()
        if user:
            roles = await UserService._get_user_roles(int(user_id))
            return {
                "id": user.id,
                "username": user.username,
                "nickname": user.nickname,
                "email": user.email,
                "avatar_url": getattr(user, "avatar_url", None),
                "is_approved": user.is_approved,
                "roles": roles,
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
        

        user = await User.create(
            username=data.username,
            password=hashed_pw,
            nickname=nickname,
            email=data.email,
            is_approved=True
        )

        protected = {"superadmin", "super_admin", "super-admin"}
        default_role = await db.fetch_one("SELECT id, code FROM roles WHERE is_default = TRUE LIMIT 1")
        if default_role and str((default_role or {}).get("code") or "").strip().lower() not in protected:
            await db.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                int(user.id),
                int(default_role["id"]),
            )
        return user.id

    @staticmethod
    async def update_user_role(user_id: int, data: RoleUpdate):
        """
        更新用户角色/权限
        并触发权限版本更新
        """
        pass

    @staticmethod
    async def user_is_superadmin(user_id: int) -> bool:
        """
        判断用户是否是超级管理员
        通过 UserRole -> Role.code="superadmin" 判断
        """
        from app.models.orm.rbac import UserRole
        return await UserRole.filter(
            user_id=user_id,
            role__code="superadmin"
        ).exists()

    @staticmethod
    async def _require_actor_superadmin_when_assigning_protected_roles(role_ids: List[int], current_user: dict):
        """
        分配受保护角色时的安全检查
        如果 role_ids 包含 superadmin 角色，且 current_user 不是 superadmin，则抛出 403
        """
        if not role_ids:
            return

        from app.models.orm.rbac import Role

        # 查询 Role.code="superadmin"
        super_role = await Role.filter(code="superadmin").first()
        if not super_role:
            return

        # 如果 role_ids 包含该角色
        if super_role.id in role_ids:
            # 且 current_user 不是 superadmin
            user_id = int(current_user.get("id"))
            is_super = await UserService.user_is_superadmin(user_id)
            if not is_super:
                raise HTTPException(status_code=403, detail="Privilege Escalation: Only superadmin can assign superadmin role")

    @staticmethod
    async def update_user_roles(user_id: int, role_ids: List[int]):
        """
        更新用户的角色
        """
        from app.models.orm.rbac import UserRole
        from app.services.rbac_service import RbacService

        await UserRole.filter(user_id=user_id).delete()
        if role_ids:
            await UserRole.bulk_create([UserRole(user_id=user_id, role_id=role_id) for role_id in role_ids])
        await RbacService.bump_user_perm_version(int(user_id))


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
             if not data.email_code:
                 raise ValueError("修改密码需要邮箱验证码")
             if len(str(data.new_password or "")) < 6:
                 raise ValueError("密码长度至少 6 位")

             user = await User.filter(id=user_id).first()
             if not user:
                 raise ValueError("用户不存在")
             if not UserService._is_valid_email(getattr(user, "email", None)):
                 raise ValueError("请先绑定邮箱后再修改密码")

             stored_pw = user.password if user else None

             from app.core.security import verify_password
             if not stored_pw or not verify_password(data.old_password, stored_pw):
                 raise ValueError("旧密码错误")

             await UserService.consume_password_change_email_code(user_id, data.email_code)

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

        return {"password_changed": bool(data.new_password)}

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
