"""Tests for fuel_alert.extract_suburb — parsing the suburb out of a NSW address.

This is the single source of truth shared by the price checker and
add_alert_locations.py, so both group/match suburbs identically.
"""

import unittest

from fuel_alert import extract_suburb


class TestExtractSuburb(unittest.TestCase):
    def test_title_case_suburb(self):
        self.assertEqual(
            extract_suburb("123 Pacific Hwy, Hornsby NSW 2077"), "Hornsby")

    def test_upper_case_suburb(self):
        self.assertEqual(
            extract_suburb("1 Bridge St, CHATSWOOD NSW 2067"), "Chatswood".upper())

    def test_multi_word_suburb(self):
        self.assertEqual(
            extract_suburb("5 Yarrara Rd, Pennant Hills NSW 2120"), "Pennant Hills")

    def test_suburb_with_unit_prefix(self):
        # The comma before the suburb is the boundary the parser relies on.
        self.assertEqual(
            extract_suburb("Shop 2, 290 Peats Ferry Rd, Hornsby NSW 2077"), "Hornsby")

    def test_unparseable_returns_none(self):
        self.assertIsNone(extract_suburb("Somewhere over the rainbow"))

    def test_blank_returns_none(self):
        self.assertIsNone(extract_suburb(""))

    def test_non_string_input(self):
        self.assertIsNone(extract_suburb(None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
