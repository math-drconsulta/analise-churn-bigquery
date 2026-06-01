import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.title("🌐 Panorama")
st.caption("Tamanho da base e churn por duração (6m vs 12m) × ciclo (1º vs 2º+)")


@st.cache_data
def load_panorama():
    return pd.read_csv("results_comite/panorama.csv")


try:
    df = load_panorama()
except FileNotFoundError:
    st.error(
        "`results_comite/panorama.csv` não encontrado. "
        "Rode `queries_comite/panorama.sql` no BigQuery e salve o resultado nesse caminho."
    )
    st.stop()

df["duracao"] = df["duracao"].astype(str)

# ─── KPIs GLOBAIS ──────────────────────────────────────────────────────────
total = int(df["total_contratos"].sum())
churners = int(df["churners"].sum())
churn_global = round(100 * churners / total, 1) if total else 0.0

st.markdown("### Recorte total")
k1, k2, k3 = st.columns(3)
k1.metric("Contratos analisados", f"{total:,.0f}")
k2.metric("Churners", f"{churners:,.0f}")
k3.metric("Churn global", f"{churn_global}%")

st.markdown("---")

# ─── PAINEIS PARALELOS 6m vs 12m ───────────────────────────────────────────
st.markdown("### Análise paralela: 6 meses vs 12 meses")
st.caption(
    "O eixo de comparação principal do app. Cada duração tem dinâmica própria — "
    "o ciclo do contrato (1º vs 2º+) é a primeira quebra dentro de cada uma."
)

agg_dur = df.groupby("duracao", as_index=False).agg(
    total_contratos=("total_contratos", "sum"),
    churners=("churners", "sum"),
)
agg_dur["churn_rate"] = round(100 * agg_dur["churners"] / agg_dur["total_contratos"], 1)

col6, col12 = st.columns(2)

for col, dur, cor_principal in [(col6, "6", "#4caf50"), (col12, "12", "#ff5722")]:
    with col:
        sub = df[df["duracao"] == dur].copy()
        sub["ciclo"] = pd.Categorical(sub["ciclo"], categories=["1o", "2o+"], ordered=True)
        sub = sub.sort_values("ciclo")

        agg_row = agg_dur[agg_dur["duracao"] == dur]
        if agg_row.empty:
            st.warning(f"Sem dados para duração {dur}m.")
            continue
        agg = agg_row.iloc[0]

        st.markdown(f"#### Plano {dur} meses")
        kk1, kk2, kk3 = st.columns(3)
        kk1.metric("Contratos", f"{int(agg['total_contratos']):,}")
        kk2.metric("Churners", f"{int(agg['churners']):,}")
        kk3.metric("Churn rate", f"{agg['churn_rate']}%")

        fig = go.Figure(go.Bar(
            x=sub["ciclo"].astype(str),
            y=sub["churn_rate"],
            text=sub["churn_rate"].apply(lambda v: f"{v}%"),
            textposition="outside",
            marker_color=["#e57373", "#81c784"],
            hovertemplate="<b>%{x}</b><br>Churn: %{y}%<extra></extra>",
        ))
        ymax = float(sub["churn_rate"].max()) if not sub.empty else 100
        fig.update_layout(
            title=f"Churn por ciclo — {dur} meses",
            xaxis=dict(title=""),
            yaxis=dict(title="Churn (%)", range=[0, max(ymax * 1.25, 30)]),
            height=320,
            margin=dict(t=50, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)

        primeiro = sub[sub["ciclo"] == "1o"]["churn_rate"].values
        segundo = sub[sub["ciclo"] == "2o+"]["churn_rate"].values
        if len(primeiro) and len(segundo):
            gap = round(float(primeiro[0]) - float(segundo[0]), 1)
            sentido = "menor" if gap > 0 else "maior"
            st.info(
                f"**Gap 1º vs 2º+:** {abs(gap)} p.p. — "
                f"quem renovou ao menos uma vez tem churn {sentido} no plano {dur}m."
            )

st.markdown("---")

# ─── COMO LER ──────────────────────────────────────────────────────────────
with st.expander("📖 Como ler esta página", expanded=False):
    st.markdown("""
    - **Recorte total** mostra o tamanho absoluto da base (cartão de crédito, B2C, últimos 12 meses).
    - Os **dois painéis paralelos** são a tese central: cada duração tem sua dinâmica. Todas as
      próximas páginas comparam 6m e 12m lado-a-lado.
    - **Ciclo do contrato** = se o cliente está no 1º contrato ou já renovou ao menos uma vez (2º+).
      É a variável mais discriminante do estudo.

    **Próxima página:** *Narrativa* — drill-down em ciclo × faixa etária × crônico para cada duração.
    """)
