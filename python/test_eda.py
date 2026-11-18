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

import numpy as np
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


class CustomerTest(unittest.TestCase):
    """C-1 ordered W-1 (1 March) and S-1 (3 March). C-2 ordered W-2 (2 March)."""

    def test_repeat_customers(self):
        table = eda.repeat_customers(clean()["orders"]).set_index("version")
        row = table.loc["all counted orders"]
        self.assertEqual((row["customers"], row["repeat_customers"], row["repeat_share"]), (2, 1, 0.5))

    def test_repeat_customers_without_possible_duplicates(self):
        def s1_duplicate(tables):
            tables["orders"].loc[2, "review_flags"] = "possible_duplicate"
        table = eda.repeat_customers(clean(s1_duplicate)["orders"]).set_index("version")
        self.assertEqual(table.loc["all counted orders", "repeat_customers"], 1)
        self.assertEqual(table.loc["without possible duplicates", "repeat_customers"], 0)

    def test_unknown_customers_are_left_out(self):
        def no_phone(tables):
            tables["orders"].loc[1, "review_flags"] = "missing_phone"
        row = eda.repeat_customers(clean(no_phone)["orders"]).iloc[0]
        self.assertEqual(row["customers"], 1)

    def test_days_to_second_order(self):
        row = eda.days_to_second_order(clean()["orders"]).iloc[0]
        self.assertEqual((row["customers_with_a_second_order"], row["median_days"]), (1, 2.0))

    def test_no_second_orders(self):
        row = eda.days_to_second_order(clean(cancel_s1)["orders"]).iloc[0]
        self.assertEqual(row["customers_with_a_second_order"], 0)

    def test_new_and_returning_by_month(self):
        def no_phone(tables):
            tables["orders"].loc[1, "review_flags"] = "missing_phone"
        row = eda.new_and_returning_by_month(clean(no_phone)["orders"]).iloc[0]
        self.assertEqual((row["new_customer_orders"], row["returning_customer_orders"],
                          row["unknown_customer_orders"]), (1, 1, 1))

    def test_repeat_by_district_leaves_out_small_districts(self):
        orders = clean()["orders"]
        table = eda.repeat_customers_by_district(orders, min_customers=1)
        self.assertEqual(table.to_dict("records"), [{"district_city": "Chennai", "state": "Tamil Nadu",
                                                     "customers": 2, "repeat_customers": 1, "repeat_share": 0.5}])
        self.assertTrue(eda.repeat_customers_by_district(orders, min_customers=3).empty)


class PaymentTest(unittest.TestCase):
    """W-1 is COD. W-2 and S-1 are Prepaid."""

    def test_payment_by_month(self):
        row = eda.payment_by_month(clean()["orders"]).iloc[0]
        self.assertEqual((row["cod"], row["prepaid"], row["needs_review"]), (1, 2, 0))
        self.assertAlmostEqual(row["cod_share"], 1 / 3)

    def test_needs_review_is_left_out_of_the_cod_share(self):
        def needs_review(tables):
            tables["orders"].loc[1, "payment_type"] = "needs_review"
        row = eda.payment_by_month(clean(needs_review)["orders"]).iloc[0]
        self.assertEqual((row["needs_review"], row["cod_share"]), (1, 0.5))   # 1 COD of 2 known

    def test_cod_share_by_state_leaves_out_small_states(self):
        orders = clean()["orders"]
        row = eda.cod_share_by_state(orders, min_orders=3).iloc[0]
        self.assertEqual((row["state"], row["orders"]), ("Tamil Nadu", 3))
        self.assertAlmostEqual(row["cod_share"], 1 / 3)
        self.assertTrue(eda.cod_share_by_state(orders, min_orders=4).empty)

    def test_basket_by_payment(self):
        table = eda.basket_by_payment(clean()["orders"]).set_index("payment_type")
        self.assertEqual((table.loc["cod", "orders"], table.loc["cod", "average_units"]), (1, 2.0))
        self.assertEqual((table.loc["prepaid", "orders"], table.loc["prepaid", "average_units"]), (2, 1.0))

    def test_product_mix_by_payment(self):
        table = eda.product_mix_by_payment(clean()["order_items"], clean()["orders"]).set_index("product_code")
        self.assertEqual((table.loc["CXE", "cod"], table.loc["LP", "cod"]), (0.5, 0.5))
        self.assertEqual((table.loc["CXE", "prepaid"], table.loc["LP", "prepaid"]), (1.0, 0.0))

    def test_cod_to_collect_by_week(self):
        table = eda.cod_to_collect_by_week(clean()["orders"])
        self.assertEqual(table.to_dict("records"), [{
            "week_start": pd.Timestamp("2025-02-24"), "cod_orders": 1, "amount_to_collect": 650.0,
            "estimated_to_collect": 0.0, "orders_without_value": 0}])

    def test_cod_estimate_is_kept_apart_from_the_recorded_amount(self):
        def no_brackets(tables):
            tables["orders"].loc[0, ["order_amount", "amount_basis", "review_flags"]] = [None, "unknown", "cod_amount_missing"]
            tables["order_items"].loc[[0, 1], "line_amount"] = None
        row = eda.cod_to_collect_by_week(clean(no_brackets)["orders"]).iloc[0]
        self.assertEqual((row["amount_to_collect"], row["estimated_to_collect"]), (0.0, 800.0))   # COD prices 600 + 200


