"""Data quality audit: count the problems in the eight tables.

The audit only LOOKS. It reads the tables through a read-only
connection, changes nothing, and returns one report table:

    table, check, rows_checked, rows_found, share

"share" is rows_found divided by rows_checked (0.05 = 5%).

Not every finding is an error. Some are facts the analysis must know,
for example "orders with no amount": WhatsApp prepaid orders have no
recorded amount. The cleaning rules (phase 3.3) decide what to do with
each finding.

How to run (from the project folder):
    python python/audit_data_quality.py --database marketpulse_synthetic

Options:
    --schema         schema to audit (default: public)
    --period-start   first day of the data, for example 2025-01-01
    --period-end     last day of the data, for example 2025-12-31
    --output         folder for data_quality_report.csv

What is printed shows table names, check names and counts only, never a
value from a row. So the result of a run on the private database is
safe to share. The report file holds the same counts, but it is still
business information: the script writes it only outside the project or
under data/processed/ (ignored by Git).
"""

import argparse

import numpy as np
import pandas as pd

from database import ConnectionProblem, connect, kind_of_data, read_tables
from parse_whatsapp_orders import check_output_folder

REPORT_COLUMNS = ["table", "check", "rows_checked", "rows_found", "share"]
REPORT_FILE = "data_quality_report.csv"

# Columns that must be unique in each table.
KEYS = {
    "products": ["product_code"],
    "product_aliases": ["alias"],
    "customers": ["customer_id"],
    "orders": ["order_id"],
    "shipments": ["shipment_id"],
    "ad_campaigns": ["campaign_id"],
    "ad_performance": ["campaign_id", "report_date"],
}

# Columns that hold codes, and the codes they may hold.
ALLOWED_VALUES = {
    ("orders", "sales_channel"): {"whatsapp", "shopify"},
    ("orders", "payment_type"): {"prepaid", "cod", "needs_review"},
    ("orders", "amount_basis"): {"cod_collectible", "shopify_total", "estimated", "unknown"},
    ("product_aliases", "source"): {"whatsapp", "shopify"},
    ("shipments", "courier"): {"speed_post", "delhivery"},
    ("shipments", "delivery_status"): {"delivered", "returned", "unknown"},
}

# Date columns that can never be in the future.
DATE_COLUMNS = [
    ("orders", "order_datetime"),
    ("orders", "cancelled_at"),
    ("shipments", "delivered_date"),
    ("ad_performance", "report_date"),
]

# Date columns that must lie inside the data period, when one is given.
# Delivery dates are left out: an order from the last day of the period
# is delivered after it.
PERIOD_COLUMNS = [("orders", "order_datetime"), ("ad_performance", "report_date")]

# Numbers checked for unusual values with the IQR rule.
NUMBER_COLUMNS = [
    ("order_items", "quantity"),
    ("order_items", "line_amount"),
    ("orders", "order_amount"),
    ("shipments", "shipping_cost"),
    ("ad_performance", "amount_spent_inr"),
]

# Two amounts closer than this are the same (half a paisa).
TOLERANCE = 0.005


class Report:
    """Collects the result of every check, one row each."""

    def __init__(self):
        self.rows = []

    def add(self, table, check, rows_checked, rows_found):
        rows_checked, rows_found = int(rows_checked), int(rows_found)
        share = round(rows_found / rows_checked, 4) if rows_checked else 0.0
        self.rows.append([table, check, rows_checked, rows_found, share])

    def to_frame(self):
        return pd.DataFrame(self.rows, columns=REPORT_COLUMNS)


def is_missing(column):
    """True for an empty value: missing, or text with nothing but spaces."""
    missing = column.isna()
    if column.dtype == object:
        missing = missing | (column.notna() & column.astype(str).str.strip().eq(""))
    return missing


def count_outliers(values):
    """Count the values outside the usual range, using the IQR rule.

    Q1 and Q3 are the values a quarter and three quarters of the way up
    the sorted list. The IQR (interquartile range) is Q3 - Q1. A value
    more than 1.5 IQR below Q1 or above Q3 is called unusual.

    Unusual is not wrong. A customer can really buy ten creams. These
    values are counted so a person looks at them. They are never removed.
    """
    numbers = pd.Series(values).dropna().to_numpy(dtype=float)
    if len(numbers) < 4:
        return 0   # too few values to say what is usual
    q1, q3 = np.percentile(numbers, [25, 75])
    spread = q3 - q1
    return int(((numbers < q1 - 1.5 * spread) | (numbers > q3 + 1.5 * spread)).sum())


