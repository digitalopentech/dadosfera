# %% [markdown]
# # Qualidade de Dados — Olist Brazilian E-Commerce
# ## Great Expectations (GX Core 1.x) — Case Técnico Dadosfera
#
# **Objetivo:** Executar validações de qualidade de dados nas 9 tabelas do dataset
# Olist usando Great Expectations, cobrindo as dimensões de completude, unicidade,
# validade, consistência e volume.
#
# **Dataset:** [Olist Brazilian E-Commerce](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
#
# **Como obter o dataset:**
# 1. Acesse o link acima e faça download do ZIP no Kaggle
# 2. Extraia os arquivos CSV para uma pasta chamada `data/` no mesmo diretório deste notebook
# 3. Alternativamente, use a Kaggle API:
#    ```bash
#    pip install kaggle
#    kaggle datasets download -d olistbr/brazilian-ecommerce
#    unzip brazilian-ecommerce.zip -d data/
#    ```
#
# **Ambiente:** Google Colab (Python 3.10+)

# %% [markdown]
# ## 1. Instalação de Dependências

# %%
# Instalar pacotes necessários
# Execute esta célula primeiro e reinicie o runtime se necessário

import subprocess
import sys

def install_packages():
    packages = [
        "great_expectations==1.3.10",
        "pandas==2.2.3",
        "numpy==1.26.4",
        "matplotlib==3.9.2",
        "seaborn==0.13.2",
        "jinja2==3.1.4",
    ]
    for pkg in packages:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", pkg, "--quiet"]
        )
    print("Todos os pacotes instalados com sucesso.")

install_packages()

# %% [markdown]
# ## 2. Imports e Configurações Globais

# %%
import os
import json
import warnings
from pathlib import Path
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import great_expectations as gx
from great_expectations.core import ExpectationSuite
from great_expectations.expectations import (
    ExpectColumnValuesToNotBeNull,
    ExpectColumnValuesToBeUnique,
    ExpectColumnValuesToBeInSet,
    ExpectColumnValuesToBeBetween,
    ExpectTableRowCountToBeBetween,
    ExpectColumnValuesToMatchRegex,
    ExpectColumnValueLengthsToBeBetween,
    ExpectColumnValuesToBeOfType,
    ExpectColumnPairValuesAToBeGreaterThanB,
    ExpectCompoundColumnsToBeUnique,
)

warnings.filterwarnings("ignore")
pd.set_option("display.max_columns", 50)
pd.set_option("display.float_format", "{:.4f}".format)

# --- Configuração de caminhos ---
# Ajuste DATA_DIR para o caminho onde estão os arquivos CSV
DATA_DIR = Path("data")  # Altere se necessário, ex: Path("/content/drive/MyDrive/olist")

# Mapeamento: nome lógico → nome do arquivo CSV
CSV_FILES = {
    "orders":               "olist_orders_dataset.csv",
    "order_items":          "olist_order_items_dataset.csv",
    "order_payments":       "olist_order_payments_dataset.csv",
    "order_reviews":        "olist_order_reviews_dataset.csv",
    "customers":            "olist_customers_dataset.csv",
    "products":             "olist_products_dataset.csv",
    "sellers":              "olist_sellers_dataset.csv",
    "geolocation":          "olist_geolocation_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}

REPORT_DIR = Path("reports/data_quality")
REPORT_DIR.mkdir(parents=True, exist_ok=True)

print(f"Great Expectations versão: {gx.__version__}")
print(f"Pandas versão: {pd.__version__}")
print(f"Diretório de dados: {DATA_DIR.resolve()}")
print(f"Relatórios em: {REPORT_DIR.resolve()}")

# %% [markdown]
# ## 3. Carregamento dos Dados

# %%
def load_csv(name: str, filename: str, data_dir: Path) -> Optional[pd.DataFrame]:
    """Carrega um arquivo CSV e retorna um DataFrame com metadados de diagnóstico."""
    filepath = data_dir / filename
    if not filepath.exists():
        print(f"  [AVISO] Arquivo não encontrado: {filepath}")
        print(f"          Verifique se DATA_DIR está correto: {data_dir.resolve()}")
        return None
    df = pd.read_csv(filepath, low_memory=False)
    print(f"  [OK] {name:25s} — {len(df):>10,} linhas | {df.shape[1]:>2} colunas | "
          f"{filepath.stat().st_size / 1024:.1f} KB")
    return df


print("Carregando dataset Olist...\n")
dataframes: dict[str, pd.DataFrame] = {}

for name, filename in CSV_FILES.items():
    df = load_csv(name, filename, DATA_DIR)
    if df is not None:
        dataframes[name] = df

loaded = list(dataframes.keys())
missing = [k for k in CSV_FILES if k not in dataframes]

print(f"\nTabelas carregadas ({len(loaded)}/9): {loaded}")
if missing:
    print(f"Tabelas ausentes: {missing}")
    print("\nAtencao: validacoes para tabelas ausentes serao ignoradas.")

# %% [markdown]
# ## 4. Análise Exploratória Rápida (EDA)

# %%
def quick_eda(name: str, df: pd.DataFrame) -> dict:
    """Gera um perfil de qualidade básico do DataFrame."""
    total = len(df)
    null_counts = df.isnull().sum()
    null_pct = (null_counts / total * 100).round(2)
    dup_count = df.duplicated().sum()

    profile = {
        "tabela": name,
        "total_linhas": total,
        "total_colunas": df.shape[1],
        "duplicatas_completas": int(dup_count),
        "pct_duplicatas": round(dup_count / total * 100, 4),
        "colunas_com_nulos": int((null_counts > 0).sum()),
        "nulos_por_coluna": null_pct[null_counts > 0].to_dict(),
        "tipos_de_dados": df.dtypes.astype(str).to_dict(),
    }
    return profile


print("=" * 70)
print("PERFIL DE QUALIDADE POR TABELA")
print("=" * 70)

eda_results = {}
for name, df in dataframes.items():
    profile = quick_eda(name, df)
    eda_results[name] = profile

    print(f"\n[{name.upper()}]")
    print(f"  Linhas:            {profile['total_linhas']:>10,}")
    print(f"  Colunas:           {profile['total_colunas']:>10}")
    print(f"  Duplicatas:        {profile['duplicatas_completas']:>10,} "
          f"({profile['pct_duplicatas']:.2f}%)")
    print(f"  Colunas c/ nulos:  {profile['colunas_com_nulos']:>10}")

    if profile["nulos_por_coluna"]:
        print("  Nulos por coluna:")
        for col, pct in profile["nulos_por_coluna"].items():
            bar = "#" * int(pct / 5)
            print(f"    {col:45s} {pct:6.2f}% {bar}")

# %% [markdown]
# ## 5. Validações com Great Expectations
#
# Cada tabela recebe uma `ExpectationSuite` com regras específicas cobrindo:
# - **Completude:** campos obrigatórios não nulos
# - **Unicidade:** chaves primárias únicas
# - **Validade:** domínios, ranges e formatos
# - **Consistência:** integridade referencial entre tabelas
# - **Volume:** contagem de linhas dentro do esperado

# %%
# Inicializar contexto GX (modo efêmero, sem persistência em disco)
context = gx.get_context(mode="ephemeral")

# Dicionário para armazenar resultados de todas as validações
validation_results: dict[str, dict] = {}


def run_suite(
    table_name: str,
    df: pd.DataFrame,
    suite: ExpectationSuite,
    context: gx.DataContext,
) -> dict:
    """Executa uma suite de expectativas e retorna o resultado estruturado."""
    if df is None:
        return {"skipped": True, "reason": "DataFrame não disponível"}

    # Registrar datasource e asset para este DataFrame
    ds_name = f"ds_{table_name}"
    try:
        datasource = context.data_sources.add_pandas(ds_name)
    except Exception:
        datasource = context.data_sources.get(ds_name)

    asset = datasource.add_dataframe_asset(f"asset_{table_name}")
    batch_def = asset.add_batch_definition_whole_dataframe(f"batch_{table_name}")

    validation_def = context.validation_definitions.add(
        gx.ValidationDefinition(
            name=f"val_{table_name}",
            data=batch_def,
            suite=suite,
        )
    )
    checkpoint = context.checkpoints.add(
        gx.Checkpoint(
            name=f"chk_{table_name}",
            validation_definitions=[validation_def],
        )
    )

    result = checkpoint.run(batch_parameters={"dataframe": df})

    # Extrair métricas resumidas
    total_exp = 0
    passed_exp = 0
    failed_details = []

    for vr in result.run_results.values():
        for exp_result in vr.results:
            total_exp += 1
            if exp_result.success:
                passed_exp += 1
            else:
                failed_details.append({
                    "expectation": exp_result.expectation_config.type,
                    "column": exp_result.expectation_config.kwargs.get("column", "TABLE"),
                    "result": exp_result.result,
                })

    score = round(passed_exp / total_exp, 4) if total_exp > 0 else 0.0

    return {
        "table": table_name,
        "success": result.success,
        "score": score,
        "total_expectations": total_exp,
        "passed": passed_exp,
        "failed": total_exp - passed_exp,
        "failed_details": failed_details,
    }


# %%
# Constantes de domínio reutilizadas nas suites
VALID_ORDER_STATUSES = [
    "approved", "canceled", "created", "delivered",
    "invoiced", "processing", "shipped", "unavailable",
]
VALID_PAYMENT_TYPES = [
    "boleto", "credit_card", "debit_card", "not_defined", "voucher",
]
VALID_STATES_BR = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO",
    "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI",
    "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
]

