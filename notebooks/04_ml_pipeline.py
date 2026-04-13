# %% [markdown]
# # Pipeline de ML — Recomendacao de Produtos e Previsao de Entrega
#
# **Caso Tecnico:** Dadosfera Data Platform
# **Notebook:** 04 — ML Pipeline (Colab-compatible)
# **Data:** Abril de 2026
# **Versao:** 1.0
#
# ---
#
# ## Objetivos
#
# Este notebook implementa dois pipelines de Machine Learning sobre o dataset Olist:
#
# 1. **Recomendacao de Produtos** — filtragem baseada em conteudo via TF-IDF + similaridade de cosseno
# 2. **Previsao de Tempo de Entrega** — Random Forest Regressor com analise de importancia de features
#
# ## Arquitetura do Pipeline
#
# ```
# Raw CSVs
#    |
#    v
# [ETL: Raw → Trusted]   ← limpeza, tipos, deduplicacao
#    |
#    v
# [ETL: Trusted → Refined]  ← star schema (fact_orders, fact_reviews, dims)
#    |
#    v
# [Feature Engineering]
#    |
#    +──→ [ML: Recomendacao de Produtos (TF-IDF + Cosine Similarity)]
#    |
#    +──→ [ML: Previsao de Entrega (Random Forest Regressor)]
#    |
#    v
# [Artefatos: modelos serializados, metricas, parquet refinado]
# ```

# %% [markdown]
# ## 1. Instalacao e Importacoes

# %%
# Instalar dependencias se necessario (Google Colab)
import subprocess
import sys


def install_if_missing(package: str) -> None:
    """Install a package if it is not already available."""
    try:
        __import__(package.split("==")[0].replace("-", "_"))
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", package])


for pkg in ["scikit-learn", "joblib", "tqdm"]:
    install_if_missing(pkg)

# %%
from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.preprocessing import LabelEncoder
from tqdm import tqdm

warnings.filterwarnings("ignore")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# %% [markdown]
# ## 2. Configuracao e Paths