def check_missing_values(tables, report):
    """Every column with empty values. Columns with none are not listed."""
    for name, table in tables.items():
        for column in table.columns:
            found = is_missing(table[column]).sum()
            if found:
                report.add(name, f"missing {column}", len(table), found)


def check_duplicates(tables, report):
    for name, key in KEYS.items():
        table = tables[name]
        report.add(name, "duplicate " + " + ".join(key), len(table), table.duplicated(key).sum())
    phones = tables["customers"]["phone"].dropna()
    report.add("customers", "duplicate phone", len(phones), phones.duplicated().sum())


def check_review_flags(tables, report):
    """Split "flag_a;flag_b" into single flags and count each one."""
    orders = tables["orders"]
    flags = orders["review_flags"].dropna().str.split(";").explode().str.strip()
    flags = flags[flags.notna() & (flags != "")]
    # One row per order and flag, so a flag written twice counts once.
    pairs = flags.rename("flag").reset_index().drop_duplicates()
    report.add("orders", "orders with any review flag", len(orders), pairs["index"].nunique())
    for flag, count in pairs["flag"].value_counts().sort_index().items():
        report.add("orders", f"flag {flag}", len(orders), count)


def check_codes(tables, report):
    for (name, column), allowed in ALLOWED_VALUES.items():
        values = tables[name][column].dropna()
        report.add(name, f"unexpected {column} value", len(values), (~values.isin(allowed)).sum())


def check_dates(tables, report, today, period):
    for name, column in DATE_COLUMNS:
        values = pd.to_datetime(tables[name][column]).dropna()
        report.add(name, f"{column} in the future", len(values), (values > today).sum())

    if period is not None:
        start, end = period
        after_end = end + pd.Timedelta(days=1)   # the whole last day counts
        for name, column in PERIOD_COLUMNS:
            values = pd.to_datetime(tables[name][column]).dropna()
            outside = (values < start) | (values >= after_end)
            report.add(name, f"{column} outside the period", len(values), outside.sum())

    orders = tables["orders"]
    cancelled = orders.dropna(subset=["cancelled_at"])
    report.add("orders", "cancelled before ordered", len(cancelled),
               (cancelled["cancelled_at"] < cancelled["order_datetime"]).sum())

    delivered = tables["shipments"].dropna(subset=["delivered_date"]).merge(
        orders[["order_id", "order_datetime"]], on="order_id")
    too_early = pd.to_datetime(delivered["delivered_date"]) < delivered["order_datetime"].dt.normalize()
    report.add("shipments", "delivered before ordered", len(delivered), too_early.sum())


def check_links(tables, report):
    """Rows that should point to another table, and rows nothing points to."""
    orders, items, shipments = tables["orders"], tables["order_items"], tables["shipments"]
    customers, products = tables["customers"], tables["products"]
    campaigns, ads = tables["ad_campaigns"], tables["ad_performance"]

    report.add("orders", "orders without items", len(orders), (~orders["order_id"].isin(items["order_id"])).sum())
    report.add("orders", "orders without a shipment", len(orders),
               (~orders["order_id"].isin(shipments["order_id"])).sum())
    report.add("order_items", "items of unknown orders", len(items),
               (~items["order_id"].isin(orders["order_id"])).sum())
    report.add("order_items", "items of unknown products", len(items),
               (~items["product_code"].isin(products["product_code"])).sum())
    report.add("shipments", "shipments of unknown orders", len(shipments),
               (~shipments["order_id"].isin(orders["order_id"])).sum())
    cancelled_ids = orders.loc[orders["cancelled_at"].notna(), "order_id"]
    report.add("shipments", "shipments of cancelled orders", len(shipments),
               shipments["order_id"].isin(cancelled_ids).sum())
    report.add("customers", "customers without orders", len(customers),
               (~customers["customer_id"].isin(orders["customer_id"])).sum())
    report.add("ad_campaigns", "campaigns without any day", len(campaigns),
               (~campaigns["campaign_id"].isin(ads["campaign_id"])).sum())


