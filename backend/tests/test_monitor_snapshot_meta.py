import time
import unittest

from app.workers.monitor.manager import MonitorManager


class TestMonitorSnapshotMeta(unittest.TestCase):
    def setUp(self):
        self.monitor = MonitorManager()
        self.monitor.devices.clear()
        self.monitor.tasks.clear()

    def test_age_and_stale_computed_from_last_updated(self):
        snap = {
            "status": "在线",
            "fsm_state": "online",
            "last_updated": str(time.time() - 1000),
        }
        out = self.monitor._enrich_snapshot_meta(snap, "redis")
        self.assertGreaterEqual(float(out.get("age_seconds") or 0), 900.0)
        self.assertTrue(bool(out.get("stale")))
        self.assertEqual(out.get("snapshot_source"), "redis")

    def test_no_timestamp_is_not_stale(self):
        snap = {"status": "无运行态", "fsm_state": ""}
        out = self.monitor._enrich_snapshot_meta(snap, "miss")
        self.assertEqual(float(out.get("age_seconds") or 0), 0.0)
        self.assertFalse(bool(out.get("stale")))
        self.assertEqual(out.get("snapshot_source"), "miss")


if __name__ == "__main__":
    unittest.main()

