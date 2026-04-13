"""
Pagina: Similaridade de Produtos
==================================
TF-IDF + Cosine Similarity para recomendacao de produtos Olist.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Similaridade de Produtos | Dadosfera",
    page_icon="🔍",
    layout="wide",
)

DATA_DIR = Path(__file__).parent.parent.parent / "data"

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Carregando catalogo de produtos...")
def load_product_catalog(data_dir: str = str(DATA_DIR)) -> pd.DataFrame:
    """Load and enrich products with category translation and order stats."""
    base = Path(data_dir)

    products_path = base / "olist_products_dataset.csv"
    items_path = base / "olist_order_items_dataset.csv"
    reviews_path = base / "olist_order_reviews_dataset.csv"
    trans_path = base / "product_category_name_translation.csv"

    if not products_path.exists():
        return pd.DataFrame()

    products = pd.read_csv(products_path, low_memory=False)

    # Translation
    if trans_path.exists():
        trans = pd.read_csv(trans_path)
        products = products.merge(trans, on="product_category_name", how="left")
        products["category_label"] = products["product_category_name_english"].fillna(
            products["product_category_name"]
        )
    else:
        products["category_label"] = products["product_category_name"]

    # Order stats
    if items_path.exists():
        items = pd.read_csv(items_path, low_memory=False)
        stats = items.groupby("product_id").agg(
            order_count=("order_id", "nunique"),
            avg_price=("price", "mean"),
            total_revenue=("price", "sum"),
        ).reset_index()
        products = products.merge(stats, on="product_id", how="left")

        # Avg review score per product
        if reviews_path.exists():
            reviews = pd.read_csv(reviews_path, low_memory=False)
            order_reviews = items[["order_id", "product_id"]].merge(
                reviews[["order_id", "review_score"]], on="order_id", how="left"
            )
            prod_reviews = (
                order_reviews.groupby("product_id")["review_score"]
                .mean()
                .reset_index()
                .rename(columns={"review_score": "avg_review_score"})
            )
            products = products.merge(prod_reviews, on="product_id", how="left")

    # Numeric cleanup
    for col in ["product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"]:
        if col in products.columns:
            products[col] = pd.to_numeric(products[col], errors="coerce").fillna(0)

    products["product_volume_cm3"] = (
        products.get("product_length_cm", 0)
        * products.get("product_height_cm", 0)
        * products.get("product_width_cm", 0)
    )

    # Fill sales stats
    for col, default in [("order_count", 0), ("avg_price", 0.0), ("avg_review_score", 3.0)]:
        if col in products.columns:
            products[col] = products[col].fillna(default)

    # Text corpus for TF-IDF
    products["text_corpus"] = (
        products["category_label"].fillna("").str.replace("_", " ")
        + " "
        + products["product_category_name"].fillna("").str.replace("_", " ")
        + " weight "
        + products["product_weight_g"].astype(str)
        + " volume "
        + products["product_volume_cm3"].astype(str)
    ).str.strip()

    return products.reset_index(drop=True)


@st.cache_resource(show_spinner="Calculando similaridade TF-IDF...")
def build_similarity_model(data_dir: str = str(DATA_DIR)) -> tuple[np.ndarray, list[str], TfidfVectorizer]:
    """Fit TF-IDF and compute full cosine similarity matrix. Cached as resource."""
    products = load_product_catalog(data_dir)
    if products.empty:
        return np.array([]), [], TfidfVectorizer()

    corpus = products["text_corpus"].tolist()
    product_ids = products["product_id"].tolist()

    vectorizer = TfidfVectorizer(
        max_features=500,
        ngram_range=(1, 2),
        min_df=2,
        sublinear_tf=True,
    )
    tfidf_matrix = vectorizer.fit_transform(corpus)
    sim_matrix = cosine_similarity(tfidf_matrix, dense_output=True)

    return sim_matrix, product_ids, vectorizer


# ---------------------------------------------------------------------------
# Recommendation helpers
# ---------------------------------------------------------------------------

def get_recommendations(
    product_id: str,
    sim_matrix: np.ndarray,
    product_ids: list[str],
    products_df: pd.DataFrame,
    top_n: int = 10,
) -> pd.DataFrame:
    """Return top_n most similar products for a given product_id."""
    if product_id not in product_ids:
        return pd.DataFrame()

    idx = product_ids.index(product_id)
    scores = sim_matrix[idx].copy()
    scores[idx] = -1  # exclude self

    top_indices = np.argsort(scores)[::-1][:top_n]

    result = pd.DataFrame(
        {
            "product_id": [product_ids[i] for i in top_indices],
            "similarity_score": scores[top_indices],
        }
    )

    # Enrich with product info
    cols_to_join = ["product_id", "category_label", "avg_price", "avg_review_score", "order_count"]
    available = [c for c in cols_to_join if c in products_df.columns]
    result = result.merge(products_df[available], on="product_id", how="left")

    return result


# ---------------------------------------------------------------------------
# Heatmap helper
# ---------------------------------------------------------------------------

def render_similarity_heatmap(
    product_ids_subset: list[str],
    sim_matrix: np.ndarray,
    all_product_ids: list[str],
    products_df: pd.DataFrame,
) -> None:
    """Render a heatmap of pairwise similarities for a product subset."""
    valid_ids = [pid for pid in product_ids_subset if pid in all_product_ids]
    if len(valid_ids) < 2:
        st.info("Selecione pelo menos 2 produtos para o heatmap.")
        return

    indices = [all_product_ids.index(pid) for pid in valid_ids]
    sub_matrix = sim_matrix[np.ix_(indices, indices)]

    # Labels: category + product_id (last 8 chars)
    labels = []
    for pid in valid_ids:
        row = products_df[products_df["product_id"] == pid]
        cat = row["category_label"].values[0] if not row.empty and "category_label" in row.columns else pid[:8]
        labels.append(f"{cat[:20]}...{pid[-6:]}")

    fig = go.Figure(
        data=go.Heatmap(
            z=sub_matrix,
            x=labels,
            y=labels,
            colorscale="Blues",
            zmin=0,
            zmax=1,
            text=np.round(sub_matrix, 3),
            texttemplate="%{text}",
            textfont={"size": 10},
        )
    )
    fig.update_layout(
        title="Matriz de Similaridade (Cosseno)",
        xaxis_tickangle=-45,
        height=500,
        margin={"l": 150, "b": 150},
    )
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

def main() -> None:
    st.title("Similaridade de Produtos")
    st.caption("Filtragem baseada em conteudo — TF-IDF + Similaridade de Cosseno")
    st.markdown(
        """
        Selecione um produto do catalogo Olist para visualizar os 10 produtos mais similares,
        calculados via **TF-IDF** sobre categoria e atributos fisicos com **similaridade de cosseno**.
        """
    )

    products = load_product_catalog()
    if products.empty:
        st.error(
            f"Catalogo de produtos nao encontrado em `{DATA_DIR}`. "
            "Certifique-se de que `olist_products_dataset.csv` esta na pasta `/data`."
        )
        st.stop()

    sim_matrix, product_ids, vectorizer = build_similarity_model()

    if sim_matrix.size == 0:
        st.error("Nao foi possivel construir o modelo de similaridade.")
        st.stop()

    # ---- Sidebar controls -----------------------------------------------
    st.sidebar.header("Configuracoes")
    top_n = st.sidebar.slider("Top N Recomendacoes", min_value=5, max_value=20, value=10)

    category_options = sorted(products["category_label"].dropna().unique().tolist())
    selected_category = st.sidebar.selectbox(
        "Filtrar por Categoria", options=["Todas"] + category_options
    )

    # ---- Product selector -----------------------------------------------
    if selected_category != "Todas":
        filtered_products = products[products["category_label"] == selected_category].copy()
    else:
        filtered_products = products.copy()

    # Build display labels
    if "order_count" in filtered_products.columns:
        filtered_products["display_label"] = (
            filtered_products["category_label"].fillna("N/A")
            + " | "
            + filtered_products["product_id"].str[-8:]
            + " | Vendas: "
            + filtered_products["order_count"].astype(int).astype(str)
        )
    else:
        filtered_products["display_label"] = (
            filtered_products["category_label"].fillna("N/A")
            + " | "
            + filtered_products["product_id"].str[-8:]
        )

    selected_label = st.selectbox(
        "Selecione um Produto",
        options=filtered_products["display_label"].tolist(),
        help="Busque por categoria ou ID do produto",
    )

    selected_row = filtered_products[filtered_products["display_label"] == selected_label]
    if selected_row.empty:
        st.warning("Produto nao encontrado.")
        st.stop()

    selected_product_id = selected_row["product_id"].iloc[0]

    # ---- Selected product card ------------------------------------------
    st.divider()
    st.subheader("Produto Selecionado")

    card_cols = st.columns(5)
    card_data = [
        ("Categoria", selected_row.get("category_label", pd.Series(["N/A"])).iloc[0]),
        ("Preco Medio", f"R$ {selected_row['avg_price'].iloc[0]:,.2f}" if "avg_price" in selected_row else "N/A"),
        ("Avaliacao Media", f"{selected_row['avg_review_score'].iloc[0]:.2f}" if "avg_review_score" in selected_row else "N/A"),
        ("Total Vendas", f"{int(selected_row['order_count'].iloc[0]):,}" if "order_count" in selected_row else "N/A"),
        ("Peso (g)", f"{int(selected_row.get('product_weight_g', pd.Series([0])).iloc[0]):,}" if "product_weight_g" in selected_row.columns else "N/A"),
    ]
    for col, (label, value) in zip(card_cols, card_data):
        col.metric(label, value)

    st.caption(f"**Product ID:** `{selected_product_id}`")

    # ---- Recommendations ------------------------------------------------
    st.divider()
    st.subheader(f"Top {top_n} Produtos Similares")

    recs = get_recommendations(
        selected_product_id, sim_matrix, product_ids, products, top_n=top_n
    )

    if recs.empty:
        st.warning("Nenhuma recomendacao disponivel para este produto.")
        st.stop()

    # Chart: similarity scores
    fig_scores = px.bar(
        recs,
        x="similarity_score",
        y=recs.index.astype(str).map(lambda i: f"#{int(i)+1}"),
        orientation="h",
        title="Score de Similaridade de Cosseno",
        labels={"similarity_score": "Similaridade", "y": "Rank"},
        color="similarity_score",
        color_continuous_scale="Blues",
        hover_data={"similarity_score": ":.4f"},
    )
    fig_scores.update_layout(
        yaxis={"categoryorder": "total ascending"},
        coloraxis_showscale=False,
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=420,
    )

    col_chart, col_table = st.columns([1, 1])

    with col_chart:
        st.plotly_chart(fig_scores, use_container_width=True)

    with col_table:
        display_cols = ["product_id", "similarity_score"]
        if "category_label" in recs.columns:
            display_cols.insert(1, "category_label")
        if "avg_price" in recs.columns:
            display_cols.append("avg_price")
        if "avg_review_score" in recs.columns:
            display_cols.append("avg_review_score")

        recs_display = recs[display_cols].copy()
        recs_display.index = range(1, len(recs_display) + 1)
        recs_display.index.name = "Rank"

        st.dataframe(
            recs_display.rename(columns={
                "product_id": "Product ID",
                "category_label": "Categoria",
                "similarity_score": "Similaridade",
                "avg_price": "Preco Medio",
                "avg_review_score": "Avaliacao",
            }),
            use_container_width=True,
        )

    # ---- Similarity heatmap ---------------------------------------------
    st.divider()
    st.subheader("Matriz de Similaridade — Comparacao Interativa")
    st.caption("Selecione produtos adicionais para comparar na matriz.")

    other_products = products[products["product_id"] != selected_product_id].copy()
    if "order_count" in other_products.columns:
        popular = other_products.nlargest(50, "order_count")
    else:
        popular = other_products.head(50)

    popular_labels = (
        popular["category_label"].fillna("N/A").str[:20]
        + " | "
        + popular["product_id"].str[-8:]
    ).tolist()

    selected_compare_labels = st.multiselect(
        "Adicionar produtos à comparacao (top 50 mais vendidos):",
        options=popular_labels,
        max_selections=9,
        help="Selecione ate 9 produtos para visualizar a matriz de similaridade.",
    )

    heatmap_pids = [selected_product_id]
    for lbl in selected_compare_labels:
        pid_suffix = lbl.split(" | ")[-1]
        match = popular[popular["product_id"].str.endswith(pid_suffix)]
        if not match.empty:
            heatmap_pids.append(match["product_id"].iloc[0])

    # Also add top recommendations
    if len(heatmap_pids) < 5 and not recs.empty:
        heatmap_pids += recs["product_id"].head(4).tolist()

    heatmap_pids = list(dict.fromkeys(heatmap_pids))  # dedup preserving order

    render_similarity_heatmap(heatmap_pids, sim_matrix, product_ids, products)

    # ---- TF-IDF vocabulary insight --------------------------------------
    with st.expander("Inspecionar vocabulario TF-IDF"):
        feature_names = vectorizer.get_feature_names_out()
        st.write(f"Vocabulario com **{len(feature_names):,} termos**. Amostra:")
        st.write(", ".join(feature_names[:50]))


if __name__ == "__main__":
    main()
