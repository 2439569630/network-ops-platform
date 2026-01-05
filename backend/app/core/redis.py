
import logging
from redis.asyncio import ConnectionPool, Redis
from app.core.config import settings

logger = logging.getLogger(__name__)

class RedisManager:
    _pool: ConnectionPool = None

    @classmethod
    async def init(cls):
        if cls._pool:
            return

        logger.info("正在初始化 Redis 连接池...")
        try:
            url = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}" \
                if settings.REDIS_PASSWORD else \
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}"
            
            cls._pool = ConnectionPool.from_url(
                url,
                decode_responses=True,
                max_connections=20,
                health_check_interval=30
            )
            logger.info("Redis 初始化完成")
        except Exception as e:
            logger.error(f"Redis 初始化失败: {e}")
            raise e

    @classmethod
    async def close(cls):
        if cls._pool:
            await cls._pool.disconnect()
            cls._pool = None
            logger.info("Redis 连接已断开")

    @classmethod
    def get_client(cls) -> Redis:
        if not cls._pool:
            raise RuntimeError("Redis not initialized")
        return Redis(connection_pool=cls._pool)

redis_manager = RedisManager()
