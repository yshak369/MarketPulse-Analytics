"""Generate SYNTHETIC (fake) data for the public MarketPulse portfolio.

Everything this script creates is made up. All settings are invented
round numbers. They are NOT tuned to match the real business, so no
confidential figure can leak. See docs/synthetic_data_plan.md.

How to run (from the project folder):
    python python/generate_synthetic_data.py

Output: CSV files in data/synthetic/, each name starting with "synthetic_".

Tables built so far: products, product_aliases, customers, orders,
order_items. The other tables are added in later steps.
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

    print("Done. This data is fake and must never be presented as real.")


if __name__ == "__main__":
    main()
