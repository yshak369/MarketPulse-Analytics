-- =====================================================================
-- MarketPulse Analytics: add the COD price to an existing products table
-- =====================================================================
-- A product has one normal price for Prepaid orders (selling_price) and
-- another for COD orders (cod_price). Databases built with
-- sql/01_create_tables.sql after November 2026 already have the column.
-- This file adds it to a database built before that.
--
-- How to run (from the project folder):
--   psql -U marketpulse_user -d <database> -h localhost -f sql/06_add_cod_price.sql
--
-- Safe to run again: if the column is already there, nothing changes.
-- The new column starts empty (unknown). Fill it afterwards, for example
-- in pgAdmin (made-up values):
--   UPDATE products SET cod_price = 120 WHERE product_code = 'ABC';
-- =====================================================================

\set ON_ERROR_STOP on

ALTER TABLE products
    ADD COLUMN IF NOT EXISTS cod_price numeric(10, 2) CHECK (cod_price >= 0);

COMMENT ON COLUMN products.selling_price IS 'Normal Prepaid price';
COMMENT ON COLUMN products.cod_price IS 'Normal COD price';

SELECT count(*) AS products, count(cod_price) AS with_cod_price FROM products;
