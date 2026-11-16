"""Tests for eda.py.

The tiny clean tables are made by running the real cleaning code on the
three fake orders of the audit tests:
  W-1  Saturday 1 March 2025 10:00, WhatsApp COD, CXE + LP, Rs 650 recorded
  W-2  Sunday 2 March 2025 11:00, WhatsApp Prepaid, 1 CXE, estimated Rs 500
  S-1  Monday 3 March 2025 12:00, Shopify Prepaid, 1 CXE, Rs 500 recorded
All three are in Chennai, Tamil Nadu.

How to run (from the project folder):
    python -m unittest discover -s python -v
"""

import unittest

import pandas as pd

import clean_data
import eda
from test_audit_data_quality import make_tables


def clean(change=None):
    """Clean the fake tables, after an optional change to the raw ones."""
    tables = make_tables()
    if change:
        change(tables)
    return clean_data.clean_all(tables)


def cancel_s1(tables):
    tables["orders"].loc[2, "cancelled_at"] = pd.Timestamp("2025-03-03 15:00")


class OrdersOverTimeTest(unittest.TestCase):
    def test_orders_by_month(self):
        table = eda.orders_by_month(clean()["orders"])
        self.assertEqual(table.to_dict("records"), [{"order_month": pd.Timestamp("2025-03-01"), "orders": 3}])

    def test_empty_months_are_zero(self):
        def move_s1(tables):
            tables["orders"].loc[2, "order_datetime"] = pd.Timestamp("2025-05-10 12:00")
        table = eda.orders_by_month(clean(move_s1)["orders"])
        self.assertEqual(list(table["orders"]), [2, 0, 1])   # March, April (none), May

    def test_orders_by_week_with_empty_weeks_and_trend(self):
        def move_s1(tables):
            tables["orders"].loc[2, "order_datetime"] = pd.Timestamp("2025-03-17 12:00")
        table = eda.orders_by_week(clean(move_s1)["orders"])
        self.assertEqual(list(table["week_start"].dt.strftime("%Y-%m-%d")),
                         ["2025-02-24", "2025-03-03", "2025-03-10", "2025-03-17"])
        self.assertEqual(list(table["orders"]), [2, 0, 0, 1])
        self.assertEqual(list(table["trend"]), [2.0, 1.0, 2 / 3, 0.75])

    def test_cancelled_orders_are_not_counted(self):
        self.assertEqual(eda.orders_by_month(clean(cancel_s1)["orders"])["orders"].sum(), 2)


class ProductTest(unittest.TestCase):
    def test_units_by_product(self):
        table = eda.units_by_product(clean()["order_items"]).set_index("product_code")
        self.assertEqual(table.loc["CXE", "units_total"], 3)
        self.assertEqual(table.loc["LP", "units_total"], 1)
        self.assertEqual(table.loc["CXE", "share_of_units"], 0.75)
        self.assertEqual(list(table.index), ["CXE", "LP"])   # most units first

    def test_defaulted_units_are_shown_apart(self):
        def default_w2(tables):
            tables["order_items"].loc[2, "product_defaulted"] = True
        cxe = eda.units_by_product(clean(default_w2)["order_items"]).set_index("product_code").loc["CXE"]
        self.assertEqual((cxe["units_written"], cxe["units_defaulted"], cxe["units_total"]), (2, 1, 3))

    def test_product_pairs(self):
        table = eda.product_pairs(clean()["order_items"])
        self.assertEqual(table.to_dict("records"), [{"product_a": "CXE", "product_b": "LP", "orders": 1}])

    def test_a_pair_counts_once_per_order(self):
        def second_lp_line(tables):
            items = tables["order_items"]
            items.loc[4] = [5, "W-1", "LP", 2, 300.0, False]
        table = eda.product_pairs(clean(second_lp_line)["order_items"])
        self.assertEqual(table["orders"].tolist(), [1])

    def test_no_pairs(self):
        def single_lines(tables):
            tables["order_items"] = tables["order_items"].drop(index=1)
        self.assertTrue(eda.product_pairs(clean(single_lines)["order_items"]).empty)


