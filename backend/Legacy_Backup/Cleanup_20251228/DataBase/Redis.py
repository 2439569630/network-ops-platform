import asyncio
import logging
import os
from dotenv import load_dotenv
from redis.asyncio import ConnectionPool, Redis

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()


class RedisManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisManager, cls).__new__(cls)
            cls._instance.pool = None
            cls._instance.redis = None
            
            # 获取环境变量
            redis_password = os.getenv("REDISPASSWORD", "")
            redis_host = os.getenv("REDISHOST", "localhost")

            # 正确构建 Redis URL
            if redis_password:
                # 包含密码的格式
                cls._instance.Redis_URL = f"redis://:{redis_password}@{redis_host}:6379"
            else:
                # 无密码连接
                cls._instance.Redis_URL = f"redis://{redis_host}:6379"

            logger.info(f"使用 Redis URL: {cls._instance.Redis_URL}")
        return cls._instance

    async def init_pool(self):
        """初始化连接池"""
        logger.info('初始化Redis链接池')
        try:
            self.pool = ConnectionPool.from_url(
                self.Redis_URL,
                db=0,
                decode_responses=True,
                max_connections=20,
                socket_timeout=5,
                socket_connect_timeout=2,
                health_check_interval=30,
                retry_on_timeout=True,
            )
            logger.info('Redis连接池初始化成功')
        except Exception as e:
            logger.error(f"初始化链接池失败: {str(e)}")
            raise

    async def get_redis(self) -> Redis:
        """获取Redis连接"""
        if not self.pool:
            # 如果连接池未初始化，先初始化
            await self.init_pool()

        # 创建使用连接池的Redis客户端
        return Redis(connection_pool=self.pool)

    async def close_pool(self):
        """关闭连接池"""
        if self.pool:
            await self.pool.disconnect()
            logger.info("Redis连接池已关闭")


# 测试用例
if __name__ == '__main__':
    async def main():
        """主测试函数"""
        # 初始化Redis管理器
        redis_manager = RedisManager()

        try:
            # 获取Redis连接
            redis = await redis_manager.get_redis()

            # 测试基本操作
            await redis.set("test", "hello world")
            value = await redis.get("test")
            logger.info(f"获取的值: {value}")

            # 测试更多操作
            await redis.hset("user:1", mapping={"name": "Alice", "age": "30"})
            user_data = await redis.hgetall("user:1")
            logger.info(f"用户数据: {user_data}")

        except Exception as e:
            logger.error(f"测试过程中出错: {str(e)}")
        finally:
            # 关闭连接池
            await redis_manager.close_pool()


    # 运行测试
    asyncio.run(main())
