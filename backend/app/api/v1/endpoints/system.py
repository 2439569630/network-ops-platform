from fastapi import APIRouter, Depends
from app.core.database import db
from app.core.security import allow_admin
from app.core.system_config import SystemConfig
from pydantic import BaseModel
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class ConfigUpdate(BaseModel):
    key: str
    value: str

@router.get("/config/list", response_model=dict)
async def list_config(user: dict = Depends(allow_admin)):
    """获取所有系统配置 (仅管理员)"""
    try:
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
async def update_config(data: ConfigUpdate, user: dict = Depends(allow_admin)):
    """更新系统配置 (仅管理员)"""
    try:
        if data.key == "trap_autostart":
            return {"code": 400, "message": "trap_autostart 已废弃，无法更新"}
        sql = "UPDATE system_settings SET value = $1 WHERE key = $2"
        await db.execute(sql, data.value, data.key)
        
        # 刷新内存缓存
        await SystemConfig.refresh()
        
        return {"code": 200, "message": "配置更新成功"}
    except Exception as e:
        logger.error(f"更新配置失败: {e}")
        return {"code": 500, "message": f"更新失败: {str(e)}"}
