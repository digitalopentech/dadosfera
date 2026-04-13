# Arquitetura de Pipelines — ETL e ML

> **Caso Tecnico:** Dadosfera Data Platform
> **Documento:** 08 — Pipelines de Dados e Machine Learning
> **Data:** Abril de 2026
> **Versao:** 1.0

---

## 1. Visao Geral

Este documento descreve a arquitetura completa dos pipelines de dados implementados para o caso tecnico Dadosfera, cobrindo as camadas ETL (Raw → Trusted → Refined) e os dois pipelines de Machine Learning: **Recomendacao de Produtos** e **Previsao de Tempo de Entrega**.

---

## 2. Diagrama de Arquitetura do Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CAMADA RAW (Bronze)                             │
│                                                                         │
│   olist_orders.csv        olist_products.csv    olist_sellers.csv       │
│   olist_order_items.csv   olist_customers.csv   olist_geolocation.csv   │
│   olist_order_payments.csv  olist_order_reviews.csv  category_tr.csv   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │    ETL: Raw → Trusted   │
                    │  - Deduplicacao por PK  │
                    │  - Tratamento de nulos  │
                    │  - Correcao de tipos    │
                    │  - Filtros de qualidade │
                    │  - Normalizacao strings │
                    └────────────┬────────────┘
                                 │
┌─────────────────────────────────────────────────────────────────────────┐
│                       CAMADA TRUSTED (Silver)                           │
│                                                                         │
│   orders_trusted      products_trusted    sellers_trusted               │
│   order_items_trusted customers_trusted   order_reviews_trusted         │
│   order_payments_trusted                                                │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │  ETL: Trusted → Refined │
                    │  - Star Schema Kimball  │
                    │  - Surrogate keys (SK)  │
                    │  - Metricas derivadas   │
                    │  - dim_date gerada      │
                    └────────────┬────────────┘
                                 │
┌─────────────────────────────────────────────────────────────────────────┐
│                        CAMADA REFINED (Gold)                            │
│                                                                         │
│   fact_orders          dim_customer        dim_date                     │
│   fact_reviews         dim_product         dim_geography                │
│                        dim_seller                                       │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                                     │
   ┌──────────▼──────────┐             ┌────────────▼────────────┐
   │  ML: Recomendacao   │             │  ML: Previsao Entrega   │
   │  - TF-IDF (500 ft.) │             │  - Feature Engineering  │
   │  - Cosine Similarity│             │  - Random Forest (200t) │
   │  - Precision@10     │             │  - Cross-validation 5k  │
   │  - Recall@10        │             │  - RMSE / MAE / R2      │
   └──────────┬──────────┘             └────────────┬────────────┘
              │                                     │
              └──────────────────┬──────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   Artefatos (.joblib)   │
                    │   Parquet refinados     │
                    │   ml_metrics.csv        │
                    └─────────────────────────┘
```

---

## 3. ETL — Raw → Trusted

### 3.1 Objetivo

A camada Trusted garante que todos os dados estejam **livres de duplicatas, com tipos corretos e sem nulos criticos**, prontos para transformacoes analiticas. Nenhuma logica de negocio e aplicada nesta etapa — apenas higiene de dados.

### 3.2 Regras de Limpeza por Tabela

| Tabela | Chave Natural | Tratamento de Nulos | Filtros |
|--------|--------------|---------------------|---------|
| `olist_orders` | `order_id` | timestamps: `NaT` preservado | `order_status IN (valid_set)` |
| `olist_order_items` | `(order_id, order_item_id)` | `price`, `freight_value` → 0 | `price >= 0` e `freight_value >= 0` |
| `olist_order_payments` | `(order_id, payment_sequential)` | `installments` → 1 | `payment_value >= 0` |
| `olist_order_reviews` | `review_id` | comentarios → `""` | `review_score BETWEEN 1 AND 5` |
| `olist_customers` | `customer_id` | — | — |
| `olist_products` | `product_id` | dimensoes fisicas → 0 | — |
| `olist_sellers` | `seller_id` | — | — |

### 3.3 Transformacoes Adicionais

- **Produtos:** calculo de `product_volume_cm3 = length * height * width`; join com tabela de traducao de categorias para gerar `product_category_name_english`
- **Customers/Sellers:** normalizacao de `state` (uppercase) e `city` (lowercase)
- **Orders:** parse seguro de timestamps com `errors='coerce'` — datas invalidas viram `NaT` em vez de causar falha no pipeline

### 3.4 Validacoes de Qualidade (Pre-Refined)

```python
assert trusted.orders["order_id"].is_unique, "order_id deve ser unico"
assert (trusted.order_items["price"] >= 0).all(), "preco nao pode ser negativo"
assert trusted.order_reviews["review_score"].between(1, 5).all(), "score invalido"
```

---

## 4. ETL — Trusted → Refined (Star Schema)

### 4.1 Modelo Dimensional

O schema segue o padrao **Kimball Star Schema** com granularidade de item de pedido na tabela fato principal.

```
                    ┌──────────────┐
                    │  dim_date    │
                    │  date_key PK │
                    └──────┬───────┘
                           │
