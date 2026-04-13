"""
Script para download e preparacao dos datasets do case Dadosfera.

Datasets:
1. Olist Brazilian E-Commerce (Kaggle) - 100k pedidos
2. Amazon Product Data (amostra) - descricoes de produtos para LLM

Uso:
    python scripts/download_data.py

Requisitos:
    pip install kaggle pandas requests tqdm
"""

import os
import zipfile
import json
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm


DATA_DIR = Path(__file__).parent.parent / "data"
OLIST_DIR = DATA_DIR / "olist"
AMAZON_DIR = DATA_DIR / "amazon"


def download_file(url: str, dest: Path, desc: str = "Downloading") -> None:
    """Download arquivo com barra de progresso."""
    response = requests.get(url, stream=True)
    total = int(response.headers.get("content-length", 0))

    with open(dest, "wb") as f, tqdm(
        desc=desc, total=total, unit="B", unit_scale=True
    ) as pbar:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            pbar.update(len(chunk))


def download_olist_kaggle() -> None:
    """Download Olist dataset via Kaggle API."""
    OLIST_DIR.mkdir(parents=True, exist_ok=True)

    try:
        from kaggle.api.kaggle_api_extended import KaggleApi

        api = KaggleApi()
        api.authenticate()

        print("Baixando dataset Olist do Kaggle...")
        api.dataset_download_files(
            "olistbr/brazilian-ecommerce",
            path=str(OLIST_DIR),
            unzip=True,
        )
        print(f"Dataset Olist salvo em {OLIST_DIR}")

    except ImportError:
        print(
            "Kaggle API nao instalada. Instale com: pip install kaggle\n"
            "Configure suas credenciais em ~/.kaggle/kaggle.json\n"
            "Ou baixe manualmente de: "
            "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce"
        )
        print(f"\nColoque os CSVs descompactados em: {OLIST_DIR}")
        return
    except Exception as e:
        print(f"Erro ao baixar via Kaggle API: {e}")
        print(
            "Baixe manualmente de: "
            "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce"
        )
        print(f"Coloque os CSVs descompactados em: {OLIST_DIR}")
        return


