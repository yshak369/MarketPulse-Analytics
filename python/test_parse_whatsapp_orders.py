"""Tests for parse_whatsapp_orders.py, using the fake chat files only.

How to run (from the project folder):
    python -m unittest discover -s python -v
"""

import csv
import tempfile
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
        self.assertEqual(counts, {"order": 11, "skipped": 4, "other": 2})

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


def parse_fake_chats(pin_codes=None):
    """Parse, extract and validate both fake chats, as the script does."""
    aliases = parser.read_aliases(SYNTHETIC / "synthetic_product_aliases.csv")
    orders = []
    for path, group in ((PREPAID_CHAT, "prepaid"), (COD_CHAT, "cod")):
        for message in parser.parse_chat(path, group, IGNORE_PHONES):
            if message.category == "order":
                orders.append(parser.extract_order(message, aliases, IGNORE_PHONES))
    return parser.validate_orders(orders, pin_codes)


class PinCodeLookupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pin_codes = parser.read_pin_codes(SYNTHETIC / "synthetic_pin_code_sample.csv")
        cls.orders = {}
        for order in parse_fake_chats(cls.pin_codes):
            cls.orders.setdefault(order.name, order)

    def place(self, name):
        order = self.orders[name]
        return order.district_city, order.state

    def test_sample_list_is_read(self):
        self.assertEqual(len(self.pin_codes), 10)
        self.assertEqual(self.pin_codes["600001"], ("Chennai", "Tamil Nadu"))

    def test_district_and_state_are_filled(self):
        self.assertEqual(self.place("Test Customer One"), ("Madurai", "Tamil Nadu"))
        self.assertEqual(self.place("Test Customer Four"), ("Ernakulam", "Kerala"))   # PIN inside the address line
        self.assertEqual(self.place("Test Buyer Six"), ("Hyderabad", "Telangana"))
        self.assertEqual(self.orders["Test Customer One"].flags, [])

    def test_unknown_pin_code_is_flagged_and_left_empty(self):
        self.assertEqual(self.place("Test Customer Twelve"), ("", ""))
        self.assertEqual(self.orders["Test Customer Twelve"].flags, ["pin_code_not_found"])

    def test_two_pin_codes_are_not_looked_up(self):
        self.assertEqual(self.place("Test Buyer Eight"), ("", ""))
        self.assertEqual(self.orders["Test Buyer Eight"].flags, ["multiple_pin_codes"])

    def test_pin_code_with_two_places_is_ambiguous(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "pins.csv"
            path.write_text("pin_code,district,state\n600001,Chennai,Tamil Nadu\n"
                            "600001,Chennai,Tamil Nadu\n625001,Madurai,Tamil Nadu\n"
                            "625001,Somewhere Else,Tamil Nadu\n", encoding="utf-8")
            pin_codes = parser.read_pin_codes(path)
        self.assertEqual(pin_codes["600001"], ("Chennai", "Tamil Nadu"))   # same place twice is fine
        self.assertIsNone(pin_codes["625001"])

        order = make_order("9000000201", datetime(2025, 3, 3, 10, 0))
        order.pin_codes = ["625001"]
        parser.validate_orders([order], pin_codes)
        self.assertEqual((order.district_city, order.flags), ("", ["pin_code_ambiguous"]))

    def test_list_with_empty_district_fills_the_state_and_flags_the_order(self):
        order = make_order("9000000201", datetime(2025, 3, 3, 10, 0))
        order.pin_codes = ["641001"]
        parser.validate_orders([order], {"641001": ("", "TAMIL NADU")})
        self.assertEqual((order.district_city, order.state), ("", "TAMIL NADU"))
        self.assertEqual(order.flags, ["pin_code_ambiguous"])

    def test_without_a_list_nothing_is_filled_or_flagged(self):
        orders = {o.name: o for o in parse_fake_chats()}
        self.assertEqual(orders["Test Customer Twelve"].flags, [])
        self.assertEqual(orders["Test Buyer Six"].district_city, "")


def make_order(phone, recorded_at, product_code="CXE", quantity=1, group="prepaid"):
    """A small hand-made order for testing one rule at a time."""
    item = parser.OrderItem(product_code.lower(), product_code, quantity, None)
    return parser.Order(
        source_group=group, line_number=1, recorded_at=recorded_at, name="Test Person",
        address="1 Test Street", phones=[phone] if phone else [], pin_codes=["600001"],
        payment_word=None, items=[item],
    )


class ValidateFakeChatsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orders = parse_fake_chats()

    def flags_by_group(self, group):
        return [(o.name, o.flags) for o in self.orders if o.source_group == group]

    def test_prepaid_flags(self):
        self.assertEqual(self.flags_by_group("prepaid"), [
            ("Test Customer One", []),
            ("Test Customer Two", []),            # defaulted to 1 CXE: a note, not a flag
            ("Test Customer Three", []),
            ("Test Customer Four", []),
            ("Test Customer Five", []),
            ("Test Customer Six", []),
            ("Test Customer Seven", []),
            ("Test Customer Eight", ["unknown_product"]),
            ("Test Customer Nine", ["missing_phone"]),
            ("Test Customer Ten", ["prepaid_with_amount"]),
            ("Test Customer One", []),            # same order two days later: outside 24 hours
            ("Test Customer Eleven", ["payment_conflict"]),
            ("Test Customer Twelve", []),
            ("TEST CUSTOMER THIRTEEN", []),
        ])

    def test_cod_flags(self):
        self.assertEqual(self.flags_by_group("cod"), [
            ("Test Buyer One", []),
            ("Test Buyer Two", ["cod_amount_missing"]),     # no product line, so no amount
            ("Test Buyer Three", ["cod_amount_missing"]),   # product line without an amount
            ("Test Buyer Four", ["amount_out_of_range"]),   # Rs 5
            ("Test Buyer Five", ["amount_out_of_range"]),   # Rs 50,000
            ("Test Buyer One", ["possible_duplicate"]),     # same order six hours later
            ("Test Buyer Six", []),
            ("Test Buyer Seven", ["payment_conflict"]),
            ("Test Buyer Eight", ["multiple_pin_codes"]),
            ("Test Buyer Nine", ["bad_quantity"]),
            ("Test Buyer Ten", []),
        ])

    def test_payment_type(self):
        types = {(o.source_group, o.name): o.payment_type for o in self.orders}
        self.assertEqual(types[("prepaid", "Test Customer Two")], "prepaid")
        self.assertEqual(types[("cod", "Test Buyer Six")], "cod")
        self.assertEqual(types[("prepaid", "Test Customer Eleven")], "needs_review")
        self.assertEqual(types[("cod", "Test Buyer Seven")], "needs_review")

    def test_order_ids_are_unique(self):
        ids = [o.order_id for o in self.orders]
        self.assertEqual(len(set(ids)), len(ids))
        self.assertTrue(all(i.startswith("W-") for i in ids))

    def test_amount_is_known_only_for_complete_cod_orders(self):
        amounts = {}
        for order in self.orders:
            amounts.setdefault((order.source_group, order.name), parser.order_amount_and_basis(order))
        self.assertEqual(amounts[("cod", "Test Buyer One")], (650.0, "cod_collectible"))
        self.assertEqual(amounts[("cod", "Test Buyer Six")], (1300.0, "cod_collectible"))
        self.assertEqual(amounts[("cod", "Test Buyer Two")], (None, "unknown"))       # amount missing
        self.assertEqual(amounts[("cod", "Test Buyer Seven")], (None, "unknown"))     # needs review
        self.assertEqual(amounts[("prepaid", "Test Customer One")], (None, "unknown"))
        self.assertEqual(amounts[("prepaid", "Test Customer Ten")], (None, "unknown"))


class DuplicateRuleTest(unittest.TestCase):
    def flags(self, *orders):
        parser.validate_orders(list(orders))
        return [o.flags for o in orders]

    def test_same_order_within_24_hours_is_flagged(self):
        first = make_order("9000000201", datetime(2025, 3, 3, 10, 0))
        second = make_order("9000000201", datetime(2025, 3, 4, 10, 0))   # exactly 24 hours later
        self.assertEqual(self.flags(first, second), [[], ["possible_duplicate"]])

    def test_same_order_after_24_hours_is_not_flagged(self):
        first = make_order("9000000201", datetime(2025, 3, 3, 10, 0))
        second = make_order("9000000201", datetime(2025, 3, 4, 10, 1))
        self.assertEqual(self.flags(first, second), [[], []])

    def test_different_products_or_phone_are_not_duplicates(self):
        first = make_order("9000000201", datetime(2025, 3, 3, 10, 0))
        other_product = make_order("9000000201", datetime(2025, 3, 3, 11, 0), product_code="LP")
        other_quantity = make_order("9000000201", datetime(2025, 3, 3, 12, 0), quantity=2)
        other_phone = make_order("9000000202", datetime(2025, 3, 3, 13, 0))
        self.assertEqual(self.flags(first, other_product, other_quantity, other_phone), [[], [], [], []])

    def test_duplicate_across_the_two_groups_is_found(self):
        prepaid = make_order("9000000201", datetime(2025, 3, 3, 10, 0), group="prepaid")
        cod = make_order("9000000201", datetime(2025, 3, 3, 12, 0), group="cod")
        self.assertIn("possible_duplicate", self.flags(prepaid, cod)[1])

    def test_orders_without_phone_are_never_called_duplicates(self):
        first = make_order(None, datetime(2025, 3, 3, 10, 0))
        second = make_order(None, datetime(2025, 3, 3, 11, 0))
        self.assertEqual(self.flags(first, second), [["missing_phone"], ["missing_phone"]])


class OutputFolderGuardTest(unittest.TestCase):
    def test_folders_tracked_by_git_are_refused(self):
        for folder in (parser.PROJECT_FOLDER, parser.PROJECT_FOLDER / "python",
                       parser.PROJECT_FOLDER / "data" / "synthetic", parser.PROJECT_FOLDER / "data"):
            with self.assertRaises(SystemExit):
                parser.check_output_folder(folder)

    def test_ignored_folder_and_outside_folders_are_allowed(self):
        allowed = parser.PROJECT_FOLDER / "data" / "processed" / "anything"
        self.assertEqual(parser.check_output_folder(allowed), allowed.resolve())
        with tempfile.TemporaryDirectory() as outside:
            self.assertEqual(parser.check_output_folder(outside), Path(outside).resolve())


class WriteOutputsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        parser.write_outputs(parse_fake_chats(), cls.folder.name)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def rows(self, name):
        with open(Path(self.folder.name) / name, encoding="utf-8", newline="") as csv_file:
            return list(csv.DictReader(csv_file))

    def test_row_counts(self):
        self.assertEqual(len(self.rows("whatsapp_orders.csv")), 25)
        self.assertEqual(len(self.rows("whatsapp_order_items.csv")), 35)
        self.assertEqual(len(self.rows("whatsapp_review_queue.csv")), 12)
        self.assertEqual(self.rows("whatsapp_unknown_products.csv"), [{"raw_name": "mystery cream", "count": "1"}])

    def test_every_item_points_to_an_order(self):
        order_ids = {row["order_id"] for row in self.rows("whatsapp_orders.csv")}
        self.assertTrue(all(row["order_id"] in order_ids for row in self.rows("whatsapp_order_items.csv")))

    def test_amount_and_basis_always_agree(self):
        for row in self.rows("whatsapp_orders.csv"):
            self.assertEqual(row["amount_basis"] == "unknown", row["order_amount"] == "")

    def test_clean_cod_order_row(self):
        row = [r for r in self.rows("whatsapp_orders.csv")
               if r["customer_name"] == "Test Buyer Six"][0]
        self.assertEqual(row["order_datetime"], "2025-03-04 10:00:00")
        self.assertEqual((row["sales_channel"], row["payment_type"]), ("whatsapp", "cod"))
        self.assertEqual((row["phone"], row["pin_code"]), ("9000000106", "500001"))
        self.assertEqual((row["order_amount"], row["amount_basis"]), ("1300", "cod_collectible"))
        self.assertEqual((row["review_flags"], row["district_city"], row["state"]), ("", "", ""))

    def test_pin_code_is_empty_when_there_are_two(self):
        row = [r for r in self.rows("whatsapp_orders.csv")
               if r["customer_name"] == "Test Buyer Eight"][0]
        self.assertEqual((row["pin_code"], row["review_flags"]), ("", "multiple_pin_codes"))

    def test_review_queue_keeps_the_raw_message(self):
        row = [r for r in self.rows("whatsapp_review_queue.csv")
               if r["review_flags"] == "unknown_product"][0]
        self.assertIn("1 cxe,1 mystery cream", row["raw_message"])


if __name__ == "__main__":
    unittest.main()
