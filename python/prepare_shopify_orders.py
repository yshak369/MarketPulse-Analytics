"""Clean a Shopify orders export for the database.

Input:  the orders export from Shopify admin (Orders > Export > CSV).
        Shopify writes ONE ROW PER PRODUCT LINE. Order details (total,
        status, address, phone) appear only on the first row of each order.
Output: files for sql/05_load_shopify_orders.sql:
          shopify_orders.csv            one row per order
          shopify_order_items.csv       one row per product line
          shopify_unknown_products.csv  product titles not in the alias file

Design: docs/schema_design.md (orders, order_items, product_aliases).

How to run on the fake export (from the project folder):
    python python/prepare_shopify_orders.py --input data/synthetic/synthetic_shopify_orders_export.csv --aliases data/synthetic/synthetic_product_aliases.csv --pin-codes data/synthetic/synthetic_pin_code_sample.csv --output data/processed/shopify_test_output

The real export holds customer names, addresses and phones. Keep it, and
the output, outside this project or under data/processed/ (ignored by
Git). What is printed on screen shows counts and payment method names only.

Rules:
  * Order IDs are fixed: Shopify order #1001 becomes S-1001, so loading
    the same order again updates it instead of adding a copy.
  * Phone: Shipping Phone, then Billing Phone, then Phone. Cleaned the
    same way as WhatsApp phones, so one phone = one customer in both.
  * Payment type: "Cash on Delivery" or the word "COD" in Payment Method
    means cod. A non-COD method on a paid or refunded order means
    prepaid. Anything else is needs_review. Check the printed list of
    payment methods the first time you run this on real data.
  * order_amount is Shopify's Total, with amount_basis shopify_total.
    For a COD order that is the amount to COLLECT, not money received.
  * Cancelled and refunded orders are kept, with their status.
  * District and state come from the PIN code list, as for WhatsApp.
  * Unknown product titles are flagged, never matched to a similar name.
"""

import argparse
import csv
import re
from collections import Counter

import pandas as pd

from parse_whatsapp_orders import (
    PHONE, PIN_CODE, check_output_folder, format_amount, normalise_product_name,
    read_aliases, read_pin_codes, write_csv,
)

REQUIRED_COLUMNS = [
    "Name", "Created at", "Financial Status", "Fulfillment Status", "Total", "Cancelled at",
    "Payment Method", "Refunded Amount", "Lineitem quantity", "Lineitem name", "Lineitem price",
    "Shipping Name", "Shipping Address1", "Shipping Address2", "Shipping City", "Shipping Zip",
    "Shipping Phone", "Billing Name", "Billing Phone", "Phone",
]

# Columns to try, in order, for the customer's phone.
PHONE_COLUMNS = ["Shipping Phone", "Billing Phone", "Phone"]

# Financial statuses that show the money was paid online at some point.
PAID_STATUSES = {"paid", "partially_paid", "partially_refunded", "refunded"}

COD_WORDS = re.compile(r"cash on delivery|\bcod\b", re.IGNORECASE)

ORDER_COLUMNS = [
    "order_id", "order_datetime", "sales_channel", "payment_type", "customer_name", "phone",
    "address", "pin_code", "district_city", "state", "order_amount", "amount_basis",
    "financial_status", "fulfillment_status", "cancelled_at", "review_flags", "notes",
]
ITEM_COLUMNS = ["order_id", "product_code", "raw_name", "quantity", "line_amount", "product_defaulted"]


class ExportProblem(Exception):
    """The export cannot be cleaned without guessing. A person must look."""


def read_export(path):
    """Read the export as text, so nothing is changed silently."""
    export = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    export.columns = [column.strip() for column in export.columns]
    missing = [column for column in REQUIRED_COLUMNS if column not in export.columns]
    if missing:
        raise ExportProblem("The export is missing these columns: " + ", ".join(missing))
    return export.apply(lambda column: column.str.strip())


def clean_phone(text):
    """Return a 10-digit phone, "" when blank, or None when it cannot be read."""
    digits = re.sub(r"[\s\-()]", "", text)
    if not digits:
        return ""
    match = PHONE.match(digits)
    return match.group(1) if match else None


def to_local_time(text):
    """Shopify writes "2025-03-05 10:15:00 +0530". Store Indian local time without the offset."""
    if not text:
        return ""
    moment = pd.to_datetime(text, format="%Y-%m-%d %H:%M:%S %z")
    return moment.tz_convert("Asia/Kolkata").strftime("%Y-%m-%d %H:%M:%S")


def payment_type_of(method, financial_status):
    """Decide cod, prepaid or needs_review. Never guessed from anything else."""
    if COD_WORDS.search(method):
        return "cod"
    if method and financial_status.lower() in PAID_STATUSES:
        return "prepaid"
    return "needs_review"


def to_number(text, what, order_name):
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        raise ExportProblem(f"Order {order_name}: unreadable {what} '{text}'")


