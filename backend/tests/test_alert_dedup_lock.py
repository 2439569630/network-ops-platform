import unittest
from unittest.mock import patch

from app.workers.monitor.alert_handler import AlertHandler


class TestAlertDedupLock(unittest.IsolatedAsyncioTestCase):
    def test_compute_lock_ttl(self):
        h = AlertHandler()
        self.assertEqual(h._compute_firing_lock_ttl_seconds(cooldown_seconds=0), 600)
        self.assertEqual(h._compute_firing_lock_ttl_seconds(cooldown_seconds=120), 600)
        self.assertEqual(h._compute_firing_lock_ttl_seconds(cooldown_seconds=3600), 3600)

    async def test_lock_fallback_without_redis(self):
        h = AlertHandler()
        with patch("app.workers.monitor.alert_handler.redis_manager.get_client", side_effect=Exception("no redis")):
            token = await h._try_acquire_firing_lock(1, 2, 10)
            self.assertEqual(token, "local")
            await h._release_firing_lock(1, 2, token="local")
            await h._refresh_firing_lock(1, 2, token="local", ttl_seconds=10)


if __name__ == "__main__":
    unittest.main()
