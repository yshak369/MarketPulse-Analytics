-- =====================================================================
-- MarketPulse Analytics: load a cleaned Shopify orders export
-- =====================================================================
-- Reads the files written by python/prepare_shopify_orders.py:
--   shopify_orders.csv and shopify_order_items.csv
-- and loads them into customers, orders and order_items.
--
-- How to run (from the project folder):
--   psql -U marketpulse_user -d <database> -h localhost
--        -v schema=<schema> -v input_folder=<folder with the files>
--        -f sql/05_load_shopify_orders.sql
--   The folder must use forward slashes and contain no spaces.
--
-- Test run on the fake export (see sql/test_setup_parser_schema.sql):
--   psql -U marketpulse_user -d marketpulse_synthetic -h localhost -v schema=parser_test -v input_folder=data/processed/shopify_test_output -f sql/05_load_shopify_orders.sql
--
-- Rules:
--   * Shopify order IDs are fixed (S-1001), so this script "upserts":
--     an order already in the database is updated, a new one is added.
--     Its product lines are replaced. Orders not in this export are kept.
--   * One phone number = one customer, across WhatsApp and Shopify.
--   * An order without a phone keeps the customer it already has, or
--     gets its own new customer. Orders without phones are never merged.
--   * Flagged orders ARE loaded, with their review_flags.
--   * An order the tables cannot hold (unknown product, quantity below
--     1, product missing from the products table) is skipped and listed.
--   * All or nothing: everything runs inside one transaction.
--
-- Safety: the script refuses to load into the public schema of
-- marketpulse_synthetic.
-- =====================================================================

\set ON_ERROR_STOP on
\encoding UTF8

\if :{?schema}
\else
  \echo 'Missing setting: add -v schema=<schema name> to the command.'
  \set schema __missing__
\endif
\if :{?input_folder}
\else
  \echo 'Missing setting: add -v input_folder=<folder with the files> to the command.'
  \set input_folder __missing__
\endif

SET search_path TO :"schema";

DO $$
BEGIN
    IF current_schema() IS NULL THEN
        RAISE EXCEPTION 'The schema given with -v schema does not exist in this database.';
    END IF;
    IF current_database() = 'marketpulse_synthetic' AND current_schema() = 'public' THEN
        RAISE EXCEPTION 'Refusing to load into the public synthetic dataset. Use a separate schema, such as -v schema=parser_test.';
    END IF;
END $$;

-- Forward slashes, no spaces, no quotes (see sql/03_load_whatsapp_orders.sql).
\cd :input_folder

BEGIN;

CREATE TEMP TABLE staging_orders (
    order_id text, order_datetime text, sales_channel text, payment_type text, customer_name text,
    phone text, address text, pin_code text, district_city text, state text, order_amount text,
    amount_basis text, financial_status text, fulfillment_status text, cancelled_at text,
    review_flags text, notes text
) ON COMMIT DROP;

CREATE TEMP TABLE staging_items (
    order_id text, product_code text, raw_name text, quantity text, line_amount text, product_defaulted text
) ON COMMIT DROP;

\copy staging_orders FROM 'shopify_orders.csv' WITH (FORMAT csv, HEADER true)
\copy staging_items FROM 'shopify_order_items.csv' WITH (FORMAT csv, HEADER true)

-- Orders that cannot be stored, with the reason.
CREATE TEMP TABLE skipped_orders ON COMMIT DROP AS
SELECT
    i.order_id,
    string_agg(DISTINCT
        CASE
            WHEN i.quantity IS NULL THEN 'unreadable_quantity'
            WHEN i.product_code IS NULL THEN 'unknown_product'
            WHEN NOT EXISTS (SELECT 1 FROM products p WHERE p.product_code = i.product_code)
                THEN 'product_not_in_products_table'
            ELSE 'bad_quantity'
        END, ';') AS reason
FROM staging_items i
WHERE i.quantity IS NULL
   OR i.product_code IS NULL
   OR NOT EXISTS (SELECT 1 FROM products p WHERE p.product_code = i.product_code)
   OR i.quantity::integer < 1
GROUP BY i.order_id;

CREATE TEMP TABLE orders_to_load ON COMMIT DROP AS
SELECT s.* FROM staging_orders s
WHERE NOT EXISTS (SELECT 1 FROM skipped_orders k WHERE k.order_id = s.order_id);

-- For the summary: which orders and phones are already known.
CREATE TEMP TABLE known_orders ON COMMIT DROP AS
SELECT t.order_id FROM orders_to_load t JOIN orders o ON o.order_id = t.order_id;

