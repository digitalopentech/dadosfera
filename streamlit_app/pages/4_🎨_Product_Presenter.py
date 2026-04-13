"""
Bonus: GenAI Product Presenter — Streamlit Data App

Pagina do Streamlit que permite gerar apresentacoes de produtos
com Inteligencia Artificial Generativa (GPT-4o-mini + DALL-E 3).

Funcionalidades:
- Entrada de titulo e descricao do produto
- Geracao de marketing copy (3 variacoes)
- Extracao de selling points, publico-alvo, SEO keywords
- Geracao de imagem do produto via DALL-E 3
- Download da apresentacao em HTML
- Galeria de apresentacoes geradas anteriormente
"""

import json
import os
import time
import base64
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuracao
# ---------------------------------------------------------------------------

logger = logging.getLogger("product_presenter")

TEXT_MODEL = "gpt-4o-mini"
IMAGE_MODEL = "dall-e-3"
COST_PER_1K_INPUT = 0.00015
COST_PER_1K_OUTPUT = 0.0006
COST_PER_IMAGE = 0.040

OUTPUT_DIR = Path("output/presentations")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Pagina
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Product Presenter", page_icon="", layout="wide")

st.title("GenAI Product Presenter")
st.markdown(
    "Gere apresentacoes profissionais de produtos com Inteligencia Artificial. "
    "O pipeline usa **GPT-4o-mini** para texto e **DALL-E 3** para imagens."
)


# ---------------------------------------------------------------------------
# Estado da sessao
# ---------------------------------------------------------------------------

if "presentations" not in st.session_state:
    st.session_state.presentations = []
if "api_costs" not in st.session_state:
    st.session_state.api_costs = {
        "input_tokens": 0,
        "output_tokens": 0,
        "images": 0,
        "calls": 0,
    }


# ---------------------------------------------------------------------------
# Funcoes auxiliares
# ---------------------------------------------------------------------------

