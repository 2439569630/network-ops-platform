import unittest

from app.workers.monitor.manager import normalize_period_seconds


class TestNormalizePeriodSeconds(unittest.TestCase):
    def test_minus_one_disables(self):
        self.assertEqual(normalize_period_seconds(-1, default_seconds=60.0), 0.0)

    def test_zero_uses_default(self):
        self.assertEqual(normalize_period_seconds(0, default_seconds=60.0), 60.0)

    def test_none_uses_default(self):
        self.assertEqual(normalize_period_seconds(None, default_seconds=60.0), 60.0)

    def test_positive_clamps_min(self):
        self.assertEqual(normalize_period_seconds(0.1, default_seconds=60.0), 1.0)
        self.assertEqual(normalize_period_seconds(5, default_seconds=60.0), 5.0)


if __name__ == "__main__":
    unittest.main()

