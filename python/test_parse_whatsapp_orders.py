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


if __name__ == "__main__":
    unittest.main()
