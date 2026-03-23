import time
import unittest

from app.drivers.base import BaseDevice
from app.utils.device_status import status_fields_from_snapshot
from app.workers.monitor.manager import MonitorManager


class DummyDevice(BaseDevice):
    def __init__(self, device_info: dict):
        super().__init__(device_info)
        self.device_type = "linux"

    def _connect_once_sync(self):
        return None

    async def collect_status(self):
        return {}


class TestRuntimeSnapshotSemantics(unittest.TestCase):
    def setUp(self):
        self.monitor = MonitorManager()
        self.monitor.devices.clear()
        self.monitor.tasks.clear()

    def test_offline_snapshot_metrics_hidden(self):
        d = DummyDevice({"id": 1, "ipv4": "127.0.0.1"})
        d.online_status = False
        d.fsm_state = "offline"
        d.last_metrics = {
            "cpu_usage": 81.2,
            "memory_usage": 73.4,
            "disk_usage": 65.1,
            "uptime": "10d",
        }
        d.last_metrics_updated = time.time()
        self.monitor.devices[1] = d

        snap = self.monitor.get_runtime_snapshot(1)
        self.assertEqual(snap.get("cpu_usage"), "--")
        self.assertEqual(snap.get("memory_usage"), "--")
        self.assertEqual(snap.get("disk_usage"), "--")

        status_fields = status_fields_from_snapshot(snap)
        self.assertEqual(status_fields.get("connectivity"), "offline")

    def test_online_snapshot_metrics_visible_and_freshness_fields(self):
        d = DummyDevice({"id": 2, "ipv4": "127.0.0.2"})
        d.online_status = True
        d.fsm_state = "online"
        d.last_metrics = {
            "cpu_usage": 23.6,
            "memory_usage": 45.2,
            "disk_usage": 67.9,
            "uptime": "2d",
        }
        d.last_metrics_updated = time.time()
        self.monitor.devices[2] = d

        snap = self.monitor.get_runtime_snapshot(2)
        self.assertTrue(str(snap.get("cpu_usage", "")).endswith("%"))
        self.assertIn("last_updated", snap)
        self.assertIn("age_seconds", snap)
        self.assertIn("stale", snap)

    def test_snapshot_marks_stale_when_last_update_too_old(self):
        d = DummyDevice({"id": 3, "ipv4": "127.0.0.3"})
        d.online_status = True
        d.fsm_state = "online"
        d.last_metrics = {
            "cpu_usage": 1.0,
            "memory_usage": 2.0,
            "disk_usage": 3.0,
        }
        d.last_metrics_updated = time.time() - 100000
        self.monitor.devices[3] = d

        snap = self.monitor.get_runtime_snapshot(3)
        self.assertTrue(bool(snap.get("stale")))
        self.assertGreater(float(snap.get("age_seconds") or 0), 0.0)


if __name__ == "__main__":
    unittest.main()
