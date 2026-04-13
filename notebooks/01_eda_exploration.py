# %% [markdown]
# # Analise Exploratoria de Dados (EDA) - Olist E-Commerce
#
# **Case Tecnico Dadosfera** | Leonardo Nunes | Abril 2026
#
# Este notebook realiza a analise exploratoria do dataset Olist Brazilian
# E-Commerce, contendo 100k+ pedidos de 2016 a 2018.
#
# **Objetivos:**
# - Entender a estrutura e volume dos dados
# - Identificar padroes e tendencias
# - Validar qualidade dos dados
# - Gerar insights para dashboards

# %% [markdown]
# ## 1. Setup e Instalacao

# %%
# !pip install pandas matplotlib seaborn plotly openpyxl -q

# %%
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import warnings

warnings.filterwarnings("ignore")
sns.set_theme(style="whitegrid", palette="husl")
plt.rcParams["figure.figsize"] = (12, 6)
plt.rcParams["font.size"] = 12

# %% [markdown]
# ## 2. Carregamento dos Dados
#
# O dataset Olist contem 9 tabelas CSV interrelacionadas.
# Baixe de: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce

# %%
# Ajuste o caminho conforme necessario
# No Google Colab, faca upload dos CSVs ou monte o Google Drive
DATA_DIR = Path("../data/olist")

# Para Google Colab, descomente:
# from google.colab import drive
# drive.mount('/content/drive')
# DATA_DIR = Path('/content/drive/MyDrive/case-dadosfera/data/olist')

# %%
# Carregar todos os datasets
datasets = {}
csv_files = {
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "categories": "product_category_name_translation.csv",
}

for name, filename in csv_files.items():
    filepath = DATA_DIR / filename
    if filepath.exists():
        datasets[name] = pd.read_csv(filepath)
        print(f"{name:15s}: {len(datasets[name]):>10,} registros | {len(datasets[name].columns):>2} colunas")
    else:
        print(f"{name:15s}: ARQUIVO NAO ENCONTRADO ({filepath})")

# %%
# Desempacotar para variaveis individuais
orders = datasets.get("orders", pd.DataFrame())
order_items = datasets.get("order_items", pd.DataFrame())
payments = datasets.get("payments", pd.DataFrame())
reviews = datasets.get("reviews", pd.DataFrame())
customers = datasets.get("customers", pd.DataFrame())
products = datasets.get("products", pd.DataFrame())
sellers = datasets.get("sellers", pd.DataFrame())
geolocation = datasets.get("geolocation", pd.DataFrame())
categories = datasets.get("categories", pd.DataFrame())

total_records = sum(len(df) for df in datasets.values())
print(f"\nTotal de registros em todas as tabelas: {total_records:,}")
print(f"Requisito minimo (100k): {'ATENDIDO' if total_records >= 100_000 else 'NAO ATENDIDO'}")

# %% [markdown]
# ## 3. Visao Geral das Tabelas

# %%
# Resumo de cada tabela
for name, df in datasets.items():
    print(f"\n{'='*60}")
    print(f"TABELA: {name.upper()}")
    print(f"{'='*60}")
    print(f"Registros: {len(df):,}")
    print(f"Colunas: {list(df.columns)}")
    print(f"\nTipos de dados:")
    print(df.dtypes.to_string())
    print(f"\nValores nulos:")
    nulls = df.isnull().sum()
    nulls_pct = (df.isnull().sum() / len(df) * 100).round(2)
    null_info = pd.DataFrame({"nulos": nulls, "percentual": nulls_pct})
    print(null_info[null_info["nulos"] > 0].to_string() if null_info["nulos"].sum() > 0 else "  Nenhum valor nulo")

# %% [markdown]
# ## 4. Analise de Pedidos

# %%
# Converter timestamps
date_cols = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]
for col in date_cols:
    if col in orders.columns:
        orders[col] = pd.to_datetime(orders[col])

# %%
# Distribuicao de status dos pedidos
status_counts = orders["order_status"].value_counts()
print("Distribuicao de Status dos Pedidos:")
print(status_counts)
print(f"\nTaxa de entrega: {status_counts.get('delivered', 0) / len(orders) * 100:.1f}%")

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

status_counts.plot(kind="barh", ax=axes[0], color=sns.color_palette("viridis", len(status_counts)))
axes[0].set_title("Distribuicao de Status dos Pedidos")
axes[0].set_xlabel("Quantidade")

