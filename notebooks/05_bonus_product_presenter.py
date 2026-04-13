# %% [markdown]
# # Bonus: GenAI Product Presenter
#
# > **Caso Tecnico:** Dadosfera Data Platform
# > **Notebook:** 05 — GenAI Data App: Apresentacao Automatica de Produtos
# > **Data:** Abril de 2026
# > **Versao:** 1.0
#
# ---
#
# ## Objetivo
#
# Este notebook demonstra como a Dadosfera pode potencializar a equipe de marketing
# de um e-commerce com **Inteligencia Artificial Generativa**. O pipeline:
#
# 1. Recebe titulo e descricao de um produto
# 2. Gera copy de marketing em 3 tons (formal, casual, urgente)
# 3. Extrai pontos-chave de venda, publico-alvo e keywords SEO
# 4. Gera uma imagem do produto via DALL-E 3
# 5. Monta um cartao de apresentacao em HTML
#
# **Integracao com Dadosfera:** Na plataforma, este notebook rodaria no modulo
# **Inteligencia**, com acesso direto aos dados do catalogo de produtos via
# Snowflake Backend e deploy como **Streamlit Data App**.

# %% [markdown]
# ## 1. Setup e Dependencias

# %%
# !pip install openai python-dotenv requests Pillow tqdm --quiet

# %%
import os
import json
import time
import base64
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("product_presenter")

# %% [markdown]
# ## 2. Configuracao da API OpenAI

# %%
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise EnvironmentError(
        "OPENAI_API_KEY nao encontrada. "
        "Configure no .env ou como variavel de ambiente."
    )

OPENAI_BASE_URL = "https://api.openai.com/v1"

HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json",
}

# Modelos utilizados
TEXT_MODEL = "gpt-4o-mini"
IMAGE_MODEL = "dall-e-3"

# Controle de custos
COST_PER_1K_INPUT_TOKENS = 0.00015   # gpt-4o-mini input
COST_PER_1K_OUTPUT_TOKENS = 0.0006   # gpt-4o-mini output
COST_PER_IMAGE = 0.040               # DALL-E 3 standard 1024x1024

# %% [markdown]
# ## 3. Estruturas de Dados

# %%
@dataclass
class CostTracker:
    """Rastreia custos acumulados de chamadas a API."""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_images: int = 0
    api_calls: int = 0

    @property
    def text_cost(self) -> float:
        return (
            (self.total_input_tokens / 1000) * COST_PER_1K_INPUT_TOKENS
            + (self.total_output_tokens / 1000) * COST_PER_1K_OUTPUT_TOKENS
        )

    @property
    def image_cost(self) -> float:
        return self.total_images * COST_PER_IMAGE

    @property
    def total_cost(self) -> float:
        return self.text_cost + self.image_cost

    def log_text_call(self, input_tokens: int, output_tokens: int) -> None:
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.api_calls += 1

    def log_image_call(self) -> None:
        self.total_images += 1
        self.api_calls += 1

    def summary(self) -> str:
        return (
            f"API Calls: {self.api_calls} | "
            f"Input Tokens: {self.total_input_tokens:,} | "
            f"Output Tokens: {self.total_output_tokens:,} | "
            f"Images: {self.total_images} | "
            f"Text Cost: ${self.text_cost:.4f} | "
            f"Image Cost: ${self.image_cost:.4f} | "
            f"TOTAL: ${self.total_cost:.4f}"
        )


@dataclass
class MarketingCopy:
    """Copy de marketing gerada para um produto."""
    formal: str = ""
    casual: str = ""
    urgent: str = ""


@dataclass
class ProductPresentation:
    """Apresentacao completa de um produto."""
    title: str = ""
    description: str = ""
    marketing_copy: MarketingCopy = field(default_factory=MarketingCopy)
    selling_points: list[str] = field(default_factory=list)
    target_audience: str = ""
    seo_keywords: list[str] = field(default_factory=list)
    image_url: Optional[str] = None
    image_base64: Optional[str] = None
    generated_at: str = ""
    generation_time_seconds: float = 0.0


cost_tracker = CostTracker()

