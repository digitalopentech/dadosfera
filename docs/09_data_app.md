# Data App — Streamlit Analytics Platform

> **Caso Tecnico:** Dadosfera Data Platform
> **Documento:** 09 — Data App (Streamlit)
> **Data:** Abril de 2026
> **Versao:** 1.0

---

## 1. Visao Geral

O **Olist Analytics App** e uma aplicacao Streamlit multi-pagina que demonstra as capacidades
analiticas construidas sobre o dataset Olist. O app serve como camada de visualizacao e
exploracao interativa sobre o pipeline ETL/ML documentado nos notebooks e na Dadosfera.

### Paginas

| Pagina | Arquivo | Descricao |
|--------|---------|-----------|
| Home | `app.py` | Visao geral, metricas rapidas, status dos dados |
| Analise Exploratoria | `pages/1_Analise_Exploratoria.py` | EDA completa com filtros interativos |
| Similaridade de Produtos | `pages/2_Similaridade_Produtos.py` | Recomendacao via TF-IDF + cosseno |
| Features GenAI | `pages/3_GenAI_Features.py` | Exploracao de features extraidas por LLM |

---

## 2. Como Executar Localmente

### 2.1 Pre-requisitos

- Python 3.11+
- CSVs do dataset Olist na pasta `data/` (download: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
- Opcional: `data/genai_product_features.parquet` (gerado pelo notebook `03_genai_features.py`)

### 2.2 Instalacao

```bash
# Clonar o repositorio
git clone <repo-url>
cd case-dadosfera

# Criar ambiente virtual
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows

# Instalar dependencias do app
pip install -r streamlit_app/requirements.txt
```

### 2.3 Execucao

```bash
# A partir da raiz do repositorio
streamlit run streamlit_app/app.py
```

O app sera iniciado em `http://localhost:8501`.

### 2.4 Configuracao Opcional

Crie o arquivo `.streamlit/config.toml` para customizar o tema:

```toml
[theme]
primaryColor = "#1565C0"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F0F2F6"
textColor = "#262730"
font = "sans serif"

[server]
headless = true
port = 8501
```

---

## 3. Como Fazer Deploy no Streamlit Community Cloud

### 3.1 Pre-requisitos

- Conta em https://share.streamlit.io
- Repositorio publico no GitHub com o codigo do app
- CSVs no repositorio ou acessiveis via URL publica (ex.: Google Drive, S3)

### 3.2 Passo a Passo

**1. Preparar o repositorio**

```
case-dadosfera/
├── streamlit_app/
│   ├── app.py              ← entry point do app
│   ├── requirements.txt    ← dependencias do app
│   └── pages/
│       ├── 1_📊_Analise_Exploratoria.py
│       ├── 2_🔍_Similaridade_Produtos.py
│       └── 3_🤖_GenAI_Features.py
└── data/
    └── *.csv               ← arquivos de dados
```

**2. Fazer push para o GitHub**

```bash
git add streamlit_app/ data/
git commit -m "feat: add streamlit data app"
git push origin main
```

**3. Configurar no Streamlit Cloud**

1. Acessar https://share.streamlit.io
2. Clicar em **New app**
3. Selecionar o repositorio e branch `main`
4. Definir **Main file path:** `streamlit_app/app.py`
5. Clicar em **Deploy!**

**4. Configurar secrets (se necessario)**

No painel do Streamlit Cloud, em **Settings → Secrets**, adicionar:

```toml
[openai]
api_key = "sk-..."

[dadosfera]
username = "email@exemplo.com"
```

Acessar no codigo com:

```python
import streamlit as st
api_key = st.secrets["openai"]["api_key"]
```

### 3.3 Notas sobre Dados

Os CSVs do Olist (~100 MB total) podem ser versionados no repositorio se o tamanho total
do repo permitir. Para repos menores, uma alternativa e:

```python
# Carregar de URL publica
@st.cache_data
def load_data_from_url() -> pd.DataFrame:
    url = "https://storage.googleapis.com/meu-bucket/olist_orders_dataset.csv"
    return pd.read_csv(url)
```

---

## 4. Arquitetura do App

```
streamlit_app/
├── app.py                          # Configuracao global + Home page
│   ├── load_olist_data()           # @st.cache_data — carrega todos os CSVs
│   ├── build_enriched_orders()     # @st.cache_data — tabela analitica plana
│   ├── render_home()               # Pagina inicial
│   └── render_sidebar()            # Navegacao lateral
│
├── pages/
│   ├── 1_📊_Analise_Exploratoria.py
│   │   ├── load_data()             # @st.cache_data
│   │   ├── build_analytics_base()  # @st.cache_data — join completo
│   │   ├── render_kpi_cards()
│   │   ├── chart_revenue_over_time()
│   │   ├── chart_top_categories()
│   │   ├── chart_state_orders()    # Mapa coropletico BR
│   │   ├── chart_order_status_funnel()
│   │   └── chart_review_distribution()
│   │
│   ├── 2_🔍_Similaridade_Produtos.py
│   │   ├── load_product_catalog()  # @st.cache_data
│   │   ├── build_similarity_model() # @st.cache_resource — TF-IDF + matriz
│   │   ├── get_recommendations()
│   │   └── render_similarity_heatmap()
│   │
│   └── 3_🤖_GenAI_Features.py
│       ├── load_genai_features()   # @st.cache_data — real ou sintetico
│       ├── chart_sentiment_distribution()
│       ├── chart_quality_tier_by_category()
│       ├── chart_confidence_distribution()
│       ├── chart_use_case_treemap()
│       └── render_product_card()
│
└── requirements.txt
```

### 4.1 Estrategia de Cache

| Recurso | Decorator | Motivo |
|---------|-----------|--------|
| CSVs raw | `@st.cache_data` | Dados serializaveis, invalida com TTL |
| Tabela analitica | `@st.cache_data` | Resultado determinista de join |
| Modelo TF-IDF + matriz | `@st.cache_resource` | Objeto nao-serializavel, compartilhado entre sessoes |
| Features GenAI | `@st.cache_data` | Dados ou sinteticos, invalida com TTL |

### 4.2 Fluxo de Dados

```
CSVs Olist (disk)
      |
      v (cache_data)
load_data() ──→ dict[str, DataFrame]
      |
      v (cache_data)
build_analytics_base() ──→ DataFrame plano (orders + items + customers + products + reviews)
      |
      v (filtros Streamlit)
df_filtered ──→ charts e metricas
```

---

## 5. Descricao das Telas

### 5.1 Home

A tela inicial apresenta:
- Logo Dadosfera na sidebar
- 4 metricas rapidas: total de pedidos, produtos, clientes unicos e vendedores
- Diagrama de arquitetura da solucao em texto
- Cards descritivos das 3 paginas analiticas
- Tabela de status dos datasets carregados (linhas, colunas, % nulos)

[Screenshot placeholder: home_screen.png]

### 5.2 Analise Exploratoria

Organizada em 5 abas:

**Visao Geral:** 5 KPI cards + tabela de overview dos datasets
[Screenshot placeholder: eda_kpis.png]

**Tendencias Temporais:** Grafico de receita mensal com markers + distribuicao de avaliacoes + pedidos por dia da semana
[Screenshot placeholder: eda_temporal.png]

**Distribuicao Geografica:** Mapa coropletico do Brasil com densidade de pedidos + ranking de receita por UF
[Screenshot placeholder: eda_geo.png]

**Produtos:** Top 15 categorias por receita + funil de status dos pedidos
[Screenshot placeholder: eda_products.png]

**Qualidade:** Analise de nulos por coluna + distribuicao de dias de entrega + % de atrasos
[Screenshot placeholder: eda_quality.png]

### 5.3 Similaridade de Produtos

- Seletor de produto com busca por categoria e ID
- Card do produto selecionado com 5 metricas
- Grafico de barras com scores de similaridade dos top N
- Tabela interativa com os recomendados
- Heatmap de matriz de similaridade para comparacao multipla
- Expander com vocabulario TF-IDF

[Screenshot placeholder: similarity_main.png]
[Screenshot placeholder: similarity_heatmap.png]

### 5.4 Features GenAI

- Banner informativo quando usando dados sinteticos
- 5 KPI cards: produtos enriquecidos, confianca media, % positivo, % premium, categorias
- Aba Distribuicoes: pie chart sentimento + histograma confianca + barras categoria
- Aba Qualidade & Sentimento: stacked bar por tier/categoria + box plot scores
- Aba Use Cases: treemap de tags + barras de atributos chave
- Aba Cards: 12 cards visuais com todas as features extraidas

[Screenshot placeholder: genai_cards.png]
[Screenshot placeholder: genai_treemap.png]

---

## 6. Dependencias

```
streamlit  >= 1.32   # Multi-page, cache_resource, st.status
pandas     >= 2.1    # copy-on-write, ArrowDtype
numpy      >= 1.26   # compativel com scikit-learn 1.4
pyarrow    >= 14.0   # leitura de parquet refinado
scikit-learn >= 1.4  # TfidfVectorizer, cosine_similarity
plotly     >= 5.19   # choropleth, treemap, funnel, box
joblib     >= 1.3    # carregar modelos .joblib (opcional)
```

---

## 7. Limitacoes Conhecidas

| Limitacao | Impacto | Mitigacao |
|-----------|---------|-----------|
| Matriz TF-IDF carregada em memoria | ~100 MB para 32k produtos | `@st.cache_resource` — carrega uma unica vez por processo |
| CSVs no repositorio | Git LFS ou limite de tamanho | Alternativa: URL publica (S3, GCS) |
| Mapa coropletico usa GeoJSON externo | Falha offline | Embutir GeoJSON no repo como alternativa |
| Sem autenticacao | Qualquer um pode ver os dados | Streamlit Auth ou autenticacao por `.streamlit/secrets.toml` |

---

**Confianca:** 0.95 | **Impacto:** Alto
**Referencias:** Streamlit Docs | KB: python/patterns/clean-architecture.md
