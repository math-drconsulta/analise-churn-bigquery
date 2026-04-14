import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Perfis Compostos · Churn", page_icon="🎯", layout="wide")

# ═══════════════════════════════════════════════════════════════════════
st.title("🎯 Capítulo 4 — Perfis compostos de risco")
st.markdown("""
Até aqui, cada variável apareceu isolada. Mas o cancelamento resulta da combinação de
idade + família + histórico + duração. Aqui, cruzamos até 7 variáveis para identificar
os micro-segmentos onde o risco é máximo e onde a retenção é mais forte.
""")

with st.expander("📖 Dicionário de Dados desta Seção", expanded=False):
    st.markdown("""
    **Fonte:** Queries `perfis_compostos_risco_a/b/c.csv`

    Nesta análise, cruzamos **até 7 variáveis** simultaneamente para criar micro-segmentos:

    | Variável | Significado | Valores |
    |---|---|---|
    | `duracao` | Duração do plano | `6` ou `12` meses |
    | `contrato` | Ciclo do contrato | `1o` (novo) ou `2o+` (renovação) |
    | `dependentes` | Faixa de dependentes | `sem_dep`, `1-2_dep` / `1-2dep`, `3+_dep` / `3+dep` |
    | `consumo` | Se usou o plano | `S` ou `N` |
    | `faixa_idade` | Idade do titular | `00-30` / `<=30`, `31-50`, `51-70`, `71+` |
    | `cronico` | Titular com doença crônica | `S` ou `N` |
    | `classe` | Classe social agrupada | `A`, `B`, `C`, `DE`, `(sem)` |
    | `categoria` | Apenas em `_b.csv` — se é Alto ou Baixo Risco no ranking | `ALTO_RISCO` ou `BAIXO_RISCO` |
    | `media_consultas` | Média de consultas médicas no grupo (apenas em `_b.csv`) | Numérico |
    | `media_exames` | Média de exames realizados (apenas em `_b.csv`) | Numérico |

    **Filtro de volume:** Apenas perfis com **≥100 contratos** (arquivo _a) ou **≥200 contratos** (arquivo _b/_c) são exibidos para evitar ruído estatístico.
    """)

# ═══════════════════════════════════════════════════════════════════════
# DADOS
# ═══════════════════════════════════════════════════════════════════════
@st.cache_data
def load_a(): return pd.read_csv("results/perfis_compostos_risco_a.csv")
@st.cache_data
def load_b(): return pd.read_csv("results/perfis_compostos_risco_b.csv")
@st.cache_data
def load_c(): return pd.read_csv("results/perfis_compostos_risco_c.csv")

tab1, tab2, tab3 = st.tabs(["🆚 Extremos (Alto vs Baixo Risco)", "🌳 Mapa de Perfis", "🔍 Análise Detalhada"])

