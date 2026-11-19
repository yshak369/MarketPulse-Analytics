# Power BI Dashboard (Phase 6)

This file explains the Power BI dashboard in `dashboards/marketpulse_synthetic.pbix`: how it is built, which rules it follows, and how every number was checked.

All figures come from the **synthetic (fake) data** in `marketpulse_synthetic`. They are not real business results.

## 1. What is in `dashboards/`

| File | What it is |
|---|---|
| `marketpulse_synthetic.pbix` | The Power BI report (synthetic data only). |
| `01_overview.png` | Overview page. |
| `02_sales.png` | Sales page. |
| `03_payment_shipping.png` | Payment & Shipping page. |
| `04_marketing.png` | Marketing page. |
| `05_customers.png` | Customers page. |

A report built on the private database is a different file. It must never be committed (see `docs/data_privacy.md`).

## 2. How the data gets in

- Power BI Desktop, **Get data → PostgreSQL database**, server `localhost`, database `marketpulse_synthetic`, **Import** mode.
- Seven tables from the `clean` schema: `orders`, `order_items`, `customers`, `products`, `shipments`, `ad_campaigns`, `ad_performance`.
- Power BI imports them as `clean orders` and so on, because it adds the schema name — each table was renamed (`orders`, `order_items`, ...) straight after import, so every DAX formula below can use the plain name.
- Import mode keeps a copy of the data inside the `.pbix`, so the file opens without the database. **Refresh** needs PostgreSQL running.

## 3. The data model

| From (many) | To (one) | Notes |
|---|---|---|
| `orders[customer_id]` | `customers[customer_id]` | |
| `order_items[order_id]` | `orders[order_id]` | |
| `order_items[product_code]` | `products[product_code]` | |
| `shipments[order_id]` | `orders[order_id]` | One order, one shipment (one-to-one). |
| `ad_performance[campaign_id]` | `ad_campaigns[campaign_id]` | |
| `orders[order_date]` | `Date[Date]` | |
| `ad_performance[report_date]` | `Date[Date]` | |

- **There is no link between ads and orders.** Nothing records which ad led to which order, so the model never joins them. The dashboard shows spend next to orders, never "ROAS" or cost per order.
- **`Date`** is a calendar table made with DAX. It runs from 1 January of the earliest year to 31 December of the latest year in the data, and has Year, Month Number, Month Name, Year-Month and Week Number columns. Month Name is sorted by Month Number.
- **`customers` is not linked to `Date`**, so the month slicer does not change the customer cards. The Customers page has no slicer for that reason.

## 4. Rules every measure follows

1. **Counted rows only.** Orders, shipments and order items are filtered to `include_in_analysis = TRUE`. Customers must have `orders_counted > 0`.
2. **Recorded and estimated are kept apart.** `Order Value` is shown as recorded + estimated and labelled so on the dashboard.
3. **A COD amount is the amount to collect, not confirmed revenue.**
4. **Different result types are never added together.** Messaging conversations are counted only where `result_type = 'messaging_conversation'`, and cost per conversation uses only that spend.

## 5. The measures, and how each was checked

Each total was compared with the figures already published in `reports/eda_synthetic/` and `docs/sql_analysis.md`.

| Measure | Idea | Result in Power BI | Checked against |
|---|---|---|---|
| Total Orders | Count of counted orders | 2,892 (October 352) | S1 / S8 |
| Recorded Order Value | Sum of `order_value`, basis "recorded" | 1,380,350 | S8 |
| Estimated Order Value | Same, basis "estimated" | 588,700 | S8 |
| Order Value | Recorded + estimated | 1,969,050 | S8 |
| COD Share | COD / (COD + prepaid) | 58.75% | D1 (59%) |
| Shipments / Delivered Shipments | Counted parcels / delivered ones | 2,880 / 2,498 | D5 |
| Delivery Share | Delivered / shipments | 86.74% | D5 |
| Average Delivery Days | Mean of `delivery_days` | 4.49 | D6 |
| Identified Customers | Customers with a counted order | 1,992 | C1 |
| Repeat Customers / Share | Customers with more than one order | 474 / 23.80% | C1 |
| Ad Spend | Sum of `amount_spent_inr` | 422,947.96 | M1 |
| Messaging Conversations | Sum of `results` for conversation rows | 26,156 | M2 |
| Cost per Conversation | Conversation spend / conversations | 15.70 (per campaign 15.31 to 16.02) | M2 |
| Total Impressions / Total Clicks | Sums | 3,813,854 / 94,249 | M3 |
| CPM / CTR | Spend per 1,000 impressions / clicks per impression | 110.90 / 2.47% | M3 |
| Total Units / Defaulted Units | Items sold / items assumed to be 1 cream | Same product ranking as S2 (Cream first) | S2 |
| New / Returning Customer Orders | Orders with customer order number 1 / above 1 | January 232 / 9 | C4 |

## 6. The five pages

| Page | What it shows |
|---|---|
| Overview | Total orders, order value, ad spend, delivery share; orders per month; recorded vs estimated value per month; month slicer. |
| Sales | Units by product, orders by state, orders by sales channel; month slicer. |
| Payment & Shipping | Courier table (shipments, delivered, delivery share, average days); COD vs prepaid orders per month; month slicer. |
| Marketing | Campaign table (spend, conversations, cost per conversation, CPM, clicks, CTR); ad spend per month; month slicer. |
| Customers | Identified and repeat customers; new vs returning customer orders per month. |

A hidden `Checks` page holds the working tables used to test each measure.

## 7. Mistakes caught while building

These were found by checking the numbers, not by trusting the formulas:

- **Total Orders showed 354 for October, not 352.** The measure did not skip rows with `include_in_analysis = FALSE`. Fixed in the measure.
- **Identified Customers showed 2,000, not 1,992.** Eight customers had only excluded orders. Fixed with `orders_counted > 0`.
- **Total cost per conversation showed 16.17, not 15.70.** The two Instagram boost campaigns spent money but started no conversations. Fixed by dividing only conversation spend.
- **A measure named `Impressions` clashed with the column `impressions`.** Renamed `Total Impressions`.
- **A first guess at the expected order value (Rs 1,241,030) was wrong.** That figure is a price-list estimate by product (P2), a different thing from `order_value`.

## 8. Known limits

- **No Profitability page.** Gross margin and profit are in the SQL analysis (P1 to P3) but not on this dashboard. P4 and P5 still need return-cost and confirmed-payment data.
- **Order Value mixes recorded and estimated amounts.** The dashboard says so, and the recorded/estimated chart shows both.
- **Ad spend is not linked to orders.** Weekly spend and weekly orders can be compared as a pattern, not as cause and effect.
- **Synthetic data has built-in patterns** (see `docs/sql_analysis.md`, section 6). A tidy number is not an insight.
