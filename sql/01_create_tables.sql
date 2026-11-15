-- =====================================================================
-- MarketPulse Analytics: create the database tables
-- =====================================================================
-- This file builds the eight empty tables described in
-- docs/schema_design.md. It contains structure only, no data.
--
-- The same file is used for both databases:
--   marketpulse_synthetic  (fake public data)
--   marketpulse_private    (real data, owner's computer only)
--
-- How to run (from the project folder, in your own terminal):
--   psql -U marketpulse_user -d marketpulse_synthetic -v ON_ERROR_STOP=1 -f sql/01_create_tables.sql
--
-- Everything runs inside one transaction (BEGIN ... COMMIT).
-- If any statement fails, nothing is created, so the database is
-- never left half-built.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. products: one row per product
-- ---------------------------------------------------------------------
CREATE TABLE products (
    product_code   text PRIMARY KEY,               -- for example 'CXE'
    product_name   text NOT NULL,                  -- for example 'Cream'
    selling_price  numeric(10, 2) CHECK (selling_price >= 0),
    unit_cost      numeric(10, 2) CHECK (unit_cost >= 0),
    CHECK (product_code = upper(product_code))     -- codes are stored in capitals
);

-- ---------------------------------------------------------------------
-- 2. product_aliases: every way a product is written -> one product_code
-- ---------------------------------------------------------------------
CREATE TABLE product_aliases (
    alias         text PRIMARY KEY,                -- name as written, in lower case
    source        text NOT NULL CHECK (source IN ('whatsapp', 'shopify')),
    product_code  text NOT NULL REFERENCES products (product_code),
    CHECK (alias = lower(alias))
);

-- ---------------------------------------------------------------------
-- 3. customers: one row per customer
-- ---------------------------------------------------------------------
CREATE TABLE customers (
    customer_id    text PRIMARY KEY,               -- new random ID, not made from the phone
    customer_name  text,                           -- private only; placeholder in synthetic data
    phone          text UNIQUE                     -- one phone = one customer; empty in synthetic data
);

-- ---------------------------------------------------------------------
-- 4. orders: one row per order, from WhatsApp or Shopify
-- ---------------------------------------------------------------------
CREATE TABLE orders (
    order_id            text PRIMARY KEY,          -- new random ID
    customer_id         text NOT NULL REFERENCES customers (customer_id),
    order_datetime      timestamp NOT NULL,        -- Indian local time
    sales_channel       text NOT NULL CHECK (sales_channel IN ('whatsapp', 'shopify')),
    payment_type        text NOT NULL CHECK (payment_type IN ('prepaid', 'cod', 'needs_review')),
    address             text,                      -- private only
    district_city       text,
    state               text,
    pin_code            text,                      -- text, not a number: it is a code, not a quantity
    order_amount        numeric(10, 2) CHECK (order_amount >= 0),
    amount_basis        text NOT NULL CHECK (amount_basis IN
                            ('cod_collectible', 'shopify_total', 'estimated', 'unknown')),
    financial_status    text,                      -- Shopify only
    fulfillment_status  text,                      -- Shopify only
    cancelled_at        timestamp,                 -- Shopify only; empty if not cancelled
    review_flags        text,                      -- empty if clean
    notes               text,                      -- for example 'product_defaulted_to_cxe'

    -- Honesty rule: an amount exists exactly when its basis is known.
    -- 'unknown' must have no amount; every other basis must have one.
    CHECK ((amount_basis = 'unknown') = (order_amount IS NULL))
);

-- ---------------------------------------------------------------------
-- 5. order_items: one row per product line in an order
-- ---------------------------------------------------------------------
CREATE TABLE order_items (
    order_item_id      integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- automatic number
    order_id           text NOT NULL REFERENCES orders (order_id),
    product_code       text NOT NULL REFERENCES products (product_code),
    quantity           integer NOT NULL CHECK (quantity >= 1),
    line_amount        numeric(10, 2) CHECK (line_amount >= 0),  -- total for the line; empty for WhatsApp prepaid
    product_defaulted  boolean NOT NULL DEFAULT false            -- true when no product line was written
);

-- ---------------------------------------------------------------------
-- 6. shipments: one row per shipment (mostly empty until courier data is added)
-- ---------------------------------------------------------------------
CREATE TABLE shipments (
    shipment_id          text PRIMARY KEY,         -- new random ID
    order_id             text NOT NULL REFERENCES orders (order_id),
    courier              text CHECK (courier IN ('speed_post', 'delhivery')),
    delivery_status      text,                     -- for example 'delivered', 'returned', 'unknown'
    delivered_date       date,
    cod_amount_received  numeric(10, 2) CHECK (cod_amount_received >= 0),  -- money actually received
    shipping_cost        numeric(10, 2) CHECK (shipping_cost >= 0)
);

-- ---------------------------------------------------------------------
-- 7. ad_campaigns: one row per Meta campaign
-- ---------------------------------------------------------------------
CREATE TABLE ad_campaigns (
    campaign_id          text PRIMARY KEY,         -- Meta's own Campaign ID (names are not unique)
    campaign_name        text NOT NULL,
    delivery_status      text,
    attribution_setting  text,                     -- empty when Meta shows '-'
    budget_amount        numeric(12, 2) CHECK (budget_amount >= 0),  -- empty when set at ad set level
    budget_type          text,
    end_date             date                      -- empty when the campaign is ongoing
);

-- ---------------------------------------------------------------------
-- 8. ad_performance: one row per campaign per day
-- ---------------------------------------------------------------------
-- Not linked to orders: nothing records which ad led to which order.
-- Derived figures (CPM, CPC, CTR, frequency, cost per result) are not
-- stored. They are calculated in SQL from the raw numbers below.
CREATE TABLE ad_performance (
    campaign_id         text NOT NULL REFERENCES ad_campaigns (campaign_id),
    report_date         date NOT NULL,
    amount_spent_inr    numeric(12, 2) NOT NULL CHECK (amount_spent_inr >= 0),
    impressions         integer NOT NULL CHECK (impressions >= 0),
    reach               integer CHECK (reach >= 0),         -- never add reach across days
    link_clicks         integer CHECK (link_clicks >= 0),
    clicks_all          integer CHECK (clicks_all >= 0),
    landing_page_views  integer CHECK (landing_page_views >= 0),
    results             integer CHECK (results >= 0),       -- meaning depends on result_indicator
    result_indicator    text,                               -- only add results with the same indicator
    PRIMARY KEY (campaign_id, report_date)                  -- at most one row per campaign per day
);

COMMIT;