# ═══════════════════════════════════════════════════════════════════════
# TAB 1: EXTREMOS
# ═══════════════════════════════════════════════════════════════════════
with tab1:
    try:
        df_b = load_b()

        alto = df_b[df_b["categoria"] == "ALTO_RISCO"].copy()
        baixo = df_b[df_b["categoria"] == "BAIXO_RISCO"].copy()

        st.markdown("### Os perfis que mais cancelam vs os que mais ficam")
        st.markdown("Comparação direta dos 30 piores vs. 30 melhores perfis compostos (volume mínimo: 200 contratos).")

        col_bad, col_good = st.columns(2)

        with col_bad:
            st.error("### Perfis de Maior Risco")

            st.markdown(f"""
            **Top 3 piores:**
            1. **{alto.iloc[0]['perfil']}** → {alto.iloc[0]['churn_rate']}% ({int(alto.iloc[0]['total_contratos']):,} contratos)
            2. **{alto.iloc[1]['perfil']}** → {alto.iloc[1]['churn_rate']}% ({int(alto.iloc[1]['total_contratos']):,} contratos)
            3. **{alto.iloc[2]['perfil']}** → {alto.iloc[2]['churn_rate']}% ({int(alto.iloc[2]['total_contratos']):,} contratos)
            """)

            st.markdown("""
            **Padrão dominante:**
            - 1º contrato
            - Jovem (≤30 anos)
            - Sem ou poucos dependentes
            - Plano de 12 meses
            - Consumo baixo ou nulo
            - Não crônico

            > Assinou por impulso, não formou hábito, não renovou.
            """)

        with col_good:
            st.success("### Perfis de Maior Retenção")

            st.markdown(f"""
            **Top 3 melhores:**
            1. **{baixo.iloc[0]['perfil']}** → {baixo.iloc[0]['churn_rate']}% ({int(baixo.iloc[0]['total_contratos']):,} contratos)
            2. **{baixo.iloc[1]['perfil']}** → {baixo.iloc[1]['churn_rate']}% ({int(baixo.iloc[1]['total_contratos']):,} contratos)
            3. **{baixo.iloc[2]['perfil']}** → {baixo.iloc[2]['churn_rate']}% ({int(baixo.iloc[2]['total_contratos']):,} contratos)
            """)

            st.markdown("""
            **Padrão dominante:**
            - 2º+ contrato (renovação)
            - 3+ dependentes
            - Idade 51-70 anos ou com dependente idoso
            - Plano de 6 meses
            - Crônico
            - O consumo não é o diferenciador — a dependência da rede sim

            > Família grande, necessidade contínua de saúde, confia na rede.
            """)

        st.markdown("---")

        # Scatter plot comparativo
        df_b["cor"] = df_b["categoria"].map({"ALTO_RISCO": "Alto Risco", "BAIXO_RISCO": "Baixo Risco"})

        fig = px.scatter(
            df_b, x="total_contratos", y="churn_rate", color="cor",
            hover_name="perfil",
            size="total_contratos", size_max=35,
            title="Mapa de Perfis: Alto Risco vs Baixo Risco",
            labels={"total_contratos": "Volume de Contratos", "churn_rate": "Churn (%)", "cor": "Categoria"},
            color_discrete_map={"Alto Risco": "#d62728", "Baixo Risco": "#2ca02c"},
        )
        fig.update_layout(height=500, yaxis_range=[25, 85])
        st.plotly_chart(fig, use_container_width=True)

        # Dados extras
        with st.expander("📋 Ver tabela completa dos Top 30 Alto Risco"):
            st.dataframe(alto[["perfil", "total_contratos", "churners", "churn_rate",
                               "media_consultas", "media_exames"]].rename(columns={
                "perfil": "Perfil", "total_contratos": "Contratos", "churners": "Churners",
                "churn_rate": "Churn (%)", "media_consultas": "Consultas/Pac.", "media_exames": "Exames/Pac."
            }), hide_index=True, use_container_width=True)

        with st.expander("📋 Ver tabela completa dos Top 30 Baixo Risco"):
            st.dataframe(baixo[["perfil", "total_contratos", "churners", "churn_rate",
                                "media_consultas", "media_exames"]].rename(columns={
                "perfil": "Perfil", "total_contratos": "Contratos", "churners": "Churners",
                "churn_rate": "Churn (%)", "media_consultas": "Consultas/Pac.", "media_exames": "Exames/Pac."
            }), hide_index=True, use_container_width=True)

    except Exception as e:
        st.error(f"Erro: {e}")

# ═══════════════════════════════════════════════════════════════════════
# TAB 2: TREEMAP
# ═══════════════════════════════════════════════════════════════════════
with tab2:
    try:
        df_a = load_a()

        st.subheader("Navegação Hierárquica dos Perfis de Risco")
        st.caption("Clique nos blocos para fazer drill-down. Quanto mais vermelho, maior o churn.")

        # Escolha do nível de drill-down
        hierarchy = st.radio(
            "Nível de detalhe:",
            ["Duração → Contrato → Idade → Dependentes",
             "Contrato → Consumo → Idade → Classe"],
            horizontal=True
        )

        if hierarchy.startswith("Duração"):
            path_cols = ["duracao", "contrato", "faixa_idade", "dependentes"]
        else:
            path_cols = ["contrato", "consumo", "faixa_idade", "classe"]

        fig = px.treemap(
            df_a,
            path=path_cols,
            values="total_contratos",
            color="churn_rate",
            color_continuous_scale="RdYlGn_r",
            range_color=[35, 85],
            title="Mapa de Árvore — Perfis por Taxa de Churn",
            labels={"churn_rate": "Churn (%)"},
        )
        fig.update_traces(root_color="lightgrey")
        fig.update_layout(height=600)
        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Erro: {e}")

