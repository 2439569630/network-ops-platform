import unittest

from app.drivers.models.status import DeviceStatus


class TestDeviceStatusFsm(unittest.TestCase):
    def test_disallow_back_to_init(self):
        st = DeviceStatus(fsm_state="online")
        changed = st.set_fsm("init", "manual_reset")
        self.assertFalse(changed)
        self.assertEqual(st.fsm_state, "online")

    def test_disallow_unknown_state(self):
        st = DeviceStatus(fsm_state="online")
        changed = st.set_fsm("some_new_state", "x")
        self.assertFalse(changed)
        self.assertEqual(st.fsm_state, "online")

    def test_allow_offline_from_any_state(self):
        for start in ("init", "checking", "collecting", "online", "degraded", "recovering", "reloading"):
            st = DeviceStatus(fsm_state=start)
            changed = st.set_fsm("offline", "test")
            self.assertTrue(changed, start)
            self.assertEqual(st.fsm_state, "offline", start)

    def test_offline_to_online_when_recovery_threshold_is_one(self):
        st = DeviceStatus(fsm_state="offline", recovery_success_threshold=1)
        changed = st.record_success()
        self.assertTrue(changed)
        self.assertEqual(st.fsm_state, "online")

    def test_online_to_offline_by_failure_threshold(self):
        st = DeviceStatus(fsm_state="online", offline_fail_threshold=2)
        changed1 = st.record_failure("timeout")
        self.assertTrue(changed1)
        self.assertEqual(st.fsm_state, "degraded")
        changed2 = st.record_failure("timeout")
        self.assertTrue(changed2)
        self.assertEqual(st.fsm_state, "offline")

    def test_offline_to_recovering_then_online(self):
        st = DeviceStatus(fsm_state="offline", recovery_success_threshold=2)
        changed1 = st.record_success()
        self.assertTrue(changed1)
        self.assertEqual(st.fsm_state, "recovering")
        changed2 = st.record_success()
        self.assertTrue(changed2)
        self.assertEqual(st.fsm_state, "online")


if __name__ == "__main__":
    unittest.main()
