-- =====================================================================
-- MarketPulse Analytics: load a cleaned Meta Ads export
-- =====================================================================
-- Reads the two files written by python/prepare_meta_ads.py:
--   meta_ad_campaigns.csv and meta_ad_performance.csv
-- and loads them into ad_campaigns and ad_performance.
--
-- How to run (from the project folder):
--   psql -U marketpulse_user -d <database> -h localhost
--        -v schema=<schema> -v input_folder=<folder with the two files>
--        -f sql/04_load_meta_ads.sql
--   The folder must use forward slashes and contain no spaces.
--
-- Test run on the fake export (see sql/test_setup_parser_schema.sql):
--   psql -U marketpulse_user -d marketpulse_synthetic -h localhost -v schema=parser_test -v input_folder=data/processed/meta_test_output -f sql/04_load_meta_ads.sql
--
-- Rules:
--   * "Upsert": a campaign or campaign-day that is already in the
--     database is updated, a new one is added. So loading the same
--     export twice, or a newer export that overlaps an older one,
--     never creates duplicates.
--   * Rows already in the database but not in this export are kept.
--     An export of a short period never deletes older data.
--   * All or nothing: everything runs inside one transaction.
--
-- Safety: the script refuses to load into the public schema of
-- marketpulse_synthetic, so test data never mixes with the public
-- synthetic dataset.
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
  \echo 'Missing setting: add -v input_folder=<folder with the two files> to the command.'
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

CREATE TEMP TABLE staging_campaigns (
    campaign_id text, campaign_name text, delivery_status text, attribution_setting text,
    budget_amount text, budget_type text, end_date text
) ON COMMIT DROP;

CREATE TEMP TABLE staging_performance (
    campaign_id text, report_date text, amount_spent_inr text, impressions text, reach text,
    link_clicks text, clicks_all text, landing_page_views text, results text, result_indicator text
) ON COMMIT DROP;

\copy staging_campaigns FROM 'meta_ad_campaigns.csv' WITH (FORMAT csv, HEADER true)
\copy staging_performance FROM 'meta_ad_performance.csv' WITH (FORMAT csv, HEADER true)

-- Note what is new before loading, for the summary.
CREATE TEMP TABLE new_campaigns ON COMMIT DROP AS
SELECT campaign_id FROM staging_campaigns s
WHERE NOT EXISTS (SELECT 1 FROM ad_campaigns a WHERE a.campaign_id = s.campaign_id);

CREATE TEMP TABLE new_days ON COMMIT DROP AS
SELECT campaign_id, report_date FROM staging_performance s
WHERE NOT EXISTS (SELECT 1 FROM ad_performance a
                  WHERE a.campaign_id = s.campaign_id AND a.report_date = s.report_date::date);

-- Campaigns: add new ones, update the details of known ones.
INSERT INTO ad_campaigns (campaign_id, campaign_name, delivery_status, attribution_setting,
                          budget_amount, budget_type, end_date)
SELECT campaign_id, campaign_name, delivery_status, attribution_setting,
       budget_amount::numeric, budget_type, end_date::date
FROM staging_campaigns
ON CONFLICT (campaign_id) DO UPDATE SET
    campaign_name       = EXCLUDED.campaign_name,
    delivery_status     = EXCLUDED.delivery_status,
    attribution_setting = EXCLUDED.attribution_setting,
    budget_amount       = EXCLUDED.budget_amount,
    budget_type         = EXCLUDED.budget_type,
    end_date            = EXCLUDED.end_date;

-- Daily performance: add new days, update days already loaded.
INSERT INTO ad_performance (campaign_id, report_date, amount_spent_inr, impressions, reach,
                            link_clicks, clicks_all, landing_page_views, results, result_indicator)
SELECT campaign_id, report_date::date, amount_spent_inr::numeric, impressions::integer, reach::integer,
       link_clicks::integer, clicks_all::integer, landing_page_views::integer, results::integer,
       result_indicator
FROM staging_performance
ON CONFLICT (campaign_id, report_date) DO UPDATE SET
    amount_spent_inr   = EXCLUDED.amount_spent_inr,
    impressions        = EXCLUDED.impressions,
    reach              = EXCLUDED.reach,
    link_clicks        = EXCLUDED.link_clicks,
    clicks_all         = EXCLUDED.clicks_all,
    landing_page_views = EXCLUDED.landing_page_views,
    results            = EXCLUDED.results,
    result_indicator   = EXCLUDED.result_indicator;

\echo
\echo 'Load summary'
SELECT
    (SELECT count(*) FROM staging_campaigns)                      AS campaigns_in_file,
    (SELECT count(*) FROM new_campaigns)                          AS campaigns_new,
    (SELECT count(*) FROM staging_performance)                    AS days_in_file,
    (SELECT count(*) FROM new_days)                               AS days_new,
    (SELECT sum(amount_spent_inr::numeric) FROM staging_performance) AS spend_in_file_inr;

\echo 'Results in this file, by kind (never add different kinds together)'
SELECT result_indicator, sum(results::integer) AS results
FROM staging_performance
WHERE result_indicator IS NOT NULL
GROUP BY result_indicator
ORDER BY result_indicator;

COMMIT;
