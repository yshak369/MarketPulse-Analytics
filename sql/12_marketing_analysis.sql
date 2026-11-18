-- =====================================================================
-- MarketPulse Analytics: marketing analysis (Phase 5)
-- =====================================================================
-- Answers the Marketing Analytics questions (M1-M6) in
-- docs/business_questions.md, reading only the "clean" schema
-- (docs/data_cleaning.md).
--
-- The same questions are also answered in python/eda.py: the same
-- question, the same database, two independent tools.
--
-- Results of different result_type values are never added together.
-- Ad spend and orders are compared by week only: nothing in this data
-- links one ad to one order (docs/schema_design.md), so a correlation
-- below is a PATTERN, never proof that spend caused those orders.
--
-- Every query here returns 0 rows, not an error, when ad_performance
-- is empty (no Meta Ads import has been run yet).
--
-- How to run (from the project folder):
--   psql -U marketpulse_user -d marketpulse_synthetic -h localhost -f sql/12_marketing_analysis.sql
--   psql -U marketpulse_user -d marketpulse_private -h localhost -f sql/12_marketing_analysis.sql
--
-- Every statement here is a read-only SELECT. Nothing is ever written.
-- =====================================================================

\set ON_ERROR_STOP on

-- ---------------------------------------------------------------------
-- M1: How much is spent on ads per day and per week?
-- ---------------------------------------------------------------------
\echo '--- M1: ad spend per week ---'
WITH weeks AS (
    SELECT generate_series(min(week_start), max(week_start), interval '7 days')::date AS week_start
    FROM clean.ad_performance
), weekly AS (
    SELECT week_start, sum(amount_spent_inr) AS amount_spent_inr
    FROM clean.ad_performance
    GROUP BY week_start
)
SELECT w.week_start, coalesce(x.amount_spent_inr, 0) AS amount_spent_inr
FROM weeks w
LEFT JOIN weekly x USING (week_start)
ORDER BY w.week_start;

-- ---------------------------------------------------------------------
-- M2: Which campaigns have the lowest cost per messaging conversation started?
-- ---------------------------------------------------------------------
\echo '--- M2: cost per messaging conversation, per campaign ---'
SELECT campaign_id, campaign_name,
       sum(amount_spent_inr) AS amount_spent_inr,
       sum(results) AS conversations,
       round(sum(amount_spent_inr) / NULLIF(sum(results), 0), 2) AS cost_per_conversation
FROM clean.ad_performance
WHERE result_type = 'messaging_conversation'
GROUP BY campaign_id, campaign_name
ORDER BY cost_per_conversation;

-- ---------------------------------------------------------------------
-- M3: How do CPM and CTR change over time for each campaign?
-- ---------------------------------------------------------------------
-- CPM and CTR are worked out here from raw spend/impressions/clicks,
-- never stored (docs/schema_design.md, design rule 1).
\echo '--- M3: weekly CPM and CTR per campaign ---'
SELECT campaign_id, campaign_name, week_start,
       sum(amount_spent_inr) AS amount_spent_inr,
       sum(impressions) AS impressions,
       round(sum(amount_spent_inr) / NULLIF(sum(impressions), 0) * 1000, 2) AS cpm,
       round(sum(clicks_all)::numeric / NULLIF(sum(impressions), 0), 4) AS ctr
FROM clean.ad_performance
GROUP BY campaign_id, campaign_name, week_start
ORDER BY campaign_id, week_start;

-- ---------------------------------------------------------------------
-- M4-M6: On weeks with higher ad spend, are there more orders? What is
--        the overall spend per order, and conversations per order?
-- ---------------------------------------------------------------------
\echo '--- M4-M6: weekly ad spend vs weekly WhatsApp orders ---'
WITH weeks AS (
    SELECT generate_series(min(week_start), max(week_start), interval '7 days')::date AS week_start
    FROM clean.ad_performance
), spend AS (
    SELECT week_start, sum(amount_spent_inr) AS amount_spent_inr
    FROM clean.ad_performance
    GROUP BY week_start
), conversations AS (
    SELECT week_start, sum(results) AS messaging_conversations
    FROM clean.ad_performance
    WHERE result_type = 'messaging_conversation'
    GROUP BY week_start
), whatsapp_orders AS (
    SELECT week_start, count(*) AS whatsapp_orders
    FROM clean.orders
    WHERE include_in_analysis AND sales_channel = 'whatsapp'
    GROUP BY week_start
)
SELECT w.week_start,
       coalesce(s.amount_spent_inr, 0)         AS amount_spent_inr,
       coalesce(c.messaging_conversations, 0)  AS messaging_conversations,
       coalesce(o.whatsapp_orders, 0)          AS whatsapp_orders,
       round(coalesce(s.amount_spent_inr, 0) / NULLIF(coalesce(o.whatsapp_orders, 0), 0), 2) AS spend_per_order,
       round(coalesce(c.messaging_conversations, 0)::numeric
             / NULLIF(coalesce(o.whatsapp_orders, 0), 0), 2) AS conversations_per_order
FROM weeks w
LEFT JOIN spend s USING (week_start)
LEFT JOIN conversations c USING (week_start)
LEFT JOIN whatsapp_orders o USING (week_start)
ORDER BY w.week_start;

-- corr() is PostgreSQL's built-in Pearson correlation, the SQL
-- equivalent of np.corrcoef. NULL when there are too few weeks, or
-- spend or orders never vary (never a divide-by-zero error).
\echo '--- M4-M6: correlation between weekly spend and weekly WhatsApp orders (a PATTERN, not proof) ---'
WITH weeks AS (
    SELECT generate_series(min(week_start), max(week_start), interval '7 days')::date AS week_start
    FROM clean.ad_performance
), spend AS (
    SELECT week_start, sum(amount_spent_inr) AS amount_spent_inr
    FROM clean.ad_performance
    GROUP BY week_start
), whatsapp_orders AS (
    SELECT week_start, count(*) AS whatsapp_orders
    FROM clean.orders
    WHERE include_in_analysis AND sales_channel = 'whatsapp'
    GROUP BY week_start
)
SELECT round(corr(coalesce(s.amount_spent_inr, 0), coalesce(o.whatsapp_orders, 0))::numeric, 4) AS correlation
FROM weeks w
LEFT JOIN spend s USING (week_start)
LEFT JOIN whatsapp_orders o USING (week_start);
