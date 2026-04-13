-- =============================================================================
-- ETL: Trusted Zone -> Refined Zone (Star Schema)
-- Criacao das dimensoes e tabelas fato do modelo Kimball
-- Dialeto: Snowflake SQL
-- Projeto: Case Tecnico Dadosfera - E-commerce Olist
-- =============================================================================

-- -----------------------------------------------------------------------------
-- DIMENSAO: DIM_DATE
-- Calendario completo cobrindo o periodo dos dados (2016-2018)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE REFINED_ZONE.DIM_DATE AS
WITH date_spine AS (
    SELECT
        DATEADD('day', seq4(), '2016-01-01'::DATE) AS full_date
    FROM TABLE(GENERATOR(ROWCOUNT => 1096))  -- ~3 anos
)
SELECT
    TO_CHAR(full_date, 'YYYYMMDD')::INTEGER AS date_key,
    full_date,
    YEAR(full_date) AS year,
    QUARTER(full_date) AS quarter,
    MONTH(full_date) AS month,
    CASE MONTH(full_date)
        WHEN 1 THEN 'Janeiro'
        WHEN 2 THEN 'Fevereiro'
        WHEN 3 THEN 'Marco'
        WHEN 4 THEN 'Abril'
        WHEN 5 THEN 'Maio'
        WHEN 6 THEN 'Junho'
        WHEN 7 THEN 'Julho'
        WHEN 8 THEN 'Agosto'
        WHEN 9 THEN 'Setembro'
        WHEN 10 THEN 'Outubro'
        WHEN 11 THEN 'Novembro'
        WHEN 12 THEN 'Dezembro'
    END AS month_name,
    WEEKOFYEAR(full_date) AS week_of_year,
    DAYOFWEEK(full_date) AS day_of_week,
    CASE DAYOFWEEK(full_date)
        WHEN 0 THEN 'Domingo'
        WHEN 1 THEN 'Segunda'
        WHEN 2 THEN 'Terca'
        WHEN 3 THEN 'Quarta'
        WHEN 4 THEN 'Quinta'
        WHEN 5 THEN 'Sexta'
        WHEN 6 THEN 'Sabado'
    END AS day_of_week_name,
    CASE WHEN DAYOFWEEK(full_date) IN (0, 6) THEN TRUE ELSE FALSE END AS is_weekend,
    TO_CHAR(full_date, 'YYYY-MM') AS year_month,
    TO_CHAR(full_date, 'YYYY-Q') AS year_quarter
FROM date_spine
WHERE full_date <= '2018-12-31';

-- -----------------------------------------------------------------------------
-- DIMENSAO: DIM_CUSTOMER
-- Clientes unicos com localizacao e geolocalizacao
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE REFINED_ZONE.DIM_CUSTOMER AS
SELECT
    ROW_NUMBER() OVER (ORDER BY c.customer_unique_id) AS customer_key,
    c.customer_id,
    c.customer_unique_id,
    c.customer_zip_code_prefix,
    c.customer_city,
    c.customer_state,
    c.customer_region,
    g.geolocation_lat AS customer_lat,
    g.geolocation_lng AS customer_lng,
    CURRENT_TIMESTAMP() AS loaded_at
FROM TRUSTED_ZONE.TRUSTED_CUSTOMERS c
LEFT JOIN TRUSTED_ZONE.TRUSTED_GEOLOCATION g
    ON c.customer_zip_code_prefix = g.geolocation_zip_code_prefix;

-- -----------------------------------------------------------------------------
-- DIMENSAO: DIM_PRODUCT
-- Produtos com categorias traduzidas e metricas fisicas
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE REFINED_ZONE.DIM_PRODUCT AS
SELECT
    ROW_NUMBER() OVER (ORDER BY p.product_id) AS product_key,
    p.product_id,
    p.product_category_name,
    p.product_category_english,
    p.product_name_length,
    p.product_description_length,
    p.product_photos_qty,
    p.product_weight_g,
    p.product_length_cm,
    p.product_height_cm,
    p.product_width_cm,
    p.product_volume_cm3,
    -- Faixas de peso para analise
    CASE
        WHEN p.product_weight_g <= 500 THEN 'Leve (ate 500g)'
        WHEN p.product_weight_g <= 2000 THEN 'Medio (500g-2kg)'
        WHEN p.product_weight_g <= 10000 THEN 'Pesado (2kg-10kg)'
        ELSE 'Muito Pesado (10kg+)'
    END AS weight_category,
    CURRENT_TIMESTAMP() AS loaded_at
