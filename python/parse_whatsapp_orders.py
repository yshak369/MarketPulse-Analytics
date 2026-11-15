"""Turn exported WhatsApp chats into order tables.

Design: docs/whatsapp_parser_plan.md (version 2).

This script runs only on the owner's computer. It uses plain Python.
It never sends data anywhere.

What this version does:
  Part 1. Split a chat file into messages, and sort each message into
          "skipped", "order" or "other".
  Part 2. Extract the fields of each order: name, address, phone,
          PIN code, payment word and products.
A later part will validate the orders and write the output files.

How to run on the fake test chats (from the project folder):
    python python/parse_whatsapp_orders.py --prepaid data/synthetic/synthetic_whatsapp_chat_prepaid.txt --cod data/synthetic/synthetic_whatsapp_chat_cod.txt --ignore-phones data/synthetic/synthetic_ignore_phones.txt --aliases data/synthetic/synthetic_product_aliases.csv

Add --details to list every message with its line number and group.
The output shows counts and line numbers only, never message text,
so it is safe to share.
"""

import argparse
import csv
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------
# Patterns. A "regular expression" (regex) describes the shape of a text.
# ---------------------------------------------------------------------

# Start of a message in an Android export: "03/03/2025, 10:15 - rest"
MESSAGE_START = re.compile(r"^(\d{1,2}/\d{1,2}/\d{4}), (\d{1,2}:\d{2}) - (.*)$")

# "Sender: text". System lines (for example "X created group") have no colon.
SENDER_AND_TEXT = re.compile(r"^([^:]+): ?(.*)$")

# Start of a copied order inside a message: "[04/03, 22:36] Sender: text"
COPIED_START = re.compile(r"^\[(\d{1,2}/\d{1,2}, \d{1,2}:\d{2})\] [^:]+: ?(.*)$")

# Lines WhatsApp writes in place of media or deleted messages.
MEDIA_LINE = re.compile(r"^<[^<>]* omitted>$")
DELETED_LINES = {"You deleted this message", "This message was deleted"}

# A message that is nothing but one link.
ONLY_A_LINK = re.compile(r"^https?://\S+$")

# Labels some orders put at the start of a line, such as "Name:" or "Pin code:".
LABEL = re.compile(
    r"^\s*(name|address|add|pin ?code|pin|phone ?(number|no)?|pho ?no|ph ?no|ph"
    r"|mobile ?(number|no)?|mob)\s*[:.\-]\s*",
    re.IGNORECASE,
)

# A run of digits that may have spaces inside, such as "+91 90000 00003" or "641 001".
NUMBER_RUN = re.compile(r"\+?\d(?:[\d ]*\d)?")

# A phone: 10 digits starting with 6 to 9, after an optional +91, 91 or 0.
PHONE = re.compile(r"^(?:\+?91|0)?([6-9]\d{9})$")

# A PIN code: exactly 6 digits, not starting with 0.
PIN_CODE = re.compile(r"^[1-9]\d{5}$")

# Invisible marks WhatsApp sometimes adds to exported lines.
INVISIBLE_MARKS = "‎‏‪‬﻿"

# Text WhatsApp adds to the end of an edited message.
EDITED_MARK = "<This message was edited>"

# A line that only says how the order is paid.
PAYMENT_WORD = re.compile(r"^(cod|prepaid)$", re.IGNORECASE)

# One product: a quantity, a name, and for COD an amount in brackets.
# Examples: "1 cxe", "2 cxe(1000)", "1BL", "1 Serum ( 600 )"
PRODUCT_PART = re.compile(
    r"^(\d+)\s*([A-Za-z][A-Za-z0-9 +.&]*?)\s*(?:\(\s*(\d+(?:\.\d+)?)\s*\))?$"
)

# Owner's business rule: an order with no product line is 1 cream.
DEFAULT_PRODUCT_CODE = "CXE"
DEFAULT_PRODUCT_NOTE = "product_defaulted_to_cxe"