# %%
@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Immutable configuration for the ML pipeline."""

    data_dir: Path = field(default=Path("../data"))
    output_dir: Path = field(default=Path("../data/refined"))
    models_dir: Path = field(default=Path("../models"))
    random_state: int = 42
    test_size: float = 0.2
    n_estimators: int = 200
    tfidf_max_features: int = 500
    top_n_recommendations: int = 10
    min_orders_for_rec: int = 3

    def __post_init__(self) -> None:
        object.__setattr__(self, "output_dir", Path(self.output_dir))
        object.__setattr__(self, "models_dir", Path(self.models_dir))


@dataclass(slots=True)
class OlistDataset:
    """Container for all raw Olist DataFrames."""

    orders: pd.DataFrame = field(default_factory=pd.DataFrame)
    order_items: pd.DataFrame = field(default_factory=pd.DataFrame)
    order_payments: pd.DataFrame = field(default_factory=pd.DataFrame)
    order_reviews: pd.DataFrame = field(default_factory=pd.DataFrame)
    customers: pd.DataFrame = field(default_factory=pd.DataFrame)
    products: pd.DataFrame = field(default_factory=pd.DataFrame)
    sellers: pd.DataFrame = field(default_factory=pd.DataFrame)
    geolocation: pd.DataFrame = field(default_factory=pd.DataFrame)
    category_translation: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def is_complete(self) -> bool:
        return all(
            not df.empty
            for df in [
                self.orders,
                self.order_items,
                self.products,
                self.customers,
                self.sellers,
            ]
        )


@dataclass(slots=True)
class TrustedDataset:
    """Cleaned and validated DataFrames (Trusted zone)."""

    orders: pd.DataFrame = field(default_factory=pd.DataFrame)
    order_items: pd.DataFrame = field(default_factory=pd.DataFrame)
    order_payments: pd.DataFrame = field(default_factory=pd.DataFrame)
    order_reviews: pd.DataFrame = field(default_factory=pd.DataFrame)
    customers: pd.DataFrame = field(default_factory=pd.DataFrame)
    products: pd.DataFrame = field(default_factory=pd.DataFrame)
    sellers: pd.DataFrame = field(default_factory=pd.DataFrame)


@dataclass(slots=True)
class RefinedDataset:
    """Star schema tables (Refined zone)."""

    fact_orders: pd.DataFrame = field(default_factory=pd.DataFrame)
    fact_reviews: pd.DataFrame = field(default_factory=pd.DataFrame)
    dim_customer: pd.DataFrame = field(default_factory=pd.DataFrame)
    dim_product: pd.DataFrame = field(default_factory=pd.DataFrame)
    dim_seller: pd.DataFrame = field(default_factory=pd.DataFrame)
    dim_date: pd.DataFrame = field(default_factory=pd.DataFrame)
    dim_geography: pd.DataFrame = field(default_factory=pd.DataFrame)


@dataclass(slots=True)
class ModelMetrics:
    """Evaluation metrics for a regression model."""

    rmse: float = 0.0
    mae: float = 0.0
    r2: float = 0.0
    cv_rmse_mean: float = 0.0
    cv_rmse_std: float = 0.0

    def __str__(self) -> str:
        return (
            f"RMSE={self.rmse:.2f} | MAE={self.mae:.2f} | R2={self.r2:.4f} | "
            f"CV-RMSE={self.cv_rmse_mean:.2f} ± {self.cv_rmse_std:.2f}"
        )


CFG = PipelineConfig()

# %% [markdown]
# ## 3. Carga dos Dados Brutos (Raw Layer)

# %%
RAW_FILES: dict[str, str] = {
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}

TIMESTAMP_COLS: dict[str, list[str]] = {
    "orders": [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ],
    "order_items": ["shipping_limit_date"],
    "order_reviews": ["review_creation_date", "review_answer_timestamp"],
}


def load_raw_dataset(cfg: PipelineConfig) -> OlistDataset:
    """Load all 9 Olist CSV files from data_dir into an OlistDataset container."""
    dataset = OlistDataset()
    loaded: list[str] = []
    missing: list[str] = []

    for attr, filename in tqdm(RAW_FILES.items(), desc="Carregando CSVs"):
        path = cfg.data_dir / filename
        if not path.exists():
            log.warning("Arquivo nao encontrado: %s", path)
            missing.append(filename)
            continue

        parse_dates = TIMESTAMP_COLS.get(attr, False)
        df = pd.read_csv(path, parse_dates=parse_dates, low_memory=False)
        object.__setattr__(dataset, attr, df) if hasattr(dataset, "__slots__") else setattr(
            dataset, attr, df
        )
        loaded.append(f"{attr} ({len(df):,} linhas)")

    log.info("Carregados: %s", " | ".join(loaded))
    if missing:
        log.warning("Ausentes: %s", ", ".join(missing))

    return dataset


raw = load_raw_dataset(CFG)

log.info("Dataset completo: %s", raw.is_complete)

# %% [markdown]
# ## 4. ETL — Raw → Trusted (Limpeza e Validacao)
#
# Nesta etapa aplicamos:
# - Remocao de duplicatas por chave primaria
# - Tratamento de nulos com estrategias especificas por coluna
# - Correcao de tipos de dados
# - Normalizacao de strings (strip, lower onde aplicavel)
# - Filtros de qualidade (ex.: pedidos com status valido)

# %%
ORDER_STATUS_VALID: frozenset[str] = frozenset(
    {"created", "approved", "processing", "invoiced", "shipped", "delivered", "canceled", "unavailable"}
)


def clean_orders(df: pd.DataFrame) -> pd.DataFrame:
    """Clean olist_orders: dedup, filter status, fill missing dates."""
    df = df.drop_duplicates(subset=["order_id"]).copy()
    df = df[df["order_status"].isin(ORDER_STATUS_VALID)].copy()

    # Timestamps: convert robustly (already parsed if parse_dates worked)
    ts_cols = TIMESTAMP_COLS["orders"]
    for col in ts_cols:
        if col in df.columns and not pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = pd.to_datetime(df[col], errors="coerce")

    log.info("orders: %d linhas apos limpeza", len(df))
    return df


def clean_order_items(df: pd.DataFrame) -> pd.DataFrame:
    """Clean order_items: dedup, non-negative price/freight."""
    df = df.drop_duplicates(subset=["order_id", "order_item_id"]).copy()
    df = df[(df["price"] >= 0) & (df["freight_value"] >= 0)].copy()
    df["price"] = df["price"].fillna(0.0)
    df["freight_value"] = df["freight_value"].fillna(0.0)
    log.info("order_items: %d linhas apos limpeza", len(df))
    return df


def clean_order_payments(df: pd.DataFrame) -> pd.DataFrame:
    """Clean payments: dedup, valid payment_value."""
    df = df.drop_duplicates(subset=["order_id", "payment_sequential"]).copy()
    df = df[df["payment_value"] >= 0].copy()
    df["payment_installments"] = df["payment_installments"].fillna(1).astype(int)
    log.info("order_payments: %d linhas apos limpeza", len(df))
    return df


def clean_order_reviews(df: pd.DataFrame) -> pd.DataFrame:
    """Clean reviews: dedup by review_id, valid scores 1-5."""
    df = df.drop_duplicates(subset=["review_id"]).copy()
    df = df[df["review_score"].between(1, 5)].copy()
    df["review_comment_title"] = df["review_comment_title"].fillna("").str.strip()
    df["review_comment_message"] = df["review_comment_message"].fillna("").str.strip()
    log.info("order_reviews: %d linhas apos limpeza", len(df))
    return df


def clean_customers(df: pd.DataFrame) -> pd.DataFrame:
    """Clean customers: dedup, normalize state codes."""
    df = df.drop_duplicates(subset=["customer_id"]).copy()
    df["customer_state"] = df["customer_state"].str.upper().str.strip()
    df["customer_city"] = df["customer_city"].str.lower().str.strip()
    log.info("customers: %d linhas apos limpeza", len(df))
    return df


def clean_products(df: pd.DataFrame, translation: pd.DataFrame) -> pd.DataFrame:
    """Clean products: fill nulls, add English category, compute volume."""
    df = df.drop_duplicates(subset=["product_id"]).copy()

    numeric_cols = [
        "product_name_lenght",
        "product_description_lenght",
        "product_photos_qty",
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # Volume em cm³
    df["product_volume_cm3"] = (
        df["product_length_cm"] * df["product_height_cm"] * df["product_width_cm"]
    )

    # Categoria em portugues: fallback para 'sem_categoria'
    df["product_category_name"] = (
        df["product_category_name"].fillna("sem_categoria").str.strip().str.lower()
    )

    # Adicionar traducao
    if not translation.empty:
        df = df.merge(translation, on="product_category_name", how="left")
        df["product_category_name_english"] = df["product_category_name_english"].fillna(
            df["product_category_name"]
        )
    else:
        df["product_category_name_english"] = df["product_category_name"]

    log.info("products: %d linhas apos limpeza", len(df))
    return df


def clean_sellers(df: pd.DataFrame) -> pd.DataFrame:
    """Clean sellers: dedup, normalize state."""
    df = df.drop_duplicates(subset=["seller_id"]).copy()
    df["seller_state"] = df["seller_state"].str.upper().str.strip()
    df["seller_city"] = df["seller_city"].str.lower().str.strip()
    log.info("sellers: %d linhas apos limpeza", len(df))
    return df


def build_trusted(raw: OlistDataset) -> TrustedDataset:
    """Run all cleaning steps and return a TrustedDataset."""
    log.info("=== ETL: Raw → Trusted ===")
    return TrustedDataset(
        orders=clean_orders(raw.orders),
        order_items=clean_order_items(raw.order_items),
        order_payments=clean_order_payments(raw.order_payments),
        order_reviews=clean_order_reviews(raw.order_reviews),
        customers=clean_customers(raw.customers),
        products=clean_products(raw.products, raw.category_translation),
        sellers=clean_sellers(raw.sellers),
    )


trusted = build_trusted(raw)
log.info("Trusted layer pronto.")

# %% [markdown]
# ## 5. ETL — Trusted → Refined (Star Schema)
#
# Construcao das tabelas dimensionais e de fatos seguindo o padrao Kimball:
#
# ```
# fact_orders ──→ dim_customer
#             ──→ dim_product
#             ──→ dim_seller
#             ──→ dim_date
#             ──→ dim_geography
# fact_reviews ──→ fact_orders
# ```

# %%
def build_dim_date(orders: pd.DataFrame) -> pd.DataFrame:
    """Generate a date dimension from all purchase timestamps."""
    dates = pd.to_datetime(orders["order_purchase_timestamp"].dropna()).dt.normalize()
    dates = dates.drop_duplicates().sort_values()

    dim = pd.DataFrame({"date_key": dates.dt.strftime("%Y%m%d").astype(int), "full_date": dates})
    dim["year"] = dates.dt.year.values
    dim["quarter"] = dates.dt.quarter.values
    dim["month"] = dates.dt.month.values
    dim["month_name_pt"] = dates.dt.strftime("%B").values
    dim["week_of_year"] = dates.dt.isocalendar().week.values
    dim["day_of_week"] = dates.dt.dayofweek.values
    dim["day_name_pt"] = dates.dt.day_name().values
    dim["is_weekend"] = (dates.dt.dayofweek >= 5).values

    log.info("dim_date: %d linhas", len(dim))
    return dim.reset_index(drop=True)


def build_dim_customer(customers: pd.DataFrame) -> pd.DataFrame:
    """Build customer dimension with surrogate key."""
    dim = customers[
        ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"]
    ].copy()
    dim.insert(0, "customer_sk", range(1, len(dim) + 1))
    log.info("dim_customer: %d linhas", len(dim))
    return dim.reset_index(drop=True)


def build_dim_product(products: pd.DataFrame) -> pd.DataFrame:
    """Build product dimension with surrogate key."""
    cols = [
        "product_id",
        "product_category_name",
        "product_category_name_english",
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
        "product_volume_cm3",
        "product_photos_qty",
    ]
    available = [c for c in cols if c in products.columns]
    dim = products[available].copy()
    dim.insert(0, "product_sk", range(1, len(dim) + 1))
    log.info("dim_product: %d linhas", len(dim))
    return dim.reset_index(drop=True)


def build_dim_seller(sellers: pd.DataFrame) -> pd.DataFrame:
    """Build seller dimension with surrogate key."""
    dim = sellers[["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"]].copy()
    dim.insert(0, "seller_sk", range(1, len(dim) + 1))
    log.info("dim_seller: %d linhas", len(dim))
    return dim.reset_index(drop=True)


def build_fact_orders(
    trusted: TrustedDataset,
    dim_customer: pd.DataFrame,
    dim_product: pd.DataFrame,
    dim_seller: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build fact_orders grain = one row per order_item.

    Metrics: price, freight_value, payment_value, delivery_days, is_late.
    """
    items = trusted.order_items.copy()
    orders = trusted.orders.copy()
    payments = trusted.order_payments.copy()

    # Aggregate payments per order
    pay_agg = (
        payments.groupby("order_id")
        .agg(
            total_payment=("payment_value", "sum"),
            installments_max=("payment_installments", "max"),
            payment_types=("payment_type", lambda x: "|".join(sorted(set(x)))),
        )
        .reset_index()
    )

    # Join items → orders → payments
    fact = items.merge(orders, on="order_id", how="left")
    fact = fact.merge(pay_agg, on="order_id", how="left")

    # Surrogate key joins
    fact = fact.merge(dim_customer[["customer_id", "customer_sk"]], on="customer_id", how="left")
    fact = fact.merge(dim_product[["product_id", "product_sk"]], on="product_id", how="left")
    fact = fact.merge(dim_seller[["seller_id", "seller_sk"]], on="seller_id", how="left")

    # Derived metrics
    fact["delivery_days"] = (
        fact["order_delivered_customer_date"] - fact["order_purchase_timestamp"]
    ).dt.total_seconds() / 86400
    fact["estimated_days"] = (
        fact["order_estimated_delivery_date"] - fact["order_purchase_timestamp"]
    ).dt.total_seconds() / 86400
    fact["is_late"] = (
        fact["order_delivered_customer_date"] > fact["order_estimated_delivery_date"]
    ).fillna(False)
    fact["date_key"] = pd.to_datetime(fact["order_purchase_timestamp"]).dt.strftime("%Y%m%d").astype("Int64")

    # Select final columns
    final_cols = [
        "order_id",
        "order_item_id",
        "order_status",
        "customer_sk",
        "product_sk",
        "seller_sk",
        "date_key",
        "price",
        "freight_value",
        "total_payment",
        "installments_max",
        "payment_types",
        "delivery_days",
        "estimated_days",
        "is_late",
        "order_purchase_timestamp",
    ]
    available_cols = [c for c in final_cols if c in fact.columns]
    fact = fact[available_cols].copy()

    log.info("fact_orders: %d linhas", len(fact))
    return fact.reset_index(drop=True)


