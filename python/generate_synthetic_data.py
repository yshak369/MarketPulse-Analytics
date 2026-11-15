"""Generate SYNTHETIC (fake) data for the public MarketPulse portfolio.

Everything this script creates is made up. All settings are invented
round numbers. They are NOT tuned to match the real business, so no
confidential figure can leak. See docs/synthetic_data_plan.md.

How to run (from the project folder):
    python python/generate_synthetic_data.py

Output: CSV files in data/synthetic/, each name starting with "synthetic_".

Tables built so far: products, product_aliases, customers, orders,
order_items, ad_campaigns, ad_performance, shipments.
"""

from pathlib import Path

import numpy as np
import pandas as pd

# A fixed seed makes the "random" numbers the same on every run,
# so anyone can rebuild exactly the same dataset.
SEED = 42

NUM_CUSTOMERS = 2000

# Folder for the output files: <project>/data/synthetic
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "synthetic"

# Invented products: (code, name, selling price, unit cost).
# The prices and costs are made-up round numbers, not real ones.
PRODUCTS = [
    ("CXE", "Cream", 500, 200),
    ("FW", "Facewash", 300, 120),
    ("BL", "Body lotion", 400, 160),
    ("LP", "Lip balm", 150, 60),
    ("SS", "Sunscreen", 450, 180),
    ("SERUM", "Serum", 600, 240),
    ("KOJIGLOW", "Kojiglow", 350, 140),
    ("MOISTURIZER", "Moisturizer", 400, 160),
]

# Made-up Shopify product titles (Shopify has no SKUs, so titles are mapped).
SHOPIFY_TITLES = {
    "CXE": "synthetic glow cream 50g",
    "FW": "synthetic gentle facewash 100ml",
    "BL": "synthetic body lotion 200ml",
    "LP": "synthetic lip balm 10g",
    "SS": "synthetic sunscreen spf 50",
    "SERUM": "synthetic face serum 30ml",
    "KOJIGLOW": "synthetic kojiglow soap 75g",
    "MOISTURIZER": "synthetic daily moisturizer 100ml",
}

# ---------------------------------------------------------------------
# Invented settings for orders. None of these come from the real business.
# ---------------------------------------------------------------------

# The made-up year the synthetic orders fall in.
PERIOD_START = "2025-01-01"
PERIOD_END = "2025-12-31"

# How many orders a customer places, and how likely each count is.
# 75% order once; the other 25% are repeat customers.
ORDER_COUNTS = [1, 2, 3, 4, 5]
ORDER_COUNT_CHANCES = [0.75, 0.11, 0.07, 0.05, 0.02]

# State: (share of customers, share of orders that are COD, districts).
# The place names are real and public. The shares are invented.
STATES = {
    "Kerala": (0.25, 0.60, ["Thiruvananthapuram", "Kollam", "Ernakulam", "Thrissur", "Kozhikode"]),
    "Tamil Nadu": (0.20, 0.60, ["Chennai", "Coimbatore", "Madurai", "Tiruchirappalli", "Salem"]),
    "Karnataka": (0.15, 0.50, ["Bengaluru Urban", "Mysuru", "Dakshina Kannada", "Belagavi"]),
    "Maharashtra": (0.15, 0.50, ["Mumbai", "Pune", "Nagpur", "Nashik"]),
    "Telangana": (0.15, 0.75, ["Hyderabad", "Warangal", "Karimnagar", "Nizamabad"]),
    "Andhra Pradesh": (0.10, 0.75, ["Visakhapatnam", "Guntur", "Krishna", "Chittoor"]),
}

WHATSAPP_SHARE = 0.80  # the rest of the orders come from Shopify

# Timing patterns, built in on purpose so the analysis has something to find.
WEEKEND_BOOST = 1.3    # Saturdays and Sundays get 1.3 times the orders
FESTIVE_START = "2025-10-10"
FESTIVE_END = "2025-11-10"
FESTIVE_BOOST = 1.8    # the festive season gets 1.8 times the orders