# %% [markdown]
# ### 5.1 Validação — olist_orders_dataset

# %%
if "orders" in dataframes:
    suite_orders = context.suites.add(
        ExpectationSuite(name="suite_orders")
    )

    # Completude — campos obrigatórios
    suite_orders.add_expectation(
        ExpectColumnValuesToNotBeNull(column="order_id")
    )
    suite_orders.add_expectation(
        ExpectColumnValuesToNotBeNull(column="customer_id")
    )
    suite_orders.add_expectation(
        ExpectColumnValuesToNotBeNull(column="order_status")
    )
    suite_orders.add_expectation(
        ExpectColumnValuesToNotBeNull(column="order_purchase_timestamp")
    )
    suite_orders.add_expectation(
        ExpectColumnValuesToNotBeNull(column="order_estimated_delivery_date")
    )

    # Unicidade — chave primária
    suite_orders.add_expectation(
        ExpectColumnValuesToBeUnique(column="order_id")
    )

    # Validade — domínio de status
    suite_orders.add_expectation(
        ExpectColumnValuesToBeInSet(
            column="order_status",
            value_set=VALID_ORDER_STATUSES,
        )
    )

    # Volume esperado para o dataset Olist
    suite_orders.add_expectation(
        ExpectTableRowCountToBeBetween(min_value=90_000, max_value=110_000)
    )

    result_orders = run_suite("orders", dataframes["orders"], suite_orders, context)
    validation_results["orders"] = result_orders
    status = "PASSOU" if result_orders["success"] else "FALHOU"
    print(f"[orders] {status} | Score: {result_orders['score']:.2%} "
          f"| {result_orders['passed']}/{result_orders['total_expectations']} expectativas")

# %% [markdown]
# ### 5.2 Validação — olist_order_items_dataset

# %%
if "order_items" in dataframes:
    suite_items = context.suites.add(
        ExpectationSuite(name="suite_order_items")
    )

    # Completude
    for col in ["order_id", "order_item_id", "product_id", "seller_id",
                "shipping_limit_date", "price", "freight_value"]:
        suite_items.add_expectation(
            ExpectColumnValuesToNotBeNull(column=col)
        )

    # Unicidade — chave composta simulada via coluna auxiliar
    # GX 1.x suporta ExpectCompoundColumnsToBeUnique
    suite_items.add_expectation(
        ExpectCompoundColumnsToBeUnique(column_list=["order_id", "order_item_id"])
    )

    # Validade — price e freight
    suite_items.add_expectation(
        ExpectColumnValuesToBeBetween(
            column="price", min_value=0.01, max_value=10_000.0
        )
    )
    suite_items.add_expectation(
        ExpectColumnValuesToBeBetween(
            column="freight_value", min_value=0.0, max_value=5_000.0
        )
    )

    # Validade — order_item_id >= 1
    suite_items.add_expectation(
        ExpectColumnValuesToBeBetween(
            column="order_item_id", min_value=1, max_value=999
        )
    )

    # Volume
    suite_items.add_expectation(
        ExpectTableRowCountToBeBetween(min_value=100_000, max_value=125_000)
    )

    result_items = run_suite("order_items", dataframes["order_items"], suite_items, context)
    validation_results["order_items"] = result_items
    status = "PASSOU" if result_items["success"] else "FALHOU"
    print(f"[order_items] {status} | Score: {result_items['score']:.2%} "
          f"| {result_items['passed']}/{result_items['total_expectations']} expectativas")

