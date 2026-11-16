"""Tests for audit_data_quality.py.

Most tests use tiny hand-made tables: first a clean set, where no check
may find a problem, then one planted problem at a time, which its check
must find. The last test class runs the audit on the synthetic database
and is skipped on a computer without it.

How to run (from the project folder):
    python -m unittest discover -s python -v
"""

import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import audit_data_quality as audit_module
import database

SYNTHETIC = Path(__file__).resolve().parent.parent / "data" / "synthetic"
TODAY = pd.Timestamp("2026-01-01")
PERIOD = ("2025-03-01", "2025-03-31")

# Checks that must find nothing in clean tables. Facts such as
# "orders with no amount" are left out, because clean data has them too.
PROBLEM_CHECKS = [
    ("orders", "duplicate order_id"),
    ("customers", "duplicate phone"),
    ("orders", "unexpected payment_type value"),
    ("orders", "order_datetime in the future"),
    ("orders", "order_datetime outside the period"),
    ("orders", "cancelled before ordered"),
    ("shipments", "delivered before ordered"),
    ("orders", "orders without items"),
    ("orders", "orders without a shipment"),
    ("order_items", "items of unknown orders"),
    ("order_items", "items of unknown products"),
    ("shipments", "shipments of cancelled orders"),
    ("customers", "customers without orders"),
    ("ad_campaigns", "campaigns without any day"),
    ("orders", "amount rule broken"),
    ("orders", "COD lines do not add up to the order amount"),
    ("shipments", "COD received above the amount to collect"),
    ("shipments", "money received on a non-COD order"),
    ("ad_performance", "reach above impressions"),
    ("ad_performance", "link clicks above all clicks"),
    ("ad_performance", "results without an indicator"),
]


def make_tables():
    """Three fake orders with everything in order."""
    return {
        "products": pd.DataFrame({
            "product_code": ["CXE", "LP"], "product_name": ["Cream", "Lip balm"],
            "selling_price": [500.0, 150.0], "unit_cost": [200.0, 60.0]}),
        "product_aliases": pd.DataFrame({
            "alias": ["cxe", "lp"], "source": ["whatsapp", "whatsapp"], "product_code": ["CXE", "LP"]}),
        "customers": pd.DataFrame({
            "customer_id": ["C-1", "C-2"], "customer_name": ["Test One", "Test Two"],
            "phone": ["9000000001", "9000000002"]}),
        "orders": pd.DataFrame({
            "order_id": ["W-1", "W-2", "S-1"], "customer_id": ["C-1", "C-2", "C-1"],
            "order_datetime": pd.to_datetime(["2025-03-01 10:00", "2025-03-02 11:00", "2025-03-03 12:00"]),
            "sales_channel": ["whatsapp", "whatsapp", "shopify"], "payment_type": ["cod", "prepaid", "prepaid"],
            "address": ["1 Test Street"] * 3, "district_city": ["Chennai"] * 3, "state": ["Tamil Nadu"] * 3,
            "pin_code": ["600001"] * 3, "order_amount": [650.0, np.nan, 500.0],
            "amount_basis": ["cod_collectible", "unknown", "shopify_total"],
            "financial_status": [None, None, "paid"], "fulfillment_status": [None, None, "fulfilled"],
            "cancelled_at": pd.to_datetime([None, None, None]),
            "review_flags": [None, None, None], "notes": [None, None, None]}),
        "order_items": pd.DataFrame({
            "order_item_id": [1, 2, 3, 4], "order_id": ["W-1", "W-1", "W-2", "S-1"],
            "product_code": ["CXE", "LP", "CXE", "CXE"], "quantity": [1, 1, 1, 1],
            "line_amount": [500.0, 150.0, np.nan, 500.0], "product_defaulted": [False] * 4}),
        "shipments": pd.DataFrame({
            "shipment_id": ["SH-1", "SH-2", "SH-3"], "order_id": ["W-1", "W-2", "S-1"],
            "courier": ["delhivery", "speed_post", "speed_post"], "delivery_status": ["delivered"] * 3,
            "delivered_date": pd.to_datetime(["2025-03-05", "2025-03-06", "2025-03-07"]),
            "cod_amount_received": [650.0, np.nan, np.nan], "shipping_cost": [80.0, 60.0, 60.0]}),
        "ad_campaigns": pd.DataFrame({
            "campaign_id": ["120001"], "campaign_name": ["Test campaign"], "delivery_status": ["active"],
            "attribution_setting": ["7-day click or 1-day view"], "budget_amount": [500.0],
            "budget_type": ["daily"], "end_date": pd.to_datetime([None])}),
        "ad_performance": pd.DataFrame({
            "campaign_id": ["120001", "120001"], "report_date": pd.to_datetime(["2025-03-01", "2025-03-02"]),
            "amount_spent_inr": [450.0, 430.0], "impressions": [4000, 3800], "reach": [3500, 3300],
            "link_clicks": [60, 55], "clicks_all": [100, 90], "landing_page_views": [np.nan, np.nan],
            "results": [20, 18], "result_indicator": ["actions:messaging"] * 2}),
    }