def build_fact_reviews(orders_reviews: pd.DataFrame, fact_orders: pd.DataFrame) -> pd.DataFrame:
    """Build fact_reviews grain = one row per review."""
    reviews = orders_reviews.copy()
    order_meta = fact_orders[["order_id", "customer_sk", "date_key"]].drop_duplicates("order_id")
    fact = reviews.merge(order_meta, on="order_id", how="left")
    fact["has_comment"] = (fact["review_comment_message"].str.len() > 0).astype(int)
    log.info("fact_reviews: %d linhas", len(fact))
    return fact.reset_index(drop=True)


def build_refined(trusted: TrustedDataset) -> RefinedDataset:
    """Orchestrate Trusted → Refined transformation."""
    log.info("=== ETL: Trusted → Refined (Star Schema) ===")

    dim_customer = build_dim_customer(trusted.customers)
    dim_product = build_dim_product(trusted.products)
    dim_seller = build_dim_seller(trusted.sellers)
    dim_date = build_dim_date(trusted.orders)
    fact_orders = build_fact_orders(trusted, dim_customer, dim_product, dim_seller)
    fact_reviews = build_fact_reviews(trusted.order_reviews, fact_orders)

    return RefinedDataset(
        fact_orders=fact_orders,
        fact_reviews=fact_reviews,
        dim_customer=dim_customer,
        dim_product=dim_product,
        dim_seller=dim_seller,
        dim_date=dim_date,
    )


