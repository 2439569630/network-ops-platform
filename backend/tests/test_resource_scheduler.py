import asyncio
import contextlib
import unittest
from unittest import mock

from app.drivers.models.status import DeviceConfig, DeviceStatus
from app.workers.monitor.manager import MonitorManager


class DummyHuaweiDevice:
    def __init__(
        self,
        *,
        interval: float = 0.0,
        monitor_interval: float = 0.0,
        interfaces_sync_interval: float = 3.0,
        routes_sync_interval: float = 0.0,
        vlans_sync_interval: float = 0.0,
        interfaces_slot0_sync_interval: float = 0.0,
    ):
        self.device_id = 1
        self.ip = "127.0.0.1"
        self.device_name = "dummy-huawei"
        self.config = DeviceConfig(
            interval=float(interval),
            monitor_interval=float(monitor_interval),
            interfaces_sync_interval=float(interfaces_sync_interval),
            routes_sync_interval=float(routes_sync_interval),
            vlans_sync_interval=float(vlans_sync_interval),
            interfaces_slot0_sync_interval=float(interfaces_slot0_sync_interval),
        )
        self.interval = float(interval)
        self.monitor_interval = float(monitor_interval)
        self.status = DeviceStatus(offline_fail_threshold=3, recovery_success_threshold=1)
        self.connected = True
        self.last_connect_error = None
        self.collect_calls = 0
        self.interfaces_calls = 0
        self.schedule_rev = 0

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

    async def connect(self, progress_cb=None) -> bool:
        self.connected = True
        return True

    async def collect_once(self):
        return {}

    async def check_online(self, progress_cb=None) -> bool:
        return True

    async def collect_status(self):
        self.collect_calls += 1
        return {"cpu_usage": 1.0, "memory_usage": 2.0, "disk_usage": 3.0}

    async def collect_interfaces(self):
        self.interfaces_calls += 1
        return [{"name": "Eth0/0/0", "status": "up"}]

    def set_state_phase(self, phase: str, reason: str | None = None) -> bool:
        return self.status.set_phase(phase, reason)


