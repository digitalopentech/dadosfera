# 07 - Estratégia de Análise e Dashboard

> **Plataforma:** Dadosfera (backend Snowflake) + Metabase  
> **Dataset:** Olist Brazilian E-Commerce Public Dataset  
> **Collection:** Leonardo Nunes - 04_2026  
> **Arquivo de queries:** `sql/analytics/dashboard_queries.sql`

---

## 1. Estratégia do Dashboard

### Objetivo

O dashboard tem como objetivo transformar os dados brutos do marketplace Olist em inteligência de negócio acionável para três públicos distintos: **gestores comerciais** (performance de categorias e vendedores), **analistas de operações** (logística, prazo de entrega, estados) e **liderança executiva** (visão temporal de crescimento e tendências).

### Princípios de Design

A coleção foi estruturada seguindo três princípios:

1. **Hierarquia de visão:** do macro para o micro. As visualizações começam com tendência temporal (toda a base), passam pela distribuição geográfica e de pagamentos, e chegam ao ranking granular de vendedores.
2. **Cobertura de tipos de gráfico:** o Metabase oferece bar, line, pie, map, table, scatter e funnel. A coleção utiliza todos os sete tipos para demonstrar versatilidade analítica, conforme requisito do case.
3. **Perguntas de negócio explícitas:** cada visualização responde a uma pergunta específica, não apenas exibe dados. Isso orienta o consumidor do dashboard sem necessidade de explicação adicional.

### Layout da Collection no Metabase

```
Leonardo Nunes - 04_2026
├── [Line]    Evolução Mensal de Vendas (2016–2018)          ← ancora temporal
├── [Bar]     Receita por Categoria de Produto (Top 15)      ← visão comercial
├── [Pie]     Distribuição dos Métodos de Pagamento          ← comportamento do consumidor
├── [Map]     Volume de Pedidos por Estado Brasileiro        ← visão logística/geográfica
├── [Table]   Ranking de Performance dos Vendedores (Top 20) ← operacional granular
├── [Scatter] Preço Médio vs. Satisfação por Categoria       ← análise de correlação (bônus)
└── [Funnel]  Distribuição de Pedidos por Status             ← funil de conversão (bônus)
```

---

## 2. Como Localizar as Tabelas no Metabase

Após carregar o dataset Olist pela Dadosfera, as tabelas ficam disponíveis no Metabase via conexão Snowflake. Para localizá-las:

1. Acesse **Browse Data** no menu superior do Metabase.
2. Selecione a conexão Snowflake configurada pela Dadosfera (geralmente identificada pelo nome do workspace ou dataset ID).
3. As tabelas estarão no schema `RAW_OLIST` (ou `PUBLIC`, dependendo da configuração de ingestão).
4. No editor SQL nativo (**New > SQL Query**), referencie as tabelas com o prefixo de schema: `RAW_OLIST.OLIST_ORDERS_DATASET`.

**Tabelas disponíveis no schema RAW_OLIST:**

| Tabela | Descrição |
|--------|-----------|
| `OLIST_ORDERS_DATASET` | Pedidos com timestamps e status |
| `OLIST_ORDER_ITEMS_DATASET` | Itens por pedido (price, freight_value) |
| `OLIST_ORDER_PAYMENTS_DATASET` | Pagamentos por pedido |
| `OLIST_ORDER_REVIEWS_DATASET` | Avaliações dos clientes (review_score) |
| `OLIST_CUSTOMERS_DATASET` | Clientes com cidade e estado |
| `OLIST_PRODUCTS_DATASET` | Produtos com categoria em português |
| `OLIST_SELLERS_DATASET` | Vendedores com cidade e estado |
| `OLIST_GEOLOCATION_DATASET` | Coordenadas por CEP |
| `PRODUCT_CATEGORY_NAME_TRANSLATION` | Tradução das categorias PT → EN |

> **Dica:** Para encontrar o dataset ID na Dadosfera, navegue até o menu "Dados" > "Datasets" e copie o identificador único. Ele é usado para rastrear linhagem e conectar com as queries SQL da plataforma.

