from fastapi import APIRouter, Depends, Query
from app.core.database import db
from app.core.security import PermissionChecker
from app.core.system_config import SystemConfig
from app.services.user_admin_audit_service import UserAdminAuditService
from pydantic import BaseModel
from typing import Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()

class ConfigUpdate(BaseModel):
    key: str
    value: str

_DEFAULT_CONFIG_META = {
    "email_enabled": {"group_name": "notification", "description": "是否启用邮件通知"},
    "email_host": {"group_name": "notification", "description": "邮箱 SMTP 地址"},
    "email_port": {"group_name": "notification", "description": "邮箱 SMTP 端口"},
    "email_username": {"group_name": "notification", "description": "邮箱账号"},
    "email_password": {"group_name": "notification", "description": "邮箱密码"},
    "email_nickname": {"group_name": "notification", "description": "邮件发件人昵称"},
    "repair_image_api_base_url": {"group_name": "repair", "description": "外部图片服务 base_url，例如 http://host/api/v1"},
    "repair_image_api_email": {"group_name": "repair", "description": "外部图片服务账号邮箱(/tokens)"},
    "repair_image_api_password": {"group_name": "repair", "description": "外部图片服务账号密码(/tokens)"},
}

_REMOVED_CONFIG_KEYS = {
    "pushplus_token",
    "repair_image_upload_base_url",
    "repair_image_storage_provider",
    "repair_image_api_token",
    "repair_image_api_strategy_id",
}

_HIDDEN_CONFIG_KEYS = {
    "rbac:disabled_permissions",
}

_BLOCKED_GROUPS = {
    "monitor",
}

async def _ensure_default_configs_exist(keys: list[str]) -> None:
    if not keys:
        return
    rows = await db.fetch_all(
        "SELECT key FROM system_settings WHERE key = ANY($1::text[])",
        [str(k) for k in keys],
    )
    existing = {str(r.get("key")) for r in (rows or [])}
    missing = [k for k in keys if k not in existing]
    for key in missing:
        meta = _DEFAULT_CONFIG_META.get(key) or {}
        group_name = str(meta.get("group_name") or "system")
        description = meta.get("description")
        await db.execute(
            """
            INSERT INTO system_settings (key, value, description, group_name)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (key) DO NOTHING
            """,
            str(key),
            "",
            description,
            group_name,
        )

@router.get("/config/list", response_model=dict)
async def list_config(user: dict = Depends(PermissionChecker(["sys:config:view"]))):
    try:
        await _ensure_default_configs_exist([
            "email_enabled",
            "email_host",
            "email_port",
            "email_username",
            "email_password",
            "email_nickname",
            "repair_image_api_base_url",
            "repair_image_api_email",
            "repair_image_api_password",
        ])
        sql = """
            SELECT key, value, description, group_name
            FROM system_settings
            WHERE key <> 'trap_autostart'
            AND COALESCE(group_name, 'system') <> ALL($1::text[])
            AND NOT (key = ANY($2::text[]))
            ORDER BY group_name, key
        """
        ignored = list(_REMOVED_CONFIG_KEYS | _HIDDEN_CONFIG_KEYS)
        blocked_groups = list(_BLOCKED_GROUPS)
        configs = await db.fetch_all(sql, blocked_groups, ignored)
        return {"code": 200, "data": [dict(c) for c in configs]}
    except Exception as e:
        return {"code": 500, "message": f"获取配置失败: {str(e)}"}

@router.post("/config/update", response_model=dict)
async def update_config(data: ConfigUpdate, user: dict = Depends(PermissionChecker(["sys:config:edit"]))):
    try:
        if data.key == "trap_autostart":
            return {"code": 400, "message": "trap_autostart 已废弃，无法更新"}
        if str(data.key) in _REMOVED_CONFIG_KEYS:
            return {"code": 400, "message": "该配置项已移除"}
        if str(data.key) in _HIDDEN_CONFIG_KEYS:
            return {"code": 400, "message": "该配置项不在全局配置中维护，请使用 RBAC 管理接口"}

        meta = _DEFAULT_CONFIG_META.get(str(data.key)) or {}
        next_group = str(meta.get("group_name") or "system")
        next_desc = meta.get("description")

        existing = await db.fetch_one(
            "SELECT group_name, description FROM system_settings WHERE key = $1",
            str(data.key),
        )
        if existing:
            exist_group = str(existing.get("group_name") or "system")
            if exist_group in _BLOCKED_GROUPS:
                return {"code": 400, "message": "该配置项属于设备/监控配置，禁止在全局配置中维护"}
            next_group = exist_group
            if next_desc is None:
                next_desc = existing.get("description")
        else:
            if next_group in _BLOCKED_GROUPS:
                return {"code": 400, "message": "该配置项属于设备/监控配置，禁止在全局配置中维护"}

        await db.execute(
            """
            INSERT INTO system_settings (key, value, description, group_name)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            str(data.key),
            str(data.value),
            next_desc,
            next_group,
        )

        await SystemConfig.refresh()
        return {"code": 200, "message": "配置更新成功"}
    except Exception as e:
        logger.error(f"更新配置失败: {e}")
        return {"code": 500, "message": f"更新失败: {str(e)}"}


@router.get("/audit/user-admin", response_model=dict)
async def list_user_admin_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    actor_username: Optional[str] = Query(None, max_length=100),
    action: Optional[str] = Query(None, max_length=100),
    target_user_id: Optional[int] = Query(None),
    start_at: Optional[datetime] = Query(None),
    end_at: Optional[datetime] = Query(None),
    user: dict = Depends(PermissionChecker(["sys:audit:view"])),
):
    try:
        where = ["1=1"]
        args: list = []
        idx = 1
        if actor_username:
            where.append(f"actor_username ILIKE ${idx}")
            args.append(f"%{str(actor_username).strip()}%")
            idx += 1
        if action:
            where.append(f"action ILIKE ${idx}")
            args.append(f"%{str(action).strip()}%")
            idx += 1
        if target_user_id is not None:
            where.append(f"target_user_id = ${idx}")
            args.append(int(target_user_id))
            idx += 1
        if start_at is not None:
            where.append(f"created_at >= ${idx}")
            args.append(start_at)
            idx += 1
        if end_at is not None:
            where.append(f"created_at <= ${idx}")
            args.append(end_at)
            idx += 1

        where_sql = " AND ".join(where)
        total = await db.fetch_val(f"SELECT COUNT(1) FROM user_admin_audit_log WHERE {where_sql}", *args)
        limit = int(page_size)
        offset = (int(page) - 1) * int(page_size)
        rows = await db.fetch_all(
            f"""
            SELECT id, actor_user_id, actor_username, action, target_user_id, request_ip, detail, created_at
            FROM user_admin_audit_log
            WHERE {where_sql}
            ORDER BY created_at DESC, id DESC
            LIMIT {limit} OFFSET {offset}
            """,
            *args,
        )
        items = [dict(r) for r in (rows or [])]
        for it in items:
            it["action_label"] = UserAdminAuditService.get_action_label(it.get("action"))
        return {
            "code": 200,
            "data": items,
            "meta": {"total": int(total or 0), "page": int(page), "page_size": int(page_size)},
        }
    except Exception as e:
        return {"code": 500, "message": f"获取审计日志失败: {str(e)}"}