# ═══════════════════════════════════════════════════════════════════════
# TAB 3: ANÁLISE DETALHADA (COM QUERY 2C - CHURN SILENCIOSO)
# ═══════════════════════════════════════════════════════════════════════
with tab3:
    try:
        df_c = load_c()

        st.subheader("Churn 'Silencioso' — Sem Pedido de Cancelamento")
        st.caption("Esta tabela exclui pacientes que solicitaram `unsubscription`, focando apenas no churn passivo.")

        # Filtros interativos
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            dur_filter = st.multiselect("Duração:", df_c["duracao"].unique().tolist(),
                                        default=df_c["duracao"].unique().tolist())
        with col_f2:
            cont_filter = st.multiselect("Contrato:", df_c["contrato"].unique().tolist(),
                                         default=df_c["contrato"].unique().tolist())
        with col_f3:
            idade_filter = st.multiselect("Faixa de Idade:", df_c["faixa_idade"].unique().tolist(),
                                          default=df_c["faixa_idade"].unique().tolist())

        mask = (
            df_c["duracao"].isin(dur_filter) &
            df_c["contrato"].isin(cont_filter) &
            df_c["faixa_idade"].isin(idade_filter)
        )
        df_filtered = df_c[mask].copy()

        if df_filtered.empty:
            st.warning("Nenhum dado com os filtros selecionados.")
        else:
            # Ordenar
            sort_col = st.selectbox("Ordenar por:", ["churn_rate", "total_contratos", "churners"],
                                    format_func=lambda x: {"churn_rate": "Churn (%)", "total_contratos": "Volume", "churners": "Churners"}.get(x, x))
            df_filtered = df_filtered.sort_values(sort_col, ascending=(sort_col == "total_contratos"))

            fig = px.bar(
                df_filtered.head(30), x="churn_rate",
                y=df_filtered.head(30).apply(
                    lambda r: f"{r['duracao']}m|{r['contrato']}|{r['dependentes']}|{r['consumo']}|{r['faixa_idade']}|{r['cronico']}",
                    axis=1
                ),
                orientation="h",
                color="churn_rate",
                color_continuous_scale="RdYlGn_r",
                title=f"Top 30 Perfis (Churn Silencioso) — ordenados por {sort_col}",
                labels={"x": "Churn (%)", "y": "Perfil"},
                text="churn_rate",
            )
            fig.update_layout(height=max(500, len(df_filtered.head(30)) * 22), yaxis_title="")
            fig.update_traces(texttemplate="%{text}%", textposition="outside")
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")
            st.markdown("""
            #### 🩺 Por que Analisar o Churn Silencioso Separadamente?

            O churn com `unsubscription = S` (cancelamento ativo) é de 98,7% — óbvio e inevitável.
            Mas o churn **sem unsubscription** (48,7% da base restante) são contratos que simplesmente
            "morrem de inanição": o cartão falha, a fatura não é paga, ou o paciente ignora os lembretes.

            Esses são os churners que **ainda podem ser salvos** com intervenções assertivas.
            Os filtros acima permitem que o time de CRM e Growth identifiquem exatamente quais
            micro-segmentos silenciosos priorizar em réguas de WhatsApp/SMS pré-vencimento.
            """)

            with st.expander("📋 Tabela Completa"):
                st.dataframe(df_filtered.rename(columns={
                    "duracao": "Duração", "contrato": "Contrato", "dependentes": "Dependentes",
                    "consumo": "Consumo", "faixa_idade": "Idade", "cronico": "Crônico",
                    "total_contratos": "Contratos", "churners": "Churners", "churn_rate": "Churn (%)"
                }), hide_index=True, use_container_width=True)

    except Exception as e:
        st.error(f"Erro: {e}")

# ═══════════════════════════════════════════════════════════════════════
# CONCLUSÃO DA PÁGINA
# ═══════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("""
### Síntese: as alavancas de retenção

Cada variável contribui independentemente. Juntas, pintam um retrato claro:

| Variável | Efeito no Churn | Magnitude |
|---|---|---|
| **1º contrato** vs 2o+ | ↑ Aumenta | ~10-20 p.p. |
| **Sem dependentes** vs 3+ dep. | ↑ Aumenta | ~10 p.p. |
| **Jovem (≤30)** vs 51-70 | ↑ Aumenta | ~10-15 p.p. |
| **12 meses** vs 6 meses | ↑ Aumenta | ~5-10 p.p. |
| **Não crônico** vs crônico | ↑ Aumenta | ~5-7 p.p. |
| **Sem consumo** vs consumo (controlado) | ↑ Aumenta | ~5-10 p.p. |

A combinação dos 3 piores fatores (1º contrato + jovem + sem dep.) gera churn de **~79%**.
A combinação dos 3 melhores (2o+ + 3+ dep. + crônico + 6m) gera churn de **~29-35%**.

O spread de **~45 p.p.** entre os extremos confirma que campanhas segmentadas
podem ter impacto material no resultado.
""")
