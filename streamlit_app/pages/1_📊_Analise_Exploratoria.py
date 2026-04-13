"""
Pagina: Analise Exploratoria de Dados
======================================
EDA completa do dataset Olist com filtros interativos, KPIs e visualizacoes.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Analise Exploratoria | Dadosfera",
    page_icon="📊",
    layout="wide",
)

DATA_DIR = Path(__file__).parent.parent.parent / "data"

TIMESTAMP_COLS = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Carregando dados...")
def load_data(data_dir: str = str(DATA_DIR)) -> dict[str, pd.DataFrame]:
    """Load and minimally process Olist CSVs for EDA."""
    base = Path(data_dir)
    frames: dict[str, pd.DataFrame] = {}
    file_map = {
        "orders": "olist_orders_dataset.csv",
        "order_items": "olist_order_items_dataset.csv",
        "order_payments": "olist_order_payments_dataset.csv",
        "order_reviews": "olist_order_reviews_dataset.csv",
        "customers": "olist_customers_dataset.csv",
        "products": "olist_products_dataset.csv",
        "sellers": "olist_sellers_dataset.csv",
        "category_translation": "product_category_name_translation.csv",
    }
    for key, fname in file_map.items():
        path = base / fname
        if path.exists():
            try:
                frames[key] = pd.read_csv(
                    path,
                    parse_dates=TIMESTAMP_COLS if key == "orders" else False,
                    low_memory=False,
                )
            except Exception:
                frames[key] = pd.DataFrame()
        else:
            frames[key] = pd.DataFrame()
    return frames


@st.cache_data(show_spinner="Construindo base analitica...")
def build_analytics_base(data_dir: str = str(DATA_DIR)) -> pd.DataFrame:
    """Join orders, items, customers, products, reviews into one flat table."""
    frames = load_data(data_dir)

    orders = frames.get("orders", pd.DataFrame())
    if orders.empty:
        return pd.DataFrame()

    items = frames.get("order_items", pd.DataFrame())
    customers = frames.get("customers", pd.DataFrame())
    products = frames.get("products", pd.DataFrame())
    reviews = frames.get("order_reviews", pd.DataFrame())
    payments = frames.get("order_payments", pd.DataFrame())
    cat_trans = frames.get("category_translation", pd.DataFrame())

    # Aggregate items per order
    if not items.empty:
        items_agg = items.groupby("order_id").agg(
            total_items=("order_item_id", "count"),
            total_price=("price", "sum"),
            total_freight=("freight_value", "sum"),
            product_id_first=("product_id", "first"),
        ).reset_index()
        base = orders.merge(items_agg, on="order_id", how="left")
    else:
        base = orders.copy()

    # Payments
    if not payments.empty:
        pay_agg = payments.groupby("order_id").agg(
            total_payment=("payment_value", "sum"),
            payment_type=("payment_type", "first"),
        ).reset_index()
        base = base.merge(pay_agg, on="order_id", how="left")

    # Customers
    if not customers.empty:
        base = base.merge(
            customers[["customer_id", "customer_state", "customer_city", "customer_unique_id"]],
            on="customer_id",
            how="left",
        )

    # Reviews (first per order)
    if not reviews.empty:
        rev_agg = reviews.groupby("order_id")["review_score"].mean().reset_index()
        base = base.merge(rev_agg, on="order_id", how="left")

    # Product category
    if not items.empty and not products.empty:
        prod_cat = products[["product_id", "product_category_name"]].copy()
        if not cat_trans.empty:
            prod_cat = prod_cat.merge(cat_trans, on="product_category_name", how="left")
            prod_cat["category_label"] = prod_cat.get(
                "product_category_name_english", prod_cat["product_category_name"]
            )
        else:
            prod_cat["category_label"] = prod_cat["product_category_name"]

        items_cat = items[["order_id", "product_id"]].merge(
            prod_cat[["product_id", "category_label"]], on="product_id", how="left"
        )
        cat_per_order = items_cat.groupby("order_id")["category_label"].first().reset_index()
        base = base.merge(cat_per_order, on="order_id", how="left")

    # Derived columns
    base["purchase_date"] = pd.to_datetime(base["order_purchase_timestamp"]).dt.normalize()
    base["purchase_month"] = pd.to_datetime(base["order_purchase_timestamp"]).dt.to_period("M").astype(str)
    base["delivery_days"] = (
        pd.to_datetime(base["order_delivered_customer_date"])
        - pd.to_datetime(base["order_purchase_timestamp"])
    ).dt.total_seconds() / 86400
    base["is_late"] = (
        pd.to_datetime(base["order_delivered_customer_date"])
        > pd.to_datetime(base["order_estimated_delivery_date"])
    ).fillna(False)
    base["revenue"] = base.get("total_payment", base.get("total_price", pd.Series(0.0, index=base.index)))

    return base


# ---------------------------------------------------------------------------
# Dataset overview helper
# ---------------------------------------------------------------------------

def render_dataset_overview(frames: dict[str, pd.DataFrame]) -> None:
    """Show shape, dtypes, and null counts for each table."""
    st.subheader("Visao Geral dos Datasets")
    overview_rows = []
    for name, df in frames.items():
        if df.empty:
            continue
        null_count = int(df.isnull().sum().sum())
        null_pct = f"{100 * null_count / max(df.size, 1):.1f}%"
        overview_rows.append(
            {
                "Tabela": name,
                "Linhas": f"{len(df):,}",
                "Colunas": str(df.shape[1]),
                "Nulos Totais": f"{null_count:,}",
                "% Nulos": null_pct,
            }
        )
    st.dataframe(pd.DataFrame(overview_rows), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------

def render_kpi_cards(df: pd.DataFrame) -> None:
    """Render top-level KPI metric cards."""
    col1, col2, col3, col4, col5 = st.columns(5)

    total_orders = df["order_id"].nunique()
    total_revenue = df["revenue"].sum()
    avg_ticket = total_revenue / max(total_orders, 1)
    avg_review = df["review_score"].mean() if "review_score" in df.columns else 0.0
    avg_delivery = df.loc[df["delivery_days"] > 0, "delivery_days"].mean()

    col1.metric("Total de Pedidos", f"{total_orders:,}")
    col2.metric("Receita Total", f"R$ {total_revenue:,.0f}")
    col3.metric("Ticket Medio", f"R$ {avg_ticket:,.2f}")
    col4.metric("Avaliacao Media", f"{avg_review:.2f} / 5.0")
    col5.metric("Entrega Media", f"{avg_delivery:.1f} dias")


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def chart_revenue_over_time(df: pd.DataFrame) -> None:
    """Monthly revenue trend line chart."""
    monthly = (
        df.groupby("purchase_month")
        .agg(revenue=("revenue", "sum"), orders=("order_id", "nunique"))
        .reset_index()
        .sort_values("purchase_month")
    )

    fig = px.line(
        monthly,
        x="purchase_month",
        y="revenue",
        title="Receita Mensal (R$)",
        labels={"purchase_month": "Mes", "revenue": "Receita (R$)"},
        markers=True,
    )
    fig.update_traces(line_color="#5B9BD5", line_width=2.5, marker_size=6)
    fig.update_layout(
        xaxis_tickangle=-45,
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=380,
    )
    st.plotly_chart(fig, use_container_width=True)


def chart_top_categories(df: pd.DataFrame, top_n: int = 15) -> None:
    """Horizontal bar chart of top N categories by revenue."""
    if "category_label" not in df.columns:
        st.info("Coluna category_label nao disponivel.")
        return

    cat_revenue = (
        df.groupby("category_label")["revenue"]
        .sum()
        .sort_values(ascending=False)
        .head(top_n)
        .reset_index()
    )

    fig = px.bar(
        cat_revenue,
        x="revenue",
        y="category_label",
        orientation="h",
        title=f"Top {top_n} Categorias por Receita",
        labels={"revenue": "Receita (R$)", "category_label": "Categoria"},
        color="revenue",
        color_continuous_scale="Blues",
    )
    fig.update_layout(
        yaxis={"categoryorder": "total ascending"},
        coloraxis_showscale=False,
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=480,
    )
    st.plotly_chart(fig, use_container_width=True)


def chart_state_orders(df: pd.DataFrame) -> None:
    """Choropleth map of Brazil with orders per state."""
    if "customer_state" not in df.columns:
        st.info("Dados de estado nao disponiveis.")
        return

    state_data = (
        df.groupby("customer_state")
        .agg(orders=("order_id", "nunique"), revenue=("revenue", "sum"))
        .reset_index()
    )

    fig = px.choropleth(
        state_data,
        geojson="https://raw.githubusercontent.com/codeforamerica/click_that_hood/master/public/data/brazil-states.geojson",
        featureidkey="properties.sigla",
        locations="customer_state",
        color="orders",
        hover_name="customer_state",
        hover_data={"orders": ":,", "revenue": ":,.0f"},
        color_continuous_scale="Blues",
        title="Pedidos por Estado (Brasil)",
        scope="south america",
    )
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(height=500, margin={"r": 0, "t": 40, "l": 0, "b": 0})
    st.plotly_chart(fig, use_container_width=True)


def chart_order_status_funnel(df: pd.DataFrame) -> None:
    """Funnel chart for order status distribution."""
    status_order = [
        "created", "approved", "invoiced", "processing",
        "shipped", "delivered", "canceled", "unavailable",
    ]
    status_counts = (
        df.groupby("order_status")["order_id"]
        .nunique()
        .reindex(status_order, fill_value=0)
        .reset_index()
        .rename(columns={"order_id": "count"})
    )
    status_counts = status_counts[status_counts["count"] > 0]

    fig = go.Figure(
        go.Funnel(
            y=status_counts["order_status"],
            x=status_counts["count"],
            textinfo="value+percent initial",
            marker_color=[
                "#2196F3", "#42A5F5", "#64B5F6", "#90CAF9",
                "#BBDEFB", "#EF9A9A", "#F44336", "#B71C1C",
            ][: len(status_counts)],
        )
    )
    fig.update_layout(title="Funil de Status dos Pedidos", height=420)
    st.plotly_chart(fig, use_container_width=True)


def chart_review_distribution(df: pd.DataFrame) -> None:
    """Bar chart of review score distribution."""
    if "review_score" not in df.columns:
        return

    review_counts = (
        df["review_score"]
        .value_counts()
        .sort_index()
        .reset_index()
        .rename(columns={"index": "score", "review_score": "count"})
    )
    # Plotly express with new pandas naming
    fig = px.bar(
        review_counts,
        x="review_score",
        y="count",
        title="Distribuicao de Avaliacoes (1–5)",
        labels={"review_score": "Nota", "count": "Quantidade"},
        color="review_score",
        color_continuous_scale=["#EF9A9A", "#FFCC80", "#FFF176", "#A5D6A7", "#66BB6A"],
    )
    fig.update_layout(
        coloraxis_showscale=False,
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=350,
    )
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

def main() -> None:
    st.title("Analise Exploratoria de Dados")
    st.caption("Dataset Olist Brazilian E-Commerce | Set/2016 – Out/2018")

    frames = load_data()
    df_base = build_analytics_base()

    if df_base.empty:
        st.error(
            f"Dados nao encontrados em `{DATA_DIR}`. "
            "Faca o download dos CSVs da Olist no Kaggle e coloque na pasta `/data`."
        )
        st.stop()

    # ---- Sidebar filters ------------------------------------------------
    st.sidebar.header("Filtros")

    # Date range filter
    min_date = df_base["purchase_date"].min()
    max_date = df_base["purchase_date"].max()
    date_range = st.sidebar.date_input(
        "Periodo de Compra",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    # State filter
    all_states = sorted(df_base["customer_state"].dropna().unique().tolist())
    selected_states = st.sidebar.multiselect(
        "Estado do Cliente", options=all_states, default=[]
    )

    # Category filter
    if "category_label" in df_base.columns:
        all_cats = sorted(df_base["category_label"].dropna().unique().tolist())
        selected_cats = st.sidebar.multiselect(
            "Categoria de Produto", options=all_cats, default=[]
        )
    else:
        selected_cats = []

    # Apply filters
    mask = pd.Series([True] * len(df_base), index=df_base.index)

    if len(date_range) == 2:
        start_date = pd.Timestamp(date_range[0])
        end_date = pd.Timestamp(date_range[1])
        mask &= (df_base["purchase_date"] >= start_date) & (df_base["purchase_date"] <= end_date)

    if selected_states:
        mask &= df_base["customer_state"].isin(selected_states)

    if selected_cats:
        mask &= df_base["category_label"].isin(selected_cats)

    df_filtered = df_base[mask].copy()

    n_filtered = df_filtered["order_id"].nunique()
    n_total = df_base["order_id"].nunique()

    if n_filtered == 0:
        st.warning("Nenhum pedido encontrado com os filtros selecionados.")
        st.stop()

    st.caption(f"Exibindo {n_filtered:,} de {n_total:,} pedidos")

    # ---- Tabs -----------------------------------------------------------
    tab_overview, tab_temporal, tab_geo, tab_products, tab_quality = st.tabs(
        ["Visao Geral", "Tendencias Temporais", "Distribuicao Geografica", "Produtos", "Qualidade"]
    )

    with tab_overview:
        st.subheader("KPIs Principais")
        render_kpi_cards(df_filtered)
        st.divider()
        render_dataset_overview(frames)

    with tab_temporal:
        chart_revenue_over_time(df_filtered)
        col_l, col_r = st.columns(2)
        with col_l:
            chart_review_distribution(df_filtered)
        with col_r:
            # Orders per day of week
            df_filtered["day_of_week"] = pd.to_datetime(
                df_filtered["purchase_date"]
            ).dt.day_name()
            dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            dow_counts = (
                df_filtered["day_of_week"]
                .value_counts()
                .reindex(dow_order, fill_value=0)
                .reset_index()
                .rename(columns={"index": "day", "day_of_week": "count"})
            )
            fig_dow = px.bar(
                dow_counts,
                x="day_of_week",
                y="count",
                title="Pedidos por Dia da Semana",
                labels={"day_of_week": "Dia", "count": "Pedidos"},
                color_discrete_sequence=["#5B9BD5"],
            )
            fig_dow.update_layout(plot_bgcolor="white", paper_bgcolor="white", height=350)
            st.plotly_chart(fig_dow, use_container_width=True)

    with tab_geo:
        col_map, col_bar = st.columns([2, 1])
        with col_map:
            chart_state_orders(df_filtered)
        with col_bar:
            state_rev = (
                df_filtered.groupby("customer_state")["revenue"]
                .sum()
                .sort_values(ascending=False)
                .head(10)
                .reset_index()
            )
            fig_state = px.bar(
                state_rev,
                x="revenue",
                y="customer_state",
                orientation="h",
                title="Top 10 Estados por Receita",
                labels={"revenue": "Receita (R$)", "customer_state": "UF"},
                color_discrete_sequence=["#5B9BD5"],
            )
            fig_state.update_layout(
                yaxis={"categoryorder": "total ascending"},
                plot_bgcolor="white",
                paper_bgcolor="white",
                height=420,
            )
            st.plotly_chart(fig_state, use_container_width=True)

    with tab_products:
        col_cat, col_funnel = st.columns([2, 1])
        with col_cat:
            chart_top_categories(df_filtered)
        with col_funnel:
            chart_order_status_funnel(df_filtered)

    with tab_quality:
        st.subheader("Analise de Qualidade dos Dados")

        col_q1, col_q2 = st.columns(2)
        with col_q1:
            # Null analysis
            null_analysis = []
            for col in df_filtered.columns:
                null_pct = 100 * df_filtered[col].isnull().mean()
                if null_pct > 0:
                    null_analysis.append({"Coluna": col, "% Nulos": f"{null_pct:.1f}%"})
            if null_analysis:
                st.markdown("**Colunas com Nulos**")
                st.dataframe(
                    pd.DataFrame(null_analysis).sort_values("% Nulos", ascending=False),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.success("Nenhum nulo encontrado nas colunas selecionadas.")

        with col_q2:
            # Delivery analysis
            delivered = df_filtered[
                (df_filtered["order_status"] == "delivered")
                & (df_filtered["delivery_days"] > 0)
                & (df_filtered["delivery_days"] < 120)
            ]
            if not delivered.empty:
                late_pct = 100 * delivered["is_late"].mean()
                st.metric("Pedidos com Atraso", f"{late_pct:.1f}%")
                st.metric("Entrega Media (entregues)", f"{delivered['delivery_days'].mean():.1f} dias")
                st.metric("Entrega Mediana", f"{delivered['delivery_days'].median():.1f} dias")

                fig_del = px.histogram(
                    delivered,
                    x="delivery_days",
                    nbins=40,
                    title="Distribuicao de Dias para Entrega",
                    labels={"delivery_days": "Dias", "count": "Pedidos"},
                    color_discrete_sequence=["#5B9BD5"],
                )
                fig_del.update_layout(
                    plot_bgcolor="white",
                    paper_bgcolor="white",
                    height=320,
                )
                st.plotly_chart(fig_del, use_container_width=True)


if __name__ == "__main__":
    main()
