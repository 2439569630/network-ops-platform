
import logging
from typing import Dict, Any
from app.models.orm.config import SystemSetting

logger = logging.getLogger(__name__)

class SystemConfig:
    """动态系统配置管理类"""
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
            settings = await SystemSetting.all()
            for s in settings:
                if s.key != 'trap_autostart':
                    cls._config[s.key] = s.value or ""
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
            
            # Use update_or_create
            await SystemSetting.update_or_create(
                key=key,
                defaults={"value": str(value), "group_name": "system"}
            )
            
            # Update memory cache
            cls._config[key] = str(value)
            logger.info(f"更新系统配置: {key} = {value}")
            return True
        except Exception as e:
            logger.error(f"更新系统配置失败 {key}={value}: {e}")
            raise e