# %% [markdown]
# ### 5.3 Validação — olist_order_payments_dataset

# %%
if "order_payments" in dataframes:
    suite_payments = context.suites.add(
        ExpectationSuite(name="suite_order_payments")
    )

    # Completude
    for col in ["order_id", "payment_sequential", "payment_type",
                "payment_installments", "payment_value"]:
        suite_payments.add_expectation(
            ExpectColumnValuesToNotBeNull(column=col)
        )

    # Unicidade — chave composta
    suite_payments.add_expectation(
        ExpectCompoundColumnsToBeUnique(
            column_list=["order_id", "payment_sequential"]
        )
    )

    # Validade — tipo de pagamento
    suite_payments.add_expectation(
        ExpectColumnValuesToBeInSet(
            column="payment_type",
            value_set=VALID_PAYMENT_TYPES,
        )
    )

    # Validade — valor do pagamento
    suite_payments.add_expectation(
        ExpectColumnValuesToBeBetween(
            column="payment_value", min_value=0.01, max_value=100_000.0
        )
    )

    # Validade — parcelas >= 1
    suite_payments.add_expectation(
        ExpectColumnValuesToBeBetween(
            column="payment_installments", min_value=1, max_value=24
        )
    )

    # Validade — sequential >= 1
    suite_payments.add_expectation(
        ExpectColumnValuesToBeBetween(
            column="payment_sequential", min_value=1, max_value=29
        )
    )

    result_payments = run_suite(
        "order_payments", dataframes["order_payments"], suite_payments, context
    )
    validation_results["order_payments"] = result_payments
    status = "PASSOU" if result_payments["success"] else "FALHOU"
    print(f"[order_payments] {status} | Score: {result_payments['score']:.2%} "
          f"| {result_payments['passed']}/{result_payments['total_expectations']} expectativas")

# %% [markdown]
# ### 5.4 Validação — olist_order_reviews_dataset

# %%
if "order_reviews" in dataframes:
    suite_reviews = context.suites.add(
        ExpectationSuite(name="suite_order_reviews")
    )

    # Completude — campos obrigatórios
    for col in ["review_id", "order_id", "review_score",
                "review_creation_date", "review_answer_timestamp"]:
        suite_reviews.add_expectation(
            ExpectColumnValuesToNotBeNull(column=col)
        )

    # Unicidade — PK
    suite_reviews.add_expectation(
        ExpectColumnValuesToBeUnique(column="review_id")
    )

    # Validade — score entre 1 e 5
    suite_reviews.add_expectation(
        ExpectColumnValuesToBeInSet(
            column="review_score",
            value_set=[1, 2, 3, 4, 5],
        )
    )

    # Validade — comprimento do título (quando presente)
    suite_reviews.add_expectation(
        ExpectColumnValueLengthsToBeBetween(
            column="review_comment_title",
            min_value=1,
            max_value=255,
            mostly=0.99,
        )
    )

    # Volume
    suite_reviews.add_expectation(
        ExpectTableRowCountToBeBetween(min_value=90_000, max_value=110_000)
    )

    result_reviews = run_suite(
        "order_reviews", dataframes["order_reviews"], suite_reviews, context
    )
    validation_results["order_reviews"] = result_reviews
    status = "PASSOU" if result_reviews["success"] else "FALHOU"
    print(f"[order_reviews] {status} | Score: {result_reviews['score']:.2%} "
          f"| {result_reviews['passed']}/{result_reviews['total_expectations']} expectativas")

# %% [markdown]
# ### 5.5 Validação — olist_customers_dataset

# %%
if "customers" in dataframes:
    suite_customers = context.suites.add(
        ExpectationSuite(name="suite_customers")
    )

    # Completude
    for col in ["customer_id", "customer_unique_id",
                "customer_zip_code_prefix", "customer_city", "customer_state"]:
        suite_customers.add_expectation(
            ExpectColumnValuesToNotBeNull(column=col)
        )

    # Unicidade — customer_id é PK desta tabela
    suite_customers.add_expectation(
        ExpectColumnValuesToBeUnique(column="customer_id")
    )

    # Validade — estado brasileiro
    suite_customers.add_expectation(
        ExpectColumnValuesToBeInSet(
            column="customer_state",
            value_set=VALID_STATES_BR,
        )
    )

    # Validade — CEP: 5 dígitos numéricos (como string)
    suite_customers.add_expectation(
        ExpectColumnValuesToMatchRegex(
            column="customer_zip_code_prefix",
            regex=r"^\d{5}$",
        )
    )

    # Validade — comprimento do ZIP (sempre 5)
    suite_customers.add_expectation(
        ExpectColumnValueLengthsToBeBetween(
            column="customer_zip_code_prefix",
            min_value=5,
            max_value=5,
        )
    )

    # Volume
    suite_customers.add_expectation(
        ExpectTableRowCountToBeBetween(min_value=90_000, max_value=110_000)
    )

    result_customers = run_suite(
        "customers", dataframes["customers"], suite_customers, context
    )
    validation_results["customers"] = result_customers
    status = "PASSOU" if result_customers["success"] else "FALHOU"
    print(f"[customers] {status} | Score: {result_customers['score']:.2%} "
          f"| {result_customers['passed']}/{result_customers['total_expectations']} expectativas")

# %% [markdown]
# ### 5.6 Validação — olist_products_dataset