CREATE TEMP TABLE known_phones ON COMMIT DROP AS
SELECT DISTINCT t.phone FROM orders_to_load t JOIN customers c ON c.phone = t.phone;

-- Customers with a phone: a new customer for every phone not seen before.
INSERT INTO customers (customer_id, customer_name, phone)
SELECT 'C-' || left(replace(gen_random_uuid()::text, '-', ''), 8), first_order.customer_name, first_order.phone
FROM (
    SELECT DISTINCT ON (phone) phone, customer_name
    FROM orders_to_load
    WHERE phone IS NOT NULL
    ORDER BY phone, order_datetime
) AS first_order
WHERE NOT EXISTS (SELECT 1 FROM customers c WHERE c.phone = first_order.phone);

-- Orders without a phone: keep the customer the order already has,
-- otherwise make a new one.
CREATE TEMP TABLE no_phone_customers ON COMMIT DROP AS
SELECT t.order_id,
       COALESCE(o.customer_id, 'C-' || left(replace(gen_random_uuid()::text, '-', ''), 8)) AS customer_id,
       t.customer_name,
       o.customer_id IS NULL AS is_new
FROM orders_to_load t
LEFT JOIN orders o ON o.order_id = t.order_id
WHERE t.phone IS NULL;

INSERT INTO customers (customer_id, customer_name, phone)
SELECT customer_id, customer_name, NULL FROM no_phone_customers WHERE is_new;

-- Orders: add new ones, update known ones.
INSERT INTO orders (
    order_id, customer_id, order_datetime, sales_channel, payment_type, address, district_city,
    state, pin_code, order_amount, amount_basis, financial_status, fulfillment_status,
    cancelled_at, review_flags, notes
)
SELECT
    t.order_id, COALESCE(c.customer_id, n.customer_id), t.order_datetime::timestamp, t.sales_channel,
    t.payment_type, t.address, t.district_city, t.state, t.pin_code, t.order_amount::numeric,
    t.amount_basis, t.financial_status, t.fulfillment_status, t.cancelled_at::timestamp,
    t.review_flags, t.notes
FROM orders_to_load t
LEFT JOIN customers c ON c.phone = t.phone
LEFT JOIN no_phone_customers n ON n.order_id = t.order_id
ON CONFLICT (order_id) DO UPDATE SET
    customer_id        = EXCLUDED.customer_id,
    order_datetime     = EXCLUDED.order_datetime,
    sales_channel      = EXCLUDED.sales_channel,
    payment_type       = EXCLUDED.payment_type,
    address            = EXCLUDED.address,
    district_city      = EXCLUDED.district_city,
    state              = EXCLUDED.state,
    pin_code           = EXCLUDED.pin_code,
    order_amount       = EXCLUDED.order_amount,
    amount_basis       = EXCLUDED.amount_basis,
    financial_status   = EXCLUDED.financial_status,
    fulfillment_status = EXCLUDED.fulfillment_status,
    cancelled_at       = EXCLUDED.cancelled_at,
    review_flags       = EXCLUDED.review_flags,
    notes              = EXCLUDED.notes;

-- Product lines: replace those of every order in this file.
DELETE FROM order_items WHERE order_id IN (SELECT order_id FROM orders_to_load);

INSERT INTO order_items (order_id, product_code, quantity, line_amount, product_defaulted)
SELECT i.order_id, i.product_code, i.quantity::integer, i.line_amount::numeric, i.product_defaulted::boolean
FROM staging_items i
WHERE EXISTS (SELECT 1 FROM orders_to_load t WHERE t.order_id = i.order_id);

-- A customer can be left without orders if an order's phone changed.
DELETE FROM customers c
WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.customer_id);

\echo
\echo 'Load summary'
SELECT
    (SELECT count(*) FROM staging_orders)                                AS orders_in_file,
    (SELECT count(*) FROM orders_to_load)                                AS orders_loaded,
    (SELECT count(*) FROM known_orders)                                  AS of_which_updated,
    (SELECT count(*) FROM skipped_orders)                                AS orders_skipped,
    (SELECT count(*) FROM orders_to_load WHERE review_flags IS NOT NULL) AS loaded_with_flags,
    (SELECT count(DISTINCT phone) FROM orders_to_load)                   AS customers_with_phone,
    (SELECT count(*) FROM known_phones)                                  AS of_which_already_known;

\echo 'Skipped orders (fix these, then run both scripts again)'
SELECT order_id, reason FROM skipped_orders ORDER BY order_id;

COMMIT;
