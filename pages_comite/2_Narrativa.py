import streamlit as st
import pandas as pd
import plotly.express as px

st.title("📖 Narrativa — 4 Variáveis Core")
st.caption("Ciclo · Faixa etária · Crônico · Composição do titular — com toggle de duração (6m / 12m / ambos)")


@st.cache_data
def load_univariada():
    return pd.read_csv("results_comite/storytelling_univariada.csv")


@st.cache_data
def load_cruzamento():
    return pd.read_csv("results_comite/storytelling_cruzamento.csv")


try:
    df_uni = load_univariada()
    df_crz = load_cruzamento()
except FileNotFoundError as e:
    st.error(
        f"CSV não encontrado: `{e.filename}`. "
        f"Rode `queries_comite/storytelling_3vars.sql` no BigQuery e salve os 2 blocos como "
        f"`storytelling_univariada.csv` e `storytelling_cruzamento.csv` em `results_comite/`."
    )
    st.stop()

df_uni["duracao"] = df_uni["duracao"].astype(str)
df_crz["duracao"] = df_crz["duracao"].astype(str)

# ─── SIDEBAR: filtro de duração ────────────────────────────────────────────
st.sidebar.markdown("### 🔍 Duração do plano")
duracao = st.sidebar.radio(
    "Selecione:",
    options=["6m", "12m", "Ambos"],
    index=0,
    key="narrativa_dur",
)
dur_filter = {"6m": ["6"], "12m": ["12"], "Ambos": ["6", "12"]}[duracao]

df_uni_f = df_uni[df_uni["duracao"].isin(dur_filter)].copy()
df_crz_f = df_crz[df_crz["duracao"].isin(dur_filter)].copy()

st.markdown(f"**Recorte ativo:** plano de **{duracao}**")

tab_uni, tab_crz = st.tabs(["📊 Univariadas", "🔀 Cruzamento (3 vars)"])

# ═══════════════════════════════════════════════════════════════════════════
# TAB 1: UNIVARIADAS
# ═══════════════════════════════════════════════════════════════════════════
SEG_ORDER = {
    "ciclo": ["1o", "2o+"],
    "faixa_etaria": ["00-20", "21-30", "31-50", "51-70", "71+"],
    "cronico": ["S", "N"],
    "composicao_titular": ["solo", "com_crianca", "com_idoso", "com_ambos"],
}
DIM_LABELS = {
    "ciclo": "Ciclo do contrato",
    "faixa_etaria": "Faixa etária",
    "cronico": "Doença crônica (S/N)",
    "composicao_titular": "Composição do titular (deps)",
}

