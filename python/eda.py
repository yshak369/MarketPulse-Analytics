"""Exploratory data analysis (Phase 4) on the clean tables.

Each analysis is a small function: clean tables in, one summary table
(a pandas DataFrame) out. The question codes (S1, S2 ...) are the ones
in docs/business_questions.md.

Rules for every analysis (see docs/eda.md):
  * Only counted orders (include_in_analysis = true) are used.
  * Weeks and months with no orders are shown as 0, not left out, so a
    trend never skips quiet periods.
  * Values always say what they are: recorded, estimated or unknown.
    A recorded COD amount is the amount to COLLECT, not money received.
  * Orders with no product line were set to 1 cream (CXE) by the owner's
    rule. Product figures show them separately.
  * An empty table gives an empty result, never an error.

The input is the dictionary that clean_data.clean_all() returns, or the
same tables read from the "clean" schema.
"""

import argparse
from itertools import combinations
from pathlib import Path

import matplotlib
matplotlib.use("Agg")   # draw straight to a file, never to a screen
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from database import ConnectionProblem, SYNTHETIC_DATABASE, connect, kind_of_data, read_table
from parse_whatsapp_orders import check_output_folder

# The clean schema has no product_aliases table (only the import code
# needs it), unlike database.TABLE_NAMES, so the tables are named here.
CLEAN_TABLE_NAMES = ["products", "customers", "orders", "order_items", "shipments", "ad_campaigns", "ad_performance"]

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
UNKNOWN = "(unknown)"
ALL_STATES = "(all states)"
VALUE_BASES = ["recorded", "estimated", "unknown"]

# Where the synthetic report may be published (tracked by Git). Any other
# database follows the same rule as the import scripts: outside the
# project, or under data/processed/ (see parse_whatsapp_orders.check_output_folder).
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
SYNTHETIC_REPORT_FOLDER = PROJECT_FOLDER / "reports" / "eda_synthetic"

# The label shown in chart titles and the report header for synthetic data.
# None (no label) for a private run: it is the owner's own data.
SYNTHETIC_DATABASE_LABEL = "SYNTHETIC DATA"


def counted_orders(orders):
    """Orders that count in the analysis."""
    return orders[orders["include_in_analysis"].astype(bool)]


def counted_items(items):
    return items[items["include_in_analysis"].astype(bool)]


def share(counts):
    """Each count as a share of the total (0.25 = 25%). All zero when the total is 0."""
    total = counts.sum()
    return counts / total if total else counts * 0.0


# ---------------------------------------------------------------------
# Sales (S1 to S8)
# ---------------------------------------------------------------------

def orders_by_month(orders):
    """S1: number of counted orders per month, with empty months as 0."""
    months = counted_orders(orders)["order_month"]
    if months.empty:
        return pd.DataFrame(columns=["order_month", "orders"])
    every_month = pd.date_range(months.min(), months.max(), freq="MS")
    counts = months.value_counts().reindex(every_month, fill_value=0)
    return pd.DataFrame({"order_month": every_month, "orders": counts.to_numpy()})


def orders_by_week(orders, trend_weeks=4):
    """S1: counted orders per week (weeks start on Monday), with a trend.

    The trend is the average of the last `trend_weeks` weeks (a rolling
    average). It smooths out week-to-week noise, so a rise or fall is
    easier to see.
    """
    weeks = counted_orders(orders)["week_start"]
    if weeks.empty:
        return pd.DataFrame(columns=["week_start", "orders", "trend"])
    every_week = pd.date_range(weeks.min(), weeks.max(), freq="W-MON")
    counts = weeks.value_counts().reindex(every_week, fill_value=0)
    table = pd.DataFrame({"week_start": every_week, "orders": counts.to_numpy()})
    table["trend"] = table["orders"].rolling(trend_weeks, min_periods=1).mean()
    return table


def units_by_product(items):
    """S2: units sold per product, split into written and defaulted.

    "defaulted" units come from orders with no product line, which the
    owner's rule counts as 1 cream (CXE). They are not what the customer
    wrote, so they are shown apart.
    """
    lines = counted_items(items)
    columns = ["product_code", "product_name", "units_written", "units_defaulted", "units_total", "share_of_units"]
    if lines.empty:
        return pd.DataFrame(columns=columns)
    defaulted = lines["product_defaulted"].astype(bool)
    table = (lines.assign(units_written=lines["quantity"].where(~defaulted, 0),
                          units_defaulted=lines["quantity"].where(defaulted, 0))
             .groupby(["product_code", "product_name"], dropna=False)[["units_written", "units_defaulted"]]
             .sum().reset_index())
    table["units_total"] = table["units_written"] + table["units_defaulted"]
    table["share_of_units"] = share(table["units_total"])
    return table.sort_values(["units_total", "product_code"], ascending=[False, True])[columns].reset_index(drop=True)


def product_pairs(items, top=10):
    """S3: which two products are most often in the same order.

    Each order counts once per pair, whatever the quantities.
    """
    lines = counted_items(items)
    columns = ["product_a", "product_b", "orders"]
    products_per_order = lines.groupby("order_id")["product_code"].apply(lambda codes: sorted(set(codes)))
    pairs = [pair for codes in products_per_order for pair in combinations(codes, 2)]
    if not pairs:
        return pd.DataFrame(columns=columns)
    table = pd.DataFrame(pairs, columns=["product_a", "product_b"]).value_counts().rename("orders").reset_index()
    return table.sort_values(["orders", "product_a", "product_b"], ascending=[False, True, True]).head(top).reset_index(drop=True)


def orders_by_channel(orders):
    """S4: counted orders per sales channel, with each channel's share."""
    counts = counted_orders(orders)["sales_channel"].value_counts()
    table = pd.DataFrame({"sales_channel": counts.index, "orders": counts.to_numpy()})
    table["share"] = share(table["orders"])
    return table


