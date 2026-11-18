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

from itertools import combinations

import numpy as np
import pandas as pd

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
UNKNOWN = "(unknown)"
ALL_STATES = "(all states)"
VALUE_BASES = ["recorded", "estimated", "unknown"]


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