@dataclass
class Message:
    """One message from a chat, or one copied order inside a message."""

    source_group: str        # "prepaid" or "cod"
    line_number: int         # line in the file where the message starts
    recorded_at: datetime    # when the message was posted (the "date recorded")
    sender: str | None       # None for system lines
    text: str                # the message text, possibly several lines
    copied_time: str | None = None  # for a copied order: its inner "day/month, time"
    category: str = ""       # "skipped", "order" or "other"


@dataclass
class OrderItem:
    """One product in an order."""

    raw_name: str               # the name as written, in lower case
    product_code: str | None    # None when the name is not in the alias file
    quantity: int | None        # None when the part could not be read
    amount: float | None        # COD amount for the line; None when not written
    defaulted: bool = False     # True when the order had no product line


@dataclass
class Order:
    """The fields extracted from one order message. Nothing is validated yet."""

    source_group: str
    line_number: int
    recorded_at: datetime
    name: str
    address: str
    phones: list            # every phone found, in order; the first is the main one
    pin_codes: list         # every PIN code found; more than one is flagged later
    payment_word: str | None   # "cod", "prepaid" or None
    items: list
    notes: list = field(default_factory=list)
    raw_message: str = ""   # private: kept so the owner can check the parser's work


def read_messages(path, source_group):
    """Read one exported chat file and split it into messages."""
    messages = []
    current = None

    with open(path, encoding="utf-8-sig") as chat_file:
        for line_number, raw_line in enumerate(chat_file, start=1):
            line = raw_line.rstrip("\n").strip(INVISIBLE_MARKS)

            start = MESSAGE_START.match(line)
            if start:
                # A new message begins here.
                date_text, time_text, rest = start.groups()
                recorded_at = datetime.strptime(f"{date_text} {time_text}", "%d/%m/%Y %H:%M")

                sender_match = SENDER_AND_TEXT.match(rest)
                if sender_match:
                    sender, text = sender_match.groups()
                else:
                    sender, text = None, rest   # a system line

                current = Message(source_group, line_number, recorded_at, sender, text)
                messages.append(current)
            elif current is not None:
                # No timestamp, so this line continues the message above it.
                current.text += "\n" + line

    return messages


def split_copied_orders(message):
    """Split a message that holds several copied orders (layout E).

    A copied order starts with a line like "[04/03, 22:36] Sender: text".
    A message without such lines is returned unchanged.
    """
    parts = []
    current_lines = []
    current_time = None
    found_copied_order = False

    def close_part():
        text = "\n".join(current_lines).strip()
        if text:
            parts.append(
                Message(
                    message.source_group, message.line_number, message.recorded_at,
                    message.sender, text, copied_time=current_time,
                )
            )

    for line in message.text.split("\n"):
        copied = COPIED_START.match(line)
        if copied:
            found_copied_order = True
            close_part()
            current_time, first_line = copied.groups()
            current_lines = [first_line]
        else:
            current_lines.append(line)
    close_part()

    return parts if found_copied_order else [message]


def remove_label(line):
    """Remove a label such as "Name:" from the start of a line."""
    return LABEL.sub("", line)


def find_phones_and_pin_codes(text, ignore_phones=frozenset()):
    """Find phone numbers and PIN codes anywhere in a message.

    Fields are found by their pattern, not by their position, because
    real orders write them in different places.
    Returns two lists: phones and PIN codes, in the order they appear.
    """
    phones = []
    pin_codes = []

    def check(candidate):
        """Add the candidate to a list if it is a phone or a PIN code."""
        phone = PHONE.match(candidate)
        if phone:
            if phone.group(1) not in ignore_phones:
                phones.append(phone.group(1))
            return True
        if PIN_CODE.match(candidate):
            pin_codes.append(candidate)
            return True
        return False

    for line in text.split("\n"):
        for run in NUMBER_RUN.findall(remove_label(line)):
            # First try the whole run with its spaces removed ("641 001").
            if not check(run.replace(" ", "")):
                # Otherwise try each piece by itself ("12 600001").
                for piece in run.split():
                    check(piece)

    return phones, pin_codes


