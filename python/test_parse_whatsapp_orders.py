"""Tests for parse_whatsapp_orders.py, using the fake chat files only.

How to run (from the project folder):
    python -m unittest discover -s python -v
"""

import unittest
from collections import Counter
from datetime import datetime
from pathlib import Path

import parse_whatsapp_orders as parser

SYNTHETIC = Path(__file__).resolve().parent.parent / "data" / "synthetic"
PREPAID_CHAT = SYNTHETIC / "synthetic_whatsapp_chat_prepaid.txt"
COD_CHAT = SYNTHETIC / "synthetic_whatsapp_chat_cod.txt"
IGNORE_PHONES = parser.read_ignore_phones(SYNTHETIC / "synthetic_ignore_phones.txt")


def first_line(message):
    return message.text.split("\n")[0].strip()


class ReadMessagesTest(unittest.TestCase):
    def setUp(self):
        self.messages = parser.read_messages(PREPAID_CHAT, "prepaid")

    def test_number_of_messages(self):
        self.assertEqual(len(self.messages), 24)

    def test_system_line_has_no_sender(self):
        self.assertIsNone(self.messages[0].sender)
        self.assertIsNone(self.messages[1].sender)

    def test_date_is_day_month_year(self):
        order = self.messages[3]
        self.assertEqual(order.recorded_at, datetime(2025, 3, 3, 10, 15))
        self.assertEqual(order.sender, "Synthetic Shop")

    def test_message_keeps_all_its_lines(self):
        order = self.messages[3]
        self.assertEqual(first_line(order), "Test Customer One")
        self.assertEqual(len(order.text.split("\n")), 7)


class SplitCopiedOrdersTest(unittest.TestCase):
    def test_two_copied_orders_become_two_messages(self):
        messages = parser.read_messages(PREPAID_CHAT, "prepaid")
        copied = [m for m in messages if m.text.startswith("[")]
        self.assertEqual(len(copied), 1)

        parts = parser.split_copied_orders(copied[0])
        self.assertEqual([first_line(p) for p in parts], ["Test Customer Six", "Test Customer Seven"])
        self.assertEqual([p.copied_time for p in parts], ["04/03, 22:36", "05/03, 09:17"])
        # Both keep the date of the outer message: the date recorded.
        self.assertEqual(parts[0].recorded_at, datetime(2025, 3, 5, 10, 5))

    def test_normal_message_is_unchanged(self):
        message = parser.read_messages(PREPAID_CHAT, "prepaid")[3]
        self.assertEqual(parser.split_copied_orders(message), [message])


class FindNumbersTest(unittest.TestCase):
    def find(self, text):
        return parser.find_phones_and_pin_codes(text, IGNORE_PHONES)

    def test_plain_phone_and_pin(self):
        self.assertEqual(self.find("625001\n9000000001"), (["9000000001"], ["625001"]))

    def test_spaces_plus91_and_leading_zero(self):
        self.assertEqual(self.find("+91 90000 00003"), (["9000000003"], []))
        self.assertEqual(self.find("09000000013"), (["9000000013"], []))
        self.assertEqual(self.find("641 001"), ([], ["641001"]))

    def test_pin_at_end_of_address_line(self):
        self.assertEqual(self.find("Address: 3 Test Lane, Kochi 682001"), ([], ["682001"]))

    def test_label_before_phone(self):
        self.assertEqual(self.find("Pho No: 9000000005"), (["9000000005"], []))

    def test_house_numbers_are_not_pin_codes(self):
        self.assertEqual(self.find("12 Sample Street\n4/21 Example Road"), ([], []))

    def test_two_phones_keep_their_order(self):
        phones, _ = self.find("+91 90000 00003\n9000000004")
        self.assertEqual(phones, ["9000000003", "9000000004"])

    def test_ignored_phone_is_not_returned(self):
        self.assertEqual(self.find("Payment number: 9000000099"), ([], []))