# Relative chance of an order in each hour of the day (0 = midnight).
# Quiet at night, busiest in the evening.
HOUR_WEIGHTS = [1, 1, 1, 1, 1, 1, 2, 3, 4, 5, 6, 6,
                6, 5, 5, 5, 6, 7, 8, 10, 10, 9, 6, 3]

# How many different products are in one order.
ITEMS_PER_ORDER = [1, 2, 3]
ITEMS_PER_ORDER_CHANCES = [0.70, 0.22, 0.08]

# How likely each product is to be picked (same order as PRODUCTS).
PRODUCT_CHANCES = [0.40, 0.12, 0.08, 0.10, 0.10, 0.08, 0.07, 0.05]

QUANTITY_TWO_CHANCE = 0.10       # most lines have quantity 1

# Messy rows, added on purpose so the cleaning phase has real work.
MISSING_DISTRICT_CHANCE = 0.01   # any order
DEFAULTED_PRODUCT_CHANCE = 0.01  # WhatsApp orders with no product line
PAYMENT_CONFLICT_CHANCE = 0.005  # WhatsApp orders with unclear payment type
DUPLICATE_SHARE = 0.005          # WhatsApp orders posted twice
SHOPIFY_CANCEL_CHANCE = 0.03     # Shopify orders that were cancelled

# ---------------------------------------------------------------------
# Invented settings for advertising. None of these come from the real business.
# ---------------------------------------------------------------------

# What a "result" means for each kind of campaign. These two must never
# be added together.
RESULT_INDICATORS = {
    "messaging": "actions:onsite_conversion.messaging_conversation_started_7d",
    "post": "actions:link_click",
}

# Made-up campaigns:
# (name, kind, start date, end date or None if ongoing,
#  budget amount or None if set at ad set level, usual spend per day in rupees)
# Two campaigns share one name on purpose. Real exports do this too,
# which is why the campaign ID, not the name, is the key.
CAMPAIGNS = [
    ("Synthetic WhatsApp Campaign A", "messaging", "2025-01-01", None, 500, 450),
    ("Synthetic WhatsApp Campaign B", "messaging", "2025-01-01", "2025-06-30", None, 300),
    ("Synthetic WhatsApp Campaign C", "messaging", "2025-04-01", None, 400, 350),
    ("Synthetic Festive Offer Campaign", "messaging", "2025-10-01", "2025-11-15", 800, 700),
    ("Synthetic WhatsApp Campaign E", "messaging", "2025-07-01", None, None, 300),
    ("Synthetic Instagram Post Boost", "post", "2025-02-01", "2025-02-28", 200, 150),
    ("Synthetic Instagram Post Boost", "post", "2025-06-01", "2025-06-30", 200, 150),
    ("Synthetic Instagram Reel Boost", "post", "2025-09-01", "2025-09-21", 250, 200),
]

NO_DELIVERY_CHANCE = 0.03        # days when a campaign showed no ads at all
SPEND_NOISE = 0.15               # how much daily spend wobbles at random

# Ranges used to build the daily numbers, as (lowest, highest).
CPM_RANGE = {"messaging": (80, 150), "post": (60, 120)}  # rupees per 1,000 impressions
REACH_SHARE_RANGE = (0.75, 0.95)       # reach as a share of impressions
CTR_RANGE = (0.015, 0.035)             # all clicks as a share of impressions
LINK_CLICK_SHARE_RANGE = (0.50, 0.80)  # link clicks as a share of all clicks
CONVERSATION_SHARE_RANGE = (0.30, 0.60)  # conversations started per link click
LANDING_VIEW_SHARE_RANGE = (0.60, 0.90)  # landing page views per link click

# ---------------------------------------------------------------------
# Invented settings for shipments. None of these come from the real business.
# ---------------------------------------------------------------------

# Payment type: (courier, delivery days lowest-highest, shipping cost lowest-highest,
#                chance of delivered / returned / unknown)
SHIPPING = {
    "prepaid": ("speed_post", (3, 8), (50, 80), [0.96, 0.02, 0.02]),
    "cod": ("delhivery", (2, 6), (70, 110), [0.80, 0.17, 0.03]),
}
DELIVERY_STATUSES = ["delivered", "returned", "unknown"]

