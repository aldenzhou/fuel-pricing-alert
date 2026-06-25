"""Tests for fuel_alert.parse_alert_threshold.

Converts the optional 'Alert Threshold ($/L)' sheet cell (dollars per litre)
into a threshold in cents per litre, or None when no valid threshold is set.
"""

import logging
import unittest

from fuel_alert import logger, parse_alert_threshold

# parse_alert_threshold logs warnings for invalid input via the 'fuel_alert'
# logger. The tests don't configure logging, so attach a NullHandler to keep
# those warnings from falling back to Python's stderr handler and cluttering the
# test output. The dedicated logging test below uses assertLogs, which captures
# records regardless of this handler.
logger.addHandler(logging.NullHandler())


def parse_quiet(raw, station="TestStation"):
    """Call parse_alert_threshold (warnings are swallowed by the NullHandler)."""
    return parse_alert_threshold(raw, station)


class TestParseAlertThreshold(unittest.TestCase):
    # --- "no threshold" cases -> None (alert on any change) ---
    def test_blank_is_none(self):
        self.assertIsNone(parse_alert_threshold("", "S"))

    def test_whitespace_is_none(self):
        self.assertIsNone(parse_alert_threshold("   ", "S"))

    def test_none_value_is_none(self):
        self.assertIsNone(parse_quiet(None))

    # --- valid conversions: dollars/L -> cents/L (x100) ---
    def test_dollars_converted_to_cents(self):
        self.assertEqual(parse_alert_threshold("0.10", "S"), 10.0)

    def test_real_sheet_value_0_1(self):
        # Exactly what station 2608 has in the sheet.
        self.assertEqual(parse_alert_threshold("0.1", "Ampol"), 10.0)

    def test_small_threshold(self):
        self.assertEqual(parse_alert_threshold("0.05", "S"), 5.0)

    def test_integer_value(self):
        self.assertEqual(parse_alert_threshold("1", "S"), 100.0)

    def test_zero_is_zero_cents(self):
        self.assertEqual(parse_alert_threshold("0", "S"), 0.0)

    def test_numeric_type_input(self):
        # gspread can hand back a float rather than a string.
        self.assertEqual(parse_alert_threshold(0.1, "S"), 10.0)

    # --- invalid values -> None, with a logged warning ---
    def test_invalid_string_is_none(self):
        self.assertIsNone(parse_quiet("abc"))

    def test_negative_is_none(self):
        self.assertIsNone(parse_quiet("-0.10"))

    def test_invalid_value_is_logged(self):
        with self.assertLogs(logger, level="WARNING") as cm:
            parse_alert_threshold("abc", "Ampol Foodary Thornleigh")
        output = "\n".join(cm.output)
        self.assertIn("Invalid", output)
        self.assertIn("Ampol Foodary Thornleigh", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
