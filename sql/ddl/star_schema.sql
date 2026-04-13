-- =============================================================================
-- FILE: star_schema.sql
-- PROJECT: Dadosfera Data Platform -- E-Commerce Case Study
-- DESCRIPTION: Complete DDL for the Kimball Star Schema (Snowflake dialect)
--              Covers all three zones: raw_zone, trusted_zone, refined_zone
-- GRAIN (fact_orders): One row = one order item (product sold in one order)
-- GRAIN (fact_reviews): One row = one customer review per order
-- SCD STRATEGY: Type 1 (overwrite) -- static dataset (Olist 2016-2018)
-- DIALECT: Snowflake SQL
-- AUTHOR: Leonardo Nunes
-- DATE: April 2026
-- VERSION: 1.0
-- =============================================================================


-- =============================================================================
-- SECTION 1: SCHEMA DEFINITIONS
-- =============================================================================

-- Raw Zone: Landing area for unprocessed CSV data ingested from Kaggle
-- No transformations, no enforced types beyond VARCHAR. Audit trail.
CREATE SCHEMA IF NOT EXISTS raw_zone
    COMMENT = 'Landing zone for raw CSV data from Olist Kaggle dataset. No transformations applied.';

-- Trusted Zone: Cleansed, typed, and deduplicated staging layer.
-- Enforces data types, removes duplicates, validates referential integrity.
CREATE SCHEMA IF NOT EXISTS trusted_zone
    COMMENT = 'Cleansed and validated staging layer. Typed columns, deduplication, PK enforcement.';

-- Refined Zone: Consumption-ready dimensional model (Kimball Star Schema).
-- Dimensions with surrogate keys and facts with measures. BI-ready.
CREATE SCHEMA IF NOT EXISTS refined_zone
    COMMENT = 'Kimball Star Schema for analytical consumption. Dimensions + facts. BI-ready.';


-- =============================================================================
-- SECTION 2: RAW ZONE -- LANDING TABLES
-- =============================================================================
-- All columns are VARCHAR to preserve raw data exactly as ingested.
-- No PKs enforced at this layer. Load timestamp added for auditing.

