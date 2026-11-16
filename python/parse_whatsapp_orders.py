"""Turn exported WhatsApp chats into order tables.

Design: docs/whatsapp_parser_plan.md (version 2).

This script runs only on the owner's computer. It uses plain Python.
It never sends data anywhere.

What this version does:
  Part 1. Split a chat file into messages, and sort each message into
          "skipped", "order" or "other".
  Part 2. Extract the fields of each order: name, address, phone,
          PIN code, payment word and products.
  Part 3. Validate each order, flag anything unclear for manual
          review, and write the output files.
  Part 4. Fill in district and state from the PIN code, using a PIN
          code list (columns: pin_code, district, state).
  Part 5. Optional: use the owner's own override file for PIN codes
          the list cannot decide (--pin-code-overrides, same columns).

How to run on the fake test chats (from the project folder):
    python python/parse_whatsapp_orders.py --prepaid data/synthetic/synthetic_whatsapp_chat_prepaid.txt --cod data/synthetic/synthetic_whatsapp_chat_cod.txt --ignore-phones data/synthetic/synthetic_ignore_phones.txt --aliases data/synthetic/synthetic_product_aliases.csv --pin-codes data/synthetic/synthetic_pin_code_sample.csv --output data/processed/whatsapp_test_output

The PIN code file used above is a small hand-written sample for tests.
It is not the official India Post list.

Add --details to list every message with its line number and group.
What is printed on screen shows counts and line numbers only, never
message text, so it is safe to share. The output FILES hold the full
orders and must stay private when the chats are real.

Safety: the script refuses to write output inside the project folder,
except under data/processed/, which Git ignores.
"""

import argparse
import csv
import re
import secrets
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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

# Note on an order whose district and state come from the owner's override file.
OVERRIDE_NOTE = "pin_code_override"

# ---------------------------------------------------------------------
# Validation settings. The owner can change these in one place.
# ---------------------------------------------------------------------

# A COD line amount outside this range is flagged as a likely typing mistake.
MIN_LINE_AMOUNT = 50
MAX_LINE_AMOUNT = 10000

# The same phone and the same products within this many hours is a possible duplicate.
DUPLICATE_WINDOW_HOURS = 24

# Output may be written outside the project, or inside this one ignored folder.
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
ALLOWED_OUTPUT_FOLDER = PROJECT_FOLDER / "data" / "processed"


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
    # Filled in by validate_orders:
    order_id: str = ""      # new random ID
    payment_type: str = ""  # "prepaid", "cod" or "needs_review"
    flags: list = field(default_factory=list)   # reasons for manual review; empty if clean
    district_city: str = ""   # looked up from the PIN code, never read from the address
    state: str = ""           # looked up from the PIN code


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


def validate_order(order):
    """Set the payment type of one order and list its review flags.

    A flag means "a person must look at this". The parser never fixes
    or guesses a value.
    """
    flags = []

    # Payment type comes from the group. A payment word that disagrees
    # with the group means a person must decide.
    order.payment_type = order.source_group
    if order.payment_word and order.payment_word != order.source_group:
        order.payment_type = "needs_review"
        flags.append("payment_conflict")

    # Required fields.
    if not order.name:
        flags.append("missing_name")
    if not order.address:
        flags.append("missing_address")
    if not order.phones:
        flags.append("missing_phone")
    if not order.pin_codes:
        flags.append("missing_pin_code")
    if len(order.pin_codes) > 1:
        flags.append("multiple_pin_codes")   # the parser does not choose between them

    # Products.
    if any(item.quantity is None for item in order.items):
        flags.append("unreadable_product")
    if any(item.quantity is not None and item.product_code is None for item in order.items):
        flags.append("unknown_product")
    if any(item.quantity == 0 for item in order.items):
        flags.append("bad_quantity")

    # Amounts.
    amounts = [item.amount for item in order.items if item.amount is not None]
    if order.source_group == "cod" and len(amounts) < len(order.items):
        flags.append("cod_amount_missing")
    if order.source_group == "prepaid" and amounts:
        flags.append("prepaid_with_amount")
    if any(amount < MIN_LINE_AMOUNT or amount > MAX_LINE_AMOUNT for amount in amounts):
        flags.append("amount_out_of_range")

    order.flags = flags


