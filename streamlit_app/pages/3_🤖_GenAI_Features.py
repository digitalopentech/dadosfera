"""
Pagina: Features GenAI
========================
Visualizacao e exploracao de features extraidas por LLM de descricoes de produtos.
Demonstra o pipeline de enrichment semantico: LLM → Features estruturadas → Analytics.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Features GenAI | Dadosfera",
    page_icon="🤖",
    layout="wide",
)

DATA_DIR = Path(__file__).parent.parent.parent / "data"
GENAI_FEATURES_PATH = DATA_DIR / "genai_product_features.parquet"

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ProductFeatureCard:
    """Structured representation of LLM-extracted features for one product."""

    product_id: str
    category_name: str
    extracted_category_en: str
    sentiment_label: str
    sentiment_score: float
    quality_tier: str
    use_case_tags: list[str] = field(default_factory=list)
    key_attributes: list[str] = field(default_factory=list)
    confidence_score: float = 0.0
    llm_model: str = "gpt-3.5-turbo"


# ---------------------------------------------------------------------------
# Sample/synthetic data generation (for demo when real data is unavailable)
# ---------------------------------------------------------------------------

SAMPLE_CATEGORIES = [
    "bed_bath_table", "health_beauty", "sports_leisure", "computers_accessories",
    "furniture_decor", "housewares", "watches_gifts", "telephony", "toys",
    "garden_tools", "auto", "cool_stuff", "office_furniture", "pet_shop",
]

CATEGORY_EN_MAP = {
    "bed_bath_table": "Bed, Bath & Table",
    "health_beauty": "Health & Beauty",
    "sports_leisure": "Sports & Leisure",
    "computers_accessories": "Computers & Accessories",
    "furniture_decor": "Furniture & Decor",
    "housewares": "Housewares",
    "watches_gifts": "Watches & Gifts",
    "telephony": "Telephony",
    "toys": "Toys",
    "garden_tools": "Garden Tools",
    "auto": "Auto Parts",
    "cool_stuff": "Cool Stuff",
    "office_furniture": "Office Furniture",
    "pet_shop": "Pet Shop",
}

QUALITY_TIERS = ["Premium", "Standard", "Economy"]
SENTIMENT_LABELS = ["Positivo", "Neutro", "Negativo"]

USE_CASE_TAGS_BY_CATEGORY: dict[str, list[str]] = {
    "health_beauty": ["personal_care", "skincare", "hygiene", "wellness"],
    "sports_leisure": ["fitness", "outdoor", "team_sports", "recreation"],
    "computers_accessories": ["productivity", "gaming", "peripherals", "networking"],
    "furniture_decor": ["home_office", "living_room", "bedroom", "storage"],
    "toys": ["education", "creative_play", "outdoor_play", "family"],
    "pet_shop": ["nutrition", "grooming", "accessories", "health"],
}

KEY_ATTRIBUTES_BY_CATEGORY: dict[str, list[str]] = {
    "health_beauty": ["dermatologist_tested", "cruelty_free", "natural_ingredients", "spf_protection"],
    "sports_leisure": ["waterproof", "lightweight", "high_durability", "ergonomic_design"],
    "computers_accessories": ["usb_c_compatible", "wireless", "plug_and_play", "cross_platform"],
    "furniture_decor": ["assembly_required", "eco_friendly_material", "modular", "space_saving"],
    "toys": ["age_3_plus", "safety_certified", "washable", "batteries_included"],
    "pet_shop": ["vet_approved", "grain_free", "natural_formula", "breed_specific"],
}


def _generate_synthetic_features(n: int = 500, seed: int = 42) -> pd.DataFrame:
    """
    Generate synthetic LLM-extracted features for demo purposes.
    Used when real genai_product_features.parquet is not available.
    """
    rng = np.random.default_rng(seed)
    random.seed(seed)

    rows = []
    for i in range(n):
        cat = random.choice(SAMPLE_CATEGORIES)
        cat_en = CATEGORY_EN_MAP.get(cat, cat)
        sentiment = random.choices(
            SENTIMENT_LABELS, weights=[0.55, 0.30, 0.15], k=1
        )[0]
        sentiment_score = float(
            rng.beta(7, 3) if sentiment == "Positivo"
            else rng.beta(5, 5) if sentiment == "Neutro"
            else rng.beta(3, 7)
        )
        quality = random.choices(QUALITY_TIERS, weights=[0.25, 0.55, 0.20], k=1)[0]
        confidence = float(rng.uniform(0.65, 0.98))

        use_cases = random.sample(
            USE_CASE_TAGS_BY_CATEGORY.get(cat, ["general"]),
            k=min(2, len(USE_CASE_TAGS_BY_CATEGORY.get(cat, ["general"]))),
        )
        key_attrs = random.sample(
            KEY_ATTRIBUTES_BY_CATEGORY.get(cat, ["standard"]),
            k=min(3, len(KEY_ATTRIBUTES_BY_CATEGORY.get(cat, ["standard"]))),
        )

        rows.append(
            {
                "product_id": f"synth_{i:05d}",
                "category_name": cat,
                "extracted_category_en": cat_en,
                "sentiment_label": sentiment,
                "sentiment_score": round(sentiment_score, 4),
                "quality_tier": quality,
                "use_case_tags": json.dumps(use_cases),
                "key_attributes": json.dumps(key_attrs),
                "confidence_score": round(confidence, 4),
                "llm_model": "gpt-3.5-turbo",
                "is_synthetic": True,
            }
        )

    return pd.DataFrame(rows)


@st.cache_data(show_spinner="Carregando features GenAI...")
def load_genai_features(data_dir: str = str(DATA_DIR)) -> tuple[pd.DataFrame, bool]:
    """
    Load LLM-extracted features.
    Returns (DataFrame, is_real_data: bool).
    Falls back to synthetic data if parquet file not found.
    """
    path = Path(data_dir) / "genai_product_features.parquet"

    if path.exists():
        try:
            df = pd.read_parquet(path)
            df["is_synthetic"] = False
            return df, True
        except Exception:
            pass

    # Fallback: synthetic demo data
    df = _generate_synthetic_features(n=500)
    return df, False


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------

def chart_sentiment_distribution(df: pd.DataFrame) -> None:
    """Pie chart of sentiment label distribution."""
    sentiment_counts = df["sentiment_label"].value_counts().reset_index()
    sentiment_counts.columns = ["sentiment_label", "count"]

    color_map = {"Positivo": "#66BB6A", "Neutro": "#FFA726", "Negativo": "#EF5350"}

    fig = px.pie(
        sentiment_counts,
        names="sentiment_label",
        values="count",
        title="Distribuicao de Sentimento",
        color="sentiment_label",
        color_discrete_map=color_map,
        hole=0.4,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(height=360, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)


def chart_quality_tier_by_category(df: pd.DataFrame) -> None:
    """Stacked bar chart of quality tiers by category."""
    pivot = (
        df.groupby(["extracted_category_en", "quality_tier"])
        .size()
        .reset_index(name="count")
    )
    top_cats = (
        df["extracted_category_en"]
        .value_counts()
        .head(10)
        .index.tolist()
    )
    pivot = pivot[pivot["extracted_category_en"].isin(top_cats)]

    fig = px.bar(
        pivot,
        x="extracted_category_en",
        y="count",
        color="quality_tier",
        title="Distribuicao de Qualidade por Categoria (Top 10)",
        labels={
            "extracted_category_en": "Categoria",
            "count": "Produtos",
            "quality_tier": "Tier",
        },
        color_discrete_map={
            "Premium": "#1565C0",
            "Standard": "#5B9BD5",
            "Economy": "#B3CDE8",
        },
        barmode="stack",
    )
    fig.update_layout(
        xaxis_tickangle=-30,
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=420,
    )
    st.plotly_chart(fig, use_container_width=True)


def chart_confidence_distribution(df: pd.DataFrame) -> None:
    """Histogram of LLM confidence scores."""
    fig = px.histogram(
        df,
        x="confidence_score",
        nbins=30,
        title="Distribuicao de Confianca do LLM",
        labels={"confidence_score": "Score de Confianca", "count": "Quantidade"},
        color_discrete_sequence=["#5B9BD5"],
    )
    fig.add_vline(
        x=df["confidence_score"].mean(),
        line_dash="dash",
        line_color="red",
        annotation_text=f"Media: {df['confidence_score'].mean():.3f}",
        annotation_position="top right",
    )
    fig.update_layout(plot_bgcolor="white", paper_bgcolor="white", height=340)
    st.plotly_chart(fig, use_container_width=True)


def chart_sentiment_score_boxplot(df: pd.DataFrame) -> None:
    """Box plot of sentiment scores by category."""
    top_cats = df["extracted_category_en"].value_counts().head(8).index.tolist()
    df_top = df[df["extracted_category_en"].isin(top_cats)].copy()

    fig = px.box(
        df_top,
        x="extracted_category_en",
        y="sentiment_score",
        color="quality_tier",
        title="Score de Sentimento por Categoria e Tier",
        labels={
            "extracted_category_en": "Categoria",
            "sentiment_score": "Score de Sentimento",
            "quality_tier": "Tier",
        },
        color_discrete_map={
            "Premium": "#1565C0",
            "Standard": "#5B9BD5",
            "Economy": "#B3CDE8",
        },
    )
    fig.update_layout(
        xaxis_tickangle=-30,
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=420,
    )
    st.plotly_chart(fig, use_container_width=True)


def chart_use_case_treemap(df: pd.DataFrame) -> None:
    """Treemap of use case tag frequency."""
    all_tags: list[str] = []
    all_cats: list[str] = []

    for _, row in df.iterrows():
        try:
            tags = json.loads(row["use_case_tags"]) if isinstance(row["use_case_tags"], str) else []
        except (json.JSONDecodeError, TypeError):
            tags = []
        for tag in tags:
            all_tags.append(tag)
            all_cats.append(row["extracted_category_en"])

    if not all_tags:
        st.info("Dados de use_case_tags nao disponiveis.")
        return

    tag_df = pd.DataFrame({"tag": all_tags, "category": all_cats})
    tag_counts = tag_df.groupby(["category", "tag"]).size().reset_index(name="count")
    tag_counts = tag_counts.nlargest(60, "count")

    fig = px.treemap(
        tag_counts,
        path=["category", "tag"],
        values="count",
        title="Mapa de Use Cases Extraidos por LLM",
        color="count",
        color_continuous_scale="Blues",
    )
    fig.update_layout(height=480)
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Product feature cards
# ---------------------------------------------------------------------------

def render_product_card(row: pd.Series) -> None:
    """Render a styled card for a single product's LLM features."""
    sentiment_colors = {"Positivo": "#E8F5E9", "Neutro": "#FFF9C4", "Negativo": "#FFEBEE"}
    bg = sentiment_colors.get(row.get("sentiment_label", "Neutro"), "#F5F5F5")

    try:
        tags = json.loads(row["use_case_tags"]) if isinstance(row.get("use_case_tags"), str) else []
        attrs = json.loads(row["key_attributes"]) if isinstance(row.get("key_attributes"), str) else []
    except (json.JSONDecodeError, TypeError):
        tags = []
        attrs = []

    tags_html = " ".join(
        f'<span style="background:#E3F2FD;padding:2px 8px;border-radius:12px;font-size:0.8rem">{t}</span>'
        for t in tags
    )
    attrs_html = " ".join(
        f'<span style="background:#E8F5E9;padding:2px 8px;border-radius:12px;font-size:0.8rem">{a}</span>'
        for a in attrs
    )

    st.markdown(
        f"""
        <div style="background:{bg};padding:16px;border-radius:10px;margin-bottom:12px;
                    border-left:4px solid #1565C0;">
            <strong>🏷️ {row.get('extracted_category_en', 'N/A')}</strong>
            <span style="float:right;color:#666;font-size:0.85rem">
                Confianca: {row.get('confidence_score', 0):.1%}
            </span>
            <br>
            <code style="font-size:0.75rem;color:#888">{row.get('product_id', '')}</code>
            <br><br>
            <strong>Sentimento:</strong> {row.get('sentiment_label', 'N/A')}
            (score: {row.get('sentiment_score', 0):.3f})
            &nbsp;|&nbsp;
            <strong>Tier:</strong> {row.get('quality_tier', 'N/A')}
            <br><br>
            <strong>Use Cases:</strong> {tags_html or '<em>N/A</em>'}
            <br>
            <strong>Atributos:</strong> {attrs_html or '<em>N/A</em>'}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

def main() -> None:
    st.title("Features GenAI — Extracao por LLM")
    st.caption("Pipeline de enrichment semantico: Amazon Product Data → GPT → Features estruturadas")

    df, is_real = load_genai_features()

    if not is_real:
        st.info(
            "Dados sinteticos para demonstracao. Para dados reais, execute o notebook "
            "`03_genai_features.py` e salve em `data/genai_product_features.parquet`.",
            icon="ℹ️",
        )
    else:
        st.success(f"Features reais carregadas: {len(df):,} produtos enriquecidos.")

    # ---- Pipeline explanation ------------------------------------------
    with st.expander("Como funciona o pipeline de Features GenAI"):
        st.markdown(
            """
            ```
            Produto Olist (sem descricao)
                    |
                    v
            [Match por categoria → Amazon Product Data]
                    |
                    v
            [Prompt LLM] → Extrair:
              - sentiment_label (Positivo/Neutro/Negativo)
              - sentiment_score (0.0 a 1.0)
              - quality_tier (Premium/Standard/Economy)
              - use_case_tags (lista de tags de uso)
              - key_attributes (atributos chave do produto)
              - confidence_score (confianca do modelo)
                    |
                    v
            [JSON estruturado → DataFrame → Parquet]
                    |
                    v
            [JOIN com dim_product → Refinado enriquecido]
            ```

            **Modelo utilizado:** GPT-3.5-turbo (OpenAI API)
            **Estrategia de prompt:** Few-shot com 3 exemplos por categoria
            **Custo estimado:** ~$0.002 por produto (100k produtos ≈ $200)
            """
        )

    # ---- Top KPIs -------------------------------------------------------
    st.divider()
    col1, col2, col3, col4, col5 = st.columns(5)

    total_products = len(df)
    avg_confidence = df["confidence_score"].mean()
    pct_positive = 100 * (df["sentiment_label"] == "Positivo").mean()
    pct_premium = 100 * (df["quality_tier"] == "Premium").mean()
    n_categories = df["extracted_category_en"].nunique()

    col1.metric("Produtos Enriquecidos", f"{total_products:,}")
    col2.metric("Confianca Media", f"{avg_confidence:.1%}")
    col3.metric("Sentimento Positivo", f"{pct_positive:.1f}%")
    col4.metric("Tier Premium", f"{pct_premium:.1f}%")
    col5.metric("Categorias Unicas", str(n_categories))

    # ---- Sidebar filters -----------------------------------------------
    st.sidebar.header("Filtros")

    all_categories = sorted(df["extracted_category_en"].dropna().unique().tolist())
    sel_categories = st.sidebar.multiselect(
        "Categorias", options=all_categories, default=[]
    )

    all_sentiments = sorted(df["sentiment_label"].dropna().unique().tolist())
    sel_sentiments = st.sidebar.multiselect(
        "Sentimento", options=all_sentiments, default=[]
    )

    all_tiers = sorted(df["quality_tier"].dropna().unique().tolist())
    sel_tiers = st.sidebar.multiselect(
        "Quality Tier", options=all_tiers, default=[]
    )

    min_conf = st.sidebar.slider(
        "Confianca Minima", min_value=0.0, max_value=1.0, value=0.0, step=0.05
    )

    # Apply filters
    mask = pd.Series([True] * len(df), index=df.index)
    if sel_categories:
        mask &= df["extracted_category_en"].isin(sel_categories)
    if sel_sentiments:
        mask &= df["sentiment_label"].isin(sel_sentiments)
    if sel_tiers:
        mask &= df["quality_tier"].isin(sel_tiers)
    mask &= df["confidence_score"] >= min_conf

    df_filtered = df[mask].copy()
    st.caption(f"Exibindo {len(df_filtered):,} de {len(df):,} produtos")

    if df_filtered.empty:
        st.warning("Nenhum produto encontrado com os filtros aplicados.")
        st.stop()

    # ---- Charts --------------------------------------------------------
    st.divider()

    tab_dist, tab_qual, tab_usecases, tab_cards = st.tabs(
        ["Distribuicoes", "Qualidade & Sentimento", "Use Cases", "Cards de Produtos"]
    )

    with tab_dist:
        col_l, col_r = st.columns(2)
        with col_l:
            chart_sentiment_distribution(df_filtered)
        with col_r:
            chart_confidence_distribution(df_filtered)

        # Category breakdown
        cat_counts = df_filtered["extracted_category_en"].value_counts().head(15).reset_index()
        cat_counts.columns = ["category", "count"]
        fig_cats = px.bar(
            cat_counts,
            x="count",
            y="category",
            orientation="h",
            title="Produtos por Categoria Extraida (Top 15)",
            labels={"count": "Quantidade", "category": "Categoria"},
            color_discrete_sequence=["#5B9BD5"],
        )
        fig_cats.update_layout(
            yaxis={"categoryorder": "total ascending"},
            plot_bgcolor="white",
            paper_bgcolor="white",
            height=440,
        )
        st.plotly_chart(fig_cats, use_container_width=True)

    with tab_qual:
        chart_quality_tier_by_category(df_filtered)
        chart_sentiment_score_boxplot(df_filtered)

    with tab_usecases:
        chart_use_case_treemap(df_filtered)

        # Key attributes word frequency
        all_attrs: list[str] = []
        for val in df_filtered["key_attributes"]:
            try:
                attrs = json.loads(val) if isinstance(val, str) else []
            except (json.JSONDecodeError, TypeError):
                attrs = []
            all_attrs.extend(attrs)

        if all_attrs:
            attr_counts = pd.Series(all_attrs).value_counts().head(20).reset_index()
            attr_counts.columns = ["attribute", "count"]
            fig_attrs = px.bar(
                attr_counts,
                x="count",
                y="attribute",
                orientation="h",
                title="Atributos Chave mais Frequentes",
                labels={"count": "Frequencia", "attribute": "Atributo"},
                color="count",
                color_continuous_scale="Blues",
            )
            fig_attrs.update_layout(
                yaxis={"categoryorder": "total ascending"},
                coloraxis_showscale=False,
                plot_bgcolor="white",
                paper_bgcolor="white",
                height=480,
            )
            st.plotly_chart(fig_attrs, use_container_width=True)

    with tab_cards:
        st.subheader("Cards de Produtos — Features Extraidas por LLM")
        st.caption("Mostrando 12 amostras do conjunto filtrado.")

        sample_size = min(12, len(df_filtered))
        sample_df = df_filtered.sample(n=sample_size, random_state=42)

        col1_c, col2_c = st.columns(2)
        for i, (_, row) in enumerate(sample_df.iterrows()):
            with col1_c if i % 2 == 0 else col2_c:
                render_product_card(row)

    # ---- Data table ---------------------------------------------------
    st.divider()
    with st.expander("Tabela de dados completa"):
        display_cols = [
            c for c in [
                "product_id", "extracted_category_en", "sentiment_label",
                "sentiment_score", "quality_tier", "confidence_score",
                "use_case_tags", "key_attributes",
            ] if c in df_filtered.columns
        ]
        st.dataframe(
            df_filtered[display_cols].reset_index(drop=True),
            use_container_width=True,
            height=400,
        )
        st.download_button(
            label="Baixar CSV",
            data=df_filtered[display_cols].to_csv(index=False).encode("utf-8"),
            file_name="genai_features_filtered.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()