def classify(message, ignore_phones=frozenset()):
    """Decide whether a message is "skipped", "order" or "other"."""
    text = message.text.strip()

    # Skipped: system lines, empty messages, media, deleted messages, bare links.
    if message.sender is None or not text:
        return "skipped"
    if MEDIA_LINE.match(text) or text in DELETED_LINES or ONLY_A_LINK.match(text):
        return "skipped"

    # Order: has a phone or a PIN code, plus a name line and an address line.
    phones, pin_codes = find_phones_and_pin_codes(text, ignore_phones)
    lines_with_words = [
        line for line in text.split("\n")
        if re.search(r"[A-Za-z]", remove_label(line))
    ]
    if (phones or pin_codes) and len(lines_with_words) >= 2:
        return "order"

    # Everything else: notes, advert text, price lists, stock tallies.
    return "other"


def read_aliases(path):
    """Read the alias file: every way a product is written -> its product code.

    The file has the columns alias, source, product_code.
    """
    aliases = {}
    with open(path, encoding="utf-8-sig", newline="") as alias_file:
        for row in csv.DictReader(alias_file):
            aliases[normalise_product_name(row["alias"])] = row["product_code"].strip().upper()
    return aliases


def normalise_product_name(name):
    """Lower case, with single spaces, so "Body  Lotion" equals "body lotion"."""
    return " ".join(name.lower().split())


def is_only_numbers(line):
    """True when a line holds nothing but phone numbers or PIN codes."""
    without_numbers = NUMBER_RUN.sub("", remove_label(line))
    return not re.search(r"[A-Za-z0-9]", without_numbers)


def read_product_line(line, aliases):
    """Read a product line such as "1 cxe/-, 2 LP(300)".

    Returns a list of OrderItem, or None when the line is not a product line.
    """
    parts = [part.strip() for part in line.replace("/-", "").split(",") if part.strip()]
    if not parts or not PRODUCT_PART.match(parts[0]):
        return None

    # An address line can also start with a number ("12 Sample Street 600001").
    # A product line never contains a phone number or a PIN code.
    outside_brackets = re.sub(r"\([^)]*\)", "", line)
    phones, pin_codes = find_phones_and_pin_codes(outside_brackets)
    if phones or pin_codes:
        return None

    items = []
    for part in parts:
        match = PRODUCT_PART.match(part)
        if not match:
            # Part of the line cannot be read. Keep it so it is flagged, not lost.
            items.append(OrderItem(normalise_product_name(part), None, None, None))
            continue
        quantity, name, amount = match.groups()
        raw_name = normalise_product_name(name)
        items.append(
            OrderItem(
                raw_name=raw_name,
                product_code=aliases.get(raw_name),   # None when unknown: never guessed
                quantity=int(quantity),
                amount=float(amount) if amount is not None else None,
            )
        )
    return items


