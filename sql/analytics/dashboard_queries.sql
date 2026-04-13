-- =============================================================================
-- DASHBOARD QUERIES - OLIST BRAZILIAN E-COMMERCE
-- Plataforma: Dadosfera (backend Snowflake)
-- Visualização: Metabase
-- Collection: Leonardo Nunes - 04_2026
-- Schema: RAW_OLIST
-- Autor: Leonardo Nunes
-- Data: Abril 2026
-- =============================================================================


-- =============================================================================
-- QUERY 1 - GRÁFICO DE BARRAS
-- Título: Receita por Categoria de Produto (Top 15)
-- Tipo de gráfico: Bar Chart (Horizontal ou Vertical)
-- Pergunta de negócio: Quais categorias de produto geram mais receita no
--   marketplace? Onde concentrar esforços de crescimento e negociação?
-- =============================================================================

WITH receita_por_categoria AS (
    SELECT
        COALESCE(t.product_category_name_english, p.product_category_name, 'Sem Categoria') AS categoria,
        COUNT(DISTINCT oi.order_id)                                                           AS total_pedidos,
        ROUND(SUM(oi.price), 2)                                                               AS receita_produtos,
        ROUND(SUM(oi.freight_value), 2)                                                       AS receita_frete,
        ROUND(SUM(oi.price + oi.freight_value), 2)                                            AS receita_total,
        ROUND(AVG(oi.price), 2)                                                               AS ticket_medio_produto
    FROM RAW_OLIST.OLIST_ORDER_ITEMS_DATASET    AS oi
    INNER JOIN RAW_OLIST.OLIST_PRODUCTS_DATASET AS p  ON oi.product_id = p.product_id
    LEFT JOIN  RAW_OLIST.PRODUCT_CATEGORY_NAME_TRANSLATION AS t
           ON p.product_category_name = t.product_category_name
    GROUP BY
        COALESCE(t.product_category_name_english, p.product_category_name, 'Sem Categoria')
),

ranking_categorias AS (
    SELECT
        categoria                                                                       AS "Categoria",
        total_pedidos                                                                   AS "Total de Pedidos",
        receita_produtos                                                                AS "Receita de Produtos (R$)",
        receita_frete                                                                   AS "Receita de Frete (R$)",
        receita_total                                                                   AS "Receita Total (R$)",
        ticket_medio_produto                                                            AS "Ticket Médio (R$)",
        ROUND(receita_total / SUM(receita_total) OVER () * 100, 2)                     AS "% da Receita Total",
        ROW_NUMBER() OVER (ORDER BY receita_total DESC)                                 AS ranking
    FROM receita_por_categoria
)

SELECT
    ranking                   AS "Ranking",
    "Categoria",
    "Total de Pedidos",
    "Receita Total (R$)",
    "Ticket Médio (R$)",
    "% da Receita Total"
FROM ranking_categorias
WHERE ranking <= 15
ORDER BY "Receita Total (R$)" DESC;


-- =============================================================================
-- QUERY 2 - GRÁFICO DE LINHAS
-- Título: Evolução Mensal de Vendas (2016–2018)
-- Tipo de gráfico: Line Chart (série temporal)
-- Pergunta de negócio: Como a receita e o volume de pedidos evoluíram ao
--   longo do tempo? Existem sazonalidades ou tendências de crescimento?
-- =============================================================================

WITH pedidos_por_mes AS (
    SELECT
        DATE_TRUNC('MONTH', TO_TIMESTAMP(o.order_purchase_timestamp))   AS mes_ref,
        TO_CHAR(DATE_TRUNC('MONTH', TO_TIMESTAMP(o.order_purchase_timestamp)), 'YYYY-MM') AS ano_mes,
        COUNT(DISTINCT o.order_id)                                       AS total_pedidos,
        COUNT(DISTINCT o.customer_id)                                    AS clientes_unicos,
        ROUND(SUM(oi.price + oi.freight_value), 2)                       AS receita_total,
        ROUND(AVG(oi.price + oi.freight_value), 2)                       AS ticket_medio
    FROM RAW_OLIST.OLIST_ORDERS_DATASET         AS o
    INNER JOIN RAW_OLIST.OLIST_ORDER_ITEMS_DATASET AS oi ON o.order_id = oi.order_id
    WHERE
        o.order_status NOT IN ('canceled', 'unavailable')
        AND o.order_purchase_timestamp IS NOT NULL
    GROUP BY
        DATE_TRUNC('MONTH', TO_TIMESTAMP(o.order_purchase_timestamp)),
        TO_CHAR(DATE_TRUNC('MONTH', TO_TIMESTAMP(o.order_purchase_timestamp)), 'YYYY-MM')
),

