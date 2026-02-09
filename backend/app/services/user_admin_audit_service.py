import json
from typing import Optional, Any

from app.core.database import db


class UserAdminAuditService:
    _table_ready: bool = False
    ACTION_LABELS = {
        "user.create": "创建用户",
        "user.update": "更新用户",
        "user.update_status": "封禁/解封用户",
        "user.delete": "删除用户",
        "user.batch_delete": "批量删除用户",
        "user.reset_password": "重置用户密码",
        "user.update_permissions": "更新用户权限",
        "user.import": "批量导入用户",
        "role.assign": "分配角色",
        "role.unassign": "移除角色",
        "role.grant": "授权权限",
        "role.revoke": "回收权限",
    }

    @staticmethod
    def get_action_label(action: str) -> str:
        code = str(action or "").strip()
        return str(UserAdminAuditService.ACTION_LABELS.get(code) or code)

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
                request_ip TEXT NULL,
                detail JSONB NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_admin_audit_log_created_at ON user_admin_audit_log(created_at DESC)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_admin_audit_log_target_created ON user_admin_audit_log(target_user_id, created_at DESC)"
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
        request_ip: Optional[str] = None,
        detail: Optional[Any] = None,
    ) -> None:
        try:
            await UserAdminAuditService._ensure_table()
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
                    payload = json.dumps(detail, ensure_ascii=False)
                except Exception:
                    payload = None
            await db.execute(
                """
                INSERT INTO user_admin_audit_log (actor_user_id, actor_username, action, target_user_id, request_ip, detail)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                """,
                actor_user_id,
                actor_username,
                str(action or ""),
                int(target_user_id) if target_user_id is not None else None,
                str(request_ip or "").strip() or None,
                payload,
            )
        except Exception:
            return