def orders_by_weekday_and_hour(orders):
    """S5: counted orders for each weekday (rows) and hour of the day (columns 0-23)."""
    found = counted_orders(orders)
    table = pd.crosstab(found["weekday"], found["hour"]) if not found.empty else pd.DataFrame()
    return table.reindex(index=WEEKDAYS, columns=range(24), fill_value=0).rename_axis(index="weekday", columns="hour")


def orders_by_state(orders):
    """S6: counted orders per state. A missing state is its own row, "(unknown)"."""
    states = counted_orders(orders)["state"].fillna(UNKNOWN)
    counts = states.value_counts()
    table = pd.DataFrame({"state": counts.index, "orders": counts.to_numpy()})
    table["share"] = share(table["orders"])
    return table


def top_districts(orders, top=10):
    """S6: the districts with the most counted orders, and orders with no known district."""
    found = counted_orders(orders)
    places = found.assign(district_city=found["district_city"].fillna(UNKNOWN), state=found["state"].fillna(UNKNOWN))
    counts = places.groupby(["district_city", "state"]).size().rename("orders").reset_index()
    known = counts[counts["district_city"] != UNKNOWN].sort_values(["orders", "district_city"], ascending=[False, True])
    # Orders with no known district, from every state together. Their
    # state is often known, so it is not called "unknown" here.
    unknown = counts[counts["district_city"] == UNKNOWN].groupby("district_city", as_index=False)["orders"].sum()
    unknown["state"] = ALL_STATES
    table = pd.concat([known.head(top), unknown[["district_city", "state", "orders"]]], ignore_index=True)
    table["share"] = table["orders"] / len(found) if len(found) else 0.0
    return table


def basket_size(orders):
    """S7: product lines and units per counted order: average, median and percentiles.

    A percentile says "this share of orders is at or below this number".
    For example p90 = 3 means 90% of orders have 3 or fewer.
    """
    found = counted_orders(orders)
    rows = []
    for measure in ("product_lines", "units"):
        values = found[measure].to_numpy(dtype=float)
        if len(values) == 0:
            rows.append({"measure": measure})
            continue
        p25, p50, p75, p90 = np.percentile(values, [25, 50, 75, 90])
        rows.append({"measure": measure, "orders": len(values), "average": values.mean(), "median": p50,
                     "p25": p25, "p75": p75, "p90": p90, "max": values.max()})
    return pd.DataFrame(rows)


def value_by_month(orders):
    """S8: order value per month, kept apart by where it comes from.

    recorded   amounts written in the source: Shopify totals and COD
               amounts to COLLECT (not money received)
    estimated  worked out from the price list
    unknown    orders with no value at all (counted, but no amount)
    """
    found = counted_orders(orders)
    if found.empty:
        return pd.DataFrame(columns=["order_month", "recorded_value", "estimated_value",
                                     "orders_recorded", "orders_estimated", "orders_unknown"])
    months = pd.date_range(found["order_month"].min(), found["order_month"].max(), freq="MS")
    values = found.pivot_table(index="order_month", columns="value_basis", values="order_value",
                               aggfunc="sum").reindex(index=months, columns=VALUE_BASES).fillna(0)
    counts = (found.groupby(["order_month", "value_basis"]).size().unstack()
              .reindex(index=months, columns=VALUE_BASES).fillna(0).astype(int))
    return pd.DataFrame({
        "order_month": months,
        "recorded_value": values["recorded"].to_numpy(),
        "estimated_value": values["estimated"].to_numpy(),
        "orders_recorded": counts["recorded"].to_numpy(),
        "orders_estimated": counts["estimated"].to_numpy(),
        "orders_unknown": counts["unknown"].to_numpy(),
    })


# ---------------------------------------------------------------------
# Customers (C1, C2, C4, C5)
# ---------------------------------------------------------------------

def known_customer_orders(orders):
    """Counted orders of customers that can be recognised (they had a usable phone)."""
    found = counted_orders(orders)
    return found[found["customer_identified"].astype(bool)]


def is_possible_duplicate(orders):
    return orders["review_flags"].fillna("").str.contains("possible_duplicate", regex=False)


def repeat_customers(orders):
    """C1: share of known customers with more than one counted order.

    Shown twice: with every counted order, and without the orders flagged
    possible_duplicate. A real duplicate looks like a second order, so the
    second line is the cautious one.
    """
    found = known_customer_orders(orders)
    rows = []
    for version, chosen in (("all counted orders", found),
                            ("without possible duplicates", found[~is_possible_duplicate(found)])):
        per_customer = chosen.groupby("customer_id").size()
        customers, repeat = len(per_customer), int((per_customer > 1).sum())
        rows.append({"version": version, "customers": customers, "repeat_customers": repeat,
                     "repeat_share": repeat / customers if customers else 0.0})
    return pd.DataFrame(rows)


def days_to_second_order(orders):
    """C2: days between the first and the second counted order of each customer."""
    found = known_customer_orders(orders)
    first_two = found[found["customer_order_number"].isin([1, 2])]
    dates = first_two.pivot_table(index="customer_id", columns="customer_order_number",
                                  values="order_date", aggfunc="first")
    if 2 not in dates.columns:
        return pd.DataFrame([{"customers_with_a_second_order": 0}])
    days = (dates[2] - dates[1]).dropna().dt.days.to_numpy(dtype=float)
    p25, p50, p75, p90 = np.percentile(days, [25, 50, 75, 90])
    return pd.DataFrame([{"customers_with_a_second_order": len(days), "average_days": days.mean(),
                          "median_days": p50, "p25": p25, "p75": p75, "p90": p90}])


