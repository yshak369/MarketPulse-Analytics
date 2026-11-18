-- =====================================================================
-- MarketPulse Analytics: profitability analysis (Phase 5)
-- =====================================================================
-- Answers the Profitability Analytics questions (P1-P3) in
-- docs/business_questions.md, reading only the "clean" schema
-- (docs/data_cleaning.md). This module was never built in Phase 4:
-- these three queries are new.
--
-- P4 ("How much do returned COD orders cost the business?") and P5
-- ("confirmed profit after shipping and returns") stay "Needs data":
-- no return-cost or confirmed-payment records exist anywhere in this
-- schema, so there is nothing to query for them yet.
--
-- P1 uses the price list only. P2 and P3 are ESTIMATES: they use the
-- price-list estimate on every line (clean.order_items.estimated_line_value
-- / estimated_line_cost), never a guess about what was actually paid.
-- A line whose order has only a partial COD amount, or an unclear
-- payment type, has no estimate at all (it is NULL, so SUM() leaves it
-- out, the same rule python/clean_data.py applies).
--
-- How to run (from the project folder):
--   psql -U marketpulse_user -d marketpulse_synthetic -h localhost -f sql/10_profitability_analysis.sql
--   psql -U marketpulse_user -d marketpulse_private -h localhost -f sql/10_profitability_analysis.sql
--
-- Every statement here is a read-only SELECT. Nothing is ever written.
-- =====================================================================

\set ON_ERROR_STOP on

-- ---------------------------------------------------------------------
-- P1: What is the gross margin per unit for each product (selling
--     price minus unit cost)?
-- ---------------------------------------------------------------------
-- A straight read of the price list: Prepaid and COD have different
-- normal prices (docs/whatsapp_parser_plan.md), so both margins are shown.
\echo '--- P1: gross margin per unit, Prepaid and COD ---'
SELECT product_code, product_name,
       selling_price AS prepaid_price, cod_price, unit_cost,
       selling_price - unit_cost AS prepaid_margin_per_unit,
       round((selling_price - unit_cost) / NULLIF(selling_price, 0), 4) AS prepaid_margin_share,
       cod_price - unit_cost AS cod_margin_per_unit,
       round((cod_price - unit_cost) / NULLIF(cod_price, 0), 4) AS cod_margin_share
FROM clean.products
ORDER BY product_code;

-- ---------------------------------------------------------------------
-- P2: Which products give the most estimated gross profit in total?
--     (labelled: Estimate)
-- ---------------------------------------------------------------------
\echo '--- P2: estimated gross profit per product (ESTIMATE) ---'
SELECT i.product_code, p.product_name,
       sum(i.estimated_line_value) AS estimated_revenue,
       sum(i.estimated_line_cost)  AS estimated_cost,
       sum(i.estimated_line_value - i.estimated_line_cost) AS estimated_gross_profit
FROM clean.order_items i
JOIN clean.products p USING (product_code)
WHERE i.include_in_analysis
GROUP BY i.product_code, p.product_name
ORDER BY estimated_gross_profit DESC;

-- ---------------------------------------------------------------------
-- P3: What is the estimated gross profit per week after ad spend?
--     (labelled: Estimate)
-- ---------------------------------------------------------------------
-- A week with no orders or no ad spend shows as 0, never a gap. This
-- combines two tables that are otherwise never linked (docs/schema_design.md,
-- section 3): nothing records which ad led to which order, so this is
-- week-level spend against week-level profit, not per-order attribution.
\echo '--- P3: estimated gross profit per week, minus that week ad spend (ESTIMATE) ---'
WITH weeks AS (
    SELECT generate_series(min(week_start), max(week_start), interval '7 days')::date AS week_start
    FROM clean.orders WHERE include_in_analysis
), weekly_orders AS (
    SELECT week_start,
           sum(estimated_order_value) AS estimated_revenue,
           sum(estimated_order_cost)  AS estimated_cost
    FROM clean.orders
    WHERE include_in_analysis
    GROUP BY week_start
), weekly_spend AS (
    SELECT week_start, sum(amount_spent_inr) AS amount_spent_inr
    FROM clean.ad_performance
    GROUP BY week_start
)
SELECT w.week_start,
       coalesce(o.estimated_revenue, 0) AS estimated_revenue,
       coalesce(o.estimated_cost, 0)    AS estimated_cost,
       coalesce(o.estimated_revenue, 0) - coalesce(o.estimated_cost, 0) AS estimated_gross_profit,
       coalesce(s.amount_spent_inr, 0)  AS ad_spend,
       coalesce(o.estimated_revenue, 0) - coalesce(o.estimated_cost, 0) - coalesce(s.amount_spent_inr, 0)
           AS estimated_profit_after_ad_spend
FROM weeks w
LEFT JOIN weekly_orders o USING (week_start)
LEFT JOIN weekly_spend s USING (week_start)
ORDER BY w.week_start;