refined = build_refined(trusted)
log.info("Refined layer pronto.")

# %% [markdown]
# ## 6. Feature Engineering para ML

# %%
def build_product_features(
    trusted: TrustedDataset,
    refined: RefinedDataset,
    cfg: PipelineConfig,
) -> pd.DataFrame:
    """
    Build product-level features for recommendation.

    Features:
    - TF-IDF text feature from category name + physical attributes
    - Order frequency (how often the product was sold)
    - Average price
    - Average review score
    """
    items = trusted.order_items.copy()
    products = trusted.products.copy()
    reviews = trusted.order_reviews[["order_id", "review_score"]].copy()

    # Frequency and avg price per product
    product_stats = (
        items.groupby("product_id")
        .agg(
            order_count=("order_id", "nunique"),
            avg_price=("price", "mean"),
            avg_freight=("freight_value", "mean"),
            total_revenue=("price", "sum"),
        )
        .reset_index()
    )

    # Avg review score per product (via order join)
    order_reviews_joined = items[["order_id", "product_id"]].merge(reviews, on="order_id", how="left")
    product_review_stats = (
        order_reviews_joined.groupby("product_id")
        .agg(avg_review_score=("review_score", "mean"), review_count=("review_score", "count"))
        .reset_index()
    )

    # Merge everything
    df = products.merge(product_stats, on="product_id", how="left")
    df = df.merge(product_review_stats, on="product_id", how="left")

    # Fill NaN for products with no sales (edge case)
    numeric_fill: dict[str, float] = {
        "order_count": 0,
        "avg_price": 0.0,
        "avg_freight": 0.0,
        "total_revenue": 0.0,
        "avg_review_score": 3.0,
        "review_count": 0,
    }
    for col, val in numeric_fill.items():
        if col in df.columns:
            df[col] = df[col].fillna(val)

    # TF-IDF text corpus: combine category + physical descriptor
    df["text_corpus"] = (
        df["product_category_name"].fillna("").str.replace("_", " ")
        + " "
        + df["product_category_name_english"].fillna("").str.replace("_", " ")
        + " peso "
        + df["product_weight_g"].astype(str)
        + " volume "
        + df["product_volume_cm3"].astype(str)
    ).str.strip()

    log.info("product_features: %d produtos com features", len(df))
    return df


