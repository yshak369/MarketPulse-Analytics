-- =====================================================================
-- MarketPulse Analytics: load WhatsApp parser output into the database
-- =====================================================================
-- Reads the files written by python/parse_whatsapp_orders.py:
--   whatsapp_orders.csv and whatsapp_order_items.csv
-- and loads them into customers, orders and order_items.
--
-- How to run (from the project folder):
--   psql -U marketpulse_user -d <database> -h localhost
--        -v schema=<schema> -v input_folder=<folder with the parser output>
--        -f sql/03_load_whatsapp_orders.sql
--   The folder must use forward slashes and contain no spaces.
--
-- Test run on the fake chats (see sql/test_setup_parser_schema.sql):
--   psql -U marketpulse_user -d marketpulse_synthetic -h localhost -v schema=parser_test -v input_folder=data/processed/whatsapp_test_output -f sql/03_load_whatsapp_orders.sql
--
-- Rules:
--   * One phone number = one customer. An order is linked to the
--     customer who already has that phone, or a new customer is made.
--   * An order without a phone gets its own new customer. Orders
--     without phones are never merged, because we cannot tell who
--     placed them.
--   * Flagged orders ARE loaded, with their review_flags, so analysis
--     can include or exclude them. Nothing is hidden.
--   * An order that the tables cannot hold (unknown product, unreadable
--     product, quantity below 1, product missing from the products
--     table) is skipped as a whole, and listed at the end.
--   * Safe to run again: WhatsApp orders loaded by an earlier run
--     (IDs starting with "W-") are removed first. Shopify orders and
--     other orders are not touched. If shipments already point to those
--     orders, the script stops instead of deleting the shipments.
--   * All or nothing: everything runs inside one transaction.
--
-- Safety: the script refuses to load into the public schema of
-- marketpulse_synthetic, so test orders never mix with the public
-- synthetic dataset.
-- =====================================================================

\set ON_ERROR_STOP on
\encoding UTF8

-- Both settings are required. A missing one stops the script below.
\if :{?schema}
\else
  \echo 'Missing setting: add -v schema=<schema name> to the command.'
  \set schema __missing__
\endif
\if :{?input_folder}
\else
  \echo 'Missing setting: add -v input_folder=<folder with the parser output> to the command.'
  \set input_folder __missing__
\endif

SET search_path TO :"schema";

DO $$
BEGIN
    IF current_schema() IS NULL THEN
        RAISE EXCEPTION 'The schema given with -v schema does not exist in this database.';
    END IF;
    IF current_database() = 'marketpulse_synthetic' AND current_schema() = 'public' THEN
        RAISE EXCEPTION 'Refusing to load parser output into the public synthetic dataset. Use a separate schema, such as -v schema=parser_test.';
    END IF;
END $$;

-- Relative file names below are read from the input folder.
-- Write the folder with forward slashes and no spaces, for example
-- D:/Private/MarketPulse-Data/parser_output. In psql commands a
-- backslash starts a new command, and quotes would be kept as part
-- of the folder name.
\cd :input_folder

BEGIN;

-- ---------------------------------------------------------------------
-- 1. Read the two files into temporary tables, all columns as text.
--    ON COMMIT DROP removes them when the transaction ends.
-- ---------------------------------------------------------------------
CREATE TEMP TABLE staging_orders (
    order_id text, order_datetime text, sales_channel text, source_group text,
    payment_type text, customer_name text, phone text, address text, pin_code text,
    district_city text, state text, order_amount text, amount_basis text,
    review_flags text, notes text, source_line text
) ON COMMIT DROP;

CREATE TEMP TABLE staging_items (
    order_id text, product_code text, raw_name text, quantity text,
    cod_collectible_amount text, product_defaulted text
) ON COMMIT DROP;

\copy staging_orders FROM 'whatsapp_orders.csv' WITH (FORMAT csv, HEADER true)
\copy staging_items FROM 'whatsapp_order_items.csv' WITH (FORMAT csv, HEADER true)

