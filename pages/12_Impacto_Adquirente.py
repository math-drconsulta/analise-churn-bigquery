"""
Pagina 12 — Impacto da Mudanca de Adquirente (15/mai/2026)
============================================================
Compara taxa de renovacao automatica antes vs depois da troca.
Atualizar os CSVs periodicamente para acompanhar a evolucao.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from scipy import stats

st.set_page_config(page_title="Impacto Adquirente", page_icon="💳", layout="wide")
st.title("💳 Impacto da Mudanca de Adquirente")
st.caption("Mudanca realizada em **15/mai/2026** · Comparacao antes vs depois")


# ═══════════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════════
@st.cache_data
def load_resumo():
    df = pd.read_csv("results/impacto_adquirente.csv")
    df["periodo"] = df["periodo"].str.strip()
    return df

@st.cache_data
def load_detalhe():
    df = pd.read_csv("results/impacto_adquirente_detalhe.csv")
    df["duracao"] = df["duracao"].astype(str)
    return df

@st.cache_data
def load_diario():
    df = pd.read_csv("results/impacto_adquirente_diario.csv")
    df["dia"] = pd.to_datetime(df["dia"])
    df["periodo"] = df["periodo"].str.strip()
    return df


try:
    df_res = load_resumo()
    df_det = load_detalhe()
    df_dia = load_diario()
except FileNotFoundError as e:
    st.error(f"CSV nao encontrado: {e}")
    st.stop()


# ═══════════════════════════════════════════════════════════════════
# CALCULOS GLOBAIS
# ═══════════════════════════════════════════════════════════════════
pre = df_res[df_res["periodo"] == "PRE"]
pos = df_res[df_res["periodo"] == "POS"]

n_pre = int(pre["total_contratos"].sum())
n_pos = int(pos["total_contratos"].sum())
renov_pre = int(pre["renovaram"].sum())
renov_pos = int(pos["renovaram"].sum())

taxa_pre = round(100 * renov_pre / n_pre, 2) if n_pre else 0
taxa_pos = round(100 * renov_pos / n_pos, 2) if n_pos else 0
delta_global = round(taxa_pos - taxa_pre, 2)

# Z-test de proporcoes
p_pre = renov_pre / n_pre if n_pre else 0
p_pos = renov_pos / n_pos if n_pos else 0
p_pool = (renov_pre + renov_pos) / (n_pre + n_pos) if (n_pre + n_pos) else 0
se = np.sqrt(p_pool * (1 - p_pool) * (1/n_pre + 1/n_pos)) if n_pre and n_pos else 0
z_stat = (p_pos - p_pre) / se if se > 0 else 0
p_valor = 2 * (1 - stats.norm.cdf(abs(z_stat)))

dias_pos = len(df_dia[df_dia["periodo"] == "POS"])
dias_pre = len(df_dia[df_dia["periodo"] == "PRE"])


# ═══════════════════════════════════════════════════════════════════
# HEADER — VEREDICTO
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")

# Semaforo
if p_valor < 0.05 and delta_global > 0:
    st.success(f"**RESULTADO POSITIVO** — Renovacao subiu {delta_global:+.2f} p.p. (p = {p_valor:.4f})")
    veredicto_cor = "#27ae60"
elif p_valor < 0.05 and delta_global < 0:
    st.error(f"**RESULTADO NEGATIVO** — Renovacao caiu {delta_global:+.2f} p.p. (p = {p_valor:.4f})")
    veredicto_cor = "#c0392b"
else:
    st.warning(
        f"**INCONCLUSIVO** — Diferenca de {delta_global:+.2f} p.p. nao e estatisticamente "
        f"significativa (p = {p_valor:.3f}). Ainda sao {dias_pos} dias de observacao."
    )
    veredicto_cor = "#f39c12"


# ═══════════════════════════════════════════════════════════════════
# KPIs PRINCIPAIS
# ═══════════════════════════════════════════════════════════════════
st.markdown("### Panorama Geral")

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Renovacao PRE", f"{taxa_pre:.1f}%",
          help=f"Media das 3 janelas de 10 dias antes da mudanca ({n_pre:,} contratos)")
k2.metric("Renovacao POS", f"{taxa_pos:.1f}%",
          delta=f"{delta_global:+.1f} p.p.", delta_color="normal",
          help=f"Janela pos-mudanca ({n_pos:,} contratos, {dias_pos} dias)")
k3.metric("Contratos PRE", f"{n_pre:,}")
k4.metric("Contratos POS", f"{n_pos:,}")
k5.metric("Dias de observacao POS", f"{dias_pos}",
          help="Quanto mais dias, mais confiavel a comparacao")


# ═══════════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════════
tab_visao, tab_diario, tab_segmentos, tab_estatistica = st.tabs([
    "📊 Visao por Janela",
    "📈 Curva Diaria",
    "🔍 Por Segmento",
    "📐 Teste Estatistico",
])


# ═══════════════════════════════════════════════════════════════════
# TAB 1: VISAO POR JANELA
# ═══════════════════════════════════════════════════════════════════
with tab_visao:
    st.markdown("### Taxa de Renovacao por Janela de 10 Dias")
    st.markdown("""
    Cada barra e uma janela de 10 dias. As 3 primeiras sao **antes** da mudanca,
    a ultima e **depois**. A linha tracejada e a media PRE.
    """)

    df_janela = df_res.sort_values("janela")

    fig = go.Figure()

    # Barras
    cores = []
    for _, r in df_janela.iterrows():
        if r["periodo"] == "POS":
            cores.append(veredicto_cor)
        else:
            cores.append("#3498db")

    fig.add_trace(go.Bar(
        x=df_janela["janela"].str.replace(r"^\d_", "", regex=True),
        y=df_janela["taxa_renovacao"],
        marker_color=cores,
        text=df_janela.apply(
            lambda r: f'{r["taxa_renovacao"]:.1f}%<br>({int(r["total_contratos"]):,})', axis=1
        ),
        textposition="outside",
        textfont=dict(size=13),
    ))

    # Media PRE
    fig.add_hline(
        y=taxa_pre, line_dash="dash", line_color="#3498db", line_width=2,
        annotation_text=f"Media PRE: {taxa_pre:.1f}%",
        annotation_position="top left",
        annotation_font=dict(size=12, color="#3498db"),
    )

    fig.update_layout(
        yaxis_title="Taxa de Renovacao (%)",
        height=420,
        yaxis=dict(range=[
            max(0, min(df_janela["taxa_renovacao"]) - 5),
            max(df_janela["taxa_renovacao"]) + 5
        ]),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Tabela
    df_janela_display = df_janela.copy()
    df_janela_display["janela"] = df_janela_display["janela"].str.replace(r"^\d_", "", regex=True)
    df_janela_display["total_contratos"] = df_janela_display["total_contratos"].apply(lambda v: f"{v:,}")
    df_janela_display["renovaram"] = df_janela_display["renovaram"].apply(lambda v: f"{v:,}")
    df_janela_display["nao_renovaram"] = df_janela_display["nao_renovaram"].apply(lambda v: f"{v:,}")
    df_janela_display["taxa_renovacao"] = df_janela_display["taxa_renovacao"].apply(lambda v: f"{v:.2f}%")
    df_janela_display["churn_rate"] = df_janela_display["churn_rate"].apply(lambda v: f"{v:.2f}%")

    st.dataframe(
        df_janela_display.rename(columns={
            "janela": "Janela", "periodo": "Periodo", "total_contratos": "Contratos",
            "renovaram": "Renovaram", "nao_renovaram": "Nao Renovaram",
            "taxa_renovacao": "Taxa Renovacao", "churn_rate": "Churn"
        }),
        hide_index=True, use_container_width=True,
    )

    # Contexto
    melhor_pre = df_janela[df_janela["periodo"] == "PRE"]["taxa_renovacao"].max()
    pior_pre = df_janela[df_janela["periodo"] == "PRE"]["taxa_renovacao"].min()
    variacao_pre = round(melhor_pre - pior_pre, 1)

    st.markdown(f"""
    **Contexto:** A variacao natural entre as janelas PRE e de **{variacao_pre} p.p.**
    (de {pior_pre:.1f}% a {melhor_pre:.1f}%). O POS esta em **{taxa_pos:.1f}%** —
    {'acima' if taxa_pos > taxa_pre else 'abaixo' if taxa_pos < taxa_pre else 'igual a'}
    da media PRE ({taxa_pre:.1f}%).
    """)


# ═══════════════════════════════════════════════════════════════════
# TAB 2: CURVA DIARIA
# ═══════════════════════════════════════════════════════════════════
with tab_diario:
    st.markdown("### Curva Diaria de Renovacao")
    st.markdown("""
    Cada ponto e um dia. A linha vertical marca o dia da mudanca (15/mai).
    A media movel de 3 dias suaviza a volatilidade diaria.
    """)

    df_d = df_dia.sort_values("dia").copy()
    df_d["mm3"] = df_d["taxa_renovacao"].rolling(3, center=True, min_periods=1).mean()

    fig = go.Figure()

    # Pontos PRE
    pre_d = df_d[df_d["periodo"] == "PRE"]
    pos_d = df_d[df_d["periodo"] == "POS"]

    fig.add_trace(go.Scatter(
        x=pre_d["dia"], y=pre_d["taxa_renovacao"],
        mode="markers",
        marker=dict(size=8, color="#3498db", opacity=0.5),
        name="PRE (diario)",
    ))
    fig.add_trace(go.Scatter(
        x=pos_d["dia"], y=pos_d["taxa_renovacao"],
        mode="markers",
        marker=dict(size=10, color=veredicto_cor, opacity=0.7,
                    line=dict(width=1, color="white")),
        name="POS (diario)",
    ))

    # Media movel
    fig.add_trace(go.Scatter(
        x=df_d["dia"], y=df_d["mm3"],
        mode="lines",
        line=dict(width=3, color="#2c3e50"),
        name="Media movel (3 dias)",
    ))

    # Linha de corte
    fig.add_vline(
        x="2026-05-15", line_dash="dash", line_color="red", line_width=2,
    )
    fig.add_annotation(
        x="2026-05-15", y=df_d["taxa_renovacao"].max() + 2,
        text="Mudanca de adquirente",
        showarrow=True, arrowhead=2, arrowcolor="red",
        font=dict(size=12, color="red"),
    )

    # Media PRE
    fig.add_hline(
        y=taxa_pre, line_dash="dot", line_color="#3498db", line_width=1,
        annotation_text=f"Media PRE: {taxa_pre:.1f}%",
        annotation_position="bottom left",
        annotation_font=dict(size=10, color="#3498db"),
    )

    fig.update_layout(
        yaxis_title="Taxa de Renovacao (%)",
        xaxis_title="",
        height=450,
        legend=dict(orientation="h", y=1.1),
        yaxis=dict(range=[
            max(0, df_d["taxa_renovacao"].min() - 5),
            df_d["taxa_renovacao"].max() + 8
        ]),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Volume diario
    st.markdown("### Volume Diario de Contratos Vencendo")

    fig_vol = go.Figure()
    fig_vol.add_trace(go.Bar(
        x=pre_d["dia"], y=pre_d["total_contratos"],
        marker_color="#3498db", opacity=0.5, name="PRE",
    ))
    fig_vol.add_trace(go.Bar(
        x=pos_d["dia"], y=pos_d["total_contratos"],
        marker_color=veredicto_cor, opacity=0.7, name="POS",
    ))
    fig_vol.add_vline(x="2026-05-15", line_dash="dash", line_color="red", line_width=2)
    fig_vol.update_layout(
        yaxis_title="Contratos", height=300,
        legend=dict(orientation="h", y=1.1),
        barmode="stack",
    )
    st.plotly_chart(fig_vol, use_container_width=True)

    # Estatisticas descritivas
    st.markdown("### Estatisticas Descritivas")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**PRE (por dia)**")
        st.markdown(f"""
        | Metrica | Valor |
        |---|---|
        | Dias | {dias_pre} |
        | Media | {pre_d['taxa_renovacao'].mean():.1f}% |
        | Mediana | {pre_d['taxa_renovacao'].median():.1f}% |
        | Desvio padrao | {pre_d['taxa_renovacao'].std():.1f} p.p. |
        | Min | {pre_d['taxa_renovacao'].min():.1f}% |
        | Max | {pre_d['taxa_renovacao'].max():.1f}% |
        | Volume medio/dia | {pre_d['total_contratos'].mean():.0f} |
        """)

    with col2:
        st.markdown("**POS (por dia)**")
        st.markdown(f"""
        | Metrica | Valor |
        |---|---|
        | Dias | {dias_pos} |
        | Media | {pos_d['taxa_renovacao'].mean():.1f}% |
        | Mediana | {pos_d['taxa_renovacao'].median():.1f}% |
        | Desvio padrao | {pos_d['taxa_renovacao'].std():.1f} p.p. |
        | Min | {pos_d['taxa_renovacao'].min():.1f}% |
        | Max | {pos_d['taxa_renovacao'].max():.1f}% |
        | Volume medio/dia | {pos_d['total_contratos'].mean():.0f} |
        """)

    # Dia da semana
    st.markdown("### Efeito do Dia da Semana")
    st.caption("A taxa de renovacao varia por dia da semana? Se sim, precisamos controlar isso na comparacao.")

    df_d["dia_semana"] = df_d["dia"].dt.day_name()
    dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    dow_pt = {"Monday": "Seg", "Tuesday": "Ter", "Wednesday": "Qua", "Thursday": "Qui",
              "Friday": "Sex", "Saturday": "Sab", "Sunday": "Dom"}

    dow = df_d.groupby(["dia_semana", "periodo"]).agg(
        taxa_media=("taxa_renovacao", "mean"),
        volume_medio=("total_contratos", "mean"),
    ).reset_index()
    dow["dia_semana"] = pd.Categorical(dow["dia_semana"], categories=dow_order, ordered=True)
    dow = dow.sort_values("dia_semana")
    dow["dia_pt"] = dow["dia_semana"].map(dow_pt)

    fig_dow = px.bar(
        dow, x="dia_pt", y="taxa_media", color="periodo",
        barmode="group", text_auto=".1f",
        color_discrete_map={"PRE": "#3498db", "POS": veredicto_cor},
        labels={"dia_pt": "", "taxa_media": "Taxa Renovacao Media (%)", "periodo": ""},
    )
    fig_dow.update_layout(height=350, legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig_dow, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
# TAB 3: POR SEGMENTO
# ═══════════════════════════════════════════════════════════════════
with tab_segmentos:
    st.markdown("### Impacto por Segmento")
    st.markdown("""
    A mudanca de adquirente pode ter afetado alguns segmentos mais que outros.
    Abaixo comparamos PRE vs POS para cada combinacao de **duracao × ciclo**.
    """)

    # Calcular media PRE e POS por segmento
    seg_pre = df_det[df_det["janela"].str.contains("PRE")].groupby(["duracao", "ciclo"]).agg(
        n=("total_contratos", "sum"),
        renov=("renovaram", "sum"),
    ).reset_index()
    seg_pre["taxa_pre"] = round(100 * seg_pre["renov"] / seg_pre["n"], 2)

    seg_pos = df_det[df_det["janela"].str.contains("POS")].groupby(["duracao", "ciclo"]).agg(
        n=("total_contratos", "sum"),
        renov=("renovaram", "sum"),
    ).reset_index()
    seg_pos["taxa_pos"] = round(100 * seg_pos["renov"] / seg_pos["n"], 2)

    seg = seg_pre.merge(seg_pos, on=["duracao", "ciclo"], suffixes=("_pre", "_pos"))
    seg["delta"] = round(seg["taxa_pos"] - seg["taxa_pre"], 2)
    seg["label"] = seg["duracao"] + "m · " + seg["ciclo"]

    # Z-test por segmento
    def z_test(n1, x1, n2, x2):
        p1 = x1/n1 if n1 else 0
        p2 = x2/n2 if n2 else 0
        pp = (x1+x2)/(n1+n2) if (n1+n2) else 0
        se = np.sqrt(pp*(1-pp)*(1/n1+1/n2)) if n1 and n2 and pp > 0 and pp < 1 else 0
        z = (p2-p1)/se if se > 0 else 0
        p = 2*(1-stats.norm.cdf(abs(z)))
        return p

    seg["p_valor"] = seg.apply(
        lambda r: z_test(r["n_pre"], r["renov_pre"], r["n_pos"], r["renov_pos"]), axis=1
    )
    seg["sig"] = seg["p_valor"].apply(
        lambda p: "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "n.s."
    )

    # Grafico
    fig_seg = go.Figure()

    fig_seg.add_trace(go.Bar(
        x=seg["label"], y=seg["taxa_pre"],
        name="PRE (media 30 dias)",
        marker_color="#3498db", opacity=0.6,
        text=seg["taxa_pre"].apply(lambda v: f"{v:.1f}%"),
        textposition="outside", textfont=dict(size=12),
    ))
    fig_seg.add_trace(go.Bar(
        x=seg["label"], y=seg["taxa_pos"],
        name="POS (10 dias)",
        marker_color=[
            "#27ae60" if d > 0 else "#c0392b" if d < -1 else "#f39c12"
            for d in seg["delta"]
        ],
        text=seg.apply(
            lambda r: f'{r["taxa_pos"]:.1f}% ({r["delta"]:+.1f}pp {r["sig"]})', axis=1
        ),
        textposition="outside", textfont=dict(size=12),
    ))

    fig_seg.update_layout(
        barmode="group",
        yaxis_title="Taxa de Renovacao (%)",
        height=420,
        legend=dict(orientation="h", y=1.1),
        yaxis=dict(range=[0, max(seg["taxa_pos"].max(), seg["taxa_pre"].max()) + 8]),
    )
    st.plotly_chart(fig_seg, use_container_width=True)

    # Tabela detalhada
    st.markdown("### Detalhe por Segmento")

    seg_display = seg[["label", "n_pre", "taxa_pre", "n_pos", "taxa_pos", "delta", "p_valor", "sig"]].copy()
    seg_display.columns = ["Segmento", "N (PRE)", "Renovacao PRE", "N (POS)", "Renovacao POS",
                           "Δ (p.p.)", "p-valor", "Sig."]
    seg_display["N (PRE)"] = seg_display["N (PRE)"].apply(lambda v: f"{v:,}")
    seg_display["N (POS)"] = seg_display["N (POS)"].apply(lambda v: f"{v:,}")
    seg_display["Renovacao PRE"] = seg_display["Renovacao PRE"].apply(lambda v: f"{v:.1f}%")
    seg_display["Renovacao POS"] = seg_display["Renovacao POS"].apply(lambda v: f"{v:.1f}%")
    seg_display["Δ (p.p.)"] = seg_display["Δ (p.p.)"].apply(lambda v: f"{v:+.1f}")
    seg_display["p-valor"] = seg_display["p-valor"].apply(
        lambda v: f"{v:.4f}" if v >= 0.001 else "<0.001"
    )

    st.dataframe(seg_display, hide_index=True, use_container_width=True)

    st.caption("*** p<0.001 · ** p<0.01 · * p<0.05 · n.s. = nao significativo")

    # Insights por segmento
    st.markdown("---")
    st.markdown("### Leitura por Segmento")

    for _, r in seg.sort_values("delta", ascending=False).iterrows():
        if r["delta"] > 1 and r["sig"] != "n.s.":
            st.success(
                f"**{r['label']}:** renovacao subiu de {r['taxa_pre']:.1f}% para "
                f"{r['taxa_pos']:.1f}% (**{r['delta']:+.1f} p.p.**, {r['sig']}). "
                f"Sinal positivo — {int(r['n_pos']):,} contratos observados."
            )
        elif r["delta"] < -1 and r["sig"] != "n.s.":
            st.error(
                f"**{r['label']}:** renovacao caiu de {r['taxa_pre']:.1f}% para "
                f"{r['taxa_pos']:.1f}% (**{r['delta']:+.1f} p.p.**, {r['sig']}). "
                f"Atenção — monitorar nas proximas semanas."
            )
        else:
            st.info(
                f"**{r['label']}:** {r['taxa_pre']:.1f}% → {r['taxa_pos']:.1f}% "
                f"({r['delta']:+.1f} p.p., {r['sig']}). "
                f"Sem mudanca significativa."
            )


# ═══════════════════════════════════════════════════════════════════
# TAB 4: TESTE ESTATISTICO
# ═══════════════════════════════════════════════════════════════════
with tab_estatistica:
    st.markdown("### Teste de Significancia Estatistica")
    st.markdown("""
    Para saber se a diferenca observada e real ou apenas ruido,
    usamos um **z-test de proporcoes** (bicaudal).
    """)

    # Resultado do teste
    st.markdown("#### Teste Global: PRE vs POS")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        | Parametro | Valor |
        |---|---|
        | N (PRE) | {n_pre:,} |
        | Renovacao PRE | {taxa_pre:.2f}% |
        | N (POS) | {n_pos:,} |
        | Renovacao POS | {taxa_pos:.2f}% |
        | Diferenca | **{delta_global:+.2f} p.p.** |
        | z-statistic | {z_stat:.4f} |
        | **p-valor** | **{p_valor:.4f}** |
        """)

    with col2:
        # IC 95% da diferenca
        diff = p_pos - p_pre
        se_diff = np.sqrt(p_pre*(1-p_pre)/n_pre + p_pos*(1-p_pos)/n_pos) if n_pre and n_pos else 0
        ci_lo = round(100 * (diff - 1.96 * se_diff), 2)
        ci_hi = round(100 * (diff + 1.96 * se_diff), 2)

        st.markdown(f"""
        **Intervalo de Confianca 95%:**

        A diferenca real esta entre **{ci_lo:+.2f} p.p.** e **{ci_hi:+.2f} p.p.**
        com 95% de confianca.
        """)

        if ci_lo > 0:
            st.success("O IC nao inclui zero — a melhora e estatisticamente significativa.")
        elif ci_hi < 0:
            st.error("O IC nao inclui zero — a piora e estatisticamente significativa.")
        else:
            st.warning(
                "O IC inclui zero — nao podemos afirmar que houve mudanca real. "
                "Mais dias de observacao podem resolver."
            )

        # Grafico do IC
        fig_ic = go.Figure()
        fig_ic.add_trace(go.Scatter(
            x=[delta_global], y=["Global"],
            mode="markers",
            marker=dict(size=14, color=veredicto_cor),
            error_x=dict(
                type="data", symmetric=False,
                array=[ci_hi - delta_global],
                arrayminus=[delta_global - ci_lo],
                color="rgba(0,0,0,0.5)", thickness=3, width=10,
            ),
            showlegend=False,
        ))
        fig_ic.add_vline(x=0, line_dash="dash", line_color="gray")
        fig_ic.update_layout(
            title="IC 95% da diferenca (POS - PRE)",
            xaxis_title="Δ renovacao (p.p.)",
            height=150,
            margin=dict(l=10, r=10, t=40, b=20),
        )
        st.plotly_chart(fig_ic, use_container_width=True)

    # Power analysis
    st.markdown("---")
    st.markdown("#### Quantos dias precisamos pra conclusao?")

    st.markdown("""
    O poder estatistico depende do **tamanho do efeito** e do **volume de contratos**.
    Com o volume atual, estimamos quantos dias POS sao necessarios para detectar
    diferentes niveis de melhora.
    """)

    vol_dia_pos = pos_d["total_contratos"].mean() if len(pos_d) > 0 else 650
    vol_dia_pre = pre_d["total_contratos"].mean() if len(pre_d) > 0 else 650

    cenarios = []
    for delta_alvo in [1, 2, 3, 5]:
        # N necessario por braço (z-test, alpha=0.05, power=0.80)
        p1_est = p_pre
        p2_est = p_pre + delta_alvo / 100
        p_avg = (p1_est + p2_est) / 2
        n_por_braco = int(
            ((1.96 + 0.84) ** 2 * 2 * p_avg * (1 - p_avg)) / ((delta_alvo / 100) ** 2)
        ) if delta_alvo > 0 else 999999
        dias_necessarios = max(1, int(np.ceil(n_por_braco / vol_dia_pos)))

        cenarios.append({
            "Δ a detectar": f"{delta_alvo} p.p.",
            "N necessario (POS)": f"{n_por_braco:,}",
            "Dias POS necessarios": f"{dias_necessarios}",
            "Dias ja observados": f"{dias_pos}",
            "Status": "Suficiente" if dias_pos >= dias_necessarios else f"Faltam {dias_necessarios - dias_pos} dias",
        })

    st.dataframe(pd.DataFrame(cenarios), hide_index=True, use_container_width=True)

    st.caption(
        f"Baseado em volume medio de {vol_dia_pos:.0f} contratos/dia no POS. "
        f"Alpha=0.05, Power=0.80, z-test bicaudal."
    )

    st.markdown("---")
    st.markdown("#### Recomendacao")

    if dias_pos < 20:
        st.info(f"""
        **Ainda cedo para conclusao definitiva.** Com {dias_pos} dias, so conseguimos
        detectar efeitos maiores que ~3 p.p. com confianca.

        **Proximo passo:** re-rodar a query `impacto_adquirente.sql` em mais
        {max(10, 20 - dias_pos)} dias e atualizar os CSVs. A pagina atualiza automaticamente.
        """)
    else:
        if p_valor < 0.05:
            st.success(f"""
            **Conclusao possivel.** Com {dias_pos} dias e p={p_valor:.4f},
            {'a melhora' if delta_global > 0 else 'a piora'} de {abs(delta_global):.1f} p.p.
            e estatisticamente significativa.
            """)
        else:
            st.warning(f"""
            **Sem efeito detectavel.** Com {dias_pos} dias, nao ha diferenca
            significativa (p={p_valor:.3f}). Ou o efeito e muito pequeno (<1 p.p.)
            ou nao houve impacto real na renovacao.
            """)
