# %% [markdown]
# # 03 - Extracao de Features com LLM (GPT-4o-mini)
#
# **Case Tecnico Dadosfera - GenAI Feature Extraction**
#
# Este notebook implementa a extracao de atributos estruturados a partir de dados
# nao-estruturados de produtos (titulo + descricao) utilizando o modelo GPT-4o-mini
# da OpenAI.
#
# ## Pipeline
#
# ```
# Dados Brutos (titulo + descricao)
#     -> Prompt Engineering (few-shot + schema)
#         -> GPT-4o-mini (temperature=0.0)
#             -> Validacao de Schema
#                 -> DataFrame Estruturado
#                     -> CSV + JSON + Visualizacoes
# ```
#
# ## Requisitos
# - Chave de API da OpenAI (`OPENAI_API_KEY`)
# - Python 3.10+

# %% [markdown]
# ## 1. Setup e Instalacao

# %%
# Instalacao de dependencias (descomente no Google Colab)
# !pip install openai pandas tqdm matplotlib seaborn --quiet

# %%
import os
import json
import time
import logging
from typing import Optional

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import seaborn as sns
from tqdm import tqdm
from openai import OpenAI, RateLimitError, APITimeoutError, APIError

# %%
# Configuracao de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# %%
# Configuracao da API OpenAI
# No Google Colab, defina a variavel de ambiente ou use google.colab.userdata:
#
#   from google.colab import userdata
#   os.environ["OPENAI_API_KEY"] = userdata.get("OPENAI_API_KEY")
#
# Em ambiente local, defina no .env ou exporte no terminal:
#   export OPENAI_API_KEY="sk-..."

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "sk-YOUR-API-KEY-HERE")

client = OpenAI(api_key=OPENAI_API_KEY)

# Modelo e parametros
MODEL_NAME = "gpt-4o-mini"
TEMPERATURE = 0.0
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # segundos

# Custos por 1M tokens (GPT-4o-mini, abril 2026)
COST_INPUT_PER_1M = 0.15   # USD
COST_OUTPUT_PER_1M = 0.60  # USD

# %% [markdown]
# ## 2. Dados de Exemplo
#
# Simulacao de produtos do dataset Amazon Product Data com titulos e descricoes
# realistas, cobrindo categorias variadas: capas de celular, eletronicos,
# vestuario, acessorios, etc.