# %%
if "products" in dataframes:
    # Renomear colunas com typo antes das validações
    df_products = dataframes["products"].copy()
    rename_map = {}
    if "product_name_lenght" in df_products.columns:
        rename_map["product_name_lenght"] = "product_name_length"
    if "product_description_lenght" in df_products.columns:
        rename_map["product_description_lenght"] = "product_description_length"
    if rename_map:
        df_products = df_products.rename(columns=rename_map)
        print(f"  [INFO] Colunas renomeadas (typo corrigido): {rename_map}")

    suite_products = context.suites.add(
        ExpectationSuite(name="suite_products")
    )

    # Completude — apenas product_id é obrigatório
    suite_products.add_expectation(
        ExpectColumnValuesToNotBeNull(column="product_id")
    )

    # Unicidade — PK
    suite_products.add_expectation(
        ExpectColumnValuesToBeUnique(column="product_id")
    )

    # Completude parcial — categoria pode ser nula, mas <= 5% de nulos
    suite_products.add_expectation(
        ExpectColumnValuesToNotBeNull(column="product_category_name", mostly=0.95)
    )

    # Validade — dimensões físicas positivas (quando não nulas)
    for dim_col in ["product_weight_g", "product_length_cm",
                    "product_height_cm", "product_width_cm"]:
        if dim_col in df_products.columns:
            suite_products.add_expectation(
                ExpectColumnValuesToBeBetween(
                    column=dim_col,
                    min_value=1,
                    max_value=100_000,
                    mostly=0.999,
                )
            )

    # Validade — fotos >= 1 quando presente
    if "product_photos_qty" in df_products.columns:
        suite_products.add_expectation(
            ExpectColumnValuesToBeBetween(
                column="product_photos_qty",
                min_value=1,
                max_value=20,
                mostly=0.999,
            )
        )

    # Volume
    suite_products.add_expectation(
        ExpectTableRowCountToBeBetween(min_value=28_000, max_value=38_000)
    )

    result_products = run_suite("products", df_products, suite_products, context)
    validation_results["products"] = result_products
    status = "PASSOU" if result_products["success"] else "FALHOU"
    print(f"[products] {status} | Score: {result_products['score']:.2%} "
          f"| {result_products['passed']}/{result_products['total_expectations']} expectativas")

# %% [markdown]
# ### 5.7 Validação — olist_sellers_dataset

# %%
if "sellers" in dataframes:
    suite_sellers = context.suites.add(
        ExpectationSuite(name="suite_sellers")
    )

    # Completude
    for col in ["seller_id", "seller_zip_code_prefix",
                "seller_city", "seller_state"]:
        suite_sellers.add_expectation(
            ExpectColumnValuesToNotBeNull(column=col)
        )

    # Unicidade — PK
    suite_sellers.add_expectation(
        ExpectColumnValuesToBeUnique(column="seller_id")
    )

    # Validade — estado
    suite_sellers.add_expectation(
        ExpectColumnValuesToBeInSet(
            column="seller_state",
            value_set=VALID_STATES_BR,
        )
    )

    # Validade — ZIP 5 dígitos
    suite_sellers.add_expectation(
        ExpectColumnValuesToMatchRegex(
            column="seller_zip_code_prefix",
            regex=r"^\d{5}$",
        )
    )

    # Volume
    suite_sellers.add_expectation(
        ExpectTableRowCountToBeBetween(min_value=2_500, max_value=4_000)
    )

    result_sellers = run_suite("sellers", dataframes["sellers"], suite_sellers, context)
    validation_results["sellers"] = result_sellers
    status = "PASSOU" if result_sellers["success"] else "FALHOU"
    print(f"[sellers] {status} | Score: {result_sellers['score']:.2%} "
          f"| {result_sellers['passed']}/{result_sellers['total_expectations']} expectativas")

# %% [markdown]
# ### 5.8 Validação — olist_geolocation_dataset

# %%
if "geolocation" in dataframes:
    suite_geo = context.suites.add(
        ExpectationSuite(name="suite_geolocation")
    )

    # Completude
    for col in ["geolocation_zip_code_prefix", "geolocation_lat",
                "geolocation_lng", "geolocation_city", "geolocation_state"]:
        suite_geo.add_expectation(
            ExpectColumnValuesToNotBeNull(column=col)
        )

    # Validade — coordenadas dentro do Brasil
    # Latitude: -33.75 (RS extremo sul) a 5.27 (RR extremo norte)
    suite_geo.add_expectation(
        ExpectColumnValuesToBeBetween(
            column="geolocation_lat",
            min_value=-33.75,
            max_value=5.27,
            mostly=0.999,
        )
    )
    # Longitude: -73.99 (AC extremo oeste) a -28.85 (PB extremo leste)
    suite_geo.add_expectation(
        ExpectColumnValuesToBeBetween(
            column="geolocation_lng",
            min_value=-73.99,
            max_value=-28.85,
            mostly=0.999,
        )
    )

    # Validade — estado
    suite_geo.add_expectation(
        ExpectColumnValuesToBeInSet(
            column="geolocation_state",
            value_set=VALID_STATES_BR,
        )
    )

    # Validade — ZIP 5 dígitos
    suite_geo.add_expectation(
        ExpectColumnValuesToMatchRegex(
            column="geolocation_zip_code_prefix",
            regex=r"^\d{5}$",
        )
    )

    # Volume — ~1M registros esperados
    suite_geo.add_expectation(
        ExpectTableRowCountToBeBetween(min_value=900_000, max_value=1_100_000)
    )

    result_geo = run_suite("geolocation", dataframes["geolocation"], suite_geo, context)
    validation_results["geolocation"] = result_geo
    status = "PASSOU" if result_geo["success"] else "FALHOU"
    print(f"[geolocation] {status} | Score: {result_geo['score']:.2%} "
          f"| {result_geo['passed']}/{result_geo['total_expectations']} expectativas")

# %% [markdown]
# ### 5.9 Validação — product_category_name_translation

# %%
if "category_translation" in dataframes:
    suite_cat = context.suites.add(
        ExpectationSuite(name="suite_category_translation")
    )

    # Completude — ambas as colunas são obrigatórias
    suite_cat.add_expectation(
        ExpectColumnValuesToNotBeNull(column="product_category_name")
    )
    suite_cat.add_expectation(
        ExpectColumnValuesToNotBeNull(column="product_category_name_english")
    )

    # Unicidade — ambas são chaves
    suite_cat.add_expectation(
        ExpectColumnValuesToBeUnique(column="product_category_name")
    )
    suite_cat.add_expectation(
        ExpectColumnValuesToBeUnique(column="product_category_name_english")
    )

    # Volume — tabela de lookup pequena (entre 60 e 80 categorias)
    suite_cat.add_expectation(
        ExpectTableRowCountToBeBetween(min_value=60, max_value=80)
    )

    result_cat = run_suite(
        "category_translation",
        dataframes["category_translation"],
        suite_cat,
        context,
    )
    validation_results["category_translation"] = result_cat
    status = "PASSOU" if result_cat["success"] else "FALHOU"
    print(f"[category_translation] {status} | Score: {result_cat['score']:.2%} "
          f"| {result_cat['passed']}/{result_cat['total_expectations']} expectativas")

