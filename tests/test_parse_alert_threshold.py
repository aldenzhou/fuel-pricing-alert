"""Tests for fuel_alert.parse_alert_threshold.

Converts the optional 'Alert Threshold ($/L)' sheet cell (dollars per litre)
into a threshold in cents per litre, or None when no valid threshold is set.
"""

import io
import unittest
from contextlib import redirect_stdout

from fuel_alert import parse_alert_threshold


def parse_quiet(raw, station="TestStation"):
    """Call parse_alert_threshold while swallowing its stdout logging."""
    with redirect_stdout(io.StringIO()):
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
        buf = io.StringIO()
        with redirect_stdout(buf):
            parse_alert_threshold("abc", "Ampol Foodary Thornleigh")
        self.assertIn("Invalid", buf.getvalue())
        self.assertIn("Ampol Foodary Thornleigh", buf.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