# %%
SAMPLE_PRODUCTS = [
    {
        "product_id": "B01N1SE4EP",
        "title": "FYY Leather Case with Mirror for Samsung Galaxy S8 Plus, Leather Wallet Flip Folio Case with Mirror and Wrist Strap for Samsung Galaxy S8 Plus, Black",
        "description": "Premium PU Leather Top quality. Receiver design for hand-free to answer to phone. Hand strap makes it easy to carry around. RFID Technique: protect your personal information with RFID blocking technology. Multiple card slots and side pocket for cash and receipts.",
    },
    {
        "product_id": "B07HQKZ8WM",
        "title": "Anker Soundcore Life Q20 Hybrid Active Noise Cancelling Headphones, Wireless Over Ear Bluetooth Headphones with 40H Playtime, Hi-Res Audio, Deep Bass, Memory Foam Ear Cups",
        "description": "Reduce ambient noise by up to 90% with advanced hybrid active noise cancellation. Custom 40mm drivers produce Hi-Res Audio certified sound. 40 hours of playtime in wireless active noise cancelling mode. BassUp technology uses a custom algorithm to enhance bass in real-time. Memory foam ear cups provide a comfortable fit for extended listening.",
    },
    {
        "product_id": "B08N5WRWNW",
        "title": "Apple AirPods Pro (2nd Generation) Wireless Ear Buds with USB-C Charging, Active Noise Cancellation, Transparency Mode, Personalized Spatial Audio, MagSafe Charging Case",
        "description": "Apple-designed H2 chip for smarter noise cancellation and immersive sound. Up to 2x more active noise cancellation than the previous generation. Adaptive Transparency lets outside sounds in while reducing loud noises. Personalized Spatial Audio with dynamic head tracking. Touch control lets you swipe to adjust volume.",
    },
    {
        "product_id": "B09V3KXJPB",
        "title": "Hanes Men's EcoSmart Fleece Sweatshirt, Cotton-Blend Pullover, Crewneck Sweatshirt for Men, Charcoal Heather, Large",
        "description": "Made with a cotton-rich blend for softness. EcoSmart fibers made from recycled plastic bottles. Tag-free comfort. Lay-flat collar. Ribbed waistband and cuffs. Machine washable. Available in multiple colors and sizes.",
    },
    {
        "product_id": "B0BSHF7WHT",
        "title": "JBL Charge 5 - Portable Bluetooth Speaker with IP67 Waterproof and USB Charge Out, Red",
        "description": "JBL Pro Sound delivers powerful audio with its optimized long excursion driver and dual JBL bass radiators. Stream wirelessly via Bluetooth 5.1. IP67 waterproof and dustproof rating for outdoor use. Built-in powerbank lets you charge devices via USB. Up to 20 hours of playtime. PartyBoost allows you to pair two JBL speakers together.",
    },
    {
        "product_id": "B0C8PSQW8N",
        "title": "Amazon Basics Microfiber Cleaning Cloths, Non-Abrasive, Reusable and Washable, Pack of 24, Blue/White/Yellow",
        "description": "Includes 24 microfiber cleaning cloths in 3 colors. Ultra-soft, non-abrasive material safe for all surfaces. Highly absorbent for effective cleaning. Lint-free and streak-free finish. Machine washable for hundreds of uses. Ideal for home, auto, and office use.",
    },
    {
        "product_id": "B08J65DST5",
        "title": "SAMSUNG Galaxy Tab A7 10.4 Wi-Fi 32GB Tablet, Dark Gray - SM-T500NZAAXAR",
        "description": "Immersive 10.4-inch display with slim bezels. Dolby Atmos surround sound with quad speakers. 32GB internal storage expandable up to 1TB via microSD. 8MP rear camera and 5MP front camera. 7,040mAh battery provides up to 13 hours of streaming. Samsung Knox security platform built in.",
    },
    {
        "product_id": "B0849J32ZP",
        "title": "Hydro Flask Wide Mouth Straw Lid Water Bottle - Stainless Steel, Reusable, Vacuum Insulated, 32 oz, Pacific",
        "description": "TempShield vacuum insulation keeps beverages cold up to 24 hours and hot up to 12 hours. Pro-Grade stainless steel construction. BPA-free and phthalate-free. Wide mouth opening for easy filling and cleaning. Durable powder coat finish. Straw lid included for easy sipping.",
    },
    {
        "product_id": "B07FZ8S74R",
        "title": "Echo Dot (5th Gen, 2022 release) Smart Speaker with Alexa, Charcoal",
        "description": "Our best sounding Echo Dot yet with clearer vocals, deeper bass, and vibrant sound. Voice control your entertainment with Alexa. Pair with a second Echo Dot for stereo sound. Tap the top to snooze an alarm. Designed to protect your privacy with a microphone off button. Made with 99% recycled fabric and 100% recycled aluminum.",
    },
    {
        "product_id": "B09NNLT1JC",
        "title": "Carhartt Men's Loose Fit Heavyweight Short-Sleeve Pocket T-Shirt, Black, X-Large",
        "description": "6.75-ounce, 100% cotton jersey knit. Side-seamed construction minimizes twisting. Tagless neck label. Left-chest pocket with sewn-on Carhartt label. Rib-knit crewneck collar. Relaxed fit through the chest and waist. Machine washable.",
    },
    {
        "product_id": "B0C1H2JQL8",
        "title": "Logitech MX Master 3S Wireless Performance Mouse, Ergo, 8K DPI, Quiet Clicks, USB-C, Bluetooth, Windows, macOS, Linux, Graphite",
        "description": "Flagship performance mouse with 8K DPI any-surface tracking. Quiet clicks with tactile feedback. MagSpeed scroll wheel scrolls 1,000 lines per second. Ergonomic shape for right-hand use. Connect via Bluetooth or USB-C receiver. Flow cross-computer control. USB-C quick charging: 1 minute gives 3 hours of use.",
    },
    {
        "product_id": "B0BT2N328P",
        "title": "COSRX Snail Mucin 96% Power Repairing Essence, Lightweight Hydrating Serum for All Skin Types, Korean Skincare, 3.38 fl.oz / 100ml",
        "description": "Formulated with 96.3% Snail Secretion Filtrate for intense hydration and skin repair. Lightweight, non-greasy texture absorbs quickly. Suitable for all skin types including sensitive and acne-prone. Helps reduce hyperpigmentation, fine lines, and dullness. Dermatologist tested. Cruelty-free.",
    },
    {
        "product_id": "B0BGLN2PC7",
        "title": "Stanley Quencher H2.0 FlowState Tumbler 40 oz, Cream",
        "description": "Double-wall vacuum insulation keeps drinks cold for 11 hours, iced for 2 days, and hot for 7 hours. Made with recycled 18/8 stainless steel. Rotating 3-position lid: straw opening, drink opening, full-cover top. Ergonomic handle with comfort-grip inserts. Fits most car cup holders. Dishwasher safe.",
    },
    {
        "product_id": "B09WB2NF2L",
        "title": "TOZO T6 True Wireless Earbuds Bluetooth 5.3 Headphones, IPX8 Waterproof, Touch Control with Wireless Charging Case, Premium Deep Bass, Built-in Mic, Black",
        "description": "Bluetooth 5.3 for stable connection with lower latency. IPX8 waterproof rating for swimming and heavy rain. Touch controls on both earbuds for music and calls. Wireless charging compatible case provides 30 hours total playtime. 6mm composite driver for rich bass. Built-in microphone with noise isolation for clear calls.",
    },
    {
        "product_id": "B08V1NVMYG",
        "title": "Crocs Unisex-Adult Classic Clogs, Comfortable Slip On Water Shoes, Black, 10 Women/8 Men",
        "description": "Lightweight Iconic Crocs Comfort. Ventilation ports add breathability and help shed water and debris. Easy to clean. Water-friendly and buoyant. Pivoting heel straps for a more secure fit. Croslite foam construction for cushioned comfort. Customizable with Jibbitz charms.",
    },
]

