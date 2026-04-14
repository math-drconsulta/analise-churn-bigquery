import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Saúde e Consumo · Churn", page_icon="🏥", layout="wide")

# ═══════════════════════════════════════════════════════════════════════
st.title("🏥 Capítulo 3 — Consumo do plano e impacto na retenção")
st.markdown("""
A intuição diz que quem usa o plano percebe mais valor e cancela menos.
Mas os dados revelam um cenário mais complexo — e mais útil.
""")

with st.expander("📖 Dicionário de Dados desta Seção", expanded=False):
    st.markdown("""
    **Fonte:** Queries `consumo_por_especialidade_a/b/c.csv`

    | Variável | Significado |
    |---|---|
    | `especialidade` | Tipo de serviço médico utilizado pelo paciente. Ex: `CLINICA_MEDICA`, `CARDIOLOGISTA`, `CM_TELE` (consulta médica via telemedicina), `CM_presencial` (consulta presencial), `EXAMES` |
    | `uso` | Se o paciente utilizou (`usou`) ou não (`nao_usou`) aquela especialidade específica durante a vigência do plano |
    | `total` | Número de contratos no grupo |
    | `churners` | Contratos que não renovaram |
    | `churn_rate` | Percentual de churn no grupo |
    | `faixa_consumo` | Agrupamento pela **quantidade total** de itens consumidos (consultas + exames + tele). Faixas: `A_sem_consumo`, `B_baixo (1-3)`, `C_medio (4-8)`, `D_alto (9-15)`, `E_muito_alto (16+)` |
    | `media_itens` | Média de itens consumidos no grupo |
    | `media_diversidade_servicos` | Média de tipos distintos de serviço usados (0 a 15) |
    | `diversidade_servicos` | Número de especialidades diferentes que o paciente usou (0 a 14) |

    **Nota importante:** Um paciente que "não usou Cardiologista" pode ter usado outras especialidades — as colunas são independentes.
    """)

# ═══════════════════════════════════════════════════════════════════════
# DADOS
# ═══════════════════════════════════════════════════════════════════════
@st.cache_data
def load_a(): return pd.read_csv("results/consumo_por_especialidade_a.csv")
@st.cache_data
def load_b(): return pd.read_csv("results/consumo_por_especialidade_b.csv")
@st.cache_data
def load_c(): return pd.read_csv("results/consumo_por_especialidade_c.csv")

tab1, tab2, tab3 = st.tabs(["🩺 Especialidades", "📊 Faixa de Consumo", "🔀 Diversidade de Uso"])

# ═══════════════════════════════════════════════════════════════════════
# TAB 1: ESPECIALIDADES
# ═══════════════════════════════════════════════════════════════════════
with tab1:
    try:
        df = load_a()

        st.markdown("""
        #### Para cada especialidade: quem usou cancela mais ou menos que quem não usou?
        """)

        # Calcular delta
        pivot = df.pivot(index="especialidade", columns="uso", values="churn_rate").reset_index()
        pivot["delta"] = pivot["usou"] - pivot["nao_usou"]
        pivot = pivot.sort_values("delta", ascending=True)

        # Dividir: especialidades que PROTEGEM (delta negativo) vs que AGRAVAM (delta positivo)
        protege = pivot[pivot["delta"] < 0]
        agrava = pivot[pivot["delta"] >= 0]

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Especialidades que Protegem", f"{len(protege)}", help="Usar reduz o churn")
        with col2:
            st.metric("Especialidades que Agravam", f"{len(agrava)}", help="Usar aumenta ou mantém o churn",
                      delta=f"{len(agrava)} itens", delta_color="inverse")

        # Gráfico de barras agrupadas
        fig = px.bar(
            df, x="especialidade", y="churn_rate", color="uso",
            barmode="group",
            title="Taxa de Churn: Usou vs Não Usou (por Especialidade)",
            text_auto='.1f',
            labels={"especialidade": "", "churn_rate": "Churn (%)", "uso": "Utilizou?"},
            color_discrete_map={"usou": "#d62728", "nao_usou": "#aec7e8"},
        )
        fig.update_layout(xaxis_tickangle=-35, height=480)
        st.plotly_chart(fig, use_container_width=True)

        # Gráfico de DELTA (impacto marginal)
        st.subheader("Impacto Marginal: Quanto o Uso Altera o Churn")
        st.caption("Valores negativos = usar PROTEGE | Valores positivos = usar AGRAVA")

        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            y=pivot["especialidade"],
            x=pivot["delta"],
            orientation="h",
            marker_color=[("#2ca02c" if d < 0 else "#d62728") for d in pivot["delta"]],
            text=pivot["delta"].apply(lambda x: f"{x:+.1f} p.p."),
            textposition="outside",
        ))
        fig2.update_layout(
            title="Delta de Churn: (Usou) − (Não Usou)",
            xaxis_title="Diferença em Pontos Percentuais",
            yaxis_title="",
            height=500,
            xaxis=dict(zeroline=True, zerolinewidth=2, zerolinecolor="gray"),
        )
        st.plotly_chart(fig2, use_container_width=True)

        st.markdown("""
        #### O resultado contra-intuitivo

        Em **todas as 16 especialidades**, quem usou tem churn **igual ou maior** que quem não usou.
        Usar o plano está associado a *mais* cancelamento, não menos.

        **A explicação é confounding:**
        - Pacientes de **1º contrato com 12m** (churn base altíssimo) são os que mais
          consomem nos primeiros meses — e cancelam de qualquer forma.
        - Quem "não usou" inclui renovações automáticas silenciosas com churn naturalmente baixo.

        **Especialidades mais reveladoras:**
        - **CM_TELE** (+7,1 p.p.): resolve a queixa pontual por tele e some. Não gera vínculo.
        - **PEDIATRA** (+6,3 p.p.): pais buscam por episódio agudo do filho e não retornam.
        - **PSIQUIATRIA** (+5,8 p.p.): demanda pontual de saúde mental.

        > **Importante:** Não interpretar como "usar faz mal". É armadilha estatística.
        > Na Página 5, quebramos esse paradoxo controlando pelo ciclo do contrato —
        > e aí sim, o consumo protege.
        """)
    except Exception as e:
        st.error(f"Erro: {e}")

