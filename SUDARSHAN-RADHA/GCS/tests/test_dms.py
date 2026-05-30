"""Unit tests for DeadManSwitch."""
import time
import sys
import os
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.modules.setdefault("tkinter", MagicMock())
sys.modules.setdefault("tkinter.ttk", MagicMock())
sys.modules.setdefault("tkinter.messagebox", MagicMock())

from radha_gcs import DeadManSwitch  # noqa: E402


class TestDeadManSwitch(unittest.TestCase):

    def test_remaining_starts_near_timeout(self):
        cb = MagicMock()
        dms = DeadManSwitch(30.0, cb)
        dms._active = False  # don't start background thread
        dms._last   = time.time()
        self.assertAlmostEqual(dms.remaining(), 30.0, delta=0.2)

    def test_remaining_decreases_over_time(self):
        cb = MagicMock()
        dms = DeadManSwitch(10.0, cb)
        dms._last = time.time() - 5.0
        self.assertAlmostEqual(dms.remaining(), 5.0, delta=0.3)

    def test_remaining_never_below_zero(self):
        cb = MagicMock()
        dms = DeadManSwitch(5.0, cb)
        dms._last = time.time() - 100.0
        self.assertEqual(dms.remaining(), 0.0)

    def test_reset_restores_remaining(self):
        cb = MagicMock()
        dms = DeadManSwitch(30.0, cb)
        dms._last = time.time() - 25.0
        self.assertAlmostEqual(dms.remaining(), 5.0, delta=0.3)
        dms.reset()
        self.assertAlmostEqual(dms.remaining(), 30.0, delta=0.3)

    def test_callback_fires_after_timeout(self):
        cb = MagicMock()
        # Timeout of 0.05s; the _run loop sleeps 1s, so we need to wait >1s
        dms = DeadManSwitch(0.05, cb)
        dms.start()
        time.sleep(1.3)
        dms.stop()
        cb.assert_called()

    def test_callback_not_fired_before_timeout(self):
        cb = MagicMock()
        dms = DeadManSwitch(60.0, cb)
        dms.start()
        time.sleep(0.1)
        dms.stop()
        cb.assert_not_called()

    def test_stop_prevents_further_callbacks(self):
        cb = MagicMock()
        dms = DeadManSwitch(0.05, cb)
        dms.start()
        time.sleep(0.1)
        dms.stop()
        count_at_stop = cb.call_count
        time.sleep(0.2)
        self.assertEqual(cb.call_count, count_at_stop)


if __name__ == "__main__":
    unittest.main()
