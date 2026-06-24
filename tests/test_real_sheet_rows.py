"""End-to-end tests over the two configured stations in the Alert-Locations tab.

Mirrors the real sheet data so the pieces are exercised together:

  Station 2608  Ampol Foodary Thornleigh       fuels: E10,U91,P95,P98,DL,PDL,LPG  threshold: 0.1
  Station 2707  Shell Reddy Express Queanbeyan  fuels: E10,U91,P95,P98,DL,PDL,LPG  threshold: (blank)
"""

import unittest

from fuel_alert import parse_alert_threshold, should_send_alert, split_field

EXPECTED_FUELS = ["E10", "U91", "P95", "P98", "DL", "PDL", "LPG"]


class TestStation2608(unittest.TestCase):
    """Threshold 0.1 -> only alert on moves of 10 c/L or more."""

    def test_fuel_types_parse(self):
        self.assertEqual(split_field("E10,U91,P95,P98,DL,PDL,LPG"), EXPECTED_FUELS)

    def test_threshold_parses_to_10_cents(self):
        self.assertEqual(parse_alert_threshold("0.1", "Ampol Foodary Thornleigh"), 10.0)

    def test_small_move_does_not_alert(self):
        thr = parse_alert_threshold("0.1", "Ampol Foodary Thornleigh")
        self.assertFalse(should_send_alert(189.9, 195.0, thr))  # 5.1 c/L

    def test_large_move_alerts(self):
        thr = parse_alert_threshold("0.1", "Ampol Foodary Thornleigh")
        self.assertTrue(should_send_alert(189.9, 199.9, thr))   # 10.0 c/L


class TestStation2707(unittest.TestCase):
    """Blank threshold -> alert on any change."""

    def test_fuel_types_parse(self):
        self.assertEqual(split_field("E10,U91,P95,P98,DL,PDL,LPG"), EXPECTED_FUELS)

    def test_blank_threshold_is_none(self):
        self.assertIsNone(parse_alert_threshold("", "Shell Reddy Express Queanbeyan"))

    def test_unchanged_price_no_alert(self):
        thr = parse_alert_threshold("", "Shell Reddy Express Queanbeyan")
        self.assertFalse(should_send_alert(189.9, 189.9, thr))

    def test_any_change_alerts(self):
        thr = parse_alert_threshold("", "Shell Reddy Express Queanbeyan")
        self.assertTrue(should_send_alert(189.9, 190.0, thr))   # +0.1 c/L


if __name__ == "__main__":
    unittest.main(verbosity=2)
