import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from app.core.redis_keys import RedisKeyFactory
from app.workers.monitor.alert_handler import AlertHandler


class _DummyLog:
    def __init__(self, log_id: int):
        self.id = int(log_id)
        self.triggered_at = datetime.now(timezone.utc)


class TestAlertDbTruthDedup(unittest.IsolatedAsyncioTestCase):
    async def test_prepare_firing_prefers_redis_marker(self):
        h = AlertHandler()
        h._get_unresolved_alert_marker = AsyncMock(return_value="exists")
        h._get_latest_unresolved_log = AsyncMock()
        h._set_unresolved_alert_marker = AsyncMock()

        should_notify = await h._prepare_firing_by_db_truth(1, 2)
        self.assertFalse(should_notify)
        h._get_latest_unresolved_log.assert_not_awaited()
        h._set_unresolved_alert_marker.assert_not_awaited()

    async def test_prepare_firing_rebuilds_from_db(self):
        h = AlertHandler()
        h._get_unresolved_alert_marker = AsyncMock(return_value="")
        h._get_latest_unresolved_log = AsyncMock(return_value=_DummyLog(101))
        h._set_unresolved_alert_marker = AsyncMock()

        should_notify = await h._prepare_firing_by_db_truth(3, 4)
        self.assertFalse(should_notify)
        h._set_unresolved_alert_marker.assert_awaited_once()

    async def test_prepare_firing_allows_new_alert(self):
        h = AlertHandler()
        h._get_unresolved_alert_marker = AsyncMock(return_value="")
        h._get_latest_unresolved_log = AsyncMock(return_value=None)
        h._set_unresolved_alert_marker = AsyncMock()

        should_notify = await h._prepare_firing_by_db_truth(5, 6)
        self.assertTrue(should_notify)
        h._set_unresolved_alert_marker.assert_not_awaited()


class TestRedisKeyNamespaces(unittest.TestCase):
    def test_alert_and_cache_namespace_separation(self):
        self.assertTrue(RedisKeyFactory.is_alert_state_key("alert:active:1:2"))
        self.assertTrue(RedisKeyFactory.is_alert_state_key("alert:cooldown:1:2"))
        self.assertTrue(RedisKeyFactory.is_alert_state_key("alert:dedupe:lock:1:2"))
        self.assertFalse(RedisKeyFactory.is_alert_state_key("monitor:runtime:snapshot:1"))
        self.assertFalse(RedisKeyFactory.is_alert_state_key("device:1:interfaces"))


if __name__ == "__main__":
    unittest.main()
