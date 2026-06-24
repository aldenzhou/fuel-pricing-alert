"""Tests for fuel_alert.split_field — parsing multi-value sheet cells.

These tests assume the default delimiter (a comma), which is what FIELD_DELIMITER
resolves to unless overridden in .env.
"""

import unittest

import fuel_alert
from fuel_alert import split_field


class TestSplitField(unittest.TestCase):
    def test_single_value(self):
        self.assertEqual(split_field("U91"), ["U91"])

    def test_multiple_values(self):
        # The real Fuel Types cell from the sheet.
        self.assertEqual(
            split_field("E10,U91,P95,P98,DL,PDL,LPG"),
            ["E10", "U91", "P95", "P98", "DL", "PDL", "LPG"],
        )

    def test_whitespace_is_trimmed(self):
        self.assertEqual(split_field(" E10 , U91 ,P95"), ["E10", "U91", "P95"])

    def test_blank_cell_is_empty_list(self):
        self.assertEqual(split_field(""), [])

    def test_whitespace_only_cell_is_empty_list(self):
        self.assertEqual(split_field("   "), [])

    def test_trailing_and_empty_segments_dropped(self):
        self.assertEqual(split_field("E10,,U91,"), ["E10", "U91"])

    def test_numeric_input_is_stringified(self):
        # gspread may hand back a single chat ID as an int.
        self.assertEqual(split_field(123456789), ["123456789"])

    def test_multiple_chat_ids(self):
        self.assertEqual(
            split_field("123456789,987654321"), ["123456789", "987654321"]
        )

    def test_respects_configured_delimiter(self):
        # split_field reads FIELD_DELIMITER at call time via the module global,
        # so changing it changes parsing without touching the function.
        original = fuel_alert.FIELD_DELIMITER
        try:
            fuel_alert.FIELD_DELIMITER = "||"
            self.assertEqual(split_field("U91||P98"), ["U91", "P98"])
        finally:
            fuel_alert.FIELD_DELIMITER = original


if __name__ == "__main__":
    unittest.main(verbosity=2)
