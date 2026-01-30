import unittest

from app.workers.config_push.worker import _is_job_final


class TestConfigPushJobFinal(unittest.TestCase):
    def test_finished_at_makes_final(self):
        self.assertTrue(_is_job_final("running", finished_at="2026-01-01T00:00:00Z"))

    def test_status_final_set(self):
        for s in ["success", "failed", "partial", "canceled"]:
            self.assertTrue(_is_job_final(s, finished_at=None))

    def test_status_non_final(self):
        for s in ["pending", "running", "canceling", ""]:
            self.assertFalse(_is_job_final(s, finished_at=None))