class ClassifyTest(unittest.TestCase):
    def categories(self, path, group):
        messages = parser.parse_chat(path, group, IGNORE_PHONES)
        return messages, Counter(m.category for m in messages)

    def test_prepaid_counts(self):
        _, counts = self.categories(PREPAID_CHAT, "prepaid")
        self.assertEqual(counts, {"order": 14, "skipped": 7, "other": 4})

    def test_cod_counts(self):
        _, counts = self.categories(COD_CHAT, "cod")
        self.assertEqual(counts, {"order": 10, "skipped": 4, "other": 2})

    def test_prepaid_orders_are_the_right_messages(self):
        messages, _ = self.categories(PREPAID_CHAT, "prepaid")
        names = [first_line(m) for m in messages if m.category == "order"]
        self.assertEqual(names, [
            "Test Customer One", "Test Customer Two", "Test Customer Three",
            "Name: Test Customer Four", "Test Customer Five", "Test Customer Six",
            "Test Customer Seven", "Test Customer Eight", "Test Customer Nine",
            "Test Customer Ten", "Test Customer One", "Test Customer Eleven",
            "Test Customer Twelve", "TEST CUSTOMER THIRTEEN.",
        ])

    def test_things_that_are_not_orders(self):
        messages, _ = self.categories(PREPAID_CHAT, "prepaid")
        other = [first_line(m) for m in messages if m.category == "other"]
        self.assertEqual(other, [
            "This whole file is fake test data for the MarketPulse parser. No real person appears in it.",
            "20 cxe,2 LP,1 BL",               # stock tally
            "To place an order please send",  # advert text with the shop's own number
            "Reminder",                       # a note
        ])

    def test_advert_becomes_an_order_candidate_without_the_ignore_list(self):
        # This shows why the ignore list exists.
        messages = parser.parse_chat(PREPAID_CHAT, "prepaid")
        advert = [m for m in messages if first_line(m) == "To place an order please send"][0]
        self.assertEqual(advert.category, "order")


class ReadProductLineTest(unittest.TestCase):
    ALIASES = parser.read_aliases(SYNTHETIC / "synthetic_product_aliases.csv")

    def read(self, line):
        items = parser.read_product_line(line, self.ALIASES)
        if items is None:
            return None
        return [(i.product_code, i.quantity, i.amount) for i in items]

    def test_prepaid_line_with_habit_suffix(self):
        self.assertEqual(self.read("1 cxe/-, 1 LP"), [("CXE", 1, None), ("LP", 1, None)])

    def test_cod_line_with_amounts(self):
        self.assertEqual(self.read("1 CXE(500),1 LP(150)"), [("CXE", 1, 500.0), ("LP", 1, 150.0)])

    def test_no_space_and_letter_case(self):
        self.assertEqual(self.read("1BL, 2 Serum"), [("BL", 1, None), ("SERUM", 2, None)])

    def test_unknown_name_is_kept_but_not_matched(self):
        items = parser.read_product_line("1 cxe,1 mystery cream", self.ALIASES)
        self.assertEqual(items[1].product_code, None)
        self.assertEqual(items[1].raw_name, "mystery cream")

    def test_unreadable_part_is_kept_for_review(self):
        items = parser.read_product_line("1 cxe, free gift", self.ALIASES)
        self.assertEqual((items[1].raw_name, items[1].product_code, items[1].quantity),
                         ("free gift", None, None))

    def test_address_lines_are_not_product_lines(self):
        self.assertIsNone(self.read("Sample Taluk"))
        self.assertIsNone(self.read("625001"))
        self.assertIsNone(self.read("12 Example Town 682001"))


class ExtractOrderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        aliases = parser.read_aliases(SYNTHETIC / "synthetic_product_aliases.csv")
        cls.orders = {}
        for path, group in ((PREPAID_CHAT, "prepaid"), (COD_CHAT, "cod")):
            for message in parser.parse_chat(path, group, IGNORE_PHONES):
                if message.category == "order":
                    order = parser.extract_order(message, aliases, IGNORE_PHONES)
                    # "Test Customer One" appears twice; keep the first one.
                    cls.orders.setdefault(order.name, order)

    def items(self, name):
        return [(i.product_code, i.quantity, i.amount) for i in self.orders[name].items]

    def test_usual_layout(self):
        order = self.orders["Test Customer One"]
        self.assertEqual(order.phones, ["9000000001"])
        self.assertEqual(order.pin_codes, ["625001"])
        self.assertEqual(order.address, "12 Sample Street, Example Nagar, Sample Taluk, Madurai")
        self.assertEqual(self.items("Test Customer One"), [("CXE", 1, None), ("LP", 1, None)])
        self.assertEqual(order.notes, [])
        self.assertEqual(order.recorded_at, datetime(2025, 3, 3, 10, 15))

    def test_no_product_line_defaults_to_one_cream(self):
        order = self.orders["Test Customer Two"]
        self.assertEqual(self.items("Test Customer Two"), [("CXE", 1, None)])
        self.assertTrue(order.items[0].defaulted)
        self.assertIn("product_defaulted_to_cxe", order.notes)
        self.assertEqual(order.address, "4/21 Example Road, Sampleville, Chennai")

    def test_phone_above_pin_and_second_phone(self):
        order = self.orders["Test Customer Three"]
        self.assertEqual(order.phones, ["9000000003", "9000000004"])
        self.assertEqual(order.pin_codes, ["641001"])
        self.assertEqual(order.address, "7 Example Road, Near Sample Temple, Coimbatore")
        self.assertIn("second_phone=9000000004", order.notes)

    def test_labels_are_removed(self):
        order = self.orders["Test Customer Four"]
        self.assertEqual(order.phones, ["9000000005"])
        self.assertEqual(order.pin_codes, ["682001"])
        self.assertEqual(order.address, "3 Test Lane, Example Town, Sample District, Kochi 682001")

    def test_edited_mark_is_removed(self):
        self.assertEqual(self.items("Test Customer Five"), [("CXE", 2, None)])

    def test_copied_orders(self):
        six, seven = self.orders["Test Customer Six"], self.orders["Test Customer Seven"]
        self.assertIn("copied_order_time=04/03, 22:36", six.notes)
        self.assertTrue(six.items[0].defaulted)
        self.assertEqual(six.pin_codes, ["695001"])
        self.assertEqual(self.items("Test Customer Seven"), [("CXE", 1, None)])
        self.assertFalse(seven.items[0].defaulted)

    def test_unknown_product_has_no_code(self):
        self.assertEqual(self.items("Test Customer Eight"), [("CXE", 1, None), (None, 1, None)])

    def test_missing_phone_stays_missing(self):
        order = self.orders["Test Customer Nine"]
        self.assertEqual(order.phones, [])
        self.assertEqual(order.pin_codes, ["600001"])
        self.assertEqual(self.items("Test Customer Nine"), [("SERUM", 1, None)])

    def test_payment_word_is_found(self):
        order = self.orders["Test Customer Eleven"]
        self.assertEqual(order.payment_word, "cod")
        self.assertEqual(order.address, "31 Example Market Road, Kochi")
        self.assertEqual(self.orders["Test Buyer Seven"].payment_word, "prepaid")
        self.assertEqual(self.items("Test Buyer Seven"), [("CXE", 1, 500.0)])

    def test_capitals_dot_leading_zero_and_state_line(self):
        order = self.orders["TEST CUSTOMER THIRTEEN"]
        self.assertEqual(order.phones, ["9000000013"])
        self.assertEqual(order.address, "14 EXAMPLE STREET, SAMPLE POST, HYDERABAD, Telangana")
        self.assertEqual(self.items("TEST CUSTOMER THIRTEEN"), [("SS", 1, None), ("BL", 2, None)])

    def test_cod_amounts(self):
        self.assertEqual(self.items("Test Buyer One"), [("CXE", 1, 500.0), ("LP", 1, 150.0)])
        self.assertEqual(self.items("Test Buyer Six"), [("CXE", 2, 1000.0), ("FW", 1, 300.0)])
        self.assertEqual(self.items("Test Buyer Ten"),
                         [("KOJIGLOW", 1, 350.0), ("BL", 1, 400.0), ("SS", 1, 450.0)])

    def test_cod_without_product_line_has_no_amount(self):
        self.assertEqual(self.items("Test Buyer Two"), [("CXE", 1, None)])

    def test_two_pin_codes_are_both_kept(self):
        self.assertEqual(self.orders["Test Buyer Eight"].pin_codes, ["600001", "625001"])

    def test_bad_quantity_is_kept_as_written(self):
        self.assertEqual(self.items("Test Buyer Nine"), [("CXE", 0, 500.0)])

    def test_every_order_has_a_name_and_items(self):
        self.assertEqual(len(self.orders), 23)
        for order in self.orders.values():
            self.assertTrue(order.name)
            self.assertTrue(order.items)


if __name__ == "__main__":
    unittest.main()