# The made-up state that parcels are sent from. Orders to this state
# arrive one day faster. This is an invented choice.
DISPATCH_STATE = "Karnataka"


def make_random_ids(rng, prefix, count):
    """Return `count` unique random IDs such as 'C-3f9a1c2e'.

    The IDs are random on purpose. They are never made from a phone
    number or a name, so they reveal nothing about a person.
    """
    ids = set()
    while len(ids) < count:
        number = int(rng.integers(0, 16**8))
        ids.add(f"{prefix}-{number:08x}")
    # Sort first so the result does not depend on set ordering,
    # then shuffle with the seeded generator.
    id_list = sorted(ids)
    rng.shuffle(id_list)
    return id_list


def build_products():
    """One row per product."""
    return pd.DataFrame(
        PRODUCTS,
        columns=["product_code", "product_name", "selling_price", "unit_cost"],
    )


def build_product_aliases():
    """Every way a product is written, mapped to one product_code."""
    rows = []
    for code, _name, _price, _cost in PRODUCTS:
        # In WhatsApp the product is written as its code, in any letter case.
        rows.append({"alias": code.lower(), "source": "whatsapp", "product_code": code})
        # In Shopify the product is written as a full title.
        rows.append({"alias": SHOPIFY_TITLES[code], "source": "shopify", "product_code": code})
    return pd.DataFrame(rows)


def build_customers(rng):
    """Fake customers. The phone is left empty so no number can be real."""
    customer_ids = make_random_ids(rng, "C", NUM_CUSTOMERS)
    names = [f"Synthetic Customer {i:04d}" for i in range(1, NUM_CUSTOMERS + 1)]
    return pd.DataFrame(
        {
            "customer_id": customer_ids,
            "customer_name": names,
            "phone": pd.NA,
        }
    )


def pick_order_datetimes(rng, count):
    """Pick `count` random date-times in the made-up year.

    Weekends and the festive season are more likely, and evenings are
    busier than nights.
    """
    days = pd.date_range(PERIOD_START, PERIOD_END, freq="D")

    day_weights = np.ones(len(days))
    day_weights[days.dayofweek >= 5] *= WEEKEND_BOOST  # 5 = Saturday, 6 = Sunday
    is_festive = (days >= FESTIVE_START) & (days <= FESTIVE_END)
    day_weights[is_festive] *= FESTIVE_BOOST
    day_chances = day_weights / day_weights.sum()      # chances must add up to 1

    hour_chances = np.array(HOUR_WEIGHTS) / sum(HOUR_WEIGHTS)

    chosen_days = rng.choice(len(days), size=count, p=day_chances)
    hours = rng.choice(24, size=count, p=hour_chances)
    minutes = rng.integers(0, 60, size=count)
    seconds = rng.integers(0, 60, size=count)

    return [
        days[d] + pd.Timedelta(hours=int(h), minutes=int(m), seconds=int(s))
        for d, h, m, s in zip(chosen_days, hours, minutes, seconds)
    ]


def pick_items(rng):
    """Pick the products and quantities for one normal order.

    Returns a list of (product_code, quantity, selling_price).
    """
    item_count = rng.choice(ITEMS_PER_ORDER, p=ITEMS_PER_ORDER_CHANCES)
    # replace=False means the same product is not picked twice in one order.
    chosen = rng.choice(len(PRODUCTS), size=item_count, replace=False, p=PRODUCT_CHANCES)
    items = []
    for index in chosen:
        code, _name, price, _cost = PRODUCTS[index]
        quantity = 2 if rng.random() < QUANTITY_TWO_CHANCE else 1
        items.append((code, quantity, price))
    return items


