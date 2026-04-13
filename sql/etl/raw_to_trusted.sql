-- =============================================================================
-- ETL: Raw Zone -> Trusted Zone
-- Transformacoes de limpeza, tipagem e deduplicacao
-- Dialeto: Snowflake SQL
-- Projeto: Case Tecnico Dadosfera - E-commerce Olist
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. TRUSTED_ORDERS
-- Pedidos limpos com datas convertidas e status validado
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE TRUSTED_ZONE.TRUSTED_ORDERS AS
WITH raw_orders AS (
    SELECT
        order_id,
        customer_id,
        UPPER(TRIM(order_status)) AS order_status,
        TRY_TO_TIMESTAMP_NTZ(order_purchase_timestamp) AS order_purchase_timestamp,
        TRY_TO_TIMESTAMP_NTZ(order_approved_at) AS order_approved_at,
        TRY_TO_TIMESTAMP_NTZ(order_delivered_carrier_date) AS order_delivered_carrier_date,
        TRY_TO_TIMESTAMP_NTZ(order_delivered_customer_date) AS order_delivered_customer_date,
        TRY_TO_TIMESTAMP_NTZ(order_estimated_delivery_date) AS order_estimated_delivery_date,
        ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY order_purchase_timestamp DESC) AS rn
    FROM RAW_ZONE.OLIST_ORDERS_DATASET
    WHERE order_id IS NOT NULL
      AND customer_id IS NOT NULL
)
SELECT
    order_id,
    customer_id,
    order_status,
    order_purchase_timestamp,
    order_approved_at,
    order_delivered_carrier_date,
    order_delivered_customer_date,
    order_estimated_delivery_date,
    -- Campos calculados
    DATEDIFF('day', order_purchase_timestamp, order_delivered_customer_date) AS delivery_days,
    DATEDIFF('day', order_estimated_delivery_date, order_delivered_customer_date) AS delivery_delay_days,
    CASE
        WHEN order_delivered_customer_date <= order_estimated_delivery_date THEN 'ON_TIME'
        WHEN order_delivered_customer_date > order_estimated_delivery_date THEN 'LATE'
        ELSE 'PENDING'
    END AS delivery_status,
    CURRENT_TIMESTAMP() AS loaded_at
FROM raw_orders
WHERE rn = 1;  -- Deduplicacao por order_id

-- -----------------------------------------------------------------------------
-- 2. TRUSTED_ORDER_ITEMS
-- Itens de pedido com precos validados
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE TRUSTED_ZONE.TRUSTED_ORDER_ITEMS AS
SELECT
    oi.order_id,
    oi.order_item_id::INTEGER AS order_item_id,
    oi.product_id,
    oi.seller_id,
    TRY_TO_TIMESTAMP_NTZ(oi.shipping_limit_date) AS shipping_limit_date,
    ROUND(TRY_TO_DECIMAL(oi.price, 10, 2), 2) AS price,
    ROUND(TRY_TO_DECIMAL(oi.freight_value, 10, 2), 2) AS freight_value,
    ROUND(TRY_TO_DECIMAL(oi.price, 10, 2) + TRY_TO_DECIMAL(oi.freight_value, 10, 2), 2) AS total_item_value,
    CURRENT_TIMESTAMP() AS loaded_at
FROM RAW_ZONE.OLIST_ORDER_ITEMS_DATASET oi
WHERE oi.order_id IS NOT NULL
  AND oi.product_id IS NOT NULL
  AND TRY_TO_DECIMAL(oi.price, 10, 2) > 0;

-- -----------------------------------------------------------------------------
-- 3. TRUSTED_PAYMENTS
-- Pagamentos com tipos padronizados
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE TRUSTED_ZONE.TRUSTED_PAYMENTS AS
SELECT
    order_id,
    payment_sequential::INTEGER AS payment_sequential,
    UPPER(TRIM(payment_type)) AS payment_type,
    payment_installments::INTEGER AS payment_installments,
    ROUND(TRY_TO_DECIMAL(payment_value, 10, 2), 2) AS payment_value,
    CURRENT_TIMESTAMP() AS loaded_at
