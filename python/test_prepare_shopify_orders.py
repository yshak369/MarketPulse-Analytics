"""Tests for prepare_shopify_orders.py, using the fake Shopify export only.

How to run (from the project folder):
    python -m unittest discover -s python -v
"""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

import prepare_shopify_orders as shopify
from parse_whatsapp_orders import read_aliases, read_pin_codes

SYNTHETIC = Path(__file__).resolve().parent.parent / "data" / "synthetic"
FAKE_EXPORT = SYNTHETIC / "synthetic_shopify_orders_export.csv"
ALIASES = read_aliases(SYNTHETIC / "synthetic_product_aliases.csv")
PIN_CODES = read_pin_codes(SYNTHETIC / "synthetic_pin_code_sample.csv")


def column(name):
    return shopify.ORDER_COLUMNS.index(name)


class FakeExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.export = shopify.read_export(FAKE_EXPORT)
        orders, cls.items, cls.unknown, cls.methods = shopify.build_orders(cls.export, ALIASES, PIN_CODES)
        cls.orders = {order[0]: dict(zip(shopify.ORDER_COLUMNS, order)) for order in orders}

    def items_of(self, order_id):
        return [(code, quantity, amount) for oid, code, _, quantity, amount, _ in self.items if oid == order_id]

    def test_counts(self):
        self.assertEqual(len(self.export), 16)
        self.assertEqual(len(self.orders), 11)
        self.assertEqual(len(self.items), 16)

    def test_order_ids_are_fixed(self):
        self.assertEqual(sorted(self.orders), [f"S-{n}" for n in range(1001, 1012)])

    def test_clean_prepaid_order(self):
        order = self.orders["S-1001"]
        self.assertEqual(order["order_datetime"], "2025-03-05 10:15:00")
        self.assertEqual((order["payment_type"], order["phone"]), ("prepaid", "9000000201"))
        self.assertEqual((order["order_amount"], order["amount_basis"]), ("500", "shopify_total"))
        self.assertEqual((order["district_city"], order["state"]), ("Chennai", "Tamil Nadu"))
        self.assertEqual(order["review_flags"], "")
        self.assertEqual(order["sales_channel"], "shopify")

    def test_order_fields_on_first_row_only(self):
        order = self.orders["S-1002"]
        self.assertEqual((order["payment_type"], order["order_amount"]), ("cod", "1180"))
        self.assertEqual(self.items_of("S-1002"), [("CXE", 1, "500"), ("SS", 1, "450")])

    def test_repeat_customer_has_the_same_phone(self):
        self.assertEqual(self.orders["S-1003"]["phone"], self.orders["S-1001"]["phone"])
        self.assertEqual(self.items_of("S-1003"), [("CXE", 2, "1000")])   # before the discount
        self.assertEqual(self.orders["S-1003"]["order_amount"], "900")    # Shopify total, after it

    def test_cancelled_and_refunded_orders_are_kept(self):
        cancelled = self.orders["S-1004"]
        self.assertEqual(cancelled["cancelled_at"], "2025-03-08 15:30:00")
        self.assertEqual(cancelled["financial_status"], "voided")
        refunded = self.orders["S-1005"]
        self.assertEqual((refunded["payment_type"], refunded["notes"]), ("prepaid", "refunded_amount=600"))

    def test_unknown_product_is_flagged_not_matched(self):
        self.assertEqual(self.orders["S-1006"]["review_flags"], "unknown_product")
        self.assertEqual(self.items_of("S-1006"), [("CXE", 1, "500"), ("", 1, "999")])
        self.assertEqual(dict(self.unknown), {"synthetic mystery gift box": 1})

    def test_phone_columns_in_order(self):
        self.assertEqual((self.orders["S-1007"]["phone"], self.orders["S-1007"]["review_flags"]),
                         ("", "missing_phone"))
        self.assertEqual(self.orders["S-1008"]["phone"], "9000000207")    # Billing Phone
        self.assertEqual(self.orders["S-1011"]["phone"], "9000000101")    # Phone column, "+91 90000 00101"

    def test_pin_code_not_in_list(self):
        order = self.orders["S-1008"]
        self.assertEqual((order["pin_code"], order["district_city"]), ("999999", ""))
        self.assertEqual(order["review_flags"], "pin_code_not_found")

    def test_payment_rules(self):
        self.assertEqual(self.orders["S-1009"]["payment_type"], "needs_review")
        self.assertEqual(self.orders["S-1009"]["review_flags"], "payment_unclear")
        self.assertEqual(self.orders["S-1010"]["payment_type"], "cod")     # COD with an online advance
        self.assertEqual(self.methods["Cash on Delivery (COD)"], 3)
        self.assertEqual(self.methods["(blank)"], 1)

    def test_payment_type_function(self):
        self.assertEqual(shopify.payment_type_of("COD", "pending"), "cod")
        self.assertEqual(shopify.payment_type_of("Razorpay", "paid"), "prepaid")
        self.assertEqual(shopify.payment_type_of("Razorpay", "pending"), "needs_review")
        self.assertEqual(shopify.payment_type_of("Cashfree", "paid"), "prepaid")   # "cod" only as a word

    def test_amount_and_basis_always_agree(self):
        for order in self.orders.values():
            self.assertEqual(order["order_amount"] == "", order["amount_basis"] == "unknown")


class ProblemTest(unittest.TestCase):
    def test_missing_column_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            export = pd.read_csv(FAKE_EXPORT, dtype=str, keep_default_na=False)
            path = Path(folder) / "changed.csv"
            export.drop(columns=["Shipping Phone"]).to_csv(path, index=False)
            with self.assertRaisesRegex(shopify.ExportProblem, "Shipping Phone"):
                shopify.read_export(path)

    def test_invalid_phone_is_flagged(self):
        self.assertIsNone(shopify.clean_phone("12345"))
        self.assertEqual(shopify.clean_phone("+91 90000-00001"), "9000000001")
        self.assertEqual(shopify.clean_phone(""), "")

    def test_output_guard_refuses_a_tracked_folder(self):
        with self.assertRaises(SystemExit):
            shopify.write_outputs([], [], {}, SYNTHETIC)


if __name__ == "__main__":
    unittest.main()