class TestResourceScheduler(unittest.IsolatedAsyncioTestCase):
    async def test_interfaces_job_runs_every_3_seconds_even_if_metrics_10_seconds(self):
        manager = MonitorManager()
        manager.running = True

        async def _noop(*args, **kwargs):
            return None

        manager._update_runtime_status = _noop  # type: ignore[method-assign]
        manager._update_fsm_meta = _noop  # type: ignore[method-assign]
        manager._update_heartbeat = _noop  # type: ignore[method-assign]
        manager._set_device_offline = _noop  # type: ignore[method-assign]
        manager._save_data_redis = _noop  # type: ignore[method-assign]

        device = DummyHuaweiDevice(interval=10.0, interfaces_sync_interval=3.0)

        fake_now = 0.0
        real_sleep = asyncio.sleep

        async def fake_sleep(dt: float):
            nonlocal fake_now
            try:
                fake_now += float(dt or 0.0)
            except Exception:
                pass
            if fake_now >= 10.0:
                manager.running = False
            await real_sleep(0)

        with (
            mock.patch("app.workers.monitor.manager.random.uniform", return_value=0.0),
            mock.patch("app.workers.monitor.manager.time.monotonic", side_effect=lambda: fake_now),
            mock.patch("app.workers.monitor.manager.asyncio.sleep", side_effect=fake_sleep),
            mock.patch("app.workers.monitor.manager.redis_manager.get_client", side_effect=Exception("no-redis")),
        ):
            task = asyncio.create_task(manager._monitor_device_loop(1, device))
            for _ in range(200):
                if not manager.running:
                    break
                await real_sleep(0)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        self.assertGreaterEqual(device.interfaces_calls, 4)

    async def test_interfaces_job_zero_runs_continuously(self):
        manager = MonitorManager()
        manager.running = True

        async def _noop(*args, **kwargs):
            return None

        manager._update_runtime_status = _noop  # type: ignore[method-assign]
        manager._update_fsm_meta = _noop  # type: ignore[method-assign]
        manager._update_heartbeat = _noop  # type: ignore[method-assign]
        manager._set_device_offline = _noop  # type: ignore[method-assign]
        manager._save_data_redis = _noop  # type: ignore[method-assign]

        device = DummyHuaweiDevice(interfaces_sync_interval=0.0)

        fake_now = 0.0
        real_sleep = asyncio.sleep

        async def fake_sleep(dt: float):
            nonlocal fake_now
            d = float(dt or 0.0)
            if d <= 0:
                fake_now += 0.0001
            else:
                fake_now += d
            if fake_now >= 0.01:
                manager.running = False
            await real_sleep(0)

        with (
            mock.patch("app.workers.monitor.manager.random.uniform", return_value=0.0),
            mock.patch("app.workers.monitor.manager.time.monotonic", side_effect=lambda: fake_now),
            mock.patch("app.workers.monitor.manager.asyncio.sleep", side_effect=fake_sleep),
            mock.patch("app.workers.monitor.manager.redis_manager.get_client", side_effect=Exception("no-redis")),
        ):
            task = asyncio.create_task(manager._monitor_device_loop(1, device))
            for _ in range(2000):
                if not manager.running:
                    break
                await real_sleep(0)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        self.assertGreater(device.interfaces_calls, 10)

    async def test_interfaces_job_minus_one_stops(self):
        manager = MonitorManager()
        manager.running = True

        async def _noop(*args, **kwargs):
            return None

        manager._update_runtime_status = _noop  # type: ignore[method-assign]
        manager._update_fsm_meta = _noop  # type: ignore[method-assign]
        manager._update_heartbeat = _noop  # type: ignore[method-assign]
        manager._set_device_offline = _noop  # type: ignore[method-assign]
        manager._save_data_redis = _noop  # type: ignore[method-assign]

        device = DummyHuaweiDevice(interfaces_sync_interval=-1.0)

        fake_now = 0.0
        real_sleep = asyncio.sleep

        async def fake_sleep(dt: float):
            nonlocal fake_now
            fake_now += float(dt or 0.0)
            if fake_now >= 0.05:
                manager.running = False
            await real_sleep(0)

        with (
            mock.patch("app.workers.monitor.manager.random.uniform", return_value=0.0),
            mock.patch("app.workers.monitor.manager.time.monotonic", side_effect=lambda: fake_now),
            mock.patch("app.workers.monitor.manager.asyncio.sleep", side_effect=fake_sleep),
            mock.patch("app.workers.monitor.manager.redis_manager.get_client", side_effect=Exception("no-redis")),
        ):
            task = asyncio.create_task(manager._monitor_device_loop(1, device))
            for _ in range(200):
                if not manager.running:
                    break
                await real_sleep(0)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        self.assertEqual(device.interfaces_calls, 0)

    async def test_schedule_rebuild_applies_new_intervals(self):
        manager = MonitorManager()
        manager.running = True

        async def _noop(*args, **kwargs):
            return None

        manager._update_runtime_status = _noop  # type: ignore[method-assign]
        manager._update_fsm_meta = _noop  # type: ignore[method-assign]
        manager._update_heartbeat = _noop  # type: ignore[method-assign]
        manager._set_device_offline = _noop  # type: ignore[method-assign]
        manager._save_data_redis = _noop  # type: ignore[method-assign]

        device = DummyHuaweiDevice(interval=-1.0, interfaces_sync_interval=-1.0)

        fake_now = 0.0
        real_sleep = asyncio.sleep
        updated = False

        async def fake_sleep(dt: float):
            nonlocal fake_now, updated
            d = float(dt or 0.0)
            if d <= 0:
                fake_now += 0.0001
            else:
                fake_now += d
            if not updated and fake_now >= 0.05:
                device.config = device.config.with_overrides(interfaces_sync_interval=0.0)
                device.schedule_rev += 1
                updated = True
            if fake_now >= 0.2:
                manager.running = False
            await real_sleep(0)

        with (
            mock.patch("app.workers.monitor.manager.random.uniform", return_value=0.0),
            mock.patch("app.workers.monitor.manager.time.monotonic", side_effect=lambda: fake_now),
            mock.patch("app.workers.monitor.manager.asyncio.sleep", side_effect=fake_sleep),
            mock.patch("app.workers.monitor.manager.redis_manager.get_client", side_effect=Exception("no-redis")),
        ):
            task = asyncio.create_task(manager._monitor_device_loop(1, device))
            for _ in range(2000):
                if not manager.running:
                    break
                await real_sleep(0)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        self.assertTrue(updated)
        self.assertGreater(device.interfaces_calls, 0)
