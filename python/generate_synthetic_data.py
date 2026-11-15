"""Generate SYNTHETIC (fake) data for the public MarketPulse portfolio.

Everything this script creates is made up. All settings are invented
round numbers. They are NOT tuned to match the real business, so no
confidential figure can leak. See docs/synthetic_data_plan.md.

How to run (from the project folder):
    python python/generate_synthetic_data.py

Output: CSV files in data/synthetic/, each name starting with "synthetic_".

Tables built so far: products, product_aliases, customers.
The other tables are added in later steps.
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


def save(table, name):
    """Write one table to data/synthetic/synthetic_<name>.csv."""
    path = OUTPUT_DIR / f"synthetic_{name}.csv"
    table.to_csv(path, index=False, lineterminator="\n")
    print(f"  {path.name}: {len(table)} rows")


def main():
    rng = np.random.default_rng(SEED)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Writing SYNTHETIC data to", OUTPUT_DIR)
    save(build_products(), "products")
    save(build_product_aliases(), "product_aliases")
    save(build_customers(rng), "customers")
    print("Done. This data is fake and must never be presented as real.")


if __name__ == "__main__":
    main()