df_products = pd.DataFrame(SAMPLE_PRODUCTS)
logger.info(f"Carregados {len(df_products)} produtos de exemplo")
df_products[["product_id", "title"]].head(15)

# %% [markdown]
# ## 3. Prompt Engineering
#
# Implementacao do sistema de prompts com:
# - **System prompt**: Define o papel e as restricoes do modelo
# - **Few-shot example**: Exemplo concreto de entrada/saida para alinhar o formato
# - **Schema JSON**: Especificacao dos campos esperados na saida
#
# Seguimos o paradigma de **Context Engineering** (2026): tratamos toda a entrada
# do LLM como um pipeline de dados estruturado.

# %%
SYSTEM_PROMPT = """You are an expert e-commerce product cataloging specialist.

Your task is to extract structured product attributes from the product title and description provided.

## Output Schema
Return a JSON object with the following fields:

{
  "category": "string - Main product category in English (e.g., 'Phone Accessories', 'Electronics', 'Clothing', 'Home & Kitchen')",
  "subcategory": "string - More specific subcategory (e.g., 'Phone Cases', 'Headphones', 'T-Shirts')",
  "brand": "string or null - Brand name if identifiable",
  "material": "string or null - Primary material mentioned",
  "target_device": "string or null - Compatible device if applicable",
  "color": "string or null - Primary color mentioned",
  "features": {
    "description": "object with boolean values for detected product features",
    "example_keys": ["has_mirror", "has_wallet", "is_waterproof", "has_bluetooth", "is_wireless", "has_noise_cancellation"]
  },
  "target_audience": "string or null - Target demographic if mentioned (e.g., 'Men', 'Women', 'Unisex')",
  "keywords": ["array of 3-8 relevant keywords extracted from the text"]
}

## Rules
1. Extract ONLY information explicitly stated in the text
2. If a field cannot be determined from the text, use null
3. NEVER fabricate or infer data not present in the text
4. Categories must be in English and standardized
5. Feature keys should be descriptive snake_case booleans
6. Keywords should capture the most important product attributes
7. Return ONLY the JSON object, no markdown formatting"""

# %%
FEW_SHOT_EXAMPLE_USER = """Extract structured features from this product:

Title: "FYY Leather Case with Mirror for Samsung Galaxy S8 Plus, Leather Wallet Flip Folio Case with Mirror and Wrist Strap for Samsung Galaxy S8 Plus, Black"

Description: "Premium PU Leather Top quality. Receiver design for hand-free to answer to phone. Hand strap makes it easy to carry around. RFID Technique: protect your personal information with RFID blocking technology. Multiple card slots and side pocket for cash and receipts.\""""

FEW_SHOT_EXAMPLE_ASSISTANT = """{
  "category": "Phone Accessories",
  "subcategory": "Phone Cases",
  "brand": "FYY",
  "material": "Premium PU Leather",
  "target_device": "Samsung Galaxy S8 Plus",
  "color": "Black",
  "features": {
    "has_mirror": true,
    "has_wallet": true,
    "has_wrist_strap": true,
    "has_rfid_protection": true,
    "is_flip_folio": true,
    "hands_free_receiver": true,
    "has_card_slots": true
  },
  "target_audience": null,
  "keywords": ["leather case", "wallet", "mirror", "flip folio", "wrist strap", "RFID", "Samsung Galaxy S8 Plus"]
}"""