def extract_order(message, aliases, ignore_phones=frozenset()):
    """Pull the fields out of one order message.

    Fields are found by pattern. Nothing is guessed: a field that is
    not found stays empty, and the next part of the parser flags it.
    """
    # Clean-up: remove the edited mark, extra spaces and empty lines.
    lines = [line.replace(EDITED_MARK, "").strip() for line in message.text.split("\n")]
    lines = [line for line in lines if line]

    # A line that only says "Cod" or "Prepaid".
    payment_word = None
    remaining = []
    for line in lines:
        if PAYMENT_WORD.match(remove_label(line)):
            payment_word = line.lower()
        else:
            remaining.append(line)

    # Product lines sit at the end of the message. Read upwards from the
    # last line until a line is not a product line.
    items = []
    while len(remaining) > 1:
        line_items = read_product_line(remaining[-1], aliases)
        if line_items is None:
            break
        items = line_items + items
        remaining.pop()

    notes = []
    if not items:
        # Owner's business rule, not a guess: no product line means 1 cream.
        items = [OrderItem(DEFAULT_PRODUCT_CODE.lower(), DEFAULT_PRODUCT_CODE, 1, None, defaulted=True)]
        notes.append(DEFAULT_PRODUCT_NOTE)

    # Phones and PIN codes, wherever they are in the remaining lines.
    phones, pin_codes = find_phones_and_pin_codes("\n".join(remaining), ignore_phones)
    if len(phones) > 1:
        notes.append("second_phone=" + ",".join(phones[1:]))
    if message.copied_time:
        notes.append("copied_order_time=" + message.copied_time)

    # The first line is the name. The rest is the address, without the
    # lines that hold only a phone number or a PIN code.
    name = " ".join(remove_label(remaining[0]).split()).rstrip(".").strip() if remaining else ""
    address_lines = [
        " ".join(remove_label(line).split())
        for line in remaining[1:]
        if not is_only_numbers(line)
    ]

    return Order(
        source_group=message.source_group,
        line_number=message.line_number,
        recorded_at=message.recorded_at,
        name=name,
        address=", ".join(address_lines),
        phones=phones,
        pin_codes=pin_codes,
        payment_word=payment_word,
        items=items,
        notes=notes,
        raw_message=message.text,
    )


def read_ignore_phones(path):
    """Read the owner's list of phone numbers to ignore, one per line."""
    if path is None:
        return frozenset()
    lines = Path(path).read_text(encoding="utf-8").split("\n")
    return frozenset(line.strip() for line in lines if line.strip() and not line.startswith("#"))


def parse_chat(path, source_group, ignore_phones=frozenset()):
    """Read one chat file and return its messages, split and classified."""
    result = []
    for message in read_messages(path, source_group):
        for part in split_copied_orders(message):
            part.category = classify(part, ignore_phones)
            result.append(part)
    return result


def main():
    arguments = argparse.ArgumentParser(description="Parse exported WhatsApp order chats.")
    arguments.add_argument("--prepaid", help="exported chat file of the Prepaid group")
    arguments.add_argument("--cod", help="exported chat file of the COD group")
    arguments.add_argument("--ignore-phones", help="file with phone numbers to ignore, one per line")
    arguments.add_argument("--aliases", help="alias file: product spellings and their codes")
    arguments.add_argument("--details", action="store_true", help="list every message (no message text)")
    options = arguments.parse_args()

    ignore_phones = read_ignore_phones(options.ignore_phones)
    aliases = read_aliases(options.aliases) if options.aliases else None

    for source_group, path in (("prepaid", options.prepaid), ("cod", options.cod)):
        if path is None:
            continue
        messages = parse_chat(path, source_group, ignore_phones)

        counts = {"order": 0, "other": 0, "skipped": 0}
        for message in messages:
            counts[message.category] += 1

        print(f"{source_group}: {len(messages)} messages -> "
              f"{counts['order']} orders, {counts['other']} other, {counts['skipped']} skipped")

        if aliases is not None:
            orders = [
                extract_order(message, aliases, ignore_phones)
                for message in messages if message.category == "order"
            ]
            all_items = [item for order in orders for item in order.items]
            print(f"  extracted: {len(all_items)} product lines, "
                  f"{sum(1 for o in orders if DEFAULT_PRODUCT_NOTE in o.notes)} orders defaulted to 1 CXE, "
                  f"{sum(1 for i in all_items if i.product_code is None)} unknown product names, "
                  f"{sum(1 for o in orders if not o.phones)} without phone, "
                  f"{sum(1 for o in orders if not o.pin_codes)} without PIN code")

        if options.details:
            for message in messages:
                line_count = len(message.text.split("\n"))
                copied = " (copied order)" if message.copied_time else ""
                print(f"  line {message.line_number:>5}  {message.category:<8} {line_count} lines{copied}")


if __name__ == "__main__":
    main()
