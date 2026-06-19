"""
Pagina 18 — Score v4: Comparacao 5 faixas vs 7 faixas
======================================================
Target corrigido (churn real 30d). Mostra os dois layouts lado a lado.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="Score v4 — Faixas", page_icon="📊", layout="wide")
st.title("📊 Score v4 — Comparacao de Faixas")
st.caption("Target corrigido: churn real (exclui quem volta em 30 dias) · AUC 0.665")


# ═══════════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════════
@st.cache_data
def load_faixas():
    return pd.read_csv("results/score_v4_faixas.csv")

@st.cache_data
def load_faixas_original():
    return pd.read_csv("results/score_v4_faixas_original.csv")


try:
    df = load_faixas()
    df_orig = load_faixas_original()
except FileNotFoundError as e:
    st.error(f"CSV nao encontrado: {e}. Rode `scripts/salvar_faixas_target_b.py`.")
    st.stop()

CORES_5 = {"CRITICO": "#8b0000", "ALTO": "#d62728", "MEDIO": "#ffbb33", "BAIXO": "#2ca02c", "SEGURO": "#0d3b8b"}
CORES_7 = {"CRITICO": "#8b0000", "MUITO ALTO": "#d62728", "ALTO": "#ff7f0e", "MEDIO": "#ffbb33",
           "BAIXO": "#2ca02c", "MUITO BAIXO": "#1f77b4", "SEGURO": "#0d3b8b"}


# ═══════════════════════════════════════════════════════════════════
# KPIs
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")

total = int(df[df["layout"] == "5_faixas"]["contratos"].sum())
churn_medio = round(df[df["layout"] == "5_faixas"].apply(
    lambda r: r["churners"], axis=1).sum() / total * 100, 1)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Contratos", f"{total:,}")
k2.metric("Churn real (target)", f"{churn_medio}%", help="Exclui quem volta em 30 dias")
k3.metric("AUC", "0.665", delta="+0.073 vs original", delta_color="normal")
k4.metric("Melhoria", "Target corrigido", help="Remover renovacoes tardias do target")


# ═══════════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════════
tab_5, tab_7, tab_compare, tab_evolucao = st.tabs([
    "📊 5 Faixas",
    "📊 7 Faixas",
    "⚔️ 5 vs 7",
    "📈 Evolucao do Score",
])


# ═══════════════════════════════════════════════════════════════════
# FUNCAO: GRAFICO DE FAIXAS (barras + linha)
# ═══════════════════════════════════════════════════════════════════
def grafico_faixas(df_faixa, cores, titulo):
    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=df_faixa["faixa"],
        y=df_faixa["contratos"],
        name="Contratos",
        marker_color=[cores.get(f, "gray") for f in df_faixa["faixa"]],
        opacity=0.4,
        text=df_faixa.apply(
            lambda r: f'{int(r["contratos"]):,}\n({r["pct_base"]}%)', axis=1),
        textposition="outside", textfont=dict(size=11),
    ))

    fig.add_trace(go.Scatter(
        x=df_faixa["faixa"],
        y=df_faixa["churn_rate"],
        name="Churn Real (%)",
        mode="lines+markers+text",
        marker=dict(size=14,
                    color=[cores.get(f, "gray") for f in df_faixa["faixa"]],
                    line=dict(width=2, color="white")),
        line=dict(width=3, color="gray", dash="dot"),
        yaxis="y2",
        text=df_faixa["churn_rate"].apply(lambda x: f"{x}%"),
        textposition="top center",
        textfont=dict(size=14, color="crimson"),
    ))

    spread = round(df_faixa["churn_rate"].max() - df_faixa["churn_rate"].min(), 1)

    fig.update_layout(
        title=f"{titulo} — Spread: {spread} p.p.",
        yaxis=dict(title="Contratos"),
        yaxis2=dict(title="Churn Real (%)", overlaying="y", side="right", range=[0, 110]),
        legend=dict(orientation="h", y=1.12),
        height=500,
    )
    return fig


# ═══════════════════════════════════════════════════════════════════
# TAB 1: 5 FAIXAS
# ═══════════════════════════════════════════════════════════════════
with tab_5:
    st.markdown("### Score v4 — 5 Faixas")

    df_5 = df[df["layout"] == "5_faixas"].copy()
    st.plotly_chart(grafico_faixas(df_5, CORES_5, "5 Faixas"), use_container_width=True)

    spread_5 = round(df_5["churn_rate"].max() - df_5["churn_rate"].min(), 1)

    col1, col2, col3 = st.columns(3)
    col1.metric("Pior faixa (CRITICO)", f'{df_5.iloc[0]["churn_rate"]}%')
    col2.metric("Melhor faixa (SEGURO)", f'{df_5.iloc[-1]["churn_rate"]}%')
    col3.metric("Spread", f"{spread_5} p.p.")

    st.dataframe(
        df_5[["faixa", "contratos", "churners", "churn_rate", "pct_base"]].rename(columns={
            "faixa": "Faixa", "contratos": "Contratos", "churners": "Churners",
            "churn_rate": "Churn Real (%)", "pct_base": "% da Base",
        }),
        hide_index=True, use_container_width=True,
    )


# ═══════════════════════════════════════════════════════════════════
# TAB 2: 7 FAIXAS
# ═══════════════════════════════════════════════════════════════════
with tab_7:
    st.markdown("### Score v4 — 7 Faixas")

    df_7 = df[df["layout"] == "7_faixas"].copy()
    st.plotly_chart(grafico_faixas(df_7, CORES_7, "7 Faixas"), use_container_width=True)

    spread_7 = round(df_7["churn_rate"].max() - df_7["churn_rate"].min(), 1)

    # KPIs das faixas com volume
    df_7_vol = df_7[df_7["contratos"] >= 100]
    if len(df_7_vol) >= 2:
        col1, col2, col3 = st.columns(3)
        col1.metric("Pior (com volume)", f'{df_7_vol.iloc[0]["churn_rate"]}%',
                    help=f'{df_7_vol.iloc[0]["faixa"]} ({int(df_7_vol.iloc[0]["contratos"]):,})')
        col2.metric("Melhor (com volume)", f'{df_7_vol.iloc[-1]["churn_rate"]}%',
                    help=f'{df_7_vol.iloc[-1]["faixa"]} ({int(df_7_vol.iloc[-1]["contratos"]):,})')
        spread_vol = round(df_7_vol.iloc[0]["churn_rate"] - df_7_vol.iloc[-1]["churn_rate"], 1)
        col3.metric("Spread (com volume)", f"{spread_vol} p.p.")

    st.dataframe(
        df_7[["faixa", "contratos", "churners", "churn_rate", "pct_base"]].rename(columns={
            "faixa": "Faixa", "contratos": "Contratos", "churners": "Churners",
            "churn_rate": "Churn Real (%)", "pct_base": "% da Base",
        }),
        hide_index=True, use_container_width=True,
    )

    # Nota sobre faixas pequenas
    pequenas = df_7[df_7["contratos"] < 100]
    if len(pequenas) > 0:
        faixas_peq = ", ".join(pequenas["faixa"].tolist())
        st.caption(
            f"Faixas com menos de 100 contratos ({faixas_peq}): volume insuficiente "
            f"pra conclusao — interpretar com cautela."
        )


# ═══════════════════════════════════════════════════════════════════
# TAB 3: 5 vs 7 LADO A LADO
# ═══════════════════════════════════════════════════════════════════
with tab_compare:
    st.markdown("### Comparacao: 5 Faixas vs 7 Faixas")

    fig_comp = make_subplots(
        rows=1, cols=2,
        subplot_titles=("5 Faixas", "7 Faixas"),
        shared_yaxes=True,
    )

    # 5 faixas
    for _, r in df_5.iterrows():
        fig_comp.add_trace(go.Bar(
            x=[r["faixa"]], y=[r["churn_rate"]],
            marker_color=CORES_5.get(r["faixa"], "gray"),
            text=f'{r["churn_rate"]}%<br>({int(r["contratos"]):,})',
            textposition="outside", textfont=dict(size=11),
            showlegend=False,
        ), row=1, col=1)

    # 7 faixas
    for _, r in df_7.iterrows():
        fig_comp.add_trace(go.Bar(
            x=[r["faixa"]], y=[r["churn_rate"]],
            marker_color=CORES_7.get(r["faixa"], "gray"),
            text=f'{r["churn_rate"]}%<br>({int(r["contratos"]):,})',
            textposition="outside", textfont=dict(size=11),
            showlegend=False,
        ), row=1, col=2)

    fig_comp.update_layout(height=500, yaxis_title="Churn Real (%)")
    fig_comp.update_yaxes(range=[0, 110])
    st.plotly_chart(fig_comp, use_container_width=True)

    # Tabela comparativa
    st.markdown("#### Resumo")

    spread_5 = round(df_5["churn_rate"].max() - df_5["churn_rate"].min(), 1)
    spread_7 = round(df_7["churn_rate"].max() - df_7["churn_rate"].min(), 1)
    df_7_vol = df_7[df_7["contratos"] >= 100]
    spread_7_vol = round(df_7_vol["churn_rate"].max() - df_7_vol["churn_rate"].min(), 1) if len(df_7_vol) >= 2 else 0

    st.markdown(f"""
    | Metrica | 5 Faixas | 7 Faixas |
    |---|---|---|
    | Numero de faixas | 5 | 7 |
    | Spread total | {spread_5} p.p. | {spread_7} p.p. |
    | Spread (com volume) | {spread_5} p.p. | {spread_7_vol} p.p. |
    | Faixas com <100 contratos | {len(df_5[df_5['contratos'] < 100])} | {len(df_7[df_7['contratos'] < 100])} |
    | Maior faixa | {df_5.nlargest(1, 'contratos').iloc[0]['faixa']} ({int(df_5['contratos'].max()):,}) | {df_7.nlargest(1, 'contratos').iloc[0]['faixa']} ({int(df_7['contratos'].max()):,}) |
    """)

    st.markdown("""
    **5 faixas:** mais simples, todas com volume relevante. Melhor pra comunicacao executiva.

    **7 faixas:** mais granular, identifica extremos (MUITO ALTO, MUITO BAIXO).
    Mas CRITICO e MUITO ALTO tem poucos contratos.

    **Recomendacao:** usar 7 faixas no operacional (pra priorizar acoes) e 5 faixas
    nas apresentacoes (pra simplificar a mensagem).
    """)


# ═══════════════════════════════════════════════════════════════════
# TAB 4: EVOLUCAO DO SCORE
# ═══════════════════════════════════════════════════════════════════
with tab_evolucao:
    st.markdown("### Evolucao: do score original ao v4")

    st.markdown("""
    | Versao | AUC | Spread | O que mudou |
    |---|---|---|---|
    | WLS original (pag 2) | 0.579 | ~25 p.p. | 7 vars demograficas, perfis agregados |
    | Score v3 (XGB + experiencia) | 0.590 | ~28 p.p. | +NPS, rotatividade, tempo na clinica |
    | **Score v4 (target corrigido)** | **0.665** | **89 p.p.** | Excluir quem volta em 30 dias do target |

    A maior melhoria nao veio de features ou modelo — veio de **definir corretamente
    o que e churn**. Quando removemos as renovacoes tardias (45% dos "churners" voltam
    em 30 dias), o modelo passa a prever perda real com muito mais precisao.
    """)

    # Churn original vs real por faixa
    st.markdown("---")
    st.markdown("### Churn original vs churn real por faixa")
    st.markdown("""
    O mesmo score, duas leituras: o churn **original** (inclui quem volta) e o
    churn **real** (exclui quem volta em 30 dias). Mostra quanto do "churn" de
    cada faixa e temporario.
    """)

    layout_sel = st.radio("Layout:", ["5_faixas", "7_faixas"],
                          format_func=lambda x: x.replace("_", " ").title(),
                          horizontal=True, key="evol_layout")

    df_real = df[df["layout"] == layout_sel].copy()
    df_original = df_orig[df_orig["layout"] == layout_sel].copy()

    merged = df_real.merge(df_original, on="faixa", suffixes=("_real", "_orig"))

    fig_dual = go.Figure()
    fig_dual.add_trace(go.Bar(
        x=merged["faixa"], y=merged["churn_rate_orig"],
        name="Churn original (inclui retornos)",
        marker_color="#95a5a6", opacity=0.5,
        text=merged["churn_rate_orig"].apply(lambda v: f"{v}%"),
        textposition="outside",
    ))
    fig_dual.add_trace(go.Bar(
        x=merged["faixa"], y=merged["churn_rate_real"],
        name="Churn real (exclui quem volta 30d)",
        marker_color="#c0392b",
        text=merged["churn_rate_real"].apply(lambda v: f"{v}%"),
        textposition="outside",
    ))
    fig_dual.update_layout(
        barmode="group",
        title="Churn Original vs Churn Real por Faixa",
        yaxis_title="Churn (%)", height=450,
        legend=dict(orientation="h", y=1.12),
        yaxis=dict(range=[0, 110]),
    )
    st.plotly_chart(fig_dual, use_container_width=True)

    st.markdown("""
    **Leitura:** em todas as faixas, o churn real e significativamente menor
    que o original. A diferenca e o volume de pacientes que **voltam em 30 dias**
    — renovacoes tardias que inflavam o churn.
    """)