# %% [markdown]
# ## 4. Funcao de Extracao
#
# Implementacao com:
# - Chamadas a API OpenAI (Chat Completions)
# - Few-shot learning via mensagens de conversa
# - `response_format=json_object` para garantia de JSON valido
# - Retry com backoff exponencial para resiliencia
# - Tracking de tokens para controle de custo

# %%
class TokenTracker:
    """Rastreador de uso de tokens e custo estimado."""

    def __init__(self, cost_input_per_1m: float, cost_output_per_1m: float):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.cost_input_per_1m = cost_input_per_1m
        self.cost_output_per_1m = cost_output_per_1m
        self.request_count = 0
        self.error_count = 0

    def add(self, input_tokens: int, output_tokens: int):
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.request_count += 1

    def add_error(self):
        self.error_count += 1

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def estimated_cost_usd(self) -> float:
        input_cost = (self.total_input_tokens / 1_000_000) * self.cost_input_per_1m
        output_cost = (self.total_output_tokens / 1_000_000) * self.cost_output_per_1m
        return input_cost + output_cost

    def summary(self) -> dict:
        return {
            "total_requests": self.request_count,
            "total_errors": self.error_count,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
        }

    def __repr__(self) -> str:
        return (
            f"TokenTracker(requests={self.request_count}, "
            f"tokens={self.total_tokens:,}, "
            f"cost=${self.estimated_cost_usd:.4f})"
        )


tracker = TokenTracker(COST_INPUT_PER_1M, COST_OUTPUT_PER_1M)

# %%
def extract_product_features(
    title: str,
    description: str,
    tracker: TokenTracker,
    max_retries: int = MAX_RETRIES,
) -> Optional[dict]:
    """
    Extrai features estruturadas de um produto usando GPT-4o-mini.

    Utiliza few-shot prompting com o exemplo do FYY Leather Case para
    alinhar o formato de saida. Implementa retry com backoff exponencial
    para resiliencia contra erros transientes da API.

    Args:
        title: Titulo do produto.
        description: Descricao do produto.
        tracker: Instancia de TokenTracker para monitoramento de custo.
        max_retries: Numero maximo de tentativas em caso de erro.

    Returns:
        dict com features extraidas ou None em caso de falha apos retries.
    """
    user_message = f"""Extract structured features from this product:

Title: "{title}"

Description: "{description}\""""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        # Few-shot: exemplo de entrada
        {"role": "user", "content": FEW_SHOT_EXAMPLE_USER},
        # Few-shot: exemplo de saida esperada
        {"role": "assistant", "content": FEW_SHOT_EXAMPLE_ASSISTANT},
        # Produto real a ser processado
        {"role": "user", "content": user_message},
    ]

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                temperature=TEMPERATURE,
                messages=messages,
                response_format={"type": "json_object"},
                timeout=30,
            )

            # Rastrear tokens
            usage = response.usage
            tracker.add(usage.prompt_tokens, usage.completion_tokens)

            # Parsear JSON
            raw_content = response.choices[0].message.content
            features = json.loads(raw_content)

            return features

        except RateLimitError:
            wait_time = RETRY_BACKOFF_BASE ** (attempt + 1)
            logger.warning(
                f"Rate limit atingido. Aguardando {wait_time}s "
                f"(tentativa {attempt + 1}/{max_retries})"
            )
            tracker.add_error()
            time.sleep(wait_time)

        except APITimeoutError:
            wait_time = RETRY_BACKOFF_BASE ** (attempt + 1)
            logger.warning(
                f"Timeout na API. Retry em {wait_time}s "
                f"(tentativa {attempt + 1}/{max_retries})"
            )
            tracker.add_error()
            time.sleep(wait_time)

        except APIError as e:
            logger.error(f"Erro da API OpenAI: {e}")
            tracker.add_error()
            if attempt == max_retries - 1:
                return None
            time.sleep(RETRY_BACKOFF_BASE)

        except json.JSONDecodeError as e:
            logger.error(f"Erro ao parsear JSON da resposta: {e}")
            tracker.add_error()
            if attempt == max_retries - 1:
                return None

        except Exception as e:
            logger.error(f"Erro inesperado: {type(e).__name__}: {e}")
            tracker.add_error()
            return None

    logger.error(f"Falha apos {max_retries} tentativas para: {title[:60]}...")
    return None

