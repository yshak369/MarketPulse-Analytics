"""Tests for clean_data.py: one test (or more) per cleaning rule.

The tiny fake tables come from the audit tests (make_tables): three
orders, W-1 (WhatsApp COD, Rs 650 recorded), W-2 (WhatsApp Prepaid,
no amount) and S-1 (Shopify Prepaid, Rs 500). Prices: CXE 500 Prepaid,
600 COD, cost 200. LP 150 Prepaid, 200 COD, cost 60.

The last test class runs on the synthetic database and is skipped on a
computer without it.

How to run (from the project folder):
    python -m unittest discover -s python -v
"""

import unittest

import numpy as np
import pandas as pd

import clean_data
import database
from test_audit_data_quality import make_tables


def clean(tables):
    return clean_data.clean_all(tables)


def row(table, order_id):
    return table.set_index("order_id").loc[order_id]


class RowRuleTest(unittest.TestCase):
    def setUp(self):
        self.tables = make_tables()
        self.orders = self.tables["orders"]

    def test_no_row_is_deleted(self):
        result = clean(self.tables)
        self.assertEqual(len(result["orders"]), 3)
        self.assertEqual(len(result["order_items"]), 4)
        self.assertEqual(len(result["customers"]), 2)

    def test_cancelled_order_is_kept_but_not_counted(self):
        self.orders.loc[2, "cancelled_at"] = pd.Timestamp("2025-03-03 15:00")
        orders = clean(self.tables)["orders"]
        self.assertEqual(row(orders, "S-1")["include_in_analysis"], False)
        self.assertEqual(row(orders, "S-1")["exclusion_reason"], "cancelled")
        self.assertTrue(orders.loc[orders["order_id"] != "S-1", "exclusion_reason"].isna().all())

    def test_possible_duplicate_is_counted_and_keeps_its_flag(self):
        self.orders.loc[1, "review_flags"] = "possible_duplicate"
        order = row(clean(self.tables)["orders"], "W-2")
        self.assertEqual(order["include_in_analysis"], True)
        self.assertEqual(order["review_flags"], "possible_duplicate")

    def test_payment_needs_review_is_counted_and_not_guessed(self):
        self.orders.loc[1, "payment_type"] = "needs_review"
        order = row(clean(self.tables)["orders"], "W-2")
        self.assertEqual((order["include_in_analysis"], order["payment_type"]), (True, "needs_review"))

    def test_the_raw_tables_are_not_changed(self):
        tables = make_tables()
        clean(tables)
        for name, table in make_tables().items():
            with self.subTest(table=name):
                pd.testing.assert_frame_equal(tables[name], table)


class PrivacyRuleTest(unittest.TestCase):
    def test_no_personal_column_in_any_clean_table(self):
        for name, table in clean(make_tables()).items():
            with self.subTest(table=name):
                self.assertFalse(set(clean_data.PERSONAL_COLUMNS) & set(table.columns))

    def test_facts_in_notes_are_kept_as_columns(self):
        tables = make_tables()
        tables["orders"]["notes"] = ["pin_code_override;second_phone=9000000009", None, "refunded_amount=250.5"]
        orders = clean(tables)["orders"]
        self.assertEqual(list(orders["district_from_override"]), [True, False, False])
        self.assertEqual(row(orders, "S-1")["refunded_amount"], 250.5)
        self.assertTrue(pd.isna(row(orders, "W-1")["refunded_amount"]))
        # The second phone number is nowhere in the clean tables.
        for table in clean(tables).values():
            self.assertFalse(table.astype(str).apply(lambda column: column.str.contains("9000000009")).any().any())


class PlaceRuleTest(unittest.TestCase):
    def test_place_names(self):
        tidy = clean_data.tidy_place_name
        self.assertEqual(tidy("  ERNAKULAM "), "Ernakulam")
        self.assertEqual(tidy("Ernakulam"), "Ernakulam")
        self.assertEqual(tidy("bengaluru   urban"), "Bengaluru Urban")
        self.assertEqual(tidy("ANDAMAN AND NICOBAR ISLANDS"), "Andaman and Nicobar Islands")
        self.assertEqual(tidy("Y.S.R."), "Y.S.R.")
        for empty in ("", "   ", None, np.nan):
            self.assertTrue(pd.isna(tidy(empty)))

    def test_one_district_is_written_one_way(self):
        tables = make_tables()
        tables["orders"]["district_city"] = ["CHENNAI", "chennai", "Chennai "]
        self.assertEqual(set(clean(tables)["orders"]["district_city"]), {"Chennai"})