def build_orders_and_items(rng, customers):
    """Build the orders table and the order_items table together.

    They are built together because an order's amount is the total of
    its item lines.
    """
    state_names = list(STATES)
    state_chances = [STATES[name][0] for name in state_names]

    # Each customer gets a home state and district, and a number of orders.
    home_states = rng.choice(state_names, size=len(customers), p=state_chances)
    home_districts = [rng.choice(STATES[state][2]) for state in home_states]
    order_counts = rng.choice(ORDER_COUNTS, size=len(customers), p=ORDER_COUNT_CHANCES)

    total_orders = int(order_counts.sum())
    datetimes = pick_order_datetimes(rng, total_orders)

    orders = []
    items = []
    order_number = 0

    for customer_index, customer_id in enumerate(customers["customer_id"]):
        state = home_states[customer_index]
        district = home_districts[customer_index]
        cod_share = STATES[state][1]

        for _ in range(order_counts[customer_index]):
            channel = "whatsapp" if rng.random() < WHATSAPP_SHARE else "shopify"
            payment_type = "cod" if rng.random() < cod_share else "prepaid"
            flags = []
            notes = None
            defaulted = False
            amount_known = True

            order_items = pick_items(rng)

            if channel == "whatsapp":
                # WhatsApp prepaid amounts are not recorded.
                if payment_type == "prepaid":
                    amount_known = False

                messy = rng.random()
                if messy < DEFAULTED_PRODUCT_CHANCE:
                    # No product line was written: owner's rule says 1 cream.
                    order_items = [("CXE", 1, PRODUCTS[0][2])]
                    defaulted = True
                    notes = "product_defaulted_to_cxe"
                    if payment_type == "cod":
                        # No product line also means no COD amount.
                        amount_known = False
                        flags.append("cod_amount_missing")
                elif messy < DEFAULTED_PRODUCT_CHANCE + PAYMENT_CONFLICT_CHANCE:
                    # The message text disagrees with the group it was posted in.
                    payment_type = "needs_review"
                    amount_known = False
                    flags.append("payment_conflict")

            order_district = district
            if rng.random() < MISSING_DISTRICT_CHANCE:
                order_district = None
                flags.append("missing_district")

            # Work out the amount and say honestly what kind of amount it is.
            if amount_known:
                order_amount = sum(quantity * price for _code, quantity, price in order_items)
                amount_basis = "shopify_total" if channel == "shopify" else "cod_collectible"
            else:
                order_amount = None
                amount_basis = "unknown"

            # Shopify-only columns.
            financial_status = None
            fulfillment_status = None
            cancelled_at = None
            order_datetime = datetimes[order_number]
            if channel == "shopify":
                financial_status = "paid" if payment_type == "prepaid" else "pending"
                fulfillment_status = "fulfilled"
                if rng.random() < SHOPIFY_CANCEL_CHANCE:
                    fulfillment_status = "unfulfilled"
                    cancelled_at = order_datetime + pd.Timedelta(hours=int(rng.integers(1, 48)))

            orders.append(
                {
                    "customer_id": customer_id,
                    "order_datetime": order_datetime,
                    "sales_channel": channel,
                    "payment_type": payment_type,
                    "address": None,
                    "district_city": order_district,
                    "state": state,
                    "pin_code": None,
                    "order_amount": order_amount,
                    "amount_basis": amount_basis,
                    "financial_status": financial_status,
                    "fulfillment_status": fulfillment_status,
                    "cancelled_at": cancelled_at,
                    "review_flags": ";".join(flags) if flags else None,
                    "notes": notes,
                    # Kept only while building; removed before saving.
                    "_items": [
                        {
                            "product_code": code,
                            "quantity": quantity,
                            "line_amount": quantity * price if amount_known else None,
                            "product_defaulted": defaulted,
                        }
                        for code, quantity, price in order_items
                    ],
                }
            )
            order_number += 1

    # Duplicates: a few clean WhatsApp orders are posted a second time,
    # a few minutes later. The copy is flagged, not deleted.
    clean_whatsapp = [
        index for index, order in enumerate(orders)
        if order["sales_channel"] == "whatsapp" and order["review_flags"] is None
    ]
    duplicate_count = round(DUPLICATE_SHARE * len(orders))
    last_moment = pd.Timestamp(PERIOD_END) + pd.Timedelta(hours=23, minutes=59, seconds=59)
    for index in rng.choice(clean_whatsapp, size=duplicate_count, replace=False):
        copy = dict(orders[index])
        copy["_items"] = [dict(item) for item in orders[index]["_items"]]
        later = copy["order_datetime"] + pd.Timedelta(minutes=int(rng.integers(1, 30)))
        copy["order_datetime"] = min(later, last_moment)
        copy["review_flags"] = "possible_duplicate"
        orders.append(copy)

    # Put orders in date order, then give each one a random ID.
    orders.sort(key=lambda order: order["order_datetime"])
    order_ids = make_random_ids(rng, "O", len(orders))
    for order, order_id in zip(orders, order_ids):
        order["order_id"] = order_id
        for item in order.pop("_items"):
            items.append({"order_id": order_id, **item})

    order_columns = [
        "order_id", "customer_id", "order_datetime", "sales_channel", "payment_type",
        "address", "district_city", "state", "pin_code", "order_amount", "amount_basis",
        "financial_status", "fulfillment_status", "cancelled_at", "review_flags", "notes",
    ]
    orders_table = pd.DataFrame(orders, columns=order_columns)
    items_table = pd.DataFrame(
        items, columns=["order_id", "product_code", "quantity", "line_amount", "product_defaulted"]
    )

    # "Int64" keeps whole numbers whole (500, not 500.0) even with empty cells.
    orders_table["order_amount"] = orders_table["order_amount"].astype("Int64")
    items_table["line_amount"] = items_table["line_amount"].astype("Int64")

    return orders_table, items_table


