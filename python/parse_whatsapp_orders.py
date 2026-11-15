"""Turn exported WhatsApp chats into order tables.

Design: docs/whatsapp_parser_plan.md (version 2).

This script runs only on the owner's computer. It uses plain Python.
It never sends data anywhere.

PART 1 (this version) does two jobs:
  1. Split a chat file into messages.
  2. Sort each message into "skipped", "order" or "other".
Later parts will extract the fields and validate them.

How to run on the fake test chats (from the project folder):
    python python/parse_whatsapp_orders.py --prepaid data/synthetic/synthetic_whatsapp_chat_prepaid.txt --cod data/synthetic/synthetic_whatsapp_chat_cod.txt --ignore-phones data/synthetic/synthetic_ignore_phones.txt

Add --details to list every message with its line number and group.
The details show no message text, so they are safe to share.
"""

import argparse
import re
from dataclasses import dataclass
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
    arguments.add_argument("--details", action="store_true", help="list every message (no message text)")
    options = arguments.parse_args()

    ignore_phones = read_ignore_phones(options.ignore_phones)

    for source_group, path in (("prepaid", options.prepaid), ("cod", options.cod)):
        if path is None:
            continue
        messages = parse_chat(path, source_group, ignore_phones)

        counts = {"order": 0, "other": 0, "skipped": 0}
        for message in messages:
            counts[message.category] += 1

        print(f"{source_group}: {len(messages)} messages -> "
              f"{counts['order']} orders, {counts['other']} other, {counts['skipped']} skipped")

        if options.details:
            for message in messages:
                line_count = len(message.text.split("\n"))
                copied = " (copied order)" if message.copied_time else ""
                print(f"  line {message.line_number:>5}  {message.category:<8} {line_count} lines{copied}")


if __name__ == "__main__":
    main()