# %% [markdown]
# ## 6. Verificações de Consistência Referencial e Temporal
#
# Estas verificações cruzam dados entre tabelas — não podem ser expressas como
# expectativas individuais de coluna. São executadas com pandas e os resultados
# são integrados ao relatório final.

# %%
consistency_results: list[dict] = []


def check_referential_integrity(
    child_df: pd.DataFrame,
    child_col: str,
    parent_df: pd.DataFrame,
    parent_col: str,
    description: str,
) -> dict:
    """Verifica se todos os valores de child_col existem em parent_col."""
    child_values = set(child_df[child_col].dropna())
    parent_values = set(parent_df[parent_col].dropna())
    orphans = child_values - parent_values
    total = len(child_values)
    ok_count = total - len(orphans)
    score = ok_count / total if total > 0 else 1.0
    passed = len(orphans) == 0

    result = {
        "check": description,
        "type": "referential_integrity",
        "total_values": total,
        "orphan_count": len(orphans),
        "score": round(score, 4),
        "passed": passed,
        "sample_orphans": list(orphans)[:5] if orphans else [],
    }
    status = "PASSOU" if passed else "FALHOU"
    print(f"  [{status}] {description}")
    print(f"         Valores únicos: {total:,} | Órfãos: {len(orphans):,} | Score: {score:.2%}")
    return result


def check_date_order(
    df: pd.DataFrame,
    earlier_col: str,
    later_col: str,
    description: str,
    threshold: float = 0.995,
) -> dict:
    """Verifica se earlier_col é sempre <= later_col (ignorando nulos)."""
    mask_both = df[earlier_col].notna() & df[later_col].notna()
    df_sub = df[mask_both].copy()

    try:
        earlier = pd.to_datetime(df_sub[earlier_col], errors="coerce")
        later = pd.to_datetime(df_sub[later_col], errors="coerce")
        violations = (earlier > later).sum()
        total = len(df_sub)
        score = 1.0 - (violations / total) if total > 0 else 1.0
        passed = score >= threshold
    except Exception as e:
        violations = -1
        score = 0.0
        passed = False

    result = {
        "check": description,
        "type": "date_consistency",
        "total_pairs": len(df_sub),
        "violations": int(violations),
        "score": round(score, 4),
        "passed": passed,
        "threshold": threshold,
    }
    status = "PASSOU" if passed else "FALHOU"
    print(f"  [{status}] {description}")
    print(f"         Pares avaliados: {len(df_sub):,} | Violações: {violations} | Score: {score:.2%}")
    return result


print("=" * 70)
print("VERIFICAÇÕES DE CONSISTÊNCIA REFERENCIAL E TEMPORAL")
print("=" * 70)

# --- Integridade Referencial ---
print("\n[Integridade Referencial]")

if "orders" in dataframes and "customers" in dataframes:
    r = check_referential_integrity(
        dataframes["orders"], "customer_id",
        dataframes["customers"], "customer_id",
        "orders.customer_id → customers.customer_id",
    )
    consistency_results.append(r)

if "order_items" in dataframes and "orders" in dataframes:
    r = check_referential_integrity(
        dataframes["order_items"], "order_id",
        dataframes["orders"], "order_id",
        "order_items.order_id → orders.order_id",
    )
    consistency_results.append(r)

if "order_items" in dataframes and "products" in dataframes:
    r = check_referential_integrity(
        dataframes["order_items"], "product_id",
        dataframes["products"], "product_id",
        "order_items.product_id → products.product_id",
    )
    consistency_results.append(r)

if "order_items" in dataframes and "sellers" in dataframes:
    r = check_referential_integrity(
        dataframes["order_items"], "seller_id",
        dataframes["sellers"], "seller_id",
        "order_items.seller_id → sellers.seller_id",
    )
    consistency_results.append(r)

if "order_payments" in dataframes and "orders" in dataframes:
    r = check_referential_integrity(
        dataframes["order_payments"], "order_id",
        dataframes["orders"], "order_id",
        "order_payments.order_id → orders.order_id",
    )
    consistency_results.append(r)

if "order_reviews" in dataframes and "orders" in dataframes:
    r = check_referential_integrity(
        dataframes["order_reviews"], "order_id",
        dataframes["orders"], "order_id",
        "order_reviews.order_id → orders.order_id",
    )
    consistency_results.append(r)

# --- Consistência Temporal ---
print("\n[Consistência Temporal — Ordem Cronológica das Datas do Pedido]")

if "orders" in dataframes:
    df_ord = dataframes["orders"]

    r1 = check_date_order(
        df_ord,
        "order_purchase_timestamp",
        "order_approved_at",
        "purchase_timestamp <= approved_at",
    )
    consistency_results.append(r1)

    r2 = check_date_order(
        df_ord,
        "order_approved_at",
        "order_delivered_carrier_date",
        "approved_at <= delivered_carrier_date",
    )
    consistency_results.append(r2)

    r3 = check_date_order(
        df_ord,
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "delivered_carrier_date <= delivered_customer_date",
    )
    consistency_results.append(r3)

    r4 = check_date_order(
        df_ord,
        "order_purchase_timestamp",
        "order_estimated_delivery_date",
        "purchase_timestamp <= estimated_delivery_date",
    )
    consistency_results.append(r4)

if "order_reviews" in dataframes:
    df_rev = dataframes["order_reviews"]
    r5 = check_date_order(
        df_rev,
        "review_creation_date",
        "review_answer_timestamp",
        "review_creation_date <= review_answer_timestamp",
    )
    consistency_results.append(r5)

# %% [markdown]
# ## 7. Relatório Consolidado de Qualidade