FROM RAW_ZONE.OLIST_ORDER_PAYMENTS_DATASET
WHERE order_id IS NOT NULL
  AND TRY_TO_DECIMAL(payment_value, 10, 2) > 0;

-- -----------------------------------------------------------------------------
-- 4. TRUSTED_REVIEWS
-- Avaliacoes com scores validados e textos limpos
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE TRUSTED_ZONE.TRUSTED_REVIEWS AS
SELECT
    review_id,
    order_id,
    review_score::INTEGER AS review_score,
    TRIM(COALESCE(review_comment_title, '')) AS review_comment_title,
    TRIM(COALESCE(review_comment_message, '')) AS review_comment_message,
    TRY_TO_TIMESTAMP_NTZ(review_creation_date) AS review_creation_date,
    TRY_TO_TIMESTAMP_NTZ(review_answer_timestamp) AS review_answer_timestamp,
    DATEDIFF('hour',
        TRY_TO_TIMESTAMP_NTZ(review_creation_date),
        TRY_TO_TIMESTAMP_NTZ(review_answer_timestamp)
    ) AS response_time_hours,
    CASE
        WHEN review_score::INTEGER >= 4 THEN 'POSITIVE'
        WHEN review_score::INTEGER = 3 THEN 'NEUTRAL'
        ELSE 'NEGATIVE'
    END AS sentiment_category,
    CURRENT_TIMESTAMP() AS loaded_at
FROM RAW_ZONE.OLIST_ORDER_REVIEWS_DATASET
WHERE review_id IS NOT NULL
  AND order_id IS NOT NULL
  AND review_score::INTEGER BETWEEN 1 AND 5;

-- -----------------------------------------------------------------------------
-- 5. TRUSTED_CUSTOMERS
-- Clientes deduplicados por customer_unique_id
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE TRUSTED_ZONE.TRUSTED_CUSTOMERS AS
WITH ranked_customers AS (
    SELECT
        customer_id,
        customer_unique_id,
        LPAD(customer_zip_code_prefix::VARCHAR, 5, '0') AS customer_zip_code_prefix,
        INITCAP(TRIM(customer_city)) AS customer_city,
        UPPER(TRIM(customer_state)) AS customer_state,
        ROW_NUMBER() OVER (
            PARTITION BY customer_unique_id
            ORDER BY customer_id
        ) AS rn
    FROM RAW_ZONE.OLIST_CUSTOMERS_DATASET
    WHERE customer_id IS NOT NULL
)
SELECT
    customer_id,
    customer_unique_id,
    customer_zip_code_prefix,
    customer_city,
    customer_state,
    CASE customer_state
        WHEN 'SP' THEN 'Sudeste'
        WHEN 'RJ' THEN 'Sudeste'
        WHEN 'MG' THEN 'Sudeste'
        WHEN 'ES' THEN 'Sudeste'
        WHEN 'PR' THEN 'Sul'
        WHEN 'SC' THEN 'Sul'
        WHEN 'RS' THEN 'Sul'
        WHEN 'BA' THEN 'Nordeste'
        WHEN 'PE' THEN 'Nordeste'
        WHEN 'CE' THEN 'Nordeste'
        WHEN 'MA' THEN 'Nordeste'
        WHEN 'PB' THEN 'Nordeste'
        WHEN 'PI' THEN 'Nordeste'
        WHEN 'RN' THEN 'Nordeste'
        WHEN 'AL' THEN 'Nordeste'
        WHEN 'SE' THEN 'Nordeste'
        WHEN 'DF' THEN 'Centro-Oeste'
        WHEN 'GO' THEN 'Centro-Oeste'
        WHEN 'MT' THEN 'Centro-Oeste'
        WHEN 'MS' THEN 'Centro-Oeste'
        WHEN 'AM' THEN 'Norte'
        WHEN 'PA' THEN 'Norte'
        WHEN 'AC' THEN 'Norte'
        WHEN 'AP' THEN 'Norte'
        WHEN 'RO' THEN 'Norte'
        WHEN 'RR' THEN 'Norte'
        WHEN 'TO' THEN 'Norte'
        ELSE 'Desconhecido'
    END AS customer_region,
    CURRENT_TIMESTAMP() AS loaded_at
