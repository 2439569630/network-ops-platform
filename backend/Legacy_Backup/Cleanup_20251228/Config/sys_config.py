import logging
from typing import Dict, Any
from DataBase import PostgreSQL

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
            sql = "SELECT key, value FROM system_settings"
            rows = await PostgreSQL.execute(sql, fetch=True)
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