def new_and_returning_by_month(orders):
    """C4: counted orders per month from new, returning and unknown customers.

    new        the first counted order of the customer
    returning  the second or a later counted order
    unknown    no usable phone, so it cannot be told
    """
    found = counted_orders(orders)
    columns = ["order_month", "new_customer_orders", "returning_customer_orders", "unknown_customer_orders"]
    if found.empty:
        return pd.DataFrame(columns=columns)
    unknown = ~found["customer_identified"].astype(bool)
    # An unknown customer has no order number (empty), which is never "first".
    first = (found["customer_order_number"] == 1).fillna(False).astype(bool)
    kind = pd.Series(np.select([unknown, first], ["unknown", "new"], default="returning"), index=found.index)
    months = pd.date_range(found["order_month"].min(), found["order_month"].max(), freq="MS")
    table = (pd.crosstab(found["order_month"], kind)
             .reindex(index=months, columns=["new", "returning", "unknown"], fill_value=0))
    return pd.DataFrame({"order_month": months, "new_customer_orders": table["new"].to_numpy(),
                         "returning_customer_orders": table["returning"].to_numpy(),
                         "unknown_customer_orders": table["unknown"].to_numpy()})


def repeat_customers_by_district(orders, min_customers=20):
    """C5: repeat-customer share per district, for districts with enough customers.

    A customer belongs to the district of the first counted order.
    Districts with fewer than `min_customers` customers are left out,
    because a share of a handful of customers is mostly chance.
    """
    found = known_customer_orders(orders)
    columns = ["district_city", "state", "customers", "repeat_customers", "repeat_share"]
    first = found[found["customer_order_number"] == 1][["customer_id", "district_city", "state"]]
    orders_per_customer = found.groupby("customer_id").size().rename("orders")
    customers = first.join(orders_per_customer, on="customer_id").dropna(subset=["district_city"])
    if customers.empty:
        return pd.DataFrame(columns=columns)
    table = (customers.assign(is_repeat=customers["orders"] > 1)
             .groupby(["district_city", "state"])
             .agg(customers=("customer_id", "size"), repeat_customers=("is_repeat", "sum")).reset_index())
    table = table[table["customers"] >= min_customers].copy()
    table["repeat_share"] = table["repeat_customers"] / table["customers"]
    return table.sort_values(["repeat_share", "customers"], ascending=[False, False])[columns].reset_index(drop=True)


# ---------------------------------------------------------------------
# Payment and shipping (D1 to D6)
# ---------------------------------------------------------------------

PAYMENT_TYPES = ["cod", "prepaid", "needs_review"]


def cod_share_of(counts):
    """COD orders as a share of COD + Prepaid. needs_review orders are left out."""
    known = counts.get("cod", 0) + counts.get("prepaid", 0)
    return counts.get("cod", 0) / known if known else np.nan


def payment_by_month(orders):
    """D1: COD, Prepaid and needs_review orders per month, and the COD share."""
    found = counted_orders(orders)
    columns = ["order_month"] + PAYMENT_TYPES + ["cod_share"]
    if found.empty:
        return pd.DataFrame(columns=columns)
    months = pd.date_range(found["order_month"].min(), found["order_month"].max(), freq="MS")
    table = (pd.crosstab(found["order_month"], found["payment_type"])
             .reindex(index=months, columns=PAYMENT_TYPES, fill_value=0))
    table["cod_share"] = table.apply(cod_share_of, axis=1)
    return table.rename_axis(index="order_month", columns=None).reset_index()[columns]


def cod_share_by_state(orders, min_orders=30):
    """D2: COD share per state, for states with at least `min_orders` counted orders."""
    found = counted_orders(orders)
    columns = ["state", "orders"] + PAYMENT_TYPES + ["cod_share"]
    if found.empty:
        return pd.DataFrame(columns=columns)
    table = (pd.crosstab(found["state"].fillna(UNKNOWN), found["payment_type"])
             .reindex(columns=PAYMENT_TYPES, fill_value=0))
    table["orders"] = table[PAYMENT_TYPES].sum(axis=1)
    table["cod_share"] = table.apply(cod_share_of, axis=1)
    table = table[table["orders"] >= min_orders].rename_axis(index="state", columns=None).reset_index()
    return table.sort_values(["cod_share", "orders"], ascending=[False, False])[columns].reset_index(drop=True)


def basket_by_payment(orders):
    """D3: average product lines and units per order, COD vs Prepaid."""
    found = counted_orders(orders)
    found = found[found["payment_type"].isin(["cod", "prepaid"])]
    table = found.groupby("payment_type").agg(
        orders=("order_id", "size"), average_product_lines=("product_lines", "mean"),
        average_units=("units", "mean"), median_units=("units", "median"))
    return table.reset_index()


def product_mix_by_payment(items, orders):
    """D3: the share of units of each product, for COD and for Prepaid orders."""
    lines = counted_items(items).merge(orders[["order_id", "payment_type"]], on="order_id")
    lines = lines[lines["payment_type"].isin(["cod", "prepaid"])]
    if lines.empty:
        return pd.DataFrame(columns=["product_code", "cod", "prepaid"])
    units = (lines.pivot_table(index="product_code", columns="payment_type", values="quantity",
                               aggfunc="sum", fill_value=0)
             .reindex(columns=["cod", "prepaid"], fill_value=0))
    shares = (units / units.sum().replace(0, np.nan)).fillna(0)
    return shares.sort_values("cod", ascending=False).rename_axis(columns=None).reset_index()


def cod_to_collect_by_week(orders):
    """D4: COD orders per week, and the amount to COLLECT.

    amount_to_collect     recorded COD amounts (WhatsApp brackets, Shopify totals)
    estimated_to_collect  price-list estimates for COD orders without a usable amount
    Neither is revenue: a COD parcel can be returned and never paid.
    """
    cod = counted_orders(orders)
    cod = cod[cod["payment_type"] == "cod"]
    columns = ["week_start", "cod_orders", "amount_to_collect", "estimated_to_collect", "orders_without_value"]
    if cod.empty:
        return pd.DataFrame(columns=columns)
    weeks = pd.date_range(cod["week_start"].min(), cod["week_start"].max(), freq="W-MON")
    value = cod["order_value"].fillna(0)
    parts = pd.DataFrame({
        "week_start": cod["week_start"],
        "cod_orders": 1,
        "amount_to_collect": value.where(cod["value_basis"] == "recorded", 0),
        "estimated_to_collect": value.where(cod["value_basis"] == "estimated", 0),
        "orders_without_value": (cod["value_basis"] == "unknown").astype(int),
    })
    table = parts.groupby("week_start").sum().reindex(weeks, fill_value=0)
    return table.rename_axis("week_start").reset_index()[columns]