def generate_amazon_sample() -> None:
    """Gera amostra de dados de produtos estilo Amazon para feature extraction."""
    AMAZON_DIR.mkdir(parents=True, exist_ok=True)

    products = [
        {
            "title": "FYY Leather Case with Mirror for Samsung Galaxy S8 Plus, "
            "Leather Wallet Flip Folio Case with Mirror and Wrist Strap "
            "for Samsung Galaxy S8 Plus Black",
            "description": "Premium PU Leather Top quality. Made with Premium PU "
            "Leather. Receiver design. Accurate cut-out for receiver. "
            "Convenient to Answer the phone without open the case. "
            "Hand strap makes it easy to carry around. RFID Technique: "
            "Radio Frequency Identification technology, through radio "
            "signals to identify specific targets and to read and copy "
            "electronic data. 100% Handmade. Perfect craftsmanship and "
            "reinforced stitching make it even more durable.",
        },
        {
            "title": "Anker PowerCore 10000 Portable Charger, One of the Smallest "
            "and Lightest 10000mAh Power Bank, Ultra-Compact Battery Pack",
            "description": "The Anker Advantage: Join the 50 million+ powered by "
            "our leading technology. Ultra-Compact: One of the smallest "
            "and lightest 10000mAh portable chargers. Provides 3.6 charges "
            "for iPhone X, 2.4 charges for Galaxy S9, 1.2 charges for "
            "iPad mini 4. High-Speed Charging: Anker's exclusive "
            "PowerIQ and VoltageBoost combine to deliver the fastest "
            "possible charge up to 2.4A. Does not support Qualcomm "
            "Quick Charge.",
        },
        {
            "title": "Sony WH-1000XM4 Wireless Premium Noise Canceling Overhead "
            "Headphones with Mic for Phone-Call, Black",
            "description": "Industry-leading noise canceling with Dual Noise Sensor "
            "technology. Next-level music with Edge-AI, co-developed with "
            "Sony Music Studios Tokyo. Up to 30-hour battery life with "
            "quick charging (10 min charge for 5 hours of playback). "
            "Touch Sensor controls to pause play skip tracks, control "
            "volume, activate your voice assistant, and answer phone "
            "calls. Speak-to-chat technology automatically reduces volume "
            "during conversations. Wearing detection pauses playback "
            "when headphones are removed.",
        },
        {
            "title": "Instant Pot Duo 7-in-1 Electric Pressure Cooker, "
            "Slow Cooker, Rice Cooker, Steamer, Saute, 6 Quart, 14 "
            "One-Touch Programs",
            "description": "7-IN-1 FUNCTIONALITY: Pressure cook, slow cook, rice "
            "cooker, steamer, saute pan, food warmer and yogurt maker. "
            "QUICK ONE-TOUCH COOKING: 14 customizable Smart Programs "
            "for pressure cooking ribs, soups, beans, rice, poultry, "
            "yogurt, desserts and more. COOK FAST OR SLOW: Pressure "
            "cook delicious one-pot meals up to 70% faster than "
            "traditional cooking methods or slow cook traditional "
            "favorites. EASY TO CLEAN: Fingerprint-resistant stainless "
            "steel lid and components and dishwasher-safe.",
        },
        {
            "title": "Nike Men's Revolution 5 Running Shoe, Black/Anthracite, "
            "10.5 Regular US",
            "description": "Lightweight knit material wraps your foot in breathable "
            "comfort. Soft foam cushioning delivers a smooth, stable "
            "ride. Rubber outsole adds traction and durability. "
            "Minimalist design fits in almost anywhere. Wide toe box "
            "gives toes room to splay naturally. Mesh upper for enhanced "
            "breathability. Durable rubber sole for long-lasting wear.",
        },
        {
            "title": "Kindle Paperwhite - Now Waterproof with 2x the Storage "
            "- 8 GB, Free 4G LTE + Wi-Fi",
            "description": "The thinnest, lightest Kindle Paperwhite yet with a "
            "sleek, modern design so you can read comfortably for hours. "
            "Now waterproof, so you are free to read and relax at the "
            "beach, by the pool, or in the bath. Enjoy 2x the storage "
            "with 8 GB. Or choose 32 GB to hold more magazines, comics, "
            "and audiobooks. Now with Audible. Pair with Bluetooth "
            "headphones or speakers to listen to your story. "
            "A single charge lasts weeks, not hours.",
        },
        {
            "title": "Lodge Pre-Seasoned Cast Iron Skillet with Assist Handle, "
            "10.25 inch, Black",
            "description": "SEASONED COOKWARE: A smooth, easy-release finish that "
            "improves with use. Pre-seasoned with 100% natural vegetable "
            "oil. MADE IN THE USA: Lodge has been making cast iron "
            "cookware in South Pittsburg, Tennessee since 1896. "
            "VERSATILE: Use in the oven, on the stove, on the grill, "
            "or over a campfire. EASY CARE: Hand wash, dry, rub with "
            "cooking oil. UNPARALLELED HEAT RETENTION AND EVEN HEATING: "
            "Cast iron heats slowly but provides superior heat retention.",
        },
        {
            "title": "Fitbit Charge 5 Advanced Fitness & Health Tracker with "
            "Built-in GPS, Stress Management Tools, Sleep Tracking",
            "description": "Optimize your workout with a Daily Readiness Score that "
            "reveals if you are ready to exercise or should focus on "
            "recovery. Get a daily Stress Management Score showing your "
            "body's response to stress. Track your heart health with "
            "high and low heart rate notifications and an EDA sensor "
            "for electrodermal activity responses. Built-in GPS lets "
            "you see your real-time pace and distance during outdoor "
            "runs, walks, hikes and bike rides. Advanced sleep tracking "
            "shows your sleep stages and Sleep Score.",
        },
        {
            "title": "Dyson V11 Torque Drive Cordless Vacuum Cleaner, Blue/Nickel",
            "description": "Dyson's most intelligent, powerful cordless vacuum. "
            "An integrated sensor automatically increases suction on "
            "carpets, and an LCD screen displays run time countdown so "
            "you can manage cleaning. Three cleaning modes to suit any "
            "task - Auto mode intelligently optimizes suction and run "
            "time, Eco mode for longer run time on hard floors, and "
            "Boost mode for intensive cleaning. Up to 60 minutes of "
            "run time. 14 cyclones generate forces of more than 79,000g "
            "to fling microscopic particles into the bin.",
        },
        {
            "title": "COSORI Air Fryer Max XL 5.8 Quart, 1700-Watt Electric Hot "
            "Air Fryer Oven with 11 Cooking Presets",
            "description": "100 ORIGINAL RECIPES: A complimentary cookbook is "
            "included with 100 original recipes to get you started. "
            "SQUARE BASKETS: Designed with a square shape instead of "
            "round to maximize the cooking area. 30% MORE FOOD: "
            "5.8-quart square baskets can fit a whole 5 pound chicken. "
            "CRISPY RESULTS: Create an even crispier finish with the "
            "nonstick basket. Dishwasher Safe. 11 PRESETS: Steak, "
            "Poultry, Seafood, Shrimp, Bacon, Frozen Foods, French "
            "Fries, Vegetables, Root Vegetables, Bread, Desserts.",
        },
        {
            "title": "JBL Flip 5 Waterproof Portable Bluetooth Speaker - Black",
            "description": "Wirelessly connect up to 2 smartphones or tablets to "
            "the speaker and take turns enjoying powerful sound. "
            "12 Hours of Playtime: Don't sweat the small stuff like "
            "trying to find an outlet mid-jam session. JBL Flip 5 "
            "offers 12 hours of continuous, high-quality audio playtime. "
            "IPX7 Waterproof: Take JBL Flip 5 to the beach or the pool "
            "without worrying about water damage. PartyBoost: Connect "
            "multiple JBL PartyBoost-compatible speakers for an even "
            "bigger sound.",
        },
        {
            "title": "Camiseta Masculina Algodao Premium Lisa Gola Redonda, "
            "Tam M, Azul Marinho",
            "description": "Camiseta masculina basica confeccionada em algodao "
            "premium 100% penteado, 30.1. Gola redonda reforçada com "
            "ribana 1x1. Costura dupla nas mangas e barra. Modelagem "
            "regular fit, confortavel sem ser larga. Tecido macio com "
            "toque acetinado. Pre-encolhida para manter o tamanho "
            "original apos lavagens. Disponivel em 12 cores. Ideal "
            "para uso casual e composicoes versáteis.",
        },
    ]

    output_file = AMAZON_DIR / "sample_products.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)

    print(f"Amostra de {len(products)} produtos salva em {output_file}")