-- ---------------------------------------------------------------------
-- 2. Find orders that cannot be stored, with the reason.
-- ---------------------------------------------------------------------
CREATE TEMP TABLE skipped_orders ON COMMIT DROP AS
SELECT
    i.order_id,
    string_agg(DISTINCT
        CASE
            WHEN i.quantity IS NULL THEN 'unreadable_product'
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
SELECT s.*
FROM staging_orders s
WHERE NOT EXISTS (SELECT 1 FROM skipped_orders k WHERE k.order_id = s.order_id);

-- ---------------------------------------------------------------------
-- 3. Remove the WhatsApp orders loaded by an earlier run, then any
--    customer left without orders.
-- ---------------------------------------------------------------------
DELETE FROM order_items
WHERE order_id IN (SELECT order_id FROM orders WHERE sales_channel = 'whatsapp' AND order_id LIKE 'W-%');

DELETE FROM orders
WHERE sales_channel = 'whatsapp' AND order_id LIKE 'W-%';

DELETE FROM customers c
WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.customer_id);

-- ---------------------------------------------------------------------
-- 4. Customers.
-- ---------------------------------------------------------------------
-- Note which phones already belong to a customer, for the summary.
CREATE TEMP TABLE known_phones ON COMMIT DROP AS
SELECT DISTINCT t.phone
FROM orders_to_load t
JOIN customers c ON c.phone = t.phone;

-- A new customer for every phone not seen before. The name comes from
-- that phone's earliest order. IDs are random, never made from the phone.
INSERT INTO customers (customer_id, customer_name, phone)
SELECT 'C-' || left(replace(gen_random_uuid()::text, '-', ''), 8), first_order.customer_name, first_order.phone
FROM (
    SELECT DISTINCT ON (phone) phone, customer_name
    FROM orders_to_load
    WHERE phone IS NOT NULL
    ORDER BY phone, order_datetime
) AS first_order
WHERE NOT EXISTS (SELECT 1 FROM customers c WHERE c.phone = first_order.phone);

-- An order without a phone gets its own customer.
CREATE TEMP TABLE no_phone_customers ON COMMIT DROP AS
SELECT order_id, 'C-' || left(replace(gen_random_uuid()::text, '-', ''), 8) AS customer_id, customer_name
FROM orders_to_load
WHERE phone IS NULL;

INSERT INTO customers (customer_id, customer_name, phone)
SELECT customer_id, customer_name, NULL
FROM no_phone_customers;

-- ---------------------------------------------------------------------
-- 5. Orders and order items.
-- ---------------------------------------------------------------------
INSERT INTO orders (
    order_id, customer_id, order_datetime, sales_channel, payment_type,
    address, district_city, state, pin_code, order_amount, amount_basis,
    review_flags, notes
)
SELECT
    t.order_id,
    COALESCE(c.customer_id, n.customer_id),
    t.order_datetime::timestamp,
    t.sales_channel,
    t.payment_type,
    t.address,
    t.district_city,
    t.state,
    t.pin_code,
    t.order_amount::numeric,
    t.amount_basis,
    t.review_flags,
    t.notes
FROM orders_to_load t
LEFT JOIN customers c ON c.phone = t.phone
LEFT JOIN no_phone_customers n ON n.order_id = t.order_id;

INSERT INTO order_items (order_id, product_code, quantity, line_amount, product_defaulted)
SELECT i.order_id, i.product_code, i.quantity::integer, i.cod_collectible_amount::numeric, i.product_defaulted::boolean
FROM staging_items i
WHERE EXISTS (SELECT 1 FROM orders_to_load t WHERE t.order_id = i.order_id);

-- ---------------------------------------------------------------------
-- 6. Summary. Counts and order IDs only, never customer details.
-- ---------------------------------------------------------------------
\echo
\echo 'Load summary'
SELECT
    (SELECT count(*) FROM staging_orders)                                AS orders_in_file,
    (SELECT count(*) FROM orders_to_load)                                AS orders_loaded,
    (SELECT count(*) FROM skipped_orders)                                AS orders_skipped,
    (SELECT count(*) FROM orders_to_load WHERE review_flags IS NOT NULL) AS loaded_with_flags,
    (SELECT count(DISTINCT phone) FROM orders_to_load)                   AS customers_with_phone,
    (SELECT count(*) FROM known_phones)                                  AS of_which_already_known,
    (SELECT count(*) FROM no_phone_customers)                            AS customers_without_phone,
    (SELECT count(*) FROM staging_items i
      WHERE EXISTS (SELECT 1 FROM orders_to_load t WHERE t.order_id = i.order_id)) AS items_loaded;

\echo 'Skipped orders (fix these in review, then run the parser and this script again)'
SELECT order_id, reason FROM skipped_orders ORDER BY order_id;

COMMIT;