def check_amounts(tables, report):
    orders, items, shipments = tables["orders"], tables["order_items"], tables["shipments"]

    report.add("orders", "cancelled orders", len(orders), orders["cancelled_at"].notna().sum())
    report.add("orders", "orders with no amount", len(orders), orders["order_amount"].isna().sum())

    # The honesty rule of the schema: an amount exists exactly when its basis is known.
    broken = (orders["amount_basis"] == "unknown") != orders["order_amount"].isna()
    report.add("orders", "amount rule broken", len(orders), broken.sum())

    # A COD amount to collect is the sum of its product lines.
    cod = orders[orders["amount_basis"] == "cod_collectible"].set_index("order_id")["order_amount"]
    cod_items = items[items["order_id"].isin(cod.index)]
    line_totals = cod_items.groupby("order_id")["line_amount"].sum().reindex(cod.index)
    line_missing = (cod_items.assign(gap=cod_items["line_amount"].isna())
                    .groupby("order_id")["gap"].any().reindex(cod.index, fill_value=True))
    differs = line_missing | line_totals.isna() | ((cod - line_totals).abs() > TOLERANCE)
    report.add("orders", "COD lines do not add up to the order amount", len(cod), differs.sum())

    # Money received, from courier records.
    paid = shipments.dropna(subset=["cod_amount_received"]).merge(
        orders[["order_id", "payment_type", "order_amount"]], on="order_id")
    above = paid["order_amount"].notna() & (paid["cod_amount_received"] > paid["order_amount"] + TOLERANCE)
    report.add("shipments", "COD received above the amount to collect", len(paid), above.sum())
    report.add("shipments", "money received on a non-COD order", len(paid), (paid["payment_type"] != "cod").sum())


def check_unusual_numbers(tables, report):
    for name, column in NUMBER_COLUMNS:
        values = tables[name][column].dropna()
        report.add(name, f"unusual {column} (IQR rule)", len(values), count_outliers(values))


def check_ads(tables, report):
    ads = tables["ad_performance"]
    report.add("ad_performance", "reach above impressions", len(ads), (ads["reach"] > ads["impressions"]).sum())
    report.add("ad_performance", "link clicks above all clicks", len(ads),
               (ads["link_clicks"] > ads["clicks_all"]).sum())
    report.add("ad_performance", "results without an indicator", len(ads),
               ((ads["results"].fillna(0) > 0) & ads["result_indicator"].isna()).sum())


def audit(tables, today=None, period=None):
    """Run every check and return the report as a DataFrame.

    tables  the eight tables, as read_tables() returns them
    today   dates after this moment are "in the future" (default: now)
    period  (first day, last day) of the data, or None to skip that check
    """
    today = pd.Timestamp.now() if today is None else pd.Timestamp(today)
    if period is not None:
        period = (pd.Timestamp(period[0]), pd.Timestamp(period[1]))
    report = Report()
    check_missing_values(tables, report)
    check_duplicates(tables, report)
    check_review_flags(tables, report)
    check_codes(tables, report)
    check_dates(tables, report, today, period)
    check_links(tables, report)
    check_amounts(tables, report)
    check_unusual_numbers(tables, report)
    check_ads(tables, report)
    return report.to_frame()


def print_report(report):
    """Print the checks that found something, then how many found nothing."""
    found = report[report["rows_found"] > 0]
    print(f"{'table':<16}{'check':<46}{'found':>8}{'of rows':>9}{'share':>8}")
    for row in found.itertuples(index=False):
        print(f"{row.table:<16}{row.check:<46}{row.rows_found:>8}{row.rows_checked:>9}{row.share:>8.1%}")
    print(f"\n{len(report)} checks: {len(found)} found something, {len(report) - len(found)} found nothing")


def write_report(report, folder):
    folder = check_output_folder(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / REPORT_FILE
    report.to_csv(path, index=False, lineterminator="\n")
    return path


def main():
    arguments = argparse.ArgumentParser(description="Count data quality problems. Changes nothing.")
    arguments.add_argument("--database", required=True, help="for example marketpulse_synthetic")
    arguments.add_argument("--schema", default="public", help="schema to audit (default: public)")
    arguments.add_argument("--period-start", help="first day of the data, for example 2025-01-01")
    arguments.add_argument("--period-end", help="last day of the data, for example 2025-12-31")
    arguments.add_argument("--output", help=f"folder for {REPORT_FILE}")
    options = arguments.parse_args()

    if bool(options.period_start) != bool(options.period_end):
        raise SystemExit("Give both --period-start and --period-end, or neither.")
    period = (options.period_start, options.period_end) if options.period_start else None
    if options.output:
        check_output_folder(options.output)   # fail early, before any work is done

    try:
        engine = connect(options.database)   # read-only
    except ConnectionProblem as problem:
        raise SystemExit(str(problem))
    try:
        tables = read_tables(engine, options.schema)
    except ValueError as problem:
        raise SystemExit(f"Could not read schema '{options.schema}': {problem}")
    finally:
        engine.dispose()

    print(f"data quality audit: {options.database}, schema {options.schema}")
    print(f"  {kind_of_data(options.database)}")
    print(f"  period: {period[0]} to {period[1]}" if period else "  period: not given, so not checked")
    print()
    report = audit(tables, period=period)
    print_report(report)
    if options.output:
        print(f"report written to {write_report(report, options.output)}")


if __name__ == "__main__":
    main()