class ShippingTest(unittest.TestCase):
    """SH-1 (W-1, Delhivery), SH-2 (W-2) and SH-3 (S-1, both Speed Post): all delivered after 4 days."""

    def test_delivery_outcomes(self):
        tables = clean()
        table = eda.delivery_outcomes(tables["shipments"], tables["orders"])
        self.assertEqual(table[["courier", "payment_type", "shipments", "delivered"]].to_dict("records"), [
            {"courier": "delhivery", "payment_type": "cod", "shipments": 1, "delivered": 1},
            {"courier": "speed_post", "payment_type": "prepaid", "shipments": 2, "delivered": 2}])

    def test_returned_share(self):
        def returned(tables):
            tables["shipments"].loc[1, ["delivery_status", "delivered_date"]] = ["returned", pd.NaT]
        tables = clean(returned)
        row = eda.delivery_outcomes(tables["shipments"], tables["orders"]).set_index("courier").loc["speed_post"]
        self.assertEqual((row["returned"], row["returned_share"]), (1, 0.5))

    def test_delivery_days_by_courier(self):
        tables = clean()
        table = eda.delivery_days_by_courier(tables["shipments"], tables["orders"]).set_index("courier")
        self.assertEqual((table.loc["speed_post", "deliveries"], table.loc["speed_post", "median_days"]), (2, 4.0))

    def test_no_courier_records_yet(self):
        def no_shipments(tables):
            tables["shipments"] = tables["shipments"].iloc[0:0]
        tables = clean(no_shipments)
        self.assertTrue(eda.delivery_outcomes(tables["shipments"], tables["orders"]).empty)
        self.assertTrue(eda.delivery_days_by_courier(tables["shipments"], tables["orders"]).empty)


def make_ad_tables():
    """Two fake campaigns over two weeks, cleaned: one messaging, one link-click.

    Week 2025-02-24 (Mon 24 Feb - Sun 2 Mar): campaign A spends 100+200,
    gets 10+15 messaging conversations. Campaign B spends 50, 1 link click.
    Week 2025-03-03: campaign A spends 300, 20 conversations.
    """
    tables = make_tables()
    tables["ad_campaigns"] = pd.DataFrame({
        "campaign_id": ["A", "B"], "campaign_name": ["Campaign A", "Campaign B"],
        "delivery_status": ["active", "active"], "attribution_setting": ["7-day click", None],
        "budget_amount": [500.0, 200.0], "budget_type": ["daily", "daily"],
        "end_date": pd.to_datetime([None, None])})
    tables["ad_performance"] = pd.DataFrame({
        "campaign_id": ["A", "A", "B", "A"],
        "report_date": pd.to_datetime(["2025-02-24", "2025-02-25", "2025-02-26", "2025-03-03"]),
        "amount_spent_inr": [100.0, 200.0, 50.0, 300.0],
        "impressions": [2000, 3000, 1000, 4000], "reach": [1800, 2700, 900, 3600],
        "link_clicks": [30, 40, 20, 50], "clicks_all": [40, 60, 25, 70],
        "landing_page_views": [np.nan, np.nan, 15, np.nan], "results": [10, 15, 1, 20],
        "result_indicator": ["actions:onsite_conversion.messaging_conversation_started_7d"] * 2
                           + ["actions:link_click"] + ["actions:onsite_conversion.messaging_conversation_started_7d"]})
    return clean_data.clean_all(tables)


