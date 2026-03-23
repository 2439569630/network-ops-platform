import unittest
from unittest.mock import patch

from app.services.notification_service import NotificationService


class TestNotificationEmailBoundaries(unittest.IsolatedAsyncioTestCase):
    async def test_alert_capabilities_global_block_reason_is_config_based(self):
        def _get_value(key):
            if key == "email_enabled":
                return "0"
            return None

        with patch("app.services.notification_service.SystemConfig.get", side_effect=_get_value):
            data = await NotificationService.get_alert_notification_capabilities(user_id=None, device_id=None)

        email = data.get("email") or {}
        reasons = email.get("unavailable_reasons") or []
        self.assertFalse(email.get("global_enabled"))
        self.assertEqual(email.get("global_block_reason"), "config_disabled")
        self.assertNotIn("permission_disabled", reasons)


if __name__ == "__main__":
    unittest.main()
