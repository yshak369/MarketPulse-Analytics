"""Clean the raw tables into analysis-ready tables.

The raw tables are never changed. Every function takes pandas tables
and returns new ones. Phase 3.5 writes the result to the "clean" schema.

The rules (approved by the owner, November 2026; see docs/data_cleaning.md):

  Rows
    * No row is deleted. An order that must not be counted keeps its row,
      with include_in_analysis = false and an exclusion_reason.
    * Cancelled orders are not counted (reason "cancelled").
    * Possible duplicates ARE counted. They keep their flag, so any
      figure can still be shown with and without them.
    * Orders with payment type "needs_review" are counted. The payment
      type is never guessed.

  Privacy
    * No name, phone, address, PIN code or free-text note leaves this
      step. A note can hold a second phone number, so the useful facts
      in notes become their own columns first.

  Places
    * District and state are trimmed and written in one style
      ("ERNAKULAM" and "Ernakulam" become "Ernakulam"). Empty stays empty.

  Customers
    * An order flagged missing_phone or invalid_phone has no known
      customer: customer_identified = false. Such orders count as
      orders, but not in repeat-customer figures.

  Products
    * Orders with no product line were set to 1 cream (CXE) by the
      owner's rule. They are counted, and marked with product_defaulted.

  Amounts (the most important part)
    * order_amount is the amount as RECORDED. It is never changed.
    * amount_reliable = false when the amount is missing or an amount
      flag is set. A COD amount is the amount to COLLECT, not revenue.
    * estimated_order_value is worked out from the price list:
        WhatsApp COD lines      quantity x COD price
        WhatsApp Prepaid lines  quantity x normal (Prepaid) price
        Shopify lines           quantity x normal price (the website price)
        payment "needs_review"  unknown: the right price is unknown
      An order where only some COD products had an amount
      (cod_amount_partial) is NEVER estimated: its one amount may be the
      total for the whole order. A missing price makes the estimate unknown.
    * order_value is the recorded amount when it is reliable, otherwise
      the estimate. value_basis says which: recorded, estimated or unknown.
"""

import numpy as np
import pandas as pd

# Columns that identify a person, or can (notes). Never in clean tables.
PERSONAL_COLUMNS = ["customer_name", "phone", "address", "pin_code", "notes"]

# Flags that make a recorded amount unreliable.
AMOUNT_FLAGS = {"amount_out_of_range", "cod_amount_missing", "cod_amount_partial", "prepaid_with_amount"}

# Flags that forbid an estimate: one bracket may hold the whole order's total.
NO_ESTIMATE_FLAGS = {"cod_amount_partial"}

# Flags that mean the customer is not known.
NO_CUSTOMER_FLAGS = {"missing_phone", "invalid_phone"}

# Small words written in lower case inside place names ("Daman and Diu").
SMALL_WORDS = {"and", "of", "the"}

ORDER_COLUMNS = [
    "order_id", "customer_id", "customer_identified", "customer_order_number", "is_repeat_order",
    "order_datetime", "order_date", "order_month", "week_start", "weekday", "hour",
    "sales_channel", "payment_type", "district_city", "state", "district_from_override",
    "units", "product_lines", "product_defaulted",
    "order_amount", "amount_basis", "amount_reliable",
    "estimated_order_value", "estimated_order_cost", "order_value", "value_basis",
    "financial_status", "fulfillment_status", "is_cancelled", "refunded_amount",
    "review_flags", "include_in_analysis", "exclusion_reason",
]

ITEM_COLUMNS = [
    "order_item_id", "order_id", "product_code", "product_name", "quantity", "line_amount",
    "product_defaulted", "price_used", "estimated_line_value", "estimated_line_cost",
    "include_in_analysis",
]

CUSTOMER_COLUMNS = [
    "customer_id", "customer_identified", "first_order_date", "last_order_date",
    "orders_counted", "is_repeat_customer",
]

AD_COLUMNS = [
    "campaign_id", "campaign_name", "report_date", "week_start", "report_month", "weekday",
    "amount_spent_inr", "impressions", "reach", "link_clicks", "clicks_all", "landing_page_views",
    "results", "result_type", "result_indicator",
]

SHIPMENT_COLUMNS = [
    "shipment_id", "order_id", "courier", "delivery_status", "delivered_date", "delivery_days",
    "delivery_date_problem", "cod_amount_received", "shipping_cost", "include_in_analysis",
]

# Meta's long "result indicator" -> a short result type. Checked in order.
# Results of different types are never added together.
RESULT_TYPES = [
    ("messaging_conversation_started", "messaging_conversation"),
    ("link_click", "link_click"),
    ("post_engagement", "post_engagement"),
]


def flag_sets(review_flags):
    """Turn "flag_a;flag_b" into {"flag_a", "flag_b"}, one set per order."""
    return review_flags.fillna("").astype(str).apply(
        lambda text: {flag.strip() for flag in text.split(";") if flag.strip()})