# %% [markdown]
# ## 5. Validacao de Schema
#
# Validacao dos resultados extraidos para garantir conformidade com o schema
# esperado. Verifica tipos, campos obrigatorios e consistencia dos dados.

# %%
REQUIRED_FIELDS = {"category", "subcategory", "brand", "material", "color",
                    "target_device", "features", "target_audience", "keywords"}

VALID_CATEGORIES = {
    "Phone Accessories", "Electronics", "Clothing", "Home & Kitchen",
    "Audio", "Smart Home", "Beauty & Personal Care", "Drinkware",
    "Sports & Outdoors", "Computers & Accessories", "Footwear",
    "Health & Household", "Office Products", "Cleaning Supplies",
    "Skincare", "Kitchen & Dining",
}


def validate_extracted_features(features: dict) -> dict:
    """
    Valida as features extraidas contra o schema esperado.

    Retorna um dicionario com:
        - is_valid (bool): se passou em todas as validacoes criticas
        - issues (list[str]): lista de problemas encontrados
        - warnings (list[str]): alertas nao-criticos
    """
    issues = []
    warnings = []

    # Verificar campos obrigatorios
    missing = REQUIRED_FIELDS - set(features.keys())
    if missing:
        issues.append(f"Campos ausentes: {missing}")

    # Verificar tipo de 'features'
    feat = features.get("features")
    if feat is not None and not isinstance(feat, dict):
        issues.append(f"'features' deveria ser dict, recebeu {type(feat).__name__}")
    elif isinstance(feat, dict):
        # Verificar se todos os valores sao booleanos
        non_bool = {k: type(v).__name__ for k, v in feat.items() if not isinstance(v, bool)}
        if non_bool:
            warnings.append(f"Valores nao-booleanos em features: {non_bool}")

    # Verificar tipo de 'keywords'
    kw = features.get("keywords")
    if kw is not None and not isinstance(kw, list):
        issues.append(f"'keywords' deveria ser list, recebeu {type(kw).__name__}")
    elif isinstance(kw, list):
        if len(kw) < 2:
            warnings.append(f"Poucas keywords: {len(kw)} (minimo recomendado: 3)")
        if len(kw) > 10:
            warnings.append(f"Muitas keywords: {len(kw)} (maximo recomendado: 8)")

    # Verificar categoria contra lista conhecida
    cat = features.get("category")
    if cat and cat not in VALID_CATEGORIES:
        warnings.append(f"Categoria '{cat}' nao esta na lista padrao")

    is_valid = len(issues) == 0

    return {
        "is_valid": is_valid,
        "issues": issues,
        "warnings": warnings,
    }

# %%
# Teste rapido da validacao com o exemplo few-shot
test_features = json.loads(FEW_SHOT_EXAMPLE_ASSISTANT)
validation = validate_extracted_features(test_features)
print(f"Valido: {validation['is_valid']}")
print(f"Issues: {validation['issues']}")
print(f"Warnings: {validation['warnings']}")

# %% [markdown]
# ## 6. Processamento em Batch
#
# Processamento de todos os produtos com:
# - Barra de progresso (`tqdm`)
# - Delay entre requests para respeitar rate limits
# - Validacao de cada resultado
# - Coleta de metricas de qualidade

# %%
DELAY_BETWEEN_REQUESTS = 0.5  # segundos (conservador para Tier 1)