serie_com_crescimento AS (
    SELECT
        mes_ref,
        ano_mes                                                                                         AS "Ano-Mês",
        total_pedidos                                                                                   AS "Total de Pedidos",
        clientes_unicos                                                                                 AS "Clientes Únicos",
        receita_total                                                                                   AS "Receita Total (R$)",
        ticket_medio                                                                                    AS "Ticket Médio (R$)",
        LAG(receita_total) OVER (ORDER BY mes_ref)                                                     AS receita_mes_anterior,
        ROUND(
            (receita_total - LAG(receita_total) OVER (ORDER BY mes_ref))
            / NULLIF(LAG(receita_total) OVER (ORDER BY mes_ref), 0) * 100,
            2
        )                                                                                               AS "Crescimento MoM (%)"
    FROM pedidos_por_mes
)

SELECT
    "Ano-Mês",
    "Total de Pedidos",
    "Clientes Únicos",
    "Receita Total (R$)",
    "Ticket Médio (R$)",
    "Crescimento MoM (%)"
FROM serie_com_crescimento
ORDER BY mes_ref ASC;


-- =============================================================================
-- QUERY 3 - GRÁFICO DE PIZZA / ROSCA
-- Título: Distribuição dos Métodos de Pagamento
-- Tipo de gráfico: Pie Chart / Donut Chart
-- Pergunta de negócio: Qual é a preferência de pagamento dos clientes?
--   Qual proporção usa parcelamento (cartão de crédito)?
-- =============================================================================

WITH pagamentos_agrupados AS (
    SELECT
        CASE
            WHEN payment_type = 'credit_card' THEN 'Cartão de Crédito'
            WHEN payment_type = 'boleto'       THEN 'Boleto Bancário'
            WHEN payment_type = 'voucher'      THEN 'Voucher'
            WHEN payment_type = 'debit_card'   THEN 'Cartão de Débito'
            ELSE 'Outros'
        END                              AS metodo_pagamento,
        COUNT(DISTINCT order_id)         AS total_pedidos,
        ROUND(SUM(payment_value), 2)     AS valor_total_pago,
        ROUND(AVG(payment_installments), 1) AS media_parcelas
    FROM RAW_OLIST.OLIST_ORDER_PAYMENTS_DATASET
    GROUP BY payment_type
),

totais AS (
    SELECT SUM(total_pedidos) AS total_geral
    FROM pagamentos_agrupados
)

SELECT
    p.metodo_pagamento                                             AS "Método de Pagamento",
    p.total_pedidos                                               AS "Total de Pedidos",
    ROUND(p.total_pedidos / t.total_geral * 100, 2)              AS "Participação (%)",
    p.valor_total_pago                                            AS "Valor Total Pago (R$)",
    p.media_parcelas                                              AS "Média de Parcelas"
FROM pagamentos_agrupados AS p
CROSS JOIN totais AS t
ORDER BY p.total_pedidos DESC;


-- =============================================================================
-- QUERY 4 - MAPA / GEO CHART
-- Título: Volume de Pedidos por Estado Brasileiro
-- Tipo de gráfico: Map Chart (Choropleth por UF)
-- Pergunta de negócio: Qual é a distribuição geográfica dos pedidos?
--   Quais estados têm maior potencial de crescimento logístico?
-- =============================================================================

WITH pedidos_por_estado AS (
    SELECT
        c.customer_state                                            AS uf,
        COUNT(DISTINCT o.order_id)                                 AS total_pedidos,
        COUNT(DISTINCT o.customer_id)                              AS total_clientes,
        ROUND(SUM(oi.price + oi.freight_value), 2)                 AS receita_total,
        ROUND(AVG(oi.freight_value), 2)                            AS frete_medio,
        ROUND(
            AVG(
                DATEDIFF('DAY',
                    TO_TIMESTAMP(o.order_purchase_timestamp),
                    TO_TIMESTAMP(o.order_delivered_customer_date)
                )
            ), 1
        )                                                           AS prazo_entrega_medio_dias
    FROM RAW_OLIST.OLIST_ORDERS_DATASET            AS o
    INNER JOIN RAW_OLIST.OLIST_CUSTOMERS_DATASET   AS c  ON o.customer_id = c.customer_id
    INNER JOIN RAW_OLIST.OLIST_ORDER_ITEMS_DATASET AS oi ON o.order_id    = oi.order_id
    WHERE
        o.order_status = 'delivered'
        AND o.order_delivered_customer_date IS NOT NULL
    GROUP BY c.customer_state
),

totais AS (
    SELECT SUM(total_pedidos) AS total_brasil
    FROM pedidos_por_estado
)

