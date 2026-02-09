import unittest

from app.drivers.ssh_retry import classify_ssh_failure
from app.services.notification_service import NotificationService


class NetmikoTimeoutException(Exception):
    pass


class TestSSHFailureLocalization(unittest.TestCase):
    def test_timeout_reason_is_chinese(self):
        e = NetmikoTimeoutException("TCP connection to device failed.")
        decision = classify_ssh_failure(e)
        self.assertEqual(decision.category, "timeout")
        self.assertIn("连接超时", decision.reason)
        self.assertIn("TCP 连接失败", decision.reason)
        self.assertNotIn("TCP connection", decision.reason)
        self.assertNotIn("NetmikoTimeoutException", decision.reason)

    def test_unknown_reason_does_not_leak_raw_english(self):
        class WeirdError(Exception):
            pass

        e = WeirdError("some random english detail")
        decision = classify_ssh_failure(e)
        self.assertEqual(decision.category, "unknown")
        self.assertIn("连接失败", decision.reason)
        self.assertNotIn("random", decision.reason.lower())


class TestAlertEmailFormatting(unittest.TestCase):
    def test_offline_email_is_structured(self):
        body = NotificationService._format_device_alert_email_content(
            message="设备离线: 连接超时: TCP 连接失败",
            device_name="AR1",
            device_ip="127.0.0.1",
            severity_cn="严重",
            time_iso="2026-02-06T09:59:46.176369+00:00",
        )
        self.assertTrue(body.startswith("告警: 设备离线\n"))
        self.assertIn("原因: 连接超时: TCP 连接失败\n", body)
        self.assertIn("设备: AR1 (127.0.0.1)\n", body)
        self.assertIn("级别: 严重\n", body)
        self.assertIn("时间: 2026-02-06T09:59:46.176369+00:00\n", body)
        self.assertIn("处理建议:\n", body)
        self.assertNotIn("TCP connection", body)


if __name__ == "__main__":
    unittest.main()

