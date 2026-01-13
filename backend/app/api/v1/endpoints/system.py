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
        await _ensure_default_configs_exist(["email_nickname"])
        sql = """
            SELECT key, value, description, group_name
            FROM system_settings
            WHERE key <> 'trap_autostart'
            ORDER BY group_name, key
        """
        configs = await db.fetch_all(sql)
        return {"code": 200, "data": [dict(c) for c in configs]}
    except Exception as e:
        return {"code": 500, "message": f"获取配置失败: {str(e)}"}

@router.post("/config/update", response_model=dict)
async def update_config(data: ConfigUpdate, user: dict = Depends(PermissionChecker(["sys:config:edit"]))):
    """更新系统配置 (仅管理员)"""
    try:
        if data.key == "trap_autostart":
            return {"code": 400, "message": "trap_autostart 已废弃，无法更新"}
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
