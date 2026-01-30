import unittest

from app.services.notification_service import NotificationService


class TestAlertSubscriptionSeverityMatch(unittest.TestCase):
    def test_severity_matches(self):
        self.assertTrue(NotificationService._severity_matches(None, "info"))
        self.assertTrue(NotificationService._severity_matches([], "info"))
        self.assertTrue(NotificationService._severity_matches(["warning", "critical"], "critical"))
        self.assertFalse(NotificationService._severity_matches(["warning", "critical"], "info"))


if __name__ == "__main__":
    unittest.main()