def has_any_flag(flags, wanted):
    return flags.apply(lambda found: bool(found & wanted))


def tidy_place_name(value):
    """Trim, use single spaces and one letter style. Empty becomes missing."""
    if value is None or pd.isna(value):
        return pd.NA
    words = str(value).split()
    if not words:
        return pd.NA
    tidy = [word.lower() if position and word.lower() in SMALL_WORDS else word.title()
            for position, word in enumerate(words)]
    return " ".join(tidy)


def line_prices(items, orders, products):
    """The normal price for each product line, following the rules above.

    Returns the items with three more columns: price_used,
    estimated_line_value and estimated_line_cost.
    """
    lines = items.merge(orders[["order_id", "sales_channel", "payment_type"]], on="order_id", how="left")
    lines = lines.merge(products[["product_code", "product_name", "selling_price", "cod_price", "unit_cost"]],
                        on="product_code", how="left")
    whatsapp = lines["sales_channel"] == "whatsapp"
    price = np.select(
        [whatsapp & (lines["payment_type"] == "cod"),
         whatsapp & (lines["payment_type"] == "prepaid"),
         lines["sales_channel"] == "shopify"],
        [lines["cod_price"], lines["selling_price"], lines["selling_price"]],
        default=np.nan,
    )
    lines["price_used"] = pd.to_numeric(pd.Series(price, index=lines.index), errors="coerce")
    lines["estimated_line_value"] = lines["quantity"] * lines["price_used"]
    lines["estimated_line_cost"] = lines["quantity"] * lines["unit_cost"]
    return lines


def total_or_unknown(lines, column):
    """Sum a column per order. Unknown when any line is unknown."""
    grouped = lines.groupby("order_id")[column]
    total = grouped.sum(min_count=1)
    return total.mask(grouped.apply(lambda values: values.isna().any()))


def clean_orders(orders, items, products, customers=None):
    """Return the clean orders table. The input tables are not changed.

    customers is not used for any value. It is accepted so all clean_*
    functions can be called the same way.
    """
    clean = orders.copy()
    flags = flag_sets(clean["review_flags"])
    notes = clean["notes"].fillna("").astype(str)

    # Rows: cancelled orders are kept but not counted.
    clean["is_cancelled"] = clean["cancelled_at"].notna()
    clean["include_in_analysis"] = ~clean["is_cancelled"]
    clean["exclusion_reason"] = pd.Series(np.where(clean["is_cancelled"], "cancelled", None),
                                          index=clean.index, dtype="object")

    # Places.
    clean["district_city"] = clean["district_city"].apply(tidy_place_name)
    clean["state"] = clean["state"].apply(tidy_place_name)
    clean["district_from_override"] = notes.str.contains("pin_code_override", regex=False)

    # Facts kept from the notes, before the notes are dropped.
    refunded = notes.str.extract(r"refunded_amount=([0-9]+(?:\.[0-9]+)?)", expand=False)
    clean["refunded_amount"] = pd.to_numeric(refunded, errors="coerce")

    # Dates.
    when = clean["order_datetime"]
    clean["order_date"] = when.dt.normalize()
    clean["order_month"] = when.dt.to_period("M").dt.to_timestamp()
    clean["week_start"] = clean["order_date"] - pd.to_timedelta(when.dt.dayofweek, unit="D")
    clean["weekday"] = when.dt.day_name()
    clean["hour"] = when.dt.hour

    # Products.
    lines = line_prices(items, clean, products)
    per_order = lines.groupby("order_id")
    clean["units"] = clean["order_id"].map(per_order["quantity"].sum()).fillna(0).astype(int)
    clean["product_lines"] = clean["order_id"].map(per_order.size()).fillna(0).astype(int)
    clean["product_defaulted"] = clean["order_id"].map(per_order["product_defaulted"].any()).fillna(False).astype(bool)

    # Amounts.
    clean["amount_reliable"] = clean["order_amount"].notna() & ~has_any_flag(flags, AMOUNT_FLAGS)
    estimate = clean["order_id"].map(total_or_unknown(lines, "estimated_line_value"))
    estimate = estimate.mask(has_any_flag(flags, NO_ESTIMATE_FLAGS))
    clean["estimated_order_value"] = estimate
    clean["estimated_order_cost"] = clean["order_id"].map(total_or_unknown(lines, "estimated_line_cost"))
    clean["order_value"] = clean["order_amount"].where(clean["amount_reliable"], estimate)
    clean["value_basis"] = np.select(
        [clean["amount_reliable"], estimate.notna()], ["recorded", "estimated"], default="unknown")

    # Customers: only counted orders of known customers are numbered.
    clean["customer_identified"] = ~has_any_flag(flags, NO_CUSTOMER_FLAGS)
    numbered = clean[clean["include_in_analysis"] & clean["customer_identified"]]
    numbered = numbered.sort_values(["customer_id", "order_datetime", "order_id"])
    clean["customer_order_number"] = (numbered.groupby("customer_id").cumcount() + 1).reindex(clean.index).astype("Int64")
    clean["is_repeat_order"] = (clean["customer_order_number"] > 1).astype("boolean")

    return clean[ORDER_COLUMNS]


