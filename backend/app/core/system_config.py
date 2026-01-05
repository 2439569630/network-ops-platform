import logging
from typing import Dict, Any
from app.core.database import db

logger = logging.getLogger(__name__)

class SystemConfig:
    _instance = None
    _config: Dict[str, str] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SystemConfig, cls).__new__(cls)
        return cls._instance

    @classmethod
    async def load(cls):
        """从数据库加载所有配置到内存"""
        try:
            logger.info("正在加载系统配置...")
            sql = "SELECT key, value FROM system_settings WHERE key <> 'trap_autostart'"
            rows = await db.fetch_all(sql)
            if rows:
                for row in rows:
                    cls._config[row['key']] = row['value']
            logger.info(f"系统配置加载完成: {cls._config}")
        except Exception as e:
            logger.error(f"加载系统配置失败: {e}")

    @classmethod
    def get(cls, key: str, default: Any = None) -> str:
        """获取配置值 (同步方法)"""
        return cls._config.get(key, default)

    @classmethod
    def get_int(cls, key: str, default: int = 0) -> int:
        """获取整数配置值"""
        val = cls._config.get(key)
        try:
            return int(val) if val is not None else default
        except ValueError:
            return default

    @classmethod
    async def refresh(cls):
        """刷新配置"""
        await cls.load()

    @classmethod
    async def set(cls, key: str, value: str):
        """设置配置值并持久化到数据库"""
        try:
            if key == "trap_autostart":
                raise ValueError("trap_autostart 配置已废弃")
            # 1. 更新数据库
            # 使用 UPSERT 语法 (PostgreSQL 特有: ON CONFLICT)
            # 注意：system_settings 表有 not-null 约束的 group_name 字段，默认设为 'system'
            sql = """
                INSERT INTO system_settings (key, value, group_name) 
                VALUES ($1, $2, 'system')
                ON CONFLICT (key) 
                DO UPDATE SET value = $2
            """
            await db.execute(sql, key, str(value))
            
            # 2. 更新内存缓存
            cls._config[key] = str(value)
            logger.info(f"更新系统配置: {key} = {value}")
            return True
        except Exception as e:
            logger.error(f"更新系统配置失败 {key}={value}: {e}")
            raise e
