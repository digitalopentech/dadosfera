# Estratégia de Qualidade de Dados — Olist Brazilian E-Commerce

> **Projeto:** Case Técnico Dadosfera — Análise de E-Commerce Brasileiro
> **Dataset:** Olist Brazilian E-Commerce (Kaggle) — ~100k pedidos, 9 tabelas
> **Ferramenta Principal:** Great Expectations (GX Core 1.x)
> **Última atualização:** 2026-04-13

---

## Sumário

1. [Visão Geral da Estratégia](#1-visão-geral-da-estratégia)
2. [Dimensões de Qualidade Avaliadas](#2-dimensões-de-qualidade-avaliadas)
3. [Problemas Identificados no Dataset Olist](#3-problemas-identificados-no-dataset-olist)
4. [Regras de Validação por Tabela](#4-regras-de-validação-por-tabela)
5. [Estratégias de Remediação](#5-estratégias-de-remediação)
6. [Thresholds e SLAs de Qualidade](#6-thresholds-e-slas-de-qualidade)
7. [Proposta de Common Data Model (CDM)](#7-proposta-de-common-data-model-cdm)
8. [Integração com o Pipeline de Dados](#8-integração-com-o-pipeline-de-dados)

---

## 1. Visão Geral da Estratégia

A estratégia de qualidade de dados para o projeto Olist/Dadosfera é organizada em três camadas de validação, alinhadas à arquitetura Medallion do Data Lake:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PIRÂMIDE DE QUALIDADE                            │
│                                                                     │
│              [Gold]  ◄── Testes de contrato: SLAs,                 │
│             /      \     consistência de modelos dimensionais       │
│           /          \                                              │
│         /  [Silver]   \◄── GE Suites: completude, unicidade,       │
│       /                \   validade, consistência referencial       │
│     /     [Bronze]      \◄── Validações estruturais: schema,       │
│   /________________________\  tipos, encoding, tamanho de arquivo   │
└─────────────────────────────────────────────────────────────────────┘
```

### Princípios Orientadores

| Princípio | Aplicação |
|---|---|
| **Qualidade é observabilidade, não transformação** | Checks são read-only — nunca UPDATE/DELETE |
| **Fail fast** | Validações de Raw Zone bloqueiam promoção para Trusted Zone |
| **Thresholds contextuais** | Nenhum threshold fixo sem justificativa de negócio |
| **PII nunca em resultados de teste** | Colunas sensíveis mascaradas nas asserções |
| **Idempotência** | Reexecutar os mesmos checks produz os mesmos resultados |

---

## 2. Dimensões de Qualidade Avaliadas

### 2.1 Completude (Completeness)

**Definição:** Proporção de valores não nulos em campos obrigatórios.

**Relevância para Olist:** Campos críticos como `order_id`, `customer_id` e `order_purchase_timestamp` não podem ser nulos — a ausência inviabiliza análises de ciclo de vida do pedido.

**Métricas:**

```sql
-- Taxa de completude por coluna crítica
SELECT
    1.0 - (COUNT(*) FILTER (WHERE order_id IS NULL)::FLOAT / COUNT(*))
        AS completude_order_id,
    1.0 - (COUNT(*) FILTER (WHERE customer_id IS NULL)::FLOAT / COUNT(*))
        AS completude_customer_id,
    1.0 - (COUNT(*) FILTER (WHERE order_purchase_timestamp IS NULL)::FLOAT / COUNT(*))
        AS completude_purchase_ts
FROM trusted.olist_orders;
```

**Threshold:** >= 99,5% para colunas obrigatórias.

---

### 2.2 Unicidade (Uniqueness)

**Definição:** Garantia de que chaves primárias e identificadores únicos não se repetem.

**Relevância para Olist:** Pedidos duplicados causam dupla contagem de receita. Clientes duplicados distorcem análises de retenção.

**Métricas:**

```sql
-- Verificar duplicatas em order_id
SELECT
    COUNT(*) AS total_registros,
    COUNT(DISTINCT order_id) AS order_ids_unicos,
    COUNT(*) - COUNT(DISTINCT order_id) AS duplicatas
FROM trusted.olist_orders;
```

**Threshold:** 100% — zero duplicatas em chaves primárias.

---

### 2.3 Validade (Validity)

**Definição:** Conformidade dos valores com regras de negócio, formatos esperados e domínios definidos.

**Relevância para Olist:** Preços negativos, notas de avaliação fora do intervalo 1-5, ou status de pedido inválidos corrompem relatórios e métricas de negócio.

**Exemplos de regras de validade:**

| Coluna | Regra | SQL |
|---|---|---|
| `review_score` | Entre 1 e 5 | `review_score BETWEEN 1 AND 5` |
| `price` | Maior que zero | `price > 0` |
| `payment_type` | Enum fixo | `payment_type IN ('boleto', 'credit_card', 'debit_card', 'voucher', 'not_defined')` |
| `order_status` | Enum fixo | `order_status IN ('approved', 'canceled', 'created', 'delivered', ...)` |
| `customer_state` | UF válida | `customer_state IN ('AC', 'AL', 'AP', ..., 'TO')` |
| `geolocation_lat` | Dentro do Brasil | `geolocation_lat BETWEEN -33.75 AND 5.27` |

**Threshold:** >= 99,5% de conformidade por regra.

---

### 2.4 Consistência (Consistency)

**Definição:** Coerência entre tabelas relacionadas (integridade referencial) e dentro da mesma linha (consistência intra-registro).

**Relevância para Olist:** Pedidos referenciando clientes inexistentes, itens vinculados a produtos deletados do catálogo, ou datas de entrega anteriores à data de compra são exemplos de inconsistências que invalidam análises.

**Dois tipos de consistência monitorados:**

**a) Consistência referencial (entre tabelas):**

```sql
-- Pedidos sem cliente correspondente
SELECT COUNT(*) AS pedidos_sem_cliente
FROM trusted.olist_orders o
LEFT JOIN trusted.olist_customers c ON o.customer_id = c.customer_id
WHERE c.customer_id IS NULL;

-- Itens referenciando produtos inexistentes
SELECT COUNT(*) AS itens_sem_produto
FROM trusted.olist_order_items i
LEFT JOIN trusted.olist_products p ON i.product_id = p.product_id
WHERE p.product_id IS NULL;
```

**b) Consistência temporal (dentro do registro):**

```sql
-- Pedidos com datas em ordem incorreta
SELECT COUNT(*) AS datas_inconsistentes
FROM trusted.olist_orders
WHERE order_delivered_customer_date < order_purchase_timestamp
   OR order_approved_at < order_purchase_timestamp
   OR order_delivered_carrier_date < order_approved_at;
```

**Threshold:** Zero registros inconsistentes em validações de integridade referencial.

---

### 2.5 Atualidade (Timeliness)

**Definição:** Frescor dos dados em relação ao SLA de ingestão.

**Relevância para Olist:** Para este dataset histórico (Kaggle), a dimensão de atualidade é aplicada ao pipeline de ingestão — garantindo que novos arquivos CSV são processados dentro do prazo acordado.

**Métricas de monitoramento:**

```sql
-- Staleness do batch mais recente
SELECT
    MAX(_ingested_at) AS ultima_ingestao,
    EXTRACT(HOURS FROM (CURRENT_TIMESTAMP - MAX(_ingested_at)))
        AS horas_desde_ultima_ingestao,
    CASE
        WHEN MAX(_ingested_at) < CURRENT_TIMESTAMP - INTERVAL '24 hours'
        THEN 'ATRASADO'
        ELSE 'OK'
    END AS status_frescor
FROM raw.olist_orders;
```

**SLA:** Ingestão diária — dados disponíveis na Trusted Zone em até 4 horas após disponibilização.

---

### 2.6 Acurácia (Accuracy)

**Definição:** Conformidade dos dados com a realidade ou fonte verdadeira (ground truth).

**Relevância para Olist:** Para dados históricos de Kaggle, a acurácia é verificada por amostragem e análise de distribuição estatística — identificando anomalias que sugerem erros de captura ou transformação.

**Técnicas aplicadas:**

```sql
-- Análise de distribuição de preços (detectar outliers)
SELECT
    MIN(price) AS preco_minimo,
    MAX(price) AS preco_maximo,
    AVG(price) AS preco_medio,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price) AS mediana,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY price) AS p99,
    STDDEV(price) AS desvio_padrao
FROM trusted.olist_order_items;

-- Proporção de pedidos por status (detectar anomalias de distribuição)
SELECT
    order_status,
    COUNT(*) AS quantidade,
    ROUND(COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER () * 100, 2) AS percentual
FROM trusted.olist_orders
GROUP BY order_status
ORDER BY quantidade DESC;
```

---

## 3. Problemas Identificados no Dataset Olist

Com base na análise exploratória do dataset público, os seguintes problemas de qualidade foram catalogados:

### 3.1 Problemas de Completude

| Tabela | Coluna | Problema | Frequência Estimada | Severidade |
|---|---|---|---|---|
| `olist_orders` | `order_approved_at` | Nulo para pedidos cancelados antes da aprovação | ~1.1% | Média |
| `olist_orders` | `order_delivered_carrier_date` | Nulo para pedidos não despachados | ~2.8% | Alta |
| `olist_orders` | `order_delivered_customer_date` | Nulo para pedidos em trânsito ou cancelados | ~3.0% | Alta |
| `olist_products` | `product_category_name` | Categoria ausente em alguns produtos | ~1.9% | Média |
| `olist_products` | `product_name_lenght` | Dimensões ausentes em produtos descontinuados | ~1.7% | Baixa |
| `olist_reviews` | `review_comment_title` | Avaliação sem título (campo opcional) | ~58.8% | Informativa |
| `olist_reviews` | `review_comment_message` | Avaliação sem comentário (campo opcional) | ~41.3% | Informativa |

### 3.2 Problemas de Unicidade

| Tabela | Coluna | Problema | Frequência Estimada | Severidade |
|---|---|---|---|---|
| `olist_reviews` | `order_id` | Múltiplas avaliações por pedido (reenvio de formulário) | ~3% dos pedidos | Alta |
| `olist_geolocation` | `geolocation_zip_code_prefix` | Múltiplas coordenadas por CEP | ~100% dos CEPs | Estrutural |

### 3.3 Problemas de Validade

| Tabela | Coluna | Problema | Frequência Estimada | Severidade |
|---|---|---|---|---|
| `olist_customers` | `customer_city` | Nomes de cidades com variações ortográficas (acentos, maiúsculas) | ~15% | Alta |
| `olist_sellers` | `seller_city` | Mesmo problema de padronização de cidades | ~12% | Alta |
| `olist_geolocation` | `geolocation_lat/lng` | Coordenadas fora do território brasileiro | ~0.5% | Alta |
| `olist_products` | `product_weight_g` | Peso zero ou implausível em alguns registros | ~0.2% | Média |
| `olist_orders` | `order_status` | Pedidos com status `not_defined` | <0.1% | Baixa |

### 3.4 Problemas de Consistência

| Verificação | Problema | Frequência Estimada | Severidade |
|---|---|---|---|
| Datas do pedido | `order_delivered_customer_date` < `order_purchase_timestamp` | ~0.3% | Crítica |
| Integridade de itens | Itens sem produto no catálogo (produto removido) | ~0.05% | Alta |
| Pagamentos vs Itens | Pedidos com itens mas sem registro de pagamento | ~0.1% | Alta |
| Avaliações vs Pedidos | Avaliações referenciando pedidos inexistentes | ~0.05% | Alta |

### 3.5 Problemas Estruturais / Técnicos

| Tabela | Problema | Impacto |
|---|---|---|
| `olist_products` | Typo no nome das colunas (`lenght` vs `length`) | Requer renomeação na Trusted Zone |
| Todas as datas | Armazenadas como STRING no CSV — cast necessário | Erros se formato inconsistente |
| `olist_products` | Colunas numéricas com tipo FLOAT para valores inteiros | Possível perda semântica |
| `olist_geolocation` | Volume 10x maior que esperado para análises de CEP | Performance e custo |

---

## 4. Regras de Validação por Tabela

### 4.1 olist_orders_dataset — Suite de Validações

| # | Expectativa | Tipo | Threshold |
|---|---|---|---|
| 1 | `order_id` não nulo | Completude | 100% |
| 2 | `order_id` único | Unicidade | 100% |
| 3 | `customer_id` não nulo | Completude | 100% |
| 4 | `order_status` no conjunto de valores válidos | Validade | 100% |
| 5 | `order_purchase_timestamp` não nulo | Completude | 100% |
| 6 | `order_estimated_delivery_date` não nulo | Completude | 100% |
| 7 | `order_delivered_customer_date` >= `order_purchase_timestamp` (quando não nulo) | Consistência | 100% |
| 8 | `order_approved_at` >= `order_purchase_timestamp` (quando não nulo) | Consistência | 100% |
| 9 | Contagem de linhas entre 90.000 e 110.000 | Volume | Exato |
| 10 | `order_delivered_customer_date` nulo apenas para status não-entregues | Consistência | 99,5% |

### 4.2 olist_order_items_dataset — Suite de Validações

| # | Expectativa | Tipo | Threshold |
|---|---|---|---|
| 1 | `order_id` não nulo | Completude | 100% |
| 2 | `order_item_id` não nulo e >= 1 | Validade | 100% |
| 3 | `product_id` não nulo | Completude | 100% |
| 4 | `seller_id` não nulo | Completude | 100% |
| 5 | `price` > 0 | Validade | 100% |
| 6 | `freight_value` >= 0 | Validade | 100% |
| 7 | `(order_id, order_item_id)` únicos em conjunto | Unicidade | 100% |
| 8 | `price` entre R$ 0,85 e R$ 6.735 (percentis históricos) | Acurácia | 99% |
| 9 | `product_id` existe em `olist_products` | Consistência | 99,9% |
| 10 | `seller_id` existe em `olist_sellers` | Consistência | 99,9% |

### 4.3 olist_order_payments_dataset — Suite de Validações

| # | Expectativa | Tipo | Threshold |
|---|---|---|---|
| 1 | `order_id` não nulo | Completude | 100% |
| 2 | `payment_sequential` não nulo e >= 1 | Validade | 100% |
| 3 | `payment_type` no conjunto de valores válidos | Validade | 100% |
| 4 | `payment_installments` >= 1 | Validade | 100% |
| 5 | `payment_value` > 0 | Validade | 100% |
| 6 | `(order_id, payment_sequential)` únicos | Unicidade | 100% |
| 7 | `payment_installments` = 1 para `payment_type = 'boleto'` | Consistência | 100% |

### 4.4 olist_order_reviews_dataset — Suite de Validações

| # | Expectativa | Tipo | Threshold |
|---|---|---|---|
| 1 | `review_id` não nulo | Completude | 100% |
| 2 | `review_id` único | Unicidade | 100% |
| 3 | `order_id` não nulo | Completude | 100% |
| 4 | `review_score` entre 1 e 5 | Validade | 100% |
| 5 | `review_creation_date` não nulo | Completude | 100% |
| 6 | `review_answer_timestamp` >= `review_creation_date` | Consistência | 100% |
| 7 | `order_id` existe em `olist_orders` | Consistência | 99,9% |

### 4.5 olist_customers_dataset — Suite de Validações

| # | Expectativa | Tipo | Threshold |
|---|---|---|---|
| 1 | `customer_id` não nulo e único | Completude + Unicidade | 100% |
| 2 | `customer_unique_id` não nulo | Completude | 100% |
| 3 | `customer_zip_code_prefix` não nulo | Completude | 100% |
| 4 | `customer_zip_code_prefix` com 5 dígitos numéricos | Validade | 100% |
| 5 | `customer_state` em conjunto de 27 UFs válidas | Validade | 100% |
| 6 | `customer_city` não nulo | Completude | 100% |

### 4.6 olist_products_dataset — Suite de Validações

| # | Expectativa | Tipo | Threshold |
|---|---|---|---|
| 1 | `product_id` não nulo e único | Completude + Unicidade | 100% |
| 2 | `product_weight_g` > 0 quando não nulo | Validade | 100% |
| 3 | `product_length_cm` > 0 quando não nulo | Validade | 100% |
| 4 | `product_height_cm` > 0 quando não nulo | Validade | 100% |
| 5 | `product_width_cm` > 0 quando não nulo | Validade | 100% |
| 6 | `product_photos_qty` >= 1 quando não nulo | Validade | 100% |
| 7 | `product_category_name` nulo em menos de 5% das linhas | Completude | >= 95% |

### 4.7 olist_geolocation_dataset — Suite de Validações

| # | Expectativa | Tipo | Threshold |
|---|---|---|---|
| 1 | `geolocation_lat` entre -33.75 e 5.27 | Validade | 99,9% |
| 2 | `geolocation_lng` entre -73.99 e -28.85 | Validade | 99,9% |
| 3 | `geolocation_zip_code_prefix` não nulo | Completude | 100% |
| 4 | `geolocation_state` em conjunto de 27 UFs | Validade | 100% |
| 5 | Contagem de linhas entre 900.000 e 1.100.000 | Volume | Exato |

---

## 5. Estratégias de Remediação

### 5.1 Nulos em Colunas de Data (Alta Prioridade)

**Problema:** `order_delivered_customer_date` nulo para ~3% dos pedidos.

**Causa:** Pedidos cancelados, em trânsito ou com problemas de entrega nunca recebem a data de entrega.

**Remediação:**
- Não preencher com valor padrão — a ausência é semanticamente correta
- Criar coluna derivada `is_delivered` (BOOLEAN) na Trusted Zone para facilitar filtros
- Garantir que métricas de prazo de entrega excluem pedidos não entregues com `WHERE is_delivered = TRUE`

```python
# Na Trusted Zone:
df["is_delivered"] = df["order_delivered_customer_date"].notna()
df["delivery_delay_days"] = (
    df["order_delivered_customer_date"] - df["order_estimated_delivery_date"]
).dt.days
# delivery_delay_days = NaN para pedidos não entregues (correto)
```

### 5.2 Duplicatas em Avaliações (Alta Prioridade)

**Problema:** Um mesmo pedido pode ter múltiplas avaliações por reenvio do formulário.

**Causa:** A Olist reenvia o questionário de satisfação se o cliente não responder na primeira tentativa. Ocasionalmente ambas as respostas são registradas.

**Remediação:** Deduplicar na Trusted Zone selecionando a avaliação mais recente por `order_id`:

```sql
-- Deduplicação: manter apenas a última avaliação por pedido
SELECT DISTINCT ON (order_id) *
FROM raw.olist_order_reviews
ORDER BY order_id, review_answer_timestamp DESC;
```

### 5.3 Padronização de Nomes de Cidades (Alta Prioridade)

**Problema:** Cidades com grafias inconsistentes (ex: `sao paulo`, `São Paulo`, `SAO PAULO`, `S Paulo`).

**Causa:** Dados inseridos manualmente por clientes e vendedores sem validação no formulário.

**Remediação:** Normalização em dois passos na Trusted Zone:

```python
import unicodedata
import re

def normalize_city(city: str) -> str:
    if not city:
        return city
    # Remover acentos
    city = unicodedata.normalize("NFKD", city)
    city = "".join(c for c in city if not unicodedata.combining(c))
    # Lowercase e remover espaços extras
    city = re.sub(r"\s+", " ", city.lower().strip())
    return city

df["customer_city"] = df["customer_city"].apply(normalize_city)
```

### 5.4 Coordenadas Fora do Brasil (Alta Prioridade)

**Problema:** Aproximadamente 0,5% dos registros de geolocalização possuem coordenadas fora do território brasileiro.

**Causa:** Erro de entrada de dados ou ruído no geocodificador utilizado pela Olist.

**Remediação:** Filtrar na Trusted Zone e logar registros rejeitados:

```python
BRAZIL_LAT_BOUNDS = (-33.75, 5.27)
BRAZIL_LNG_BOUNDS = (-73.99, -28.85)

mask_valid = (
    df["geolocation_lat"].between(*BRAZIL_LAT_BOUNDS) &
    df["geolocation_lng"].between(*BRAZIL_LNG_BOUNDS)
)
df_rejected = df[~mask_valid].copy()  # Logar para auditoria
df_clean = df[mask_valid].copy()
```

### 5.5 Typos em Nomes de Colunas (Média Prioridade)

**Problema:** Colunas `product_name_lenght` e `product_description_lenght` com erro ortográfico.

**Remediação:** Renomear no pipeline de ingestão para a Trusted Zone, mantendo aliases para compatibilidade:

```python
df = df.rename(columns={
    "product_name_lenght": "product_name_length",
    "product_description_lenght": "product_description_length"
})
```

### 5.6 Deduplicação de Geolocalização (Prioridade Estrutural)

**Problema:** Tabela de geolocalização com ~1M registros para ~19k CEPs únicos.

**Remediação:** Agregar na Trusted Zone usando centroide por CEP:

```sql
SELECT
    geolocation_zip_code_prefix,
    AVG(geolocation_lat) AS geolocation_lat,
    AVG(geolocation_lng) AS geolocation_lng,
    MAX(geolocation_city) AS geolocation_city,
    MAX(geolocation_state) AS geolocation_state
FROM raw.olist_geolocation
GROUP BY geolocation_zip_code_prefix;
```

---

## 6. Thresholds e SLAs de Qualidade

### 6.1 Scorecard de Qualidade por Dimensão

| Dimensão | Tabela | Métrica | Threshold Mínimo | Ação se Violado |
|---|---|---|---|---|
| Completude | orders | `order_id` não nulo | 100% | Bloquear promoção para Trusted |
| Completude | orders | `customer_id` não nulo | 100% | Bloquear promoção para Trusted |
| Completude | order_items | `price` não nulo | 100% | Bloquear promoção para Trusted |
| Unicidade | orders | `order_id` único | 100% | Bloquear promoção para Trusted |
| Unicidade | customers | `customer_id` único | 100% | Bloquear promoção para Trusted |
| Validade | reviews | `review_score` em [1,5] | 100% | Bloquear promoção para Trusted |
| Validade | order_items | `price > 0` | 100% | Bloquear promoção para Trusted |
| Validade | geolocation | coordenadas no Brasil | 99,9% | Filtrar + logar, continuar |
| Consistência | orders/customers | Integridade referencial | 99,9% | Alerta + investigar |
| Consistência | orders | Ordem cronológica de datas | 99,5% | Alerta + investigar |
| Volume | orders | 90k–110k registros | Exato | Alerta crítico |
| Atualidade | todas | Ingestão < 24h | SLA | Alerta operacional |

### 6.2 Score Global de Qualidade

O score global de qualidade do dataset é calculado como média ponderada das dimensões:

```
Score_Global = (
    0.30 * Score_Completude +
    0.25 * Score_Unicidade +
    0.20 * Score_Validade +
    0.15 * Score_Consistência +
    0.10 * Score_Atualidade
)
```

**Meta:** Score Global >= 0.95 para promoção de qualquer zona.

---

## 7. Proposta de Common Data Model (CDM)

O Common Data Model (CDM) tem como objetivo padronizar as entidades de negócio reutilizáveis entre diferentes datasets e análises, facilitando a integração de novas fontes de dados no futuro.

### 7.1 Entidades do CDM para E-Commerce

```yaml
# common_data_model/ecommerce_entities.yaml

version: "1.0"
domain: ecommerce

entities:

  customer:
    description: Consumidor final que realiza transações
    canonical_key: customer_unique_id
    fields:
      - name: customer_id
        type: VARCHAR(32)
        role: surrogate_key
      - name: customer_unique_id
        type: VARCHAR(32)
        role: natural_key
        pii: false
      - name: location_zip_code
        type: VARCHAR(5)
        pii: quasi_identifier
      - name: location_city
        type: VARCHAR(100)
        pii: quasi_identifier
      - name: location_state
        type: CHAR(2)
        pii: false

  order:
    description: Transação comercial realizada por um cliente
    canonical_key: order_id
    fields:
      - name: order_id
        type: VARCHAR(32)
        role: natural_key
      - name: customer_id
        type: VARCHAR(32)
        role: foreign_key
        references: customer.customer_id
      - name: status
        type: VARCHAR(20)
        enum: [approved, canceled, created, delivered, invoiced, processing, shipped, unavailable]
      - name: purchase_timestamp
        type: TIMESTAMP
        role: event_time
      - name: estimated_delivery_date
        type: TIMESTAMP

  product:
    description: Item comercializado no marketplace
    canonical_key: product_id
    fields:
      - name: product_id
        type: VARCHAR(32)
        role: natural_key
      - name: category_name_pt
        type: VARCHAR(100)
      - name: category_name_en
        type: VARCHAR(100)
        source: product_category_name_translation

  seller:
    description: Lojista parceiro que vende no marketplace
    canonical_key: seller_id
    fields:
      - name: seller_id
        type: VARCHAR(32)
        role: natural_key
      - name: location_zip_code
        type: VARCHAR(5)
      - name: location_state
        type: CHAR(2)
```

### 7.2 Benefícios do CDM para a Dadosfera

| Benefício | Descrição |
|---|---|
| **Integração futura** | Novas fontes (ex: dados do ERP do cliente) mapeiam para as mesmas entidades CDM |
| **Glossário unificado** | Todos os times usam a mesma definição de "Cliente" e "Pedido" |
| **Testes reutilizáveis** | Suites de GE definidas para entidades CDM são aplicadas a qualquer dataset que implemente o modelo |
| **Lineage simplificado** | Rastreamento de `customer_id` traversa automaticamente todas as fontes que implementam `customer` do CDM |
| **Onboarding acelerado** | Analistas novos aprendem um modelo, não N sistemas |

### 7.3 Mapeamento Olist → CDM

| Entidade CDM | Tabela Olist | Campo Olist | Campo CDM |
|---|---|---|---|
| `customer` | `olist_customers_dataset` | `customer_unique_id` | `customer.customer_unique_id` |
| `customer` | `olist_customers_dataset` | `customer_zip_code_prefix` | `customer.location_zip_code` |
| `order` | `olist_orders_dataset` | `order_id` | `order.order_id` |
| `order` | `olist_orders_dataset` | `order_status` | `order.status` |
| `order` | `olist_orders_dataset` | `order_purchase_timestamp` | `order.purchase_timestamp` |
| `product` | `olist_products_dataset` | `product_id` | `product.product_id` |
| `product` | `product_category_name_translation` | `product_category_name_english` | `product.category_name_en` |
| `seller` | `olist_sellers_dataset` | `seller_id` | `seller.seller_id` |

---

## 8. Integração com o Pipeline de Dados

### 8.1 Fluxo de Validação no Pipeline

```
Ingestão Raw
    │
    ▼
[GE Suite: Schema Validation]
    │ PASS ──► Trusted Zone Pipeline
    │ FAIL ──► Quarentena + Alerta + Stop
    │
    ▼
Trusted Zone
    │
    ▼
[GE Suite: Business Rules Validation]
    │ PASS ──► Gold Zone Pipeline
    │ FAIL (crítico) ──► Stop + Alerta Crítico
    │ FAIL (aviso)   ──► Log + Continuar com flag
    │
    ▼
Gold Zone
    │
    ▼
[GE Suite: Contract Validation]
    │ PASS ──► Disponibilizar para consumo
    │ FAIL ──► Reverter + Alerta Crítico
```

### 8.2 Ações Configuradas no Checkpoint GE

| Ação | Tipo | Quando | Destino |
|---|---|---|---|
| `store_validation_result` | Persistência | Sempre | GE Data Docs (local/S3) |
| `update_data_docs` | Relatório | Sempre | HTML estático |
| `send_slack_notification` | Alerta | Apenas em falha | Canal #data-quality |
| `fail_fast` | Controle | Falha crítica | Para execução do pipeline |

### 8.3 Relatório de Qualidade — Estrutura

O relatório HTML gerado pelo Great Expectations Data Docs inclui:

- **Sumário executivo:** Score global e status por dimensão
- **Detalhamento por suite:** Resultado de cada expectativa (PASS/FAIL + %)
- **Tendência histórica:** Evolução do score ao longo do tempo
- **Registros problemáticos:** Exemplos (mascarados) de registros que falharam
- **Recomendações:** Ações priorizadas para melhoria

**Localização do relatório:** `reports/data_quality/index.html`
