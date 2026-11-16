# Data Cleaning (Phase 3)

This file explains how the raw tables become analysis-ready tables, rule by rule, and why.

All counts in this file come from the **synthetic (fake) data**. They show what each rule does. They are not real business results.

## 1. The idea in one picture

```
raw tables (schema "public")          clean tables (schema "clean")
  filled by the import scripts   ──►    filled by python/clean_data.py
  never changed by cleaning             rebuilt from scratch on every run
  hold names, phones, addresses         hold no personal details
```

Phases 4 to 6 (exploratory analysis, SQL analysis, Power BI) read **only** the `clean` schema.

## 2. The three steps

| Step | Script | What it does | Changes data? |
|---|---|---|---|
| 1. Audit | `python/audit_data_quality.py` | Counts problems: missing values, duplicates, flags, impossible dates, broken links, amounts that do not add up, unusual numbers | No. Read-only connection |
| 2. Clean | `clean_all()` in `python/clean_data.py` | Applies the rules below, in memory | No. Works on copies |
| 3. Write | `python/clean_data.py` (command line) | Replaces the `clean` schema in **one transaction** | Only the `clean` schema |

How to run, from the project folder:

```
python python/audit_data_quality.py --database marketpulse_synthetic --period-start 2025-01-01 --period-end 2025-12-31
python python/clean_data.py --database marketpulse_synthetic
```

## 3. Design decisions

| Decision | Why |
|---|---|
| Raw tables are never changed. The `clean` schema is rebuilt from scratch on every run | Safe to run again. A mistake in a rule can always be undone by fixing the rule and running again |
| **No row is deleted.** An order that must not be counted stays, with `include_in_analysis = false` and an `exclusion_reason` | Totals always add up: raw rows = clean rows. Every number can be traced back |
| No personal details in `clean` | Analysis and dashboards can never show a name, phone or address |
| Unknown stays unknown. Estimates have their own columns and labels | A guess is never shown as a fact |
| Every rule is a small, tested Python function | Easy to explain and to check. 1 test or more per rule |

## 4. The rules

### Rows

| Found in the data | Rule | Synthetic count |
|---|---|---|
| Cancelled order (Shopify) | Kept, **not counted**. Reason `cancelled` | 20 of 2,912 orders |
| `possible_duplicate` flag | **Counted**, and the flag is kept. Owner's choice | 14 orders |
| Payment type `needs_review` | Counted. The payment type is never guessed | 12 orders |

**Trade-off of counting possible duplicates:** a real duplicate then counts as a repeat order of the same customer, so repeat figures can look slightly higher. The flag stays, so any figure can be shown with and without these orders.

### Privacy

Removed from every clean table: `customer_name`, `phone`, `address`, `pin_code`, `notes`.

A note can hold a second phone number, so the useful facts in notes become their own columns first:

| Note | New column |
|---|---|
| `pin_code_override` | `district_from_override` (true/false) |
| `refunded_amount=600` | `refunded_amount` (a number) |
| `product_defaulted_to_cxe` | `product_defaulted` (true/false), taken from the product lines |

### Places

District and state are trimmed and written in one style, so the same district is never shown twice in a chart:

| As written | After cleaning |
|---|---|
| `  ERNAKULAM ` | `Ernakulam` |
| `bengaluru   urban` | `Bengaluru Urban` |
| `ANDAMAN AND NICOBAR ISLANDS` | `Andaman and Nicobar Islands` |
| empty | stays empty (38 synthetic orders) |

### Customers

| Found in the data | Rule |
|---|---|
| `missing_phone` or `invalid_phone` flag | `customer_identified = false`. The order counts as an order, but not in repeat-customer figures |
| Counted orders of identified customers | Numbered per customer: `customer_order_number` 1, 2, 3 ... and `is_repeat_order` |

Synthetic result: 474 repeat customers, 900 repeat orders.

### Products

Orders with no product line were set to 1 cream (CXE) by the owner's rule. They are **counted** and marked with `product_defaulted`, so a chart can show "written" and "by the default rule" separately. Synthetic count: 23 orders.

### Amounts: the most important part

| Column | Meaning |
|---|---|
| `order_amount` | The amount **as recorded**. Never changed. For COD it is the amount to **collect**, not money received |
| `amount_reliable` | False when the amount is missing, or an amount flag is set (`amount_out_of_range`, `cod_amount_missing`, `cod_amount_partial`, `prepaid_with_amount`) |
| `estimated_order_value` | Worked out from the price list. An **estimate** |
| `estimated_order_cost` | Quantity × unit cost. An **estimate** |
| `order_value` | The recorded amount when it is reliable, otherwise the estimate |
| `value_basis` | `recorded`, `estimated` or `unknown`: where `order_value` comes from |

Which price an estimate uses:

| Order | Price |
|---|---|
| WhatsApp COD | `cod_price` (normal COD price) |
| WhatsApp Prepaid | `selling_price` (normal Prepaid price) |
| Shopify | `selling_price` (the website price) |
| Payment `needs_review` | none: the right price is unknown, so the value stays **unknown** |
| `cod_amount_partial` (only some COD products had an amount) | none: the one amount may be the total for the whole order, so the value stays **unknown** |
| A product with no price | none: the value stays **unknown** |

Synthetic result for the 2,892 counted orders:

| value_basis | Orders |
|---|---|
| recorded | 1,940 |
| estimated | 940 |
| unknown | 12 |

### Ads

- Meta's long result indicator becomes a short `result_type`: `messaging_conversation`, `link_click`, `post_engagement`, or `other` for a kind not seen before. It is never guessed to be one of the known kinds.
- Results of different types are never added together.
- Only raw numbers are stored. Ratios such as CPM, CTR and cost per result are worked out from them when needed.
- Week, month and weekday columns are added.

### Shipments

- `delivery_days` = delivery date − order date.
- A delivery date before the order date is impossible: `delivery_days` stays empty and `delivery_date_problem = true`.
- A shipment of a cancelled order is not counted.

## 5. Safety rules of the write step

| Rule | Why |
|---|---|
| The target schema must be `clean` or end in `_clean`, and differ from the source | The write step deletes the target first. It can never delete the raw tables |
| Everything runs in **one transaction** | If anything fails, nothing changes: the old `clean` schema stays as it was |
| The clean tables have CHECK rules (`sql/07_create_clean_tables.sql`) | The database itself refuses a result that breaks a cleaning rule, for example an order that is left out without a reason |
| Row counts are compared before the commit | A table that was not written in full is never saved |
| Errors show only their first line | A database error can quote values from a row |

## 6. How it was tested

- One test or more per rule, on tiny hand-made tables (`python/test_clean_data.py`).
- On the synthetic database: every clean table has as many rows as its raw table; ad spend and recorded amounts are identical before and after; no personal column exists in `clean`; a second run gives the same counts; the raw orders are unchanged (same fingerprint).
- A run with broken data was refused by the database, and the old `clean` schema stayed complete.

## 7. Known limits

- **Estimates.** In the owner's real data, most orders have no recorded amount, because Prepaid amounts are not written in WhatsApp. So most value figures are estimates, and every chart must say so.
- **The IQR rule** in the audit calls almost every quantity of 2 "unusual", because nearly all quantities are 1. It only reports, it never removes anything.
- **No notebook yet.** A Jupyter notebook walk-through was planned. Windows Smart App Control on the development computer blocks a file that every notebook needs (`pyzmq`). The security setting was kept on. This file explains the cleaning instead.
