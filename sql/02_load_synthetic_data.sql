-- =====================================================================
-- MarketPulse Analytics: load the SYNTHETIC (fake) data
-- =====================================================================
-- This file copies the eight CSV files in data/synthetic/ into the
-- tables made by 01_create_tables.sql.
--
-- All of this data is fake. See docs/synthetic_data_plan.md.
-- Use this file ONLY on the marketpulse_synthetic database.
--
-- How to run (from the project folder, because the file paths below
-- start from there):
--   psql -U marketpulse_user -d marketpulse_synthetic -h localhost -f sql/02_load_synthetic_data.sql
--
-- It is safe to run again: the tables are emptied first, and
-- everything happens inside one transaction (all or nothing).
--
-- Lines starting with a backslash are psql commands, not SQL, so this
-- file must be run with psql (not pasted into pgAdmin).
-- =====================================================================

-- Stop at the first error instead of carrying on.
\set ON_ERROR_STOP on

-- The CSV files are saved as UTF-8 text.
\encoding UTF8

BEGIN;

-- Empty all eight tables. RESTART IDENTITY sets the automatic
-- order_item_id numbering back to 1.
TRUNCATE TABLE
    ad_performance, ad_campaigns, shipments, order_items, orders,
    customers, product_aliases, products
RESTART IDENTITY;

-- Load order matters: a table is loaded after the tables it points to.
-- In CSV format an empty cell is loaded as NULL (unknown).

\copy products (product_code, product_name, selling_price, unit_cost, cod_price) FROM 'data/synthetic/synthetic_products.csv' WITH (FORMAT csv, HEADER true)

\copy product_aliases (alias, source, product_code) FROM 'data/synthetic/synthetic_product_aliases.csv' WITH (FORMAT csv, HEADER true)

\copy customers (customer_id, customer_name, phone) FROM 'data/synthetic/synthetic_customers.csv' WITH (FORMAT csv, HEADER true)

\copy orders (order_id, customer_id, order_datetime, sales_channel, payment_type, address, district_city, state, pin_code, order_amount, amount_basis, financial_status, fulfillment_status, cancelled_at, review_flags, notes) FROM 'data/synthetic/synthetic_orders.csv' WITH (FORMAT csv, HEADER true)

-- order_item_id is not in the file. The database numbers the rows itself.
\copy order_items (order_id, product_code, quantity, line_amount, product_defaulted) FROM 'data/synthetic/synthetic_order_items.csv' WITH (FORMAT csv, HEADER true)

\copy shipments (shipment_id, order_id, courier, delivery_status, delivered_date, cod_amount_received, shipping_cost) FROM 'data/synthetic/synthetic_shipments.csv' WITH (FORMAT csv, HEADER true)

\copy ad_campaigns (campaign_id, campaign_name, delivery_status, attribution_setting, budget_amount, budget_type, end_date) FROM 'data/synthetic/synthetic_ad_campaigns.csv' WITH (FORMAT csv, HEADER true)

\copy ad_performance (campaign_id, report_date, amount_spent_inr, impressions, reach, link_clicks, clicks_all, landing_page_views, results, result_indicator) FROM 'data/synthetic/synthetic_ad_performance.csv' WITH (FORMAT csv, HEADER true)

COMMIT;

-- Show how many rows each table now holds.
SELECT 'products' AS table_name, count(*) AS row_count FROM products
UNION ALL SELECT 'product_aliases', count(*) FROM product_aliases
UNION ALL SELECT 'customers', count(*) FROM customers
UNION ALL SELECT 'orders', count(*) FROM orders
UNION ALL SELECT 'order_items', count(*) FROM order_items
UNION ALL SELECT 'shipments', count(*) FROM shipments
UNION ALL SELECT 'ad_campaigns', count(*) FROM ad_campaigns
UNION ALL SELECT 'ad_performance', count(*) FROM ad_performance;