def process_products_batch(
    df: pd.DataFrame,
    tracker: TokenTracker,
    delay: float = DELAY_BETWEEN_REQUESTS,
) -> pd.DataFrame:
    """
    Processa um DataFrame de produtos, extraindo features via LLM.

    Para cada produto, chama a API OpenAI, valida o resultado e
    armazena as features extraidas junto com metricas de qualidade.

    Args:
        df: DataFrame com colunas 'product_id', 'title', 'description'.
        tracker: Instancia de TokenTracker.
        delay: Tempo de espera entre requests (segundos).

    Returns:
        DataFrame com os resultados da extracao.
    """
    results = []

    for _, row in tqdm(df.iterrows(), total=len(df), desc="Extraindo features"):
        product_id = row["product_id"]
        title = row["title"]
        description = row["description"]

        # Extrair features
        features = extract_product_features(title, description, tracker)

        if features is None:
            results.append({
                "product_id": product_id,
                "title": title,
                "extraction_status": "FAILED",
                "is_valid": False,
                "raw_features": None,
            })
            continue

        # Validar
        validation = validate_extracted_features(features)

        # Montar resultado
        result = {
            "product_id": product_id,
            "title": title,
            "extraction_status": "SUCCESS",
            "is_valid": validation["is_valid"],
            "validation_issues": "; ".join(validation["issues"]) if validation["issues"] else None,
            "validation_warnings": "; ".join(validation["warnings"]) if validation["warnings"] else None,
            "llm_category": features.get("category"),
            "llm_subcategory": features.get("subcategory"),
            "llm_brand": features.get("brand"),
            "llm_material": features.get("material"),
            "llm_target_device": features.get("target_device"),
            "llm_color": features.get("color"),
            "llm_target_audience": features.get("target_audience"),
            "llm_feature_count": len(features.get("features", {})),
            "llm_features_json": json.dumps(features.get("features", {})),
            "llm_keywords": ", ".join(features.get("keywords", [])),
            "llm_keywords_count": len(features.get("keywords", [])),
            "raw_features": json.dumps(features),
        }

        results.append(result)

        # Rate limiting
        time.sleep(delay)

    return pd.DataFrame(results)


# Executar processamento
logger.info("Iniciando extracao de features...")
df_results = process_products_batch(df_products, tracker)
logger.info(f"Processamento concluido. {tracker}")

# %% [markdown]
# ## 7. Analise dos Resultados
#
# Visualizacao e analise dos atributos extraidos.

# %%
# Resumo geral
print("=" * 70)
print("RESUMO DA EXTRACAO")
print("=" * 70)
print(f"Total de produtos processados: {len(df_results)}")
print(f"Extracoes bem-sucedidas:       {(df_results['extraction_status'] == 'SUCCESS').sum()}")
print(f"Extracoes com falha:           {(df_results['extraction_status'] == 'FAILED').sum()}")
print(f"Validacoes aprovadas:          {df_results['is_valid'].sum()}")
print(f"Taxa de sucesso:               {(df_results['extraction_status'] == 'SUCCESS').mean():.1%}")
print(f"Taxa de validacao:             {df_results['is_valid'].mean():.1%}")
print("=" * 70)

# %%
# Tabela resumo das features extraidas
summary_cols = [
    "product_id", "llm_category", "llm_subcategory", "llm_brand",
    "llm_material", "llm_color", "llm_feature_count", "llm_keywords_count",
]
df_summary = df_results[df_results["extraction_status"] == "SUCCESS"][summary_cols].copy()
df_summary.columns = [
    "Product ID", "Category", "Subcategory", "Brand",
    "Material", "Color", "Num Features", "Num Keywords",
]
print("\nResumo das Features Extraidas:")
print(df_summary.to_string(index=False))

# %%
# Detalhe: titulo + categoria + features principais
print("\n" + "=" * 70)
print("DETALHE POR PRODUTO")
print("=" * 70)
for _, row in df_results[df_results["extraction_status"] == "SUCCESS"].iterrows():
    title_short = row["title"][:65] + "..." if len(row["title"]) > 65 else row["title"]
    print(f"\n  {row['product_id']} | {title_short}")
    print(f"  Categoria: {row['llm_category']} > {row['llm_subcategory']}")
    print(f"  Marca: {row['llm_brand']} | Material: {row['llm_material']} | Cor: {row['llm_color']}")
    print(f"  Features ({row['llm_feature_count']}): {row['llm_features_json'][:80]}...")
    print(f"  Keywords: {row['llm_keywords'][:80]}...")

# %% [markdown]
# ## 8. Visualizacoes
#
# Graficos para analise da distribuicao de features extraidas.

# %%
# Configuracao visual
sns.set_theme(style="whitegrid", font_scale=1.1)
PALETTE = sns.color_palette("viridis", n_colors=10)

fig, axes = plt.subplots(2, 2, figsize=(16, 12))
fig.suptitle(
    "Analise de Features Extraidas por LLM (GPT-4o-mini)",
    fontsize=16,
    fontweight="bold",
    y=1.02,
)

df_valid = df_results[df_results["extraction_status"] == "SUCCESS"].copy()

# --- Grafico 1: Distribuicao de Categorias ---
ax1 = axes[0, 0]
if not df_valid.empty and "llm_category" in df_valid.columns:
    cat_counts = df_valid["llm_category"].value_counts()
    bars = ax1.barh(cat_counts.index, cat_counts.values, color=PALETTE)
    ax1.set_xlabel("Numero de Produtos")
    ax1.set_title("Distribuicao de Categorias")
    ax1.invert_yaxis()
    for bar, val in zip(bars, cat_counts.values):
        ax1.text(val + 0.1, bar.get_y() + bar.get_height() / 2,
                 str(val), va="center", fontweight="bold")

