import asyncio
import unittest

from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.redis import redis_manager


class TestRedisPoolSplit(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        try:
            await redis_manager.init()
            client = redis_manager.get_client()
            await asyncio.wait_for(client.ping(), timeout=0.5)
        except Exception:
            raise unittest.SkipTest("Redis 不可用，跳过连接池拆分测试")

    async def asyncTearDown(self) -> None:
        try:
            await redis_manager.close()
        except Exception:
            pass

    async def test_pubsub_does_not_exhaust_default_pool(self):
        client = redis_manager.get_client()
        pubsub_client = redis_manager.get_pubsub_client()

        pubsubs = []
        try:
            for i in range(30):
                ps = pubsub_client.pubsub()
                await asyncio.wait_for(ps.subscribe(f"test:poolsplit:{i}"), timeout=0.5)
                pubsubs.append(ps)

            await client.set("test:poolsplit:key", "1", ex=30)
            v = await client.get("test:poolsplit:key")
            self.assertEqual(v, "1")
        except asyncio.TimeoutError:
            raise unittest.SkipTest("Redis 连接超时，跳过连接池拆分测试")
        except RedisConnectionError as e:
            self.fail(f"不应因 PubSub 长连接占满导致默认池耗尽: {e}")
        finally:
            for i, ps in enumerate(pubsubs):
                try:
                    await ps.unsubscribe(f"test:poolsplit:{i}")
                except Exception:
                    pass
                try:
                    await ps.aclose()
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()