FROM TRUSTED_ZONE.TRUSTED_PRODUCTS p;

-- -----------------------------------------------------------------------------
-- DIMENSAO: DIM_SELLER
-- Vendedores com localizacao
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE REFINED_ZONE.DIM_SELLER AS
SELECT
    ROW_NUMBER() OVER (ORDER BY s.seller_id) AS seller_key,
    s.seller_id,
    s.seller_zip_code_prefix,
    s.seller_city,
    s.seller_state,
    g.geolocation_lat AS seller_lat,
    g.geolocation_lng AS seller_lng,
    CURRENT_TIMESTAMP() AS loaded_at
FROM TRUSTED_ZONE.TRUSTED_SELLERS s
LEFT JOIN TRUSTED_ZONE.TRUSTED_GEOLOCATION g
    ON s.seller_zip_code_prefix = g.geolocation_zip_code_prefix;

-- -----------------------------------------------------------------------------
-- DIMENSAO: DIM_GEOGRAPHY
-- Localizacoes unicas (CEP como granularidade)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE REFINED_ZONE.DIM_GEOGRAPHY AS
SELECT
    ROW_NUMBER() OVER (ORDER BY geolocation_zip_code_prefix) AS geography_key,
    geolocation_zip_code_prefix AS zip_code,
    geolocation_city AS city,
    geolocation_state AS state,
    geolocation_lat AS latitude,
    geolocation_lng AS longitude,
    CASE geolocation_state
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
        ELSE 'Norte'
    END AS region,
    CURRENT_TIMESTAMP() AS loaded_at
FROM TRUSTED_ZONE.TRUSTED_GEOLOCATION;

-- -----------------------------------------------------------------------------
-- FATO: FACT_ORDERS
-- Visao 1 - Analise de Vendas
-- Grao: 1 linha por item de pedido
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE REFINED_ZONE.FACT_ORDERS AS
SELECT
    oi.order_id || '-' || oi.order_item_id::VARCHAR AS order_item_key,
    o.order_id,
    oi.order_item_id,

    -- Foreign Keys para dimensoes
    dc.customer_key,
    dp.product_key,
    ds.seller_key,
    TO_CHAR(o.order_purchase_timestamp, 'YYYYMMDD')::INTEGER AS purchase_date_key,
    TO_CHAR(o.order_approved_at, 'YYYYMMDD')::INTEGER AS approved_date_key,
    TO_CHAR(o.order_delivered_customer_date, 'YYYYMMDD')::INTEGER AS delivery_date_key,

    -- Atributos do pedido
    o.order_status,
    o.delivery_status,

    -- Metricas de pagamento
    pay.payment_type,
    pay.payment_installments,

    -- Metricas financeiras (fatos aditivos)
    oi.price,
    oi.freight_value,
    oi.total_item_value,
    pay.payment_value,

    -- Metricas de tempo (fatos aditivos)
    o.delivery_days,
    o.delivery_delay_days,

    -- Timestamps para referencia
    o.order_purchase_timestamp,
    o.order_approved_at,
    o.order_delivered_carrier_date,
    o.order_delivered_customer_date,
    o.order_estimated_delivery_date,

    CURRENT_TIMESTAMP() AS loaded_at

FROM TRUSTED_ZONE.TRUSTED_ORDERS o
INNER JOIN TRUSTED_ZONE.TRUSTED_ORDER_ITEMS oi
    ON o.order_id = oi.order_id
INNER JOIN REFINED_ZONE.DIM_CUSTOMER dc
    ON o.customer_id = dc.customer_id
INNER JOIN REFINED_ZONE.DIM_PRODUCT dp
    ON oi.product_id = dp.product_id
INNER JOIN REFINED_ZONE.DIM_SELLER ds
    ON oi.seller_id = ds.seller_id
LEFT JOIN (
    -- Pegar o tipo de pagamento principal (maior valor)
    SELECT
        order_id,
        payment_type,
        payment_installments,
        payment_value,
        ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY payment_value DESC) AS rn
    FROM TRUSTED_ZONE.TRUSTED_PAYMENTS
) pay
    ON o.order_id = pay.order_id AND pay.rn = 1;

