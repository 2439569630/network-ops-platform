
import asyncpg
import logging
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

class Database:
    """PostgreSQL 数据库管理类"""
    _pool: Optional[asyncpg.Pool] = None

    @classmethod
    async def connect(cls):
        """连接数据库"""
        if cls._pool:
            return
            
        logger.info("正在连接 PostgreSQL 数据库...")
        try:
            cls._pool = await asyncpg.create_pool(
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                host=settings.POSTGRES_SERVER,
                port=settings.POSTGRES_PORT,
                database=settings.POSTGRES_DB,
                min_size=5,
                max_size=20,
            )
            logger.info("数据库连接成功")
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            raise e

    @classmethod
    async def disconnect(cls):
        """断开数据库连接"""
        if cls._pool:
            await cls._pool.close()
            cls._pool = None
            logger.info("数据库连接已断开")

    @classmethod
    def get_pool(cls) -> asyncpg.Pool:
        if not cls._pool:
            raise RuntimeError("Database not initialized")
        return cls._pool

    # Helper methods
    @classmethod
    async def fetch_all(cls, query: str, *args):
        if not cls._pool:
            raise RuntimeError("Database not initialized")
        async with cls._pool.acquire() as conn:
            return await conn.fetch(query, *args)

    @classmethod
    async def fetch_one(cls, query: str, *args):
        if not cls._pool:
            raise RuntimeError("Database not initialized")
        async with cls._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    @classmethod
    async def execute(cls, query: str, *args):
        if not cls._pool:
            raise RuntimeError("Database not initialized")
        async with cls._pool.acquire() as conn:
            return await conn.execute(query, *args)
            
    @classmethod
    async def fetch_val(cls, query: str, *args):
        if not cls._pool:
            raise RuntimeError("Database not initialized")
        async with cls._pool.acquire() as conn:
            return await conn.fetchval(query, *args)

db = Database()

TORTOISE_ORM = {
    "connections": {"default": settings.DATABASE_URL},
    "apps": {
        "models": {
            "models": [
                "app.models.orm.user",
                "app.models.orm.device",
                "app.models.orm.audit",
                "app.models.orm.notification",
                "app.models.orm.location",
                "app.models.orm.rbac",
                "app.models.orm.repair",
                "app.models.orm.log",
                "app.models.orm.config",
                "app.models.orm.config_push",
                "app.models.orm.alert",
                "aerich.models",
            ],
            "default_connection": "default",
        },
    },
}
