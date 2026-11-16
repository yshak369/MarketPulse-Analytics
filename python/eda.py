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
