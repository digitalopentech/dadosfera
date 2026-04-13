# Item 2 - Integracao de Dados na Dadosfera

> Guia passo-a-passo para carregar o dataset Olist na plataforma Dadosfera

## Visao Geral

Este documento descreve o processo de integracao dos dados do dataset Olist Brazilian E-Commerce na plataforma Dadosfera, utilizando o modulo de **Coleta (Integrar)**.

## Pre-requisitos

- Acesso ao ambiente de treinamento da Dadosfera
- Dataset Olist baixado do Kaggle (9 arquivos CSV, ~45MB)
- Navegador web atualizado

## Passo 1: Acessar o Modulo de Coleta

1. Acesse [app.dadosfera.ai](https://app.dadosfera.ai)
2. Faca login com suas credenciais
3. No menu lateral, clique em **Coletar** (ou **Integrar**)

## Passo 2: Importar Arquivos CSV

Para cada um dos 9 arquivos CSV do dataset Olist:

### 2.1 Criar Nova Conexao

1. Clique em **"+ Nova Conexao"** ou **"Importar Arquivo"**
2. Selecione **"Upload de Arquivo"** como tipo de fonte
3. Arraste ou selecione o arquivo CSV

### 2.2 Configurar Import dos Arquivos

Importe os arquivos na seguinte ordem (respeitando dependencias):

| # | Arquivo | Registros | Descricao |
|---|---------|-----------|-----------|
| 1 | `olist_customers_dataset.csv` | ~99.441 | Clientes e localizacao |
| 2 | `olist_sellers_dataset.csv` | ~3.095 | Vendedores |
| 3 | `olist_products_dataset.csv` | ~32.951 | Catalogo de produtos |
| 4 | `product_category_name_translation.csv` | ~71 | Traducao de categorias |
| 5 | `olist_geolocation_dataset.csv` | ~1.000.163 | Geolocalizacao (CEPs) |
| 6 | `olist_orders_dataset.csv` | ~99.441 | Pedidos |
| 7 | `olist_order_items_dataset.csv` | ~112.650 | Itens dos pedidos |
| 8 | `olist_order_payments_dataset.csv` | ~103.886 | Pagamentos |
| 9 | `olist_order_reviews_dataset.csv` | ~99.224 | Avaliacoes |

**Total estimado: ~1.550.000+ registros** (muito acima do minimo de 100k)

### 2.3 Configuracao de Cada Arquivo

Para cada arquivo, configure:

- **Nome do Dataset:** Manter o nome original (ex: `olist_orders_dataset`)
- **Delimitador:** Virgula (`,`)
- **Encoding:** UTF-8
- **Header:** Sim (primeira linha contem cabecalhos)
- **Tipo de Dados:** Deixar auto-deteccao ou configurar manualmente

### 2.4 Mapeamento de Tipos

| Tipo Original (CSV) | Tipo Dadosfera/Snowflake |
|---------------------|--------------------------|
| IDs (order_id, customer_id) | VARCHAR |
| Datas (timestamps) | TIMESTAMP_NTZ |
| Precos (price, freight) | DECIMAL(10,2) |
| Contagens (qty, installments) | INTEGER |
| Texto (review_comment) | VARCHAR |
| Coordenadas (lat, lng) | FLOAT |

## Passo 3: Verificar Carga

Apos o upload de cada arquivo:

1. Acesse o modulo **Explorar**
2. Localize o dataset pelo nome
3. Verifique:
   - Numero de registros carregados
   - Tipos de dados detectados
   - Amostras dos dados

## Passo 4: Organizacao em Zonas do Data Lake

Na Dadosfera, organize os dados seguindo as zonas padrao:

```
Data Lake
├── Raw Zone (Bronze)
│   ├── olist_orders_dataset          ← Dados originais
│   ├── olist_order_items_dataset
│   ├── olist_order_payments_dataset
│   ├── olist_order_reviews_dataset
│   ├── olist_customers_dataset
│   ├── olist_products_dataset
│   ├── olist_sellers_dataset
│   ├── olist_geolocation_dataset
│   └── product_category_name_translation
│
├── Trusted Zone (Silver)
│   ├── trusted_orders                ← Dados limpos e tipados
│   ├── trusted_order_items
│   ├── trusted_payments
│   ├── trusted_reviews
│   ├── trusted_customers
│   ├── trusted_products
│   └── trusted_sellers
│
└── Refined Zone (Gold)
    ├── dim_customer                  ← Star Schema
    ├── dim_product
    ├── dim_seller
    ├── dim_date
    ├── dim_geography
    ├── fact_orders
    └── fact_reviews
```

## Passo 5: Catalogar os Datasets

Para cada dataset carregado, preencha no catalogo da Dadosfera:

- **Nome:** Nome descritivo em portugues
- **Descricao:** O que o dataset contem e sua finalidade
- **Tags:** `olist`, `e-commerce`, `case-tecnico`, zona (`raw`, `trusted`, `refined`)
- **Dono:** Seu nome

Consulte o documento [03_data_catalog.md](./03_data_catalog.md) para o dicionario de dados completo.

## Bonus: Microtransformacao

Para demonstrar a feature de Microtransformacao da Dadosfera:

1. Carregue os dados em uma base transacional SQL (pode usar o proprio Snowflake da Dadosfera)
2. No modulo de Coleta, configure uma **Microtransformacao**:
   - Exemplo: Converter `order_purchase_timestamp` de STRING para TIMESTAMP
   - Exemplo: Criar campo calculado `total_order_value = price + freight_value`
   - Exemplo: Filtrar apenas pedidos com status `delivered`

## Bonus: Catalogacao via API

Use o script `scripts/dadosfera_api.py` para catalogar assets automaticamente:

```python
from scripts.dadosfera_api import DadosferaClient

client = DadosferaClient(
    username=os.getenv("DADOSFERA_USERNAME"),
    password=os.getenv("DADOSFERA_PASSWORD"),
)
client.authenticate()

# Listar todos os assets
assets = client.list_catalog_assets()

# Atualizar metadados de um asset
client.update_asset(
    asset_id=123,
    name="Pedidos Olist - Raw Zone",
    description="Dataset de pedidos do e-commerce Olist, zona raw (dados brutos)",
    tags=["olist", "e-commerce", "raw-zone", "pedidos"],
)
```

## Evidencias Necessarias

Para o README do case, inclua:

- [ ] Screenshot da tela de Coleta com os datasets importados
- [ ] Screenshot do catalogo com os datasets catalogados
- [ ] Print mostrando o numero de registros carregados (100k+)
- [ ] Link para os assets na Dadosfera

## Troubleshooting

| Problema | Solucao |
|----------|---------|
| Upload falha por tamanho | Dividir arquivo em partes menores |
| Tipos detectados incorretamente | Configurar mapeamento manual |
| Caracteres especiais (acentos) | Verificar encoding UTF-8 |
| Timeout no upload | Tentar em horario de menor uso |
| Dados duplicados | Verificar se ja existe dataset com mesmo nome |

## Proximos Passos

Apos a integracao, siga para:
- [Item 3 - Catalogo de Dados](./03_data_catalog.md)
- [Item 4 - Qualidade de Dados](./04_data_quality.md)
