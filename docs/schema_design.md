# Database Schema Design

Status: approved design. No database has been created yet.

All examples in this document are fake. No real customer data, spend figures or campaign names appear here.

## 1. Purpose

This file is the blueprint for the PostgreSQL database. It lists each table, its columns and how the tables link together.

The same schema is used in both environments (see `data_privacy.md`):

- **Private:** filled with the real business data, on the owner's computer only.
- **Public:** filled with clearly labelled synthetic data, for the portfolio.

## 2. Where the data comes from

| Source | Tables it fills |
|---|---|
| WhatsApp groups (through the parser) | `customers`, `orders`, `order_items` |
| Shopify order export | `customers`, `orders`, `order_items` |
| Meta Ads Manager campaigns export | `ad_campaigns`, `ad_performance` |
| Owner's own records (price list, costs, courier reports) | `products`, `product_aliases`, `shipments` |

## 3. How the tables link

```
customers ──< orders ──< order_items >── products ──< product_aliases
                 │
                 └──< shipments

ad_campaigns ──< ad_performance
```

`──<` means "one to many". For example, one customer can have many orders.

**The advertising tables are not linked to the order tables.** Nothing records which ad led to which order. Advertising and orders are compared by date only (by day or by week). No per-order attribution is claimed.

## 4. Tables

### 4.1 `products`

One row per product.

| Column | Type | Notes |
|---|---|---|
| `product_code` | text, primary key | For example `CXE`. Stored in capitals |
| `product_name` | text | For example Cream |
| `selling_price` | numeric | Normal selling price. Used only for labelled estimates |
| `unit_cost` | numeric | Cost to the business for one unit. Filled privately |

### 4.2 `product_aliases`

Shopify has no SKUs, and WhatsApp uses short codes. This table maps every way a product is written to one `product_code`.

| Column | Type | Notes |
|---|---|---|
| `alias` | text, primary key | The name exactly as written in the source, in lower case |
| `source` | text | `whatsapp` or `shopify` |
| `product_code` | text, links to `products` | The product it means |

Fake example: the alias `sample glow cream 50g` from `shopify` maps to `CXE`.

A name that is not in this table is flagged for review. It is never matched to the nearest product.

### 4.3 `customers`

One row per customer.

| Column | Type | Notes |
|---|---|---|
| `customer_id` | text, primary key | New random ID. Not made from the phone number |
| `customer_name` | text | Private only |
| `phone` | text, unique | Private only. One phone number = one customer, across WhatsApp and Shopify. Empty in synthetic data |

### 4.4 `orders`

One row per order, from WhatsApp or Shopify.

| Column | Type | Notes |
|---|---|---|
| `order_id` | text, primary key | New random ID |
| `customer_id` | text, links to `customers` | |
| `order_datetime` | timestamp | WhatsApp message time or Shopify order time |
| `sales_channel` | text | `whatsapp` or `shopify` |
| `payment_type` | text | `prepaid`, `cod` or `needs_review` |
| `address` | text | Private only |
| `district_city` | text | For WhatsApp orders, looked up from the PIN code, not read from the address text |
| `state` | text | For WhatsApp orders, looked up from the PIN code |
| `pin_code` | text | Private only, or shortened in the public version |
| `order_amount` | numeric | Can be empty. See `amount_basis` |
| `amount_basis` | text | `cod_collectible`, `shopify_total`, `estimated` or `unknown` |
| `financial_status` | text | Shopify only, for example paid or refunded |
| `fulfillment_status` | text | Shopify only |
| `cancelled_at` | timestamp | Shopify only. Empty if not cancelled |
| `review_flags` | text | Reasons for manual review. Empty if clean |
| `notes` | text | For example `product_defaulted_to_cxe` |

**Why `amount_basis` matters:** it says what `order_amount` really is, so an amount is never mistaken for confirmed revenue.

- `cod_collectible`: the amount to be collected on delivery. Not confirmed revenue.
- `shopify_total`: the order total recorded by Shopify.
- `estimated`: worked out from the price list. Always labelled as an estimate.
- `unknown`: no amount is recorded (most WhatsApp prepaid orders).