def _get_api_key() -> Optional[str]:
    """Obtem a API key do ambiente ou do sidebar."""
    return os.getenv("OPENAI_API_KEY") or st.session_state.get("openai_key")


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _chat(
    api_key: str,
    system: str,
    user: str,
    temperature: float = 0.7,
    max_tokens: int = 2000,
) -> str:
    """Chamada a API de chat completions com retry."""
    payload = {
        "model": TEXT_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    for attempt in range(3):
        try:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=_headers(api_key),
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            usage = data.get("usage", {})
            st.session_state.api_costs["input_tokens"] += usage.get("prompt_tokens", 0)
            st.session_state.api_costs["output_tokens"] += usage.get("completion_tokens", 0)
            st.session_state.api_costs["calls"] += 1
            return data["choices"][0]["message"]["content"]
        except requests.exceptions.HTTPError as exc:
            if exc.response and exc.response.status_code == 429:
                time.sleep(2 ** (attempt + 1))
                continue
            raise
        except requests.exceptions.RequestException:
            time.sleep(2 ** attempt)
            continue

    raise RuntimeError("Todas as tentativas de chamada a API falharam.")


def _generate_image(api_key: str, prompt: str) -> Optional[str]:
    """Gera imagem via DALL-E 3 e retorna URL."""
    payload = {
        "model": IMAGE_MODEL,
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024",
        "quality": "standard",
    }

    for attempt in range(3):
        try:
            resp = requests.post(
                "https://api.openai.com/v1/images/generations",
                headers=_headers(api_key),
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            st.session_state.api_costs["images"] += 1
            st.session_state.api_costs["calls"] += 1
            return resp.json()["data"][0]["url"]
        except requests.exceptions.HTTPError as exc:
            if exc.response and exc.response.status_code in (429, 500, 502, 503):
                time.sleep(2 ** (attempt + 1))
                continue
            raise
        except requests.exceptions.RequestException:
            time.sleep(2 ** attempt)
            continue

    return None


def _download_as_b64(url: str) -> Optional[str]:
    """Baixa imagem e converte para base64."""
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return base64.b64encode(resp.content).decode("utf-8")
    except Exception:
        return None


def _calculate_cost() -> float:
    c = st.session_state.api_costs
    text = (c["input_tokens"] / 1000) * COST_PER_1K_INPUT + (c["output_tokens"] / 1000) * COST_PER_1K_OUTPUT
    img = c["images"] * COST_PER_IMAGE
    return text + img


# ---------------------------------------------------------------------------
# Prompts do sistema
# ---------------------------------------------------------------------------

COPY_SYSTEM = """Voce e um copywriter profissional de e-commerce brasileiro.
Crie textos de marketing persuasivos.

REGRAS:
- Portugues brasileiro
- Cada variacao: 2-4 frases
- Adapte o tom conforme solicitado
- Nao invente especificacoes

Responda EXCLUSIVAMENTE em JSON valido, sem markdown:
{
    "formal": "texto formal",
    "casual": "texto casual",
    "urgent": "texto urgente"
}"""

META_SYSTEM = """Voce e um especialista em marketing digital e SEO para e-commerce brasileiro.

REGRAS:
- Portugues brasileiro
- 5 selling points concisos
- Publico-alvo em 2-3 frases
- 8-12 keywords SEO

Responda EXCLUSIVAMENTE em JSON valido, sem markdown:
{
    "selling_points": ["..."],
    "target_audience": "...",
    "seo_keywords": ["..."]
}"""


# ---------------------------------------------------------------------------
# Pipeline de geracao
# ---------------------------------------------------------------------------

def generate_presentation(
    title: str,
    description: str,
    with_image: bool = True,
) -> dict:
    """Executa o pipeline completo de geracao."""
    api_key = _get_api_key()
    if not api_key:
        st.error("API Key da OpenAI nao configurada.")
        return {}

    start = time.time()
    result = {
        "title": title,
        "description": description,
        "generated_at": datetime.now().isoformat(),
    }

    # 1. Marketing copy
    copy_raw = _chat(
        api_key,
        COPY_SYSTEM,
        f"Produto: {title}\nDescricao: {description}\n\n"
        "Crie tres variacoes: FORMAL, CASUAL e URGENTE.",
        temperature=0.8,
    )
    try:
        copy_data = json.loads(copy_raw)
    except json.JSONDecodeError:
        copy_data = {"formal": copy_raw, "casual": "", "urgent": ""}
    result["copy"] = copy_data

    # 2. Metadados
    meta_raw = _chat(
        api_key,
        META_SYSTEM,
        f"Produto: {title}\nDescricao: {description}\n\n"
        "Extraia os metadados.",
        temperature=0.5,
    )
    try:
        meta_data = json.loads(meta_raw)
    except json.JSONDecodeError:
        meta_data = {"selling_points": [], "target_audience": meta_raw, "seo_keywords": []}
    result["selling_points"] = meta_data.get("selling_points", [])
    result["target_audience"] = meta_data.get("target_audience", "")
    result["seo_keywords"] = meta_data.get("seo_keywords", [])

    # 3. Imagem
    result["image_url"] = None
    result["image_b64"] = None
    if with_image:
        img_prompt = (
            f"Professional product photography of {title}. "
            f"{description[:500]}. "
            "Clean white background, studio lighting, high resolution, "
            "e-commerce product listing style, no text overlay."
        )
        img_url = _generate_image(api_key, img_prompt)
        if img_url:
            result["image_url"] = img_url
            result["image_b64"] = _download_as_b64(img_url)

    result["generation_time"] = round(time.time() - start, 2)
    result["cost"] = _calculate_cost()

    return result


def build_html(data: dict) -> str:
    """Constroi HTML da apresentacao."""
    copy = data.get("copy", {})
    sp_html = "\n".join(f"<li>{p}</li>" for p in data.get("selling_points", []))
    kw_html = "\n".join(
        f'<span style="background:#f0f0f0;padding:4px 12px;border-radius:16px;'
        f'font-size:0.85rem;margin:3px;">{k}</span>'
        for k in data.get("seo_keywords", [])
    )

    img_block = ""
    if data.get("image_b64"):
        img_block = (
            f'<div style="text-align:center;margin:24px 0;">'
            f'<img src="data:image/png;base64,{data["image_b64"]}" '
            f'style="max-width:100%;border-radius:12px;" '
            f'alt="{data["title"]}">'
            f'</div>'
        )
    elif data.get("image_url"):
        img_block = (
            f'<div style="text-align:center;margin:24px 0;">'
            f'<img src="{data["image_url"]}" '
            f'style="max-width:100%;border-radius:12px;" '
            f'alt="{data["title"]}">'
            f'</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{data["title"]} — Product Presentation</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#f8f9fa;color:#2d3436;line-height:1.6;padding:2rem}}
.container{{max-width:900px;margin:0 auto}}
.header{{background:linear-gradient(135deg,#1a1a2e,#0f3460);color:#fff;padding:3rem 2rem;border-radius:16px;text-align:center;margin-bottom:2rem}}
.header h1{{font-size:2rem;margin-bottom:.5rem}}
.header p{{opacity:.85;max-width:700px;margin:0 auto}}
.card{{background:#fff;border-radius:12px;padding:1.5rem;margin-bottom:1.5rem;box-shadow:0 2px 8px rgba(0,0,0,.06);border:1px solid #dfe6e9}}
.card h2{{color:#0f3460;margin-bottom:1rem;padding-bottom:.5rem;border-bottom:2px solid #dfe6e9}}
.copy-block{{background:#f8f9fa;padding:1rem;border-radius:8px;margin-bottom:1rem;border-left:3px solid #0f3460}}
.copy-block.casual{{border-left-color:#00b894}}
.copy-block.urgent{{border-left-color:#e94560}}
h3{{font-size:.9rem;color:#636e72;text-transform:uppercase;letter-spacing:.5px;margin-bottom:.5rem}}
ul{{list-style:none;padding:0}}
li{{padding:.5rem 0;border-bottom:1px solid #eee}}
li::before{{content:"\\2713";color:#00b894;font-weight:bold;margin-right:.75rem}}
.keywords{{display:flex;flex-wrap:wrap;gap:.5rem;margin-top:.5rem}}
.footer{{text-align:center;padding:2rem;color:#636e72;font-size:.85rem}}
</style>
</head>
<body>
<div class="container">
<div class="header">
<h1>{data["title"]}</h1>
<p>{data["description"]}</p>
</div>
{img_block}
<div class="card">
<h2>Marketing Copy</h2>
<h3>Tom Formal</h3>
<div class="copy-block">{copy.get("formal","")}</div>
<h3>Tom Casual</h3>
<div class="copy-block casual">{copy.get("casual","")}</div>
<h3>Tom Urgente</h3>
<div class="copy-block urgent">{copy.get("urgent","")}</div>
</div>
<div class="card">
<h2>Pontos de Venda</h2>
<ul>{sp_html}</ul>
</div>
<div class="card">
<h2>Publico-Alvo</h2>
<p>{data.get("target_audience","")}</p>
</div>
<div class="card">
<h2>Keywords SEO</h2>
<div class="keywords">{kw_html}</div>
</div>
<div class="footer">
<p>Gerado via GenAI Product Presenter | {data.get("generated_at","")} | Tempo: {data.get("generation_time",0)}s</p>
</div>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Sidebar — Configuracao
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Configuracao")

    env_key = os.getenv("OPENAI_API_KEY")
    if env_key:
        st.success("API Key encontrada no .env")
    else:
        st.text_input(
            "OpenAI API Key",
            type="password",
            key="openai_key",
            help="Insira sua API key da OpenAI",
        )

    st.divider()

    generate_images = st.toggle("Gerar imagem (DALL-E 3)", value=True)
    st.caption(
        f"Custo estimado por produto: ~$0.01 (texto)"
        f"{' + $0.04 (imagem)' if generate_images else ''}"
    )

    st.divider()

    st.subheader("Custos da Sessao")
    cost = _calculate_cost()
    c = st.session_state.api_costs
    st.metric("Custo Total", f"${cost:.4f}")
    col1, col2 = st.columns(2)
    col1.metric("Chamadas API", c["calls"])
    col2.metric("Imagens", c["images"])

    st.divider()

    st.subheader("Produtos de Exemplo")
    sample_products = {
        "Fone Bluetooth ANC": (
            "Fone de Ouvido Bluetooth Premium ANC",
            "Fone over-ear com cancelamento ativo de ruido, driver de 40mm, "
            "bateria de 30h, Bluetooth 5.3, dobravel com estojo.",
        ),
        "Cafeteira Expresso": (
            "Cafeteira Expresso Automatica Italiana",
            "Cafeteira com moedor de ceramica, 15 bar, reservatorio 1.8L, "
            "vaporizador de leite, painel touch, 5 intensidades.",
        ),
        "Mochila Antifurto": (
            "Mochila Urban Tech Antifurto 25L",
            "Mochila para notebook 15.6\", tecido impermeavel, ziper oculto, "
            "porta USB, bolso RFID-blocking, tiras refletivas.",
        ),
        "Kit Skincare Vitamina C": (
            "Kit Skincare Vitamina C Anti-Idade",
            "Kit com serum vitamina C 20%, creme com retinol, protetor FPS 50 "
            "e agua micelar. Vegano, cruelty-free, sem parabenos.",
        ),
        "Drone 4K Compacto": (
            "Drone Compacto 4K com Gimbal 3 Eixos",
            "Drone dobravel, camera 4K 60fps, gimbal 3 eixos, 35min voo, "
            "alcance 10km, 249g, deteccao de obstaculos.",
        ),
    }

    selected_sample = st.selectbox(
        "Carregar exemplo",
        ["-- Selecione --"] + list(sample_products.keys()),
    )


# ---------------------------------------------------------------------------
# Area principal — Entrada
# ---------------------------------------------------------------------------

st.subheader("Dados do Produto")

col_title, col_desc = st.columns([1, 2])

# Pre-preencher com produto de exemplo
default_title = ""
default_desc = ""
if selected_sample and selected_sample != "-- Selecione --":
    default_title, default_desc = sample_products[selected_sample]

with col_title:
    product_title = st.text_input(
        "Titulo do Produto",
        value=default_title,
        placeholder="Ex: Fone de Ouvido Bluetooth Premium",
    )

with col_desc:
    product_description = st.text_area(
        "Descricao do Produto",
        value=default_desc,
        placeholder="Descreva o produto com detalhes: materiais, funcionalidades, diferenciais...",
        height=120,
    )

st.divider()

# ---------------------------------------------------------------------------
# Geracao
# ---------------------------------------------------------------------------

generate_button = st.button(
    "Gerar Apresentacao",
    type="primary",
    use_container_width=True,
    disabled=not (product_title and product_description and _get_api_key()),
)

if not _get_api_key():
    st.warning("Configure a API Key da OpenAI no sidebar ou no arquivo .env.")

if generate_button and product_title and product_description:
    with st.spinner("Gerando apresentacao... (pode levar 15-30 segundos)"):
        progress = st.progress(0, text="Iniciando pipeline...")

        progress.progress(10, text="Gerando marketing copy...")
        data = generate_presentation(
            title=product_title,
            description=product_description,
            with_image=generate_images,
        )

        progress.progress(100, text="Concluido!")

    if data:
        st.session_state.presentations.insert(0, data)

        st.success(
            f"Apresentacao gerada em {data.get('generation_time', 0)}s | "
            f"Custo acumulado: ${_calculate_cost():.4f}"
        )

        # Exibir resultados
        st.subheader(f"Resultado: {data['title']}")

        # Imagem
        if data.get("image_url"):
            st.image(data["image_url"], caption="Imagem gerada via DALL-E 3", width=400)

        # Marketing copy
        copy = data.get("copy", {})
        st.subheader("Marketing Copy")
        tab_formal, tab_casual, tab_urgent = st.tabs(["Formal", "Casual", "Urgente"])

        with tab_formal:
            st.markdown(f"**Tom Formal:**\n\n{copy.get('formal', '')}")
        with tab_casual:
            st.markdown(f"**Tom Casual:**\n\n{copy.get('casual', '')}")
        with tab_urgent:
            st.markdown(f"**Tom Urgente:**\n\n{copy.get('urgent', '')}")

        # Selling points
        col_sp, col_meta = st.columns(2)

        with col_sp:
            st.subheader("Pontos de Venda")
            for point in data.get("selling_points", []):
                st.markdown(f"- {point}")

        with col_meta:
            st.subheader("Publico-Alvo")
            st.markdown(data.get("target_audience", ""))

            st.subheader("Keywords SEO")
            keywords = data.get("seo_keywords", [])
            if keywords:
                # Display as comma-separated tags
                st.markdown(", ".join(f"`{kw}`" for kw in keywords))

        # Download HTML
        html_content = build_html(data)

        slug = data["title"].lower().replace(" ", "_")[:40]
        filename = f"presentation_{slug}.html"

        st.download_button(
            label="Download Apresentacao HTML",
            data=html_content,
            file_name=filename,
            mime="text/html",
            use_container_width=True,
        )

        # Salvar no disco tambem
        filepath = OUTPUT_DIR / filename
        filepath.write_text(html_content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Galeria de apresentacoes anteriores
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Galeria de Apresentacoes")

if not st.session_state.presentations:
    st.info(
        "Nenhuma apresentacao gerada nesta sessao. "
        "Preencha os dados do produto e clique em 'Gerar Apresentacao'."
    )
else:
    for i, pres in enumerate(st.session_state.presentations):
        with st.expander(
            f"{pres['title']} — {pres.get('generated_at', '')[:19]}",
            expanded=(i == 0),
        ):
            col_img, col_info = st.columns([1, 2])

            with col_img:
                if pres.get("image_url"):
                    st.image(pres["image_url"], width=250)
                else:
                    st.markdown("*Sem imagem gerada*")

            with col_info:
                copy = pres.get("copy", {})
                st.markdown(f"**Formal:** {copy.get('formal', '')[:200]}...")
                st.markdown(f"**Tempo:** {pres.get('generation_time', 0)}s")

                sp = pres.get("selling_points", [])
                if sp:
                    st.markdown("**Top 3 Pontos de Venda:**")
                    for p in sp[:3]:
                        st.markdown(f"- {p}")

            # Download individual
            html = build_html(pres)
            slug = pres["title"].lower().replace(" ", "_")[:40]
            st.download_button(
                f"Download HTML",
                data=html,
                file_name=f"presentation_{slug}.html",
                mime="text/html",
                key=f"download_{i}",
            )


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()
st.caption(
    "GenAI Product Presenter | Modulo Inteligencia da Dadosfera | "
    f"Modelos: {TEXT_MODEL} + {IMAGE_MODEL}"
)
