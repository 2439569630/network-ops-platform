import time
import unittest

from app.drivers.base import BaseDevice
from app.workers.monitor.manager import MonitorManager


class _DummyConn:
    def disconnect(self):
        return None


class DummyDevice(BaseDevice):
    def __init__(self, device_info: dict):
        super().__init__(device_info)
        self.device_type = "linux"
        self._connect_calls = 0
        self._always_fail_connect = True

    def _connect_once_sync(self):
        self._connect_calls += 1
        if self._always_fail_connect:
            raise TimeoutError("timed out")
        return _DummyConn()

    async def collect_status(self):
        return {}


class TestReconnectPolicy(unittest.IsolatedAsyncioTestCase):
    async def test_connect_startup_uses_config_retries(self):
        d = DummyDevice({"id": 1, "ipv4": "127.0.0.1"})
        d.config = d.config.with_overrides(connect_max_retries=5, connect_retry_delay_seconds=0.0)
        ok = await d.connect(purpose="startup")
        self.assertFalse(ok)
        self.assertEqual(d._connect_calls, 5)

    async def test_connect_steady_is_single_attempt(self):
        d = DummyDevice({"id": 1, "ipv4": "127.0.0.1"})
        d.config = d.config.with_overrides(connect_max_retries=9, connect_retry_delay_seconds=999.0)
        ok = await d.connect(purpose="steady")
        self.assertFalse(ok)
        self.assertEqual(d._connect_calls, 1)


class TestRetrySnapshotFields(unittest.TestCase):
    def test_snapshot_does_not_contain_retry_fields(self):
        monitor = MonitorManager()
        monitor.devices.clear()
        monitor.tasks.clear()

        d = DummyDevice({"id": 1, "ipv4": "127.0.0.1"})
        d.next_retry_at_epoch = float(time.time() + 30)
        d.next_retry_at = str(d.next_retry_at_epoch)
        d.retry_phase = "offline"
        d.retry_attempt = 2
        monitor.devices[1] = d

        snap = monitor.get_runtime_snapshot(1)
        self.assertNotIn("next_retry_at", snap)
        self.assertNotIn("next_retry_at_epoch", snap)
        self.assertNotIn("retry_in_seconds", snap)
        self.assertNotIn("retry_attempt", snap)
        self.assertNotIn("retry_phase", snap)


if __name__ == "__main__":
    unittest.main()