### 4.5 `order_items`

One row per product line in an order.

| Column | Type | Notes |
|---|---|---|
| `order_item_id` | integer, primary key | Automatic number |
| `order_id` | text, links to `orders` | |
| `product_code` | text, links to `products` | |
| `quantity` | integer | 1 or more |
| `line_amount` | numeric | Total for the line, not the price per unit. Empty for WhatsApp prepaid |
| `product_defaulted` | true/false | True when the order had no product line and was treated as 1 CXE |

### 4.6 `ad_campaigns`

One row per Meta campaign.

| Column | Type | Notes |
|---|---|---|
| `campaign_id` | text, primary key | Meta's own Campaign ID, from the export |
| `campaign_name` | text | Not unique. Several campaigns can share one name |
| `delivery_status` | text | For example active or inactive |
| `attribution_setting` | text | Empty when Meta shows `-` |
| `budget_amount` | numeric | Empty when the budget is set at ad set level |
| `budget_type` | text | For example daily, or `ad_set_level` |
| `end_date` | date | Empty when the campaign is ongoing |

**Why Meta's Campaign ID is the key:** campaign names are not unique, so a name cannot safely identify a campaign. The ID can.

### 4.7 `ad_performance`

One row per campaign per day.

| Column | Type | Notes |
|---|---|---|
| `campaign_id` | text, links to `ad_campaigns` | |
| `report_date` | date | The day the numbers are for |
| `amount_spent_inr` | numeric | |
| `impressions` | integer | |
| `reach` | integer | |
| `link_clicks` | integer | |
| `clicks_all` | integer | |
| `landing_page_views` | integer | |
| `results` | integer | Meaning depends on `result_indicator` |
| `result_indicator` | text | What a "result" is, for example a messaging conversation started or a link click |

Primary key: `campaign_id` and `report_date` together. A campaign has at most one row per day.

Rows with zero impressions are skipped when loading, because inactive campaigns still appear in every daily export.

### 4.8 `shipments`

One row per shipment. Most of this table will be empty until courier records are added.

| Column | Type | Notes |
|---|---|---|
| `shipment_id` | text, primary key | New random ID |
| `order_id` | text, links to `orders` | |
| `courier` | text | `speed_post` (prepaid) or `delhivery` (COD) |
| `delivery_status` | text | For example delivered, returned or unknown |
| `delivered_date` | date | |
| `cod_amount_received` | numeric | Money actually received for a COD order |
| `shipping_cost` | numeric | |

## 5. Design rules

1. **Store raw numbers only.** CPM, CPC, CTR, frequency and cost per result are not stored. They are calculated in SQL from spend, impressions, reach, clicks and results. This avoids two versions of the same number.
2. **Never add results of different kinds.** `results` is totalled only within the same `result_indicator`. Messaging conversations and link clicks are different things.
3. **Never add reach across days.** The same person can be reached on several days, so adding daily reach counts them more than once.
4. **Load only the campaigns export.** The ad set and ad exports contain the same spend at a finer level. Loading all three would count spend three times.
5. **Unknown stays unknown.** Empty values are left empty. They are not filled with guesses.
6. **Estimates are labelled.** Any estimated amount has `amount_basis = 'estimated'`.
7. **Flag, do not guess.** Unknown products and unclear fields go to manual review.
8. **Keep only useful Shopify columns.** About 20 of the roughly 70 export columns are kept. The exact headings are checked when the import code is written.

## 6. Public version

- Same tables and columns, filled with synthetic data that is labelled as synthetic.
- No real names, phones, addresses or PIN codes.
- Campaign names are replaced with made-up names.
- No real spend, revenue or profit figures.

## 7. Still to confirm

1. **COD amounts:** one amount per product line is assumed (see `whatsapp_parser_plan.md`).
2. **Shipment records:** which courier reports are available to fill `shipments`.
3. **Shopify headings:** exact column names, to be read from the real export file locally.