def counted_shipments(shipments, orders):
    """Counted shipments, with the payment type and state of their order."""
    found = shipments[shipments["include_in_analysis"].astype(bool)]
    return found.merge(orders[["order_id", "payment_type", "state"]], on="order_id", how="left")


def delivery_outcomes(shipments, orders):
    """D5: delivered, returned and unknown shipments per courier and payment type.

    An empty result means there are no courier records yet.
    """
    found = counted_shipments(shipments, orders)
    columns = ["courier", "payment_type", "shipments", "delivered", "returned", "unknown",
               "delivered_share", "returned_share"]
    if found.empty:
        return pd.DataFrame(columns=columns)
    status = found["delivery_status"].fillna("unknown")
    found = found.assign(is_delivered=status == "delivered", is_returned=status == "returned",
                         is_unknown=~status.isin(["delivered", "returned"]))
    table = found.groupby(["courier", "payment_type"]).agg(
        shipments=("shipment_id", "size"), delivered=("is_delivered", "sum"),
        returned=("is_returned", "sum"), unknown=("is_unknown", "sum")).reset_index()
    table["delivered_share"] = table["delivered"] / table["shipments"]
    table["returned_share"] = table["returned"] / table["shipments"]
    return table[columns]


def delivery_days_by_courier(shipments, orders):
    """D6: days from order to delivery, per courier: average, median and p90.

    An empty result means there are no courier records yet.
    """
    found = counted_shipments(shipments, orders).dropna(subset=["delivery_days"])
    columns = ["courier", "deliveries", "average_days", "median_days", "p90_days"]
    if found.empty:
        return pd.DataFrame(columns=columns)
    days = found["delivery_days"].astype(float)
    table = days.groupby(found["courier"]).agg(
        deliveries="size", average_days="mean", median_days="median",
        p90_days=lambda values: np.percentile(values, 90)).reset_index()
    return table[columns]


# ---------------------------------------------------------------------
# Marketing (M1 to M6)
# ---------------------------------------------------------------------

MESSAGING = "messaging_conversation"


def spend_by_week(ad_performance):
    """M1: ad spend per week, across all campaigns, with empty weeks as 0.

    An empty result means there is no ad data yet.
    """
    columns = ["week_start", "amount_spent_inr"]
    if ad_performance.empty:
        return pd.DataFrame(columns=columns)
    weeks = pd.date_range(ad_performance["week_start"].min(), ad_performance["week_start"].max(), freq="W-MON")
    table = ad_performance.groupby("week_start")["amount_spent_inr"].sum().reindex(weeks, fill_value=0.0)
    return table.rename_axis("week_start").reset_index()


def cost_per_conversation(ad_performance):
    """M2: cost per messaging conversation, per campaign.

    Spend of days with a messaging_conversation result, divided by those
    results. Never mixed with link clicks or other result types.
    An empty result means there is no messaging campaign data yet.
    """
    columns = ["campaign_id", "campaign_name", "amount_spent_inr", "conversations", "cost_per_conversation"]
    found = ad_performance[ad_performance["result_type"] == MESSAGING]
    if found.empty:
        return pd.DataFrame(columns=columns)
    table = found.groupby(["campaign_id", "campaign_name"]).agg(
        amount_spent_inr=("amount_spent_inr", "sum"), conversations=("results", "sum")).reset_index()
    table["cost_per_conversation"] = table["amount_spent_inr"] / table["conversations"].replace(0, np.nan)
    return table.sort_values("cost_per_conversation")[columns].reset_index(drop=True)


def weekly_cpm_and_ctr(ad_performance):
    """M3: weekly CPM (cost per 1,000 impressions) and CTR (all clicks / impressions), per campaign.

    These ratios are never stored (schema design rule 1): they are
    worked out here, from the raw spend, impressions and clicks.
    A week with zero impressions gives an empty CPM and CTR, not a
    division error.
    An empty result means there is no ad data yet.
    """
    columns = ["campaign_id", "campaign_name", "week_start", "amount_spent_inr", "impressions", "cpm", "ctr"]
    if ad_performance.empty:
        return pd.DataFrame(columns=columns)
    table = ad_performance.groupby(["campaign_id", "campaign_name", "week_start"]).agg(
        amount_spent_inr=("amount_spent_inr", "sum"), impressions=("impressions", "sum"),
        clicks_all=("clicks_all", "sum")).reset_index()
    impressions = table["impressions"].replace(0, np.nan)
    table["cpm"] = table["amount_spent_inr"] / impressions * 1000
    table["ctr"] = table["clicks_all"] / impressions
    return table[columns].sort_values(["campaign_id", "week_start"]).reset_index(drop=True)