# %%
def build_quality_report(
    validation_results: dict,
    consistency_results: list,
    eda_results: dict,
) -> dict:
    """Consolida todos os resultados em um relatório estruturado."""

    # Score por tabela (GE)
    table_scores = {}
    for table, res in validation_results.items():
        if "score" in res:
            table_scores[table] = res["score"]

    # Score de consistência
    consistency_scores = [r["score"] for r in consistency_results if "score" in r]
    consistency_avg = sum(consistency_scores) / len(consistency_scores) if consistency_scores else 1.0

    # Score global (média ponderada)
    all_scores = list(table_scores.values()) + [consistency_avg]
    global_score = sum(all_scores) / len(all_scores) if all_scores else 0.0

    # Contagens gerais
    total_exp = sum(r.get("total_expectations", 0) for r in validation_results.values())
    total_passed = sum(r.get("passed", 0) for r in validation_results.values())
    total_failed = sum(r.get("failed", 0) for r in validation_results.values())
    consistency_passed = sum(1 for r in consistency_results if r.get("passed", False))
    consistency_failed = len(consistency_results) - consistency_passed

    report = {
        "generated_at": datetime.now().isoformat(),
        "dataset": "Olist Brazilian E-Commerce",
        "tool": f"Great Expectations {gx.__version__}",
        "global_score": round(global_score, 4),
        "global_status": "APROVADO" if global_score >= 0.95 else "REPROVADO",
        "summary": {
            "tables_validated": len(validation_results),
            "ge_expectations_total": total_exp,
            "ge_expectations_passed": total_passed,
            "ge_expectations_failed": total_failed,
            "consistency_checks_total": len(consistency_results),
            "consistency_checks_passed": consistency_passed,
            "consistency_checks_failed": consistency_failed,
        },
        "table_scores": table_scores,
        "consistency_score": round(consistency_avg, 4),
        "consistency_details": consistency_results,
        "table_details": validation_results,
        "eda_profiles": eda_results,
    }
    return report


quality_report = build_quality_report(
    validation_results, consistency_results, eda_results
)

print("=" * 70)
print("RELATÓRIO CONSOLIDADO DE QUALIDADE DE DADOS")
print("=" * 70)
print(f"\nDataset:           {quality_report['dataset']}")
print(f"Gerado em:         {quality_report['generated_at']}")
print(f"Ferramenta:        {quality_report['tool']}")
print(f"\n{'SCORE GLOBAL':.<40} {quality_report['global_score']:.2%}")
print(f"{'STATUS':.<40} {quality_report['global_status']}")
print(f"\n{'Tabelas validadas':.<40} {quality_report['summary']['tables_validated']}")
print(f"{'Expectativas GE total':.<40} {quality_report['summary']['ge_expectations_total']}")
print(f"{'Expectativas GE aprovadas':.<40} {quality_report['summary']['ge_expectations_passed']}")
print(f"{'Expectativas GE reprovadas':.<40} {quality_report['summary']['ge_expectations_failed']}")
print(f"{'Checks de consistência total':.<40} {quality_report['summary']['consistency_checks_total']}")
print(f"{'Checks de consistência aprovados':.<40} {quality_report['summary']['consistency_checks_passed']}")

print("\n--- Score por Tabela ---")
for table, score in quality_report["table_scores"].items():
    bar = "=" * int(score * 30)
    status = "PASSOU" if score >= 0.95 else "ATENCAO" if score >= 0.80 else "FALHOU"
    print(f"  {table:30s} {score:.2%} [{bar:<30}] {status}")

print(f"\n{'Score de Consistência':.<40} {quality_report['consistency_score']:.2%}")

# Salvar relatório JSON
report_json_path = REPORT_DIR / "quality_report.json"
with open(report_json_path, "w", encoding="utf-8") as f:
    json.dump(quality_report, f, indent=2, ensure_ascii=False, default=str)
print(f"\nRelatório JSON salvo em: {report_json_path}")

# %% [markdown]
# ## 8. Visualizações do Relatório de Qualidade

# %%
def plot_quality_dashboard(quality_report: dict, output_dir: Path) -> None:
    """Gera visualizações do score de qualidade por tabela e dimensão."""

    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle(
        "Dashboard de Qualidade de Dados — Olist Brazilian E-Commerce",
        fontsize=16, fontweight="bold", y=1.01
    )

    # Cores por nível de qualidade
    def score_color(score: float) -> str:
        if score >= 0.95:
            return "#2ecc71"   # verde
        elif score >= 0.80:
            return "#f39c12"   # amarelo
        else:
            return "#e74c3c"   # vermelho

    # --- Plot 1: Score por Tabela ---
    ax1 = axes[0, 0]
    tables = list(quality_report["table_scores"].keys())
    scores = list(quality_report["table_scores"].values())
    colors = [score_color(s) for s in scores]

    bars = ax1.barh(tables, scores, color=colors, edgecolor="white", height=0.6)
    ax1.axvline(x=0.95, color="#e74c3c", linestyle="--", linewidth=1.5,
                label="Threshold 95%")
    ax1.set_xlim(0, 1.05)
    ax1.set_xlabel("Score de Qualidade")
    ax1.set_title("Score de Qualidade por Tabela", fontweight="bold")
    ax1.legend(fontsize=9)

    for bar, score in zip(bars, scores):
        ax1.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height() / 2,
                 f"{score:.1%}", va="center", fontsize=9)

    # --- Plot 2: Distribuição de Expectativas (Pass/Fail) ---
    ax2 = axes[0, 1]
    exp_data = {
        name: {
            "Aprovadas": res.get("passed", 0),
            "Reprovadas": res.get("failed", 0),
        }
        for name, res in quality_report["table_details"].items()
        if "passed" in res
    }

    if exp_data:
        df_exp = pd.DataFrame(exp_data).T
        df_exp.plot(
            kind="bar", ax=ax2, color=["#2ecc71", "#e74c3c"],
            edgecolor="white", width=0.7
        )
        ax2.set_title("Expectativas por Tabela (Aprovadas vs Reprovadas)", fontweight="bold")
        ax2.set_xlabel("")
        ax2.set_ylabel("Número de Expectativas")
        ax2.tick_params(axis="x", rotation=45)
        ax2.legend()

    # --- Plot 3: Nulos por Tabela (heatmap simplificado) ---
    ax3 = axes[1, 0]
    null_data = {}
    for name, profile in quality_report.get("eda_profiles", {}).items():
        null_data[name] = profile.get("nulos_por_coluna", {})

    if null_data:
        # Coletar todas as colunas com nulos
        all_cols_with_nulls = set()
        for cols in null_data.values():
            all_cols_with_nulls.update(cols.keys())

        if all_cols_with_nulls:
            null_df = pd.DataFrame(
                {tbl: {col: null_data[tbl].get(col, 0) for col in all_cols_with_nulls}
                 for tbl in null_data}
            ).T.fillna(0)

            sns.heatmap(
                null_df, ax=ax3, cmap="RdYlGn_r", annot=True, fmt=".1f",
                linewidths=0.5, cbar_kws={"label": "% Nulos"},
                annot_kws={"size": 8}
            )
            ax3.set_title("Taxa de Nulos por Tabela/Coluna (%)", fontweight="bold")
            ax3.tick_params(axis="x", rotation=45)
            ax3.tick_params(axis="y", rotation=0)
        else:
            ax3.text(0.5, 0.5, "Sem nulos detectados\nnas tabelas carregadas",
                     ha="center", va="center", fontsize=12)
            ax3.set_title("Taxa de Nulos por Tabela/Coluna (%)", fontweight="bold")

    # --- Plot 4: Score Global Gauge ---
    ax4 = axes[1, 1]
    global_score = quality_report["global_score"]
    global_status = quality_report["global_status"]

    theta = np.linspace(0, np.pi, 200)
    # Background arco cinza
    ax4.plot(np.cos(theta), np.sin(theta), linewidth=20, color="#ecf0f1", solid_capstyle="round")
    # Arco colorido proporcional ao score
    filled_theta = np.linspace(0, np.pi * global_score, 200)
    gauge_color = score_color(global_score)
    ax4.plot(np.cos(filled_theta), np.sin(filled_theta), linewidth=20,
             color=gauge_color, solid_capstyle="round")

    # Ponteiro
    angle = np.pi * (1 - global_score)
    ax4.annotate("", xy=(np.cos(angle) * 0.7, np.sin(angle) * 0.7),
                 xytext=(0, 0),
                 arrowprops=dict(arrowstyle="->", color="#2c3e50", lw=2.5))

    ax4.text(0, 0.25, f"{global_score:.1%}", ha="center", va="center",
             fontsize=28, fontweight="bold", color=gauge_color)
    ax4.text(0, -0.05, global_status, ha="center", va="center",
             fontsize=14, fontweight="bold",
             color="#2ecc71" if global_status == "APROVADO" else "#e74c3c")
    ax4.text(0, -0.25, "Score Global de Qualidade", ha="center", va="center",
             fontsize=10, color="#7f8c8d")

    ax4.text(-1.1, 0, "0%", ha="center", va="center", fontsize=9, color="#7f8c8d")
    ax4.text(1.1, 0, "100%", ha="center", va="center", fontsize=9, color="#7f8c8d")
    ax4.text(0, 1.15, "95% (threshold)", ha="center", va="center",
             fontsize=8, color="#e74c3c")

    ax4.set_xlim(-1.3, 1.3)
    ax4.set_ylim(-0.5, 1.4)
    ax4.set_aspect("equal")
    ax4.axis("off")
    ax4.set_title("Score Global de Qualidade", fontweight="bold")

    plt.tight_layout()
    chart_path = output_dir / "quality_dashboard.png"
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.show()
    print(f"Dashboard salvo em: {chart_path}")


