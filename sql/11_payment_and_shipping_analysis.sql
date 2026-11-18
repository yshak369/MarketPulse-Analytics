-- =====================================================================
-- MarketPulse Analytics: payment and shipping analysis (Phase 5)
-- =====================================================================
-- Answers the Payment and Shipping Analytics questions (D1-D6) in
-- docs/business_questions.md, reading only the "clean" schema
-- (docs/data_cleaning.md).
--
-- The same questions are also answered in python/eda.py: the same
-- question, the same database, two independent tools.
--
-- A COD amount is the amount to COLLECT. It is never confirmed
-- revenue: a COD parcel can be returned and never paid for.
--
-- D5 and D6 need courier records in the shipments table. They return
-- 0 rows, never an error, where none exist yet.
--
-- How to run (from the project folder):
--   psql -U marketpulse_user -d marketpulse_synthetic -h localhost -f sql/11_payment_and_shipping_analysis.sql
--   psql -U marketpulse_user -d marketpulse_private -h localhost -f sql/11_payment_and_shipping_analysis.sql
--
-- Every statement here is a read-only SELECT. Nothing is ever written.
-- =====================================================================

\set ON_ERROR_STOP on

-- ---------------------------------------------------------------------
-- D1: What is the split between COD and prepaid orders, and how does
--     it change over time?
-- ---------------------------------------------------------------------
-- cod_share is COD as a share of COD + Prepaid. needs_review orders are
-- counted, but left out of the share: the payment type is not guessed.
\echo '--- D1: COD vs Prepaid per month ---'
WITH months AS (
    SELECT generate_series(date_trunc('month', min(order_month)),
                           date_trunc('month', max(order_month)), interval '1 month')::date AS order_month
    FROM clean.orders WHERE include_in_analysis
), monthly AS (
    SELECT order_month,
           count(*) FILTER (WHERE payment_type = 'cod')          AS cod,
           count(*) FILTER (WHERE payment_type = 'prepaid')      AS prepaid,
           count(*) FILTER (WHERE payment_type = 'needs_review') AS needs_review
    FROM clean.orders WHERE include_in_analysis
    GROUP BY order_month
)
SELECT m.order_month,
       coalesce(x.cod, 0) AS cod,
       coalesce(x.prepaid, 0) AS prepaid,
       coalesce(x.needs_review, 0) AS needs_review,
       round(coalesce(x.cod, 0)::numeric
             / NULLIF(coalesce(x.cod, 0) + coalesce(x.prepaid, 0), 0), 4) AS cod_share
FROM months m
LEFT JOIN monthly x USING (order_month)
ORDER BY m.order_month;

-- ---------------------------------------------------------------------
-- D2: Which states and districts lean most towards COD?
-- ---------------------------------------------------------------------
-- States with fewer than 30 orders are left out: too few orders to compare.
\echo '--- D2: COD share by state (states with at least 30 orders) ---'
SELECT coalesce(state, '(unknown)') AS state,
       count(*) AS orders,
       count(*) FILTER (WHERE payment_type = 'cod')          AS cod,
       count(*) FILTER (WHERE payment_type = 'prepaid')      AS prepaid,
       count(*) FILTER (WHERE payment_type = 'needs_review') AS needs_review,
       round(count(*) FILTER (WHERE payment_type = 'cod')::numeric
             / NULLIF(count(*) FILTER (WHERE payment_type IN ('cod', 'prepaid')), 0), 4) AS cod_share
FROM clean.orders
WHERE include_in_analysis
GROUP BY coalesce(state, '(unknown)')
HAVING count(*) >= 30
ORDER BY cod_share DESC, orders DESC, state;

-- ---------------------------------------------------------------------
-- D3: Do COD orders contain different products or quantities from
--     prepaid orders?
-- ---------------------------------------------------------------------
\echo '--- D3: basket size, COD vs Prepaid ---'
SELECT payment_type, count(*) AS orders,
       round(avg(product_lines), 2) AS average_product_lines,
       round(avg(units), 2) AS average_units,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY units) AS median_units
FROM clean.orders
WHERE include_in_analysis AND payment_type IN ('cod', 'prepaid')
GROUP BY payment_type
ORDER BY payment_type;