def flag_possible_duplicates(orders):
    """Flag an order that repeats an earlier one within the time window.

    "Repeats" means the same main phone and the same products and
    quantities. The later order is flagged. Nothing is deleted.
    """
    window = timedelta(hours=DUPLICATE_WINDOW_HOURS)
    last_seen = {}

    for order in sorted(orders, key=lambda order: order.recorded_at):
        if not order.phones:
            continue   # without a phone we cannot tell who ordered
        products = sorted((item.product_code or item.raw_name, item.quantity or 0) for item in order.items)
        key = (order.phones[0], tuple(products))

        earlier = last_seen.get(key)
        if earlier is not None and order.recorded_at - earlier <= window:
            order.flags.append("possible_duplicate")
        last_seen[key] = order.recorded_at


def read_pin_codes(path):
    """Read the PIN code list: pin_code -> (district, state).

    The file has the columns pin_code, district, state.
    If one PIN code appears with two different districts or states,
    it is stored as None, which means "ambiguous: do not choose".
    """
    pin_codes = {}
    with open(path, encoding="utf-8-sig", newline="") as pin_file:
        for row in csv.DictReader(pin_file):
            pin_code = row["pin_code"].strip()
            place = (row["district"].strip(), row["state"].strip())
            if pin_code in pin_codes and pin_codes[pin_code] != place:
                pin_codes[pin_code] = None
            else:
                pin_codes[pin_code] = place
    return pin_codes