plot_quality_dashboard(quality_report, REPORT_DIR)

# %% [markdown]
# ## 9. Exportação do Relatório HTML

# %%
def generate_html_report(quality_report: dict, output_dir: Path) -> Path:
    """Gera um relatório HTML standalone com os resultados de qualidade."""

    def score_badge(score: float) -> str:
        if score >= 0.95:
            return f'<span class="badge badge-green">{score:.1%}</span>'
        elif score >= 0.80:
            return f'<span class="badge badge-yellow">{score:.1%}</span>'
        else:
            return f'<span class="badge badge-red">{score:.1%}</span>'

    def status_icon(passed: bool) -> str:
        return "&#10003;" if passed else "&#10007;"

    def status_class(passed: bool) -> str:
        return "pass" if passed else "fail"

    # Gerar linhas da tabela de expectativas GE
    ge_rows = ""
    for table, res in quality_report["table_details"].items():
        if "total_expectations" not in res:
            continue
        row_class = "pass" if res.get("success", False) else "fail"
        ge_rows += f"""
        <tr class="{row_class}">
            <td><code>{table}</code></td>
            <td>{res.get('total_expectations', 0)}</td>
            <td>{res.get('passed', 0)}</td>
            <td>{res.get('failed', 0)}</td>
            <td>{score_badge(res.get('score', 0))}</td>
            <td>{status_icon(res.get('success', False))}</td>
        </tr>"""

    # Gerar linhas da tabela de consistência
    consistency_rows = ""
    for check in quality_report["consistency_details"]:
        row_class = status_class(check.get("passed", False))
        consistency_rows += f"""
        <tr class="{row_class}">
            <td>{check.get('check', '')}</td>
            <td>{check.get('type', '')}</td>
            <td>{check.get('total_values', check.get('total_pairs', '-')):,}</td>
            <td>{check.get('orphan_count', check.get('violations', '-'))}</td>
            <td>{score_badge(check.get('score', 0))}</td>
            <td>{status_icon(check.get('passed', False))}</td>
        </tr>"""

    # Gerar linhas de perfil EDA
    eda_rows = ""
    for table, profile in quality_report.get("eda_profiles", {}).items():
        eda_rows += f"""
        <tr>
            <td><code>{table}</code></td>
            <td>{profile.get('total_linhas', 0):,}</td>
            <td>{profile.get('total_colunas', 0)}</td>
            <td>{profile.get('duplicatas_completas', 0):,}</td>
            <td>{profile.get('pct_duplicatas', 0):.2f}%</td>
            <td>{profile.get('colunas_com_nulos', 0)}</td>
        </tr>"""

    global_score = quality_report["global_score"]
    global_status = quality_report["global_status"]
    status_color = "#2ecc71" if global_status == "APROVADO" else "#e74c3c"
    summary = quality_report["summary"]

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Relatório de Qualidade de Dados — Olist | Dadosfera Case</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          background: #f5f6fa; color: #2c3e50; line-height: 1.6; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 2rem 1rem; }}
  header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
             color: white; padding: 2.5rem 2rem; border-radius: 12px; margin-bottom: 2rem; }}
  header h1 {{ font-size: 1.8rem; margin-bottom: 0.5rem; }}
  header .meta {{ opacity: 0.7; font-size: 0.9rem; }}
  .score-hero {{ display: flex; gap: 1rem; margin-bottom: 2rem; flex-wrap: wrap; }}
  .score-card {{ background: white; border-radius: 12px; padding: 1.5rem 2rem;
                  box-shadow: 0 2px 12px rgba(0,0,0,0.08); flex: 1; min-width: 180px; }}
  .score-card .value {{ font-size: 2.5rem; font-weight: 800; color: {status_color}; }}
  .score-card .label {{ font-size: 0.85rem; color: #7f8c8d; text-transform: uppercase;
                         letter-spacing: 0.05em; margin-top: 0.25rem; }}
  .card {{ background: white; border-radius: 12px; padding: 1.5rem;
            box-shadow: 0 2px 12px rgba(0,0,0,0.08); margin-bottom: 1.5rem; }}
  .card h2 {{ font-size: 1.1rem; margin-bottom: 1rem; color: #2c3e50;
               border-bottom: 2px solid #ecf0f1; padding-bottom: 0.5rem; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
  th {{ background: #f8f9fa; padding: 0.75rem 1rem; text-align: left;
         font-weight: 600; color: #555; font-size: 0.8rem; text-transform: uppercase; }}
  td {{ padding: 0.7rem 1rem; border-bottom: 1px solid #f0f0f0; vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  tr.pass td:last-child {{ color: #27ae60; font-weight: bold; font-size: 1.1rem; }}
  tr.fail td:last-child {{ color: #e74c3c; font-weight: bold; font-size: 1.1rem; }}
  tr.fail {{ background: #fff5f5; }}
  tr.pass {{ background: #f9fff9; }}
  .badge {{ display: inline-block; padding: 0.2rem 0.6rem; border-radius: 20px;
             font-weight: 700; font-size: 0.85rem; }}
  .badge-green {{ background: #d5f5e3; color: #27ae60; }}
  .badge-yellow {{ background: #fef9e7; color: #f39c12; }}
  .badge-red {{ background: #fdecea; color: #e74c3c; }}
  code {{ background: #f0f0f0; padding: 0.1rem 0.4rem; border-radius: 4px;
           font-size: 0.85em; }}
  .threshold-note {{ font-size: 0.8rem; color: #7f8c8d; margin-top: 0.5rem; }}
  footer {{ text-align: center; color: #aaa; font-size: 0.8rem; padding: 2rem 0 0; }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>Relatório de Qualidade de Dados</h1>
    <div class="meta">
      Dataset: Olist Brazilian E-Commerce &nbsp;|&nbsp;
      Ferramenta: {quality_report['tool']} &nbsp;|&nbsp;
      Gerado em: {quality_report['generated_at'][:19].replace('T', ' ')}
    </div>
  </header>

  <div class="score-hero">
    <div class="score-card">
      <div class="value">{global_score:.1%}</div>
      <div class="label">Score Global</div>
    </div>
    <div class="score-card">
      <div class="value" style="color: {status_color};">{global_status}</div>
      <div class="label">Status (threshold: 95%)</div>
    </div>
    <div class="score-card">
      <div class="value">{summary['ge_expectations_total']}</div>
      <div class="label">Expectativas GE</div>
    </div>
    <div class="score-card">
      <div class="value">{summary['ge_expectations_passed']}</div>
      <div class="label">Aprovadas</div>
    </div>
    <div class="score-card">
      <div class="value" style="color: #e74c3c;">{summary['ge_expectations_failed']}</div>
      <div class="label">Reprovadas</div>
    </div>
    <div class="score-card">
      <div class="value">{summary['consistency_checks_total']}</div>
      <div class="label">Checks de Consistência</div>
    </div>
  </div>

  <div class="card">
    <h2>Perfil Exploratório por Tabela</h2>
    <table>
      <thead>
        <tr>
          <th>Tabela</th>
          <th>Total Linhas</th>
          <th>Colunas</th>
          <th>Duplicatas</th>
          <th>% Dupl.</th>
          <th>Colunas c/ Nulos</th>
        </tr>
      </thead>
      <tbody>{eda_rows}</tbody>
    </table>
  </div>

  <div class="card">
    <h2>Resultados Great Expectations — Suites por Tabela</h2>
    <p class="threshold-note">Threshold de aprovacao: score &ge; 95%. Vermelho = abaixo do threshold.</p>
    <br/>
    <table>
      <thead>
        <tr>
          <th>Tabela</th>
          <th>Total Expect.</th>
          <th>Aprovadas</th>
          <th>Reprovadas</th>
          <th>Score</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>{ge_rows}</tbody>
    </table>
  </div>

  <div class="card">
    <h2>Verificacoes de Consistencia (Referencial e Temporal)</h2>
    <table>
      <thead>
        <tr>
          <th>Verificacao</th>
          <th>Tipo</th>
          <th>Total Avaliado</th>
          <th>Violacoes</th>
          <th>Score</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>{consistency_rows}</tbody>
    </table>
  </div>

  <footer>
    <p>Gerado por Great Expectations {gx.__version__} &nbsp;|&nbsp;
       Case Tecnico Dadosfera &nbsp;|&nbsp;
       Dataset: Olist Brazilian E-Commerce (Kaggle)</p>
  </footer>
</div>
</body>
</html>
"""

    html_path = output_dir / "index.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    return html_path


html_path = generate_html_report(quality_report, REPORT_DIR)
print(f"\nRelatório HTML gerado em: {html_path}")
print("\nPara visualizar no Colab:")
print("  from IPython.display import IFrame")
print(f"  IFrame(src='{html_path}', width='100%', height=800)")

# %% [markdown]
# ## 10. Abrir Relatório no Colab (opcional)

# %%
try:
    from IPython.display import IFrame, display
    display(IFrame(src=str(html_path), width="100%", height=800))
except Exception:
    print(f"Relatório disponível em: {html_path.resolve()}")
    print("Abra o arquivo no navegador para visualizar o relatório completo.")

# %% [markdown]
# ## 11. Sumário Final

# %%
print("=" * 70)
print("SUMARIO FINAL — QUALIDADE DE DADOS OLIST")
print("=" * 70)

print(f"\nScore Global:  {quality_report['global_score']:.2%}")
print(f"Status:        {quality_report['global_status']}")
print(f"\nArquivos gerados:")
print(f"  - {REPORT_DIR / 'quality_report.json'}   (dados brutos JSON)")
print(f"  - {REPORT_DIR / 'quality_dashboard.png'} (visualizacoes)")
print(f"  - {REPORT_DIR / 'index.html'}            (relatorio HTML)")

print("\nPróximos passos recomendados:")
print("  1. Investigar os checks de consistência que falharam (ver consistency_results)")
print("  2. Aplicar estratégias de remediação documentadas em docs/04_data_quality.md")
print("  3. Reexecutar validações após aplicar correções na Trusted Zone")
print("  4. Integrar este script ao pipeline de ingestão (ex: após carga na Raw Zone)")
print("  5. Configurar alertas para falhas críticas (score < 0.95)")