# ═══════════════════════════════════════════════════════════════════════
# TAB 2: FAIXA DE CONSUMO
# ═══════════════════════════════════════════════════════════════════════
with tab2:
    try:
        df_b = load_b()

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df_b["faixa_consumo"],
            y=df_b["total_contratos"],
            name="Contratos",
            marker_color="rgba(99, 110, 250, 0.5)",
        ))
        fig.add_trace(go.Scatter(
            x=df_b["faixa_consumo"],
            y=df_b["churn_rate"],
            name="Churn (%)",
            mode="lines+markers+text",
            marker=dict(size=12, color="crimson"),
            line=dict(width=3, color="crimson"),
            yaxis="y2",
            text=df_b["churn_rate"].apply(lambda x: f"{x}%"),
            textposition="top center",
            textfont=dict(size=12, color="crimson"),
        ))
        fig.update_layout(
            title="Faixa de Consumo vs. Churn",
            yaxis=dict(title="Contratos"),
            yaxis2=dict(title="Churn (%)", overlaying="y", side="right", range=[0, 70]),
            legend=dict(orientation="h", y=1.12),
            height=450,
        )
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(df_b.rename(columns={
            "faixa_consumo": "Faixa", "total_contratos": "Contratos", "churners": "Churners",
            "churn_rate": "Churn (%)", "media_itens": "Itens/Paciente", "media_diversidade_servicos": "Diversidade Média"
        }), hide_index=True, use_container_width=True)

        st.markdown("""
        #### A curva de consumo

        | Faixa | Churn | Diversidade Média |
        |---|---|---|
        | Sem consumo | 52,2% | 0,0 |
        | Baixo (1-3) | **61,6%** | 1,2 |
        | Médio (4-8) | 59,6% | 2,4 |
        | Alto (9-15) | 57,9% | 3,0 |
        | Muito Alto (16+) | **56,4%** | 3,9 |

        "Sem consumo" tem churn menor que "Baixo" — reforça o confounding:
        renovações silenciosas (que não usam) derrubam artificialmente o churn da faixa zero.

        Porém, de **Baixo → Muito Alto**, a tendência é clara: **mais consumo = menos churn**.
        Delta entre Baixo e Muito Alto: **5,2 p.p.** — significativo em escala.
        """)
    except Exception as e:
        st.error(f"Erro: {e}")

# ═══════════════════════════════════════════════════════════════════════
# TAB 3: DIVERSIDADE DE USO
# ═══════════════════════════════════════════════════════════════════════
with tab3:
    try:
        df_c = load_c()

        # Filtrar out volumes muito baixos para visualização limpa
        df_c_valid = df_c[df_c["total_contratos"] >= 30].copy()

        fig = go.Figure()

        fig.add_trace(go.Bar(
            x=df_c_valid["diversidade_servicos"],
            y=df_c_valid["total_contratos"],
            name="Contratos",
            marker_color="rgba(44, 160, 44, 0.5)",
        ))

        fig.add_trace(go.Scatter(
            x=df_c_valid["diversidade_servicos"],
            y=df_c_valid["churn_rate"],
            name="Churn (%)",
            mode="lines+markers+text",
            marker=dict(size=10, color="crimson"),
            line=dict(width=3, color="crimson"),
            yaxis="y2",
            text=df_c_valid["churn_rate"].apply(lambda x: f"{x}%"),
            textposition="top center",
        ))

        fig.update_layout(
            title="Churn vs. Diversidade de Especialidades Usadas",
            xaxis=dict(title="Nº de Especialidades Diferentes", dtick=1),
            yaxis=dict(title="Contratos"),
            yaxis2=dict(title="Churn (%)", overlaying="y", side="right", range=[45, 70]),
            legend=dict(orientation="h", y=1.12),
            height=450,
        )
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("""
        #### Diversidade: nem tanto

        A teoria parecia lógica: usar cardiologista + dermatologista + pediatra = difícil substituir o plano.

        **Na prática, o efeito é limitado:**
        - 0 especialidades: 52,2% (confounding — inclui renovações silenciosas)
        - 1-2 especialidades: ~60% (pior faixa)
        - 3-12 especialidades: oscila entre 55-58%

        A diversidade não protege tanto quanto o **volume total de uso**. Usar 1 especialidade
        20 vezes (longitudinalidade) protege mais do que usar 5 especialidades 1 vez cada.

        **Implicação pra produto:** Trilhas de cuidado continuado (acompanhamento trimestral
        com o mesmo clínico) podem ser mais eficazes que incentivar "testar todas as especialidades".
        """)
    except Exception as e:
        st.error(f"Erro: {e}")
