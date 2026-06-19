"""
Pagina 17 — Win-back Voluntario
================================
Quem churna e volta? Em quanto tempo? Qual o perfil?
Mostra que ~56% dos churners voltam em ate 2 anos — e 45% no 1o mes.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(page_title="Win-back Voluntario", page_icon="🔄", layout="wide")
st.title("🔄 Win-back Voluntario")
st.caption("Dos pacientes que saem, quantos voltam por conta propria — e em quanto tempo")


# ═══════════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════════
@st.cache_data
def load_detalhado():
    return pd.read_csv("results/winback_voluntario.csv")

@st.cache_data
def load_resumo():
    return pd.read_csv("results/winback_resumo.csv")


try:
    df = load_detalhado()
    df_res = load_resumo()
except FileNotFoundError as e:
    st.error(f"CSV nao encontrado: {e}")
    st.stop()

total_churners = len(df)
voltaram = (df["retorno_status"] == "voltou").sum()
nao_voltaram = total_churners - voltaram
taxa_retorno = round(100 * voltaram / total_churners, 1)

FAIXA_ORDER = [
    "01_ate_30_dias", "02_31_a_60_dias", "03_61_a_90_dias",
    "04_91_a_180_dias", "05_181_a_365_dias", "06_366_a_730_dias", "nao_voltou"
]
FAIXA_LABELS = {
    "01_ate_30_dias": "Ate 30 dias",
    "02_31_a_60_dias": "31-60 dias",
    "03_61_a_90_dias": "61-90 dias",
    "04_91_a_180_dias": "3-6 meses",
    "05_181_a_365_dias": "6m-1 ano",
    "06_366_a_730_dias": "1-2 anos",
    "nao_voltou": "Nao voltou",
}
FAIXA_CORES = {
    "01_ate_30_dias": "#27ae60",
    "02_31_a_60_dias": "#2ecc71",
    "03_61_a_90_dias": "#82e0aa",
    "04_91_a_180_dias": "#f39c12",
    "05_181_a_365_dias": "#e67e22",
    "06_366_a_730_dias": "#d35400",
    "nao_voltou": "#c0392b",
}


# ═══════════════════════════════════════════════════════════════════
# KPIs
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Contratos que churaram", f"{total_churners:,}")
k2.metric("Voltaram (ate 2 anos)", f"{voltaram:,}",
          delta=f"{taxa_retorno}%", delta_color="normal")
k3.metric("Nao voltaram", f"{nao_voltaram:,}",
          delta=f"{100 - taxa_retorno:.1f}% (perda definitiva)", delta_color="inverse")

# Mediana de retorno
dias_retorno = df[df["dias_ate_retorno"].notna()]["dias_ate_retorno"]
if len(dias_retorno) > 0:
    k4.metric("Mediana de retorno", f"{int(dias_retorno.median())} dias",
              help=f"Media: {dias_retorno.mean():.0f} dias")


# ═══════════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════════
tab_visao, tab_curva, tab_perfil, tab_detalhe, tab_insights = st.tabs([
    "📊 Visao Geral",
    "📈 Curva de Retorno",
    "👤 Perfil de quem volta",
    "🔍 Por Segmento",
    "💡 Insights",
])


# ═══════════════════════════════════════════════════════════════════
# TAB 1: VISAO GERAL
# ═══════════════════════════════════════════════════════════════════
with tab_visao:
    st.markdown("### De cada 100 churners, quantos voltam?")

    col1, col2 = st.columns([2, 1])

    with col1:
        # Distribuicao por faixa
        faixa_counts = df["faixa_retorno"].value_counts().reindex(FAIXA_ORDER, fill_value=0)

        fig = go.Figure(data=[go.Pie(
            labels=[FAIXA_LABELS.get(f, f) for f in faixa_counts.index],
            values=faixa_counts.values,
            hole=0.5,
            marker_colors=[FAIXA_CORES.get(f, "#95a5a6") for f in faixa_counts.index],
            textinfo="label+percent",
            textfont=dict(size=12),
            sort=False,
        )])
        fig.update_layout(
            title="Distribuicao: quando voltam (ou nao)",
            height=450, showlegend=False,
            annotations=[dict(
                text=f"{taxa_retorno}%<br>voltam",
                x=0.5, y=0.5, font_size=20, showarrow=False,
            )],
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("#### Por faixa de tempo")
        for faixa in FAIXA_ORDER:
            n = int(faixa_counts.get(faixa, 0))
            pct = round(100 * n / total_churners, 1)
            label = FAIXA_LABELS.get(faixa, faixa)
            cor = "🟢" if "ate_30" in faixa else "🟡" if "60" in faixa or "90" in faixa else "🟠" if "180" in faixa or "365" in faixa else "🔴" if "730" in faixa else "⚫"
            st.markdown(f"{cor} **{label}**: {n:,} ({pct}%)")

    # Barras
    st.markdown("---")
    faixa_sem_nao_voltou = faixa_counts.drop("nao_voltou", errors="ignore")

    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        x=[FAIXA_LABELS.get(f, f) for f in faixa_sem_nao_voltou.index],
        y=faixa_sem_nao_voltou.values,
        marker_color=[FAIXA_CORES.get(f, "#3498db") for f in faixa_sem_nao_voltou.index],
        text=[f"{v:,}<br>({100*v/total_churners:.1f}%)" for v in faixa_sem_nao_voltou.values],
        textposition="outside", textfont=dict(size=12),
    ))
    fig_bar.update_layout(
        title="Volume de retorno por faixa de tempo",
        yaxis_title="Churners que voltaram", height=400,
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown(f"""
    **O dado central:** dos {total_churners:,} contratos que churaram,
    **{voltaram:,} ({taxa_retorno}%) voltaram** em ate 2 anos.
    E a grande maioria — **{int(faixa_counts.get('01_ate_30_dias', 0)):,}
    ({100*faixa_counts.get('01_ate_30_dias', 0)/total_churners:.1f}%)** — voltou
    nos primeiros 30 dias, o que sugere renovacao tardia ou recontratacao rapida.
    """)


# ═══════════════════════════════════════════════════════════════════
# TAB 2: CURVA DE RETORNO
# ═══════════════════════════════════════════════════════════════════
with tab_curva:
    st.markdown("### Curva de Retorno Acumulado")
    st.markdown("""
    Mostra o **% acumulado** de churners que voltam ao longo do tempo.
    Quanto mais rapido a curva sobe, mais pacientes retornam cedo.
    """)

    dur_sel = st.radio("Duracao:", ["Todos", "6", "12"],
                       format_func=lambda x: "Todos" if x == "Todos" else f"{x} meses",
                       horizontal=True, key="curva_dur")

    fig_curva = go.Figure()

    if dur_sel == "Todos":
        # Curva geral
        pontos = [0]
        for faixa in FAIXA_ORDER[:-1]:  # sem "nao_voltou"
            n = faixa_counts.get(faixa, 0)
            pontos.append(pontos[-1] + n)
        pcts = [round(100 * p / total_churners, 1) for p in pontos]
        x_labels = ["Dia 0"] + [FAIXA_LABELS[f] for f in FAIXA_ORDER[:-1]]

        fig_curva.add_trace(go.Scatter(
            x=x_labels, y=pcts,
            mode="lines+markers+text",
            line=dict(width=3, color="#2c3e50"),
            marker=dict(size=10),
            text=[f"{p}%" for p in pcts],
            textposition="top center",
            fill="tozeroy", fillcolor="rgba(39, 174, 96, 0.1)",
        ))
    else:
        # Curvas por ciclo dentro da duracao selecionada
        for _, row in df_res[df_res["duracao"] == dur_sel].iterrows():
            ciclo = row["ciclo"]
            pcts = [0, row["pct_acum_30d"], row["pct_acum_60d"], row["pct_acum_90d"],
                    row["pct_acum_180d"], row["pct_acum_365d"], row["pct_acum_730d"]]
            x_labels = ["Dia 0", "30d", "60d", "90d", "6m", "1 ano", "2 anos"]

            fig_curva.add_trace(go.Scatter(
                x=x_labels, y=pcts,
                mode="lines+markers+text",
                name=f"{ciclo} ({int(row['total_churners']):,})",
                marker=dict(size=8),
                text=[f"{p}%" for p in pcts],
                textposition="top center",
            ))

    fig_curva.update_layout(
        title="% acumulado de churners que voltam",
        yaxis_title="% dos churners",
        yaxis=dict(range=[0, 70]),
        height=450,
        legend=dict(orientation="h", y=-0.15),
    )
    st.plotly_chart(fig_curva, use_container_width=True)

    # Tabela do resumo
    st.markdown("### Detalhamento por duracao × ciclo")
    df_res_display = df_res.copy()
    df_res_display["total_churners"] = df_res_display["total_churners"].apply(lambda v: f"{int(v):,}")
    df_res_display["voltaram_total"] = df_res_display["voltaram_total"].apply(lambda v: f"{int(v):,}")
    df_res_display["dias_retorno_medio"] = df_res_display["dias_retorno_medio"].apply(lambda v: f"{int(v)} dias")

    st.dataframe(
        df_res_display[[
            "duracao", "ciclo", "total_churners", "voltaram_total", "taxa_retorno_total",
            "dias_retorno_medio", "pct_acum_30d", "pct_acum_90d", "pct_acum_180d", "pct_acum_365d", "pct_acum_730d"
        ]].rename(columns={
            "duracao": "Dur.", "ciclo": "Ciclo", "total_churners": "Churners",
            "voltaram_total": "Voltaram", "taxa_retorno_total": "Retorno (%)",
            "dias_retorno_medio": "Media retorno",
            "pct_acum_30d": "30d", "pct_acum_90d": "90d",
            "pct_acum_180d": "6m", "pct_acum_365d": "1 ano", "pct_acum_730d": "2 anos",
        }),
        hide_index=True, use_container_width=True,
    )


# ═══════════════════════════════════════════════════════════════════
# TAB 3: PERFIL DE QUEM VOLTA
# ═══════════════════════════════════════════════════════════════════
with tab_perfil:
    st.markdown("### Quem volta vs quem nao volta")

    for var, label in [("ciclo", "Ciclo"), ("duracao", "Duracao"), ("tipo_venda", "Tipo de venda"), ("canal", "Canal")]:
        grp = df.groupby([var, "retorno_status"]).size().reset_index(name="n")
        grp_total = df.groupby(var).size().reset_index(name="total")
        grp = grp.merge(grp_total, on=var)
        grp["pct"] = round(100 * grp["n"] / grp["total"], 1)

        # Filtrar só "voltou"
        voltou = grp[grp["retorno_status"] == "voltou"].sort_values("pct", ascending=True)

        if len(voltou) == 0:
            continue

        fig_p = go.Figure()
        fig_p.add_trace(go.Bar(
            y=voltou[var].astype(str),
            x=voltou["pct"],
            orientation="h",
            marker_color="#27ae60",
            text=voltou.apply(lambda r: f'{r["pct"]}% ({int(r["n"]):,})', axis=1),
            textposition="outside",
        ))
        fig_p.add_vline(x=taxa_retorno, line_dash="dash", line_color="gray",
                        annotation_text=f"Media: {taxa_retorno}%")
        fig_p.update_layout(
            title=f"Taxa de retorno por {label}",
            xaxis_title="% que voltou", height=max(250, len(voltou) * 40 + 80),
            margin=dict(l=20, r=100), yaxis=dict(automargin=True),
            xaxis=dict(range=[0, max(voltou["pct"]) + 10]),
        )
        st.plotly_chart(fig_p, use_container_width=True)

    # Tempo de retorno por ciclo
    st.markdown("---")
    st.markdown("### Tempo de retorno: 1o contrato vs 2o+")

    voltou_df = df[df["dias_ate_retorno"].notna()].copy()
    if len(voltou_df) > 0:
        fig_hist = go.Figure()
        for ciclo, cor in [("1o", "#e74c3c"), ("2o+", "#3498db")]:
            sub = voltou_df[voltou_df["ciclo"] == ciclo]["dias_ate_retorno"]
            if len(sub) > 0:
                fig_hist.add_trace(go.Histogram(
                    x=sub, nbinsx=50, name=ciclo,
                    marker_color=cor, opacity=0.6,
                ))
        fig_hist.update_layout(
            barmode="overlay",
            title="Distribuicao do tempo de retorno (dias)",
            xaxis_title="Dias ate retorno", yaxis_title="Contratos",
            height=380, legend=dict(orientation="h", y=1.1),
        )
        st.plotly_chart(fig_hist, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
# TAB 4: POR SEGMENTO
# ═══════════════════════════════════════════════════════════════════
with tab_detalhe:
    st.markdown("### Retorno por segmento detalhado")

    st.dataframe(
        df_res.rename(columns={
            "duracao": "Duracao", "ciclo": "Ciclo",
            "total_churners": "Churners", "voltaram_total": "Voltaram",
            "taxa_retorno_total": "Retorno (%)",
            "ret_ate_30d": "Ate 30d", "ret_31_60d": "31-60d",
            "ret_61_90d": "61-90d", "ret_91_180d": "3-6m",
            "ret_181_365d": "6m-1a", "ret_366_730d": "1-2a",
            "dias_retorno_medio": "Media (dias)",
        }),
        hide_index=True, use_container_width=True,
    )

    # Heatmap: faixa × segmento
    st.markdown("### Heatmap: % acumulado por segmento × tempo")

    heat_data = []
    for _, row in df_res.iterrows():
        seg = f"{row['duracao']}m {row['ciclo']}"
        for col, label in [
            ("pct_acum_30d", "30d"), ("pct_acum_60d", "60d"), ("pct_acum_90d", "90d"),
            ("pct_acum_180d", "6m"), ("pct_acum_365d", "1 ano"), ("pct_acum_730d", "2 anos"),
        ]:
            heat_data.append({"segmento": seg, "tempo": label, "pct": row[col]})

    heat_df = pd.DataFrame(heat_data)
    heat_pivot = heat_df.pivot(index="segmento", columns="tempo", values="pct")
    heat_pivot = heat_pivot[["30d", "60d", "90d", "6m", "1 ano", "2 anos"]]

    fig_heat = go.Figure(data=go.Heatmap(
        z=heat_pivot.values,
        x=heat_pivot.columns.tolist(),
        y=heat_pivot.index.tolist(),
        colorscale=[[0, "#fdedec"], [0.5, "#f9e79f"], [1, "#27ae60"]],
        text=[[f"{v:.1f}%" for v in row] for row in heat_pivot.values],
        texttemplate="%{text}",
        textfont=dict(size=14),
        colorbar=dict(title="% retorno"),
    ))
    fig_heat.update_layout(
        title="% acumulado de retorno por segmento e tempo",
        height=300,
    )
    st.plotly_chart(fig_heat, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
# TAB 5: INSIGHTS
# ═══════════════════════════════════════════════════════════════════
with tab_insights:
    st.markdown("### O que o win-back voluntario revela")

    ate_30 = int(df[df["faixa_retorno"] == "01_ate_30_dias"].shape[0])
    entre_31_90 = int(df[df["faixa_retorno"].isin(["02_31_a_60_dias", "03_61_a_90_dias"])].shape[0])
    entre_91_365 = int(df[df["faixa_retorno"].isin(["04_91_a_180_dias", "05_181_a_365_dias"])].shape[0])
    entre_1_2a = int(df[df["faixa_retorno"] == "06_366_a_730_dias"].shape[0])

    st.markdown("---")
    st.markdown("#### 1. O churn nao e tao definitivo quanto parece")
    st.markdown(f"""
    Do churn de ~55% que medimos na base, **{taxa_retorno}% voltam em ate 2 anos**.
    O churn "real" (perda definitiva) e de **{100 - taxa_retorno:.1f}%** dos churners —
    ou ~{round((100 - taxa_retorno) * 55 / 100, 0):.0f}% da base total.
    """)

    st.markdown("---")
    st.markdown("#### 2. A janela de oportunidade")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Ate 30 dias", f"{ate_30:,}",
                delta=f"{100*ate_30/total_churners:.1f}%", delta_color="off")
    col2.metric("31-90 dias", f"{entre_31_90:,}",
                delta=f"{100*entre_31_90/total_churners:.1f}%", delta_color="off")
    col3.metric("3m - 1 ano", f"{entre_91_365:,}",
                delta=f"{100*entre_91_365/total_churners:.1f}%", delta_color="off")
    col4.metric("1-2 anos", f"{entre_1_2a:,}",
                delta=f"{100*entre_1_2a/total_churners:.1f}%", delta_color="off")

    st.markdown(f"""
    - **{ate_30:,} pacientes** voltam nos primeiros 30 dias — provavelmente renovacao
      tardia ou recontratacao imediata. Esses nao precisam de acao, ja voltam sozinhos.

    - **{entre_31_90:,} pacientes** voltam entre 1-3 meses — esses sao a janela de
      oportunidade pra win-back proativo. Uma regua de comunicacao (D+30, D+60, D+90)
      poderia **acelerar** o retorno e recuperar parte dos que demorariam mais.

    - **{entre_91_365:,} pacientes** voltam entre 3 meses e 1 ano — retorno espontaneo,
      dificil de influenciar mas mostra que o vinculo nao se perde completamente.

    - **{entre_1_2a:,} pacientes** voltam entre 1-2 anos — retorno de longo prazo.
    """)

    st.markdown("---")
    st.markdown("#### 3. O que isso muda na estrategia")
    st.markdown(f"""
    | Achado | Implicacao |
    |---|---|
    | 45% voltam em 30 dias | Parte do "churn" e temporario — monitorar antes de agir |
    | 5% voltam entre 1-3 meses | **Janela de win-back**: regua D+30/D+60/D+90 |
    | 56% voltam em 2 anos | O churn definitivo e ~44%, nao ~55% |
    | 12m 1o contrato tem maior retorno (58.9%) | Paciente de 1o contrato 12m volta mais que 6m |

    **A estrategia de win-back deve focar nos 31-90 dias pos-churn**,
    onde existe intencao de retorno mas o paciente precisa de um empurrao.
    Os primeiros 30 dias ja voltam sozinhos; depois de 90 dias a taxa cai muito.
    """)

    st.markdown("---")
    st.markdown("#### 4. Perguntas para o time")
    st.markdown(f"""
    1. Os {ate_30:,} que voltam em 30 dias — sao renovacoes tardias (pagamento atrasado)
       ou recontratacoes conscientes? Se for pagamento, e diferente de win-back.

    2. Existe alguma regua de comunicacao pos-churn hoje? Se nao, os {entre_31_90:,} que
       voltam entre 1-3 meses estao voltando **sem nenhuma acao** — com acao poderia ser mais.

    3. Qual o custo de aquisicao de um cliente novo vs reativar um churner?
       Se reativar e mais barato, o win-back proativo tem ROI claro.
    """)