with tab_uni:
    st.markdown(
        "Cada variável isolada — antes de combinar. Para 'Ambos', os totais são reagregados; "
        "para 6m ou 12m, mostro o churn da duração selecionada."
    )

    for dim, label in DIM_LABELS.items():
        st.markdown(f"#### {label}")
        sub = df_uni_f[df_uni_f["dimensao"] == dim].copy()

        if sub.empty:
            st.info(f"Sem dados para `{dim}`.")
            continue

        if duracao == "Ambos":
            sub_agg = sub.groupby("segmento", as_index=False).agg(
                total_contratos=("total_contratos", "sum"),
                churners=("churners", "sum"),
            )
            sub_agg["churn_rate"] = round(100 * sub_agg["churners"] / sub_agg["total_contratos"], 1)
            sub_agg["segmento"] = pd.Categorical(
                sub_agg["segmento"], categories=SEG_ORDER[dim], ordered=True
            )
            sub_agg = sub_agg.sort_values("segmento")

            fig = px.bar(
                sub_agg,
                x="segmento",
                y="churn_rate",
                text="churn_rate",
                labels={"churn_rate": "Churn (%)", "segmento": ""},
                color_discrete_sequence=["#1565c0"],
            )
        else:
            sub["segmento"] = pd.Categorical(
                sub["segmento"], categories=SEG_ORDER[dim], ordered=True
            )
            sub = sub.sort_values(["duracao", "segmento"])

            fig = px.bar(
                sub,
                x="segmento",
                y="churn_rate",
                color="duracao",
                text="churn_rate",
                barmode="group",
                labels={"churn_rate": "Churn (%)", "segmento": "", "duracao": "Duração"},
                color_discrete_map={"6": "#4caf50", "12": "#ff5722"},
            )

        fig.update_traces(texttemplate="%{text}%", textposition="outside")
        fig.update_layout(
            height=320,
            yaxis=dict(range=[0, 100]),
            margin=dict(t=20, b=20),
            legend=dict(orientation="h", y=1.1),
        )
        st.plotly_chart(fig, use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════
# TAB 2: CRUZAMENTO 4 VARS
# ═══════════════════════════════════════════════════════════════════════════
with tab_crz:
    st.markdown(
        "Cada linha = 1 perfil (ciclo × faixa × crônico × composição). "
        "Permite ver onde mora o pior e o melhor churn."
    )

    if duracao == "Ambos":
        df_show = df_crz.groupby(
            ["ciclo", "faixa_etaria", "cronico", "composicao_titular"], as_index=False
        ).agg(
            total_contratos=("total_contratos", "sum"),
            churners=("churners", "sum"),
        )
        df_show["churn_rate"] = round(100 * df_show["churners"] / df_show["total_contratos"], 1)
    else:
        df_show = df_crz_f.copy()

    if df_show.empty:
        st.warning("Sem dados para o recorte selecionado.")
        st.stop()

    df_show = df_show.sort_values("churn_rate", ascending=False)

    c1, c2 = st.columns(2)
    cols_view = ["ciclo", "faixa_etaria", "cronico", "composicao_titular", "total_contratos", "churn_rate"]
    rename = {"ciclo": "Ciclo", "faixa_etaria": "Faixa", "cronico": "Crônico",
              "composicao_titular": "Composição",
              "total_contratos": "N", "churn_rate": "Churn %"}

    with c1:
        st.markdown("##### 🔴 Top 10 — maior churn")
        top = df_show.head(10)[cols_view].rename(columns=rename)
        st.dataframe(top, hide_index=True, use_container_width=True)

    with c2:
        st.markdown("##### 🟢 Bottom 10 — menor churn")
        bot = df_show.tail(10).sort_values("churn_rate")[cols_view].rename(columns=rename)
        st.dataframe(bot, hide_index=True, use_container_width=True)

    st.markdown("---")
    st.markdown("##### Heatmap faixa × crônico, separado por ciclo")
    st.caption("Cor = churn (%). Quanto mais vermelho, maior o risco.")

    h1, h2 = st.columns(2)
    faixa_order = SEG_ORDER["faixa_etaria"]

    for col_widget, ciclo in [(h1, "1o"), (h2, "2o+")]:
        with col_widget:
            st.markdown(f"**Ciclo: {ciclo} contrato**")
            sub = df_show[df_show["ciclo"] == ciclo]
            if sub.empty:
                st.info("Sem dados.")
                continue
            pivot = sub.pivot_table(
                index="faixa_etaria", columns="cronico", values="churn_rate", aggfunc="mean"
            )
            pivot = pivot.reindex([f for f in faixa_order if f in pivot.index])
            pivot = pivot.reindex(columns=[c for c in ["N", "S"] if c in pivot.columns])

            fig = px.imshow(
                pivot,
                text_auto=".1f",
                aspect="auto",
                labels=dict(x="Crônico", y="Faixa", color="Churn %"),
                color_continuous_scale="Reds",
                zmin=0,
                zmax=100,
            )
            fig.update_layout(height=320, margin=dict(t=30, b=20))
            st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
with st.expander("📖 Como ler esta página", expanded=False):
    st.markdown("""
    - **Univariadas** isolam cada variável — ponto de partida da narrativa antes de combinar.
    - **Cruzamento** mostra os 30+ perfis possíveis (2 ciclos × 5 faixas × 2 crônicos × 2 durações),
      filtrados para combinações com pelo menos 30 contratos.
    - **Heatmaps** ajudam a ver se faixa e crônico atuam independentemente ou se há interação
      (ex.: crônico só protege em faixas mais velhas?).

    **Próxima página:** *Score e Grupos* — usar essas 3 variáveis para gerar um score simples
    e segmentar a base em 3 buckets (alto / médio / baixo risco).
    """)