-- -----------------------------------------------------------------------------
-- FATO: FACT_REVIEWS
-- Visao 2 - Analise de Satisfacao do Cliente
-- Grao: 1 linha por avaliacao
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE REFINED_ZONE.FACT_REVIEWS AS
SELECT
    r.review_id,

    -- Foreign Keys
    dc.customer_key,
    dp.product_key,
    TO_CHAR(r.review_creation_date, 'YYYYMMDD')::INTEGER AS review_date_key,

    -- Referencia ao pedido
    r.order_id,

    -- Metricas de satisfacao
    r.review_score,
    r.sentiment_category,
    r.response_time_hours,

    -- Indicadores booleanos
    CASE WHEN LENGTH(r.review_comment_message) > 0 THEN TRUE ELSE FALSE END AS has_comment,
    LENGTH(r.review_comment_message) AS comment_length,

    -- Texto para analise NLP
    r.review_comment_title,
    r.review_comment_message,

    -- Timestamps
    r.review_creation_date,
    r.review_answer_timestamp,

    CURRENT_TIMESTAMP() AS loaded_at

FROM TRUSTED_ZONE.TRUSTED_REVIEWS r
INNER JOIN TRUSTED_ZONE.TRUSTED_ORDERS o
    ON r.order_id = o.order_id
INNER JOIN REFINED_ZONE.DIM_CUSTOMER dc
    ON o.customer_id = dc.customer_id
LEFT JOIN (
    -- Produto principal do pedido (primeiro item)
    SELECT order_id, product_id,
           ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY order_item_id) AS rn
    FROM TRUSTED_ZONE.TRUSTED_ORDER_ITEMS
) oi ON r.order_id = oi.order_id AND oi.rn = 1
LEFT JOIN REFINED_ZONE.DIM_PRODUCT dp
    ON oi.product_id = dp.product_id;

-- =============================================================================
-- VIEWS ANALITICAS (para consumo direto no Metabase)
-- =============================================================================

-- View consolidada de vendas para dashboards
CREATE OR REPLACE VIEW REFINED_ZONE.VW_SALES_ANALYSIS AS
SELECT
    fo.order_id,
    dd.full_date AS purchase_date,
    dd.year_month,
    dd.month_name,
    dd.year,
    dc.customer_city,
    dc.customer_state,
    dc.customer_region,
    dp.product_category_name,
    dp.product_category_english,
    dp.weight_category,
    ds.seller_city,
    ds.seller_state,
    fo.order_status,
    fo.delivery_status,
    fo.payment_type,
    fo.payment_installments,
    fo.price,
    fo.freight_value,
    fo.total_item_value,
    fo.delivery_days,
    fo.delivery_delay_days
FROM REFINED_ZONE.FACT_ORDERS fo
JOIN REFINED_ZONE.DIM_DATE dd ON fo.purchase_date_key = dd.date_key
JOIN REFINED_ZONE.DIM_CUSTOMER dc ON fo.customer_key = dc.customer_key
JOIN REFINED_ZONE.DIM_PRODUCT dp ON fo.product_key = dp.product_key
JOIN REFINED_ZONE.DIM_SELLER ds ON fo.seller_key = ds.seller_key;

-- View consolidada de satisfacao para dashboards
CREATE OR REPLACE VIEW REFINED_ZONE.VW_SATISFACTION_ANALYSIS AS
SELECT
    fr.review_id,
    fr.order_id,
    dd.full_date AS review_date,
    dd.year_month,
    dd.month_name,
    dd.year,
    dc.customer_city,
    dc.customer_state,
    dc.customer_region,
    dp.product_category_name,
    dp.product_category_english,
    fr.review_score,
    fr.sentiment_category,
    fr.has_comment,
    fr.comment_length,
    fr.response_time_hours,
    fr.review_comment_title,
    fr.review_comment_message
FROM REFINED_ZONE.FACT_REVIEWS fr
JOIN REFINED_ZONE.DIM_DATE dd ON fr.review_date_key = dd.date_key
JOIN REFINED_ZONE.DIM_CUSTOMER dc ON fr.customer_key = dc.customer_key
LEFT JOIN REFINED_ZONE.DIM_PRODUCT dp ON fr.product_key = dp.product_key;
