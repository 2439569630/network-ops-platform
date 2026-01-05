import logging
from fastapi import APIRouter, Depends
from DataBase import PostgreSQL
from auth.security import allow_admin
from pydantic import BaseModel
from typing import List, Optional
from Config.sys_config import SystemConfig

router = APIRouter(prefix="/system/config", tags=["System Configuration"])
logger = logging.getLogger(__name__)

class ConfigItem(BaseModel):
    key: str
    value: str
    description: Optional[str] = None
    group_name: str

class ConfigUpdate(BaseModel):
    key: str
    value: str

@router.get("/list")
async def list_config(user = Depends(allow_admin)):
    """获取所有系统配置 (仅管理员)"""
    sql = "SELECT key, value, description, group_name FROM system_settings ORDER BY group_name, key"
    configs = await PostgreSQL.execute(sql, fetch=True)
    return {"code": 200, "data": configs}

@router.post("/update")
async def update_config(data: ConfigUpdate, user = Depends(allow_admin)):
    """更新系统配置 (仅管理员)"""
    try:
        sql = "UPDATE system_settings SET value = $1 WHERE key = $2"
        await PostgreSQL.execute(sql, data.value, data.key)
        
        # 刷新内存缓存
        await SystemConfig.refresh()
        
        return {"code": 200, "message": "配置更新成功"}
    except Exception as e:
        logger.error(f"更新配置失败: {e}")
        return {"code": 500, "message": str(e)}
