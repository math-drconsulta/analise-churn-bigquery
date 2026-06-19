"""
Pagina 19 — Quem esta em cada faixa e como melhorar
=====================================================
Versao didatica: retrato + motivo + acao por faixa.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="Faixas: Perfil e Acoes", page_icon="🎯", layout="wide")
st.title("🎯 Quem esta em cada faixa e como melhorar")
st.caption("Score v4 (churn real 30d) · Para cada faixa: quem sao, por que estao ali e o que fazer")


@st.cache_data
def load_drivers():
    return pd.read_csv("results/drivers_por_faixa.csv")

@st.cache_data
def load_transicoes():
    return pd.read_csv("results/transicao_faixas.csv")

@st.cache_data
def load_faixas():
    return pd.read_csv("results/score_v4_faixas.csv")

try:
    df_drv = load_drivers()
    df_trans = load_transicoes()
    df_fxs = load_faixas()
except FileNotFoundError as e:
    st.error(f"CSV nao encontrado: {e}")
    st.stop()

CORES = {"CRITICO": "#8b0000", "MUITO ALTO": "#d62728", "ALTO": "#ff7f0e",
         "MEDIO": "#ffbb33", "BAIXO": "#2ca02c", "MUITO BAIXO": "#1f77b4", "SEGURO": "#0d3b8b"}

FEAT_LABELS = {"ciclo": "Ciclo", "duracao": "Duracao", "cronico": "Cronico",
               "faixa_dep": "Dependentes", "faixa_idade_cat": "Idade",
               "canal_simples": "Canal", "faixa_nps_cat": "NPS",
               "faixa_tempo_cat": "Tempo clinica", "rotatividade_cat": "Rotatividade"}

VAL_LABELS = {
    "1o": "1o contrato", "2o+": "2o+ contrato",
    "6": "6 meses", "12": "12 meses",
    "N": "Nao", "S": "Sim",
    "sem_dep": "Sem dependentes", "1-2_dep": "1-2 dependentes", "3+_dep": "3+ dependentes",
    "jovem": "Jovem (ate 30)", "adulto": "Adulto (31-50)", "senior": "Senior (50+)",
    "digital": "Digital", "presencial": "Presencial",
    "sem_nps": "Sem NPS", "detrator": "Detrator", "neutro": "Neutro", "promotor": "Promotor",
    "sem_atend": "Sem atendimento", "curto": "Curto (<15min)", "medio": "Medio (15-30min)", "longo": "Longo (30min+)",
    "continuidade": "Mesmo medico", "moderada": "Rotatividade moderada", "alta": "Rotatividade alta",
}

# Layout
layout_sel = st.sidebar.radio("Faixas:", ["5_faixas", "7_faixas"],
                               format_func=lambda x: x.replace("_", " ").title())

df_fxs_sel = df_fxs[df_fxs["layout"] == layout_sel].dropna(subset=["contratos"])
df_fxs_sel = df_fxs_sel[df_fxs_sel["contratos"] > 0]
df_drv_sel = df_drv[df_drv["layout"] == layout_sel]
df_trans_sel = df_trans[df_trans["layout"] == layout_sel]

faixas = df_fxs_sel["faixa"].tolist()


# ═══════════════════════════════════════════════════════════════════
# VISAO GERAL: grafico de faixas
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")

fig = go.Figure()
fig.add_trace(go.Bar(
    x=df_fxs_sel["faixa"], y=df_fxs_sel["contratos"],
    marker_color=[CORES.get(f, "gray") for f in df_fxs_sel["faixa"]],
    opacity=0.4, name="Contratos",
    text=df_fxs_sel.apply(lambda r: f'{int(r["contratos"]):,}\n({r["pct_base"]}%)', axis=1),
    textposition="outside",
))
fig.add_trace(go.Scatter(
    x=df_fxs_sel["faixa"], y=df_fxs_sel["churn_rate"],
    mode="lines+markers+text", name="Churn real (%)",
    marker=dict(size=14, color=[CORES.get(f, "gray") for f in df_fxs_sel["faixa"]],
                line=dict(width=2, color="white")),
    line=dict(width=3, color="gray", dash="dot"),
    yaxis="y2",
    text=df_fxs_sel["churn_rate"].apply(lambda x: f"{x}%"),
    textposition="top center", textfont=dict(size=14, color="crimson"),
))
fig.update_layout(
    yaxis=dict(title="Contratos"), yaxis2=dict(title="Churn real (%)", overlaying="y", side="right", range=[0, 110]),
    height=420, legend=dict(orientation="h", y=1.1),
)
st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
# CARD POR FAIXA
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## Detalhamento por faixa")
st.markdown("Selecione uma faixa pra ver: quem sao, por que estao ali e o que fazer.")

faixa_sel = st.selectbox(
    "Faixa:",
    faixas,
    format_func=lambda f: f"{f} — {int(df_fxs_sel[df_fxs_sel['faixa']==f]['contratos'].values[0]):,} contratos, {df_fxs_sel[df_fxs_sel['faixa']==f]['churn_rate'].values[0]}% churn",
)

fi = df_fxs_sel[df_fxs_sel["faixa"] == faixa_sel].iloc[0]
cor = CORES.get(faixa_sel, "#333")
drv = df_drv_sel[df_drv_sel["faixa"] == faixa_sel]
trans = df_trans_sel[(df_trans_sel["faixa"] == faixa_sel) & (df_trans_sel["migraram"] > 0)]
trans = trans.sort_values("migraram", ascending=False)

# Header
st.markdown(
    f'<div style="background:linear-gradient(90deg, {cor}22, white); padding:20px; '
    f'border-left:6px solid {cor}; border-radius:8px; margin:10px 0;">'
    f'<h2 style="color:{cor}; margin:0;">{faixa_sel}</h2>'
    f'<p style="font-size:18px; margin:5px 0;">'
    f'{int(fi["contratos"]):,} contratos ({fi["pct_base"]}% da base) · '
    f'Churn real: <strong>{fi["churn_rate"]}%</strong></p>'
    f'</div>',
    unsafe_allow_html=True,
)


# ═══════════════════════════════════════════════════════════════════
# 1. QUEM SAO (retrato)
# ═══════════════════════════════════════════════════════════════════
st.markdown("### 1. Quem sao esses pacientes?")

if len(drv) > 0:
    cols = st.columns(3)
    for i, (_, r) in enumerate(drv.iterrows()):
        feat = FEAT_LABELS.get(r["feature"], r["feature"])
        val_risco = VAL_LABELS.get(r["val_risco"], r["val_risco"])
        val_protege = VAL_LABELS.get(r["val_protege"], r["val_protege"])

        with cols[i % 3]:
            # Mostrar o valor dominante (risco ou protecao)
            if r["pct_risco"] > r["pct_protege"]:
                pct = r["pct_risco"]
                val = val_risco
                delta = r["delta_risco"]
            else:
                pct = r["pct_protege"]
                val = val_protege
                delta = r["delta_protege"]

            st.metric(feat, f"{val} ({pct:.0f}%)",
                      delta=f"{delta:+.0f} p.p. vs base" if abs(delta) > 5 else None,
                      delta_color="inverse" if delta > 10 and pct == r["pct_risco"] else "normal")


# ═══════════════════════════════════════════════════════════════════
# 2. POR QUE ESTAO AQUI (drivers)
# ═══════════════════════════════════════════════════════════════════
st.markdown("### 2. Por que estao nessa faixa?")

drivers_risco = drv[drv["delta_risco"] > 10].sort_values("delta_risco", ascending=False)
drivers_protege = drv[drv["delta_protege"] > 10].sort_values("delta_protege", ascending=False)

if len(drivers_risco) > 0:
    st.markdown("**O que os coloca em risco** (mais concentrado que a base):")
    for _, r in drivers_risco.iterrows():
        feat = FEAT_LABELS.get(r["feature"], r["feature"])
        val = VAL_LABELS.get(r["val_risco"], r["val_risco"])
        barra = "🔴" * min(int(r["delta_risco"] / 10), 6)
        st.markdown(f"- {barra} **{feat}** = {val} → {r['pct_risco']:.0f}% da faixa (+{r['delta_risco']:.0f} p.p. acima da base)")

if len(drivers_protege) > 0:
    st.markdown("**O que os protege** (mais concentrado que a base):")
    for _, r in drivers_protege.iterrows():
        feat = FEAT_LABELS.get(r["feature"], r["feature"])
        val = VAL_LABELS.get(r["val_protege"], r["val_protege"])
        barra = "🟢" * min(int(r["delta_protege"] / 10), 6)
        st.markdown(f"- {barra} **{feat}** = {val} → {r['pct_protege']:.0f}% da faixa (+{r['delta_protege']:.0f} p.p. acima da base)")

if len(drivers_risco) == 0 and len(drivers_protege) == 0:
    st.info("Nenhuma feature muito acima da base — perfil proximo da media.")


# ═══════════════════════════════════════════════════════════════════
# 3. O QUE FAZER (transicoes)
# ═══════════════════════════════════════════════════════════════════
st.markdown("### 3. O que fazer pra mover esses contratos pra faixas melhores?")

if len(trans) == 0:
    if faixa_sel in ["SEGURO", "MUITO BAIXO"]:
        st.success("Essa ja e uma faixa segura. Foco: manter o vinculo existente.")
    else:
        st.info("Sem simulacoes de transicao pra essa faixa (volume insuficiente).")
else:
    for _, t in trans.head(5).iterrows():
        pct = t["pct_migraram"]
        migr = int(t["migraram"])
        afet = int(t["afetados"])
        delta_s = int(t["delta_score"])

        # Cor do impacto
        if pct > 50:
            icone = "🟢"
            descricao = "Impacto alto"
        elif pct > 10:
            icone = "🟡"
            descricao = "Impacto moderado"
        else:
            icone = "⚪"
            descricao = "Impacto baixo"

        st.markdown(
            f'{icone} **{t["mudanca"]}**\n\n'
            f'> {afet:,} contratos afetados → **{migr:,} migram** pra faixa melhor ({pct}%) '
            f'| Score {delta_s:+d} pts | Destino: {t["destinos"]}\n\n'
            f'*{descricao}*'
        )
        st.markdown("")

    # Resumo visual
    st.markdown("---")
    st.markdown("#### Resumo: impacto por acao")

    fig_t = go.Figure()
    trans_plot = trans.head(5).iloc[::-1]
    fig_t.add_trace(go.Bar(
        y=trans_plot["mudanca"],
        x=trans_plot["migraram"],
        orientation="h",
        marker_color=[
            "#27ae60" if p > 50 else "#f39c12" if p > 10 else "#95a5a6"
            for p in trans_plot["pct_migraram"]
        ],
        text=trans_plot.apply(
            lambda r: f'{int(r["migraram"]):,} contratos ({r["pct_migraram"]}%)', axis=1
        ),
        textposition="outside", textfont=dict(size=12),
    ))
    fig_t.update_layout(
        title=f"Contratos que migram pra faixa melhor — {faixa_sel}",
        xaxis_title="Contratos migrados",
        height=max(280, len(trans_plot) * 50 + 80),
        margin=dict(l=20, r=150), yaxis=dict(automargin=True),
    )
    st.plotly_chart(fig_t, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
# RESUMO EXECUTIVO (sempre visivel)
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## Resumo: as 3 alavancas principais")

st.markdown("""
Com base na analise de drivers e simulacao de transicao em todas as faixas:

| # | Acao | Por que funciona | Impacto |
|---|---|---|---|
| **1** | **Adicionar dependente** | 99% dos contratos ALTO e MEDIO sao solo. Adicionar 1 dependente move quase todos pra BAIXO/SEGURO | ~100% migram, +250-350 pts no score |
| **2** | **Incentivar uso do plano** | 79% dos contratos ALTO nunca usaram a clinica. O 1o atendimento cria vinculo | 20-50% migram pra faixa seguinte |
| **3** | **Sobreviver ao 1o ciclo** | 1o contrato concentra o risco. Quem renova uma vez muda de perfil | Consequencia das acoes 1 e 2 |

**A alavanca dominante e DEPENDENTE.** E a feature que mais separa as faixas de risco
(99% solo no ALTO vs 6% solo no SEGURO) e a que mais move contratos nas simulacoes.
""")
