
import logging
from redis.asyncio import ConnectionPool, Redis
from app.core.config import settings

logger = logging.getLogger(__name__)

class RedisManager:
    """Redis 连接管理类"""
    _pool: ConnectionPool = None
    _pubsub_pool: ConnectionPool = None
    _client: Redis = None
    _pubsub_client: Redis = None

    @classmethod
    async def init(cls):
        """初始化 Redis 连接池"""
        if cls._pool and cls._pubsub_pool:
            return

        logger.info("正在初始化 Redis 连接池...")
        try:
            host = str(settings.REDIS_HOST or "").strip() or "localhost"
            port = int(settings.REDIS_PORT or 6379)
            password_raw = settings.REDIS_PASSWORD
            password = str(password_raw).strip() if password_raw is not None else ""
            password = password or None
            
            cls._pool = ConnectionPool(
                host=host,
                port=port,
                password=password,
                decode_responses=True,
                max_connections=int(getattr(settings, "REDIS_MAX_CONNECTIONS", 20) or 20),
                health_check_interval=30
            )
            cls._pubsub_pool = ConnectionPool(
                host=host,
                port=port,
                password=password,
                decode_responses=True,
                max_connections=int(getattr(settings, "REDIS_PUBSUB_MAX_CONNECTIONS", 200) or 200),
                health_check_interval=30,
            )
            cls._client = Redis(connection_pool=cls._pool)
            cls._pubsub_client = Redis(connection_pool=cls._pubsub_pool)
            logger.info("Redis 初始化完成")
        except Exception as e:
            logger.error(f"Redis 初始化失败: {e}")
            raise e

    @classmethod
    async def close(cls):
        """关闭 Redis 连接池"""
        try:
            if cls._client is not None:
                await cls._client.aclose()
        except Exception:
            pass
        try:
            if cls._pubsub_client is not None:
                await cls._pubsub_client.aclose()
        except Exception:
            pass
        cls._client = None
        cls._pubsub_client = None

        if cls._pool:
            await cls._pool.disconnect()
        if cls._pubsub_pool:
            await cls._pubsub_pool.disconnect()
        cls._pool = None
        cls._pubsub_pool = None
        logger.info("Redis 连接已断开")

    @classmethod
    def get_client(cls) -> Redis:
        """获取 Redis 客户端实例"""
        if not cls._pool or not cls._client:
            raise RuntimeError("Redis not initialized")
        return cls._client

    @classmethod
    def get_pubsub_client(cls) -> Redis:
        if not cls._pubsub_pool or not cls._pubsub_client:
            raise RuntimeError("Redis not initialized")
        return cls._pubsub_client

redis_manager = RedisManager()