def build_ads(rng, orders):
    """Build the ad_campaigns table and the ad_performance table.

    IMPORTANT: the link between spend and orders is artificial. Weeks
    with more synthetic orders are given more ad spend, plus random
    noise. So spend and orders move together in this data only because
    this function makes them. It proves nothing about real advertising.
    """
    # How busy each week was, compared with an average week (1.0 = average).
    # A week is named by its Monday.
    order_days = orders["order_datetime"].dt.normalize()
    week_starts = order_days - pd.to_timedelta(order_days.dt.dayofweek, unit="D")
    orders_per_week = week_starts.value_counts()
    week_factor = (orders_per_week / orders_per_week.mean()).clip(0.5, 2.0)

    # Made-up 18-digit campaign IDs.
    campaign_ids = set()
    while len(campaign_ids) < len(CAMPAIGNS):
        campaign_ids.add("120" + "".join(str(d) for d in rng.integers(0, 10, size=15)))
    campaign_ids = sorted(campaign_ids)
    rng.shuffle(campaign_ids)

    campaigns = []
    performance = []

    for campaign_id, (name, kind, start, end, budget, usual_spend) in zip(campaign_ids, CAMPAIGNS):
        campaigns.append(
            {
                "campaign_id": campaign_id,
                "campaign_name": name,
                "delivery_status": "active" if end is None else "inactive",
                "attribution_setting": "7-day click or 1-day view" if kind == "messaging" else None,
                "budget_amount": budget,
                "budget_type": "daily" if budget is not None else "ad_set_level",
                "end_date": end,
            }
        )

        # One row per day the campaign was running, inside the made-up year.
        for day in pd.date_range(start, end or PERIOD_END, freq="D"):
            if rng.random() < NO_DELIVERY_CHANCE:
                continue  # no ads shown that day, so no row (zero-impression rows are skipped)

            week_start = day - pd.Timedelta(days=day.dayofweek)
            busy = week_factor.get(week_start, 1.0)
            spend = round(usual_spend * busy * rng.lognormal(0, SPEND_NOISE), 2)

            # Each number is built from the one before it, so they always
            # make sense together (for example reach is never above impressions).
            impressions = max(1, int(spend / rng.uniform(*CPM_RANGE[kind]) * 1000))
            reach = max(1, int(impressions * rng.uniform(*REACH_SHARE_RANGE)))
            clicks_all = int(impressions * rng.uniform(*CTR_RANGE))
            link_clicks = int(clicks_all * rng.uniform(*LINK_CLICK_SHARE_RANGE))

            if kind == "messaging":
                # The result is a WhatsApp conversation started.
                results = int(link_clicks * rng.uniform(*CONVERSATION_SHARE_RANGE))
                landing_page_views = None   # these ads open WhatsApp, not a web page
            else:
                # The result is a link click.
                results = link_clicks
                landing_page_views = int(link_clicks * rng.uniform(*LANDING_VIEW_SHARE_RANGE))

            performance.append(
                {
                    "campaign_id": campaign_id,
                    "report_date": day.strftime("%Y-%m-%d"),
                    "amount_spent_inr": spend,
                    "impressions": impressions,
                    "reach": reach,
                    "link_clicks": link_clicks,
                    "clicks_all": clicks_all,
                    "landing_page_views": landing_page_views,
                    "results": results,
                    "result_indicator": RESULT_INDICATORS[kind],
                }
            )

    campaigns_table = pd.DataFrame(campaigns)
    campaigns_table["budget_amount"] = campaigns_table["budget_amount"].astype("Int64")

    performance_table = pd.DataFrame(performance)
    performance_table["landing_page_views"] = performance_table["landing_page_views"].astype("Int64")
    performance_table = performance_table.sort_values(
        ["report_date", "campaign_id"], kind="stable"
    ).reset_index(drop=True)

    return campaigns_table, performance_table


