"""Tests for prepare_pin_codes.py, using a tiny made-up post office table.

How to run (from the project folder):
    python -m unittest discover -s python -v
"""

import unittest

import pandas as pd

import prepare_pin_codes as prepare


def post_offices(rows):
    """Build a table in the layout of the official file from (pincode, district, statename)."""
    return pd.DataFrame(rows, columns=["pincode", "district", "statename"])


class BuildLookupTest(unittest.TestCase):
    def lookup(self, rows):
        table = prepare.build_lookup(post_offices(rows))
        return {row.pin_code: (row.district, row.state) for row in table.itertuples()}

    def test_many_post_offices_become_one_row(self):
        result = self.lookup([
            ("600001", "CHENNAI", "TAMIL NADU"),
            ("600001", "CHENNAI", "TAMIL NADU"),
            ("600001", "CHENNAI", "TAMIL NADU"),
        ])
        self.assertEqual(result, {"600001": ("CHENNAI", "TAMIL NADU")})

    def test_letter_case_and_spaces_do_not_make_two_districts(self):
        result = self.lookup([
            ("625001", "Madurai", "Tamil Nadu"),
            ("625001", " MADURAI ", "TAMIL  NADU"),
        ])
        self.assertEqual(result, {"625001": ("MADURAI", "TAMIL NADU")})

    def test_two_districts_leave_the_district_empty_but_keep_the_state(self):
        result = self.lookup([
            ("641001", "COIMBATORE", "TAMIL NADU"),
            ("641001", "TIRUPPUR", "TAMIL NADU"),
        ])
        self.assertEqual(result, {"641001": ("", "TAMIL NADU")})

    def test_two_states_leave_the_state_empty(self):
        result = self.lookup([
            ("500001", "HYDERABAD", "TELANGANA"),
            ("500001", "HYDERABAD", "ANDHRA PRADESH"),
        ])
        self.assertEqual(result, {"500001": ("HYDERABAD", "")})

    def test_not_available_is_ignored_when_another_row_has_the_value(self):
        result = self.lookup([
            ("682001", "NA", "NA"),
            ("682001", "ERNAKULAM", "KERALA"),
        ])
        self.assertEqual(result, {"682001": ("ERNAKULAM", "KERALA")})

    def test_not_available_everywhere_stays_empty(self):
        self.assertEqual(self.lookup([("695001", "NA", "NA")]), {"695001": ("", "")})

    def test_bad_pin_codes_are_dropped(self):
        result = self.lookup([
            ("12345", "X", "Y"),
            ("012345", "X", "Y"),
            ("560001", "BENGALURU URBAN", "KARNATAKA"),
        ])
        self.assertEqual(list(result), ["560001"])


if __name__ == "__main__":
    unittest.main()