class ChannelTimeAndPlaceTest(unittest.TestCase):
    def test_orders_by_channel(self):
        table = eda.orders_by_channel(clean()["orders"]).set_index("sales_channel")
        self.assertEqual((table.loc["whatsapp", "orders"], table.loc["shopify", "orders"]), (2, 1))
        self.assertAlmostEqual(table.loc["whatsapp", "share"], 2 / 3)

    def test_weekday_and_hour(self):
        table = eda.orders_by_weekday_and_hour(clean()["orders"])
        self.assertEqual(table.shape, (7, 24))
        self.assertEqual(list(table.index), eda.WEEKDAYS)
        self.assertEqual((table.loc["Saturday", 10], table.loc["Sunday", 11], table.loc["Monday", 12]), (1, 1, 1))
        self.assertEqual(table.to_numpy().sum(), 3)

    def test_states_with_unknown_as_its_own_row(self):
        def no_state(tables):
            tables["orders"].loc[1, "state"] = None
        table = eda.orders_by_state(clean(no_state)["orders"]).set_index("state")
        self.assertEqual((table.loc["Tamil Nadu", "orders"], table.loc[eda.UNKNOWN, "orders"]), (2, 1))

    def test_top_districts_and_unknown_district(self):
        def no_district(tables):
            tables["orders"].loc[1, "district_city"] = None
        table = eda.top_districts(clean(no_district)["orders"])
        self.assertEqual(table.to_dict("records")[0], {"district_city": "Chennai", "state": "Tamil Nadu",
                                                        "orders": 2, "share": 2 / 3})
        self.assertEqual(table.iloc[-1]["district_city"], eda.UNKNOWN)
        self.assertEqual(table.iloc[-1]["state"], eda.ALL_STATES)   # the state of these orders is known
        self.assertEqual(table["orders"].sum(), 3)


class BasketAndValueTest(unittest.TestCase):
    def test_basket_size(self):
        table = eda.basket_size(clean()["orders"]).set_index("measure")
        self.assertAlmostEqual(table.loc["product_lines", "average"], 4 / 3)   # 2, 1, 1
        self.assertEqual((table.loc["product_lines", "median"], table.loc["product_lines", "max"]), (1.0, 2.0))
        self.assertEqual(table.loc["units", "orders"], 3)

    def test_value_by_month_keeps_recorded_and_estimated_apart(self):
        row = eda.value_by_month(clean()["orders"]).iloc[0]
        self.assertEqual(row["recorded_value"], 1150.0)    # W-1 650 + S-1 500
        self.assertEqual(row["estimated_value"], 500.0)    # W-2
        self.assertEqual((row["orders_recorded"], row["orders_estimated"], row["orders_unknown"]), (2, 1, 0))

    def test_unknown_values_are_counted_not_added(self):
        def needs_review(tables):
            tables["orders"].loc[1, "payment_type"] = "needs_review"
        row = eda.value_by_month(clean(needs_review)["orders"]).iloc[0]
        self.assertEqual((row["estimated_value"], row["orders_unknown"]), (0.0, 1))


class EmptyDataTest(unittest.TestCase):
    """No counted orders at all: every analysis gives an empty or zero result, never an error."""

    def test_every_sales_analysis_handles_no_orders(self):
        def cancel_all(tables):
            tables["orders"]["cancelled_at"] = pd.Timestamp("2025-03-05 10:00")
        tables = clean(cancel_all)
        orders, items = tables["orders"], tables["order_items"]
        self.assertTrue(eda.orders_by_month(orders).empty)
        self.assertTrue(eda.orders_by_week(orders).empty)
        self.assertTrue(eda.units_by_product(items).empty)
        self.assertTrue(eda.product_pairs(items).empty)
        self.assertTrue(eda.orders_by_channel(orders).empty)
        self.assertEqual(eda.orders_by_weekday_and_hour(orders).to_numpy().sum(), 0)
        self.assertTrue(eda.orders_by_state(orders).empty)
        self.assertTrue(eda.top_districts(orders).empty)
        self.assertEqual(len(eda.basket_size(orders)), 2)
        self.assertTrue(eda.value_by_month(orders).empty)


if __name__ == "__main__":
    unittest.main()
