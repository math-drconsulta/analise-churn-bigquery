"""
Pagina 12 — Impacto da Mudanca Adyen v4
========================================
Usa dados diretos: is_recurrent (renovacao), payment_status (aprovacao),
refusal_reason (motivos de recusa). Filtrado: somente contratos Adyen.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy import stats

st.set_page_config(page_title="Impacto Adyen", page_icon="💳", layout="wide")
st.title("💳 Impacto da Mudanca Adyen")
st.caption("Mudanca no sistema Adyen em **15/mai/2026** · Metrica: renovacao automatica (`is_recurrent`)")


# ═══════════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════════
@st.cache_data
def load_resumo():
    return pd.read_csv("results/impacto_adquirente.csv")

@st.cache_data
def load_semanal():
    return pd.read_csv("results/impacto_adquirente_detalhe.csv")

@st.cache_data
def load_diario():
    df = pd.read_csv("results/impacto_adquirente_diario.csv")
    df["dia"] = pd.to_datetime(df["dia"])
    df["periodo"] = df["periodo"].str.strip()
    return df

@st.cache_data
def load_aprovacao():
    try:
        return pd.read_csv("results/adyen_v4_aprovacao.csv")
    except FileNotFoundError:
        return None

@st.cache_data
def load_recusas():
    try:
        return pd.read_csv("results/adyen_v4_recusas.csv")
    except FileNotFoundError:
        return None


try:
    df_res = load_resumo()
    df_sem = load_semanal()
    df_aprov = load_aprovacao()
    df_rec = load_recusas()
except FileNotFoundError as e:
    st.error(f"CSV nao encontrado: {e}")
    st.stop()

try:
    df_dia = load_diario()
    dias_pos = len(df_dia[df_dia["periodo"] == "POS"])
except Exception:
    df_dia = None
    dias_pos = 0


# ═══════════════════════════════════════════════════════════════════
# METRICAS GLOBAIS
# ═══════════════════════════════════════════════════════════════════
pre = df_res[df_res["periodo"] == "PRE"].iloc[0]
pos = df_res[df_res["periodo"] == "POS"].iloc[0]

taxa_pre = float(pre["taxa_renovacao"])
taxa_pos = float(pos["taxa_renovacao"])
n_pre = int(pre["total_contratos"])
n_pos = int(pos["total_contratos"])
renov_pre = int(pre["renovaram"])
renov_pos = int(pos["renovaram"])
delta_global = round(taxa_pos - taxa_pre, 2)

# Pessoas retidas a mais
renovacoes_esperadas = int(round(n_pos * taxa_pre / 100))
pessoas_delta = renov_pos - renovacoes_esperadas

# Z-test
p_pre = renov_pre / n_pre if n_pre else 0
p_pos = renov_pos / n_pos if n_pos else 0
p_pool = (renov_pre + renov_pos) / (n_pre + n_pos) if (n_pre + n_pos) else 0
se = np.sqrt(p_pool * (1 - p_pool) * (1/n_pre + 1/n_pos)) if n_pre and n_pos else 0
z_stat = (p_pos - p_pre) / se if se > 0 else 0
p_valor = 2 * (1 - stats.norm.cdf(abs(z_stat)))


# ═══════════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")

if p_valor < 0.05 and delta_global > 0:
    st.success(f"**RESULTADO POSITIVO** — Renovacao subiu **{delta_global:+.1f} p.p.** (p = {p_valor:.4f})")
    veredicto_cor = "#27ae60"
elif p_valor < 0.05 and delta_global < 0:
    st.error(f"**RESULTADO NEGATIVO** — Renovacao caiu **{delta_global:+.1f} p.p.** (p = {p_valor:.4f})")
    veredicto_cor = "#c0392b"
else:
    st.warning(f"**INCONCLUSIVO** — Diferenca de {delta_global:+.1f} p.p. (p = {p_valor:.3f})")
    veredicto_cor = "#f39c12"

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Renovacao PRE", f"{taxa_pre:.1f}%", help=f"{n_pre:,} contratos Adyen")
k2.metric("Renovacao POS", f"{taxa_pos:.1f}%",
          delta=f"{delta_global:+.1f} p.p.", delta_color="normal",
          help=f"{n_pos:,} contratos Adyen")
k3.metric("Pessoas retidas a mais", f"{pessoas_delta:+,}",
          delta="vs taxa PRE mantida",
          delta_color="normal" if pessoas_delta > 0 else "inverse")
k4.metric("Contratos Adyen", f"{n_pre + n_pos:,}")
k5.metric("Dias POS", f"{dias_pos}")


# ═══════════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════════
tab_semanal, tab_aprovacao, tab_recusas, tab_diario, tab_teste = st.tabs([
    "📊 Evolucao Semanal",
    "✅ Taxa de Aprovacao",
    "❌ Motivos de Recusa",
    "📈 Curva Diaria",
    "📐 Teste Estatistico",
])


# ═══════════════════════════════════════════════════════════════════
# TAB 1: SEMANAL
# ═══════════════════════════════════════════════════════════════════
with tab_semanal:
    st.markdown("### Renovacao Automatica por Semana (is_recurrent)")

    df_s = df_sem.sort_values("janela").copy()
    df_s["label"] = df_s["janela"].str.replace(r"^\d_", "", regex=True)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_s["label"],
        y=df_s["taxa_renovacao_recurrent"],
        marker_color=[
            "#3498db" if p == "PRE" else veredicto_cor
            for p in df_s["periodo"]
        ],
        text=df_s.apply(
            lambda r: f'{r["taxa_renovacao_recurrent"]}%\n({int(r["total_contratos"]):,})', axis=1
        ),
        textposition="outside", textfont=dict(size=12),
    ))
    fig.add_hline(y=taxa_pre, line_dash="dash", line_color="#3498db", line_width=2,
                  annotation_text=f"Media PRE: {taxa_pre:.1f}%",
                  annotation_position="top left")
    fig.update_layout(
        yaxis_title="Taxa de Renovacao (%)", height=420,
        yaxis=dict(range=[
            max(0, df_s["taxa_renovacao_recurrent"].min() - 5),
            min(100, df_s["taxa_renovacao_recurrent"].max() + 5)
        ]),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Tabela
    df_tab = df_s[["label", "periodo", "total_contratos", "renovaram_recurrent",
                    "taxa_renovacao_recurrent", "cancelaram", "adyen_taxa_aprovacao"]].copy()
    df_tab["delta"] = (df_tab["taxa_renovacao_recurrent"] - taxa_pre).round(1)
    df_tab.columns = ["Semana", "Periodo", "Contratos", "Renovaram", "Renovacao (%)",
                       "Cancelaram", "Aprovacao Adyen (%)", "Δ vs PRE"]
    st.dataframe(df_tab, hide_index=True, use_container_width=True)

    st.markdown(f"""
    **Leitura:** a renovacao automatica subiu de **{taxa_pre:.1f}%** (media PRE) para
    **{taxa_pos:.1f}%** (media POS), um ganho de **{delta_global:+.1f} p.p.**
    A tendencia semanal e de **melhora progressiva** — semana 4 POS chega a
    {df_s[df_s['janela'].str.contains('sem4')]['taxa_renovacao_recurrent'].values[0] if len(df_s[df_s['janela'].str.contains('sem4')]) > 0 else '?'}%.
    """)


# ═══════════════════════════════════════════════════════════════════
# TAB 2: TAXA DE APROVACAO ADYEN
# ═══════════════════════════════════════════════════════════════════
with tab_aprovacao:
    st.markdown("### Taxa de Aprovacao de Transacoes Adyen")

    if df_aprov is not None and len(df_aprov) > 0:
        col1, col2 = st.columns(2)

        aprov_pre = df_aprov[df_aprov["periodo"] == "PRE"].iloc[0]
        aprov_pos = df_aprov[df_aprov["periodo"] == "POS"].iloc[0]

        with col1:
            st.metric("Aprovacao PRE", f'{aprov_pre["taxa_aprovacao"]}%',
                      help=f'{int(aprov_pre["total_tentativas"]):,} tentativas')
            st.metric("Tentativas PRE", f'{int(aprov_pre["total_tentativas"]):,}')
            st.metric("Sucessos PRE", f'{int(aprov_pre["sucessos"]):,}')

        with col2:
            delta_aprov = round(aprov_pos["taxa_aprovacao"] - aprov_pre["taxa_aprovacao"], 2)
            st.metric("Aprovacao POS", f'{aprov_pos["taxa_aprovacao"]}%',
                      delta=f"{delta_aprov:+.2f} p.p.", delta_color="normal")
            st.metric("Tentativas POS", f'{int(aprov_pos["total_tentativas"]):,}')
            st.metric("Sucessos POS", f'{int(aprov_pos["sucessos"]):,}')

        st.markdown(f"""
        **Contexto:** a taxa de aprovacao e baixa (~3%) porque a Adyen faz **multiplas
        tentativas** por contrato. A maioria falha, mas basta 1 sucesso pra renovar.
        O importante e que a taxa **subiu levemente** no POS ({delta_aprov:+.2f} p.p.).

        **Tentativas por contrato:**
        - PRE: {int(aprov_pre['total_tentativas']):,} tentativas / {n_pre:,} contratos = ~{aprov_pre['total_tentativas']/n_pre:.1f} tentativas/contrato
        - POS: {int(aprov_pos['total_tentativas']):,} tentativas / {n_pos:,} contratos = ~{aprov_pos['total_tentativas']/n_pos:.1f} tentativas/contrato
        """)

        # Aprovacao por semana
        st.markdown("#### Aprovacao por semana")
        df_s_aprov = df_sem[["janela", "periodo", "adyen_taxa_aprovacao", "adyen_total_tentativas",
                              "adyen_total_sucessos", "adyen_total_recusas"]].copy()
        df_s_aprov["label"] = df_s_aprov["janela"].str.replace(r"^\d_", "", regex=True)

        fig_aprov = go.Figure()
        fig_aprov.add_trace(go.Bar(
            x=df_s_aprov["label"], y=df_s_aprov["adyen_taxa_aprovacao"],
            marker_color=[
                "#3498db" if p == "PRE" else veredicto_cor
                for p in df_s_aprov["periodo"]
            ],
            text=df_s_aprov["adyen_taxa_aprovacao"].apply(lambda v: f"{v}%"),
            textposition="outside",
        ))
        fig_aprov.update_layout(
            title="Taxa de Aprovacao Adyen por Semana",
            yaxis_title="Aprovacao (%)", height=380,
            yaxis=dict(range=[0, max(df_s_aprov["adyen_taxa_aprovacao"]) + 3]),
        )
        st.plotly_chart(fig_aprov, use_container_width=True)

    else:
        st.info("Dados de aprovacao nao disponiveis.")


# ═══════════════════════════════════════════════════════════════════
# TAB 3: MOTIVOS DE RECUSA
# ═══════════════════════════════════════════════════════════════════
with tab_recusas:
    st.markdown("### Motivos de Recusa Adyen: PRE vs POS")

    if df_rec is not None and len(df_rec) > 0:
        rec_pre = df_rec[df_rec["periodo"] == "PRE"].copy()
        rec_pos = df_rec[df_rec["periodo"] == "POS"].copy()

        # Merge pra comparar
        comp = rec_pre.merge(rec_pos, on="refusal_reason", how="outer", suffixes=("_pre", "_pos"))
        comp["total_pre"] = comp["total_pre"].fillna(0).astype(int)
        comp["total_pos"] = comp["total_pos"].fillna(0).astype(int)
        comp["pct_pre"] = comp["pct_das_recusas_pre"].fillna(0)
        comp["pct_pos"] = comp["pct_das_recusas_pos"].fillna(0)
        comp["delta_pct"] = (comp["pct_pos"] - comp["pct_pre"]).round(2)
        comp = comp.sort_values("total_pos", ascending=False).head(12)

        fig_rec = go.Figure()
        fig_rec.add_trace(go.Bar(
            x=comp["refusal_reason"], y=comp["pct_pre"],
            name="PRE", marker_color="#3498db", opacity=0.6,
        ))
        fig_rec.add_trace(go.Bar(
            x=comp["refusal_reason"], y=comp["pct_pos"],
            name="POS", marker_color=veredicto_cor, opacity=0.8,
        ))
        fig_rec.update_layout(
            barmode="group", title="Distribuicao dos motivos de recusa (%)",
            yaxis_title="% das recusas", height=450,
            xaxis_tickangle=-30,
            legend=dict(orientation="h", y=1.1),
        )
        st.plotly_chart(fig_rec, use_container_width=True)

        # Destaque da mudanca principal
        blocked = comp[comp["refusal_reason"].str.contains("blocked|retry", case=False, na=False)]
        if not blocked.empty:
            b = blocked.iloc[0]
            st.success(f"""
            **Mudanca principal:** "{b['refusal_reason']}"
            caiu de **{b['pct_pre']:.1f}%** (PRE) para **{b['pct_pos']:.1f}%** (POS)
            das recusas ({b['delta_pct']:+.1f} p.p.).

            A Adyen esta **bloqueando menos tentativas** por excesso de retries.
            Isso permite mais retentativas de cobranca, o que explica a melhora na renovacao.
            """)

        # Tabela
        st.dataframe(
            comp[["refusal_reason", "total_pre", "pct_pre", "total_pos", "pct_pos", "delta_pct"]].rename(columns={
                "refusal_reason": "Motivo", "total_pre": "N (PRE)", "pct_pre": "% PRE",
                "total_pos": "N (POS)", "pct_pos": "% POS", "delta_pct": "Δ p.p.",
            }),
            hide_index=True, use_container_width=True,
        )
    else:
        st.info("Dados de recusa nao disponiveis.")


# ═══════════════════════════════════════════════════════════════════
# TAB 4: CURVA DIARIA
# ═══════════════════════════════════════════════════════════════════
with tab_diario:
    st.markdown("### Curva Diaria de Renovacao")

    if df_dia is not None and len(df_dia) > 0:
        df_d = df_dia.sort_values("dia").copy()
        df_d["mm3"] = df_d["taxa_renovacao"].rolling(3, center=True, min_periods=1).mean()

        pre_d = df_d[df_d["periodo"] == "PRE"]
        pos_d = df_d[df_d["periodo"] == "POS"]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=pre_d["dia"], y=pre_d["taxa_renovacao"],
            mode="markers", marker=dict(size=8, color="#3498db", opacity=0.5),
            name="PRE (diario)",
        ))
        fig.add_trace(go.Scatter(
            x=pos_d["dia"], y=pos_d["taxa_renovacao"],
            mode="markers", marker=dict(size=10, color=veredicto_cor, opacity=0.7,
                                         line=dict(width=1, color="white")),
            name="POS (diario)",
        ))
        fig.add_trace(go.Scatter(
            x=df_d["dia"], y=df_d["mm3"],
            mode="lines", line=dict(width=3, color="#2c3e50"),
            name="Media movel (3 dias)",
        ))

        mudanca_dt = pd.Timestamp("2026-05-15")
        fig.add_shape(
            type="line", x0=mudanca_dt, x1=mudanca_dt, y0=0, y1=1, yref="paper",
            line=dict(dash="dash", color="red", width=2),
        )
        fig.add_annotation(
            x=mudanca_dt, y=1, yref="paper", text="Mudanca Adyen",
            showarrow=False, font=dict(size=12, color="red"), yanchor="bottom",
        )
        fig.add_hline(y=taxa_pre, line_dash="dot", line_color="#3498db", line_width=1,
                      annotation_text=f"Media PRE: {taxa_pre:.1f}%",
                      annotation_position="bottom left")
        fig.update_layout(
            yaxis_title="Taxa de Renovacao (%)", height=450,
            legend=dict(orientation="h", y=1.1),
            yaxis=dict(range=[max(0, df_d["taxa_renovacao"].min() - 5),
                              min(100, df_d["taxa_renovacao"].max() + 8)]),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Dados diarios nao disponiveis.")


# ═══════════════════════════════════════════════════════════════════
# TAB 5: TESTE ESTATISTICO
# ═══════════════════════════════════════════════════════════════════
with tab_teste:
    st.markdown("### Teste de Significancia")

    diff = p_pos - p_pre
    se_diff = np.sqrt(p_pre*(1-p_pre)/n_pre + p_pos*(1-p_pos)/n_pos) if n_pre and n_pos else 0
    ci_lo = round(100 * (diff - 1.96 * se_diff), 2)
    ci_hi = round(100 * (diff + 1.96 * se_diff), 2)

    st.markdown(f"""
    | Parametro | Valor |
    |---|---|
    | N (PRE) | {n_pre:,} |
    | Renovacao PRE | {taxa_pre:.2f}% |
    | N (POS) | {n_pos:,} |
    | Renovacao POS | {taxa_pos:.2f}% |
    | Diferenca | **{delta_global:+.2f} p.p.** |
    | IC 95% | [{ci_lo:+.2f}, {ci_hi:+.2f}] p.p. |
    | z-statistic | {z_stat:.4f} |
    | **p-valor** | **{p_valor:.6f}** |
    """)

    if ci_lo > 0:
        st.success("O IC 95% nao inclui zero — a melhora e estatisticamente significativa.")
    elif ci_hi < 0:
        st.error("O IC 95% nao inclui zero — a piora e estatisticamente significativa.")
    else:
        st.warning("O IC inclui zero — nao podemos afirmar que houve mudanca real.")

    # Forest plot
    fig_ic = go.Figure()
    fig_ic.add_trace(go.Scatter(
        x=[delta_global], y=["Renovacao"],
        mode="markers", marker=dict(size=14, color=veredicto_cor),
        error_x=dict(type="data", symmetric=False,
                     array=[ci_hi - delta_global], arrayminus=[delta_global - ci_lo],
                     color="rgba(0,0,0,0.5)", thickness=3, width=10),
        showlegend=False,
    ))
    fig_ic.add_vline(x=0, line_dash="dash", line_color="gray")
    fig_ic.update_layout(
        title="IC 95% da diferenca (POS - PRE)",
        xaxis_title="Δ renovacao (p.p.)", height=150,
        margin=dict(l=10, r=10, t=40, b=20),
    )
    st.plotly_chart(fig_ic, use_container_width=True)