class MarketingTest(unittest.TestCase):
    def test_spend_by_week(self):
        table = eda.spend_by_week(make_ad_tables()["ad_performance"])
        self.assertEqual(table.to_dict("records"), [
            {"week_start": pd.Timestamp("2025-02-24"), "amount_spent_inr": 350.0},
            {"week_start": pd.Timestamp("2025-03-03"), "amount_spent_inr": 300.0}])

    def test_cost_per_conversation_excludes_link_clicks(self):
        table = eda.cost_per_conversation(make_ad_tables()["ad_performance"]).set_index("campaign_id")
        self.assertEqual((table.loc["A", "conversations"], table.loc["A", "amount_spent_inr"]), (45, 600.0))
        self.assertNotIn("B", table.index)   # B has only a link_click result

    def test_weekly_cpm_and_ctr(self):
        table = eda.weekly_cpm_and_ctr(make_ad_tables()["ad_performance"])
        row = table[(table["campaign_id"] == "A") & (table["week_start"] == pd.Timestamp("2025-02-24"))].iloc[0]
        # spend 300, impressions 5000: cpm = 300/5000*1000 = 60. clicks_all 100/5000 = 0.02
        self.assertAlmostEqual(row["cpm"], 60.0)
        self.assertAlmostEqual(row["ctr"], 0.02)

    def test_zero_impressions_gives_empty_ratios_not_an_error(self):
        tables = make_ad_tables()
        ads = tables["ad_performance"].copy()
        ads.loc[ads["campaign_id"] == "B", "impressions"] = 0   # B's only row, so its week totals 0
        table = eda.weekly_cpm_and_ctr(ads)
        b_row = table[table["campaign_id"] == "B"].iloc[0]
        a_row = table[(table["campaign_id"] == "A") & (table["week_start"] == pd.Timestamp("2025-02-24"))].iloc[0]
        self.assertTrue(pd.isna(b_row["cpm"]) and pd.isna(b_row["ctr"]))
        self.assertFalse(pd.isna(a_row["cpm"]))   # campaign A's week is unaffected by B's zero

    def test_spend_and_orders_by_week_and_correlation(self):
        tables = make_ad_tables()
        table, correlation = eda.spend_and_orders_by_week(tables["ad_performance"], tables["orders"])
        self.assertEqual(list(table["week_start"]), [pd.Timestamp("2025-02-24"), pd.Timestamp("2025-03-03")])
        # W-1 and W-2 fall in the 24 Feb week (1,2 March), S-1 (shopify) is ignored
        first = table.iloc[0]
        self.assertEqual((first["amount_spent_inr"], first["messaging_conversations"], first["whatsapp_orders"]),
                         (350.0, 25, 2))
        self.assertTrue(pd.isna(correlation) or isinstance(correlation, float))

    def test_correlation_is_nan_with_too_few_weeks(self):
        tables = make_ad_tables()
        ads = tables["ad_performance"][tables["ad_performance"]["week_start"] == pd.Timestamp("2025-02-24")]
        _table, correlation = eda.spend_and_orders_by_week(ads, tables["orders"])
        self.assertTrue(pd.isna(correlation))

    def test_no_ad_data_yet(self):
        tables = clean()   # make_tables() without any ad rows replaced
        empty_ads = tables["ad_performance"].iloc[0:0]
        self.assertTrue(eda.spend_by_week(empty_ads).empty)
        self.assertTrue(eda.cost_per_conversation(empty_ads).empty)
        self.assertTrue(eda.weekly_cpm_and_ctr(empty_ads).empty)
        table, correlation = eda.spend_and_orders_by_week(empty_ads, tables["orders"])
        self.assertTrue(table.empty)
        self.assertTrue(pd.isna(correlation))


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

    def test_every_customer_and_payment_analysis_handles_no_orders(self):
        def cancel_all(tables):
            tables["orders"]["cancelled_at"] = pd.Timestamp("2025-03-05 10:00")
        tables = clean(cancel_all)
        orders, items, shipments = tables["orders"], tables["order_items"], tables["shipments"]
        self.assertEqual(eda.repeat_customers(orders)["customers"].tolist(), [0, 0])
        self.assertEqual(eda.days_to_second_order(orders).iloc[0]["customers_with_a_second_order"], 0)
        self.assertTrue(eda.new_and_returning_by_month(orders).empty)
        self.assertTrue(eda.repeat_customers_by_district(orders, min_customers=1).empty)
        self.assertTrue(eda.payment_by_month(orders).empty)
        self.assertTrue(eda.cod_share_by_state(orders, min_orders=1).empty)
        self.assertTrue(eda.basket_by_payment(orders).empty)
        self.assertTrue(eda.product_mix_by_payment(items, orders).empty)
        self.assertTrue(eda.cod_to_collect_by_week(orders).empty)
        self.assertTrue(eda.delivery_outcomes(shipments, orders).empty)       # shipments of cancelled orders
        self.assertTrue(eda.delivery_days_by_courier(shipments, orders).empty)


if __name__ == "__main__":
    unittest.main()
