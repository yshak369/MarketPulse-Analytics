# Business Questions

Status: approved list.

These are the questions MarketPulse Analytics sets out to answer, grouped by module. They come from the owner's experience of running an e-commerce skincare business.

## How to read the status column

| Status | Meaning |
|---|---|
| Now | Can be answered from WhatsApp, Shopify and Meta Ads data as they are |
| Estimate | Needs the price list. The answer is always labelled as an estimate |
| Needs data | Needs courier or payment records that are not in the database yet |

## 1. Sales Analytics

| # | Question | Status |
|---|---|---|
| S1 | How many orders come in per day, week and month, and is the trend rising or falling? | Now |
| S2 | Which products sell the most units? | Now |
| S3 | Which products are most often bought together in one order? | Now |
| S4 | What share of orders comes from WhatsApp and what share from Shopify? | Now |
| S5 | Which days of the week and hours of the day bring the most orders? | Now |
| S6 | Which states and districts place the most orders? | Now |
| S7 | What is the average number of items per order? | Now |
| S8 | What is the estimated order value by month? | Estimate |

## 2. Marketing Analytics

| # | Question | Status |
|---|---|---|
| M1 | How much is spent on ads per day and per week? | Now |
| M2 | Which campaigns have the lowest cost per messaging conversation started? | Now |
| M3 | How do CPM and CTR change over time for each campaign? | Now |
| M4 | On weeks with higher ad spend, are there more orders? | Now |
| M5 | What is the overall ad spend per order, by week? | Now |
| M6 | How many messaging conversations happen for each WhatsApp order, by week? | Now |

**Important:** M4, M5 and M6 compare totals by date only. They show a pattern, not proof that a specific ad caused a specific order. No per-order attribution is claimed.

## 3. Customer Analytics

| # | Question | Status |
|---|---|---|
| C1 | What share of customers have ordered more than once? | Now |
| C2 | How many days pass between a customer's first and second order? | Now |
| C3 | What do repeat customers buy on their second order? | Now |
| C4 | How many new customers are gained each month, compared with returning ones? | Now |
| C5 | Which districts have the most repeat customers? | Now |

## 4. Profitability Analytics

| # | Question | Status |
|---|---|---|
| P1 | What is the gross margin per unit for each product (selling price minus unit cost)? | Now |
| P2 | Which products give the most estimated gross profit in total? | Estimate |
| P3 | What is the estimated gross profit per week after ad spend? | Estimate |
| P4 | How much do returned COD orders cost the business? | Needs data |
| P5 | What is the confirmed profit after shipping and returns? | Needs data |

## 5. Payment and Shipping Analytics

| # | Question | Status |
|---|---|---|
| D1 | What is the split between COD and prepaid orders, and how does it change over time? | Now |
| D2 | Which states and districts lean most towards COD? | Now |
| D3 | Do COD orders contain different products or quantities from prepaid orders? | Now |
| D4 | What is the total COD amount to be collected per week? | Now |
| D5 | What share of COD orders is delivered, and what share is returned? | Needs data |
| D6 | How long does delivery take by courier and by state? | Needs data |

**Important:** D4 is the amount to be collected. It is not confirmed revenue.

## Why "Needs data" questions stay on the list

They are the questions a real business cares about most. Keeping them, with an honest "not answerable yet", shows the limits of the data.

- **Private version:** they become answerable once courier reports (for example Delhivery COD remittance reports) are loaded into the `shipments` table. The schema already supports this.
- **Public version:** the synthetic data can include made-up delivery outcomes, so the dashboard can show these charts with a clear synthetic label.

## Rules for answering these questions

1. An estimate is always labelled as an estimate.
2. A COD collectible amount is never shown as revenue.
3. Messaging conversations and link clicks are never added together.
4. Reach is never added across days.
5. Unknown values stay unknown.
