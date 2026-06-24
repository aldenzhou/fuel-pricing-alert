"""Tests for fuel_alert.should_send_alert — the alert decision.

Given the previous and current price (c/L) and a threshold (c/L or None),
decide whether a Telegram alert should be sent.
"""

import unittest

from fuel_alert import should_send_alert


class TestShouldSendAlert(unittest.TestCase):
    # --- No threshold (blank cell -> None): alert on any change ---
    def test_no_threshold_unchanged_no_alert(self):
        self.assertFalse(should_send_alert(189.9, 189.9, None))

    def test_no_threshold_any_increase_alerts(self):
        self.assertTrue(should_send_alert(189.9, 190.0, None))

    def test_no_threshold_any_drop_alerts(self):
        self.assertTrue(should_send_alert(189.9, 189.8, None))

    # --- With a 10 c/L threshold (sheet value 0.1) ---
    def test_threshold_unchanged_no_alert(self):
        self.assertFalse(should_send_alert(189.9, 189.9, 10.0))

    def test_threshold_below_no_alert(self):
        self.assertFalse(should_send_alert(189.9, 195.0, 10.0))  # 5.1 c/L

    def test_threshold_just_below_no_alert(self):
        self.assertFalse(should_send_alert(189.9, 199.8, 10.0))  # 9.9 c/L

    def test_threshold_exact_boundary_alerts(self):
        self.assertTrue(should_send_alert(189.9, 199.9, 10.0))   # 10.0 c/L

    def test_threshold_above_alerts(self):
        self.assertTrue(should_send_alert(189.9, 205.0, 10.0))   # 15.1 c/L

    def test_threshold_applies_to_drops_too(self):
        self.assertTrue(should_send_alert(199.9, 189.9, 10.0))   # -10.0 c/L

    # --- Zero threshold behaves like "any change" ---
    def test_zero_threshold_any_change_alerts(self):
        self.assertTrue(should_send_alert(189.9, 190.0, 0.0))

    def test_zero_threshold_unchanged_no_alert(self):
        self.assertFalse(should_send_alert(189.9, 189.9, 0.0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
