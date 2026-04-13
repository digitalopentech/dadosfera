"""
Dadosfera Case Study — Streamlit Data App
==========================================
Main entry point. Handles page config, navigation, and cached data loading.

Run locally:
    streamlit run streamlit_app/app.py
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import streamlit as st

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APP_TITLE = "Dadosfera | Olist E-Commerce Analytics"
APP_ICON = "🛒"
DATA_DIR = Path(__file__).parent.parent / "data"

RAW_FILES: dict[str, str] = {
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
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
}

PAGES: list[dict[str, str]] = [
    {"label": "Home", "icon": "🏠"},
    {"label": "Analise Exploratoria", "icon": "📊"},
    {"label": "Similaridade de Produtos", "icon": "🔍"},
    {"label": "Features GenAI", "icon": "🤖"},
]


# ---------------------------------------------------------------------------
# Data Loading (cached)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class OlistData:
    """Container for all loaded Olist DataFrames."""

    orders: pd.DataFrame = field(default_factory=pd.DataFrame)
    order_items: pd.DataFrame = field(default_factory=pd.DataFrame)
    order_payments: pd.DataFrame = field(default_factory=pd.DataFrame)
    order_reviews: pd.DataFrame = field(default_factory=pd.DataFrame)
    customers: pd.DataFrame = field(default_factory=pd.DataFrame)
    products: pd.DataFrame = field(default_factory=pd.DataFrame)
    sellers: pd.DataFrame = field(default_factory=pd.DataFrame)
    category_translation: pd.DataFrame = field(default_factory=pd.DataFrame)
    load_errors: list[str] = field(default_factory=list)

    @property
    def is_loaded(self) -> bool:
        return not self.orders.empty and not self.order_items.empty


@st.cache_data(show_spinner="Carregando dados Olist...")
def load_olist_data(data_dir: str = str(DATA_DIR)) -> OlistData:
    """Load all Olist CSV files with caching. Returns OlistData container."""
    base = Path(data_dir)
    data = OlistData()
    errors: list[str] = []

    for attr, filename in RAW_FILES.items():
        path = base / filename
        if not path.exists():
            errors.append(f"Arquivo nao encontrado: {filename}")
            continue
        try:
            parse_dates = TIMESTAMP_COLS.get(attr, False)
            df = pd.read_csv(path, parse_dates=parse_dates, low_memory=False)
            setattr(data, attr, df)
        except Exception as exc:
            errors.append(f"Erro ao ler {filename}: {exc}")

    data.load_errors = errors
    return data


@st.cache_data(show_spinner="Processando dados...")
def build_enriched_orders(data_str_hash: str, data_dir: str = str(DATA_DIR)) -> pd.DataFrame:
    """
    Build a denormalized orders DataFrame for analytics.
    Cached separately so individual page filters don't reload everything.
    """
    data = load_olist_data(data_dir)
    if not data.is_loaded:
        return pd.DataFrame()

    orders = data.orders.copy()

    # Aggregate payments
    if not data.order_payments.empty:
        pay_agg = (
            data.order_payments.groupby("order_id")
            .agg(
                total_payment=("payment_value", "sum"),
                payment_type=("payment_type", "first"),
            )
            .reset_index()
        )
        orders = orders.merge(pay_agg, on="order_id", how="left")

    # Add customer state
    if not data.customers.empty:
        orders = orders.merge(
            data.customers[["customer_id", "customer_state", "customer_city"]],
            on="customer_id",
            how="left",
        )

    # Add review score
    if not data.order_reviews.empty:
        review_agg = (
            data.order_reviews.groupby("order_id")["review_score"]
            .mean()
            .reset_index()
            .rename(columns={"review_score": "avg_review_score"})
        )
        orders = orders.merge(review_agg, on="order_id", how="left")

    # Delivery metrics
    orders["delivery_days"] = (
        pd.to_datetime(orders["order_delivered_customer_date"])
        - pd.to_datetime(orders["order_purchase_timestamp"])
    ).dt.total_seconds() / 86400

    orders["purchase_date"] = pd.to_datetime(
        orders["order_purchase_timestamp"]
    ).dt.normalize()

    return orders


# ---------------------------------------------------------------------------
# Page: Home
# ---------------------------------------------------------------------------

def render_home(data: OlistData) -> None:
    """Render the home/overview page."""
    st.title("Dadosfera Case Study — Olist E-Commerce")
    st.caption("Plataforma de Analytics | Abril de 2026")

    st.markdown(
        """
        Este Data App demonstra as capacidades analiticas construidas sobre o dataset
        **Olist Brazilian E-Commerce** como parte do caso tecnico para a Dadosfera.
        """
    )

    # Dataset status
    if data.is_loaded:
        st.success("Dados carregados com sucesso.")
    else:
        st.warning(
            "Dados nao encontrados no diretorio esperado. "
            f"Certifique-se de que os CSVs estao em: `{DATA_DIR}`"
        )
        if data.load_errors:
            with st.expander("Detalhes dos erros"):
                for err in data.load_errors:
                    st.error(err)

    st.divider()

    # Quick stats
    col1, col2, col3, col4 = st.columns(4)

    if data.is_loaded:
        n_orders = data.orders["order_id"].nunique() if not data.orders.empty else 0
        n_products = data.products["product_id"].nunique() if not data.products.empty else 0
        n_customers = data.customers["customer_unique_id"].nunique() if not data.customers.empty else 0
        n_sellers = data.sellers["seller_id"].nunique() if not data.sellers.empty else 0
    else:
        n_orders = n_products = n_customers = n_sellers = 0

    col1.metric("Pedidos", f"{n_orders:,}")
    col2.metric("Produtos", f"{n_products:,}")
    col3.metric("Clientes Unicos", f"{n_customers:,}")
    col4.metric("Vendedores", f"{n_sellers:,}")

    st.divider()

    # Architecture overview
    st.subheader("Arquitetura da Solucao")
    st.markdown(
        """
        ```
        CSVs Olist (Raw)
             |
             v
        [ETL Pipeline]  →  Trusted (limpeza) → Refined (star schema)
             |
             v
        [ML Models]     →  Recomendacao TF-IDF | Previsao Random Forest
             |
             v
        [Data App]      →  EDA | Similaridade | GenAI Features
        ```
        """
    )

    st.subheader("Paginas do App")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.info(
            "**Analise Exploratoria**\n\n"
            "KPIs, series temporais, distribuicao por estado e funil de pedidos."
        )
    with col_b:
        st.info(
            "**Similaridade de Produtos**\n\n"
            "Recomendacao via TF-IDF + cosseno. Selecione um produto e veja os 10 mais similares."
        )
    with col_c:
        st.info(
            "**Features GenAI**\n\n"
            "Explore features extraidas por LLM de descricoes de produtos Amazon."
        )

    st.divider()

    st.subheader("Datasets Utilizados")
    datasets_info = {
        "olist_orders": (data.orders, "Pedidos"),
        "olist_order_items": (data.order_items, "Itens"),
        "olist_products": (data.products, "Produtos"),
        "olist_customers": (data.customers, "Clientes"),
        "olist_sellers": (data.sellers, "Vendedores"),
        "olist_order_reviews": (data.order_reviews, "Avaliacoes"),
    }

    rows = []
    for name, (df, label) in datasets_info.items():
        rows.append(
            {
                "Tabela": name,
                "Descricao": label,
                "Linhas": f"{len(df):,}" if not df.empty else "N/A",
                "Colunas": str(df.shape[1]) if not df.empty else "N/A",
            }
        )

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Footer
    st.divider()
    st.caption(
        "Desenvolvido por Leonardo Nunes | Dadosfera Case Study 2026 | "
        "Dataset: Olist Brazilian E-Commerce (Kaggle CC BY-NC-SA 4.0)"
    )


# ---------------------------------------------------------------------------
# Sidebar Navigation
# ---------------------------------------------------------------------------

def render_sidebar() -> str:
    """Render sidebar and return selected page label."""
    with st.sidebar:
        st.image(
            "https://dadosfera.ai/wp-content/uploads/2023/07/logo-dadosfera-white.svg",
            use_container_width=True,
        )
        st.title("Navegacao")
        st.caption("Olist Analytics Platform")
        st.divider()

        selected = st.radio(
            "Paginas",
            options=[p["label"] for p in PAGES],
            label_visibility="collapsed",
        )

        st.divider()
        st.caption("**Dataset:** Olist Brazilian E-Commerce")
        st.caption("**Periodo:** Set/2016 — Out/2018")
        st.caption("**Versao:** 1.0.0")

    return selected


# ---------------------------------------------------------------------------
# App Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    """Configure and run the Streamlit application."""
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon=APP_ICON,
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            "Get Help": "https://github.com/leonardovalleavanade/case-dadosfera",
            "About": "Dadosfera Case Study — Olist E-Commerce Analytics Platform v1.0.0",
        },
    )

    # Global CSS
    st.markdown(
        """
        <style>
        .stMetric { background-color: #f0f2f6; padding: 12px; border-radius: 8px; }
        .stMetric label { font-size: 0.85rem; color: #666; }
        div[data-testid="stSidebarNav"] { display: none; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    selected_page = render_sidebar()
    data = load_olist_data()

    if selected_page == "Home":
        render_home(data)
    elif selected_page == "Analise Exploratoria":
        st.info("Acesse via: pages/1_Analise_Exploratoria.py")
    elif selected_page == "Similaridade de Produtos":
        st.info("Acesse via: pages/2_Similaridade_Produtos.py")
    elif selected_page == "Features GenAI":
        st.info("Acesse via: pages/3_GenAI_Features.py")


if __name__ == "__main__":
    main()