def found(report, table, check):
    """rows_found of one check, or 0 when the check is not in the report."""
    rows = report[(report["table"] == table) & (report["check"] == check)]
    return int(rows["rows_found"].iloc[0]) if len(rows) else 0


def run(tables):
    return audit_module.audit(tables, today=TODAY, period=PERIOD)


class CleanTablesTest(unittest.TestCase):
    def test_clean_tables_have_no_problems(self):
        report = run(make_tables())
        for table, check in PROBLEM_CHECKS:
            with self.subTest(check=check):
                self.assertIn(check, set(report.loc[report["table"] == table, "check"]))
                self.assertEqual(found(report, table, check), 0)

    def test_report_layout(self):
        report = run(make_tables())
        self.assertEqual(list(report.columns), audit_module.REPORT_COLUMNS)
        self.assertTrue((report["rows_found"] <= report["rows_checked"]).all())

    def test_facts_are_counted(self):
        report = run(make_tables())
        self.assertEqual(found(report, "orders", "orders with no amount"), 1)
        self.assertEqual(found(report, "orders", "missing financial_status"), 2)

    def test_the_audit_changes_nothing(self):
        tables = make_tables()
        run(tables)
        for name, table in make_tables().items():
            with self.subTest(table=name):
                pd.testing.assert_frame_equal(tables[name], table)

    def test_without_a_period_that_check_is_left_out(self):
        report = audit_module.audit(make_tables(), today=TODAY)
        self.assertNotIn("order_datetime outside the period", set(report["check"]))


class PlantedProblemTest(unittest.TestCase):
    def setUp(self):
        self.tables = make_tables()
        self.orders = self.tables["orders"]

    def assertFinds(self, table, check, expected=1):
        self.assertEqual(found(run(self.tables), table, check), expected)

    def test_blank_text_counts_as_missing(self):
        self.orders.loc[0, "district_city"] = "   "
        self.orders.loc[1, "district_city"] = None
        self.assertFinds("orders", "missing district_city", 2)

    def test_duplicate_key(self):
        self.tables["orders"] = pd.concat([self.orders, self.orders.iloc[[0]]], ignore_index=True)
        self.assertFinds("orders", "duplicate order_id")

    def test_duplicate_phone(self):
        self.tables["customers"].loc[1, "phone"] = "9000000001"
        self.assertFinds("customers", "duplicate phone")

    def test_review_flags_are_split_and_counted(self):
        self.orders["review_flags"] = ["unknown_product;missing_phone", "missing_phone", None]
        report = run(self.tables)
        self.assertEqual(found(report, "orders", "flag missing_phone"), 2)
        self.assertEqual(found(report, "orders", "flag unknown_product"), 1)
        self.assertEqual(found(report, "orders", "orders with any review flag"), 2)

    def test_a_flag_written_twice_counts_once(self):
        self.orders.loc[0, "review_flags"] = "missing_phone;missing_phone"
        self.assertFinds("orders", "flag missing_phone")

    def test_unexpected_code(self):
        self.orders.loc[0, "payment_type"] = "upi"
        self.assertFinds("orders", "unexpected payment_type value")

    def test_date_in_the_future(self):
        self.orders.loc[0, "order_datetime"] = pd.Timestamp("2099-01-01")
        self.assertFinds("orders", "order_datetime in the future")

    def test_date_outside_the_period(self):
        self.orders.loc[0, "order_datetime"] = pd.Timestamp("2025-02-28 23:59")
        self.orders.loc[1, "order_datetime"] = pd.Timestamp("2025-03-31 23:59")   # last day: inside
        self.assertFinds("orders", "order_datetime outside the period")

    def test_cancelled_before_ordered(self):
        self.orders.loc[2, "cancelled_at"] = pd.Timestamp("2025-03-03 09:00")
        self.assertFinds("orders", "cancelled before ordered")

    def test_delivered_before_ordered(self):
        self.tables["shipments"].loc[0, "delivered_date"] = pd.Timestamp("2025-02-27")
        self.assertFinds("shipments", "delivered before ordered")

    def test_delivered_on_the_order_day_is_fine(self):
        self.tables["shipments"].loc[0, "delivered_date"] = pd.Timestamp("2025-03-01")
        self.assertFinds("shipments", "delivered before ordered", 0)

    def test_order_without_items(self):
        items = self.tables["order_items"]
        self.tables["order_items"] = items[items["order_id"] != "S-1"]
        self.assertFinds("orders", "orders without items")

    def test_order_without_a_shipment(self):
        self.tables["shipments"] = self.tables["shipments"].iloc[:2]
        self.assertFinds("orders", "orders without a shipment")

    def test_item_of_an_unknown_product(self):
        self.tables["order_items"].loc[3, "product_code"] = "XYZ"
        self.assertFinds("order_items", "items of unknown products")

    def test_shipment_of_a_cancelled_order(self):
        self.orders.loc[2, "cancelled_at"] = pd.Timestamp("2025-03-03 15:00")
        report = run(self.tables)
        self.assertEqual(found(report, "shipments", "shipments of cancelled orders"), 1)
        self.assertEqual(found(report, "orders", "cancelled orders"), 1)

    def test_customer_without_orders(self):
        self.tables["customers"].loc[2] = ["C-3", "Test Three", "9000000003"]
        self.assertFinds("customers", "customers without orders")

    def test_amount_rule_broken(self):
        self.orders.loc[1, "order_amount"] = 100.0   # basis is still "unknown"
        self.assertFinds("orders", "amount rule broken")

    def test_cod_lines_that_do_not_add_up(self):
        self.orders.loc[0, "order_amount"] = 700.0   # the lines add up to 650
        self.assertFinds("orders", "COD lines do not add up to the order amount")

    def test_cod_line_without_an_amount(self):
        self.tables["order_items"].loc[1, "line_amount"] = np.nan
        self.assertFinds("orders", "COD lines do not add up to the order amount")

    def test_cod_received_above_the_amount_to_collect(self):
        self.tables["shipments"].loc[0, "cod_amount_received"] = 700.0
        self.assertFinds("shipments", "COD received above the amount to collect")

    def test_money_received_on_a_prepaid_order(self):
        self.tables["shipments"].loc[2, "cod_amount_received"] = 500.0
        self.assertFinds("shipments", "money received on a non-COD order")

    def test_impossible_ad_numbers(self):
        ads = self.tables["ad_performance"]
        ads.loc[0, "reach"] = 5000                  # above 4,000 impressions
        ads.loc[1, "link_clicks"] = 95              # above 90 clicks in all
        ads.loc[1, "result_indicator"] = None       # 18 results of an unknown kind
        report = run(self.tables)
        self.assertEqual(found(report, "ad_performance", "reach above impressions"), 1)
        self.assertEqual(found(report, "ad_performance", "link clicks above all clicks"), 1)
        self.assertEqual(found(report, "ad_performance", "results without an indicator"), 1)