FROM ranked_customers
WHERE rn = 1;

-- -----------------------------------------------------------------------------
-- 6. TRUSTED_PRODUCTS
-- Produtos com categorias traduzidas e metricas limpas
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE TRUSTED_ZONE.TRUSTED_PRODUCTS AS
SELECT
    p.product_id,
    COALESCE(TRIM(p.product_category_name), 'sem_categoria') AS product_category_name,
    COALESCE(TRIM(t.product_category_name_english), 'uncategorized') AS product_category_english,
    COALESCE(p.product_name_lenght::INTEGER, 0) AS product_name_length,
    COALESCE(p.product_description_lenght::INTEGER, 0) AS product_description_length,
    COALESCE(p.product_photos_qty::INTEGER, 0) AS product_photos_qty,
    COALESCE(p.product_weight_g::FLOAT, 0) AS product_weight_g,
    COALESCE(p.product_length_cm::FLOAT, 0) AS product_length_cm,
    COALESCE(p.product_height_cm::FLOAT, 0) AS product_height_cm,
    COALESCE(p.product_width_cm::FLOAT, 0) AS product_width_cm,
    -- Volume calculado (cm3)
    ROUND(
        COALESCE(p.product_length_cm::FLOAT, 0) *
        COALESCE(p.product_height_cm::FLOAT, 0) *
        COALESCE(p.product_width_cm::FLOAT, 0), 2
    ) AS product_volume_cm3,
    CURRENT_TIMESTAMP() AS loaded_at
FROM RAW_ZONE.OLIST_PRODUCTS_DATASET p
LEFT JOIN RAW_ZONE.PRODUCT_CATEGORY_NAME_TRANSLATION t
    ON TRIM(p.product_category_name) = TRIM(t.product_category_name)
WHERE p.product_id IS NOT NULL;

-- -----------------------------------------------------------------------------
-- 7. TRUSTED_SELLERS
-- Vendedores com localizacao padronizada
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE TRUSTED_ZONE.TRUSTED_SELLERS AS
SELECT
    seller_id,
    LPAD(seller_zip_code_prefix::VARCHAR, 5, '0') AS seller_zip_code_prefix,
    INITCAP(TRIM(seller_city)) AS seller_city,
    UPPER(TRIM(seller_state)) AS seller_state,
    CURRENT_TIMESTAMP() AS loaded_at
FROM RAW_ZONE.OLIST_SELLERS_DATASET
WHERE seller_id IS NOT NULL;

-- -----------------------------------------------------------------------------
-- 8. TRUSTED_GEOLOCATION
-- Geolocalizacao deduplicada por CEP (media das coordenadas)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE TRUSTED_ZONE.TRUSTED_GEOLOCATION AS
SELECT
    LPAD(geolocation_zip_code_prefix::VARCHAR, 5, '0') AS geolocation_zip_code_prefix,
    ROUND(AVG(geolocation_lat::FLOAT), 6) AS geolocation_lat,
    ROUND(AVG(geolocation_lng::FLOAT), 6) AS geolocation_lng,
    MODE(INITCAP(TRIM(geolocation_city))) AS geolocation_city,
    MODE(UPPER(TRIM(geolocation_state))) AS geolocation_state,
    COUNT(*) AS registro_count,
    CURRENT_TIMESTAMP() AS loaded_at
FROM RAW_ZONE.OLIST_GEOLOCATION_DATASET
WHERE geolocation_zip_code_prefix IS NOT NULL
  AND geolocation_lat::FLOAT BETWEEN -35.0 AND 6.0   -- Limites do Brasil
  AND geolocation_lng::FLOAT BETWEEN -74.0 AND -34.0
GROUP BY LPAD(geolocation_zip_code_prefix::VARCHAR, 5, '0');
