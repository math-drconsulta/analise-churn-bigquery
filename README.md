# Análise de Churn — dr.consulta

Análise de cancelamento (churn) de contratos da dr.consulta. Combina queries no BigQuery com um app Streamlit para exploração visual: score de risco 0-1000, perfis compostos, sazonalidade, churn silencioso vs ativo, e conversão pós-falha de pagamento.

## Escopo dos dados

- **Tabela fonte:** `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
- **Universo:** contratos pagos via `credit_card`, planos de **6 ou 12 meses**, exclui `order_source = 'b2b'`
- **Janela:** vencimentos nos últimos 12 meses (`contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)`)
- **Volume típico:** ~200k contratos
- **Definição de churn:** `churn_renovacao_automatica_sn = 'S'` (renovação automática não aconteceu)

## Estrutura do projeto

```
analise-churn-bigquery/
├── app.py                       # landing page do Streamlit
├── pages/                       # capítulos do app (1-6)
├── queries/                     # SQL ativas (fonte de verdade analítica)
├── queries_originais/           # SQL legadas da empresa (referência histórica)
├── results/                     # CSVs gerados rodando queries/
└── pyproject.toml               # deps gerenciadas via uv
```

- `queries/` é o que **você edita**. Cada `.sql` corresponde a um ou mais CSVs em `results/`.
- `queries_originais/` é histórico. Não modificar.
- `results/` precisa ser **regerado** sempre que uma query mudar (ver "Como rodar" abaixo).

## Mapa query → CSV → página

| SQL em `queries/` | CSVs gerados em `results/` | Consumido por |
|---|---|---|
| `univariada.sql` | `univariada.csv` | `app.py`, `pages/1_Visao_Geral.py` |
| `univariada_temporal.sql` | `univariada_temporal.csv` | `pages/1_Visao_Geral.py` |
| `unidade_evolucao_score.sql` | `unidade_evolucao_score_a.csv` (4A unidade), `_b.csv` (4B mês), `_c.csv` (4C faixas de score) | `pages/2_Risco_e_Evolucao.py` |
| `perfis_compostos_risco.sql` | `perfis_compostos_risco_a.csv` (2A 5 vars), `perfis_compostos_7vars.csv` (2A' 7 vars), `_b.csv` (2B top alto/baixo Wilson), `_c.csv` (2C silencioso) | `pages/2_Risco_e_Evolucao.py` (7 vars), `pages/4_Perfis_Compostos.py` (5 vars, top extremos, silencioso) |
| `consumo_por_especialidade.sql` | `consumo_por_especialidade_a/b/c.csv` | `pages/3_Saude_e_Consumo.py` |
| `conversao_apos_falha_pgto.sql` | `conversao_apos_falha_pgto.csv` | `pages/6_Conversao_Falha_Pgto.py` |
| `novas_analises.sql` | múltiplos: `motivos_cancelamento.csv`, `winback_reativacoes.csv`, `tempo_primeiro_uso.csv`, `consumo_controlado_ciclo.csv`, `interacao_contrato_dep_cronico.csv`, `churn_silencioso_vs_ativo.csv` | `app.py`, `pages/5_Analises_Avancadas.py` |
| `demandas_negocio.sql` | (sob demanda) | — |

## Como rodar

### 1. Setup do ambiente

```bash
# instala uv se ainda não tiver
curl -LsSf https://astral.sh/uv/install.sh | sh

# instala deps do projeto
uv sync
```

### 2. Regerar CSVs do BigQuery

Cada bloco numerado em uma `.sql` (2A, 2B, 2C…) é uma query separada. Rode cada bloco no BigQuery e exporte o resultado para o CSV correspondente em `results/`.

Exemplo via `bq` CLI:

```bash
bq query --use_legacy_sql=false --format=csv --max_rows=10000 < queries/univariada.sql > results/univariada.csv
```

Ou cole no console do BigQuery → "Save results" → CSV → mover para `results/`.

> **Atenção:** SQLs com vários blocos (`perfis_compostos_risco.sql` tem 2A, 2B, 2C) precisam ser rodados separadamente — cada bloco gera um CSV diferente.

### 3. Rodar o app

```bash
uv run streamlit run app.py
```

## Metodologia

### Score de churn (0-1000)

- **Onde:** `queries/unidade_evolucao_score.sql` (4C) tem a fórmula hardcoded; `pages/2_Risco_e_Evolucao.py:fit_score_model` recomputa dinamicamente lendo `perfis_compostos_7vars.csv`.
- **Modelo:** WLS (Weighted Least Squares) sobre `logit(churn_rate)` dos perfis compostos. Equivalente à logística agrupada (método de Berkson).
- **Pesos:** volume de contratos por perfil.
- **Saída:** logit predito → mapeado linearmente para 0-1000 (alto = seguro, análogo ao Serasa).
- **Faixas:** CRITICO (0-199), ALTO (200-399), MEDIO (400-599), BAIXO (600-799), MINIMO (800-1000).

> **Inconsistência conhecida:** o SQL hardcoded usa 5 variáveis (idade, dependentes, duração, contrato, crônico) com pesos calculados em uma rodada anterior; o Python recomputa com 7 variáveis (acrescenta canal e classe). A página 2 mostra os números do Python. Resolver na Fase 2 — geração do SQL a partir dos coeficientes ajustados.

### Segmentação de perfis

- **Onde:** `queries/perfis_compostos_risco.sql`.
- **Variáveis:** duração × ciclo de contrato × dependentes × faixa etária (5 buckets) × crônico × canal × classe.
- **Faixas etárias:** 00-20, 21-30, 31-50, 51-70, 71+ (split em 5 buckets para separar comportamento infantil de jovem adulto).
- **Threshold de volume:** `HAVING COUNT(*) >= 50` em 2A/2C, `>= 100` em 2B (top alto/baixo).
- **Ranking de extremos (2B):** ordena por **Wilson 95% CI lower bound** (alto risco) e **upper bound** (baixo risco) em vez do ponto estimado — evita selecionar perfis pequenos com churn extremo por acaso.
- **Análise estratificada:** cada driver é testado dentro de estratos da principal confundidora (z-test bicaudal de proporções com IC 95% de Wilson).

## Limitações conhecidas (a tratar)

- **Validação:** MAE e correlação são calculados sobre os mesmos perfis usados para ajustar o modelo. Não há split out-of-time. (Fase 3 do roadmap.)
- **AUC moderado:** o score usa só variáveis demográficas/contratuais. Falta integrar features comportamentais (recência, falha de pagamento, "nunca consumiu", consumo por especialidade) — disponíveis em queries laterais mas não no score. (Fase 4.)
- **Aditividade no logit:** WLS aditivo não captura interações tipo "1o + jovem + 12m". Avaliar LightGBM com restrições de monotonicidade. (Fase 4.)
- **Filtros restritivos:** apenas `credit_card` + 6/12m + sem B2B. Não cobre boleto, débito automático, planos mensais nem B2B.
- **Definição binária de churn:** não há análise de tempo até cancelar (survival).

## Stack

- Python 3.12, gerenciado via [uv](https://docs.astral.sh/uv/)
- Streamlit, Plotly, pandas, scipy
- BigQuery via `google-cloud-bigquery[pandas]`