class OutlierTest(unittest.TestCase):
    def test_iqr_rule(self):
        values = list(range(1, 21)) + [100]         # Q1 6, Q3 16, so above 31 is unusual
        self.assertEqual(audit_module.count_outliers(values), 1)

    def test_missing_values_are_ignored(self):
        self.assertEqual(audit_module.count_outliers([1, 2, 3, 4, np.nan, 100]), 1)

    def test_too_few_values(self):
        self.assertEqual(audit_module.count_outliers([1, 2, 1000]), 0)

    def test_all_values_the_same(self):
        self.assertEqual(audit_module.count_outliers([1] * 10), 0)


class OutputTest(unittest.TestCase):
    def test_report_is_never_written_to_a_tracked_folder(self):
        with self.assertRaises(SystemExit):
            audit_module.write_report(run(make_tables()), SYNTHETIC)


class SyntheticDatabaseTest(unittest.TestCase):
    """The counts already known from Phase 2 must come out of the audit."""

    @classmethod
    def setUpClass(cls):
        try:
            engine = database.connect(database.SYNTHETIC_DATABASE, ask_password=False)
        except database.ConnectionProblem as problem:
            raise unittest.SkipTest(f"the synthetic database is not available here: {problem}")
        try:
            tables = database.read_tables(engine)
        finally:
            engine.dispose()
        cls.report = audit_module.audit(tables, period=("2025-01-01", "2025-12-31"))

    def test_known_counts(self):
        expected = {
            ("orders", "missing district_city"): 38,
            ("orders", "flag missing_district"): 38,
            ("orders", "flag possible_duplicate"): 14,
            ("orders", "flag payment_conflict"): 12,
            ("orders", "flag cod_amount_missing"): 9,
            ("orders", "orders with any review flag"): 73,
            ("orders", "cancelled orders"): 20,
            ("orders", "orders with no amount"): 952,
            ("orders", "orders without a shipment"): 32,
        }
        for (table, check), count in expected.items():
            with self.subTest(check=check):
                self.assertEqual(found(self.report, table, check), count)

    def test_no_broken_rules(self):
        for table, check in PROBLEM_CHECKS:
            if check == "orders without a shipment":
                continue   # 32 orders were never sent: cancelled or payment unclear
            with self.subTest(check=check):
                self.assertEqual(found(self.report, table, check), 0)


if __name__ == "__main__":
    unittest.main()