def build_orders(export, aliases, pin_codes=None):
    """Group the rows by order and return (orders, items, unknown titles, payment methods)."""
    orders = []
    items = []
    unknown_titles = Counter()
    payment_methods = Counter()

    for order_name, rows in export.groupby("Name", sort=False):
        first = rows.iloc[0]   # Shopify writes order fields on the first row only
        number = order_name.lstrip("#").strip()
        if not number:
            raise ExportProblem("A row has no order Name, so it cannot be grouped into an order.")
        order_id = "S-" + number
        flags = []
        notes = []

        # Phone: the first column that has one.
        phone = ""
        for column in PHONE_COLUMNS:
            cleaned = clean_phone(first[column])
            if cleaned is None:
                flags.append("invalid_phone")
                continue
            if cleaned:
                phone = cleaned
                break
        if not phone and "invalid_phone" not in flags:
            flags.append("missing_phone")

        # Payment type.
        method = first["Payment Method"]
        payment_methods[method or "(blank)"] += 1
        payment_type = payment_type_of(method, first["Financial Status"])
        if payment_type == "needs_review":
            flags.append("payment_unclear")

        # Location: PIN code, then district and state from the PIN code list.
        pin_code = re.sub(r"\s", "", first["Shipping Zip"])
        district = state = ""
        if not PIN_CODE.match(pin_code):
            flags.append("missing_pin_code" if not pin_code else "invalid_pin_code")
            pin_code = ""
        elif pin_codes is not None:
            place = pin_codes.get(pin_code, "not found")
            if place == "not found":
                flags.append("pin_code_not_found")
            elif place is None or not place[0] or not place[1]:
                flags.append("pin_code_ambiguous")
                if place:
                    district, state = place
            else:
                district, state = place

        # Amount: Shopify's own total.
        total = to_number(first["Total"], "Total", order_name)
        refunded = to_number(first["Refunded Amount"], "Refunded Amount", order_name) or 0
        if refunded:
            notes.append("refunded_amount=" + format_amount(refunded))

        # Product lines.
        for _, row in rows.iterrows():
            raw_name = normalise_product_name(row["Lineitem name"])
            product_code = aliases.get(raw_name)
            if product_code is None:
                unknown_titles[raw_name] += 1
                if "unknown_product" not in flags:
                    flags.append("unknown_product")
            quantity_text = row["Lineitem quantity"]
            quantity = int(quantity_text) if quantity_text.isdigit() else None
            if quantity is None or quantity < 1:
                if "bad_quantity" not in flags:
                    flags.append("bad_quantity")
            price = to_number(row["Lineitem price"], "Lineitem price", order_name)
            line_amount = quantity * price if quantity is not None and price is not None else None
            items.append([order_id, product_code or "", raw_name, "" if quantity is None else quantity,
                          format_amount(line_amount), "false"])

        address_parts = [first["Shipping Address1"], first["Shipping Address2"], first["Shipping City"]]
        orders.append([
            order_id,
            to_local_time(first["Created at"]),
            "shopify",
            payment_type,
            first["Shipping Name"] or first["Billing Name"],
            phone,
            ", ".join(part for part in address_parts if part),
            pin_code,
            district,
            state,
            format_amount(total),
            "shopify_total" if total is not None else "unknown",
            first["Financial Status"],
            first["Fulfillment Status"],
            to_local_time(first["Cancelled at"]),
            ";".join(flags),
            ";".join(notes),
        ])

    return orders, items, unknown_titles, payment_methods


def write_outputs(orders, items, unknown_titles, folder):
    folder = check_output_folder(folder)
    folder.mkdir(parents=True, exist_ok=True)
    write_csv(folder / "shopify_orders.csv", ORDER_COLUMNS, orders)
    write_csv(folder / "shopify_order_items.csv", ITEM_COLUMNS, items)
    write_csv(folder / "shopify_unknown_products.csv", ["raw_name", "count"], unknown_titles.most_common())
    return folder


def main():
    arguments = argparse.ArgumentParser(description="Clean a Shopify orders export.")
    arguments.add_argument("--input", required=True, help="the Shopify orders export (CSV)")
    arguments.add_argument("--aliases", required=True, help="alias file: product titles and their codes")
    arguments.add_argument("--pin-codes", help="PIN code list with the columns pin_code, district, state")
    arguments.add_argument("--output", required=True, help="folder for the output files")
    options = arguments.parse_args()

    check_output_folder(options.output)   # fail early, before any work is done
    aliases = read_aliases(options.aliases)
    pin_codes = read_pin_codes(options.pin_codes) if options.pin_codes else None
    try:
        export = read_export(options.input)
        orders, items, unknown_titles, payment_methods = build_orders(export, aliases, pin_codes)
    except ExportProblem as problem:
        raise SystemExit(f"Stopped: {problem}")

    flagged = [order for order in orders if order[ORDER_COLUMNS.index("review_flags")]]
    payment_types = Counter(order[ORDER_COLUMNS.index("payment_type")] for order in orders)
    flag_counts = Counter(flag for order in flagged for flag in order[ORDER_COLUMNS.index("review_flags")].split(";"))

    print(f"export rows read:  {len(export)}")
    print(f"orders:            {len(orders)} -> {len(orders) - len(flagged)} clean, {len(flagged)} need review")
    print(f"product lines:     {len(items)}")
    print("payment types:     " + ", ".join(f"{name} {count}" for name, count in sorted(payment_types.items())))
    for flag, count in sorted(flag_counts.items()):
        print(f"  {flag}: {count}")
    print("payment methods seen (check the COD rule against these):")
    for method, count in payment_methods.most_common():
        print(f"  {count:>5}  {method}")
    if pin_codes is None:
        print("district and state: not filled (no --pin-codes file was given)")

    folder = write_outputs(orders, items, unknown_titles, options.output)
    print(f"three files written to {folder}")


if __name__ == "__main__":
    main()