# --- Grafico 2: Numero de Features por Produto ---
ax2 = axes[0, 1]
if not df_valid.empty and "llm_feature_count" in df_valid.columns:
    feature_counts = df_valid["llm_feature_count"].sort_values(ascending=True)
    labels = [pid[:12] for pid in df_valid.loc[feature_counts.index, "product_id"]]
    bars = ax2.barh(labels, feature_counts.values, color=PALETTE[:len(labels)])
    ax2.set_xlabel("Numero de Features Booleanas")
    ax2.set_title("Features Extraidas por Produto")
    for bar, val in zip(bars, feature_counts.values):
        ax2.text(val + 0.1, bar.get_y() + bar.get_height() / 2,
                 str(val), va="center", fontweight="bold")

# --- Grafico 3: Distribuicao de Keywords por Produto ---
ax3 = axes[1, 0]
if not df_valid.empty and "llm_keywords_count" in df_valid.columns:
    kw_counts = df_valid["llm_keywords_count"]
    ax3.hist(kw_counts, bins=range(1, kw_counts.max() + 2), color=PALETTE[3],
             edgecolor="white", alpha=0.85)
    ax3.set_xlabel("Numero de Keywords")
    ax3.set_ylabel("Numero de Produtos")
    ax3.set_title("Distribuicao de Keywords Extraidas")
    ax3.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax3.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))

# --- Grafico 4: Preenchimento de Campos (completude) ---
ax4 = axes[1, 1]
field_cols = [
    "llm_category", "llm_subcategory", "llm_brand", "llm_material",
    "llm_color", "llm_target_device", "llm_target_audience",
]
if not df_valid.empty:
    fill_rates = []
    field_labels = []
    for col in field_cols:
        if col in df_valid.columns:
            rate = df_valid[col].notna().mean() * 100
            # Contar strings vazias como nao-preenchidas
            non_empty = df_valid[col].apply(lambda x: x is not None and str(x).strip() != "" and str(x).lower() != "none")
            rate = non_empty.mean() * 100
            fill_rates.append(rate)
            field_labels.append(col.replace("llm_", "").replace("_", " ").title())

    bars = ax4.barh(field_labels, fill_rates, color=PALETTE[5])
    ax4.set_xlabel("Taxa de Preenchimento (%)")
    ax4.set_title("Completude dos Campos Extraidos")
    ax4.set_xlim(0, 110)
    ax4.invert_yaxis()
    for bar, val in zip(bars, fill_rates):
        ax4.text(val + 1, bar.get_y() + bar.get_height() / 2,
                 f"{val:.0f}%", va="center", fontweight="bold")

plt.tight_layout()
plt.savefig("feature_extraction_analysis.png", dpi=150, bbox_inches="tight")
plt.show()
print("Grafico salvo em: feature_extraction_analysis.png")

# %% [markdown]
# ## 9. Rastreamento de Custo
#
# Monitoramento detalhado do uso de tokens e custo estimado da extracao.

# %%
cost_summary = tracker.summary()

print("=" * 70)
print("RASTREAMENTO DE CUSTO - OpenAI API")
print("=" * 70)
print(f"  Modelo:                {MODEL_NAME}")
print(f"  Total de requests:     {cost_summary['total_requests']}")
print(f"  Total de erros:        {cost_summary['total_errors']}")
print(f"  Tokens de input:       {cost_summary['total_input_tokens']:,}")
print(f"  Tokens de output:      {cost_summary['total_output_tokens']:,}")
print(f"  Total de tokens:       {cost_summary['total_tokens']:,}")
print(f"  Custo estimado:        ${cost_summary['estimated_cost_usd']:.6f}")
print("=" * 70)

# Projecao para escala real
products_processed = cost_summary["total_requests"]
if products_processed > 0:
    cost_per_product = cost_summary["estimated_cost_usd"] / products_processed
    tokens_per_product = cost_summary["total_tokens"] / products_processed

    print("\nPROJECAO DE CUSTO:")
    print(f"  Custo por produto:     ${cost_per_product:.6f}")
    print(f"  Tokens por produto:    {tokens_per_product:.0f}")
    print(f"  ---")
    for scale in [100, 1_000, 10_000, 100_000]:
        projected_cost = cost_per_product * scale
        projected_tokens = tokens_per_product * scale
        print(
            f"  {scale:>7,} produtos:     "
            f"${projected_cost:>8.2f}  "
            f"({projected_tokens:>12,.0f} tokens)"
        )

