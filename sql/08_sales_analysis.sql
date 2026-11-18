-- =====================================================================
-- MarketPulse Analytics: sales analysis (Phase 5)
-- =====================================================================
-- Answers the Sales Analytics questions (S1-S8) in docs/business_questions.md,
-- reading only the "clean" schema (docs/data_cleaning.md).
--
-- These same questions are answered in Python in python/eda.py. Running
-- both against the same database and getting the same numbers is a
-- deliberate cross-check between two independent tools.
--
-- How to run (from the project folder):
--   psql -U marketpulse_user -d marketpulse_synthetic -h localhost -f sql/08_sales_analysis.sql
--   psql -U marketpulse_user -d marketpulse_private -h localhost -f sql/08_sales_analysis.sql
--
-- Every statement here is a read-only SELECT. Nothing is ever written.
-- Run on the private database, the result rows are real business figures
-- (no personal details: the clean schema holds none) and stay on the
-- owner's own screen, never pasted elsewhere. See docs/data_privacy.md.
-- =====================================================================

\set ON_ERROR_STOP on

-- ---------------------------------------------------------------------
-- S1: How many orders come in per day, week and month, and is the
--     trend rising or falling?
-- ---------------------------------------------------------------------
\echo '--- S1: orders per month ---'
SELECT order_month, count(*) AS orders
FROM clean.orders
WHERE include_in_analysis
GROUP BY order_month
ORDER BY order_month;

-- A full week-by-week spine (generate_series), so a quiet week with no
-- orders shows as 0, never a gap. The trend is a 4-week rolling average,
-- the SQL equivalent of pandas' .rolling(4).mean().
\echo '--- S1: orders per week, with a 4-week rolling trend ---'
WITH weeks AS (
    SELECT generate_series(min(week_start), max(week_start), interval '7 days')::date AS week_start
    FROM clean.orders WHERE include_in_analysis
), weekly AS (
    SELECT week_start, count(*) AS orders
    FROM clean.orders WHERE include_in_analysis
    GROUP BY week_start
)
SELECT w.week_start, coalesce(wk.orders, 0) AS orders,
       round(avg(coalesce(wk.orders, 0)) OVER (
           ORDER BY w.week_start ROWS BETWEEN 3 PRECEDING AND CURRENT ROW), 2) AS trend_4_week
FROM weeks w
LEFT JOIN weekly wk USING (week_start)
ORDER BY w.week_start;

-- ---------------------------------------------------------------------
-- S2: Which products sell the most units?
-- ---------------------------------------------------------------------
-- "defaulted" units come from orders with no product line (the owner's
-- rule: 1 cream). Shown apart from what was actually written.
\echo '--- S2: units sold per product, written vs defaulted ---'
SELECT i.product_code, p.product_name,
       coalesce(sum(i.quantity) FILTER (WHERE NOT i.product_defaulted), 0) AS units_written,
       coalesce(sum(i.quantity) FILTER (WHERE i.product_defaulted), 0)     AS units_defaulted,
       sum(i.quantity) AS units_total,
       round(sum(i.quantity)::numeric / sum(sum(i.quantity)) OVER (), 4) AS share_of_units
FROM clean.order_items i
JOIN clean.products p USING (product_code)
WHERE i.include_in_analysis
GROUP BY i.product_code, p.product_name
ORDER BY units_total DESC;

-- ---------------------------------------------------------------------
-- S3: Which products are most often bought together in one order?
-- ---------------------------------------------------------------------
-- A self-join on order_items, keeping only b.product_code > a.product_code
-- so each pair in an order is counted once (never a product with itself).
\echo '--- S3: products most often bought together, top 10 pairs ---'
SELECT a.product_code AS product_a, b.product_code AS product_b,
       count(DISTINCT a.order_id) AS orders
FROM clean.order_items a
JOIN clean.order_items b ON b.order_id = a.order_id AND b.product_code > a.product_code
WHERE a.include_in_analysis
GROUP BY a.product_code, b.product_code
ORDER BY orders DESC, product_a, product_b
LIMIT 10;

-- ---------------------------------------------------------------------
-- S4: What share of orders comes from WhatsApp and what share from Shopify?
-- ---------------------------------------------------------------------
\echo '--- S4: orders by channel ---'
SELECT sales_channel, count(*) AS orders,
       round(count(*)::numeric / sum(count(*)) OVER (), 4) AS share
FROM clean.orders
WHERE include_in_analysis
GROUP BY sales_channel
ORDER BY orders DESC, sales_channel;