-- Each product's share of units, worked out separately within COD
-- orders and within Prepaid orders, so the two columns compare
-- product MIX, not raw counts (COD has more orders overall).
\echo '--- D3: product mix, COD vs Prepaid (share of units) ---'
WITH lines AS (
    SELECT i.product_code, o.payment_type, i.quantity
    FROM clean.order_items i
    JOIN clean.orders o USING (order_id)
    WHERE i.include_in_analysis AND o.payment_type IN ('cod', 'prepaid')
)
SELECT product_code,
       round(sum(quantity) FILTER (WHERE payment_type = 'cod')::numeric
             / sum(sum(quantity) FILTER (WHERE payment_type = 'cod')) OVER (), 4) AS cod,
       round(sum(quantity) FILTER (WHERE payment_type = 'prepaid')::numeric
             / sum(sum(quantity) FILTER (WHERE payment_type = 'prepaid')) OVER (), 4) AS prepaid
FROM lines
GROUP BY product_code
ORDER BY cod DESC NULLS LAST;

-- ---------------------------------------------------------------------
-- D4: What is the total COD amount to be collected per week?
-- ---------------------------------------------------------------------
-- Not revenue. Kept apart by where the amount comes from, same as S8.
\echo '--- D4: COD amount to collect per week ---'
WITH weeks AS (
    SELECT generate_series(min(week_start), max(week_start), interval '7 days')::date AS week_start
    FROM clean.orders WHERE include_in_analysis AND payment_type = 'cod'
), weekly AS (
    SELECT week_start,
           count(*) AS cod_orders,
           sum(order_value) FILTER (WHERE value_basis = 'recorded')  AS amount_to_collect,
           sum(order_value) FILTER (WHERE value_basis = 'estimated') AS estimated_to_collect,
           count(*) FILTER (WHERE value_basis = 'unknown') AS orders_without_value
    FROM clean.orders
    WHERE include_in_analysis AND payment_type = 'cod'
    GROUP BY week_start
)
SELECT w.week_start,
       coalesce(x.cod_orders, 0) AS cod_orders,
       coalesce(x.amount_to_collect, 0)    AS amount_to_collect,
       coalesce(x.estimated_to_collect, 0) AS estimated_to_collect,
       coalesce(x.orders_without_value, 0) AS orders_without_value
FROM weeks w
LEFT JOIN weekly x USING (week_start)
ORDER BY w.week_start;

-- ---------------------------------------------------------------------
-- D5: What share of COD orders is delivered, and what share is returned?
-- ---------------------------------------------------------------------
-- A shipment of a cancelled order is already excluded from the clean
-- table (python/clean_data.py), so include_in_analysis is enough here.
\echo '--- D5: delivery outcomes by courier and payment type ---'
SELECT s.courier, o.payment_type,
       count(*) AS shipments,
       count(*) FILTER (WHERE s.delivery_status = 'delivered') AS delivered,
       count(*) FILTER (WHERE s.delivery_status = 'returned')  AS returned,
       count(*) FILTER (WHERE s.delivery_status NOT IN ('delivered', 'returned')
                          OR s.delivery_status IS NULL) AS unknown,
       round(count(*) FILTER (WHERE s.delivery_status = 'delivered')::numeric / count(*), 4) AS delivered_share,
       round(count(*) FILTER (WHERE s.delivery_status = 'returned')::numeric  / count(*), 4) AS returned_share
FROM clean.shipments s
JOIN clean.orders o USING (order_id)
WHERE s.include_in_analysis
GROUP BY s.courier, o.payment_type
ORDER BY s.courier, o.payment_type;

-- ---------------------------------------------------------------------
-- D6: How long does delivery take by courier and by state?
-- ---------------------------------------------------------------------
\echo '--- D6: delivery days by courier ---'
SELECT courier,
       count(*) AS deliveries,
       round(avg(delivery_days), 2) AS average_days,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY delivery_days) AS median_days,
       percentile_cont(0.9) WITHIN GROUP (ORDER BY delivery_days) AS p90_days
FROM clean.shipments
WHERE include_in_analysis AND delivery_days IS NOT NULL
GROUP BY courier
ORDER BY courier;
