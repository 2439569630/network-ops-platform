import asyncio
import contextlib
import unittest
from unittest import mock

from app.drivers.models.status import DeviceConfig, DeviceStatus
from app.workers.monitor.manager import MonitorManager


class DummyDevice:
    def __init__(self, interval: float, monitor_interval: float):
        self.device_id = 1
        self.ip = "127.0.0.1"
        self.device_name = "dummy"
        self.config = DeviceConfig(
            interval=float(interval),
            monitor_interval=float(monitor_interval),
            offline_fail_threshold=3,
            recovery_success_threshold=1,
            connect_timeout=0.1,
            auth_timeout=0.1,
            banner_timeout=0.1,
            connect_max_retries=1,
            connect_retry_delay_seconds=0.0,
            offline_retry_delay_seconds=0.1,
        )
        self.interval = float(interval)
        self.monitor_interval = float(monitor_interval)
        self.status = DeviceStatus(
            offline_fail_threshold=3,
            recovery_success_threshold=1,
        )
        self.connected = True
        self.last_connect_error = None
        self.collect_calls = 0
        self._active_inspection_id = None
        self._active_inspection_commands = []

    def begin_inspection(self, inspect_id: str, max_commands: int = 8) -> None:
        self._active_inspection_id = inspect_id
        self._active_inspection_commands = []

    def end_inspection(self):
        cmds = list(self._active_inspection_commands)
        self._active_inspection_id = None
        self._active_inspection_commands = []
        return cmds

    @property
    def fsm_state(self) -> str:
        return str(self.status.fsm_state or "")

    @property
    def fsm_reason(self) -> str:
        return str(self.status.fsm_reason or "")

    @property
    def offline_fail_threshold(self) -> int:
        return int(self.status.offline_fail_threshold)

    @property
    def consecutive_failures(self) -> int:
        return int(self.status.consecutive_failures)

    def record_success(self) -> bool:
        return bool(self.status.record_success())

    def record_failure(self, reason: str | None = None):
        return self.status.record_failure(reason)

    async def connect(self, progress_cb=None, purpose: str | None = None) -> bool:
        self.connected = True
        return True

    async def check_online(self, progress_cb=None) -> bool:
        return True

    async def collect_once(self):
        return {}

    async def collect_status(self):
        self.collect_calls += 1
        if self._active_inspection_id:
            self._active_inspection_commands.append("dummy:collect_status")
        return {"cpu_usage": 1.0, "memory_usage": 2.0, "disk_usage": 3.0}


class TestMonitorTickless(unittest.IsolatedAsyncioTestCase):
    async def test_interval_one_second_not_blocked_by_monitor_interval(self):
        manager = MonitorManager()
        manager.running = True
        manager._monitor_log_detail = "summary"

        async def _noop(*args, **kwargs):
            return None

        manager._update_runtime_status = _noop  # type: ignore[method-assign]
        manager._update_fsm_meta = _noop  # type: ignore[method-assign]
        manager._update_heartbeat = _noop  # type: ignore[method-assign]
        manager._set_device_offline = _noop  # type: ignore[method-assign]
        manager._save_data_redis = _noop  # type: ignore[method-assign]

        device = DummyDevice(interval=1.0, monitor_interval=10.0)

        with self.assertLogs("app.workers.monitor.manager", level="INFO") as cm:
            with mock.patch("app.workers.monitor.manager.random.uniform", return_value=0.0):
                task = asyncio.create_task(manager._monitor_device_loop(1, device))
                await asyncio.sleep(2.2)
                manager.running = False
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        self.assertGreaterEqual(device.collect_calls, 2)
        logs = "\n".join(cm.output)
        self.assertIn("巡检开始 inspect_id=", logs)
        self.assertIn("巡检完成 inspect_id=", logs)
        self.assertIn("cmds=[dummy:collect_status]", logs)


class TestDriverTimeSlicing(unittest.TestCase):
    def test_linux_driver_time_slicing(self):
        from app.drivers.linux_driver import LinuxServer

        device = LinuxServer(
            {
                "id": 1,
                "ipv4": "127.0.0.1",
                "user_name": "x",
                "password": "y",
                "ssh_port": 22,
                "device_type": "linux",
            }
        )

        calls = {"cpu": 0, "mem": 0, "disk": 0}

        async def cpu():
            calls["cpu"] += 1
            return 10.0

        async def mem():
            calls["mem"] += 1
            return 20.0

        async def disk():
            calls["disk"] += 1
            return 30.0

        device.get_cpu_usage = cpu  # type: ignore[method-assign]
        device.get_memory_usage = mem  # type: ignore[method-assign]
        device.get_disk_usage = disk  # type: ignore[method-assign]

        async def run():
            with mock.patch("app.drivers.linux_driver.time.monotonic", side_effect=[0.0, 1.0, 2.0, 9.0, 10.0, 11.0]):
                await device.collect_status()
                await device.collect_status()
                await device.collect_status()
                await device.collect_status()
                await device.collect_status()
                await device.collect_status()

        asyncio.run(run())

        self.assertGreaterEqual(calls["cpu"], 2)
        self.assertGreaterEqual(calls["mem"], 2)
        self.assertEqual(calls["disk"], 2)

    def test_huawei_driver_time_slicing(self):
        from app.drivers.netmiko_driver import HuaweiDevice

        device = HuaweiDevice(
            {
                "id": 1,
                "ipv4": "127.0.0.1",
                "user_name": "x",
                "password": "y",
                "ssh_port": 22,
                "device_type": "huawei",
            }
        )

        calls = {"health": 0, "version": 0}

        async def health():
            calls["health"] += 1
            return "System CPU Usage Information\n0 20 %\n"

        async def version():
            calls["version"] += 1
            return "Huawei AR2220 Router uptime is 1 week, 2 days\n"

        device.fetch_display_health = health  # type: ignore[method-assign]
        device.fetch_display_version = version  # type: ignore[method-assign]

        async def run():
            with mock.patch("app.drivers.netmiko_driver.time.monotonic", side_effect=[0.0, 1.0, 2.0, 59.0, 60.0, 61.0]):
                await device.collect_status()
                await device.collect_status()
                await device.collect_status()
                await device.collect_status()
                await device.collect_status()
                await device.collect_status()

        asyncio.run(run())

        self.assertGreaterEqual(calls["health"], 2)
        self.assertEqual(calls["version"], 2)