status_counts.plot(kind="pie", ax=axes[1], autopct="%1.1f%%", startangle=90)
axes[1].set_title("Proporcao de Status")
axes[1].set_ylabel("")

plt.tight_layout()
plt.savefig("../docs/diagrams/order_status.png", dpi=150, bbox_inches="tight")
plt.show()

# %%
# Serie temporal de pedidos (mensal)
orders["year_month"] = orders["order_purchase_timestamp"].dt.to_period("M")
monthly = orders.groupby("year_month").agg(
    pedidos=("order_id", "count"),
).reset_index()
monthly["year_month"] = monthly["year_month"].astype(str)

fig, ax = plt.subplots(figsize=(14, 5))
ax.plot(monthly["year_month"], monthly["pedidos"], marker="o", linewidth=2, color="#2196F3")
ax.fill_between(range(len(monthly)), monthly["pedidos"], alpha=0.15, color="#2196F3")
ax.set_title("Evolucao Mensal de Pedidos (2016-2018)")
ax.set_xlabel("Mes")
ax.set_ylabel("Quantidade de Pedidos")
plt.xticks(rotation=45, ha="right")
plt.tight_layout()
plt.savefig("../docs/diagrams/monthly_orders.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ## 5. Analise Financeira

# %%
# Metricas financeiras
order_values = order_items.groupby("order_id").agg(
    total_price=("price", "sum"),
    total_freight=("freight_value", "sum"),
    items_count=("order_item_id", "count"),
).reset_index()
order_values["total_order"] = order_values["total_price"] + order_values["total_freight"]

print("Metricas Financeiras:")
print(f"  Receita total (produtos): R$ {order_values['total_price'].sum():,.2f}")
print(f"  Frete total:              R$ {order_values['total_freight'].sum():,.2f}")
print(f"  Receita total geral:      R$ {order_values['total_order'].sum():,.2f}")
print(f"  Ticket medio:             R$ {order_values['total_order'].mean():,.2f}")
print(f"  Ticket mediano:           R$ {order_values['total_order'].median():,.2f}")
print(f"  Items por pedido (media): {order_values['items_count'].mean():.2f}")

# %%
# Distribuicao de valores dos pedidos
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

axes[0].hist(order_values["total_order"], bins=50, range=(0, 1000), color="#4CAF50", edgecolor="white")
axes[0].set_title("Distribuicao de Valor dos Pedidos (ate R$ 1.000)")
axes[0].set_xlabel("Valor Total (R$)")
axes[0].set_ylabel("Frequencia")
axes[0].axvline(order_values["total_order"].median(), color="red", linestyle="--", label=f"Mediana: R$ {order_values['total_order'].median():.0f}")
axes[0].legend()

# Box plot por faixa
axes[1].boxplot(order_values["total_order"], vert=True, showfliers=False)
axes[1].set_title("Box Plot - Valor dos Pedidos (sem outliers)")
axes[1].set_ylabel("Valor Total (R$)")

plt.tight_layout()
plt.savefig("../docs/diagrams/order_values.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ## 6. Analise por Categoria de Produto

# %%
# Top 15 categorias por receita
items_products = order_items.merge(products, on="product_id", how="left")
items_products = items_products.merge(categories, on="product_category_name", how="left")

category_revenue = items_products.groupby("product_category_name_english").agg(
    receita=("price", "sum"),
    pedidos=("order_id", "nunique"),
    items=("order_item_id", "count"),
    ticket_medio=("price", "mean"),
).reset_index().sort_values("receita", ascending=False).head(15)

fig, ax = plt.subplots(figsize=(14, 7))
bars = ax.barh(
    category_revenue["product_category_name_english"],
    category_revenue["receita"],
    color=sns.color_palette("viridis", 15),
)
ax.set_title("Top 15 Categorias por Receita")
ax.set_xlabel("Receita (R$)")
ax.invert_yaxis()

for bar, val in zip(bars, category_revenue["receita"]):
    ax.text(val + 1000, bar.get_y() + bar.get_height() / 2, f"R$ {val:,.0f}", va="center", fontsize=9)

plt.tight_layout()
plt.savefig("../docs/diagrams/top_categories.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ## 7. Analise Geografica

# %%
# Pedidos por estado
orders_customers = orders.merge(customers, on="customer_id", how="left")
state_analysis = orders_customers.groupby("customer_state").agg(
    pedidos=("order_id", "count"),
).reset_index().sort_values("pedidos", ascending=False)

fig, ax = plt.subplots(figsize=(14, 6))
colors = sns.color_palette("YlOrRd", len(state_analysis))
ax.bar(state_analysis["customer_state"], state_analysis["pedidos"], color=colors[::-1])
ax.set_title("Distribuicao de Pedidos por Estado")
ax.set_xlabel("Estado")
ax.set_ylabel("Quantidade de Pedidos")
plt.xticks(rotation=0)
plt.tight_layout()
plt.savefig("../docs/diagrams/orders_by_state.png", dpi=150, bbox_inches="tight")
plt.show()

# Top 5 estados
print("\nTop 5 Estados por Pedidos:")
for _, row in state_analysis.head(5).iterrows():
    pct = row["pedidos"] / len(orders) * 100
    print(f"  {row['customer_state']}: {row['pedidos']:,} pedidos ({pct:.1f}%)")

# %% [markdown]
# ## 8. Analise de Pagamentos

# %%
# Metodos de pagamento
payment_dist = payments.groupby("payment_type").agg(
    transacoes=("order_id", "count"),
    valor_total=("payment_value", "sum"),
    valor_medio=("payment_value", "mean"),
    parcelas_media=("payment_installments", "mean"),
).reset_index().sort_values("transacoes", ascending=False)

print("Distribuicao de Metodos de Pagamento:")
for _, row in payment_dist.iterrows():
    pct = row["transacoes"] / len(payments) * 100
    print(f"  {row['payment_type']:15s}: {row['transacoes']:>8,} transacoes ({pct:5.1f}%) | "
          f"Valor medio: R$ {row['valor_medio']:>8.2f} | "
          f"Parcelas media: {row['parcelas_media']:.1f}")

# %%
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

payment_dist.plot(
    kind="pie", y="transacoes", labels=payment_dist["payment_type"],
    ax=axes[0], autopct="%1.1f%%", startangle=90
)
axes[0].set_title("Distribuicao de Metodos de Pagamento")
axes[0].set_ylabel("")

# Parcelas por metodo
credit_data = payments[payments["payment_type"] == "credit_card"]
axes[1].hist(credit_data["payment_installments"], bins=range(1, 25), color="#FF9800", edgecolor="white")
axes[1].set_title("Distribuicao de Parcelas (Cartao de Credito)")
axes[1].set_xlabel("Numero de Parcelas")
axes[1].set_ylabel("Frequencia")

plt.tight_layout()
plt.savefig("../docs/diagrams/payment_analysis.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ## 9. Analise de Satisfacao do Cliente

# %%
# Distribuicao de notas
score_dist = reviews["review_score"].value_counts().sort_index()

print("Distribuicao de Notas de Avaliacao:")
for score, count in score_dist.items():
    pct = count / len(reviews) * 100
    bar = "#" * int(pct)
    print(f"  {score} estrela{'s' if score > 1 else ''}: {count:>6,} ({pct:5.1f}%) {bar}")

print(f"\nNota media: {reviews['review_score'].mean():.2f}")
print(f"Nota mediana: {reviews['review_score'].median():.0f}")

# %%
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

colors_score = ["#f44336", "#ff9800", "#ffeb3b", "#8bc34a", "#4caf50"]
score_dist.plot(kind="bar", ax=axes[0], color=colors_score, edgecolor="white")
axes[0].set_title("Distribuicao de Notas de Avaliacao")
axes[0].set_xlabel("Nota")
axes[0].set_ylabel("Quantidade")
axes[0].set_xticklabels(axes[0].get_xticklabels(), rotation=0)

# NPS-like: promotores vs detratores
promoters = len(reviews[reviews["review_score"] >= 4])
passives = len(reviews[reviews["review_score"] == 3])
detractors = len(reviews[reviews["review_score"] <= 2])
nps = (promoters - detractors) / len(reviews) * 100

axes[1].bar(
    ["Detratores\n(1-2)", "Neutros\n(3)", "Promotores\n(4-5)"],
    [detractors, passives, promoters],
    color=["#f44336", "#ff9800", "#4caf50"],
)
axes[1].set_title(f"NPS Score: {nps:.0f}")
axes[1].set_ylabel("Quantidade")

plt.tight_layout()
plt.savefig("../docs/diagrams/satisfaction.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ## 10. Analise de Entregas

# %%
# Tempo de entrega
delivered = orders[orders["order_status"] == "delivered"].copy()
delivered["delivery_time"] = (
    delivered["order_delivered_customer_date"] - delivered["order_purchase_timestamp"]
).dt.days
delivered["delivery_delay"] = (
    delivered["order_delivered_customer_date"] - delivered["order_estimated_delivery_date"]
).dt.days

print("Metricas de Entrega:")
print(f"  Tempo medio de entrega: {delivered['delivery_time'].mean():.1f} dias")
print(f"  Tempo mediano:          {delivered['delivery_time'].median():.0f} dias")
print(f"  Entregas no prazo:      {(delivered['delivery_delay'] <= 0).sum():,} "
      f"({(delivered['delivery_delay'] <= 0).mean() * 100:.1f}%)")
print(f"  Entregas atrasadas:     {(delivered['delivery_delay'] > 0).sum():,} "
      f"({(delivered['delivery_delay'] > 0).mean() * 100:.1f}%)")
print(f"  Atraso medio (quando atrasado): {delivered[delivered['delivery_delay'] > 0]['delivery_delay'].mean():.1f} dias")

# %%
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

axes[0].hist(
    delivered["delivery_time"].clip(0, 60), bins=30,
    color="#2196F3", edgecolor="white", alpha=0.8
)
axes[0].axvline(delivered["delivery_time"].mean(), color="red", linestyle="--",
                label=f"Media: {delivered['delivery_time'].mean():.0f} dias")
axes[0].set_title("Distribuicao do Tempo de Entrega")
axes[0].set_xlabel("Dias")
axes[0].set_ylabel("Frequencia")
axes[0].legend()

on_time = (delivered["delivery_delay"] <= 0).sum()
late = (delivered["delivery_delay"] > 0).sum()
axes[1].pie(
    [on_time, late], labels=["No Prazo", "Atrasado"],
    autopct="%1.1f%%", colors=["#4CAF50", "#f44336"], startangle=90
)
axes[1].set_title("Entregas: No Prazo vs Atrasadas")

plt.tight_layout()
plt.savefig("../docs/diagrams/delivery_analysis.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ## 11. Resumo Executivo

# %%
print("=" * 60)
print("RESUMO EXECUTIVO - EDA Olist E-Commerce")
print("=" * 60)
print(f"""
VOLUME DE DADOS:
  - {len(orders):,} pedidos
  - {len(order_items):,} itens vendidos
  - {len(customers):,} clientes
  - {len(products):,} produtos
  - {len(sellers):,} vendedores
  - {total_records:,} registros totais

METRICAS FINANCEIRAS:
  - Receita total: R$ {order_values['total_order'].sum():,.2f}
  - Ticket medio: R$ {order_values['total_order'].mean():,.2f}
  - Ticket mediano: R$ {order_values['total_order'].median():,.2f}

SATISFACAO:
  - Nota media: {reviews['review_score'].mean():.2f}/5.0
  - NPS Score: {nps:.0f}
  - Promotores (4-5): {promoters / len(reviews) * 100:.1f}%

ENTREGAS:
  - Tempo medio: {delivered['delivery_time'].mean():.1f} dias
  - Taxa no prazo: {(delivered['delivery_delay'] <= 0).mean() * 100:.1f}%

GEOGRAFIA:
  - {orders_customers['customer_state'].nunique()} estados atendidos
  - Top estado: {state_analysis.iloc[0]['customer_state']} ({state_analysis.iloc[0]['pedidos']:,} pedidos)

CATEGORIAS:
  - {products['product_category_name'].nunique()} categorias de produtos
  - Top categoria: {category_revenue.iloc[0]['product_category_name_english']}
""")

# %% [markdown]
# ## Proximos Passos
#
# 1. **Data Quality** (Item 4): Rodar Great Expectations para validacao formal
# 2. **Feature Extraction** (Item 5): Usar GPT para extrair features de descricoes
# 3. **Star Schema** (Item 6): Implementar modelagem dimensional Kimball
# 4. **Dashboard** (Item 7): Criar visualizacoes no Metabase da Dadosfera
