-- =====================================================================
-- MarketPulse Analytics: the clean tables (analysis-ready)
-- =====================================================================
-- python/clean_data.py runs this file inside a new, empty schema (for
-- example "clean"), then fills the tables. Phases 4 to 6 (EDA, SQL
-- analysis, Power BI) read only these tables.
--
-- There are no personal details here: no name, phone, address, PIN
-- code or free-text note.
--
-- The CHECK rules repeat the cleaning rules (see docs/data_cleaning.md).
-- So the database itself refuses a cleaning result that breaks them.
--
-- This file contains plain SQL only (no psql commands), because Python
-- runs it. It creates the tables in the current schema.
-- =====================================================================

CREATE TABLE products (
    product_code   text PRIMARY KEY,
    product_name   text NOT NULL,
    selling_price  numeric(10, 2) CHECK (selling_price >= 0),   -- normal Prepaid price
    unit_cost      numeric(10, 2) CHECK (unit_cost >= 0),
    cod_price      numeric(10, 2) CHECK (cod_price >= 0)        -- normal COD price
);

CREATE TABLE customers (
    customer_id          text PRIMARY KEY,
    customer_identified  boolean NOT NULL,    -- false when the orders had no usable phone
    first_order_date     date,                -- counted orders only
    last_order_date      date,
    orders_counted       integer NOT NULL CHECK (orders_counted >= 0),
    is_repeat_customer   boolean NOT NULL,
    CHECK (NOT is_repeat_customer OR (customer_identified AND orders_counted > 1)),
    CHECK ((first_order_date IS NULL) = (orders_counted = 0))
);

CREATE TABLE orders (
    order_id               text PRIMARY KEY,
    customer_id            text NOT NULL REFERENCES customers (customer_id),
    customer_identified    boolean NOT NULL,
    customer_order_number  integer CHECK (customer_order_number >= 1),  -- 1 = first counted order
    is_repeat_order        boolean,
    order_datetime         timestamp NOT NULL,
    order_date             date NOT NULL,
    order_month            date NOT NULL,     -- first day of the month
    week_start             date NOT NULL,     -- the Monday of the week
    weekday                text NOT NULL,
    hour                   integer NOT NULL CHECK (hour BETWEEN 0 AND 23),
    sales_channel          text NOT NULL CHECK (sales_channel IN ('whatsapp', 'shopify')),
    payment_type           text NOT NULL CHECK (payment_type IN ('prepaid', 'cod', 'needs_review')),
    district_city          text,
    state                  text,
    district_from_override boolean NOT NULL,  -- district from the owner's override file
    units                  integer NOT NULL CHECK (units >= 0),
    product_lines          integer NOT NULL CHECK (product_lines >= 0),
    product_defaulted      boolean NOT NULL,  -- no product line: 1 CXE by the owner's rule
    order_amount           numeric(10, 2),    -- as RECORDED, never changed
    amount_basis           text NOT NULL,
    amount_reliable        boolean NOT NULL,
    estimated_order_value  numeric(12, 2),    -- from the price list: an ESTIMATE
    estimated_order_cost   numeric(12, 2),    -- from unit costs: an ESTIMATE
    order_value            numeric(12, 2),    -- recorded if reliable, else the estimate
    value_basis            text NOT NULL CHECK (value_basis IN ('recorded', 'estimated', 'unknown')),
    financial_status       text,
    fulfillment_status     text,
    is_cancelled           boolean NOT NULL,
    refunded_amount        numeric(10, 2) CHECK (refunded_amount >= 0),
    review_flags           text,
    include_in_analysis    boolean NOT NULL,
    exclusion_reason       text,

    -- An order is left out exactly when it has a reason.
    CHECK (include_in_analysis = (exclusion_reason IS NULL)),
    CHECK (NOT is_cancelled OR NOT include_in_analysis),
    -- Amounts: every value says where it comes from.
    CHECK (NOT amount_reliable OR order_amount IS NOT NULL),
    CHECK ((value_basis = 'recorded') = amount_reliable),
    CHECK ((value_basis = 'unknown') = (order_value IS NULL)),
    CHECK (value_basis <> 'recorded' OR order_value = order_amount),
    CHECK (value_basis <> 'estimated' OR order_value = estimated_order_value),
    -- Only counted orders of known customers are numbered.
    CHECK (customer_order_number IS NULL OR (include_in_analysis AND customer_identified)),
    CHECK ((is_repeat_order IS NULL) = (customer_order_number IS NULL)),
    -- Date parts agree with the date.
    CHECK (order_date = order_datetime::date),
    CHECK (extract(isodow FROM week_start) = 1)
);

CREATE TABLE order_items (
    order_item_id         integer PRIMARY KEY,
    order_id              text NOT NULL REFERENCES orders (order_id),
    product_code          text NOT NULL REFERENCES products (product_code),
    product_name          text,
    quantity              integer NOT NULL CHECK (quantity >= 1),
    line_amount           numeric(10, 2),     -- as RECORDED
    product_defaulted     boolean NOT NULL,
    price_used            numeric(10, 2),     -- price used for the estimate
    estimated_line_value  numeric(12, 2),     -- an ESTIMATE
    estimated_line_cost   numeric(12, 2),     -- an ESTIMATE
    include_in_analysis   boolean NOT NULL
);

CREATE TABLE shipments (
    shipment_id            text PRIMARY KEY,
    order_id               text NOT NULL REFERENCES orders (order_id),
    courier                text,
    delivery_status        text,
    delivered_date         date,
    delivery_days          integer CHECK (delivery_days >= 0),
    delivery_date_problem  boolean NOT NULL,  -- delivered before ordered: days left empty
    cod_amount_received    numeric(10, 2) CHECK (cod_amount_received >= 0),
    shipping_cost          numeric(10, 2) CHECK (shipping_cost >= 0),
    include_in_analysis    boolean NOT NULL,
    CHECK (NOT delivery_date_problem OR delivery_days IS NULL)
);

CREATE TABLE ad_campaigns (
    campaign_id          text PRIMARY KEY,
    campaign_name        text NOT NULL,
    delivery_status      text,
    attribution_setting  text,
    budget_amount        numeric(12, 2) CHECK (budget_amount >= 0),
    budget_type          text,
    end_date             date
);

-- Raw numbers only. Ratios such as CPM and CTR are worked out in SQL.
CREATE TABLE ad_performance (
    campaign_id         text NOT NULL REFERENCES ad_campaigns (campaign_id),
    campaign_name       text,               -- copied from ad_campaigns, for easier charts
    report_date         date NOT NULL,
    week_start          date NOT NULL,
    report_month        date NOT NULL,
    weekday             text NOT NULL,
    amount_spent_inr    numeric(12, 2) NOT NULL CHECK (amount_spent_inr >= 0),
    impressions         integer NOT NULL CHECK (impressions >= 0),
    reach               integer CHECK (reach >= 0),
    link_clicks         integer CHECK (link_clicks >= 0),
    clicks_all          integer CHECK (clicks_all >= 0),
    landing_page_views  integer CHECK (landing_page_views >= 0),
    results             integer CHECK (results >= 0),   -- only add results of the same result_type
    result_type         text CHECK (result_type IN
                            ('messaging_conversation', 'link_click', 'post_engagement', 'other')),
    result_indicator    text,
    PRIMARY KEY (campaign_id, report_date),
    CHECK ((result_type IS NULL) = (result_indicator IS NULL))
);