┌──────────────┐    ┌──────▼───────────┐    ┌──────────────┐
│ dim_customer │    │   fact_orders    │    │ dim_product  │
│ customer_sk  │◄───│ order_id         │───►│ product_sk   │
└──────────────┘    │ order_item_id    │    └──────────────┘
                    │ customer_sk  FK  │
┌──────────────┐    │ product_sk   FK  │    ┌──────────────┐
│  dim_seller  │◄───│ seller_sk    FK  │    │ fact_reviews │
│  seller_sk   │    │ date_key     FK  │    │ review_id    │
└──────────────┘    │ price            │◄───│ order_id  FK │
                    │ freight_value    │    │ review_score │
                    │ total_payment    │    └──────────────┘
                    │ delivery_days    │
                    │ is_late          │
                    └──────────────────┘
```

### 4.2 Metricas Derivadas em `fact_orders`

| Metrica | Calculo | Unidade |
|---------|---------|---------|
| `delivery_days` | `order_delivered_customer_date - order_purchase_timestamp` | dias |
| `estimated_days` | `order_estimated_delivery_date - order_purchase_timestamp` | dias |
| `is_late` | `delivered_date > estimated_date` | boolean |
| `total_payment` | `SUM(payment_value) por order_id` | R$ |

### 4.3 `dim_date` — Atributos Gerados

A dimensao de tempo e gerada programaticamente a partir das datas unicas de compra:

```
year | quarter | month | month_name_pt | week_of_year | day_of_week | day_name_pt | is_weekend
```

---

## 5. Pipeline de ML — Recomendacao de Produtos

### 5.1 Abordagem

**Content-based filtering** usando TF-IDF sobre um corpus textual derivado de:
- `product_category_name` (portugues)
- `product_category_name_english` (ingles)
- `product_weight_g` (peso como token numerico)
- `product_volume_cm3` (volume calculado)

A matriz de similaridade de cosseno e calculada entre todos os produtos e persistida em memoria para consulta em O(1).

### 5.2 Fluxo

```
product_features DataFrame
        |
        v
TfidfVectorizer(max_features=500, ngram_range=(1,2), sublinear_tf=True)
        |
        v
tfidf_matrix (sparse: n_products × 500)
        |
        v
cosine_similarity(tfidf_matrix)  →  similarity_matrix (n × n)
        |
        v