---

## 3. Visualizações do Dashboard

### Visualização 1 - Receita por Categoria de Produto (Top 15)

**Tipo de gráfico:** Bar Chart (barras verticais ou horizontais)

**Pergunta de negócio:** Quais categorias de produto geram mais receita no marketplace? Onde concentrar esforços de crescimento, negociação com fornecedores e campanhas de marketing?

**Descrição:** Agrega a receita total (preço do produto + frete) por categoria, usando a tradução para inglês como label. Limita ao Top 15 para evitar poluição visual. Inclui ticket médio para identificar categorias de alto valor unitário mesmo com baixo volume.

**Lógica da query:**
- JOIN entre `OLIST_ORDER_ITEMS_DATASET`, `OLIST_PRODUCTS_DATASET` e `PRODUCT_CATEGORY_NAME_TRANSLATION`
- `COALESCE` para tratar categorias sem tradução disponível
- `ROW_NUMBER()` para ranking e filtro no `WHERE ranking <= 15`
- `PERCENT_RANK()` sobre o total para calcular participação percentual

**Insights esperados:**
- Categorias de `health_beauty`, `watches_gifts` e `bed_bath_table` tendem a liderar em receita
- Alta receita de frete em eletrônicos indica oportunidade de otimização logística
- Categorias no Top 5 representam tipicamente mais de 40% da receita total do marketplace

---

### Visualização 2 - Evolução Mensal de Vendas (2016–2018)

**Tipo de gráfico:** Line Chart (série temporal com dois eixos)

**Pergunta de negócio:** Como a receita e o volume de pedidos evoluíram ao longo dos três anos de operação? Existem sazonalidades, picos ou quedas relevantes?

**Descrição:** Extrai ano-mês a partir de `order_purchase_timestamp`, agrega contagem de pedidos, clientes únicos e receita total por mês. Calcula crescimento mês a mês (MoM) com `LAG()` para identificar aceleração ou desaceleração.

**Lógica da query:**
- `DATE_TRUNC('MONTH', TO_TIMESTAMP(...))` para normalizar timestamps para granularidade mensal
- `LAG(receita_total) OVER (ORDER BY mes_ref)` para cálculo de crescimento MoM
- Filtro `order_status NOT IN ('canceled', 'unavailable')` para excluir pedidos não concluídos da análise de tendência

**Insights esperados:**
- Crescimento acelerado de 2016 para 2017, com pico em novembro (Black Friday)
- Os dados de 2018 são parciais (dataset encerra em agosto/2018)
- Ticket médio tende a ser estável, indicando crescimento por volume e não por preço

---

### Visualização 3 - Distribuição dos Métodos de Pagamento

**Tipo de gráfico:** Pie Chart / Donut Chart

**Pergunta de negócio:** Qual é a preferência de pagamento dos clientes brasileiros? Qual proporção utiliza parcelamento? Como isso impacta o fluxo de caixa do marketplace?

**Descrição:** Consolida os pagamentos por tipo, calcula percentual de participação e mostra a média de parcelas para cartão de crédito — indicador direto de comprometimento financeiro do consumidor.

**Lógica da query:**
- `CASE` para traduzir os valores originais em inglês para rótulos em português
- `CROSS JOIN` com CTE de totais para calcular participação percentual sem subquery correlacionada
- Agrupamento por `payment_type` com `COUNT(DISTINCT order_id)` para evitar dupla contagem em pedidos com múltiplos pagamentos

**Insights esperados:**
- Cartão de crédito representa mais de 70% dos pagamentos
- Boleto bancário ainda é relevante no contexto brasileiro (15–20%)
- Média de parcelas no cartão de crédito entre 3 e 4, indicando ticket médio moderado

---

### Visualização 4 - Volume de Pedidos por Estado Brasileiro

**Tipo de gráfico:** Map Chart (Choropleth por sigla de UF)

**Pergunta de negócio:** Qual é a distribuição geográfica dos pedidos? Quais estados têm maior potencial de crescimento e quais apresentam desafios logísticos (frete alto, prazo longo)?