# %% [markdown]
# ## 10. Exportacao dos Resultados
#
# Salvamento dos resultados em CSV (para analise tabular) e JSON
# (para integracao com pipelines downstream e carga no star schema).

# %%
# Preparar DataFrame final para exportacao
export_cols = [
    "product_id", "title", "extraction_status", "is_valid",
    "llm_category", "llm_subcategory", "llm_brand", "llm_material",
    "llm_target_device", "llm_color", "llm_target_audience",
    "llm_feature_count", "llm_features_json", "llm_keywords",
]

df_export = df_results[
    [c for c in export_cols if c in df_results.columns]
].copy()

# Adicionar metadados da extracao
df_export["llm_model"] = MODEL_NAME
df_export["llm_extraction_date"] = pd.Timestamp.now().isoformat()

# Salvar CSV
csv_path = "extracted_features.csv"
df_export.to_csv(csv_path, index=False, encoding="utf-8")
logger.info(f"Resultados salvos em CSV: {csv_path}")

# Salvar JSON (formato lista de objetos, ideal para APIs e pipelines)
json_path = "extracted_features.json"
records = df_export.to_dict(orient="records")

# Converter features JSON string de volta para dict no export JSON
for record in records:
    if record.get("llm_features_json"):
        try:
            record["llm_features"] = json.loads(record["llm_features_json"])
        except (json.JSONDecodeError, TypeError):
            record["llm_features"] = {}
        del record["llm_features_json"]

with open(json_path, "w", encoding="utf-8") as f:
    json.dump(records, f, indent=2, ensure_ascii=False)
logger.info(f"Resultados salvos em JSON: {json_path}")

# Salvar resumo de custo
cost_path = "extraction_cost_report.json"
cost_report = {
    "model": MODEL_NAME,
    "timestamp": pd.Timestamp.now().isoformat(),
    "products_processed": len(df_results),
    "success_rate": float((df_results["extraction_status"] == "SUCCESS").mean()),
    "validation_rate": float(df_results["is_valid"].mean()),
    **cost_summary,
}
with open(cost_path, "w", encoding="utf-8") as f:
    json.dump(cost_report, f, indent=2)
logger.info(f"Relatorio de custo salvo em: {cost_path}")

print(f"\nArquivos exportados:")
print(f"  - {csv_path}")
print(f"  - {json_path}")
print(f"  - {cost_path}")

# %% [markdown]
# ## 11. Exemplo de Resultado Completo
#
# Visualizacao do JSON completo extraido para um produto, demonstrando
# a riqueza dos atributos estruturados obtidos a partir de texto livre.

# %%
# Exibir resultado completo do primeiro produto bem-sucedido
success_rows = df_results[df_results["extraction_status"] == "SUCCESS"]
if not success_rows.empty:
    first = success_rows.iloc[0]
    print(f"Produto: {first['title'][:80]}...")
    print(f"ID: {first['product_id']}")
    print(f"\nFeatures extraidas:")
    try:
        features_pretty = json.loads(first["raw_features"])
        print(json.dumps(features_pretty, indent=2, ensure_ascii=False))
    except (json.JSONDecodeError, TypeError):
        print(first["raw_features"])

# %% [markdown]
# ## 12. Integracao com Star Schema
#
# As features extraidas alimentam a dimensao `dim_product` do star schema.
# O prefixo `llm_` identifica colunas geradas por IA, garantindo
# rastreabilidade e governanca de dados.
#
# ```sql
# -- Exemplo de query analitica habilitada pelas features LLM
# SELECT
#     dp.llm_category,
#     dp.llm_material,
#     COUNT(DISTINCT fr.review_id) as total_reviews,
#     AVG(fr.overall_rating) as avg_rating
# FROM fact_review fr
# JOIN dim_product dp ON fr.product_sk = dp.product_sk
# WHERE dp.llm_category IS NOT NULL
# GROUP BY dp.llm_category, dp.llm_material
# ORDER BY total_reviews DESC;
# ```
#
# ### Proximos Passos
#
# 1. **Escalar** para o dataset completo via OpenAI Batch API (50% desconto)
# 2. **Cachear** resultados para evitar re-processamento
# 3. **Monitorar** drift de qualidade ao longo do tempo
# 4. **Avaliar** fine-tuning para o dominio especifico de e-commerce