CREATE OR REPLACE TABLE raw_zone.raw_orders (
    order_id                        VARCHAR(50),
    customer_id                     VARCHAR(50),
    order_status                    VARCHAR(50),
    order_purchase_timestamp        VARCHAR(30),
    order_approved_at               VARCHAR(30),
    order_delivered_carrier_date    VARCHAR(30),
    order_delivered_customer_date   VARCHAR(30),
    order_estimated_delivery_date   VARCHAR(30),
    _ingested_at                    TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Raw landing table for olist_orders.csv. All columns VARCHAR. No transformations.';

CREATE OR REPLACE TABLE raw_zone.raw_order_items (
    order_id                VARCHAR(50),
    order_item_id           VARCHAR(10),
    product_id              VARCHAR(50),
    seller_id               VARCHAR(50),
    shipping_limit_date     VARCHAR(30),
    price                   VARCHAR(20),
    freight_value           VARCHAR(20),
    _ingested_at            TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Raw landing table for olist_order_items.csv. All columns VARCHAR.';

CREATE OR REPLACE TABLE raw_zone.raw_order_payments (
    order_id                VARCHAR(50),
    payment_sequential      VARCHAR(10),
    payment_type            VARCHAR(30),
    payment_installments    VARCHAR(10),
    payment_value           VARCHAR(20),
    _ingested_at            TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Raw landing table for olist_order_payments.csv. All columns VARCHAR.';

CREATE OR REPLACE TABLE raw_zone.raw_order_reviews (
    review_id               VARCHAR(50),
    order_id                VARCHAR(50),
    review_score            VARCHAR(5),
    review_comment_title    VARCHAR(200),
    review_comment_message  VARCHAR(2000),
    review_creation_date    VARCHAR(30),
    review_answer_timestamp VARCHAR(30),
    _ingested_at            TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Raw landing table for olist_order_reviews.csv. All columns VARCHAR.';

CREATE OR REPLACE TABLE raw_zone.raw_customers (
    customer_id             VARCHAR(50),
    customer_unique_id      VARCHAR(50),
    customer_zip_code_prefix VARCHAR(10),
    customer_city           VARCHAR(100),
    customer_state          VARCHAR(5),
    _ingested_at            TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Raw landing table for olist_customers.csv. All columns VARCHAR.';

CREATE OR REPLACE TABLE raw_zone.raw_products (
    product_id                  VARCHAR(50),
    product_category_name       VARCHAR(100),
    product_name_lenght         VARCHAR(10),
    product_description_lenght  VARCHAR(10),
    product_photos_qty          VARCHAR(10),
    product_weight_g            VARCHAR(10),
    product_length_cm           VARCHAR(10),
    product_height_cm           VARCHAR(10),
    product_width_cm            VARCHAR(10),
    _ingested_at                TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Raw landing table for olist_products.csv. All columns VARCHAR.';

CREATE OR REPLACE TABLE raw_zone.raw_sellers (
    seller_id               VARCHAR(50),
    seller_zip_code_prefix  VARCHAR(10),
    seller_city             VARCHAR(100),
    seller_state            VARCHAR(5),
    _ingested_at            TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Raw landing table for olist_sellers.csv. All columns VARCHAR.';

CREATE OR REPLACE TABLE raw_zone.raw_geolocation (
    geolocation_zip_code_prefix VARCHAR(10),
    geolocation_lat             VARCHAR(30),
    geolocation_lng             VARCHAR(30),
    geolocation_city            VARCHAR(100),
    geolocation_state           VARCHAR(5),
    _ingested_at                TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Raw landing table for olist_geolocation.csv. Multiple rows per ZIP prefix expected.';

CREATE OR REPLACE TABLE raw_zone.raw_category_translation (
    product_category_name           VARCHAR(100),
    product_category_name_english   VARCHAR(100),
    _ingested_at                    TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Raw landing table for product_category_name_translation.csv.';


-- =============================================================================
-- SECTION 3: TRUSTED ZONE -- STAGING TABLES
-- =============================================================================
-- Typed, deduplicated, validated. Source of truth for dimensional modeling.
-- Natural keys enforced. Referential integrity validated (not enforced by DB).

CREATE OR REPLACE TABLE trusted_zone.stg_orders (
    order_id                        VARCHAR(50)     NOT NULL,   -- PK: unique order identifier
    customer_id                     VARCHAR(50)     NOT NULL,   -- FK to stg_customers (per-order ID)
    order_status                    VARCHAR(20)     NOT NULL,   -- Values: created, approved, processing, shipped, delivered, canceled, unavailable
    order_purchase_timestamp        TIMESTAMP_NTZ   NOT NULL,   -- Moment of purchase
    order_approved_at               TIMESTAMP_NTZ,              -- Nullable: approval may not happen (canceled orders)
    order_delivered_carrier_date    TIMESTAMP_NTZ,              -- Nullable: shipped orders only
    order_delivered_customer_date   TIMESTAMP_NTZ,              -- Nullable: delivered orders only
    order_estimated_delivery_date   TIMESTAMP_NTZ,              -- Promised delivery date
    _ingested_at                    TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    _updated_at                     TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT stg_orders_pk PRIMARY KEY (order_id)
)
COMMENT = 'Cleansed orders staging table. Typed columns, unique order_id enforced.';

CREATE OR REPLACE TABLE trusted_zone.stg_order_items (
    order_id                VARCHAR(50)     NOT NULL,   -- FK to stg_orders
    order_item_id           INTEGER         NOT NULL,   -- Sequential item number within the order
    product_id              VARCHAR(50)     NOT NULL,   -- FK to stg_products
    seller_id               VARCHAR(50)     NOT NULL,   -- FK to stg_sellers
    shipping_limit_date     TIMESTAMP_NTZ   NOT NULL,   -- Deadline for seller to dispatch
    price                   DECIMAL(12, 2)  NOT NULL,   -- Unit price of the product
    freight_value           DECIMAL(12, 2)  NOT NULL,   -- Freight cost for this item
    _ingested_at            TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT stg_order_items_pk PRIMARY KEY (order_id, order_item_id)
)
COMMENT = 'Cleansed order items staging table. Composite PK (order_id, order_item_id).';

CREATE OR REPLACE TABLE trusted_zone.stg_order_payments (
    order_id                VARCHAR(50)     NOT NULL,   -- FK to stg_orders
    payment_sequential      INTEGER         NOT NULL,   -- Sequence: 1 = primary payment method
    payment_type            VARCHAR(20)     NOT NULL,   -- Values: credit_card, boleto, voucher, debit_card
    payment_installments    INTEGER         NOT NULL,   -- Number of installments (1 = lump sum)
    payment_value           DECIMAL(12, 2)  NOT NULL,   -- Amount paid via this method
    _ingested_at            TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT stg_order_payments_pk PRIMARY KEY (order_id, payment_sequential)
)
COMMENT = 'Cleansed payments staging table. One order may have multiple payment methods.';

CREATE OR REPLACE TABLE trusted_zone.stg_order_reviews (
    review_id               VARCHAR(50)     NOT NULL,   -- PK: unique review identifier
    order_id                VARCHAR(50)     NOT NULL,   -- FK to stg_orders (1 review per order)
    review_score            INTEGER         NOT NULL,   -- Rating 1-5 (1 = worst, 5 = best)
    review_comment_title    VARCHAR(200),               -- Optional: title provided by customer
    review_comment_message  VARCHAR(2000),              -- Optional: free text review
    review_creation_date    TIMESTAMP_NTZ   NOT NULL,   -- When the review request was sent
    review_answer_timestamp TIMESTAMP_NTZ,              -- When the customer responded (nullable)
    _ingested_at            TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT stg_order_reviews_pk PRIMARY KEY (review_id)
)
COMMENT = 'Cleansed reviews staging table. Not all orders have reviews (nullable relationship).';

CREATE OR REPLACE TABLE trusted_zone.stg_customers (
    customer_id             VARCHAR(50)     NOT NULL,   -- Per-order customer ID (unique per order)
    customer_unique_id      VARCHAR(50)     NOT NULL,   -- True customer identifier (for recurrence analysis)
    customer_zip_code_prefix VARCHAR(10)    NOT NULL,   -- 5-digit ZIP prefix (not full ZIP for anonymization)
    customer_city           VARCHAR(100)    NOT NULL,   -- Customer city
    customer_state          VARCHAR(5)      NOT NULL,   -- Brazilian state abbreviation (e.g., SP, RJ)
    _ingested_at            TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT stg_customers_pk PRIMARY KEY (customer_id)
)
COMMENT = 'Cleansed customers staging. customer_id is per-order; customer_unique_id identifies the real person.';

CREATE OR REPLACE TABLE trusted_zone.stg_products (
    product_id                  VARCHAR(50)     NOT NULL,   -- PK: unique product identifier
    product_category_name       VARCHAR(100),               -- Category name in Portuguese (nullable: some products uncategorized)
    product_name_length         INTEGER,                    -- Proxy for name detail richness
    product_description_length  INTEGER,                    -- Proxy for description richness
    product_photos_qty          INTEGER,                    -- Number of product photos
    product_weight_g            INTEGER,                    -- Weight in grams (for freight calculation)
    product_length_cm           INTEGER,                    -- Length in centimeters
    product_height_cm           INTEGER,                    -- Height in centimeters
    product_width_cm            INTEGER,                    -- Width in centimeters
    _ingested_at                TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT stg_products_pk PRIMARY KEY (product_id)
)
COMMENT = 'Cleansed products staging. Physical dimensions and category attributes.';

CREATE OR REPLACE TABLE trusted_zone.stg_sellers (
    seller_id               VARCHAR(50)     NOT NULL,   -- PK: unique seller identifier
    seller_zip_code_prefix  VARCHAR(10)     NOT NULL,   -- 5-digit ZIP prefix of seller location
    seller_city             VARCHAR(100)    NOT NULL,   -- Seller city
    seller_state            VARCHAR(5)      NOT NULL,   -- Brazilian state abbreviation
    _ingested_at            TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT stg_sellers_pk PRIMARY KEY (seller_id)
)
COMMENT = 'Cleansed sellers staging. Location attributes for seller performance analysis.';

CREATE OR REPLACE TABLE trusted_zone.stg_geolocation (
    zip_code_prefix         VARCHAR(10)     NOT NULL,   -- 5-digit ZIP prefix (deduplicated: 1 row per ZIP)
    latitude                DECIMAL(12, 8)  NOT NULL,   -- Centroid latitude of the ZIP area
    longitude               DECIMAL(12, 8)  NOT NULL,   -- Centroid longitude of the ZIP area
    city                    VARCHAR(100)    NOT NULL,   -- City name
    state                   VARCHAR(5)      NOT NULL,   -- Brazilian state abbreviation
    _ingested_at            TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT stg_geolocation_pk PRIMARY KEY (zip_code_prefix)
)
COMMENT = 'Deduplicated geolocation staging. One row per ZIP prefix using centroid coordinates.';

CREATE OR REPLACE TABLE trusted_zone.stg_category_translation (
    product_category_name           VARCHAR(100)    NOT NULL,   -- Portuguese category name (PK)
    product_category_name_english   VARCHAR(100)    NOT NULL,   -- English translation
    _ingested_at                    TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT stg_category_translation_pk PRIMARY KEY (product_category_name)
)
COMMENT = 'Category name translation table (PT -> EN) for internationalized dashboards.';


-- =============================================================================
-- SECTION 4: REFINED ZONE -- DIMENSIONAL MODEL (STAR SCHEMA)
-- =============================================================================
-- Kimball methodology. Surrogate keys on all dimensions.
-- FK references documented as comments (Snowflake does not enforce FKs).
-- SCD Type 1: overwrite (static dataset).


-- -----------------------------------------------------------------------------
-- DIMENSION: dim_date
-- Grain: One row = one calendar day
-- Type: Static / Type 0 (immutable by nature)
-- Source: Generated by calendar generation script (not from source data)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE refined_zone.dim_date (

    -- Primary key
    date_key            INTEGER         NOT NULL,   -- Surrogate key in YYYYMMDD format (e.g., 20170312). Numeric for fast joins.

    -- Date attributes
    full_date           DATE            NOT NULL,   -- Full calendar date (e.g., 2017-03-12)
    year                INTEGER         NOT NULL,   -- Calendar year (e.g., 2017)
    quarter             INTEGER         NOT NULL,   -- Quarter of year: 1, 2, 3, or 4
    month               INTEGER         NOT NULL,   -- Month number: 1-12
    month_name          VARCHAR(20)     NOT NULL,   -- Month name in Portuguese (e.g., Janeiro, Fevereiro)
    week                INTEGER         NOT NULL,   -- ISO week number: 1-53
    day_of_month        INTEGER         NOT NULL,   -- Day within the month: 1-31
    day_of_week         INTEGER         NOT NULL,   -- ISO day of week: 1=Monday ... 7=Sunday
    day_of_week_name    VARCHAR(20)     NOT NULL,   -- Day name in Portuguese (e.g., Segunda-feira)
    is_weekend          BOOLEAN         NOT NULL,   -- TRUE if Saturday or Sunday
    is_holiday          BOOLEAN         NOT NULL DEFAULT FALSE,  -- TRUE if Brazilian national holiday

    CONSTRAINT dim_date_pk PRIMARY KEY (date_key)
)
COMMENT = 'Conformed date dimension. Shared by fact_orders and fact_reviews. Generated from calendar script.';

COMMENT ON COLUMN refined_zone.dim_date.date_key IS 'Surrogate key in YYYYMMDD integer format. Used as FK in fact tables.';
COMMENT ON COLUMN refined_zone.dim_date.full_date IS 'Full calendar date. Used for range filters in analytical queries.';
COMMENT ON COLUMN refined_zone.dim_date.is_weekend IS 'TRUE for Saturday (day_of_week=6) and Sunday (day_of_week=7).';
COMMENT ON COLUMN refined_zone.dim_date.is_holiday IS 'TRUE for Brazilian national holidays. Populated from holiday calendar.';


-- Sentinel row for unknown dates
INSERT INTO refined_zone.dim_date
    (date_key, full_date, year, quarter, month, month_name, week, day_of_month, day_of_week, day_of_week_name, is_weekend, is_holiday)
VALUES
    (-1, '1900-01-01', 1900, 1, 1, 'Desconhecido', 0, 0, 0, 'Desconhecido', FALSE, FALSE);


-- -----------------------------------------------------------------------------
-- DIMENSION: dim_customer
-- Grain: One row = one unique customer (customer_unique_id)
-- SCD Type: 1 (overwrite) -- static dataset
-- Source: trusted_zone.stg_customers (deduped to customer_unique_id level)
-- Note: customer_id in source is per-order; we model at customer_unique_id grain
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE refined_zone.dim_customer (

    -- Surrogate key (system-generated, stable, immutable)
    customer_key            NUMBER          NOT NULL AUTOINCREMENT START 1 INCREMENT 1,

    -- Natural key (business identifier from source)
    customer_unique_id      VARCHAR(50)     NOT NULL,   -- True customer identifier across multiple orders

    -- Descriptive attributes
    customer_city           VARCHAR(100)    NOT NULL,   -- City of the customer (from ZIP lookup)
    customer_state          VARCHAR(5)      NOT NULL,   -- Brazilian state abbreviation (e.g., SP, MG, RJ)
    customer_zip_code       VARCHAR(10)     NOT NULL,   -- 5-digit ZIP prefix (anonymized, not full ZIP)
    customer_region         VARCHAR(20),                -- Macro-region derived from state (Norte, Sul, etc.)

    -- Metadata
    _loaded_at              TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    _source                 VARCHAR(50)     NOT NULL DEFAULT 'olist_customers',

    CONSTRAINT dim_customer_pk PRIMARY KEY (customer_key),
    CONSTRAINT dim_customer_nk UNIQUE (customer_unique_id)
)
COMMENT = 'Customer dimension. Grain: one unique customer (customer_unique_id). SCD Type 1.';

COMMENT ON COLUMN refined_zone.dim_customer.customer_key IS 'Surrogate key. System-generated. Used as FK in fact tables.';
COMMENT ON COLUMN refined_zone.dim_customer.customer_unique_id IS 'Natural key. Identifies the real customer across multiple orders.';
COMMENT ON COLUMN refined_zone.dim_customer.customer_zip_code IS '5-digit ZIP prefix. Not full ZIP code — anonymized in source data.';
COMMENT ON COLUMN refined_zone.dim_customer.customer_region IS 'Brazilian macro-region: Norte, Nordeste, Centro-Oeste, Sudeste, Sul. Derived from state.';

-- Sentinel row: FK=-1 used when order has no matching customer
INSERT INTO refined_zone.dim_customer
    (customer_key, customer_unique_id, customer_city, customer_state, customer_zip_code, customer_region)
OVERWRITE
VALUES
    (-1, 'UNKNOWN', 'UNKNOWN', 'XX', '00000', 'UNKNOWN');


-- -----------------------------------------------------------------------------
-- DIMENSION: dim_product
-- Grain: One row = one unique product (product_id)
-- SCD Type: 1 (overwrite) -- product attributes treated as current state
-- Source: trusted_zone.stg_products + trusted_zone.stg_category_translation
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE refined_zone.dim_product (

    -- Surrogate key
    product_key                 NUMBER          NOT NULL AUTOINCREMENT START 1 INCREMENT 1,

    -- Natural key
    product_id                  VARCHAR(50)     NOT NULL,   -- Original product identifier from Olist

    -- Category attributes (enriched with English translation)
    product_category_name       VARCHAR(100),               -- Category in Portuguese (nullable: some products uncategorized)
    product_category_english    VARCHAR(100),               -- Category in English (from translation table)

    -- Content richness attributes (proxies for listing quality)
    product_name_length         INTEGER,                    -- Character count of product name
    product_description_length  INTEGER,                    -- Character count of product description
    product_photos_qty          INTEGER,                    -- Number of product photos in listing

    -- Physical dimensions (used in freight calculation)
    product_weight_g            INTEGER,                    -- Weight in grams
    product_length_cm           INTEGER,                    -- Length in centimeters
    product_height_cm           INTEGER,                    -- Height in centimeters
    product_width_cm            INTEGER,                    -- Width in centimeters

    -- Metadata
    _loaded_at                  TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    _source                     VARCHAR(50)     NOT NULL DEFAULT 'olist_products',

    CONSTRAINT dim_product_pk PRIMARY KEY (product_key),
    CONSTRAINT dim_product_nk UNIQUE (product_id)
)
COMMENT = 'Product dimension. Grain: one unique product. SCD Type 1. Enriched with EN category translation.';

COMMENT ON COLUMN refined_zone.dim_product.product_key IS 'Surrogate key. System-generated. Used as FK in fact tables.';
COMMENT ON COLUMN refined_zone.dim_product.product_id IS 'Natural key. Original anonymized product identifier from Olist dataset.';
COMMENT ON COLUMN refined_zone.dim_product.product_category_name IS 'Category in Portuguese. NULL if product has no category in source.';
COMMENT ON COLUMN refined_zone.dim_product.product_category_english IS 'Category translated to English via product_category_name_translation table.';
COMMENT ON COLUMN refined_zone.dim_product.product_name_length IS 'Proxy metric for listing name richness. Longer names typically more descriptive.';
COMMENT ON COLUMN refined_zone.dim_product.product_photos_qty IS 'Number of photos in product listing. Higher values correlate with better conversion.';

-- Sentinel row
INSERT INTO refined_zone.dim_product
    (product_key, product_id, product_category_name, product_category_english)
OVERWRITE
VALUES
    (-1, 'UNKNOWN', 'UNKNOWN', 'UNKNOWN');


-- -----------------------------------------------------------------------------
-- DIMENSION: dim_seller
-- Grain: One row = one unique seller (seller_id)
-- SCD Type: 1 (overwrite)
-- Source: trusted_zone.stg_sellers + trusted_zone.stg_geolocation
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE refined_zone.dim_seller (

    -- Surrogate key
    seller_key          NUMBER          NOT NULL AUTOINCREMENT START 1 INCREMENT 1,

    -- Natural key
    seller_id           VARCHAR(50)     NOT NULL,   -- Original seller identifier from Olist

    -- Location attributes
    seller_city         VARCHAR(100)    NOT NULL,   -- City where seller is based
    seller_state        VARCHAR(5)      NOT NULL,   -- Brazilian state abbreviation
    seller_zip_code     VARCHAR(10)     NOT NULL,   -- 5-digit ZIP prefix of seller location
    seller_region       VARCHAR(20),                -- Macro-region derived from state

    -- Metadata
    _loaded_at          TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    _source             VARCHAR(50)     NOT NULL DEFAULT 'olist_sellers',

    CONSTRAINT dim_seller_pk PRIMARY KEY (seller_key),
    CONSTRAINT dim_seller_nk UNIQUE (seller_id)
)
COMMENT = 'Seller dimension. Grain: one unique seller. SCD Type 1. Location enriched with region.';

COMMENT ON COLUMN refined_zone.dim_seller.seller_key IS 'Surrogate key. System-generated. Used as FK in fact_orders.';
COMMENT ON COLUMN refined_zone.dim_seller.seller_id IS 'Natural key. Original anonymized seller identifier from Olist dataset.';
COMMENT ON COLUMN refined_zone.dim_seller.seller_region IS 'Brazilian macro-region: Norte, Nordeste, Centro-Oeste, Sudeste, Sul. Derived from seller_state.';

-- Sentinel row
INSERT INTO refined_zone.dim_seller
    (seller_key, seller_id, seller_city, seller_state, seller_zip_code)
OVERWRITE
VALUES
    (-1, 'UNKNOWN', 'UNKNOWN', 'XX', '00000');


-- -----------------------------------------------------------------------------
-- DIMENSION: dim_geography
-- Grain: One row = one unique ZIP code prefix (after deduplication)
-- SCD Type: 0 (fixed reference table -- geography does not change)
-- Source: trusted_zone.stg_geolocation (deduplicated by zip_code_prefix)
-- Note: Raw source has multiple lat/lng per ZIP; we use centroid (AVG)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE refined_zone.dim_geography (

    -- Surrogate key
    geography_key       NUMBER          NOT NULL AUTOINCREMENT START 1 INCREMENT 1,

    -- Natural key
    zip_code            VARCHAR(10)     NOT NULL,   -- 5-digit ZIP prefix (Brazilian CEP prefix)

    -- Location attributes
    city                VARCHAR(100)    NOT NULL,   -- City associated with ZIP prefix
    state               VARCHAR(5)      NOT NULL,   -- Brazilian state abbreviation
    region              VARCHAR(20),                -- Macro-region (Norte, Nordeste, Centro-Oeste, Sudeste, Sul)

    -- Geospatial coordinates (centroid of ZIP prefix area)
    latitude            DECIMAL(12, 8),             -- Centroid latitude (-90 to 90). NULL if coordinates unavailable.
    longitude           DECIMAL(12, 8),             -- Centroid longitude (-180 to 180). NULL if coordinates unavailable.

    -- Metadata
    _loaded_at          TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    _source             VARCHAR(50)     NOT NULL DEFAULT 'olist_geolocation',

    CONSTRAINT dim_geography_pk PRIMARY KEY (geography_key),
    CONSTRAINT dim_geography_nk UNIQUE (zip_code)
)
COMMENT = 'Geography dimension. Grain: one ZIP prefix (deduplicated centroid). Shared by customer and seller geolocation.';

COMMENT ON COLUMN refined_zone.dim_geography.geography_key IS 'Surrogate key. System-generated. Used as FK in fact_orders.';
COMMENT ON COLUMN refined_zone.dim_geography.zip_code IS 'Natural key. 5-digit Brazilian CEP prefix. Deduplicated from olist_geolocation.';
COMMENT ON COLUMN refined_zone.dim_geography.latitude IS 'Centroid latitude computed as AVG of all coordinates for this ZIP prefix in source data.';
COMMENT ON COLUMN refined_zone.dim_geography.longitude IS 'Centroid longitude computed as AVG of all coordinates for this ZIP prefix in source data.';
COMMENT ON COLUMN refined_zone.dim_geography.region IS 'Macro-region classification: Norte, Nordeste, Centro-Oeste, Sudeste, Sul.';

-- Sentinel row
INSERT INTO refined_zone.dim_geography
    (geography_key, zip_code, city, state)
OVERWRITE
VALUES
    (-1, '00000', 'UNKNOWN', 'XX');


-- =============================================================================
-- SECTION 5: FACT TABLE -- fact_orders
-- =============================================================================
-- Grain: One row = one order item (one product sold in one order by one seller)
-- This is the most atomic grain available in the Olist dataset.
-- Measures: price, freight_value, payment_value (all additive)
-- Degenerate dimensions: order_id (no separate dim table needed)
-- FKs are documented as comments -- Snowflake does not enforce referential integrity
-- =============================================================================

CREATE OR REPLACE TABLE refined_zone.fact_orders (

    -- Surrogate primary key
    order_item_key          NUMBER          NOT NULL AUTOINCREMENT START 1 INCREMENT 1,  -- System PK

    -- Degenerate dimensions (dimension attributes stored directly in fact)
    order_id                VARCHAR(50)     NOT NULL,   -- Degenerate dim: order identifier (no separate dim table)
    order_item_sequence     INTEGER         NOT NULL,   -- Item sequence within the order (1, 2, 3...)

    -- Foreign keys to dimensions
    -- FK: refined_zone.dim_customer (customer_key)
    customer_key            NUMBER          NOT NULL DEFAULT -1,

    -- FK: refined_zone.dim_product (product_key)
    product_key             NUMBER          NOT NULL DEFAULT -1,

    -- FK: refined_zone.dim_seller (seller_key)
    seller_key              NUMBER          NOT NULL DEFAULT -1,

    -- FK: refined_zone.dim_date (date_key) -- date of purchase
    date_key                INTEGER         NOT NULL DEFAULT -1,

    -- FK: refined_zone.dim_geography (geography_key) -- customer location at time of order
    geography_key           NUMBER          NOT NULL DEFAULT -1,

    -- Descriptive fact attributes (low-cardinality, not worth separate dim tables)
    payment_type            VARCHAR(20),                -- Primary payment method for the order (credit_card, boleto, voucher, debit_card)
    order_status            VARCHAR(20)     NOT NULL,   -- Final status: delivered, canceled, shipped, processing, etc.

    -- Additive measures (can be SUM-ed across all dimensions)
    price                   DECIMAL(12, 2)  NOT NULL,   -- Unit price of the product at time of purchase
    freight_value           DECIMAL(12, 2)  NOT NULL,   -- Freight cost attributed to this item
    payment_value           DECIMAL(12, 2),             -- Payment amount attributed to this item (proportional to item price)

    -- Semi-additive measure (AVG makes sense, SUM does not)
    payment_installments    INTEGER,                    -- Number of installments for the order payment

    -- Metadata
    _loaded_at              TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    _source                 VARCHAR(50)     NOT NULL DEFAULT 'olist_order_items+payments',

    CONSTRAINT fact_orders_pk PRIMARY KEY (order_item_key)

    -- FK references (informational -- not enforced by Snowflake):
    -- REFERENCES refined_zone.dim_customer(customer_key)
    -- REFERENCES refined_zone.dim_product(product_key)
    -- REFERENCES refined_zone.dim_seller(seller_key)
    -- REFERENCES refined_zone.dim_date(date_key)
    -- REFERENCES refined_zone.dim_geography(geography_key)
)
CLUSTER BY (date_key, customer_key)
COMMENT = 'Fact table for sales analysis. Grain: one order item. Additive measures: price, freight_value, payment_value.';

COMMENT ON COLUMN refined_zone.fact_orders.order_item_key IS 'Surrogate PK. System-generated AUTOINCREMENT. Uniquely identifies each order item record.';
COMMENT ON COLUMN refined_zone.fact_orders.order_id IS 'Degenerate dimension. Original order ID preserved in fact. Enables order-level aggregation without separate dim table.';
COMMENT ON COLUMN refined_zone.fact_orders.order_item_sequence IS 'Sequential item number within the order (1 = first item). From olist_order_items.order_item_id.';
COMMENT ON COLUMN refined_zone.fact_orders.customer_key IS 'FK to dim_customer. Default -1 (sentinel row) when customer not found.';
COMMENT ON COLUMN refined_zone.fact_orders.product_key IS 'FK to dim_product. Default -1 (sentinel row) when product not found.';
COMMENT ON COLUMN refined_zone.fact_orders.seller_key IS 'FK to dim_seller. Default -1 (sentinel row) when seller not found.';
COMMENT ON COLUMN refined_zone.fact_orders.date_key IS 'FK to dim_date in YYYYMMDD format. Based on order_purchase_timestamp.';
COMMENT ON COLUMN refined_zone.fact_orders.geography_key IS 'FK to dim_geography. Based on customer ZIP prefix at time of order.';
COMMENT ON COLUMN refined_zone.fact_orders.payment_type IS 'Primary payment method for the order. Derived from payment with payment_sequential=1.';
COMMENT ON COLUMN refined_zone.fact_orders.price IS 'Additive measure. Unit price of the product. Source: olist_order_items.price.';
COMMENT ON COLUMN refined_zone.fact_orders.freight_value IS 'Additive measure. Freight cost per item. Source: olist_order_items.freight_value.';
COMMENT ON COLUMN refined_zone.fact_orders.payment_value IS 'Additive measure. Payment value proportionally attributed to this item based on price ratio.';
COMMENT ON COLUMN refined_zone.fact_orders.payment_installments IS 'Semi-additive. Number of installments. Use AVG() for analysis, not SUM().';


-- =============================================================================
-- SECTION 6: FACT TABLE -- fact_reviews
-- =============================================================================
-- Grain: One row = one customer review per order
-- Note: Not all orders have reviews (~50% coverage). This is documented.
-- Degenerate dimensions: review_id, order_id
-- FKs: dim_customer, dim_product (primary product of the order), dim_date
-- =============================================================================

CREATE OR REPLACE TABLE refined_zone.fact_reviews (

    -- Surrogate primary key
    review_key              NUMBER          NOT NULL AUTOINCREMENT START 1 INCREMENT 1,  -- System PK

    -- Degenerate dimensions
    review_id               VARCHAR(50)     NOT NULL,   -- Degenerate dim: original review identifier
    order_id                VARCHAR(50)     NOT NULL,   -- Degenerate dim: order being reviewed (links to fact_orders for cross-fact analysis)

    -- Foreign keys to dimensions
    -- FK: refined_zone.dim_customer (customer_key)
    customer_key            NUMBER          NOT NULL DEFAULT -1,

    -- FK: refined_zone.dim_product (product_key) -- primary product of the reviewed order
    product_key             NUMBER          NOT NULL DEFAULT -1,

    -- FK: refined_zone.dim_date (date_key) -- date the customer submitted the review
    date_key                INTEGER         NOT NULL DEFAULT -1,

    -- Measures
    review_score            INTEGER         NOT NULL,   -- Additive (for AVG): rating from 1 (worst) to 5 (best)
    response_time_hours     DECIMAL(10, 2), -- Additive: hours elapsed between review_creation_date and review_answer_timestamp

    -- Textual attributes (stored in fact for direct access without JOIN)
    review_comment_title    VARCHAR(200),               -- Optional title provided by the customer
    review_comment_message  VARCHAR(2000),              -- Optional free-text review body

    -- Temporal attribute
    review_answer_timestamp TIMESTAMP_NTZ,              -- Exact moment the customer submitted the review response

    -- Metadata
    _loaded_at              TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    _source                 VARCHAR(50)     NOT NULL DEFAULT 'olist_order_reviews',

    CONSTRAINT fact_reviews_pk PRIMARY KEY (review_key),
    CONSTRAINT fact_reviews_review_nk UNIQUE (review_id)

    -- FK references (informational -- not enforced by Snowflake):
    -- REFERENCES refined_zone.dim_customer(customer_key)
    -- REFERENCES refined_zone.dim_product(product_key)
    -- REFERENCES refined_zone.dim_date(date_key)
)
COMMENT = 'Fact table for customer satisfaction analysis. Grain: one review per order. ~50% order coverage.';

COMMENT ON COLUMN refined_zone.fact_reviews.review_key IS 'Surrogate PK. System-generated AUTOINCREMENT.';
COMMENT ON COLUMN refined_zone.fact_reviews.review_id IS 'Degenerate dimension. Original review UUID from Olist. Unique per review.';
COMMENT ON COLUMN refined_zone.fact_reviews.order_id IS 'Degenerate dimension. Links this review to the corresponding order. Use to JOIN with fact_orders for combined analysis.';
COMMENT ON COLUMN refined_zone.fact_reviews.customer_key IS 'FK to dim_customer. Default -1 when customer not resolvable.';
COMMENT ON COLUMN refined_zone.fact_reviews.product_key IS 'FK to dim_product. Represents the primary product of the reviewed order (first item by order_item_sequence).';
COMMENT ON COLUMN refined_zone.fact_reviews.date_key IS 'FK to dim_date. Based on review_answer_timestamp date (when customer responded).';
COMMENT ON COLUMN refined_zone.fact_reviews.review_score IS 'Additive-for-AVG measure. Integer 1-5. AVG(review_score) is a valid NPS-proxy metric.';
COMMENT ON COLUMN refined_zone.fact_reviews.response_time_hours IS 'Additive measure. DATEDIFF(hours, review_creation_date, review_answer_timestamp). NULL if customer never responded.';
COMMENT ON COLUMN refined_zone.fact_reviews.review_comment_message IS 'Free text. Source for NLP/sentiment analysis pipelines.';


-- =============================================================================
-- SECTION 7: SAMPLE ANALYTICAL QUERIES
-- =============================================================================
-- Reference queries to validate model correctness and demonstrate grain behavior.

-- Query 1: Monthly Revenue by Product Category (fact_orders x dim_date x dim_product)
-- Validates: date_key JOIN, product_key JOIN, additive measure SUM
/*
SELECT
    d.year,
    d.month,
    d.month_name,
    p.product_category_english,
    COUNT(DISTINCT fo.order_id)     AS total_orders,
    COUNT(fo.order_item_key)        AS total_items,
    SUM(fo.price)                   AS gross_revenue,
    SUM(fo.freight_value)           AS total_freight,
    SUM(fo.price + fo.freight_value) AS total_gmv
FROM refined_zone.fact_orders fo
    JOIN refined_zone.dim_date d
        ON fo.date_key = d.date_key
    JOIN refined_zone.dim_product p
        ON fo.product_key = p.product_key
WHERE d.year = 2017
  AND fo.order_status = 'delivered'
  AND fo.product_key != -1
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2, SUM(fo.price) DESC;
*/

-- Query 2: Average Review Score by Seller State (fact_reviews x dim_customer x fact_orders x dim_seller)
-- Validates: cross-fact JOIN via order_id degenerate dimension
/*
SELECT
    s.seller_state,
    COUNT(fr.review_key)        AS total_reviews,
    AVG(fr.review_score)        AS avg_score,
    AVG(fr.response_time_hours) AS avg_response_hours
FROM refined_zone.fact_reviews fr
    JOIN refined_zone.dim_customer c
        ON fr.customer_key = c.customer_key
    JOIN refined_zone.fact_orders fo
        ON fr.order_id = fo.order_id
    JOIN refined_zone.dim_seller s
        ON fo.seller_key = s.seller_key
WHERE fr.review_score IS NOT NULL
  AND fr.customer_key != -1
GROUP BY 1
ORDER BY AVG(fr.review_score) DESC;
*/

-- Query 3: Weekend vs Weekday Sales Distribution (fact_orders x dim_date)
-- Validates: boolean dimension attribute filter
/*
SELECT
    d.is_weekend,
    d.day_of_week_name,
    COUNT(DISTINCT fo.order_id)     AS total_orders,
    SUM(fo.price)                   AS gross_revenue,
    AVG(fo.price)                   AS avg_order_value
FROM refined_zone.fact_orders fo
    JOIN refined_zone.dim_date d
        ON fo.date_key = d.date_key
WHERE fo.order_status = 'delivered'
GROUP BY 1, 2
ORDER BY 1, SUM(fo.price) DESC;
*/


-- =============================================================================
-- END OF FILE
-- Tables created: 9 (raw_zone) + 9 (trusted_zone) + 7 (refined_zone) = 25 total
-- Star schema: 5 dimensions + 2 facts
-- Sentinel rows: inserted for all 4 non-date dimensions (key = -1)
-- CLUSTER BY: fact_orders clustered on (date_key, customer_key)
-- =============================================================================
