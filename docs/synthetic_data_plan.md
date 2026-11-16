# Synthetic Data Plan

Status: approved plan. The data was generated in Phase 2 and is in `data/synthetic/`.

This file explains how the fake data for the public portfolio is made.

## 1. Decisions

| Topic | Decision |
|---|---|
| Public data | Fully synthetic. No real rows, not even anonymised ones |
| What is committed to Git | Both the generator script and the generated CSV files |
| Made-up period | 1 January 2025 to 31 December 2025 |

## 2. The most important rule

All settings in the generator are **invented round numbers**. They are not tuned to look like the real business.

Tuned values would leak confidential figures, such as the real COD share, ad spend or margins.

## 3. How the data is made

- One Python script, `python/generate_synthetic_data.py`, using NumPy and Pandas.
- The script uses a **fixed random seed**. The "random" numbers come out the same on every run, so anyone can rebuild exactly the same dataset.
- It fills the same eight tables as the approved schema (see `schema_design.md`).
- Output goes to `data/synthetic/`. This folder is tracked by Git, unlike `data/raw` and `data/processed`. The files are about 0.8 MB in total.

## 4. What each table gets

| Table | Plan |
|---|---|
| `products` | The same 8 product codes, with made-up prices and costs |
| `product_aliases` | Each product code as written in WhatsApp, and a made-up Shopify product title |
| `customers` | About 2,000 customers named `Synthetic Customer 0001`, `Synthetic Customer 0002` and so on. Phone left empty, so no number can belong to a real person |
| `orders` | About 3,000 orders over the made-up year. Real Indian state and district names from a public list. Address and PIN code left empty |
| `order_items` | 1 to 3 products per order |
| `ad_campaigns` | About 8 campaigns with made-up names, using both result types (messaging conversations and link clicks) |
| `ad_performance` | Daily rows. Spend, impressions and clicks are made from invented CPM and CTR ranges |
| `shipments` | Made-up delivery and return outcomes, so questions D5, D6 and P4 can be shown |

## 5. Patterns built in on purpose

These give the analysis something to find:

- More orders on some weekdays and at some hours
- A festive season peak
- Some repeat customers
- More COD orders in some states
- More orders in weeks with higher ad spend

**Honesty note:** any pattern in the public dashboard comes from the generator's rules. It is not a real business result. The README and dashboard must say this.

## 6. Messy data on purpose

A small share of rows has problems, so the cleaning phase has real work to show:

- Missing districts
- Orders with no product line (defaulted to 1 CXE)
- Orders with an unclear payment type
- Duplicate orders
- Cancelled Shopify orders

An unknown product name cannot be stored in the tables, so it appears in the fake export files instead.

Fake export files test the import code: two WhatsApp chats, a Meta Ads export and a Shopify export. They are fixed test files, not made by the generator. They follow the real layouts and contain only fake names, addresses and numbers.

## 7. Labelling

- Every file name starts with `synthetic_`, for example `synthetic_orders.csv`.
- The README, this plan and every dashboard page say "Synthetic data".
- Synthetic results are never presented as real business results.