class CustomerRuleTest(unittest.TestCase):
    def test_missing_phone_means_customer_unknown(self):
        tables = make_tables()
        tables["orders"].loc[1, "review_flags"] = "missing_phone"
        orders = clean(tables)["orders"]
        self.assertEqual(row(orders, "W-2")["customer_identified"], False)
        self.assertTrue(pd.isna(row(orders, "W-2")["customer_order_number"]))
        customers = clean(tables)["customers"].set_index("customer_id")
        self.assertEqual(customers.loc["C-2", "customer_identified"], False)

    def test_order_numbers_and_repeat_orders(self):
        orders = clean(make_tables())["orders"]   # C-1 ordered W-1 (1 March) and S-1 (3 March)
        self.assertEqual(row(orders, "W-1")["customer_order_number"], 1)
        self.assertEqual(row(orders, "S-1")["customer_order_number"], 2)
        self.assertEqual(list(orders["is_repeat_order"]), [False, False, True])
        customers = clean(make_tables())["customers"].set_index("customer_id")
        self.assertEqual(customers.loc["C-1", "orders_counted"], 2)
        self.assertEqual(customers.loc["C-1", "is_repeat_customer"], True)
        self.assertEqual(customers.loc["C-2", "is_repeat_customer"], False)
        self.assertEqual(customers.loc["C-1", "first_order_date"], pd.Timestamp("2025-03-01"))

    def test_a_cancelled_order_is_not_numbered(self):
        tables = make_tables()
        tables["orders"].loc[0, "cancelled_at"] = pd.Timestamp("2025-03-01 12:00")
        orders = clean(tables)["orders"]
        self.assertTrue(pd.isna(row(orders, "W-1")["customer_order_number"]))
        self.assertEqual(row(orders, "S-1")["customer_order_number"], 1)   # now the first counted order
        customers = clean(tables)["customers"].set_index("customer_id")
        self.assertEqual(customers.loc["C-1", "orders_counted"], 1)


class ProductRuleTest(unittest.TestCase):
    def test_units_and_lines(self):
        tables = make_tables()
        tables["order_items"].loc[0, "quantity"] = 3
        orders = clean(tables)["orders"]
        self.assertEqual((row(orders, "W-1")["units"], row(orders, "W-1")["product_lines"]), (4, 2))

    def test_defaulted_product_is_counted_and_marked(self):
        tables = make_tables()
        tables["order_items"].loc[2, "product_defaulted"] = True     # W-2: no product line written
        result = clean(tables)
        self.assertEqual(row(result["orders"], "W-2")["product_defaulted"], True)
        self.assertEqual(row(result["orders"], "W-1")["product_defaulted"], False)
        items = result["order_items"]
        self.assertEqual(items.loc[2, "include_in_analysis"], True)
        self.assertEqual(items.loc[2, "product_name"], "Cream")