def build_shipments(rng, orders):
    """Build the shipments table: one row per order that was sent.

    Cancelled Shopify orders and 'needs_review' orders are not sent,
    so they get no shipment.

    The delivery and return rates are invented. They are not real results.
    """
    shipments = []

    for order in orders.itertuples():
        was_cancelled = not pd.isna(order.cancelled_at)
        if was_cancelled or order.payment_type == "needs_review":
            continue

        courier, day_range, cost_range, status_chances = SHIPPING[order.payment_type]
        status = rng.choice(DELIVERY_STATUSES, p=status_chances)

        # Delivery time in days. rng.integers leaves out the top number, so add 1.
        days = int(rng.integers(day_range[0], day_range[1] + 1))
        if order.state == DISPATCH_STATE:
            days -= 1

        shipping_cost = int(rng.integers(cost_range[0], cost_range[1] + 1))
        if status == "returned" and order.payment_type == "cod":
            shipping_cost *= 2  # paid for the trip out and the trip back

        delivered_date = None
        cod_amount_received = None
        if status == "delivered":
            delivered_date = (order.order_datetime + pd.Timedelta(days=days)).strftime("%Y-%m-%d")
            # Money is received only for a delivered COD order with a known amount.
            if order.payment_type == "cod" and not pd.isna(order.order_amount):
                cod_amount_received = order.order_amount

        shipments.append(
            {
                "order_id": order.order_id,
                "courier": courier,
                "delivery_status": status,
                "delivered_date": delivered_date,
                "cod_amount_received": cod_amount_received,
                "shipping_cost": shipping_cost,
            }
        )

    shipments_table = pd.DataFrame(shipments)
    shipments_table.insert(0, "shipment_id", make_random_ids(rng, "S", len(shipments_table)))
    shipments_table["cod_amount_received"] = shipments_table["cod_amount_received"].astype("Int64")
    return shipments_table


def save(table, name):
    """Write one table to data/synthetic/synthetic_<name>.csv."""
    path = OUTPUT_DIR / f"synthetic_{name}.csv"
    table.to_csv(path, index=False, lineterminator="\n", date_format="%Y-%m-%d %H:%M:%S")
    print(f"  {path.name}: {len(table)} rows")


def main():
    rng = np.random.default_rng(SEED)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Writing SYNTHETIC data to", OUTPUT_DIR)
    save(build_products(), "products")
    save(build_product_aliases(), "product_aliases")

    customers = build_customers(rng)
    save(customers, "customers")

    orders, order_items = build_orders_and_items(rng, customers)
    save(orders, "orders")
    save(order_items, "order_items")

    ad_campaigns, ad_performance = build_ads(rng, orders)
    save(ad_campaigns, "ad_campaigns")
    save(ad_performance, "ad_performance")

    save(build_shipments(rng, orders), "shipments")

    print("Done. This data is fake and must never be presented as real.")


if __name__ == "__main__":
    main()