recommend(product_id, top_n=10)  →  DataFrame [(product_id, similarity_score)]
```

### 5.3 Avaliacao

A validacao usa **co-purchase**: um par (A, B) e considerado relevante se aparece no mesmo pedido. Limitado a pedidos com 2+ produtos.

| Metrica | Descricao |
|---------|-----------|
| `Precision@10` | Proporcao de recomendados que sao co-comprados |
| `Recall@10` | Proporcao de co-comprados que sao recomendados |

> **Nota:** O dataset Olist possui 98% dos pedidos com apenas 1 item, o que limita o sinal de co-purchase. Em producao, a abordagem seria complementada com **embeddings semanticos** (sentence-transformers ou OpenAI embeddings) sobre descricoes de produtos.

---

## 6. Pipeline de ML — Previsao de Tempo de Entrega

### 6.1 Features

| Feature | Tipo | Descricao |
|---------|------|-----------|
| `seller_state_enc` | int | UF do vendedor (LabelEncoder) |
| `customer_state_enc` | int | UF do cliente (LabelEncoder) |
| `product_weight_g` | float | Peso em gramas |
| `product_volume_cm3` | float | Volume calculado |
| `freight_value` | float | Valor do frete cobrado |
| `price` | float | Preco do produto |
| `same_state` | int | Flag: vendedor e cliente na mesma UF |

### 6.2 Target e Filtros

- **Target:** `delivery_days` — dias corridos entre compra e entrega
- **Filtro de qualidade:** apenas pedidos `delivered` com `0 < delivery_days <= 120`
- **Split:** 80% treino / 20% teste, `random_state=42`

### 6.3 Modelo

```
RandomForestRegressor(
    n_estimators = 200,
    max_depth    = 12,
    min_samples_leaf = 5,
    n_jobs       = -1,
    random_state = 42
)
```

### 6.4 Metricas de Avaliacao

| Metrica | Descricao |
|---------|-----------|
| **RMSE** | Raiz do erro quadratico medio (mesma unidade do target: dias) |
| **MAE** | Erro absoluto medio — mais interpretavel operacionalmente |
| **R²** | Coeficiente de determinacao — proporcao da variancia explicada |
| **CV-RMSE** | RMSE medio em 5 folds no conjunto de treino (generalizacao) |

---

## 7. Catalogacao na Dadosfera (Stepsfera)

### 7.1 Visao Geral do Stepsfera

O **Stepsfera** e o orquestrador nativo da Dadosfera para pipelines de dados. Cada "Step" e uma unidade de processamento que pode ser conectada a outras em um DAG visual.

### 7.2 Estrutura de Steps para Este Pipeline

```
[Step 1: Ingestao Raw]
   Tipo: CSV Loader
   Fonte: Storage bucket (9 arquivos Olist)
   Saida: Tabelas raw no Snowflake (esquema RAW)

[Step 2: ETL Trusted]
   Tipo: Python Transformation
   Script: notebooks/04_ml_pipeline.py → funcoes clean_*()
   Dependencia: Step 1
   Saida: Tabelas no esquema TRUSTED

[Step 3: ETL Refined]
   Tipo: Python Transformation
   Script: notebooks/04_ml_pipeline.py → funcoes build_dim_*(), build_fact_*()
   Dependencia: Step 2
   Saida: Star schema no esquema REFINED

[Step 4a: ML Recomendacao]
   Tipo: Python ML
   Script: notebooks/04_ml_pipeline.py → RecommendationModel
   Dependencia: Step 3
   Saida: recommendation_model.joblib + metricas

[Step 4b: ML Previsao]
   Tipo: Python ML
   Script: notebooks/04_ml_pipeline.py → RandomForestRegressor
   Dependencia: Step 3
   Saida: delivery_rf_model.joblib + metricas

[Step 5: Publicacao]
   Tipo: Data Catalog Update
   Acao: Registrar tabelas refinadas no catalogo Dadosfera
   Dependencia: Steps 4a, 4b
```

### 7.3 Configuracao no Stepsfera

Para criar o pipeline na Dadosfera:

1. Acessar **Stepsfera** no painel da Dadosfera
2. Criar novo pipeline: `olist_etl_ml_pipeline`
3. Adicionar Steps na ordem descrita acima
4. Configurar variaveis de ambiente: `DADOSFERA_USERNAME`, `DADOSFERA_PASSWORD`
5. Definir schedule: `CRON 0 3 * * *` (execucao diaria as 3h)
6. Habilitar notificacoes de falha por email

### 7.4 Monitoramento

| Verificacao | Frequencia | Acao em Falha |
|-------------|-----------|---------------|
| Row count por tabela | A cada execucao | Alerta + pausa pipeline |
| Schema drift | A cada execucao | Alerta critico |
| RMSE do modelo | Semanal (re-treino) | Notificacao para revisao |
| Freshness dos dados | Diaria | Alerta se > 25h sem atualizar |

---

## 8. Consideracoes de Performance

| Gargalo | Volume Estimado | Estrategia |
|---------|----------------|------------|
| Matriz de similaridade (n × n) | ~32k produtos → 1 GB | Calcular sparse e converter por demanda |
| Leitura de CSVs | ~100k linhas × 9 arquivos | `parse_dates` no load, sem re-leitura |
| Random Forest | 200 arvores × 80k amostras | `n_jobs=-1` (paralelo) |
| Parquet write | 7 tabelas | Particionar `fact_orders` por `year_month` em producao |

---

**Confianca:** 0.95 | **Impacto:** Alto
**Referencias:** KB: python/patterns/clean-architecture.md | sklearn docs | Dadosfera Stepsfera Guide