product_features = build_product_features(trusted, refined, CFG)

# %% [markdown]
# ## 7. Pipeline de Recomendacao de Produtos (TF-IDF + Cosine Similarity)
#
# **Abordagem:** Content-based filtering usando TF-IDF sobre categorias e atributos fisicos.
# Calculamos a matriz de similaridade de cosseno entre todos os produtos.
#
# **Limitacao:** O dataset Olist nao possui nomes de produtos. O corpus de texto e construido
# a partir de categoria, traducao e atributos fisicos (peso, volume). Em producao, isso seria
# enriquecido com embeddings de linguagem (sentence-transformers).

# %%
@dataclass(slots=True)
class RecommendationModel:
    """Content-based product recommendation using TF-IDF cosine similarity."""

    vectorizer: TfidfVectorizer | None = None
    tfidf_matrix: Any = None  # sparse matrix
    similarity_matrix: np.ndarray | None = None
    product_ids: list[str] = field(default_factory=list)
    product_index: dict[str, int] = field(default_factory=dict)

    def fit(self, df: pd.DataFrame, cfg: PipelineConfig) -> None:
        """Fit TF-IDF vectorizer and compute cosine similarity matrix."""
        corpus = df["text_corpus"].fillna("").tolist()
        self.product_ids = df["product_id"].tolist()
        self.product_index = {pid: idx for idx, pid in enumerate(self.product_ids)}

        self.vectorizer = TfidfVectorizer(
            max_features=cfg.tfidf_max_features,
            ngram_range=(1, 2),
            min_df=2,
            sublinear_tf=True,
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(corpus)
        self.similarity_matrix = cosine_similarity(self.tfidf_matrix, dense_output=False).toarray()
        log.info(
            "RecommendationModel fit: %d produtos, %d features TF-IDF",
            len(self.product_ids),
            self.tfidf_matrix.shape[1],
        )

    def recommend(self, product_id: str, top_n: int = 10) -> pd.DataFrame:
        """Return top_n most similar products for a given product_id."""
        if product_id not in self.product_index:
            log.warning("product_id nao encontrado: %s", product_id)
            return pd.DataFrame()

        idx = self.product_index[product_id]
        sim_scores = self.similarity_matrix[idx].copy()
        sim_scores[idx] = -1  # exclude self

        top_indices = np.argsort(sim_scores)[::-1][:top_n]
        result = pd.DataFrame(
            {
                "product_id": [self.product_ids[i] for i in top_indices],
                "similarity_score": sim_scores[top_indices],
            }
        )
        return result

    def evaluate_precision_recall(
        self,
        trusted_items: pd.DataFrame,
        top_n: int = 10,
        sample_size: int = 500,
    ) -> dict[str, float]:
        """
        Approximate precision and recall via co-purchase validation.

        A product pair (A, B) is 'relevant' if they appear in the same order.
        We sample sample_size products and evaluate.
        """
        # Build co-purchase pairs
        order_products = (
            trusted_items.groupby("order_id")["product_id"]
            .apply(list)
            .reset_index()
        )
        # Only orders with 2+ products
        multi_product_orders = order_products[order_products["product_id"].apply(len) >= 2]

        copurchase: dict[str, set[str]] = {}
        for _, row in multi_product_orders.iterrows():
            for pid in row["product_id"]:
                if pid not in copurchase:
                    copurchase[pid] = set()
                copurchase[pid].update(p for p in row["product_id"] if p != pid)

        # Sample products that have co-purchase data and exist in our model
        valid_pids = [
            pid
            for pid in list(copurchase.keys())[:sample_size]
            if pid in self.product_index and len(copurchase[pid]) > 0
        ]
        if not valid_pids:
            return {"precision_at_k": 0.0, "recall_at_k": 0.0}

        precisions: list[float] = []
        recalls: list[float] = []

        for pid in valid_pids:
            recs_df = self.recommend(pid, top_n=top_n)
            if recs_df.empty:
                continue
            recommended = set(recs_df["product_id"].tolist())
            relevant = copurchase[pid]
            hits = len(recommended & relevant)
            precisions.append(hits / top_n)
            recalls.append(hits / len(relevant) if relevant else 0.0)

        return {
            "precision_at_k": float(np.mean(precisions)),
            "recall_at_k": float(np.mean(recalls)),
        }


rec_model = RecommendationModel()
rec_model.fit(product_features, CFG)

# Evaluate
rec_metrics = rec_model.evaluate_precision_recall(
    trusted.order_items,
    top_n=CFG.top_n_recommendations,
)
log.info("Recomendacao — Precision@%d: %.4f | Recall@%d: %.4f",
         CFG.top_n_recommendations, rec_metrics["precision_at_k"],
         CFG.top_n_recommendations, rec_metrics["recall_at_k"])

# Sample recommendation
if product_features["product_id"].nunique() > 0:
    sample_pid = product_features["product_id"].iloc[0]
    sample_recs = rec_model.recommend(sample_pid, top_n=5)
    log.info("Exemplo de recomendacoes para %s:\n%s", sample_pid, sample_recs.to_string(index=False))

# %% [markdown]
# ## 8. Pipeline de Previsao de Tempo de Entrega (Random Forest)
#
# **Target:** `delivery_days` — dias corridos entre compra e entrega ao cliente.
#
# **Features:**
# - `seller_state` — origem do envio (UF)
# - `customer_state` — destino (UF)
# - `product_weight_g` — peso do produto
# - `product_volume_cm3` — volume calculado
# - `freight_value` — valor do frete cobrado
# - `price` — preco do produto
# - `same_state` — flag se origem = destino
# - `installments_max` — numero de parcelas (proxy de ticket alto)

# %%
def build_delivery_features(
    trusted: TrustedDataset,
    refined: RefinedDataset,
) -> pd.DataFrame:
    """Build feature matrix for delivery time prediction."""
    fact = refined.fact_orders.copy()
    products = trusted.products[
        ["product_id", "product_weight_g", "product_volume_cm3"]
    ].copy()
    sellers = trusted.sellers[["seller_id", "seller_state"]].copy()
    customers = trusted.customers[["customer_id", "customer_state"]].copy()

    # Join product and location info
    items_base = trusted.order_items[["order_id", "product_id", "seller_id", "freight_value", "price"]].copy()
    orders_base = trusted.orders[
        ["order_id", "customer_id", "order_purchase_timestamp",
         "order_delivered_customer_date", "order_estimated_delivery_date"]
    ].copy()

    df = items_base.merge(orders_base, on="order_id", how="inner")
    df = df.merge(products, on="product_id", how="left")
    df = df.merge(sellers, on="seller_id", how="left")
    df = df.merge(customers, on="customer_id", how="left")

    # Target
    df["delivery_days"] = (
        pd.to_datetime(df["order_delivered_customer_date"])
        - pd.to_datetime(df["order_purchase_timestamp"])
    ).dt.total_seconds() / 86400

    # Remove rows without target or negative delivery times
    df = df[df["delivery_days"] > 0].dropna(subset=["delivery_days"])
    df = df[df["delivery_days"] <= 120]  # remove extreme outliers (>4 months)

    # Feature engineering
    df["same_state"] = (df["seller_state"] == df["customer_state"]).astype(int)
    df["product_weight_g"] = df["product_weight_g"].fillna(df["product_weight_g"].median())
    df["product_volume_cm3"] = df["product_volume_cm3"].fillna(df["product_volume_cm3"].median())

    # Encode states
    le_seller = LabelEncoder()
    le_customer = LabelEncoder()
    df["seller_state_enc"] = le_seller.fit_transform(df["seller_state"].fillna("SP"))
    df["customer_state_enc"] = le_customer.fit_transform(df["customer_state"].fillna("SP"))

    log.info("delivery_features: %d registros, target mean=%.1f dias", len(df), df["delivery_days"].mean())
    return df


delivery_df = build_delivery_features(trusted, refined)

FEATURE_COLS: list[str] = [
    "seller_state_enc",
    "customer_state_enc",
    "product_weight_g",
    "product_volume_cm3",
    "freight_value",
    "price",
    "same_state",
]

X = delivery_df[FEATURE_COLS].fillna(0)
y = delivery_df["delivery_days"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=CFG.test_size, random_state=CFG.random_state
)

log.info(
    "Train: %d | Test: %d | Features: %d",
    len(X_train), len(X_test), len(FEATURE_COLS),
)

# %% [markdown]
# ### 8.1 Treinamento do Modelo

# %%
rf_model = RandomForestRegressor(
    n_estimators=CFG.n_estimators,
    max_depth=12,
    min_samples_leaf=5,
    n_jobs=-1,
    random_state=CFG.random_state,
)

log.info("Treinando Random Forest com %d estimators...", CFG.n_estimators)
rf_model.fit(X_train, y_train)
log.info("Treinamento concluido.")

# %% [markdown]
# ### 8.2 Avaliacao do Modelo

# %%
def evaluate_model(
    model: RandomForestRegressor,
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
    cfg: PipelineConfig,
) -> ModelMetrics:
    """Evaluate regression model with RMSE, MAE, R2, and cross-validation."""
    y_pred = model.predict(X_test)

    rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
    mae = float(mean_absolute_error(y_test, y_pred))
    r2 = float(r2_score(y_test, y_pred))

    # 5-fold CV on training set
    cv_scores = cross_val_score(
        model, X_train, y_train,
        cv=5,
        scoring="neg_root_mean_squared_error",
        n_jobs=-1,
    )
    cv_rmse_mean = float(-cv_scores.mean())
    cv_rmse_std = float(cv_scores.std())

    return ModelMetrics(
        rmse=rmse,
        mae=mae,
        r2=r2,
        cv_rmse_mean=cv_rmse_mean,
        cv_rmse_std=cv_rmse_std,
    )


metrics = evaluate_model(rf_model, X_train, X_test, y_train, y_test, CFG)
log.info("Metricas de avaliacao: %s", metrics)

# %% [markdown]
# ### 8.3 Importancia de Features

# %%
feature_importance_df = pd.DataFrame(
    {
        "feature": FEATURE_COLS,
        "importance": rf_model.feature_importances_,
    }
).sort_values("importance", ascending=False)

log.info("Importancia de features:\n%s", feature_importance_df.to_string(index=False))

# %% [markdown]
# ## 9. Persistencia — Modelos e Dados Refinados

# %%
def save_artifacts(
    cfg: PipelineConfig,
    refined: RefinedDataset,
    rec_model: RecommendationModel,
    rf_model: RandomForestRegressor,
    product_features: pd.DataFrame,
    metrics: ModelMetrics,
    rec_metrics: dict[str, float],
) -> None:
    """Save all model artifacts and refined tables to disk."""
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    cfg.models_dir.mkdir(parents=True, exist_ok=True)

    # Save refined tables as Parquet
    parquet_tables: dict[str, pd.DataFrame] = {
        "fact_orders": refined.fact_orders,
        "fact_reviews": refined.fact_reviews,
        "dim_customer": refined.dim_customer,
        "dim_product": refined.dim_product,
        "dim_seller": refined.dim_seller,
        "dim_date": refined.dim_date,
        "product_features": product_features,
    }
    for name, df in parquet_tables.items():
        path = cfg.output_dir / f"{name}.parquet"
        df.to_parquet(path, index=False)
        log.info("Salvo: %s (%d linhas)", path, len(df))

    # Save ML models
    joblib.dump(rec_model, cfg.models_dir / "recommendation_model.joblib")
    joblib.dump(rf_model, cfg.models_dir / "delivery_rf_model.joblib")
    log.info("Modelos salvos em: %s", cfg.models_dir)

    # Save metrics report
    metrics_df = pd.DataFrame(
        [
            {
                "model": "delivery_rf",
                "rmse": metrics.rmse,
                "mae": metrics.mae,
                "r2": metrics.r2,
                "cv_rmse_mean": metrics.cv_rmse_mean,
                "cv_rmse_std": metrics.cv_rmse_std,
            },
            {
                "model": "recommendation",
                "precision_at_10": rec_metrics.get("precision_at_k", 0.0),
                "recall_at_10": rec_metrics.get("recall_at_k", 0.0),
            },
        ]
    )
    metrics_path = cfg.output_dir / "ml_metrics.csv"
    metrics_df.to_csv(metrics_path, index=False)
    log.info("Metricas salvas em: %s", metrics_path)


save_artifacts(CFG, refined, rec_model, rf_model, product_features, metrics, rec_metrics)

# %% [markdown]
# ## 10. Resumo do Pipeline
#
# | Etapa | Entradas | Saidas | Observacoes |
# |-------|----------|--------|-------------|
# | Raw Load | 9 CSVs Olist | OlistDataset | parse_dates automatico |
# | Trusted | OlistDataset | TrustedDataset | dedup, nulls, tipos |
# | Refined | TrustedDataset | RefinedDataset | star schema Kimball |
# | Feature Eng. | TrustedDataset + RefinedDataset | product_features, delivery_df | |
# | Recomendacao | product_features | rec_model | TF-IDF 500 features |
# | Previsao | delivery_df | rf_model | 200 arvores, cv=5 |
#
# ### Metricas Finais

# %%
print("\n" + "=" * 60)
print("  RESUMO DE METRICAS — ML PIPELINE")
print("=" * 60)
print(f"\n[Previsao de Entrega — Random Forest]")
print(f"  RMSE : {metrics.rmse:.2f} dias")
print(f"  MAE  : {metrics.mae:.2f} dias")
print(f"  R²   : {metrics.r2:.4f}")
print(f"  CV-RMSE: {metrics.cv_rmse_mean:.2f} ± {metrics.cv_rmse_std:.2f}")
print(f"\n[Recomendacao de Produtos — TF-IDF Cosine]")
print(f"  Precision@{CFG.top_n_recommendations}: {rec_metrics.get('precision_at_k', 0):.4f}")
print(f"  Recall@{CFG.top_n_recommendations}   : {rec_metrics.get('recall_at_k', 0):.4f}")
print("\n" + "=" * 60)
