# Catálogo de Dados — Olist Brazilian E-Commerce

> **Projeto:** Case Técnico Dadosfera — Análise de E-Commerce Brasileiro
> **Dataset:** Olist Brazilian E-Commerce (Kaggle) — ~100k pedidos, 9 tabelas
> **Plataforma:** Dadosfera Data Lake
> **Última atualização:** 2026-04-13

---

## Sumário

1. [Organização das Zonas do Data Lake](#1-organização-das-zonas-do-data-lake)
2. [Diagrama de Relacionamentos](#2-diagrama-de-relacionamentos)
3. [Dicionário de Dados por Tabela](#3-dicionário-de-dados-por-tabela)
   - [olist_orders_dataset](#31-olist_orders_dataset)
   - [olist_order_items_dataset](#32-olist_order_items_dataset)
   - [olist_order_payments_dataset](#33-olist_order_payments_dataset)
   - [olist_order_reviews_dataset](#34-olist_order_reviews_dataset)
   - [olist_customers_dataset](#35-olist_customers_dataset)
   - [olist_products_dataset](#36-olist_products_dataset)
   - [olist_sellers_dataset](#37-olist_sellers_dataset)
   - [olist_geolocation_dataset](#38-olist_geolocation_dataset)
   - [product_category_name_translation](#39-product_category_name_translation)
4. [Mapeamento entre Zonas](#4-mapeamento-entre-zonas)
5. [Lineage e Rastreabilidade](#5-lineage-e-rastreabilidade)
6. [Glossário de Negócio](#6-glossário-de-negócio)

---

## 1. Organização das Zonas do Data Lake

O Data Lake da Dadosfera segue o modelo **Medallion Architecture** com três zonas progressivas de refinamento. Cada zona representa um nível de confiança e transformação aplicado ao dado.

```
┌────────────────────────────────────────────────────────────────────┐
│                        DADOSFERA DATA LAKE                         │
├──────────────────┬──────────────────────┬──────────────────────────┤
│   RAW (Bronze)   │   TRUSTED (Silver)   │     REFINED (Gold)       │
├──────────────────┼──────────────────────┼──────────────────────────┤
│ • Dado original  │ • Dado limpo         │ • Modelo dimensional     │
│ • Sem alteração  │ • Deduplicado        │ • Star Schema            │
│ • CSV/JSON/Parq  │ • Tipado             │ • Pronto para analytics  │
│ • Imutável       │ • Particionado       │ • Agregado               │
│                  │ • Validado           │ • Histórico SCD2         │
├──────────────────┼──────────────────────┼──────────────────────────┤
│ raw.olist_*      │ trusted.olist_*      │ gold.dim_*, gold.fact_*  │
└──────────────────┴──────────────────────┴──────────────────────────┘
```

### 1.1 Raw Zone (Bronze)

**Objetivo:** Preservar o dado exatamente como recebido da fonte.

| Característica | Detalhe |
|---|---|
| Formato | CSV (origem Kaggle), convertido para Parquet |
| Particionamento | Por data de ingestão (`ingestion_date`) |
| Retenção | 90 dias (dados brutos), depois arquivamento frio |
| Acesso | Restrito a engenheiros de dados |
| Transformações | Nenhuma — somente adição de metadados de ingestão |
| Schema enforcement | Opcional (schema-on-read) |

Metadados adicionados na ingestão:
- `_ingested_at` — timestamp da carga
- `_source_file` — nome do arquivo CSV de origem
- `_batch_id` — identificador do lote de ingestão

### 1.2 Trusted Zone (Silver)

**Objetivo:** Dado confiável, limpo e padronizado para uso analítico direto.

| Característica | Detalhe |
|---|---|
| Formato | Parquet (Delta Lake / Iceberg) |
| Particionamento | Por coluna de negócio (ex: `order_purchase_date`) |
| Retenção | 3 anos |
| Acesso | Analistas de dados, cientistas de dados |
| Transformações | Cast de tipos, remoção de duplicatas, normalização de strings |
| Schema enforcement | Obrigatório (schema-on-write) |

Transformações aplicadas:
- Timestamps convertidos de string para `TIMESTAMP`
- Strings de cidade/estado padronizadas (maiúsculas, sem acentos)
- Registros duplicados removidos com lógica de deduplicação por chave primária
- Valores monetários validados (não negativos)
- Colunas calculadas adicionadas (ex: `delivery_delay_days`)

### 1.3 Refined Zone (Gold)

**Objetivo:** Modelo dimensional otimizado para consumo em BI, dashboards e relatórios executivos.

| Característica | Detalhe |
|---|---|
| Formato | Parquet (Delta Lake) ou tabelas em warehouse |
| Particionamento | Por granularidade de negócio (mensal/anual) |
| Retenção | Indefinida |
| Acesso | Todos os usuários com perfil de leitura analítica |
| Transformações | Joins, agregações, cálculo de KPIs, históricas SCD2 |
| Schema enforcement | Obrigatório com testes de contrato |

Entidades geradas:
- `fact_orders` — fato de pedidos com métricas
- `dim_customers` — dimensão de clientes (SCD Tipo 1)
- `dim_products` — dimensão de produtos com categoria em inglês
- `dim_sellers` — dimensão de vendedores com geolocalização
- `dim_date` — dimensão de tempo (gerada)
- `dim_geolocation` — dimensão de localização

---

## 2. Diagrama de Relacionamentos

```
                        ┌──────────────────────────────┐
                        │     olist_orders_dataset      │
                        │  PK: order_id                 │
                        │  FK: customer_id              │
                        └──────────┬───────────────────┘
                                   │ 1:N
          ┌────────────────────────┼────────────────────────┐
          │                        │                         │
          ▼                        ▼                         ▼
┌──────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
│ olist_order_     │   │ olist_order_payments │   │ olist_order_reviews  │
│ items_dataset    │   │ _dataset             │   │ _dataset             │
│ PK: order_id +   │   │ PK: order_id +       │   │ PK: review_id        │
│     order_item_id│   │     payment_seq      │   │ FK: order_id         │
│ FK: product_id   │   └──────────────────────┘   └──────────────────────┘
│ FK: seller_id    │
└────────┬─────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌──────────┐  ┌──────────────────┐
│ olist_   │  │ olist_sellers_   │
│ products │  │ dataset          │
│ _dataset │  │ PK: seller_id    │
│ PK:      │  │ FK: zip_code ──► │ olist_geolocation_dataset
│ product_id│  └──────────────────┘  PK: zip_code + lat + lng
└──────────┘
      │
      ▼ (via product_category_name)
┌──────────────────────────────────┐
│ product_category_name_translation│
│ PK: product_category_name        │
└──────────────────────────────────┘

olist_customers_dataset ◄── FK de olist_orders_dataset
PK: customer_id
FK: zip_code ──► olist_geolocation_dataset
```

---

## 3. Dicionário de Dados por Tabela

---

### 3.1 olist_orders_dataset

**Descrição:** Tabela central do modelo. Registra todos os pedidos realizados na plataforma Olist, com informações de status e datas do ciclo de vida do pedido (compra, aprovação, despacho e entrega).

**Volume estimado:** ~99.441 registros
**Granularidade:** Um registro por pedido
**Chave primária:** `order_id`

| Coluna | Tipo (Raw) | Tipo (Trusted) | Nullable | Descrição | Exemplo | Regras de Negócio |
|---|---|---|---|---|---|---|
| `order_id` | STRING | VARCHAR(32) | NÃO | Identificador único do pedido. Gerado pelo sistema Olist no momento da criação do pedido. | `e481f51cbdc54678b7cc49136f2d6af7` | PK. Não nulo. Único. 32 caracteres hexadecimais. |
| `customer_id` | STRING | VARCHAR(32) | NÃO | Identificador do cliente para este pedido. Cada pedido possui um `customer_id` distinto — não é o identificador único do cliente (ver `customer_unique_id` em `olist_customers_dataset`). | `9ef432eb6251297304e76186b10a928d` | FK para `olist_customers_dataset.customer_id`. Não nulo. |
| `order_status` | STRING | VARCHAR(20) | NÃO | Status atual do pedido no ciclo de vida da entrega. | `delivered` | Valores permitidos: `approved`, `canceled`, `created`, `delivered`, `invoiced`, `processing`, `shipped`, `unavailable`. |
| `order_purchase_timestamp` | STRING | TIMESTAMP | NÃO | Data e hora em que o cliente realizou o pedido na plataforma. | `2017-10-02 10:56:33` | Não nulo. Deve ser anterior a `order_approved_at`. Formato: `YYYY-MM-DD HH:MM:SS`. |
| `order_approved_at` | STRING | TIMESTAMP | SIM | Data e hora de aprovação do pagamento pelo gateway financeiro. | `2017-10-02 11:07:15` | Pode ser nulo para pedidos cancelados antes da aprovação. Deve ser >= `order_purchase_timestamp`. |
| `order_delivered_carrier_date` | STRING | TIMESTAMP | SIM | Data e hora em que o pedido foi entregue à transportadora (despacho). | `2017-10-04 19:55:00` | Pode ser nulo para pedidos não despachados. Deve ser >= `order_approved_at`. |
| `order_delivered_customer_date` | STRING | TIMESTAMP | SIM | Data e hora em que o pedido foi entregue ao cliente final. | `2017-10-10 21:25:13` | Nulo para pedidos ainda em trânsito ou cancelados. Deve ser >= `order_delivered_carrier_date`. |
| `order_estimated_delivery_date` | STRING | TIMESTAMP | NÃO | Data estimada de entrega informada ao cliente no momento da compra. | `2017-10-18 00:00:00` | Não nulo. Base para cálculo de atraso de entrega (`delivery_delay_days`). |

**Coluna calculada (Trusted Zone):**

| Coluna Derivada | Tipo | Fórmula | Descrição |
|---|---|---|---|
| `delivery_delay_days` | INTEGER | `order_delivered_customer_date - order_estimated_delivery_date` | Dias de atraso na entrega. Negativo = entrega antecipada. Nulo se pedido não entregue. |
| `order_processing_days` | INTEGER | `order_delivered_carrier_date - order_approved_at` | Dias entre aprovação e despacho. |

---

### 3.2 olist_order_items_dataset

**Descrição:** Detalha os itens que compõem cada pedido. Um pedido pode conter múltiplos itens (produtos), cada um com seu próprio `order_item_id` sequencial. Contém as informações comerciais: preço unitário e frete.

**Volume estimado:** ~112.650 registros
**Granularidade:** Um registro por item dentro de um pedido
**Chave primária:** Composta — `(order_id, order_item_id)`

| Coluna | Tipo (Raw) | Tipo (Trusted) | Nullable | Descrição | Exemplo | Regras de Negócio |
|---|---|---|---|---|---|---|
| `order_id` | STRING | VARCHAR(32) | NÃO | Identificador do pedido ao qual o item pertence. | `00010242fe8c5a6d1ba2dd792cb16214` | FK para `olist_orders_dataset.order_id`. Não nulo. |
| `order_item_id` | INTEGER | INTEGER | NÃO | Número sequencial do item dentro do pedido. Começa em 1 e incrementa por item adicionado. | `1` | Não nulo. Mínimo: 1. Combinado com `order_id` forma a PK. |
| `product_id` | STRING | VARCHAR(32) | NÃO | Identificador do produto vendido neste item. | `4244733e06e7ecb4970a6e2683c13e61` | FK para `olist_products_dataset.product_id`. Não nulo. |
| `seller_id` | STRING | VARCHAR(32) | NÃO | Identificador do vendedor responsável por este item. | `48436dade18ac8b2bce089ec2a041202` | FK para `olist_sellers_dataset.seller_id`. Não nulo. |
| `shipping_limit_date` | STRING | TIMESTAMP | NÃO | Prazo máximo para o vendedor despachar o item para a transportadora. | `2017-09-19 09:45:35` | Não nulo. Gerado pela Olist no momento do pedido. |
| `price` | FLOAT | DECIMAL(10,2) | NÃO | Preço unitário do produto em Reais (BRL). Não inclui o frete. | `58.90` | Não nulo. Deve ser > 0. Valor em BRL. |
| `freight_value` | FLOAT | DECIMAL(10,2) | NÃO | Valor do frete cobrado para este item em Reais (BRL). Quando um pedido tem múltiplos itens, o frete é rateado entre eles. | `13.29` | Não nulo. Deve ser >= 0. Valor em BRL. |

**Colunas calculadas (Trusted Zone):**

| Coluna Derivada | Tipo | Fórmula | Descrição |
|---|---|---|---|
| `item_total_value` | DECIMAL(10,2) | `price + freight_value` | Valor total do item incluindo frete |

---

### 3.3 olist_order_payments_dataset

**Descrição:** Registra as informações de pagamento de cada pedido. Um pedido pode ter múltiplos pagamentos (ex: combinação de cartão de crédito e voucher), cada um representado por um registro com seu `payment_sequential`.

**Volume estimado:** ~103.886 registros
**Granularidade:** Um registro por forma de pagamento utilizada em um pedido
**Chave primária:** Composta — `(order_id, payment_sequential)`

| Coluna | Tipo (Raw) | Tipo (Trusted) | Nullable | Descrição | Exemplo | Regras de Negócio |
|---|---|---|---|---|---|---|
| `order_id` | STRING | VARCHAR(32) | NÃO | Identificador do pedido ao qual o pagamento está associado. | `b81ef226f3fe1789b1e8b2acac839d17` | FK para `olist_orders_dataset.order_id`. Não nulo. |
| `payment_sequential` | INTEGER | INTEGER | NÃO | Número sequencial do pagamento dentro do pedido. Útil quando há múltiplos meios de pagamento para um mesmo pedido. | `1` | Não nulo. Mínimo: 1. |
| `payment_type` | STRING | VARCHAR(20) | NÃO | Método de pagamento utilizado pelo cliente. | `credit_card` | Valores permitidos: `boleto`, `credit_card`, `debit_card`, `not_defined`, `voucher`. |
| `payment_installments` | INTEGER | INTEGER | NÃO | Número de parcelas escolhidas pelo cliente no pagamento. Para pagamentos à vista, o valor é 1. | `8` | Não nulo. Mínimo: 1. Para `boleto` e `debit_card`, deve ser 1. |
| `payment_value` | FLOAT | DECIMAL(10,2) | NÃO | Valor pago nesta transação em Reais (BRL). Pode ser parte do total quando há múltiplos pagamentos. | `99.33` | Não nulo. Deve ser > 0. |

---

### 3.4 olist_order_reviews_dataset

**Descrição:** Contém as avaliações feitas pelos clientes após a conclusão do pedido. A Olist envia um questionário de satisfação por e-mail, e o cliente pode atribuir uma nota de 1 a 5 além de comentários opcionais.

**Volume estimado:** ~99.224 registros
**Granularidade:** Um registro por avaliação (pode haver múltiplas avaliações por pedido em casos raros de reenvio)
**Chave primária:** `review_id`

| Coluna | Tipo (Raw) | Tipo (Trusted) | Nullable | Descrição | Exemplo | Regras de Negócio |
|---|---|---|---|---|---|---|
| `review_id` | STRING | VARCHAR(32) | NÃO | Identificador único da avaliação. Gerado pelo sistema da Olist. | `7bc2406110b926393aa56f80a40eba40` | PK. Não nulo. Único. |
| `order_id` | STRING | VARCHAR(32) | NÃO | Identificador do pedido avaliado pelo cliente. | `73fc7af87114b39712e6da79b0a377eb` | FK para `olist_orders_dataset.order_id`. Não nulo. |
| `review_score` | INTEGER | INTEGER | NÃO | Nota de satisfação atribuída pelo cliente. Escala de 1 (muito insatisfeito) a 5 (muito satisfeito). | `4` | Não nulo. Valores permitidos: 1, 2, 3, 4, 5. |
| `review_comment_title` | STRING | VARCHAR(255) | SIM | Título opcional do comentário de avaliação escrito pelo cliente. Frequentemente nulo. | `Entrega rápida` | Pode ser nulo. Máximo: 255 caracteres. |
| `review_comment_message` | STRING | TEXT | SIM | Corpo do comentário de avaliação. Texto livre escrito pelo cliente descrevendo sua experiência. | `Produto chegou antes do prazo, muito bem embalado.` | Pode ser nulo. Sem limite de caracteres. |
| `review_creation_date` | STRING | TIMESTAMP | NÃO | Data e hora em que o formulário de avaliação foi enviado ao cliente. | `2018-01-18 00:00:00` | Não nulo. Deve ser após `order_delivered_customer_date`. |
| `review_answer_timestamp` | STRING | TIMESTAMP | NÃO | Data e hora em que o cliente respondeu à avaliação. | `2018-01-18 21:46:59` | Não nulo. Deve ser >= `review_creation_date`. |

---

### 3.5 olist_customers_dataset

**Descrição:** Contém dados cadastrais dos clientes da plataforma Olist. Importante: `customer_id` é único por pedido, enquanto `customer_unique_id` é o identificador real do cliente (uma pessoa pode ter vários `customer_id` se fizer múltiplos pedidos).

**Volume estimado:** ~99.441 registros
**Granularidade:** Um registro por `customer_id` (um por pedido)
**Chave primária:** `customer_id`

| Coluna | Tipo (Raw) | Tipo (Trusted) | Nullable | Descrição | Exemplo | Regras de Negócio |
|---|---|---|---|---|---|---|
| `customer_id` | STRING | VARCHAR(32) | NÃO | Identificador do cliente para um pedido específico. Referenciado por `olist_orders_dataset`. Não representa o cliente real de forma única. | `06b8999e2fba1a1fbc88172c00ba8bc7` | PK desta tabela. Único. Não nulo. |
| `customer_unique_id` | STRING | VARCHAR(32) | NÃO | Identificador único real do cliente. Permite rastrear todos os pedidos de um mesmo cliente ao longo do tempo. | `861eff4711a542e4b93843c6dd7febb0` | Não nulo. Vários `customer_id` podem ter o mesmo `customer_unique_id`. |
| `customer_zip_code_prefix` | STRING | VARCHAR(5) | NÃO | Primeiros 5 dígitos do CEP do endereço de entrega do cliente. Permite junção com `olist_geolocation_dataset`. | `14409` | Não nulo. 5 dígitos numéricos. FK para `olist_geolocation_dataset.geolocation_zip_code_prefix`. |
| `customer_city` | STRING | VARCHAR(100) | NÃO | Nome da cidade do endereço de entrega do cliente. | `franca` | Não nulo. Normalizar para letras minúsculas na Trusted Zone. Padronização necessária (variações ortográficas). |
| `customer_state` | STRING | CHAR(2) | NÃO | Sigla do estado (UF) do endereço de entrega do cliente. | `SP` | Não nulo. Deve ser uma das 27 UFs brasileiras. |

---

### 3.6 olist_products_dataset

**Descrição:** Catálogo de produtos disponíveis na plataforma Olist. Contém informações de categorização e atributos físicos dos produtos (dimensões e peso), essenciais para o cálculo de frete.

**Volume estimado:** ~32.951 registros
**Granularidade:** Um registro por produto
**Chave primária:** `product_id`

| Coluna | Tipo (Raw) | Tipo (Trusted) | Nullable | Descrição | Exemplo | Regras de Negócio |
|---|---|---|---|---|---|---|
| `product_id` | STRING | VARCHAR(32) | NÃO | Identificador único do produto no catálogo Olist. | `1e9e8ef04dbcff4541ed26657ea517e5` | PK. Não nulo. Único. |
| `product_category_name` | STRING | VARCHAR(100) | SIM | Nome da categoria do produto em português. Pode ser nulo para produtos não categorizados. | `perfumaria` | FK para `product_category_name_translation.product_category_name`. Pode ser nulo (~2% dos registros). |
| `product_name_lenght` | FLOAT | INTEGER | SIM | Número de caracteres no nome do produto. Nota: o dataset original contém erro de digitação no nome da coluna (`lenght` ao invés de `length`). | `40` | Pode ser nulo. Deve ser > 0 quando preenchido. |
| `product_description_lenght` | FLOAT | INTEGER | SIM | Número de caracteres na descrição do produto. | `287` | Pode ser nulo. Deve ser > 0 quando preenchido. |
| `product_photos_qty` | FLOAT | INTEGER | SIM | Quantidade de fotos publicadas para o produto no marketplace. | `1` | Pode ser nulo. Deve ser >= 1 quando preenchido. |
| `product_weight_g` | FLOAT | INTEGER | SIM | Peso do produto em gramas, incluindo embalagem. Utilizado para cálculo de frete. | `225` | Pode ser nulo. Deve ser > 0 quando preenchido. |
| `product_length_cm` | FLOAT | INTEGER | SIM | Comprimento do produto embalado em centímetros. | `16` | Pode ser nulo. Deve ser > 0 quando preenchido. |
| `product_height_cm` | FLOAT | INTEGER | SIM | Altura do produto embalado em centímetros. | `10` | Pode ser nulo. Deve ser > 0 quando preenchido. |
| `product_width_cm` | FLOAT | INTEGER | SIM | Largura do produto embalado em centímetros. | `14` | Pode ser nulo. Deve ser > 0 quando preenchido. |

**Observação técnica:** O dataset original possui os nomes de coluna `product_name_lenght` e `product_description_lenght` com erro ortográfico (`lenght` no lugar de `length`). Na Trusted Zone, as colunas são renomeadas para `product_name_length` e `product_description_length`, mantendo a compatibilidade reversa via aliases.

---

### 3.7 olist_sellers_dataset

**Descrição:** Cadastro dos vendedores (lojistas) que operam na plataforma Olist. Contém informações de localização que permitem análise geográfica de vendas por seller.

**Volume estimado:** ~3.095 registros
**Granularidade:** Um registro por vendedor
**Chave primária:** `seller_id`

| Coluna | Tipo (Raw) | Tipo (Trusted) | Nullable | Descrição | Exemplo | Regras de Negócio |
|---|---|---|---|---|---|---|
| `seller_id` | STRING | VARCHAR(32) | NÃO | Identificador único do vendedor na plataforma Olist. | `3442f8959a84dea7ee197c632cb2df15` | PK. Não nulo. Único. |
| `seller_zip_code_prefix` | STRING | VARCHAR(5) | NÃO | Primeiros 5 dígitos do CEP do endereço comercial do vendedor. | `13023` | Não nulo. 5 dígitos. FK para `olist_geolocation_dataset`. |
| `seller_city` | STRING | VARCHAR(100) | NÃO | Nome da cidade do endereço comercial do vendedor. | `campinas` | Não nulo. Normalizar para letras minúsculas. |
| `seller_state` | STRING | CHAR(2) | NÃO | Sigla do estado (UF) do endereço do vendedor. | `SP` | Não nulo. Uma das 27 UFs brasileiras. |

---

### 3.8 olist_geolocation_dataset

**Descrição:** Tabela de geolocalização que associa prefixos de CEP a coordenadas geográficas (latitude e longitude) e nomes de cidades/estados. Permite enriquecimento geoespacial de clientes e vendedores. Atenção: pode haver múltiplos registros por prefixo de CEP com coordenadas ligeiramente distintas.

**Volume estimado:** ~1.000.163 registros
**Granularidade:** Múltiplos registros por prefixo de CEP (média de ~5 coordenadas por CEP)
**Chave primária:** Não há chave natural única — composta por `(geolocation_zip_code_prefix, geolocation_lat, geolocation_lng)`

| Coluna | Tipo (Raw) | Tipo (Trusted) | Nullable | Descrição | Exemplo | Regras de Negócio |
|---|---|---|---|---|---|---|
| `geolocation_zip_code_prefix` | STRING | VARCHAR(5) | NÃO | Prefixo de 5 dígitos do CEP brasileiro. Chave de junção com `olist_customers_dataset` e `olist_sellers_dataset`. | `01037` | Não nulo. 5 dígitos. Não único — múltiplas coordenadas por CEP. |
| `geolocation_lat` | FLOAT | DOUBLE | NÃO | Latitude da localização. Coordenada geográfica no sistema WGS84. | `-23.54562128115029` | Não nulo. Intervalo válido para o Brasil: -33.75 a 5.27. Filtrar outliers. |
| `geolocation_lng` | FLOAT | DOUBLE | NÃO | Longitude da localização. Coordenada geográfica no sistema WGS84. | `-46.63929204800003` | Não nulo. Intervalo válido para o Brasil: -73.99 a -28.85. Filtrar outliers. |
| `geolocation_city` | STRING | VARCHAR(100) | NÃO | Nome da cidade correspondente ao CEP. | `são paulo` | Não nulo. Normalizar: remover acentos, padronizar capitalização. |
| `geolocation_state` | STRING | CHAR(2) | NÃO | Sigla do estado (UF) correspondente ao CEP. | `SP` | Não nulo. Uma das 27 UFs. |

**Estratégia de deduplicação (Trusted Zone):** Agregar por `geolocation_zip_code_prefix` utilizando `AVG(lat)` e `AVG(lng)` para obter o centroide do CEP. Isso reduz o volume de ~1M para ~19.015 registros únicos de CEP.

---

### 3.9 product_category_name_translation

**Descrição:** Tabela de dimensão auxiliar que fornece a tradução das categorias de produtos do português para o inglês. Utilizada para enriquecer a `olist_products_dataset` e habilitar relatórios internacionalizados.

**Volume estimado:** 71 registros
**Granularidade:** Um registro por categoria de produto
**Chave primária:** `product_category_name`

| Coluna | Tipo (Raw) | Tipo (Trusted) | Nullable | Descrição | Exemplo | Regras de Negócio |
|---|---|---|---|---|---|---|
| `product_category_name` | STRING | VARCHAR(100) | NÃO | Nome da categoria de produto em português, conforme cadastrado no dataset `olist_products_dataset`. | `beleza_saude` | PK. Não nulo. Único. FK para `olist_products_dataset.product_category_name`. |
| `product_category_name_english` | STRING | VARCHAR(100) | NÃO | Tradução do nome da categoria para o inglês. | `health_beauty` | Não nulo. Único. Utilizado nas camadas Trusted e Gold para internacionalização. |

---

## 4. Mapeamento entre Zonas

A tabela a seguir documenta como cada tabela evolui entre as três zonas do Data Lake, descrevendo as transformações aplicadas em cada etapa.

| Tabela | Raw Path | Trusted Path | Gold (entidade) | Transformações Trusted |
|---|---|---|---|---|
| `olist_orders_dataset` | `raw/olist/orders/` | `trusted/olist/orders/` | `fact_orders` | Cast timestamps, calcular `delivery_delay_days`, deduplicar por `order_id` |
| `olist_order_items_dataset` | `raw/olist/order_items/` | `trusted/olist/order_items/` | `fact_orders` (join) | Cast decimal, validar `price > 0`, calcular `item_total_value` |
| `olist_order_payments_dataset` | `raw/olist/payments/` | `trusted/olist/payments/` | `fact_orders` (agregado) | Cast decimal, validar `payment_value > 0`, agregar por pedido |
| `olist_order_reviews_dataset` | `raw/olist/reviews/` | `trusted/olist/reviews/` | `fact_reviews` | Cast timestamps, validar `review_score` in 1-5, normalizar texto |
| `olist_customers_dataset` | `raw/olist/customers/` | `trusted/olist/customers/` | `dim_customers` | Deduplicar por `customer_unique_id`, normalizar cidade/estado |
| `olist_products_dataset` | `raw/olist/products/` | `trusted/olist/products/` | `dim_products` | Corrigir nomes de colunas (`lenght`), join com tradução de categoria |
| `olist_sellers_dataset` | `raw/olist/sellers/` | `trusted/olist/sellers/` | `dim_sellers` | Normalizar cidade/estado, enriquecer com geolocalização |
| `olist_geolocation_dataset` | `raw/olist/geolocation/` | `trusted/olist/geolocation/` | `dim_geolocation` | Deduplicar por CEP (centroide), filtrar coordenadas fora do Brasil |
| `product_category_name_translation` | `raw/olist/category_translation/` | `trusted/olist/category_translation/` | `dim_products` (join) | Sem transformações — tabela de lookup estática |

---

## 5. Lineage e Rastreabilidade

### 5.1 Fluxo de Dados Simplificado

```
[Kaggle CSV] ──► [Raw Zone] ──► [Trusted Zone] ──► [Gold Zone] ──► [BI/Analytics]
     │                │               │                 │
     │           metadados       limpeza +          star schema
     │           ingestão        validação          + KPIs
     │
     └── Sem alteração após ingestão (imutabilidade da Raw Zone)
```

### 5.2 Dependências entre Tabelas Gold

| Entidade Gold | Depende de (Trusted) |
|---|---|
| `fact_orders` | `orders`, `order_items`, `order_payments` |
| `fact_reviews` | `order_reviews`, `orders` |
| `dim_customers` | `customers`, `geolocation` |
| `dim_products` | `products`, `category_translation` |
| `dim_sellers` | `sellers`, `geolocation` |
| `dim_geolocation` | `geolocation` |
| `dim_date` | Gerada programaticamente |

### 5.3 Campos de Rastreabilidade

Todos os registros nas zonas Trusted e Gold incluem os seguintes metadados para auditoria:

| Campo | Descrição |
|---|---|
| `_dw_created_at` | Timestamp de criação do registro no Data Lake |
| `_dw_updated_at` | Timestamp da última atualização |
| `_dw_source_table` | Tabela de origem (Raw Zone) |
| `_dw_batch_id` | ID do lote de processamento |
| `_dw_is_current` | Flag SCD2: registro mais recente (apenas Gold) |

---

## 6. Glossário de Negócio

| Termo | Definição |
|---|---|
| **Pedido (Order)** | Transação comercial realizada por um cliente no marketplace Olist. Um pedido pode conter múltiplos itens de diferentes vendedores. |
| **Item de Pedido** | Unidade individual dentro de um pedido, representando a compra de um produto específico de um vendedor específico. |
| **Cliente (Customer)** | Consumidor final que realiza compras na plataforma. Identificado de forma única por `customer_unique_id`. |
| **Vendedor (Seller)** | Lojista parceiro que cadastra produtos e realiza vendas através da plataforma Olist. |
| **Frete** | Custo de envio do produto do vendedor ao cliente, calculado com base nas dimensões, peso e distância. |
| **NPS / Review Score** | Nota de 1 a 5 atribuída pelo cliente após receber o pedido. Métrica de satisfação do cliente. |
| **CEP (Código de Endereçamento Postal)** | Código postal brasileiro de 8 dígitos. No dataset, utilizado na forma truncada de 5 dígitos (`zip_code_prefix`). |
| **Atraso de Entrega** | Diferença em dias entre `order_delivered_customer_date` e `order_estimated_delivery_date`. Valor positivo indica atraso. |
| **Ticket Médio** | Valor médio gasto por pedido, calculado como `SUM(price + freight_value) / COUNT(DISTINCT order_id)`. |
| **Taxa de Cancelamento** | Proporção de pedidos com `order_status = 'canceled'` sobre o total de pedidos. |
| **Seller Performance** | Conjunto de métricas de desempenho do vendedor: pontualidade de despacho, avaliação média, ticket médio, volume de vendas. |