SELECT
    p.uf                                                          AS "Estado (UF)",
    p.total_pedidos                                               AS "Total de Pedidos",
    p.total_clientes                                              AS "Clientes Únicos",
    p.receita_total                                               AS "Receita Total (R$)",
    ROUND(p.total_pedidos / t.total_brasil * 100, 2)             AS "% do Total Nacional",
    p.frete_medio                                                 AS "Frete Médio (R$)",
    p.prazo_entrega_medio_dias                                    AS "Prazo Médio de Entrega (dias)"
FROM pedidos_por_estado AS p
CROSS JOIN totais AS t
ORDER BY p.total_pedidos DESC;


-- =============================================================================
-- QUERY 5 - TABELA DE DADOS
-- Título: Ranking de Performance dos Vendedores (Top 20)
-- Tipo de gráfico: Table / Data Table
-- Pergunta de negócio: Quais são os vendedores de melhor desempenho
--   considerando volume, receita, satisfação do cliente e prazo de entrega?
-- =============================================================================

WITH metricas_vendedor AS (
    SELECT
        s.seller_id,
        s.seller_city                                                AS cidade,
        s.seller_state                                               AS estado,
        COUNT(DISTINCT oi.order_id)                                  AS total_pedidos,
        COUNT(DISTINCT oi.product_id)                                AS skus_distintos,
        ROUND(SUM(oi.price + oi.freight_value), 2)                   AS receita_total,
        ROUND(AVG(oi.price), 2)                                      AS preco_medio_produto,
        ROUND(AVG(r.review_score), 2)                                AS nota_media_avaliacao,
        COUNT(r.review_id)                                           AS total_avaliacoes,
        ROUND(
            AVG(
                DATEDIFF('DAY',
                    TO_TIMESTAMP(o.order_purchase_timestamp),
                    TO_TIMESTAMP(o.order_delivered_carrier_date)
                )
            ), 1
        )                                                            AS media_dias_despacho
    FROM RAW_OLIST.OLIST_SELLERS_DATASET              AS s
    INNER JOIN RAW_OLIST.OLIST_ORDER_ITEMS_DATASET    AS oi ON s.seller_id  = oi.seller_id
    INNER JOIN RAW_OLIST.OLIST_ORDERS_DATASET         AS o  ON oi.order_id  = o.order_id
    LEFT JOIN  RAW_OLIST.OLIST_ORDER_REVIEWS_DATASET  AS r  ON o.order_id   = r.order_id
    WHERE o.order_status = 'delivered'
    GROUP BY s.seller_id, s.seller_city, s.seller_state
),

score_composto AS (
    SELECT
        seller_id,
        cidade,
        estado,
        total_pedidos,
        skus_distintos,
        receita_total,
        preco_medio_produto,
        nota_media_avaliacao,
        total_avaliacoes,
        media_dias_despacho,
        -- Score composto: combina receita normalizada, nota e velocidade de despacho
        ROUND(
            (PERCENT_RANK() OVER (ORDER BY receita_total ASC)       * 0.50)
          + (PERCENT_RANK() OVER (ORDER BY nota_media_avaliacao ASC) * 0.35)
          + (PERCENT_RANK() OVER (ORDER BY media_dias_despacho DESC) * 0.15)
          , 4
        )                                                            AS score_performance
    FROM metricas_vendedor
    WHERE total_pedidos >= 10   -- filtro: vendedores com volume mínimo representativo
)

SELECT
    ROW_NUMBER() OVER (ORDER BY score_performance DESC)             AS "Ranking",
    seller_id                                                       AS "ID do Vendedor",
    cidade                                                          AS "Cidade",
    estado                                                          AS "Estado",
    total_pedidos                                                   AS "Total de Pedidos",
    skus_distintos                                                  AS "SKUs Distintos",
    receita_total                                                   AS "Receita Total (R$)",
    preco_medio_produto                                             AS "Preço Médio (R$)",
    nota_media_avaliacao                                            AS "Nota Média",
    total_avaliacoes                                                AS "Total de Avaliações",
    media_dias_despacho                                             AS "Dias Médios p/ Despacho",
    ROUND(score_performance * 100, 2)                              AS "Score de Performance (%)"
FROM score_composto
ORDER BY score_performance DESC
LIMIT 20;


-- =============================================================================
-- QUERY 6 (BÔNUS) - SCATTER PLOT
-- Título: Preço Médio vs. Satisfação do Cliente por Categoria
-- Tipo de gráfico: Scatter Plot (dispersão)
-- Pergunta de negócio: Existe correlação entre o preço dos produtos e a
--   satisfação dos clientes? Produtos mais caros têm melhor avaliação?
-- =============================================================================

