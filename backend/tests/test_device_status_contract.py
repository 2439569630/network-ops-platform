import unittest

from app.utils.device_status import status_fields_from_snapshot


class TestDeviceStatusContract(unittest.TestCase):
    def test_connectivity_from_fsm_state(self):
        online_states = {"online", "recovering", "degraded", "checking", "collecting", "reloading"}
        for state in online_states:
            out = status_fields_from_snapshot({"fsm_state": state})
            self.assertEqual(out["connectivity"], "online", state)
            self.assertTrue(out["online_status"], state)

        offline_states = {"offline", "init", "", None}
        for state in offline_states:
            out = status_fields_from_snapshot({"fsm_state": state})
            self.assertEqual(out["connectivity"], "offline", str(state))

    def test_display_status_fallback(self):
        out = status_fields_from_snapshot({"fsm_state": "offline"})
        self.assertEqual(out["display_status"], "离线")

        out = status_fields_from_snapshot({"fsm_state": "online"})
        self.assertEqual(out["display_status"], "在线")

        out = status_fields_from_snapshot({"fsm_state": "checking"})
        self.assertEqual(out["display_status"], "检测中")

    def test_display_status_preserves_snapshot_value(self):
        out = status_fields_from_snapshot({"fsm_state": "offline", "status": "离线", "fsm_reason": "timeout"})
        self.assertEqual(out["display_status"], "离线")
        self.assertEqual(out["fsm_reason"], "timeout")


if __name__ == "__main__":
    unittest.main()