def validate_olist_data() -> None:
    """Valida que todos os CSVs do Olist foram baixados corretamente."""
    expected_files = [
        "olist_orders_dataset.csv",
        "olist_order_items_dataset.csv",
        "olist_order_payments_dataset.csv",
        "olist_order_reviews_dataset.csv",
        "olist_customers_dataset.csv",
        "olist_products_dataset.csv",
        "olist_sellers_dataset.csv",
        "olist_geolocation_dataset.csv",
        "product_category_name_translation.csv",
    ]

    print("\nValidando arquivos do Olist:")
    all_ok = True
    total_records = 0

    for filename in expected_files:
        filepath = OLIST_DIR / filename
        if filepath.exists():
            df = pd.read_csv(filepath)
            total_records += len(df)
            print(f"  {filename}: {len(df):,} registros, {len(df.columns)} colunas")
        else:
            print(f"  {filename}: NAO ENCONTRADO")
            all_ok = False

    print(f"\nTotal de registros: {total_records:,}")
    if total_records >= 100_000:
        print("Requisito de 100k+ registros: ATENDIDO")
    else:
        print("AVISO: Requisito de 100k+ registros pode nao ser atendido")

    if all_ok:
        print("\nTodos os arquivos encontrados!")
    else:
        print(
            "\nAlguns arquivos estao faltando. "
            "Baixe o dataset completo do Kaggle."
        )


def main() -> None:
    """Executa o download e validacao dos datasets."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("DOWNLOAD DOS DATASETS - Case Dadosfera")
    print("=" * 60)

    print("\n1. Dataset Olist Brazilian E-Commerce")
    print("-" * 40)
    download_olist_kaggle()

    print("\n2. Amostra Amazon Product Data")
    print("-" * 40)
    generate_amazon_sample()

    print("\n3. Validacao dos dados")
    print("-" * 40)
    if OLIST_DIR.exists() and any(OLIST_DIR.glob("*.csv")):
        validate_olist_data()
    else:
        print(
            "Arquivos Olist nao encontrados. "
            "Execute o download manualmente do Kaggle."
        )

    print("\n" + "=" * 60)
    print("Download concluido!")
    print(f"Dados em: {DATA_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