def clean_order_items(items, clean_orders_table, products):
    """Return the clean product lines, with the price used for each estimate."""
    lines = line_prices(items, clean_orders_table, products)
    no_estimate = clean_orders_table.loc[clean_orders_table["estimated_order_value"].isna(), "order_id"]
    # A line of an order that cannot be estimated is not estimated either.
    lines.loc[lines["order_id"].isin(no_estimate), ["price_used", "estimated_line_value"]] = np.nan
    included = clean_orders_table.set_index("order_id")["include_in_analysis"]
    lines["include_in_analysis"] = lines["order_id"].map(included).fillna(False).astype(bool)
    return lines[ITEM_COLUMNS]


def build_customers(customers, clean_orders_table):
    """One row per customer, with no name and no phone."""
    counted = clean_orders_table[clean_orders_table["include_in_analysis"]]
    per_customer = counted.groupby("customer_id")
    table = pd.DataFrame({"customer_id": customers["customer_id"]})
    identified = clean_orders_table.groupby("customer_id")["customer_identified"].all()
    table["customer_identified"] = table["customer_id"].map(identified).fillna(False).astype(bool)
    table["first_order_date"] = table["customer_id"].map(per_customer["order_date"].min())
    table["last_order_date"] = table["customer_id"].map(per_customer["order_date"].max())
    table["orders_counted"] = table["customer_id"].map(per_customer.size()).fillna(0).astype(int)
    table["is_repeat_customer"] = table["customer_identified"] & (table["orders_counted"] > 1)
    return table[CUSTOMER_COLUMNS]


def result_type_of(indicator):
    """A short name for Meta's result indicator. Missing stays missing."""
    if indicator is None or pd.isna(indicator) or not str(indicator).strip():
        return pd.NA
    for part, result_type in RESULT_TYPES:
        if part in str(indicator):
            return result_type
    return "other"   # a kind not seen before: never guessed to be one of the above


def clean_ad_performance(ad_performance, ad_campaigns):
    """Daily ad numbers with a short result type and date parts.

    Only raw numbers are kept. CPM, CTR, cost per result and other
    ratios are worked out in SQL or Power BI, from these numbers.
    """
    ads = ad_performance.merge(ad_campaigns[["campaign_id", "campaign_name"]], on="campaign_id", how="left")
    day = pd.to_datetime(ads["report_date"])
    ads["report_date"] = day
    ads["week_start"] = day - pd.to_timedelta(day.dt.dayofweek, unit="D")
    ads["report_month"] = day.dt.to_period("M").dt.to_timestamp()
    ads["weekday"] = day.dt.day_name()
    ads["result_type"] = ads["result_indicator"].apply(result_type_of)
    return ads[AD_COLUMNS]


def clean_shipments(shipments, clean_orders_table):
    """Shipments with the number of days from order to delivery.

    A delivery date before the order date is impossible. Its
    delivery_days stays empty and delivery_date_problem is true.
    """
    clean = shipments.copy()
    clean["delivery_status"] = clean["delivery_status"].str.strip().str.lower()
    clean["delivered_date"] = pd.to_datetime(clean["delivered_date"])
    order_dates = clean_orders_table.set_index("order_id")["order_date"]
    days = (clean["delivered_date"] - clean["order_id"].map(order_dates)).dt.days
    clean["delivery_date_problem"] = days < 0
    clean["delivery_days"] = days.mask(days < 0).astype("Int64")
    included = clean_orders_table.set_index("order_id")["include_in_analysis"]
    clean["include_in_analysis"] = clean["order_id"].map(included).fillna(False).astype(bool)
    return clean[SHIPMENT_COLUMNS]


def clean_all(tables):
    """Clean all the tables. Returns a dictionary: table name -> DataFrame.

    products and ad_campaigns hold no personal details and need no
    cleaning, so they are copied as they are.
    """
    orders = clean_orders(tables["orders"], tables["order_items"], tables["products"])
    return {
        "products": tables["products"].copy(),
        "customers": build_customers(tables["customers"], orders),
        "orders": orders,
        "order_items": clean_order_items(tables["order_items"], orders, tables["products"]),
        "shipments": clean_shipments(tables["shipments"], orders),
        "ad_campaigns": tables["ad_campaigns"].copy(),
        "ad_performance": clean_ad_performance(tables["ad_performance"], tables["ad_campaigns"]),
    }