**Descrição:** Join entre pedidos, clientes e itens para agregar por `customer_state`. Inclui receita total, frete médio e prazo médio de entrega por estado, permitindo análise combinada de demanda e eficiência logística.

**Lógica da query:**
- `DATEDIFF('DAY', order_purchase_timestamp, order_delivered_customer_date)` para calcular prazo de entrega
- Filtro em `order_status = 'delivered'` para garantir que apenas pedidos com entrega confirmada entrem no cálculo de prazo
- `CROSS JOIN` com totais para cálculo de participação relativa nacional

**Configuração no Metabase:**
- Selecionar o campo `"Estado (UF)"` como coluna geográfica do tipo "State" com formato "BR State Abbreviation"
- Usar `"Receita Total (R$)"` como métrica de intensidade de cor (heatmap)

**Insights esperados:**
- SP, RJ e MG concentram mais de 50% dos pedidos
- Estados do Norte e Nordeste têm prazos de entrega significativamente maiores
- Frete médio acima de R$ 25 nos estados mais distantes de SP evidencia desafio para expansão

---

### Visualização 5 - Ranking de Performance dos Vendedores (Top 20)

**Tipo de gráfico:** Table / Data Table (com conditional formatting no Metabase)

**Pergunta de negócio:** Quais são os vendedores de melhor desempenho considerando uma visão holística de volume, receita, satisfação do cliente e agilidade no despacho?

**Descrição:** Calcula um score de performance composto para cada vendedor, ponderando receita total (50%), nota média de avaliação (35%) e velocidade de despacho (15%). O score usa `PERCENT_RANK()` para normalizar as métricas em escalas comparáveis antes da ponderação.

**Lógica da query:**
- Quatro JOINs: `OLIST_SELLERS_DATASET`, `OLIST_ORDER_ITEMS_DATASET`, `OLIST_ORDERS_DATASET` e `OLIST_ORDER_REVIEWS_DATASET`
- `PERCENT_RANK() OVER (ORDER BY ...)` para normalização das métricas sem necessidade de escala manual
- `HAVING COUNT(DISTINCT oi.order_id) >= 10` para excluir vendedores com volume insuficiente para análise estatística
- `ROW_NUMBER() OVER (ORDER BY score_performance DESC)` para ranking final

**Configuração no Metabase:**
- Aplicar conditional formatting: verde para notas acima de 4.0, vermelho para abaixo de 3.0
- Fixar colunas `"Ranking"` e `"ID do Vendedor"` como colunas de referência à esquerda

**Insights esperados:**
- Vendedores top 20 tendem a concentrar disproportionalmente mais receita
- Nota média acima de 4.2 é típica dos melhores performers
- Vendedores com despacho em menos de 2 dias têm notas consistentemente melhores

---

### Visualização 6 (Bônus) - Preço Médio vs. Satisfação por Categoria

**Tipo de gráfico:** Scatter Plot (dispersão com tamanho de bolha por receita)

**Pergunta de negócio:** Existe correlação entre o preço médio de produtos de uma categoria e a satisfação dos clientes? Produtos mais caros entregam mais valor percebido?

**Descrição:** Cada ponto no scatter representa uma categoria de produto. O eixo X é o preço médio, o eixo Y é a nota média de avaliação e o tamanho da bolha é proporcional à receita total da categoria. O filtro `HAVING COUNT >= 50` garante representatividade estatística mínima.

**Lógica da query:**
- JOIN completo entre itens, produtos, pedidos e avaliações para consolidar preço e nota na mesma granularidade de categoria
- `HAVING COUNT(DISTINCT oi.order_id) >= 50` como threshold de representatividade
- Resultado final é uma linha por categoria com preço médio, nota média e receita total

**Configuração no Metabase:**
- Eixo X: `"Preço Médio (R$)"`
- Eixo Y: `"Nota Média (0-5)"`
- Bubble size: `"Receita Total (R$)"`

