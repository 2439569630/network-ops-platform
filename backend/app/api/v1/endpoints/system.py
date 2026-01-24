from fastapi import APIRouter, Depends
from app.core.database import db
from app.core.security import PermissionChecker
from app.core.system_config import SystemConfig
from pydantic import BaseModel
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class ConfigUpdate(BaseModel):
    key: str
    value: str

_DEFAULT_CONFIG_META = {
    "email_host": {"group_name": "notification", "description": "邮箱 SMTP 地址"},
    "email_port": {"group_name": "notification", "description": "邮箱 SMTP 端口"},
    "email_username": {"group_name": "notification", "description": "邮箱账号"},
    "email_password": {"group_name": "notification", "description": "邮箱密码"},
    "email_nickname": {"group_name": "notification", "description": "邮件发件人昵称"},
    "pushplus_token": {"group_name": "notification", "description": "PushPlus Token"},
    "repair_image_api_base_url": {"group_name": "repair", "description": "外部图片服务 base_url，例如 http://host/api/v1"},
    "repair_image_api_email": {"group_name": "repair", "description": "外部图片服务账号邮箱(/tokens)"},
    "repair_image_api_password": {"group_name": "repair", "description": "外部图片服务账号密码(/tokens)"},
}

_REMOVED_CONFIG_KEYS = {
    "repair_image_upload_base_url",
    "repair_image_storage_provider",
    "repair_image_api_token",
    "repair_image_api_strategy_id",
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
    """获取所有系统配置 (仅管理员)"""
    try:
        await _ensure_default_configs_exist([
            "email_nickname",
            "repair_image_api_base_url",
            "repair_image_api_email",
            "repair_image_api_password",
        ])
        sql = """
            SELECT key, value, description, group_name
            FROM system_settings
            WHERE key <> 'trap_autostart'
            AND NOT (key = ANY($1::text[]))
            ORDER BY group_name, key
        """
        configs = await db.fetch_all(sql, list(_REMOVED_CONFIG_KEYS))
        return {"code": 200, "data": [dict(c) for c in configs]}
    except Exception as e:
        return {"code": 500, "message": f"获取配置失败: {str(e)}"}

@router.post("/config/update", response_model=dict)
async def update_config(data: ConfigUpdate, user: dict = Depends(PermissionChecker(["sys:config:edit"]))):
    """更新系统配置 (仅管理员)"""
    try:
        if data.key == "trap_autostart":
            return {"code": 400, "message": "trap_autostart 已废弃，无法更新"}
        if str(data.key) in _REMOVED_CONFIG_KEYS:
            return {"code": 400, "message": "该配置项已移除"}
        meta = _DEFAULT_CONFIG_META.get(str(data.key)) or {}
        group_name = str(meta.get("group_name") or "system")
        description = meta.get("description")
        await db.execute(
            """
            INSERT INTO system_settings (key, value, description, group_name)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            str(data.key),
            str(data.value),
            description,
            group_name,
        )
        
        # 刷新内存缓存
        await SystemConfig.refresh()
        
        return {"code": 200, "message": "配置更新成功"}
    except Exception as e:
        logger.error(f"更新配置失败: {e}")
        return {"code": 500, "message": f"更新失败: {str(e)}"}