def spend_and_orders_by_week(ad_performance, orders):
    """M4-M6: weekly ad spend next to weekly WhatsApp order count.

    Also returns the correlation between the two (np.corrcoef), spend
    per order, and messaging conversations per WhatsApp order. The
    correlation shows a PATTERN ONLY. It is never proof that spend in
    one week caused the orders in that week: nothing in this data links
    a specific ad to a specific order (see docs/schema_design.md).

    An empty result means there is no ad data yet. correlation is NaN
    when there are fewer than 2 weeks, or spend or orders never vary.
    """
    columns = ["week_start", "amount_spent_inr", "messaging_conversations", "whatsapp_orders",
               "spend_per_order", "conversations_per_order"]
    if ad_performance.empty:
        return pd.DataFrame(columns=columns), np.nan

    whatsapp = counted_orders(orders)
    whatsapp = whatsapp[whatsapp["sales_channel"] == "whatsapp"]
    weeks = pd.date_range(ad_performance["week_start"].min(), ad_performance["week_start"].max(), freq="W-MON")

    spend = ad_performance.groupby("week_start")["amount_spent_inr"].sum().reindex(weeks, fill_value=0.0)
    conversations = (ad_performance[ad_performance["result_type"] == MESSAGING]
                     .groupby("week_start")["results"].sum().reindex(weeks, fill_value=0))
    order_counts = whatsapp["week_start"].value_counts().reindex(weeks, fill_value=0)

    table = pd.DataFrame({"week_start": weeks, "amount_spent_inr": spend.to_numpy(),
                          "messaging_conversations": conversations.to_numpy(),
                          "whatsapp_orders": order_counts.to_numpy()})
    table["spend_per_order"] = table["amount_spent_inr"] / table["whatsapp_orders"].replace(0, np.nan)
    table["conversations_per_order"] = table["messaging_conversations"] / table["whatsapp_orders"].replace(0, np.nan)

    if len(table) >= 2 and table["amount_spent_inr"].std() > 0 and table["whatsapp_orders"].std() > 0:
        correlation = float(np.corrcoef(table["amount_spent_inr"], table["whatsapp_orders"])[0, 1])
    else:
        correlation = np.nan
    return table[columns], correlation


# =======================================================================
# The report: run every analysis, then write a Markdown report, charts
# and CSV files. See docs/eda.md for the method and the rules.
# =======================================================================

def run_all_analyses(tables):
    """Run every analysis above once, and return one dictionary of results.

    Keys follow docs/business_questions.md (S1, S2, ... M6). A question
    with more than one table gets a suffix, for example S6_state and
    S6_district. M4_6_correlation is a single number, not a table.
    """
    orders, items, shipments = tables["orders"], tables["order_items"], tables["shipments"]
    ads = tables["ad_performance"]
    spend_and_orders, correlation = spend_and_orders_by_week(ads, orders)
    return {
        "S1_month": orders_by_month(orders), "S1_week": orders_by_week(orders),
        "S2": units_by_product(items), "S3": product_pairs(items),
        "S4": orders_by_channel(orders), "S5": orders_by_weekday_and_hour(orders),
        "S6_state": orders_by_state(orders), "S6_district": top_districts(orders),
        "S7": basket_size(orders), "S8": value_by_month(orders),
        "C1": repeat_customers(orders), "C2": days_to_second_order(orders),
        "C4": new_and_returning_by_month(orders), "C5": repeat_customers_by_district(orders),
        "D1": payment_by_month(orders), "D2": cod_share_by_state(orders),
        "D3_basket": basket_by_payment(orders), "D3_mix": product_mix_by_payment(items, orders),
        "D4": cod_to_collect_by_week(orders),
        "D5": delivery_outcomes(shipments, orders), "D6": delivery_days_by_courier(shipments, orders),
        "M1": spend_by_week(ads), "M2": cost_per_conversation(ads), "M3": weekly_cpm_and_ctr(ads),
        "M4_6": spend_and_orders, "M4_6_correlation": correlation,
    }


# ---------------------------------------------------------------------
# Output folder guard
# ---------------------------------------------------------------------

def check_eda_output_folder(folder, database):
    """Refuse an output folder that could expose private business data.

    Only the synthetic database may write inside the project, and then
    only to reports/eda_synthetic/, the published report. Every other
    database follows the import scripts' own rule: a folder outside the
    project, or under data/processed/ (ignored by Git).
    """
    folder = Path(folder).resolve()
    if database == SYNTHETIC_DATABASE and (folder == SYNTHETIC_REPORT_FOLDER
                                           or SYNTHETIC_REPORT_FOLDER in folder.parents):
        return folder
    return check_output_folder(folder)


# ---------------------------------------------------------------------
# Markdown tables and sentences
# ---------------------------------------------------------------------

def format_cell(value):
    """One table cell as plain text, for the Markdown report."""
    if pd.isna(value):
        return ""
    if isinstance(value, (pd.Timestamp,)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, np.integer)):
        return f"{value:,}"
    if isinstance(value, (float, np.floating)):
        return f"{value:,.2f}"
    return str(value)


def to_markdown_table(table, max_rows=15):
    """A pandas DataFrame as a Markdown table. No extra package needed.

    Only the first `max_rows` rows are shown, with a note of how many
    more there are. The full table is always in the matching CSV file.
    """
    if table is None or table.empty:
        return "_No rows._"
    shown = table.reset_index(drop=table.index.name is None).head(max_rows)
    header = "| " + " | ".join(str(column) for column in shown.columns) + " |"
    divider = "|" + "|".join(["---"] * len(shown.columns)) + "|"
    body = ["| " + " | ".join(format_cell(value) for value in row) + " |" for row in shown.itertuples(index=False)]
    text = "\n".join([header, divider, *body])
    if len(table) > max_rows:
        text += f"\n\n_... and {len(table) - max_rows} more rows (see the matching CSV file)._"
    return text


def fmt_money(amount):
    return "unknown" if pd.isna(amount) else f"Rs {amount:,.0f}"


