import asyncio
import fnmatch
import json
import unittest


class FakeRedis:
    def __init__(self, initial=None):
        self.store = dict(initial or {})
        self.published = []

    async def delete(self, *keys):
        removed = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                removed += 1
        return removed

    async def scan(self, cursor=0, match=None, count=10):
        pattern = match or "*"
        keys = [k for k in list(self.store.keys()) if fnmatch.fnmatch(k, pattern)]
        return 0, keys

    async def publish(self, channel, message):
        self.published.append((channel, message))
        return 1


class MonitorRedisCleanupTests(unittest.TestCase):
    def test_clear_redis_status_deletes_all_resource_keys(self):
        from app.core import redis as redis_module
        from app.workers.monitor.manager import MonitorManager

        fake = FakeRedis(
            {
                "monitor:runtime:snapshot:1": "x",
                "device:1:interfaces": "x",
                "device:1:interfaces:last": "x",
                "device:1:routes": "x",
                "device:1:routes:last": "x",
                "device:1:vlans": "x",
                "device:1:vlans:last": "x",
                "device:1:resources:meta": "{}",
                "device:1:interfaces_slot0_detailed": "x",
                "device:1:interfaces_slot0_detailed:last": "x",
                "device:1:interfaces_slot12_detailed": "x",
                "device:1:interfaces_slot12_detailed:last": "x",
                "device:1:unrelated": "keep",
                "device:2:interfaces": "keep",
                "device:2:interfaces:last": "keep",
            }
        )

        original_get_client = redis_module.redis_manager.get_client
        redis_module.redis_manager.get_client = lambda: fake
        try:
            monitor = MonitorManager()
            asyncio.run(monitor._clear_redis_status(1))
        finally:
            redis_module.redis_manager.get_client = original_get_client

        self.assertNotIn("monitor:runtime:snapshot:1", fake.store)
        self.assertNotIn("device:1:interfaces", fake.store)
        self.assertNotIn("device:1:interfaces:last", fake.store)
        self.assertNotIn("device:1:routes", fake.store)
        self.assertNotIn("device:1:routes:last", fake.store)
        self.assertNotIn("device:1:vlans", fake.store)
        self.assertNotIn("device:1:vlans:last", fake.store)
        self.assertNotIn("device:1:resources:meta", fake.store)
        self.assertNotIn("device:1:interfaces_slot0_detailed", fake.store)
        self.assertNotIn("device:1:interfaces_slot0_detailed:last", fake.store)
        self.assertNotIn("device:1:interfaces_slot12_detailed", fake.store)
        self.assertNotIn("device:1:interfaces_slot12_detailed:last", fake.store)
        self.assertIn("device:1:unrelated", fake.store)
        self.assertIn("device:2:interfaces", fake.store)
        self.assertIn("device:2:interfaces:last", fake.store)

        self.assertEqual(2, len(fake.published))
        self.assertEqual("device:resource:update", fake.published[0][0])
        update_payload = json.loads(fake.published[0][1])
        self.assertEqual(1, update_payload.get("device_id"))
        self.assertEqual(
            sorted(
                [
                    "interfaces",
                    "routes",
                    "vlans",
                    "interfaces_slot0_detailed",
                    "interfaces_slot12_detailed",
                ]
            ),
            update_payload.get("resources"),
        )

        self.assertEqual("ws:devices:resources:1", fake.published[1][0])
        ws_payload = json.loads(fake.published[1][1])
        self.assertEqual("resources_updated", ws_payload.get("type"))
        self.assertEqual(1, ws_payload.get("device_id"))
        self.assertEqual(update_payload.get("resources"), ws_payload.get("resources"))
        self.assertTrue(all(isinstance(v, list) and v == [] for v in ws_payload.get("data", {}).values()))


if __name__ == "__main__":
    unittest.main()
