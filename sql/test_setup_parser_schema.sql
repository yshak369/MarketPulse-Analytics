-- =====================================================================
-- MarketPulse Analytics: set up the parser_test schema
-- =====================================================================
-- A schema is like a folder inside a database. This script makes a
-- separate schema called parser_test inside marketpulse_synthetic,
-- with its own empty copy of the eight tables, plus the synthetic
-- product list. The fake chat orders are loaded there, so they never
-- mix with the public synthetic dataset in the public schema.
--
-- WARNING: this script deletes the parser_test schema and everything
-- in it, then builds it again. It never touches the public schema.
--
-- How to run (from the project folder):
--   psql -U marketpulse_user -d marketpulse_synthetic -h localhost -f sql/test_setup_parser_schema.sql
-- =====================================================================

\set ON_ERROR_STOP on
\encoding UTF8

DROP SCHEMA IF EXISTS parser_test CASCADE;
CREATE SCHEMA parser_test;
SET search_path TO parser_test;

-- Build the eight tables inside parser_test, using the normal script.
\ir 01_create_tables.sql

-- The products are needed, because order_items must point to them.
\copy products (product_code, product_name, selling_price, unit_cost, cod_price) FROM 'data/synthetic/synthetic_products.csv' WITH (FORMAT csv, HEADER true)

SELECT count(*) AS tables_in_parser_test
FROM information_schema.tables
WHERE table_schema = 'parser_test';