def sentence(results):
    """One short, factual sentence per result table, built from that table.

    Keys match the result keys exactly (not just the question code), so
    a question with more than one table (S1, S6) gets two distinct
    sentences, never the same text shown twice.

    Nothing here is invented: every number comes straight from the
    table it describes.
    """
    lines = {}

    months = results["S1_month"]
    if not months.empty:
        peak = months.loc[months["orders"].idxmax()]
        lines["S1_month"] = (f"Orders ranged from {months['orders'].min()} to {months['orders'].max()} per month, "
                             f"peaking in {peak['order_month']:%B %Y} with {peak['orders']} orders.")

    weeks = results["S1_week"]
    if not weeks.empty:
        peak = weeks.loc[weeks["orders"].idxmax()]
        lines["S1_week"] = (f"The busiest week started {peak['week_start']:%d %b %Y}, with {peak['orders']} orders "
                            f"(trend at that point: {peak['trend']:.0f} orders per week).")

    units = results["S2"]
    if not units.empty:
        top = units.iloc[0]
        defaulted = int(units["units_defaulted"].sum())
        lines["S2"] = (f"{top['product_name']} sold the most units ({int(top['units_total']):,}, "
                       f"{top['share_of_units']:.0%} of all units)." +
                       (f" {defaulted:,} units came from orders with no product line (the owner's default rule)."
                        if defaulted else ""))

    pairs = results["S3"]
    if not pairs.empty:
        top = pairs.iloc[0]
        lines["S3"] = f"{top['product_a']} and {top['product_b']} were bought together most often ({top['orders']:,} orders)."

    channel = results["S4"]
    if not channel.empty:
        text = ", ".join(f"{row.sales_channel} {row.share:.0%}" for row in channel.itertuples())
        lines["S4"] = "Orders by channel: " + text + "."

    states = results["S6_state"]
    if not states.empty:
        top = states.iloc[states["orders"].idxmax()]
        lines["S6_state"] = f"{top['state']} placed the most orders ({top['orders']:,}, {top['share']:.0%} of the total)."

    districts = results["S6_district"]
    known = districts[districts["district_city"] != UNKNOWN]
    if not known.empty:
        top = known.iloc[known["orders"].idxmax()]
        lines["S6_district"] = (f"{top['district_city']} ({top['state']}) is the district with the most orders among "
                                f"those shown ({top['orders']:,}, {top['share']:.0%} of all counted orders).")

    basket = results["S7"]
    if not basket.empty and basket["orders"].notna().any():
        row_by_measure = basket.set_index("measure")
        lines["S7"] = (f"The median order has {row_by_measure.loc['product_lines', 'median']:.0f} product line(s) "
                       f"and {row_by_measure.loc['units', 'median']:.0f} unit(s).")

    value = results["S8"]
    if not value.empty:
        recorded, estimated = value["recorded_value"].sum(), value["estimated_value"].sum()
        unknown = int(value["orders_unknown"].sum())
        lines["S8"] = (f"Total order value: {fmt_money(recorded)} recorded, {fmt_money(estimated)} estimated"
                       f"{f', and {unknown} orders with no value at all' if unknown else ''}.")

    repeat = results["C1"]
    if not repeat.empty and repeat.iloc[0]["customers"]:
        both = repeat.set_index("version")
        lines["C1"] = (f"{both.loc['all counted orders', 'repeat_share']:.1%} of known customers ordered more than once "
                       f"({both.loc['without possible duplicates', 'repeat_share']:.1%} without possible duplicates).")

    days = results["C2"]
    if not days.empty and days.iloc[0].get("customers_with_a_second_order", 0):
        row = days.iloc[0]
        lines["C2"] = f"Customers who ordered again took a median of {row['median_days']:.0f} days to do so."

    new_returning = results["C4"]
    if not new_returning.empty:
        first, last = new_returning.iloc[0], new_returning.iloc[-1]
        lines["C4"] = (f"Returning-customer orders went from {int(first['returning_customer_orders'])} in "
                       f"{first['order_month']:%B %Y} to {int(last['returning_customer_orders'])} in "
                       f"{last['order_month']:%B %Y}. Early months of any dataset show few returning customers "
                       "simply because there has been less time for a second order, not because loyalty is rising.")

    districts_c5 = results["C5"]
    if not districts_c5.empty:
        top = districts_c5.iloc[districts_c5["repeat_share"].idxmax()]
        lines["C5"] = (f"Among districts with enough customers to compare, {top['district_city']} "
                       f"({top['state']}) has the highest repeat-customer share ({top['repeat_share']:.0%}).")

    payment = results["D1"]
    if not payment.empty:
        overall = payment[["cod", "prepaid"]].sum()
        share = overall["cod"] / overall.sum() if overall.sum() else float("nan")
        lines["D1"] = (f"Across the period, {share:.0%} of orders with a known payment type were COD."
                       if not pd.isna(share) else "")

    states_d2 = results["D2"]
    if not states_d2.empty:
        top = states_d2.iloc[0]   # already sorted by cod_share, highest first
        lines["D2"] = (f"Among states with enough orders to compare, {top['state']} leans most towards COD "
                       f"({top['cod_share']:.0%}).")

    cod_week = results["D4"]
    if not cod_week.empty:
        lines["D4"] = (f"COD orders had {fmt_money(cod_week['amount_to_collect'].sum())} recorded and "
                       f"{fmt_money(cod_week['estimated_to_collect'].sum())} estimated to COLLECT. "
                       "This is not confirmed revenue: a COD parcel can be returned and never paid for.")

    outcomes = results["D5"]
    if not outcomes.empty:
        text = "; ".join(f"{row.courier} {row.delivered_share:.0%} delivered, {row.returned_share:.0%} returned"
                         for row in outcomes.itertuples())
        lines["D5"] = text + "."
    else:
        lines["D5"] = "No courier delivery records yet."

    days6 = results["D6"]
    lines["D6"] = ("; ".join(f"{row.courier} median {row.median_days:.0f} days" for row in days6.itertuples()) + "."
                   if not days6.empty else "No courier delivery records yet.")

    spend = results["M1"]
    if not spend.empty:
        lines["M1"] = f"Total ad spend: {fmt_money(spend['amount_spent_inr'].sum())} over {len(spend)} weeks."
    else:
        lines["M1"] = "No advertising data yet."

    conversations = results["M2"]
    if not conversations.empty:
        best = conversations.iloc[0]
        lines["M2"] = (f"The cheapest messaging campaign cost {fmt_money(best['cost_per_conversation'])} "
                       "per conversation.")
    elif not results["M1"].empty:
        lines["M2"] = "No messaging-conversation campaigns in this period."

    ratios = results["M3"]
    if not ratios.empty:
        lines["M3"] = (f"Across all campaign-weeks, average CPM was {fmt_money(ratios['cpm'].mean())} "
                       f"per 1,000 impressions, and average CTR was {ratios['ctr'].mean():.1%}.")

    correlation = results["M4_6_correlation"]
    if not pd.isna(correlation):
        lines["M4_6"] = (f"Weekly ad spend and weekly WhatsApp orders moved together with a correlation of "
                         f"{correlation:.2f}. This is a PATTERN only, not proof that the spend caused those orders: "
                         "nothing in this data links one ad to one order.")
    elif not results["M1"].empty:
        lines["M4_6"] = "Not enough weeks of data to look for a pattern between spend and orders."
    else:
        lines["M4_6"] = "No advertising data yet."

    return lines