def read_pin_code_overrides(path):
    """Read the owner's override file: pin_code -> (district, state).

    The official list cannot decide some PIN codes. For those, the
    owner may write the correct district and state in this file. It is
    a decision made by a person, so the file must be exact: any unclear
    row stops the script instead of being skipped or guessed.
    """
    overrides = {}
    with open(path, encoding="utf-8-sig", newline="") as override_file:
        reader = csv.DictReader(override_file)
        missing = [name for name in ("pin_code", "district", "state") if name not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit("The override file is missing these columns: " + ", ".join(missing))
        for row_number, row in enumerate(reader, start=2):
            pin_code = re.sub(r"\s", "", row["pin_code"] or "")
            place = ((row["district"] or "").strip(), (row["state"] or "").strip())
            if not PIN_CODE.match(pin_code):
                raise SystemExit(f"Override file, row {row_number}: '{pin_code}' is not a 6-digit PIN code.")
            if not place[0] or not place[1]:
                raise SystemExit(f"Override file, row {row_number}: district and state must both be filled.")
            if overrides.get(pin_code, place) != place:
                raise SystemExit(f"Override file, row {row_number}: PIN code {pin_code} appears twice "
                                 "with different places.")
            overrides[pin_code] = place
    return overrides


def override_names_not_in_list(pin_codes, overrides):
    """District and state names in the override file that the PIN code list never uses.

    Such a name is often a typing mistake or a different spelling
    ("Chennai" and "CHENNAI" would count as two districts later).
    """
    districts = {place[0] for place in pin_codes.values() if place}
    states = {place[1] for place in pin_codes.values() if place}
    unknown = {district for district, _ in overrides.values() if district not in districts}
    unknown |= {state for _, state in overrides.values() if state not in states}
    return sorted(unknown)


def fill_district_and_state(orders, pin_codes, overrides=None):
    """Fill district and state from the PIN code list.

    Only an order with exactly one PIN code is looked up. A PIN code
    that is not in the list, or that maps to more than one place, is
    flagged and the fields stay empty.

    A PIN code in the owner's override file uses that place instead,
    and the order gets the note "pin_code_override".
    """
    for order in orders:
        if len(order.pin_codes) != 1:
            continue   # missing or several PIN codes: already flagged
        pin_code = order.pin_codes[0]
        if overrides and pin_code in overrides:
            order.district_city, order.state = overrides[pin_code]
            order.notes.append(OVERRIDE_NOTE)
        elif pin_code not in pin_codes:
            order.flags.append("pin_code_not_found")
        elif pin_codes[pin_code] is None:
            order.flags.append("pin_code_ambiguous")
        else:
            # The list leaves a district or state empty when the PIN code
            # covers more than one. Fill what is known and flag the rest.
            order.district_city, order.state = pin_codes[pin_code]
            if not order.district_city or not order.state:
                order.flags.append("pin_code_ambiguous")


def validate_orders(orders, pin_codes=None, overrides=None):
    """Validate all orders together and give each one a random ID.

    pin_codes is the PIN code list from read_pin_codes. Without it,
    district and state stay empty and no PIN code is looked up.
    overrides is the owner's file from read_pin_code_overrides.
    """
    for order in orders:
        validate_order(order)
    if pin_codes is not None:
        fill_district_and_state(orders, pin_codes, overrides)
    flag_possible_duplicates(orders)

    # Random IDs: never made from a phone number or a name.
    used_ids = set()
    for order in orders:
        while not order.order_id or order.order_id in used_ids:
            order.order_id = "W-" + secrets.token_hex(4)
        used_ids.add(order.order_id)
    return orders


def order_amount_and_basis(order):
    """Return the order amount and what kind of amount it is.

    Only a COD order with an amount on every line has a known amount,
    and that amount is what should be COLLECTED. It is not confirmed
    revenue. Everything else is honestly "unknown".
    """
    amounts = [item.amount for item in order.items]
    if order.payment_type == "cod" and all(amount is not None for amount in amounts):
        return sum(amounts), "cod_collectible"
    return None, "unknown"


def format_amount(amount):
    """Write 500.0 as "500", 99.5 as "99.5" and an unknown amount as empty."""
    if amount is None:
        return ""
    return str(int(amount)) if amount == int(amount) else str(amount)


def check_output_folder(folder):
    """Refuse an output folder that Git could pick up.

    Parser output holds customer details. It may be written outside the
    project, or inside data/processed/ (ignored by Git), nowhere else.
    """
    folder = Path(folder).resolve()
    inside_project = folder == PROJECT_FOLDER or PROJECT_FOLDER in folder.parents
    inside_allowed = folder == ALLOWED_OUTPUT_FOLDER or ALLOWED_OUTPUT_FOLDER in folder.parents
    if inside_project and not inside_allowed:
        raise SystemExit(
            f"Refusing to write output to {folder}.\n"
            "Parser output can hold customer details, and this folder is tracked by Git.\n"
            f"Use a private folder outside the project, or a folder under {ALLOWED_OUTPUT_FOLDER}."
        )
    return folder


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(header)
        writer.writerows(rows)


def write_outputs(orders, folder):
    """Write the four output files. Returns the folder they were written to."""
    folder = check_output_folder(folder)
    folder.mkdir(parents=True, exist_ok=True)

    order_rows = []
    item_rows = []
    review_rows = []
    unknown_names = Counter()

    for order in orders:
        amount, basis = order_amount_and_basis(order)
        flags = ";".join(order.flags)
        order_rows.append([
            order.order_id,
            order.recorded_at.strftime("%Y-%m-%d %H:%M:%S"),
            "whatsapp",
            order.source_group,
            order.payment_type,
            order.name,
            order.phones[0] if order.phones else "",
            order.address,
            order.pin_codes[0] if len(order.pin_codes) == 1 else "",   # never chosen from several
            order.district_city,
            order.state,
            format_amount(amount),
            basis,
            flags,
            ";".join(order.notes),
            order.line_number,
        ])
        for item in order.items:
            item_rows.append([
                order.order_id,
                item.product_code or "",
                item.raw_name,
                "" if item.quantity is None else item.quantity,
                format_amount(item.amount),
                "true" if item.defaulted else "false",
            ])
            if item.product_code is None:
                unknown_names[item.raw_name] += 1
        if order.flags:
            review_rows.append([order.order_id, order.source_group, order.line_number, flags, order.raw_message])

    write_csv(folder / "whatsapp_orders.csv",
              ["order_id", "order_datetime", "sales_channel", "source_group", "payment_type",
               "customer_name", "phone", "address", "pin_code", "district_city", "state",
               "order_amount", "amount_basis", "review_flags", "notes", "source_line"],
              order_rows)
    write_csv(folder / "whatsapp_order_items.csv",
              ["order_id", "product_code", "raw_name", "quantity", "cod_collectible_amount", "product_defaulted"],
              item_rows)
    write_csv(folder / "whatsapp_review_queue.csv",
              ["order_id", "source_group", "source_line", "review_flags", "raw_message"],
              review_rows)
    write_csv(folder / "whatsapp_unknown_products.csv",
              ["raw_name", "count"],
              unknown_names.most_common())
    return folder


def main():
    arguments = argparse.ArgumentParser(description="Parse exported WhatsApp order chats.")
    arguments.add_argument("--prepaid", help="exported chat file of the Prepaid group")
    arguments.add_argument("--cod", help="exported chat file of the COD group")
    arguments.add_argument("--ignore-phones", help="file with phone numbers to ignore, one per line")
    arguments.add_argument("--aliases", help="alias file: product spellings and their codes")
    arguments.add_argument("--pin-codes", help="PIN code list with the columns pin_code, district, state")
    arguments.add_argument("--pin-code-overrides",
                           help="your own file for PIN codes the list cannot decide (needs --pin-codes)")
    arguments.add_argument("--output", help="folder for the output files (needs --aliases)")
    arguments.add_argument("--details", action="store_true", help="list every message (no message text)")
    options = arguments.parse_args()

    if options.output and not options.aliases:
        raise SystemExit("--output needs --aliases, because products are read from the alias file.")
    if options.pin_code_overrides and not options.pin_codes:
        raise SystemExit("--pin-code-overrides needs --pin-codes.")
    if options.output:
        check_output_folder(options.output)   # fail early, before any work is done

    ignore_phones = read_ignore_phones(options.ignore_phones)
    aliases = read_aliases(options.aliases) if options.aliases else None
    orders = []

    for source_group, path in (("prepaid", options.prepaid), ("cod", options.cod)):
        if path is None:
            continue
        messages = parse_chat(path, source_group, ignore_phones)

        counts = Counter(message.category for message in messages)
        print(f"{source_group}: {len(messages)} messages -> "
              f"{counts['order']} orders, {counts['other']} other, {counts['skipped']} skipped")

        if options.details:
            for message in messages:
                line_count = len(message.text.split("\n"))
                copied = " (copied order)" if message.copied_time else ""
                print(f"  line {message.line_number:>5}  {message.category:<8} {line_count} lines{copied}")

        if aliases is not None:
            orders += [
                extract_order(message, aliases, ignore_phones)
                for message in messages if message.category == "order"
            ]

    if aliases is None:
        return

    # Both groups are validated together, so a duplicate is found even
    # when the two copies are in different groups.
    pin_codes = read_pin_codes(options.pin_codes) if options.pin_codes else None
    overrides = read_pin_code_overrides(options.pin_code_overrides) if options.pin_code_overrides else None
    validate_orders(orders, pin_codes, overrides)

    flagged = [order for order in orders if order.flags]
    all_items = [item for order in orders for item in order.items]
    print(f"\norders: {len(orders)} -> {len(orders) - len(flagged)} clean, {len(flagged)} need review")
    print(f"product lines: {len(all_items)}, "
          f"orders defaulted to 1 CXE: {sum(1 for o in orders if DEFAULT_PRODUCT_NOTE in o.notes)}")
    flag_counts = Counter(flag for order in orders for flag in order.flags)
    for flag, count in sorted(flag_counts.items()):
        print(f"  {flag}: {count}")
    if pin_codes is None:
        print("district and state: not filled (no --pin-codes file was given)")
    else:
        print(f"district and state: filled for {sum(1 for o in orders if o.district_city)} of {len(orders)} orders")
    if overrides is not None:
        print(f"PIN code overrides: {len(overrides)} in your file, "
              f"used for {sum(1 for o in orders if OVERRIDE_NOTE in o.notes)} orders")
        unknown_names = override_names_not_in_list(pin_codes, overrides)
        if unknown_names:
            print("  check the spelling: these names are not used in the PIN code list: " + ", ".join(unknown_names))

    if options.output:
        folder = write_outputs(orders, options.output)
        print(f"\nfour files written to {folder}")


if __name__ == "__main__":
    main()
