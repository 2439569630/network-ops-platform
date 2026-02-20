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
    """
    获取系统配置列表
    
    返回所有可配置的系统参数 (如邮件服务、图片服务配置等)。
    会自动初始化缺失的默认配置项。
    过滤掉废弃、隐藏或受保护的配置组。
    """
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
    except Exception:
        logger.exception("list_config failed")
        return {"code": 500, "message": "获取配置失败"}

@router.post("/config/update", response_model=dict)
async def update_config(data: ConfigUpdate, user: dict = Depends(PermissionChecker(["sys:config:edit"]))):
    """
    更新系统配置
    
    修改指定的配置项值。
    更新后会自动刷新系统内存中的配置缓存。
    
    Args:
        key: 配置键名
        value: 配置值
    """
    try:
        # 1. 检查是否为废弃或禁止修改的配置项
        if data.key == "trap_autostart":
            return {"code": 400, "message": "trap_autostart 已废弃，无法更新"}
        if str(data.key) in _REMOVED_CONFIG_KEYS:
            return {"code": 400, "message": "该配置项已移除"}
        if str(data.key) in _HIDDEN_CONFIG_KEYS:
            return {"code": 400, "message": "该配置项不在全局配置中维护，请使用 RBAC 管理接口"}

        # 2. 获取配置项元数据 (默认组名和描述)
        meta = _DEFAULT_CONFIG_META.get(str(data.key)) or {}
        next_group = str(meta.get("group_name") or "system")
        next_desc = meta.get("description")

        # 3. 检查数据库中是否存在该配置项
        existing = await db.fetch_one(
            "SELECT group_name, description FROM system_settings WHERE key = $1",
            str(data.key),
        )
        if existing:
            # 如果存在，保留原有的分组
            exist_group = str(existing.get("group_name") or "system")
            # 检查分组是否被锁定 (如 monitor 组配置禁止在此修改)
            if exist_group in _BLOCKED_GROUPS:
                return {"code": 400, "message": "该配置项属于设备/监控配置，禁止在全局配置中维护"}
            next_group = exist_group
            # 如果元数据没有描述，使用数据库中的描述
            if next_desc is None:
                next_desc = existing.get("description")
        else:
            # 如果是新配置，检查目标分组是否被锁定
            if next_group in _BLOCKED_GROUPS:
                return {"code": 400, "message": "该配置项属于设备/监控配置，禁止在全局配置中维护"}

        # 4. 执行更新或插入 (Upsert)
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

        # 5. 刷新系统配置缓存，使更改立即生效
        await SystemConfig.refresh()
        return {"code": 200, "message": "配置更新成功"}
    except Exception:
        logger.exception("update_config failed: key=%s", str(getattr(data, "key", "")))
        return {"code": 500, "message": "更新失败"}


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
    """
    获取用户管理审计日志
    
    查询管理员对用户的操作记录 (如修改密码、角色变更、封禁等)。
    支持按操作人、动作类型、目标用户、时间范围筛选。
    
    Args:
        page: 页码
        page_size: 每页数量
        actor_username: 操作人用户名 (模糊匹配)
        action: 动作类型 (如 user.set_roles)
        target_user_id: 目标用户 ID
        start_at: 开始时间
        end_at: 结束时间
    """
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
        limit_idx = idx
        offset_idx = idx + 1
        rows = await db.fetch_all(
            f"""
            SELECT id, actor_user_id, actor_username, action, target_user_id, request_ip, detail, created_at
            FROM user_admin_audit_log
            WHERE {where_sql}
            ORDER BY created_at DESC, id DESC
            LIMIT ${limit_idx} OFFSET ${offset_idx}
            """,
            *args,
            limit,
            offset,
        )
        items = [dict(r) for r in (rows or [])]
        for it in items:
            it["action_label"] = UserAdminAuditService.get_action_label(it.get("action"))
        return {
            "code": 200,
            "data": items,
            "meta": {"total": int(total or 0), "page": int(page), "page_size": int(page_size)},
        }
    except Exception:
        logger.exception(
            "list_user_admin_audit_logs failed: actor_username=%s action=%s target_user_id=%s start_at=%s end_at=%s",
            str(actor_username or ""),
            str(action or ""),
            str(target_user_id) if target_user_id is not None else "",
            str(start_at) if start_at is not None else "",
            str(end_at) if end_at is not None else "",
        )
        return {"code": 500, "message": "获取审计日志失败"}