# ---------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------

def chart_title(text, label):
    return f"{label} — {text}" if label else text


def save_figure(figure, folder, name):
    path = folder / f"{name}.png"
    figure.tight_layout()
    figure.savefig(path, dpi=110)
    plt.close(figure)
    return path.name


def draw_charts(results, folder, label):
    """Draw and save one PNG chart per main question.

    Returns a dictionary {result key: file name}, so each chart is
    matched to exactly one section of the report. A question with more
    than one table (for example S1 and S6) gets the chart on only one
    of its keys; the other key shows no image, not a repeated one.
    """
    charts = {}

    weeks = results["S1_week"]
    if not weeks.empty:
        figure, axis = plt.subplots(figsize=(8, 4))
        axis.plot(weeks["week_start"], weeks["orders"], linewidth=1, alpha=0.5, label="orders")
        axis.plot(weeks["week_start"], weeks["trend"], linewidth=2, label="4-week trend")
        axis.set_title(chart_title("Orders per week (S1)", label))
        axis.set_xlabel("week"); axis.set_ylabel("orders"); axis.legend()
        charts["S1_week"] = save_figure(figure, folder, "S1_orders_by_week")

    units = results["S2"]
    if not units.empty:
        figure, axis = plt.subplots(figsize=(7, 4))
        axis.bar(units["product_code"], units["units_written"], label="written")
        axis.bar(units["product_code"], units["units_defaulted"], bottom=units["units_written"], label="defaulted")
        axis.set_title(chart_title("Units sold per product (S2)", label))
        axis.set_xlabel("product"); axis.set_ylabel("units"); axis.legend()
        charts["S2"] = save_figure(figure, folder, "S2_units_by_product")

    channel = results["S4"]
    if not channel.empty:
        figure, axis = plt.subplots(figsize=(4, 4))
        axis.pie(channel["orders"], labels=channel["sales_channel"], autopct="%1.0f%%")
        axis.set_title(chart_title("Orders by channel (S4)", label))
        charts["S4"] = save_figure(figure, folder, "S4_orders_by_channel")

    grid = results["S5"]
    if grid.to_numpy().sum() > 0:
        figure, axis = plt.subplots(figsize=(9, 3.5))
        image = axis.imshow(grid.to_numpy(), aspect="auto", cmap="viridis")
        axis.set_yticks(range(len(grid.index))); axis.set_yticklabels(grid.index)
        axis.set_xticks(range(0, 24, 2)); axis.set_xticklabels(range(0, 24, 2))
        axis.set_xlabel("hour of day")
        axis.set_title(chart_title("Orders by weekday and hour (S5)", label))
        figure.colorbar(image, ax=axis, label="orders")
        charts["S5"] = save_figure(figure, folder, "S5_weekday_and_hour")

    states = results["S6_state"]
    if not states.empty:
        figure, axis = plt.subplots(figsize=(7, 4))
        axis.bar(states["state"], states["orders"])
        axis.set_title(chart_title("Orders by state (S6)", label))
        axis.set_ylabel("orders"); plt.setp(axis.get_xticklabels(), rotation=30, ha="right")
        charts["S6_state"] = save_figure(figure, folder, "S6_orders_by_state")

    value = results["S8"]
    if not value.empty:
        figure, axis = plt.subplots(figsize=(8, 4))
        axis.bar(value["order_month"], value["recorded_value"], width=20, label="recorded")
        axis.bar(value["order_month"], value["estimated_value"], width=20,
                bottom=value["recorded_value"], label="estimated")
        axis.set_title(chart_title("Order value per month: recorded vs estimated (S8)", label))
        axis.set_ylabel("Rs"); axis.legend()
        charts["S8"] = save_figure(figure, folder, "S8_value_by_month")

    payment = results["D1"]
    if not payment.empty:
        figure, axis = plt.subplots(figsize=(8, 4))
        axis.bar(payment["order_month"], payment["cod"], width=20, label="cod")
        axis.bar(payment["order_month"], payment["prepaid"], width=20, bottom=payment["cod"], label="prepaid")
        axis.set_title(chart_title("COD vs Prepaid orders per month (D1)", label))
        axis.set_ylabel("orders"); axis.legend()
        charts["D1"] = save_figure(figure, folder, "D1_payment_by_month")

    cod_week = results["D4"]
    if not cod_week.empty:
        figure, axis = plt.subplots(figsize=(8, 4))
        axis.plot(cod_week["week_start"], cod_week["amount_to_collect"], label="recorded, to collect")
        axis.plot(cod_week["week_start"], cod_week["estimated_to_collect"], label="estimated, to collect")
        axis.set_title(chart_title("COD amount to collect per week (D4)", label))
        axis.set_ylabel("Rs"); axis.legend()
        charts["D4"] = save_figure(figure, folder, "D4_cod_to_collect")

    spend_orders = results["M4_6"]
    if not spend_orders.empty:
        figure, axis = plt.subplots(figsize=(8, 4))
        axis.plot(spend_orders["week_start"], spend_orders["amount_spent_inr"], color="tab:blue", label="spend (Rs)")
        axis.set_ylabel("ad spend (Rs)", color="tab:blue")
        second = axis.twinx()
        second.plot(spend_orders["week_start"], spend_orders["whatsapp_orders"], color="tab:orange", label="WhatsApp orders")
        second.set_ylabel("WhatsApp orders", color="tab:orange")
        axis.set_title(chart_title("Ad spend vs WhatsApp orders per week — a pattern, not proof (M4-M6)", label))
        # Two axes, so their legend handles must be combined by hand.
        lines, labels = axis.get_legend_handles_labels()
        lines2, labels2 = second.get_legend_handles_labels()
        axis.legend(lines + lines2, labels + labels2, loc="upper left")
        charts["M4_6"] = save_figure(figure, folder, "M4_6_spend_and_orders")

    return charts