WITH base_categoria AS (
    SELECT
        COALESCE(t.product_category_name_english, p.product_category_name, 'Sem Categoria') AS categoria,
        COUNT(DISTINCT oi.order_id)                                                           AS total_pedidos,
        ROUND(AVG(oi.price), 2)                                                               AS preco_medio,
        ROUND(AVG(r.review_score), 2)                                                         AS nota_media,
        ROUND(SUM(oi.price + oi.freight_value), 2)                                            AS receita_total,
        ROUND(AVG(oi.freight_value), 2)                                                       AS frete_medio,
        COUNT(r.review_id)                                                                    AS total_avaliacoes
    FROM RAW_OLIST.OLIST_ORDER_ITEMS_DATASET               AS oi
    INNER JOIN RAW_OLIST.OLIST_PRODUCTS_DATASET            AS p  ON oi.product_id = p.product_id
    INNER JOIN RAW_OLIST.OLIST_ORDERS_DATASET              AS o  ON oi.order_id   = o.order_id
    LEFT JOIN  RAW_OLIST.OLIST_ORDER_REVIEWS_DATASET       AS r  ON o.order_id    = r.order_id
    LEFT JOIN  RAW_OLIST.PRODUCT_CATEGORY_NAME_TRANSLATION AS t  ON p.product_category_name = t.product_category_name
    WHERE
        o.order_status = 'delivered'
        AND r.review_score IS NOT NULL
    GROUP BY
        COALESCE(t.product_category_name_english, p.product_category_name, 'Sem Categoria')
    HAVING COUNT(DISTINCT oi.order_id) >= 50   -- volume mínimo para representatividade estatística
)

SELECT
    categoria                AS "Categoria",
    preco_medio              AS "Preço Médio (R$)",     -- eixo X no scatter
    nota_media               AS "Nota Média (0-5)",     -- eixo Y no scatter
    receita_total            AS "Receita Total (R$)",   -- tamanho da bolha (bubble)
    total_pedidos            AS "Total de Pedidos",
    frete_medio              AS "Frete Médio (R$)",
    total_avaliacoes         AS "Total de Avaliações"
FROM base_categoria
ORDER BY receita_total DESC;


-- =============================================================================
-- QUERY 7 (BÔNUS) - FUNIL / WATERFALL
-- Título: Distribuição de Pedidos por Status (Funil de Conversão)
-- Tipo de gráfico: Funnel Chart / Bar Chart ordenado por status
-- Pergunta de negócio: Qual é a taxa de conclusão dos pedidos? Em qual
--   etapa ocorre maior atrito ou abandono no ciclo de vida do pedido?
-- =============================================================================

WITH status_counts AS (
    SELECT
        order_status,
        COUNT(DISTINCT order_id) AS total_pedidos
    FROM RAW_OLIST.OLIST_ORDERS_DATASET
    GROUP BY order_status
),

funil_ordenado AS (
    SELECT
        order_status,
        total_pedidos,
        -- Ordem lógica do funil de ciclo de vida do pedido
        CASE order_status
            WHEN 'created'            THEN 1
            WHEN 'approved'           THEN 2
            WHEN 'processing'         THEN 3
            WHEN 'invoiced'           THEN 4
            WHEN 'shipped'            THEN 5
            WHEN 'delivered'          THEN 6
            WHEN 'canceled'           THEN 7
            WHEN 'unavailable'        THEN 8
            ELSE 9
        END                          AS ordem_funil,
        CASE order_status
            WHEN 'created'            THEN 'Criado'
            WHEN 'approved'           THEN 'Aprovado'
            WHEN 'processing'         THEN 'Em Processamento'
            WHEN 'invoiced'           THEN 'Faturado'
            WHEN 'shipped'            THEN 'Enviado'
            WHEN 'delivered'          THEN 'Entregue'
            WHEN 'canceled'           THEN 'Cancelado'
            WHEN 'unavailable'        THEN 'Indisponível'
            ELSE order_status
        END                          AS status_pt
    FROM status_counts
),

totais AS (
    SELECT
        SUM(CASE WHEN ordem_funil <= 6 THEN total_pedidos ELSE 0 END) AS pedidos_ciclo_positivo
    FROM funil_ordenado
)

SELECT
    f.ordem_funil                                                                AS "Ordem",
    f.status_pt                                                                  AS "Status do Pedido",
    f.total_pedidos                                                              AS "Total de Pedidos",
    ROUND(f.total_pedidos / SUM(f.total_pedidos) OVER () * 100, 2)             AS "% do Total",
    ROUND(
        f.total_pedidos
        / NULLIF(MAX(CASE WHEN f.ordem_funil = 1 THEN f.total_pedidos END) OVER (), 0)
        * 100,
        2
    )                                                                            AS "% Relativo ao Topo do Funil"
FROM funil_ordenado AS f
ORDER BY f.ordem_funil;
