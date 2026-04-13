# 05 - Extracao de Features com GenAI/LLM

> Transformando dados nao-estruturados de produtos em features estruturadas
> utilizando Large Language Models para enriquecimento da dimensao `dim_product`.

---

## Indice

1. [Visao Geral da Abordagem](#visao-geral-da-abordagem)
2. [Estrategia de Prompt Engineering](#estrategia-de-prompt-engineering)
3. [Schema de Saida](#schema-de-saida)
4. [Analise de Custo](#analise-de-custo)
5. [Estrategia de Processamento em Batch](#estrategia-de-processamento-em-batch)
6. [Validacao de Qualidade](#validacao-de-qualidade)
7. [Integracao com o Star Schema](#integracao-com-o-star-schema)

---

## Visao Geral da Abordagem

### O Problema

O dataset Amazon Product Data contem dados de produtos em formato semi-estruturado
(JSON), onde informacoes valiosas estao dispersas em campos textuais como `title` e
`description`. Esses campos contem, de forma implicita, atributos como:

- **Categoria** do produto (acessorios, eletronicos, vestuario)
- **Material** de fabricacao (couro, silicone, plastico)
- **Funcionalidades** especificas (porta-cartao, espelho, suporte)
- **Compatibilidade** com dispositivos
- **Publico-alvo** (masculino, feminino, universal)

Extrair esses atributos manualmente e inviavel para milhares de produtos. A solucao
e utilizar LLMs como agentes de extracao estruturada.

### Por que GPT-4o-mini?

| Criterio          | GPT-4o          | GPT-4o-mini     | GPT-3.5-turbo   |
|-------------------|-----------------|-----------------|------------------|
| Custo (input/1M)  | $2.50           | $0.15           | $0.50            |
| Custo (output/1M) | $10.00          | $0.60           | $1.50            |
| Qualidade         | Excelente       | Muito Boa       | Boa              |
| JSON reliability  | Altissima       | Alta            | Media            |
| Velocidade        | Media           | Alta            | Alta             |

**Decisao:** GPT-4o-mini oferece o melhor custo-beneficio para extracao estruturada
em escala. A qualidade e suficiente para o caso de uso (extracao de atributos de
produtos), e o custo e **~17x menor** que o GPT-4o, permitindo processar o dataset
completo dentro de um orcamento aceitavel.

Para os exemplos mais complexos ou ambiguos, uma estrategia de **fallback para
GPT-4o** pode ser implementada, mas nao e necessaria nesta fase.

---

## Estrategia de Prompt Engineering

### Paradigma: Context Engineering (2026)

Em vez de tratar o prompt como um simples texto, adotamos a abordagem de **Context
Engineering**, onde toda a entrada do LLM e projetada como um pipeline de dados:

```text
[System]       Papel + restricoes + formato de saida + regras
[Few-Shot]     Exemplos concretos de entrada/saida (1-2 exemplos)
[Instrucoes]   Regras especificas do dominio e fallback
[Input]        Titulo + descricao do produto
```

### System Prompt

O system prompt define o papel do modelo como especialista em catalogacao de
e-commerce, estabelecendo restricoes claras:

```text
Voce e um especialista em catalogacao de produtos de e-commerce.
Sua tarefa e extrair atributos estruturados de produtos a partir
do titulo e descricao fornecidos.

REGRAS:
1. Extraia APENAS informacoes explicitas no texto
2. Se um campo nao puder ser determinado, use null
3. Nao invente ou infira dados que nao estejam no texto
4. Categorias devem ser em ingles, padronizadas
5. Retorne APENAS o JSON valido, sem markdown
```

### Few-Shot Example

O exemplo ancora do case e o **FYY Leather Case**, que demonstra a extracao
esperada para o modelo:

```text
ENTRADA:
Title: "FYY Leather Case with Mirror for Samsung Galaxy S8 Plus,
Leather Wallet Flip Folio Case with Mirror and Wrist Strap for
Samsung Galaxy S8 Plus, Black"
Description: "Premium PU Leather Top quality. Receiver design
for hand-free to answer to phone. Hand strap makes it easy to
carry around. RFID Technique: protect personal info..."

SAIDA:
{
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
    "hands_free_receiver": true
  },
  "target_audience": null,
  "keywords": ["leather case", "wallet", "mirror", "flip folio",
               "wrist strap", "RFID"]
}
```

### Por que Few-Shot?

| Tecnica      | Melhoria de Acuracia | Custo de Tokens |
|--------------|----------------------|-----------------|
| Zero-shot    | Baseline             | Baixo           |
| One-shot     | +10-15%              | Baixo           |
| Few-shot 2-3 | +15-25%              | Medio           |

Com **1 exemplo detalhado** (one-shot), o modelo ja entende o formato de saida
esperado e a granularidade das features. Isso e suficiente para este caso, pois
o schema JSON e o system prompt complementam o alinhamento de formato.

### Temperatura

Utilizamos **temperature=0.0** para extracao deterministica. Dados factuais
exigem consistencia absoluta -- a mesma entrada deve gerar a mesma saida.

---

## Schema de Saida

### Definicao do Schema JSON

```json
{
  "category": "string | null",
  "subcategory": "string | null",
  "brand": "string | null",
  "material": "string | null",
  "target_device": "string | null",
  "color": "string | null",
  "features": {
    "has_mirror": "boolean",
    "has_wallet": "boolean",
    "has_wrist_strap": "boolean",
    "has_rfid_protection": "boolean",
    "is_flip_folio": "boolean",
    "hands_free_receiver": "boolean",
    "is_waterproof": "boolean",
    "has_kickstand": "boolean"
  },
  "target_audience": "string | null",
  "keywords": ["string"]
}
```

### Regras de Preenchimento

| Campo             | Tipo     | Regra                                           |
|-------------------|----------|-------------------------------------------------|
| `category`        | string   | Categoria principal padronizada em ingles        |
| `subcategory`     | string   | Subcategoria mais especifica                     |
| `brand`           | string   | Marca extraida do titulo                         |
| `material`        | string   | Material principal mencionado                    |
| `target_device`   | string   | Dispositivo compativel, se aplicavel             |
| `color`           | string   | Cor principal                                    |
| `features`        | object   | Booleanos para funcionalidades detectadas        |
| `target_audience` | string   | Publico-alvo se mencionado, senao null           |
| `keywords`        | array    | 3-8 palavras-chave relevantes                    |

### JSON Mode

Utilizamos `response_format={"type": "json_object"}` da API OpenAI para garantir
que a saida seja sempre um JSON valido, eliminando falhas de parsing.

---

## Analise de Custo

### Estimativa por Produto

| Componente       | Tokens Estimados |
|------------------|------------------|
| System prompt    | ~150 tokens      |
| Few-shot example | ~250 tokens      |
| Input (produto)  | ~100-300 tokens  |
| **Total input**  | **~500-700**     |
| Output (JSON)    | ~150-250 tokens  |

### Custo com GPT-4o-mini

| Escala          | Tokens Input   | Tokens Output  | Custo Total    |
|-----------------|----------------|----------------|----------------|
| 100 produtos    | ~60K           | ~20K           | ~$0.02         |
| 1.000 produtos  | ~600K          | ~200K          | ~$0.21         |
| 10.000 produtos | ~6M            | ~2M            | ~$2.10         |
| 100.000 produtos| ~60M           | ~20M           | ~$21.00        |

**Formula:**
```text
Custo = (tokens_input * $0.15/1M) + (tokens_output * $0.60/1M)
```

### Comparacao com GPT-4o

Para o mesmo volume de 10.000 produtos:
- **GPT-4o-mini:** ~$2.10
- **GPT-4o:** ~$35.00

Economia de **~94%** usando GPT-4o-mini, com perda marginal de qualidade para
este tipo de tarefa de extracao.

---

## Estrategia de Processamento em Batch

### Arquitetura do Pipeline

```text
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Dataset    │────>│  Batch       │────>│   OpenAI     │
│   (CSV/JSON) │     │  Processor   │     │   API        │
└──────────────┘     └──────────────┘     └──────────────┘
                           │                      │
                           │                      v
                           │               ┌──────────────┐
                           │               │  JSON        │
                           │               │  Response    │
                           │               └──────────────┘
                           │                      │
                           v                      v
                     ┌──────────────┐     ┌──────────────┐
                     │  Validacao   │<────│  Pydantic    │
                     │  Schema      │     │  Parsing     │
                     └──────────────┘     └──────────────┘
                           │
                           v
                     ┌──────────────┐
                     │  DataFrame   │────> CSV + JSON
                     │  Resultado   │────> Star Schema
                     └──────────────┘
```

### Parametros de Processamento

| Parametro           | Valor    | Justificativa                          |
|---------------------|----------|----------------------------------------|
| Batch size          | 50       | Equilibrio entre throughput e memoria  |
| Rate limit          | 500 RPM  | Tier 1 da API OpenAI                   |
| Retry attempts      | 3        | Resiliencia a erros transientes        |
| Retry backoff       | 2s, 4s   | Backoff exponencial                    |
| Timeout por request | 30s      | Prevencao de requests pendurados       |
| Delay entre batches | 1s       | Margem de seguranca para rate limit    |

### Tratamento de Erros

```text
Produto ──> API Call
              │
              ├── Sucesso ──> Validacao Schema ──> Resultado OK
              │                    │
              │                    └── Falha ──> Log + Retry
              │
              ├── Rate Limit (429) ──> Backoff exponencial ──> Retry
              │
              ├── Timeout ──> Log ──> Retry (max 3)
              │
              └── Erro Fatal ──> Log ──> Skip (com fallback default)
```

---

## Validacao de Qualidade

### Validacao em 3 Camadas

**Camada 1 -- Schema (automatica):**
- JSON valido? (garantido pelo `json_object` mode)
- Todos os campos obrigatorios presentes?
- Tipos corretos (string, boolean, array)?

**Camada 2 -- Consistencia (regras):**
- `category` esta dentro das categorias conhecidas?
- `keywords` tem entre 3 e 8 elementos?
- `features` tem pelo menos um booleano `true`?
- `brand` nao esta vazio quando presente no titulo?

**Camada 3 -- Amostragem (humana):**
- Revisao manual de 5-10% dos resultados
- Verificacao cruzada: features extraidas vs. texto original
- Identificacao de padroes de erro sistematico

### Metricas de Qualidade

| Metrica                     | Meta    | Descricao                                   |
|-----------------------------|---------|---------------------------------------------|
| Schema compliance rate      | > 99%   | % de respostas com JSON valido              |
| Field extraction rate       | > 85%   | % de campos nao-null                        |
| Category accuracy           | > 90%   | % de categorias corretas (amostra)          |
| Feature precision           | > 85%   | % de features corretas (amostra)            |
| Hallucination rate          | < 5%    | % de features inventadas (amostra)          |

---

## Integracao com o Star Schema

### Enriquecimento da dim_product

As features extraidas pelo LLM enriquecem a dimensao `dim_product` do star schema,
adicionando colunas analiticas que nao existiam nos dados brutos:

```text
dim_product (antes)                 dim_product (depois)
┌─────────────────────┐            ┌──────────────────────────┐
│ product_sk          │            │ product_sk               │
│ product_id          │            │ product_id               │
│ title               │            │ title                    │
│ description         │            │ description              │
│ price               │            │ price                    │
│ brand               │            │ brand                    │
│ created_at          │            │ created_at               │
│                     │            │ ── Features GenAI ──     │
│                     │            │ llm_category             │
│                     │            │ llm_subcategory          │
│                     │            │ llm_material             │
│                     │            │ llm_target_device        │
│                     │            │ llm_color                │
│                     │            │ llm_keywords             │
│                     │            │ llm_feature_count        │
│                     │            │ llm_extraction_date      │
│                     │            │ llm_model_version        │
└─────────────────────┘            └──────────────────────────┘
```

### Prefixo `llm_`

Todas as colunas geradas por LLM recebem o prefixo `llm_` para:

1. **Rastreabilidade** -- identificar claramente dados gerados por IA
2. **Governanca** -- permitir politicas diferenciadas para dados inferidos
3. **Versionamento** -- facilitar re-extracao com modelos mais novos
4. **Confianca** -- analistas sabem que esses dados sao inferidos, nao declarados

### Queries Analiticas Habilitadas

Com as features extraidas, novas analises se tornam possiveis:

```sql
-- Distribuicao de categorias inferidas por LLM
SELECT llm_category, COUNT(*) as total_products
FROM dim_product
WHERE llm_category IS NOT NULL
GROUP BY llm_category
ORDER BY total_products DESC;

-- Materiais mais comuns por faixa de preco
SELECT
    llm_material,
    CASE
        WHEN price < 20 THEN 'Budget'
        WHEN price < 50 THEN 'Mid-range'
        ELSE 'Premium'
    END as price_tier,
    COUNT(*) as total
FROM dim_product
WHERE llm_material IS NOT NULL
GROUP BY llm_material, price_tier
ORDER BY total DESC;

-- Produtos com mais features (complexidade)
SELECT title, llm_category, llm_feature_count
FROM dim_product
WHERE llm_feature_count > 5
ORDER BY llm_feature_count DESC
LIMIT 20;
```

### Pipeline ETL Completo

```text
Bronze (Raw)           Silver (Clean)         Gold (Analytics)
┌──────────┐          ┌──────────┐           ┌──────────┐
│ JSON raw │──Clean──>│ products │──Enrich──>│dim_product│
│ metadata │  Parse   │ cleaned  │  + LLM    │ enriched │
└──────────┘          └──────────┘           └──────────┘
                                                  │
                                                  v
                                             ┌──────────┐
                                             │fact_review│
                                             │star schema│
                                             └──────────┘
```

A extracao de features por LLM ocorre na transicao **Silver -> Gold**, apos a
limpeza e padronizacao dos dados, e antes da carga na dimensao final.

---

## Consideracoes Finais

### Vantagens da Abordagem

1. **Escalabilidade** -- Processa milhares de produtos sem intervencao humana
2. **Custo controlado** -- GPT-4o-mini mantem o custo abaixo de $25 para 100K produtos
3. **Qualidade alta** -- Schema enforcement + validacao Pydantic = >99% compliance
4. **Reprodutibilidade** -- Temperature 0.0 + prompt fixo = resultados deterministicos
5. **Rastreabilidade** -- Prefixo `llm_` + versionamento do modelo

### Limitacoes Conhecidas

1. **Dependencia de API externa** -- Requer conectividade e esta sujeito a rate limits
2. **Qualidade do input** -- Titulos truncados ou descricoes ausentes reduzem acuracia
3. **Evolucao de categorias** -- Novas categorias de produtos podem nao ser reconhecidas
4. **Custo acumulativo** -- Re-processamentos incrementam custo total

### Proximos Passos

- Implementar cache de resultados para evitar re-processamento
- Adicionar metricas de confianca por campo (`confidence_score`)
- Explorar fine-tuning de modelo para o dominio especifico
- Avaliar Batch API da OpenAI para reducao adicional de 50% no custo
