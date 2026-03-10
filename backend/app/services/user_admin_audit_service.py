import json
from typing import Optional, Any

from app.core.database import db
from app.models.orm.audit import UserAdminAuditLog



class UserAdminAuditService:
    _table_ready: bool = False
    ACTION_LABELS = {
        # User management
        "user.create": "创建用户",
        "user.update": "更新用户",
        "user.profile_update": "更新个人资料",
        "user.update_status": "封禁/解封用户",
        "user.delete": "删除用户",
        "user.batch_delete": "批量删除用户",
        "user.reset_password": "重置用户密码",
        "user.set_roles": "设置用户角色",
        "user.import_commit": "批量导入用户",
        "user.import_cancel": "取消用户导入",

        # Authentication
        "auth.register": "用户注册",
        "auth.password_reset": "重置密码 (忘记密码)",

        # RBAC
        "rbac.role.create": "创建角色",
        "rbac.role.update": "更新角色",
        "rbac.role.delete": "删除角色",
        "rbac.role.set_permissions": "设置角色权限",
        "rbac.role.set_default": "设置默认角色",
        "rbac.role.add_users": "为角色添加成员",
        "rbac.role.remove_user": "从角色移除成员",
        "rbac.permission.create": "创建权限",
        "rbac.permission.update": "更新权限",
        "rbac.permission.delete": "删除权限",
        "rbac.permission.restore_system": "恢复系统权限",
        "rbac.permission.set_disabled": "设置禁用权限",

        # System Config
        "system.config.update": "更新系统配置",
    }

    TARGET_LABELS = {
        "email_enabled": "邮件通知总开关",
        "email_host": "邮箱SMTP地址",
        "email_port": "邮箱SMTP端口",
        "email_username": "邮箱账号",
        "email_password": "邮箱密码",
        "email_nickname": "邮件发件人昵称",
        "repair_image_api_base_url": "图片服务URL",
        "repair_image_api_email": "图片服务邮箱",
        "repair_image_api_password": "图片服务密码",
    }

    @staticmethod
    def get_action_label(action: str) -> str:
        code = str(action or "").strip()
        return str(UserAdminAuditService.ACTION_LABELS.get(code) or code)

    @staticmethod
    def get_target_label(target_label: str) -> str:
        label = str(target_label or "").strip()
        return str(UserAdminAuditService.TARGET_LABELS.get(label) or label)

    @staticmethod
    async def _ensure_table() -> None:
        if UserAdminAuditService._table_ready:
            return
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_admin_audit_log (
                id BIGSERIAL PRIMARY KEY,
                actor_user_id INT NULL,
                actor_username TEXT NULL,
                action TEXT NOT NULL,
                target_user_id INT NULL,
                target_type TEXT NULL,
                target_id BIGINT NULL,
                target_label TEXT NULL,
                request_ip TEXT NULL,
                detail JSONB NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await db.execute("ALTER TABLE user_admin_audit_log ADD COLUMN IF NOT EXISTS target_type TEXT NULL")
        await db.execute("ALTER TABLE user_admin_audit_log ADD COLUMN IF NOT EXISTS target_id BIGINT NULL")
        await db.execute("ALTER TABLE user_admin_audit_log ADD COLUMN IF NOT EXISTS target_label TEXT NULL")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_admin_audit_log_created_at ON user_admin_audit_log(created_at DESC)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_admin_audit_log_target_created ON user_admin_audit_log(target_user_id, created_at DESC)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_admin_audit_log_target_obj_created ON user_admin_audit_log(target_type, target_id, created_at DESC)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_admin_audit_log_actor_created ON user_admin_audit_log(actor_user_id, created_at DESC)"
        )
        UserAdminAuditService._table_ready = True

    @staticmethod
    async def log(
        *,
        action: str,
        actor: Optional[dict] = None,
        target_user_id: Optional[int] = None,
        target_type: Optional[str] = None,
        target_id: Optional[int] = None,
        target_label: Optional[str] = None,
        request_ip: Optional[str] = None,
        detail: Optional[Any] = None,
    ) -> None:
        try:
            actor_user_id = None
            actor_username = None
            if actor:
                try:
                    actor_user_id = int(actor.get("id")) if actor.get("id") is not None else None
                except Exception:
                    actor_user_id = None
                actor_username = str(actor.get("username") or "").strip() or None

            payload = None
            if detail is not None:
                try:
                    # 确保 detail 是可序列化为 JSON 的
                    json.dumps(detail)
                    payload = detail
                except Exception:
                    payload = {"raw": str(detail)}

            await UserAdminAuditLog.create(
                actor_user_id=actor_user_id,
                actor_username=actor_username,
                action=str(action or ""),
                target_user_id=int(target_user_id) if target_user_id is not None else None,
                target_type=str(target_type or "").strip() or None,
                target_id=int(target_id) if target_id is not None else None,
                target_label=str(target_label or "").strip() or None,
                request_ip=str(request_ip or "").strip() or None,
                detail=payload,
            )
        except Exception:
            return
