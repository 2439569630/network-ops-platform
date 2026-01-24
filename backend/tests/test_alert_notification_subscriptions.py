import unittest
from unittest.mock import AsyncMock, patch

from app.services.notification_service import NotificationService


class TestAlertNotificationSubscriptions(unittest.IsolatedAsyncioTestCase):
    def test_severity_matches(self):
        self.assertTrue(NotificationService._severity_matches(None, "warning"))
        self.assertTrue(NotificationService._severity_matches([], "warning"))
        self.assertTrue(NotificationService._severity_matches(["warning"], "warning"))
        self.assertFalse(NotificationService._severity_matches(["critical"], "warning"))

    async def test_notify_device_alert_merges_recipients_and_channels(self):
        dev = type("Dev", (), {"created_by": "1", "device_name": "SW1", "ipv4": "10.0.0.1"})()
        qs = type("QS", (), {"first": AsyncMock(return_value=dev)})()

        def _filter(*args, **kwargs):
            return qs

        captured = {"site": None, "email": None}

        async def _capture_site(*, user_ids, title, content, source):
            captured["site"] = set(user_ids)

        async def _capture_email(*, user_ids, subject, content):
            captured["email"] = set(user_ids)
            return {"sent": 0, "skipped": 0, "errors": 0}

        with patch("app.services.notification_service.NetworkDevice.filter", new=_filter):
            with patch("app.services.notification_service.NotificationService.notify", new=AsyncMock(return_value={"time": "t"})):
                with patch(
                    "app.services.notification_service.NotificationService._get_location_recipient_user_ids",
                    new=AsyncMock(return_value={2}),
                ):
                    with patch(
                        "app.services.notification_service.NotificationService._get_device_location_node_id",
                        new=AsyncMock(return_value=10),
                    ):
                        with patch(
                            "app.services.notification_service.NotificationService._get_subscription_channel_recipients",
                            new=AsyncMock(return_value={"site": {3}, "email": {4}}),
                        ):
                            with patch(
                                "app.services.notification_service.NotificationService._notify_site_message_to_users",
                                new=_capture_site,
                            ):
                                with patch(
                                    "app.services.notification_service.NotificationService._send_alert_emails",
                                    new=_capture_email,
                                ):
                                    await NotificationService.notify_device_alert(
                                        99, "CPU 过高", "warning", rule_id=7
                                    )

        self.assertEqual(captured["site"], {1, 2, 3})
        self.assertEqual(captured["email"], {4})


if __name__ == "__main__":
    unittest.main()