-- ---------------------------------------------------------------------
-- S5: Which days of the week and hours of the day bring the most orders?
-- ---------------------------------------------------------------------
-- Long format (one row per weekday/hour), the natural shape for SQL; a
-- dashboard or spreadsheet pivots this into a grid. array_position puts
-- the weekdays in calendar order, not alphabetical order.
\echo '--- S5: orders by weekday and hour ---'
SELECT weekday, hour, count(*) AS orders
FROM clean.orders
WHERE include_in_analysis
GROUP BY weekday, hour
ORDER BY array_position(ARRAY['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'], weekday), hour;

-- ---------------------------------------------------------------------
-- S6: Which states and districts place the most orders?
-- ---------------------------------------------------------------------
\echo '--- S6: orders by state ---'
SELECT state, count(*) AS orders,
       round(count(*)::numeric / sum(count(*)) OVER (), 4) AS share
FROM clean.orders
WHERE include_in_analysis
GROUP BY state
ORDER BY orders DESC, state;

-- Top 10 known districts, plus ONE combined row for every order with no
-- known district (never guessed at, never split across several rows).
\echo '--- S6: top 10 districts, orders with no known district shown separately ---'
WITH counted AS (
    SELECT district_city, state FROM clean.orders WHERE include_in_analysis
), known AS (
    SELECT district_city, state, count(*) AS orders
    FROM counted WHERE district_city IS NOT NULL
    GROUP BY district_city, state
    ORDER BY orders DESC
    LIMIT 10
), unknown AS (
    SELECT '(unknown)' AS district_city, '(all states)' AS state, count(*) AS orders
    FROM counted WHERE district_city IS NULL
)
SELECT * FROM known
UNION ALL
SELECT * FROM unknown WHERE orders > 0
ORDER BY orders DESC, district_city;

-- ---------------------------------------------------------------------
-- S7: What is the average number of items per order?
-- ---------------------------------------------------------------------
-- percentile_cont is PostgreSQL's built-in equivalent of np.percentile.
\echo '--- S7: product lines and units per order ---'
SELECT 'product_lines' AS measure, count(*) AS orders, round(avg(product_lines), 2) AS average,
       percentile_cont(0.5)  WITHIN GROUP (ORDER BY product_lines) AS median,
       percentile_cont(0.25) WITHIN GROUP (ORDER BY product_lines) AS p25,
       percentile_cont(0.75) WITHIN GROUP (ORDER BY product_lines) AS p75,
       percentile_cont(0.9)  WITHIN GROUP (ORDER BY product_lines) AS p90,
       max(product_lines) AS max_value
FROM clean.orders WHERE include_in_analysis
UNION ALL
SELECT 'units', count(*), round(avg(units), 2),
       percentile_cont(0.5)  WITHIN GROUP (ORDER BY units),
       percentile_cont(0.25) WITHIN GROUP (ORDER BY units),
       percentile_cont(0.75) WITHIN GROUP (ORDER BY units),
       percentile_cont(0.9)  WITHIN GROUP (ORDER BY units),
       max(units)
FROM clean.orders WHERE include_in_analysis;

-- ---------------------------------------------------------------------
-- S8: What is the estimated order value by month?  (labelled: Estimate)
-- ---------------------------------------------------------------------
-- recorded and estimated are always kept apart. A COD amount is the
-- amount to COLLECT, not confirmed revenue (docs/data_cleaning.md).
\echo '--- S8: order value per month, recorded vs estimated ---'
WITH months AS (
    SELECT generate_series(date_trunc('month', min(order_month)),
                           date_trunc('month', max(order_month)), interval '1 month')::date AS order_month
    FROM clean.orders WHERE include_in_analysis
), monthly AS (
    SELECT order_month,
           sum(order_value) FILTER (WHERE value_basis = 'recorded')  AS recorded_value,
           sum(order_value) FILTER (WHERE value_basis = 'estimated') AS estimated_value,
           count(*) FILTER (WHERE value_basis = 'recorded')  AS orders_recorded,
           count(*) FILTER (WHERE value_basis = 'estimated') AS orders_estimated,
           count(*) FILTER (WHERE value_basis = 'unknown')   AS orders_unknown
    FROM clean.orders WHERE include_in_analysis
    GROUP BY order_month
)
SELECT m.order_month,
       coalesce(x.recorded_value, 0)  AS recorded_value,
       coalesce(x.estimated_value, 0) AS estimated_value,
       coalesce(x.orders_recorded, 0)  AS orders_recorded,
       coalesce(x.orders_estimated, 0) AS orders_estimated,
       coalesce(x.orders_unknown, 0)   AS orders_unknown
FROM months m
LEFT JOIN monthly x USING (order_month)
ORDER BY m.order_month;