# %% [markdown]
# ## 4. Funcoes de Chamada a API
#
# Todas as chamadas utilizam a API REST diretamente com `requests`,
# sem dependencia do SDK da OpenAI. Isso garante compatibilidade
# maxima com ambientes restritivos como o Dadosfera.

# %%
def chat_completion(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    retries: int = 3,
    backoff_base: float = 2.0,
) -> str:
    """
    Chama a API de chat completions da OpenAI com retry e backoff exponencial.

    Args:
        system_prompt: Instrucao de sistema para o modelo.
        user_prompt: Mensagem do usuario.
        temperature: Criatividade (0.0 = deterministico, 1.0 = criativo).
        max_tokens: Limite de tokens na resposta.
        retries: Numero de tentativas em caso de falha.
        backoff_base: Base para backoff exponencial (segundos).

    Returns:
        Texto da resposta do modelo.

    Raises:
        RuntimeError: Se todas as tentativas falharem.
    """
    payload = {
        "model": TEXT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    last_error = None
    for attempt in range(retries):
        try:
            response = requests.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                headers=HEADERS,
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

            usage = data.get("usage", {})
            cost_tracker.log_text_call(
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
            )

            return data["choices"][0]["message"]["content"]

        except requests.exceptions.HTTPError as e:
            last_error = e
            status = e.response.status_code if e.response else 0
            if status == 429:
                wait = backoff_base ** (attempt + 1)
                logger.warning(
                    f"Rate limit atingido. Aguardando {wait:.0f}s "
                    f"(tentativa {attempt + 1}/{retries})"
                )
                time.sleep(wait)
            elif status >= 500:
                wait = backoff_base ** attempt
                logger.warning(
                    f"Erro do servidor ({status}). Aguardando {wait:.0f}s "
                    f"(tentativa {attempt + 1}/{retries})"
                )
                time.sleep(wait)
            else:
                logger.error(f"Erro HTTP {status}: {e}")
                raise
        except requests.exceptions.RequestException as e:
            last_error = e
            wait = backoff_base ** attempt
            logger.warning(
                f"Erro de conexao: {e}. Aguardando {wait:.0f}s "
                f"(tentativa {attempt + 1}/{retries})"
            )
            time.sleep(wait)

    raise RuntimeError(
        f"Todas as {retries} tentativas falharam. Ultimo erro: {last_error}"
    )


def generate_image(
    prompt: str,
    size: str = "1024x1024",
    quality: str = "standard",
    retries: int = 3,
    backoff_base: float = 2.0,
) -> str:
    """
    Gera uma imagem via DALL-E 3 e retorna a URL.

    Args:
        prompt: Descricao da imagem a ser gerada.
        size: Dimensao da imagem.
        quality: Qualidade (standard ou hd).
        retries: Numero de tentativas.
        backoff_base: Base para backoff exponencial.

    Returns:
        URL da imagem gerada.

    Raises:
        RuntimeError: Se todas as tentativas falharem.
    """
    payload = {
        "model": IMAGE_MODEL,
        "prompt": prompt,
        "n": 1,
        "size": size,
        "quality": quality,
    }

    last_error = None
    for attempt in range(retries):
        try:
            response = requests.post(
                f"{OPENAI_BASE_URL}/images/generations",
                headers=HEADERS,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            cost_tracker.log_image_call()

            return data["data"][0]["url"]

        except requests.exceptions.HTTPError as e:
            last_error = e
            status = e.response.status_code if e.response else 0
            if status in (429, 500, 502, 503):
                wait = backoff_base ** (attempt + 1)
                logger.warning(
                    f"Erro {status} na geracao de imagem. Aguardando {wait:.0f}s "
                    f"(tentativa {attempt + 1}/{retries})"
                )
                time.sleep(wait)
            else:
                logger.error(f"Erro HTTP {status}: {e}")
                raise
        except requests.exceptions.RequestException as e:
            last_error = e
            wait = backoff_base ** attempt
            logger.warning(
                f"Erro de conexao: {e}. Aguardando {wait:.0f}s "
                f"(tentativa {attempt + 1}/{retries})"
            )
            time.sleep(wait)

    raise RuntimeError(
        f"Falha ao gerar imagem apos {retries} tentativas. Ultimo erro: {last_error}"
    )


def download_image_as_base64(url: str) -> Optional[str]:
    """Faz download de uma imagem e converte para base64."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return base64.b64encode(response.content).decode("utf-8")
    except Exception as e:
        logger.warning(f"Falha ao baixar imagem: {e}")
        return None

# %% [markdown]
# ## 5. Pipeline de Geracao de Conteudo
#
# O pipeline executa tres etapas sequenciais:
# 1. **Geracao de marketing copy** — tres variacoes de tom
# 2. **Extracao de metadados** — selling points, publico-alvo, SEO
# 3. **Geracao de imagem** — visual do produto via DALL-E 3

# %%
MARKETING_COPY_SYSTEM_PROMPT = """Voce e um copywriter profissional de e-commerce brasileiro.
Seu trabalho e criar textos de marketing persuasivos para produtos.

REGRAS:
- Escreva em portugues brasileiro
- Cada variacao deve ter entre 2 e 4 frases
- Adapte o tom conforme solicitado
- Nao invente especificacoes tecnicas que nao estejam na descricao
- Foque em beneficios, nao apenas features

Responda EXCLUSIVAMENTE em JSON valido, sem markdown, sem code fences:
{
    "formal": "texto formal aqui",
    "casual": "texto casual aqui",
    "urgent": "texto urgente aqui"
}"""

METADATA_SYSTEM_PROMPT = """Voce e um especialista em marketing digital e SEO para e-commerce brasileiro.
Analise o produto e extraia informacoes estruturadas.

REGRAS:
- Escreva em portugues brasileiro
- Selling points: exatamente 5 bullet points concisos
- Target audience: descricao em 2-3 frases
- SEO keywords: 8-12 palavras-chave relevantes em portugues

Responda EXCLUSIVAMENTE em JSON valido, sem markdown, sem code fences:
{
    "selling_points": ["ponto 1", "ponto 2", "ponto 3", "ponto 4", "ponto 5"],
    "target_audience": "descricao do publico-alvo",
    "seo_keywords": ["keyword1", "keyword2", "..."]
}"""

IMAGE_PROMPT_TEMPLATE = (
    "Professional product photography of {title}. "
    "{description}. "
    "Clean white background, studio lighting, high resolution, "
    "e-commerce product listing style, no text overlay."
)


def generate_marketing_copy(title: str, description: str) -> MarketingCopy:
    """Gera copy de marketing em tres tons diferentes."""
    logger.info("Gerando copy de marketing...")

    user_prompt = (
        f"Produto: {title}\n"
        f"Descricao: {description}\n\n"
        "Crie tres variacoes de copy de marketing:\n"
        "1. FORMAL - tom profissional e sofisticado\n"
        "2. CASUAL - tom amigavel e descontraido\n"
        "3. URGENTE - tom de urgencia e escassez"
    )

    response_text = chat_completion(
        system_prompt=MARKETING_COPY_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.8,
    )

    try:
        data = json.loads(response_text)
        return MarketingCopy(
            formal=data.get("formal", ""),
            casual=data.get("casual", ""),
            urgent=data.get("urgent", ""),
        )
    except json.JSONDecodeError:
        logger.warning("Resposta nao e JSON valido. Tentando extrair manualmente.")
        return MarketingCopy(formal=response_text, casual="", urgent="")


def extract_metadata(title: str, description: str) -> dict:
    """Extrai selling points, publico-alvo e keywords SEO."""
    logger.info("Extraindo metadados do produto...")

    user_prompt = (
        f"Produto: {title}\n"
        f"Descricao: {description}\n\n"
        "Analise este produto e extraia os metadados solicitados."
    )

    response_text = chat_completion(
        system_prompt=METADATA_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.5,
    )

    try:
        data = json.loads(response_text)
        return {
            "selling_points": data.get("selling_points", []),
            "target_audience": data.get("target_audience", ""),
            "seo_keywords": data.get("seo_keywords", []),
        }
    except json.JSONDecodeError:
        logger.warning("Resposta de metadados nao e JSON valido.")
        return {
            "selling_points": [],
            "target_audience": response_text,
            "seo_keywords": [],
        }


def generate_product_image(title: str, description: str) -> tuple[Optional[str], Optional[str]]:
    """Gera imagem do produto via DALL-E 3. Retorna (url, base64)."""
    logger.info("Gerando imagem do produto via DALL-E 3...")

    prompt = IMAGE_PROMPT_TEMPLATE.format(
        title=title,
        description=description[:500],
    )

    try:
        image_url = generate_image(prompt)
        image_b64 = download_image_as_base64(image_url)
        return image_url, image_b64
    except Exception as e:
        logger.error(f"Falha na geracao de imagem: {e}")
        return None, None

# %% [markdown]
# ## 6. Pipeline Completo

# %%
def create_product_presentation(
    title: str,
    description: str,
    generate_image_flag: bool = True,
) -> ProductPresentation:
    """
    Pipeline completo de geracao de apresentacao de produto.

    Args:
        title: Titulo do produto.
        description: Descricao detalhada do produto.
        generate_image_flag: Se True, gera imagem via DALL-E 3.

    Returns:
        ProductPresentation com todos os campos preenchidos.
    """
    start_time = time.time()

    presentation = ProductPresentation(
        title=title,
        description=description,
        generated_at=datetime.now().isoformat(),
    )

    # Etapa 1: Marketing copy
    presentation.marketing_copy = generate_marketing_copy(title, description)

    # Etapa 2: Metadados
    metadata = extract_metadata(title, description)
    presentation.selling_points = metadata["selling_points"]
    presentation.target_audience = metadata["target_audience"]
    presentation.seo_keywords = metadata["seo_keywords"]

    # Etapa 3: Imagem (opcional)
    if generate_image_flag:
        image_url, image_b64 = generate_product_image(title, description)
        presentation.image_url = image_url
        presentation.image_base64 = image_b64

    presentation.generation_time_seconds = round(time.time() - start_time, 2)

    logger.info(
        f"Apresentacao gerada em {presentation.generation_time_seconds}s | "
        f"{cost_tracker.summary()}"
    )

    return presentation

# %% [markdown]
# ## 7. Geracao do HTML de Apresentacao

# %%
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} — Product Presentation</title>
    <style>
        :root {{
            --primary: #1a1a2e;
            --secondary: #16213e;
            --accent: #0f3460;
            --highlight: #e94560;
            --bg: #f8f9fa;
            --card-bg: #ffffff;
            --text: #2d3436;
            --text-light: #636e72;
            --border: #dfe6e9;
            --success: #00b894;
            --warning: #fdcb6e;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
        }}

        .container {{
            max-width: 1000px;
            margin: 0 auto;
            padding: 2rem;
        }}

        .header {{
            background: linear-gradient(135deg, var(--primary), var(--accent));
            color: white;
            padding: 3rem 2rem;
            border-radius: 16px;
            margin-bottom: 2rem;
            text-align: center;
        }}

        .header h1 {{
            font-size: 2.2rem;
            margin-bottom: 0.5rem;
            font-weight: 700;
        }}

        .header p {{
            opacity: 0.85;
            font-size: 1.1rem;
            max-width: 700px;
            margin: 0 auto;
        }}

        .badge {{
            display: inline-block;
            background: var(--highlight);
            color: white;
            padding: 0.25rem 0.75rem;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
            margin-top: 1rem;
        }}

        .grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}

        .card {{
            background: var(--card-bg);
            border-radius: 12px;
            padding: 1.5rem;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
            border: 1px solid var(--border);
        }}

        .card-full {{
            grid-column: 1 / -1;
        }}

        .card h2 {{
            font-size: 1.1rem;
            color: var(--accent);
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 2px solid var(--border);
        }}

        .card h3 {{
            font-size: 0.95rem;
            color: var(--text-light);
            margin-bottom: 0.5rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .copy-block {{
            background: var(--bg);
            padding: 1rem;
            border-radius: 8px;
            margin-bottom: 1rem;
            border-left: 3px solid var(--accent);
        }}

        .copy-block.formal {{ border-left-color: var(--accent); }}
        .copy-block.casual {{ border-left-color: var(--success); }}
        .copy-block.urgent {{ border-left-color: var(--highlight); }}

        .copy-block p {{
            font-size: 0.95rem;
            color: var(--text);
        }}

        .selling-points {{
            list-style: none;
            padding: 0;
        }}

        .selling-points li {{
            padding: 0.6rem 0;
            border-bottom: 1px solid var(--border);
            font-size: 0.95rem;
        }}

        .selling-points li:last-child {{
            border-bottom: none;
        }}

        .selling-points li::before {{
            content: "\\2713";
            color: var(--success);
            font-weight: bold;
            margin-right: 0.75rem;
        }}

        .keywords {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
        }}

        .keyword {{
            background: var(--bg);
            color: var(--accent);
            padding: 0.3rem 0.8rem;
            border-radius: 20px;
            font-size: 0.85rem;
            border: 1px solid var(--border);
        }}

        .product-image {{
            width: 100%;
            border-radius: 12px;
            margin-top: 1rem;
        }}

        .audience-text {{
            font-size: 0.95rem;
            color: var(--text);
            line-height: 1.8;
        }}

        .footer {{
            text-align: center;
            padding: 2rem;
            color: var(--text-light);
            font-size: 0.85rem;
        }}

        .stats {{
            display: flex;
            justify-content: center;
            gap: 2rem;
            margin-top: 1rem;
        }}

        .stat {{
            text-align: center;
        }}

        .stat-value {{
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--accent);
        }}

        .stat-label {{
            font-size: 0.8rem;
            color: var(--text-light);
        }}

        @media (max-width: 768px) {{
            .grid {{
                grid-template-columns: 1fr;
            }}
            .header h1 {{
                font-size: 1.6rem;
            }}
            .stats {{
                flex-direction: column;
                gap: 1rem;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <p>{description}</p>
            <span class="badge">GenAI Product Presentation</span>
            <div class="stats">
                <div class="stat">
                    <div class="stat-value">{n_selling_points}</div>
                    <div class="stat-label">Selling Points</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{n_keywords}</div>
                    <div class="stat-label">SEO Keywords</div>
                </div>
                <div class="stat">
                    <div class="stat-value">3</div>
                    <div class="stat-label">Copy Variations</div>
                </div>
            </div>
        </div>

        {image_section}

        <div class="grid">
            <div class="card card-full">
                <h2>Marketing Copy</h2>

                <h3>Tom Formal</h3>
                <div class="copy-block formal">
                    <p>{copy_formal}</p>
                </div>

                <h3>Tom Casual</h3>
                <div class="copy-block casual">
                    <p>{copy_casual}</p>
                </div>

                <h3>Tom Urgente</h3>
                <div class="copy-block urgent">
                    <p>{copy_urgent}</p>
                </div>
            </div>

            <div class="card">
                <h2>Pontos de Venda</h2>
                <ul class="selling-points">
                    {selling_points_html}
                </ul>
            </div>

            <div class="card">
                <h2>Publico-Alvo</h2>
                <p class="audience-text">{target_audience}</p>

                <h2 style="margin-top: 1.5rem;">Keywords SEO</h2>
                <div class="keywords">
                    {keywords_html}
                </div>
            </div>
        </div>

        <div class="footer">
            <p>Gerado automaticamente via GenAI Product Presenter</p>
            <p>Modelo: {text_model} + {image_model} | Gerado em: {generated_at}</p>
            <p>Tempo de geracao: {generation_time}s | Custo estimado: ${cost:.4f}</p>
        </div>
    </div>
</body>
</html>"""


def render_presentation_html(
    presentation: ProductPresentation,
    cost: float = 0.0,
) -> str:
    """Renderiza a apresentacao como pagina HTML completa."""

    # Selling points como lista HTML
    selling_points_html = "\n".join(
        f"                    <li>{point}</li>"
        for point in presentation.selling_points
    )

    # Keywords como badges
    keywords_html = "\n".join(
        f'                    <span class="keyword">{kw}</span>'
        for kw in presentation.seo_keywords
    )

    # Imagem do produto (base64 inline ou URL)
    if presentation.image_base64:
        image_section = (
            '<div class="card card-full" style="text-align: center;">\n'
            '    <h2>Imagem do Produto (DALL-E 3)</h2>\n'
            f'    <img src="data:image/png;base64,{presentation.image_base64}" '
            f'class="product-image" alt="{presentation.title}">\n'
            "</div>"
        )
    elif presentation.image_url:
        image_section = (
            '<div class="card card-full" style="text-align: center;">\n'
            '    <h2>Imagem do Produto (DALL-E 3)</h2>\n'
            f'    <img src="{presentation.image_url}" '
            f'class="product-image" alt="{presentation.title}">\n'
            "</div>"
        )
    else:
        image_section = ""

    return HTML_TEMPLATE.format(
        title=presentation.title,
        description=presentation.description,
        n_selling_points=len(presentation.selling_points),
        n_keywords=len(presentation.seo_keywords),
        copy_formal=presentation.marketing_copy.formal,
        copy_casual=presentation.marketing_copy.casual,
        copy_urgent=presentation.marketing_copy.urgent,
        selling_points_html=selling_points_html,
        target_audience=presentation.target_audience,
        keywords_html=keywords_html,
        image_section=image_section,
        text_model=TEXT_MODEL,
        image_model=IMAGE_MODEL,
        generated_at=presentation.generated_at,
        generation_time=presentation.generation_time_seconds,
        cost=cost,
    )


def save_presentation(
    presentation: ProductPresentation,
    output_dir: str = "output/presentations",
) -> str:
    """
    Salva a apresentacao como arquivo HTML.

    Returns:
        Caminho do arquivo salvo.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    slug = (
        presentation.title.lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
    )
    slug = "".join(c for c in slug if c.isalnum() or c == "_")[:50]
    filename = f"{slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    filepath = output_path / filename

    html = render_presentation_html(presentation, cost=cost_tracker.total_cost)
    filepath.write_text(html, encoding="utf-8")

    logger.info(f"Apresentacao salva em: {filepath}")
    return str(filepath)

# %% [markdown]
# ## 8. Produtos de Demonstracao
#
# Cinco produtos de exemplo que cobrem diferentes categorias
# do e-commerce para demonstrar a versatilidade do pipeline.

# %%
SAMPLE_PRODUCTS = [
    {
        "title": "Fone de Ouvido Bluetooth Premium ANC",
        "description": (
            "Fone de ouvido over-ear com cancelamento ativo de ruido (ANC), "
            "driver de 40mm, bateria de 30 horas, Bluetooth 5.3, microfone "
            "embutido para chamadas, dobravel, estojo de transporte incluso. "
            "Almofadas em espuma memory foam com couro proteico."
        ),
    },
    {
        "title": "Cafeteira Expresso Automatica Italiana",
        "description": (
            "Cafeteira automatica com moedor integrado de ceramica, "
            "pressao de 15 bar, reservatorio de 1.8L, sistema de leite "
            "com vaporizador, painel touch LED, 5 niveis de intensidade, "
            "bandeja de gotejamento removivel, receitas pre-programadas "
            "para espresso, cappuccino, latte e americano."
        ),
    },
    {
        "title": "Mochila Urban Tech Antifurto 25L",
        "description": (
            "Mochila urbana com compartimento acolchoado para notebook ate 15.6 polegadas, "
            "tecido impermeavel 600D, ziper oculto antifurto, porta USB lateral, "
            "alca de trolley, divisorias internas organizadoras, bolso RFID-blocking, "
            "tiras refletivas para visibilidade noturna, peso 0.9kg."
        ),
    },
    {
        "title": "Kit Skincare Vitamina C Anti-Idade",
        "description": (
            "Kit completo com 4 produtos: serum de vitamina C 20% com acido "
            "hialuronico (30ml), creme hidratante com retinol (50ml), protetor "
            "solar FPS 50 toque seco (40ml) e agua micelar de limpeza (200ml). "
            "Formulacao vegana, cruelty-free, sem parabenos. Indicado para "
            "peles maduras e com manchas."
        ),
    },
    {
        "title": "Drone Compacto 4K com Gimbal 3 Eixos",
        "description": (
            "Drone dobravel com camera 4K 60fps, gimbal estabilizado em 3 eixos, "
            "autonomia de 35 minutos por bateria, alcance de 10km via OcuSync, "
            "deteccao de obstaculos omnidirecional, modos inteligentes (follow me, "
            "orbit, waypoint), peso 249g (dispensa registro ANAC), controle remoto "
            "com tela integrada de 5.5 polegadas."
        ),
    },
]

# %% [markdown]
# ## 9. Execucao do Pipeline
#
# Vamos gerar a apresentacao para cada produto de demonstracao.
# Para economia de custos durante o desenvolvimento, a geracao
# de imagem pode ser desabilitada com `generate_image_flag=False`.

# %%
# Configuracao: defina como True para gerar imagens (custo adicional ~$0.04/imagem)
GENERATE_IMAGES = True

output_dir = "output/presentations"
results = []

for i, product in enumerate(SAMPLE_PRODUCTS, 1):
    print(f"\n{'='*60}")
    print(f"Produto {i}/{len(SAMPLE_PRODUCTS)}: {product['title']}")
    print(f"{'='*60}")

    try:
        presentation = create_product_presentation(
            title=product["title"],
            description=product["description"],
            generate_image_flag=GENERATE_IMAGES,
        )

        filepath = save_presentation(presentation, output_dir=output_dir)

        results.append({
            "title": product["title"],
            "filepath": filepath,
            "time_seconds": presentation.generation_time_seconds,
            "success": True,
        })

        print(f"  Arquivo salvo: {filepath}")
        print(f"  Tempo: {presentation.generation_time_seconds}s")

    except Exception as e:
        logger.error(f"Erro no produto '{product['title']}': {e}")
        results.append({
            "title": product["title"],
            "filepath": None,
            "time_seconds": 0,
            "success": False,
            "error": str(e),
        })

# %% [markdown]
# ## 10. Relatorio de Custos

# %%
print("\n" + "=" * 60)
print("RELATORIO DE CUSTOS — GenAI Product Presenter")
print("=" * 60)
print(f"\n{cost_tracker.summary()}")
print(f"\nDetalhamento:")
print(f"  Chamadas de texto (GPT-4o-mini): {cost_tracker.api_calls - cost_tracker.total_images}")
print(f"  Chamadas de imagem (DALL-E 3):   {cost_tracker.total_images}")
print(f"  Tokens de entrada:               {cost_tracker.total_input_tokens:,}")
print(f"  Tokens de saida:                 {cost_tracker.total_output_tokens:,}")
print(f"  Custo texto:                     ${cost_tracker.text_cost:.4f}")
print(f"  Custo imagem:                    ${cost_tracker.image_cost:.4f}")
print(f"  Custo total:                     ${cost_tracker.total_cost:.4f}")

print(f"\nResultados:")
for r in results:
    status = "OK" if r["success"] else "ERRO"
    print(f"  [{status}] {r['title']} ({r['time_seconds']}s)")

# %% [markdown]
# ## 11. Proximos Passos
#
# ### Integracao com Dadosfera
#
# Na plataforma Dadosfera, este notebook seria integrado da seguinte forma:
#
# 1. **Dados de entrada** viriam diretamente do Snowflake Backend,
#    consultando a tabela `refined.dim_products` para obter titulo e descricao.
#
# 2. **Resultados** seriam salvos em uma tabela `refined.product_presentations`
#    com colunas para cada campo gerado (copy, keywords, etc.).
#
# 3. **Deploy** como Streamlit Data App no modulo Inteligencia, permitindo
#    que a equipe de marketing gere apresentacoes self-service.
#
# 4. **Automacao** via scheduling no modulo Integrar para gerar apresentacoes
#    automaticamente para novos produtos cadastrados.
#
# ### Otimizacoes Futuras
#
# - **Batch processing** para reduzir latencia com chamadas paralelas
# - **Cache de resultados** para evitar regeneracao de produtos ja processados
# - **A/B testing** das variacoes de copy para medir conversao
# - **Fine-tuning** do prompt com base em metricas de performance real
# - **Modelos open-source** (Llama, Mistral) para reducao de custo em escala