# ---------------------------------------------------------------------
# The report file and the command line
# ---------------------------------------------------------------------

REPORT_SECTIONS = [
    ("Sales", [("S1", "S1_month", "Orders per month"), ("S1", "S1_week", "Orders per week, with trend"),
               ("S2", "S2", "Units sold per product"), ("S3", "S3", "Products bought together, top pairs"),
               ("S4", "S4", "Orders by channel"), ("S5", "S5", "Orders by weekday and hour"),
               ("S6", "S6_state", "Orders by state"), ("S6", "S6_district", "Top districts"),
               ("S7", "S7", "Items and units per order"), ("S8", "S8", "Order value per month")]),
    ("Customers", [("C1", "C1", "Repeat customers"), ("C2", "C2", "Days to a second order"),
                   ("C4", "C4", "New vs returning customers per month"),
                   ("C5", "C5", "Repeat customers by district")]),
    ("Payment and shipping", [("D1", "D1", "COD vs Prepaid per month"), ("D2", "D2", "COD share by state"),
                              ("D3", "D3_basket", "Basket size, COD vs Prepaid"),
                              ("D3", "D3_mix", "Product mix, COD vs Prepaid"),
                              ("D4", "D4", "COD amount to collect per week"),
                              ("D5", "D5", "Delivery outcomes"), ("D6", "D6", "Delivery days by courier")]),
    ("Marketing", [("M1", "M1", "Ad spend per week"), ("M2", "M2", "Cost per messaging conversation"),
                   ("M3", "M3", "Weekly CPM and CTR per campaign"),
                   ("M4-M6", "M4_6", "Ad spend vs WhatsApp orders per week")]),
]


def render_report(results, label, chart_files):
    """Build the Markdown text of the report.

    chart_files is the {key: file name} dictionary from draw_charts.
    Both the sentence and the chart for a section are looked up by its
    exact key (for example "S1_week"), never guessed from the question
    code, so two tables under one question never show the same text
    or the same picture twice.
    """
    sentences = sentence(results)
    lines = [f"# Exploratory Data Analysis{f' — {label}' if label else ''}", ""]
    if label == SYNTHETIC_DATABASE_LABEL:
        lines += ["> **SYNTHETIC DATA.** Every number on this page comes from the fake data generator "
                 "(`python/generate_synthetic_data.py`). Any pattern shown is a pattern in made-up data, "
                 "not a real business result.", ""]
    lines += ["Only counted orders are used (`include_in_analysis = true`). An amount is labelled as it is: "
             "**recorded**, **estimated** or **unknown**. A COD amount is the amount **to collect**, "
             "not confirmed revenue. See `docs/data_cleaning.md` and `docs/eda.md`.", ""]

    for section_title, entries in REPORT_SECTIONS:
        lines += [f"## {section_title}", ""]
        for question, key, heading in entries:
            lines += [f"### {question}: {heading}", ""]
            if sentences.get(key):
                lines += [sentences[key], ""]
            if key in chart_files:
                lines += [f"![{heading}]({chart_files[key]})", ""]
            lines += [to_markdown_table(results[key]), ""]
    return "\n".join(lines)


def write_eda_report(engine, database, schema, output):
    """Read the clean schema, run every analysis, and write the report.

    Returns the folder written to, and a short summary dictionary.
    """
    folder = Path(output).resolve()   # already checked by main(), before any work was done
    folder.mkdir(parents=True, exist_ok=True)
    tables = {name: read_table(engine, name, schema) for name in CLEAN_TABLE_NAMES}
    results = run_all_analyses(tables)

    label = SYNTHETIC_DATABASE_LABEL if database == SYNTHETIC_DATABASE else None
    chart_files = draw_charts(results, folder, label)
    report_text = render_report(results, label, chart_files)
    (folder / "eda_report.md").write_text(report_text, encoding="utf-8")

    for name, table in results.items():
        if isinstance(table, pd.DataFrame):
            table.to_csv(folder / f"{name}.csv", index=False, lineterminator="\n")

    return folder, {
        "orders_counted": int(tables["orders"]["include_in_analysis"].sum()),
        "charts_written": len(chart_files),
        "ad_data": not tables["ad_performance"].empty,
        "shipment_data": not tables["shipments"].empty,
    }


def main():
    arguments = argparse.ArgumentParser(
        description="Run the exploratory data analysis and write a report, charts and CSV files.")
    arguments.add_argument("--database", required=True, help="for example marketpulse_synthetic")
    arguments.add_argument("--schema", default="clean", help="schema with the clean tables (default: clean)")
    arguments.add_argument("--output", required=True, help="folder for the report")
    options = arguments.parse_args()

    check_eda_output_folder(options.output, options.database)   # fail early, before any work is done

    try:
        engine = connect(options.database)   # read-only
    except ConnectionProblem as problem:
        raise SystemExit(str(problem))

    try:
        print(f"exploratory data analysis: {options.database}, schema {options.schema}")
        print(f"  {kind_of_data(options.database)}")
        try:
            folder, summary = write_eda_report(engine, options.database, options.schema, options.output)
        except ValueError as problem:
            raise SystemExit(f"Could not read schema '{options.schema}': {problem}")
    finally:
        engine.dispose()

    print(f"orders counted: {summary['orders_counted']}")
    print(f"charts written: {summary['charts_written']}")
    print(f"ad data: {'yes' if summary['ad_data'] else 'no data yet'}")
    print(f"shipment data: {'yes' if summary['shipment_data'] else 'no data yet'}")
    print(f"report written to {folder}")


if __name__ == "__main__":
    main()