**Insights esperados:**
- Correlação fraca a moderada entre preço e satisfação — preço alto não garante boa avaliação
- Categorias de alto volume e boa avaliação identificam o "sweet spot" do marketplace
- Categorias com preço alto e nota baixa indicam gap de expectativa vs. entrega

---

### Visualização 7 (Bônus) - Funil de Status dos Pedidos

**Tipo de gráfico:** Funnel Chart (ou Bar Chart ordenado por etapa do ciclo de vida)

**Pergunta de negócio:** Qual é a taxa de sucesso no ciclo de vida dos pedidos? Em qual etapa ocorre maior atrito ou perda?

**Descrição:** Conta pedidos por status e os ordena na sequência lógica do ciclo de vida: criado > aprovado > em processamento > faturado > enviado > entregue. Cancelamentos e indisponíveis aparecem separados como "saídas" do funil.

**Lógica da query:**
- `CASE` para mapear status em inglês para português e definir ordem lógica do funil
- `SUM(f.total_pedidos) OVER ()` como window function para calcular participação percentual sem GROUP BY adicional
- Cálculo de `"% Relativo ao Topo do Funil"` usando `MAX(CASE WHEN ordem_funil = 1 ...)` como referência dinâmica

**Configuração no Metabase:**
- Usar o tipo "Funnel" nativo do Metabase
- Campo de etapa: `"Status do Pedido"`
- Campo de valor: `"Total de Pedidos"`

**Insights esperados:**
- Taxa de entrega acima de 96% — o marketplace tem boa eficiência operacional
- Pedidos cancelados representam menos de 1%, baixo atrito
- Quantidade de pedidos em status `created` sem avanço pode indicar falha no fluxo de aprovação de pagamento

---

## 4. Decisões Técnicas de SQL

### Dialeto Snowflake via Dadosfera

Todas as queries utilizam sintaxe nativa Snowflake. Os principais pontos de atenção:

| Ponto | Abordagem adotada |
|-------|-------------------|
| Timestamps como STRING | `TO_TIMESTAMP(coluna)` para conversão explícita |
| Diferença de datas | `DATEDIFF('DAY', data_inicio, data_fim)` |
| Truncamento de data | `DATE_TRUNC('MONTH', timestamp)` |
| Formatação de data | `TO_CHAR(data, 'YYYY-MM')` para labels no Metabase |
| NULL em divisões | `NULLIF(denominador, 0)` para evitar divisão por zero |
| Window functions | `ROW_NUMBER()`, `PERCENT_RANK()`, `LAG()` com `OVER()` explícito |

### Aliases em Português

Todos os aliases de coluna estão em português para que o Metabase exiba labels legíveis diretamente, sem necessidade de configuração adicional na camada de visualização. O padrão adotado é `AS "Nome da Coluna"` com aspas duplas para preservar espaços e acentuação.

### CTEs como Estrutura Padrão

Todas as queries usam CTEs encadeadas para maximizar legibilidade e manutenibilidade. Cada CTE representa uma etapa semântica clara:

1. CTE de dados brutos com filtros básicos
2. CTE de agregação ou enriquecimento
3. CTE de métricas derivadas (scores, percentuais)
4. SELECT final com aliases de apresentação

---

## 5. Resumo dos Tipos de Gráfico Utilizados

| # | Visualização | Tipo | Requisito |
|---|-------------|------|-----------|
| 1 | Receita por Categoria (Top 15) | Bar Chart | Obrigatório |
| 2 | Evolução Mensal de Vendas | Line Chart | Obrigatório |
| 3 | Métodos de Pagamento | Pie Chart | Obrigatório |
| 4 | Pedidos por Estado | Map Chart | Obrigatório |
| 5 | Ranking de Vendedores | Table | Obrigatório |
| 6 | Preço vs. Satisfação | Scatter Plot | Bônus |
| 7 | Funil de Status | Funnel Chart | Bônus |

Total: **7 visualizações**, **7 tipos de gráfico distintos**, superando o requisito mínimo de 5 visualizações com 5 tipos diferentes.
