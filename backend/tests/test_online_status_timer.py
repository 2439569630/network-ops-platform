import asyncio
import unittest
from unittest.mock import AsyncMock

from app.workers.monitor.alert_handler import AlertHandler


class _Rule:
    def __init__(
        self,
        *,
        id: int,
        device_id: int,
        duration: int,
        cooldown: int = 0,
        severity: str = "warning",
        is_enabled: bool = True,
    ):
        self.id = int(id)
        self.device_id = int(device_id)
        self.metric = "online_status"
        self.operator = "="
        self.threshold = 1.0
        self.duration = int(duration)
        self.cooldown = int(cooldown)
        self.severity = str(severity)
        self.is_enabled = bool(is_enabled)


class TestOnlineStatusTimer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h = AlertHandler()
        self.h._try_acquire_firing_lock = AsyncMock(return_value="local")
        self.h._log_alert = AsyncMock()
        self.h.start_background_tasks()

    async def asyncTearDown(self):
        await self.h.stop_background_tasks()

    async def test_duration_zero_fires_once_per_episode(self):
        did = 101
        r = _Rule(id=1, device_id=did, duration=0)
        self.h.alert_rules[did]["online_status"] = [r]

        self.h.on_device_normal_state(did, True)
        self.h.on_device_normal_state(did, True)
        await asyncio.sleep(0.2)
        self.assertEqual(self.h._log_alert.await_count, 1)

        self.h.on_device_normal_state(did, False)
        await asyncio.sleep(0.05)
        self.h.on_device_normal_state(did, True)
        await asyncio.sleep(0.2)
        self.assertEqual(self.h._log_alert.await_count, 2)

    async def test_duration_canceled_when_leave_normal(self):
        did = 102
        r = _Rule(id=2, device_id=did, duration=1)
        self.h.alert_rules[did]["online_status"] = [r]

        self.h.on_device_normal_state(did, True)
        await asyncio.sleep(0.5)
        self.h.on_device_normal_state(did, False)
        await asyncio.sleep(0.7)
        self.assertEqual(self.h._log_alert.await_count, 0)

        self.h.on_device_normal_state(did, True)
        await asyncio.sleep(1.2)
        self.assertEqual(self.h._log_alert.await_count, 1)


if __name__ == "__main__":
    unittest.main()
