import asyncio
import contextlib
import unittest

from app.workers.monitor.manager import MonitorManager


class TestDeviceEventMerge(unittest.TestCase):
    def test_merge_priority_delete_wins(self):
        m = MonitorManager()
        merged = m._merge_device_event_payload(
            {"action": "config_update", "device_id": 1},
            {"action": "delete", "device_id": 1},
        )
        self.assertEqual(str(merged.get("action")), "delete")

    def test_merge_priority_update_over_config(self):
        m = MonitorManager()
        merged = m._merge_device_event_payload(
            {"action": "config_update", "device_id": 1},
            {"action": "update", "device_id": 1},
        )
        self.assertEqual(str(merged.get("action")), "update")


class TestDeviceEventConsumer(unittest.IsolatedAsyncioTestCase):
    async def test_consumer_coalesces_before_start(self):
        m = MonitorManager()

        orig_running = bool(getattr(m, "running", False))
        orig_handler = m._handle_device_event

        handled: list[dict] = []

        async def handler(payload: dict) -> None:
            handled.append(dict(payload))

        try:
            m.running = True
            m._handle_device_event = handler  # type: ignore[method-assign]

            await m._enqueue_device_event({"action": "update", "device_id": 1})
            await m._enqueue_device_event({"action": "config_update", "device_id": 1})
            await m._enqueue_device_event({"action": "delete", "device_id": 1})

            task = asyncio.create_task(m._device_event_consumer_loop())
            await asyncio.sleep(0.05)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        finally:
            m._handle_device_event = orig_handler  # type: ignore[method-assign]
            m.running = orig_running

        self.assertEqual(len(handled), 1)
        self.assertEqual(str(handled[0].get("action") or ""), "delete")


class TestConfigUpdateReload(unittest.IsolatedAsyncioTestCase):
    async def test_config_update_does_not_recreate(self):
        m = MonitorManager()
        orig = m._ensure_device_running
        called: list[tuple[int, bool]] = []

        async def _fake(device_id: int, recreate: bool = False) -> None:
            called.append((int(device_id), bool(recreate)))

        try:
            m._ensure_device_running = _fake  # type: ignore[method-assign]
            await m._handle_device_event({"action": "config_update", "device_id": 17})
        finally:
            m._ensure_device_running = orig  # type: ignore[method-assign]

        self.assertEqual(called, [(17, False)])
