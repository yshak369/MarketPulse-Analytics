"""Tests for database.py.

Most of these tests need the marketpulse_synthetic database on this
computer. On a computer without it they are skipped, and all the other
tests still run.

How to run (from the project folder):
    python -m unittest discover -s python -v
"""

import unittest
from pathlib import Path
from unittest import mock

import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

import database

SYNTHETIC = Path(__file__).resolve().parent.parent / "data" / "synthetic"


def read_file(table):
    """The CSV file a synthetic table was loaded from."""
    return pd.read_csv(SYNTHETIC / f"synthetic_{table}.csv")


class SyntheticDatabaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.engine = database.connect(database.SYNTHETIC_DATABASE, ask_password=False)
        except database.ConnectionProblem as problem:
            raise unittest.SkipTest(f"the synthetic database is not available here: {problem}")
        cls.tables = database.read_tables(cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_all_eight_tables_are_read(self):
        self.assertEqual(list(self.tables), database.TABLE_NAMES)
        self.assertEqual(len(self.tables), 8)

    def test_every_table_has_as_many_rows_as_its_file(self):
        for name, table in self.tables.items():
            with self.subTest(table=name):
                self.assertEqual(len(table), len(read_file(name)))
                self.assertGreater(len(table), 0)

    def test_products_hold_the_same_values_as_the_file(self):
        from_database = self.tables["products"].sort_values("product_code").reset_index(drop=True)
        from_file = read_file("products").sort_values("product_code").reset_index(drop=True)
        pd.testing.assert_frame_equal(from_database, from_file, check_dtype=False)

    def test_dates_and_numbers_arrive_with_the_right_types(self):
        orders = self.tables["orders"]
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(orders["order_datetime"]))
        self.assertTrue(pd.api.types.is_float_dtype(orders["order_amount"]))
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(self.tables["ad_performance"]["report_date"]))
        self.assertTrue(pd.api.types.is_bool_dtype(self.tables["order_items"]["product_defaulted"]))

    def test_empty_database_values_become_missing_values(self):
        missing_in_database = int(self.tables["orders"]["order_amount"].isna().sum())
        missing_in_file = int(read_file("orders")["order_amount"].isna().sum())
        self.assertEqual(missing_in_database, missing_in_file)
        self.assertGreater(missing_in_database, 0)

    def test_total_ad_spend_is_the_same_as_in_the_file(self):
        in_database = self.tables["ad_performance"]["amount_spent_inr"].sum()
        in_file = read_file("ad_performance")["amount_spent_inr"].sum()
        self.assertAlmostEqual(in_database, in_file, places=2)

    def test_connection_is_read_only_by_default(self):
        # The connection is closed without a commit, so nothing could stay
        # in the database even if the change were accepted.
        with self.engine.connect() as connection:
            with self.assertRaisesRegex(DBAPIError, "read-only transaction"):
                connection.execute(text("CREATE TABLE read_only_check (x integer)"))

    def test_missing_schema_gives_an_error(self):
        with self.assertRaises(ValueError):
            database.read_table(self.engine, "products", schema="no_such_schema")


class ConnectionProblemTest(unittest.TestCase):
    def test_database_without_a_password_is_not_opened_and_nothing_is_asked(self):
        # A made-up database name: it is not in the password file.
        with self.assertRaises(database.ConnectionProblem) as caught:
            database.connect("marketpulse_no_such_database", ask_password=False)
        self.assertIn("marketpulse_no_such_database", str(caught.exception))

    def test_nothing_is_asked_when_nobody_can_type(self):
        # No real connection is made: the answer of the database is imitated.
        with mock.patch.object(database, "try_to_open", return_value="fe_sendauth: no password supplied"), \
             mock.patch.object(database, "a_person_can_type", return_value=False), \
             mock.patch.object(database.getpass, "getpass", side_effect=AssertionError("must not ask")):
            with self.assertRaisesRegex(database.ConnectionProblem, "cannot be asked for here"):
                database.connect("marketpulse_no_such_database")

    def test_password_is_asked_once_and_never_shown(self):
        # First answer: a password is needed. Second answer: the database opens.
        answers = iter(["fe_sendauth: no password supplied", None])
        with mock.patch.object(database, "try_to_open", side_effect=lambda engine: next(answers)), \
             mock.patch.object(database, "a_person_can_type", return_value=True), \
             mock.patch.object(database.getpass, "getpass", return_value="made-up-password") as ask:
            engine = database.connect("marketpulse_no_such_database")
        ask.assert_called_once()
        self.assertEqual(engine.url.password, "made-up-password")   # kept in memory for the connection
        self.assertNotIn("made-up-password", str(engine.url))       # hidden whenever the address is printed
        self.assertNotIn("made-up-password", repr(engine))
        engine.dispose()

    def test_wrong_password_gives_a_clear_message(self):
        answers = iter(["fe_sendauth: no password supplied", "FATAL:  password authentication failed"])
        with mock.patch.object(database, "try_to_open", side_effect=lambda engine: next(answers)), \
             mock.patch.object(database, "a_person_can_type", return_value=True), \
             mock.patch.object(database.getpass, "getpass", return_value="made-up-password"):
            with self.assertRaisesRegex(database.ConnectionProblem, "password authentication failed") as caught:
                database.connect("marketpulse_no_such_database")
        self.assertNotIn("made-up-password", str(caught.exception))

    def test_every_database_is_labelled(self):
        self.assertIn("SYNTHETIC", database.kind_of_data("marketpulse_synthetic"))
        self.assertIn("PRIVATE", database.kind_of_data("marketpulse_private"))
        self.assertIn("PRIVATE", database.kind_of_data("anything_else"))


if __name__ == "__main__":
    unittest.main()