class AmountRuleTest(unittest.TestCase):
    def setUp(self):
        self.tables = make_tables()
        self.orders = self.tables["orders"]
        self.items = self.tables["order_items"]

    def order(self, order_id):
        return row(clean(self.tables)["orders"], order_id)

    def test_recorded_amount_is_used_and_never_changed(self):
        order = self.order("W-1")
        self.assertEqual((order["order_amount"], order["amount_reliable"]), (650.0, True))
        self.assertEqual((order["order_value"], order["value_basis"]), (650.0, "recorded"))
        self.assertEqual(order["estimated_order_value"], 800.0)   # 600 + 200 at COD prices: kept apart

    def test_prepaid_whatsapp_order_is_estimated_at_the_prepaid_price(self):
        order = self.order("W-2")
        self.assertTrue(pd.isna(order["order_amount"]))
        self.assertEqual((order["order_value"], order["value_basis"]), (500.0, "estimated"))

    def test_cod_order_without_any_amount_is_estimated_at_the_cod_price(self):
        self.orders.loc[0, ["order_amount", "amount_basis", "review_flags"]] = [np.nan, "unknown", "cod_amount_missing"]
        self.items.loc[[0, 1], "line_amount"] = np.nan
        order = self.order("W-1")
        self.assertEqual((order["order_value"], order["value_basis"]), (800.0, "estimated"))

    def test_partial_cod_amounts_are_never_estimated(self):
        self.orders.loc[0, ["order_amount", "amount_basis", "review_flags"]] = [np.nan, "unknown", "cod_amount_partial"]
        self.items.loc[1, "line_amount"] = np.nan
        result = clean(self.tables)
        order = row(result["orders"], "W-1")
        self.assertTrue(pd.isna(order["estimated_order_value"]))
        self.assertEqual(order["value_basis"], "unknown")
        lines = result["order_items"]
        self.assertTrue(lines.loc[lines["order_id"] == "W-1", "estimated_line_value"].isna().all())

    def test_flagged_amount_is_not_trusted(self):
        self.orders.loc[0, "review_flags"] = "amount_out_of_range"
        order = self.order("W-1")
        self.assertEqual((order["order_amount"], order["amount_reliable"]), (650.0, False))
        self.assertEqual((order["order_value"], order["value_basis"]), (800.0, "estimated"))

    def test_shopify_order_is_estimated_at_the_normal_price(self):
        self.assertEqual(self.order("S-1")["estimated_order_value"], 500.0)

    def test_needs_review_payment_has_no_estimate(self):
        self.orders.loc[1, "payment_type"] = "needs_review"
        order = self.order("W-2")
        self.assertTrue(pd.isna(order["estimated_order_value"]))
        self.assertEqual(order["value_basis"], "unknown")

    def test_missing_price_makes_the_estimate_unknown(self):
        self.tables["products"].loc[1, "cod_price"] = np.nan   # LP has no COD price
        self.orders.loc[0, "review_flags"] = "cod_amount_missing"
        order = self.order("W-1")
        self.assertTrue(pd.isna(order["estimated_order_value"]))
        self.assertEqual(order["value_basis"], "unknown")

    def test_estimated_cost(self):
        self.assertEqual(self.order("W-1")["estimated_order_cost"], 260.0)   # 200 + 60

    def test_line_estimates(self):
        lines = clean(self.tables)["order_items"]
        self.assertEqual(list(lines["price_used"]), [600.0, 200.0, 500.0, 500.0])
        self.assertEqual(list(lines["line_amount"].fillna(-1)), [500.0, 150.0, -1, 500.0])   # recorded, unchanged


class DateRuleTest(unittest.TestCase):
    def test_date_parts(self):
        orders = clean(make_tables())["orders"]
        order = row(orders, "W-1")   # Saturday 1 March 2025, 10:00
        self.assertEqual(order["order_date"], pd.Timestamp("2025-03-01"))
        self.assertEqual(order["order_month"], pd.Timestamp("2025-03-01"))
        self.assertEqual(order["week_start"], pd.Timestamp("2025-02-24"))   # the Monday before
        self.assertEqual((order["weekday"], order["hour"]), ("Saturday", 10))


class SyntheticDatabaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            engine = database.connect(database.SYNTHETIC_DATABASE, ask_password=False)
        except database.ConnectionProblem as problem:
            raise unittest.SkipTest(f"the synthetic database is not available here: {problem}")
        try:
            cls.raw = database.read_tables(engine)
        finally:
            engine.dispose()
        cls.result = clean_data.clean_all(cls.raw)
        cls.orders = cls.result["orders"]

    def test_every_row_is_kept(self):
        for name in ("orders", "order_items", "customers"):
            with self.subTest(table=name):
                self.assertEqual(len(self.result[name]), len(self.raw[name]))

    def test_counted_and_not_counted(self):
        self.assertEqual(int((~self.orders["include_in_analysis"]).sum()), 20)    # the cancelled orders
        self.assertEqual(set(self.orders["exclusion_reason"].dropna()), {"cancelled"})

    def test_value_basis(self):
        counts = self.orders["value_basis"].value_counts().to_dict()
        # 1,960 orders have a recorded amount. Of the 952 without one, the
        # 12 with payment "needs_review" stay unknown.
        self.assertEqual(counts, {"recorded": 1960, "estimated": 940, "unknown": 12})

    def test_recorded_amounts_are_unchanged(self):
        pd.testing.assert_series_equal(self.orders["order_amount"], self.raw["orders"]["order_amount"])

    def test_no_personal_column(self):
        for name, table in self.result.items():
            with self.subTest(table=name):
                self.assertFalse(set(clean_data.PERSONAL_COLUMNS) & set(table.columns))


if __name__ == "__main__":
    unittest.main()
