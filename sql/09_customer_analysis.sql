-- =====================================================================
-- MarketPulse Analytics: customer analysis (Phase 5)
-- =====================================================================
-- Answers the Customer Analytics questions (C1-C5) in docs/business_questions.md,
-- reading only the "clean" schema (docs/data_cleaning.md).
--
-- C1, C2, C4 and C5 are also answered in python/eda.py: the same
-- question, the same database, two independent tools. C3 is new here
-- (Phase 4's Python analysis did not cover it).
--
-- An order flagged missing_phone or invalid_phone has no known
-- customer (customer_identified = false). Such orders count as orders
-- elsewhere, but never in these customer-level questions.
--
-- How to run (from the project folder):
--   psql -U marketpulse_user -d marketpulse_synthetic -h localhost -f sql/09_customer_analysis.sql
--   psql -U marketpulse_user -d marketpulse_private -h localhost -f sql/09_customer_analysis.sql
--
-- Every statement here is a read-only SELECT. Nothing is ever written.
-- =====================================================================

\set ON_ERROR_STOP on

-- ---------------------------------------------------------------------
-- C1: What share of customers have ordered more than once?
-- ---------------------------------------------------------------------
-- Shown twice: with every counted order, and with possible_duplicate
-- orders left out. A real duplicate looks like a second order, so the
-- second row is the cautious one.
\echo '--- C1: repeat customers, with and without possible duplicates ---'
WITH all_orders AS (
    SELECT customer_id, count(*) AS orders
    FROM clean.orders
    WHERE include_in_analysis AND customer_identified
    GROUP BY customer_id
), without_duplicates AS (
    SELECT customer_id, count(*) AS orders
    FROM clean.orders
    WHERE include_in_analysis AND customer_identified
      AND coalesce(review_flags, '') NOT LIKE '%possible_duplicate%'
    GROUP BY customer_id
)
SELECT 'all counted orders' AS version,
       count(*) AS customers,
       count(*) FILTER (WHERE orders > 1) AS repeat_customers,
       round(count(*) FILTER (WHERE orders > 1)::numeric / count(*), 4) AS repeat_share
FROM all_orders
UNION ALL
SELECT 'without possible duplicates',
       count(*),
       count(*) FILTER (WHERE orders > 1),
       round(count(*) FILTER (WHERE orders > 1)::numeric / count(*), 4)
FROM without_duplicates;

-- ---------------------------------------------------------------------
-- C2: How many days pass between a customer's first and second order?
-- ---------------------------------------------------------------------
-- A self-join on customer_order_number: order 1 against order 2 of the
-- same customer. Subtracting two dates in PostgreSQL gives whole days.
\echo '--- C2: days from a customer first order to their second ---'
WITH first_order AS (
    SELECT customer_id, order_date FROM clean.orders
    WHERE include_in_analysis AND customer_identified AND customer_order_number = 1
), second_order AS (
    SELECT customer_id, order_date FROM clean.orders
    WHERE include_in_analysis AND customer_identified AND customer_order_number = 2
), gaps AS (
    SELECT s.order_date - f.order_date AS days
    FROM second_order s
    JOIN first_order f USING (customer_id)
)
SELECT count(*) AS customers_with_a_second_order,
       round(avg(days), 2) AS average_days,
       percentile_cont(0.5)  WITHIN GROUP (ORDER BY days) AS median_days,
       percentile_cont(0.25) WITHIN GROUP (ORDER BY days) AS p25,
       percentile_cont(0.75) WITHIN GROUP (ORDER BY days) AS p75,
       percentile_cont(0.9)  WITHIN GROUP (ORDER BY days) AS p90
FROM gaps;

-- ---------------------------------------------------------------------
-- C3 (new): What do repeat customers buy on their second order?
-- ---------------------------------------------------------------------
\echo '--- C3: products on a customer second order ---'
WITH second_order_items AS (
    SELECT i.product_code, i.quantity
    FROM clean.order_items i
    JOIN clean.orders o USING (order_id)
    WHERE o.include_in_analysis AND o.customer_identified AND o.customer_order_number = 2
      AND i.include_in_analysis
)
SELECT p.product_code, p.product_name,
       sum(i.quantity) AS units,
       round(sum(i.quantity)::numeric / sum(sum(i.quantity)) OVER (), 4) AS share_of_units
FROM second_order_items i
JOIN clean.products p USING (product_code)
GROUP BY p.product_code, p.product_name
ORDER BY units DESC;

-- ---------------------------------------------------------------------
-- C4: How many new customers are gained each month, compared with
--     returning ones?
-- ---------------------------------------------------------------------
-- Early months of any dataset always show few returning orders, simply
-- because there has been less time for a second order. This is not
-- falling (or later, rising) loyalty on its own.
\echo '--- C4: new vs returning customers per month ---'
WITH months AS (
    SELECT generate_series(date_trunc('month', min(order_month)),
                           date_trunc('month', max(order_month)), interval '1 month')::date AS order_month
    FROM clean.orders WHERE include_in_analysis
), monthly AS (
    SELECT order_month,
           count(*) FILTER (WHERE customer_identified AND customer_order_number = 1) AS new_customer_orders,
           count(*) FILTER (WHERE customer_identified AND customer_order_number > 1) AS returning_customer_orders,
           count(*) FILTER (WHERE NOT customer_identified) AS unknown_customer_orders
    FROM clean.orders WHERE include_in_analysis
    GROUP BY order_month
)
SELECT m.order_month,
       coalesce(x.new_customer_orders, 0)       AS new_customer_orders,
       coalesce(x.returning_customer_orders, 0) AS returning_customer_orders,
       coalesce(x.unknown_customer_orders, 0)   AS unknown_customer_orders
FROM months m
LEFT JOIN monthly x USING (order_month)
ORDER BY m.order_month;

-- ---------------------------------------------------------------------
-- C5: Which districts have the most repeat customers?
-- ---------------------------------------------------------------------
-- A customer belongs to the district of their first counted order.
-- Districts with fewer than 20 customers are left out: a share of a
-- handful of customers is mostly chance.
\echo '--- C5: repeat-customer share by district (at least 20 customers) ---'
WITH first_order_place AS (
    SELECT customer_id, district_city, state
    FROM clean.orders
    WHERE include_in_analysis AND customer_identified AND customer_order_number = 1
), orders_per_customer AS (
    SELECT customer_id, count(*) AS orders
    FROM clean.orders
    WHERE include_in_analysis AND customer_identified
    GROUP BY customer_id
)
SELECT f.district_city, f.state,
       count(*) AS customers,
       count(*) FILTER (WHERE o.orders > 1) AS repeat_customers,
       round(count(*) FILTER (WHERE o.orders > 1)::numeric / count(*), 4) AS repeat_share
FROM first_order_place f
JOIN orders_per_customer o USING (customer_id)
WHERE f.district_city IS NOT NULL
GROUP BY f.district_city, f.state
HAVING count(*) >= 20
ORDER BY repeat_share DESC, customers DESC, f.district_city;
