"""
Pagina 22 — Score com Plano Gratis: v4 vs v5 vs Target Estendido
==================================================================
Compara 3 definicoes de churn: v4 (exclui 30d), v5 (so exclui pago),
e target estendido (espera desfecho real pos-gratis).
Inclui analise de uso da rede durante o gratis.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="Score com Plano Gratis", page_icon="🎯", layout="wide")
st.title("🎯 Score com Plano Gratis: Comparacao de Targets")
st.caption("Se incluirmos o periodo gratis na definicao de churn, o modelo melhora?")


# ═══════════════════════════════════════════════════════════════════
# DADOS
# ═══════════════════════════════════════════════════════════════════

@st.cache_data
def load_faixas():
    return pd.read_csv("results/comparacao_v4_v5_pm_faixas.csv")

@st.cache_data
def load_contratos():
    return pd.read_csv("results/comparacao_v4_v5_pm_contratos.csv")

@st.cache_data
def load_uso_resumo():
    return pd.read_csv("results/gratis_uso_resumo.csv")

@st.cache_data
def load_uso_desfecho():
    return pd.read_csv("results/gratis_uso_por_desfecho.csv")

@st.cache_data
def load_uso_especialidades():
    return pd.read_csv("results/gratis_uso_especialidades.csv")

@st.cache_data
def load_uso_timeline():
    return pd.read_csv("results/gratis_uso_timeline.csv")


try:
    df_faixas = load_faixas()
    df_contr = load_contratos()
    df_uso_res = load_uso_resumo()
    df_uso_desf = load_uso_desfecho()
    df_uso_esp = load_uso_especialidades()
    df_uso_time = load_uso_timeline()
except FileNotFoundError as e:
    st.error(f"CSV nao encontrado: {e}")
    st.stop()


# ═══════════════════════════════════════════════════════════════════
# INTRO
# ═══════════════════════════════════════════════════════════════════

st.markdown("""
---
### A pergunta

Sabemos que ~30% dos churners migram pro plano gratis automaticamente apos falha
de pagamento, e ficam la ~2 meses. Uma proposta do Growth foi:

> *"Se a pessoa ainda esta no plano gratis, ela nao churnou de verdade.
> So deveriamos contar como churn depois que o periodo do gratis acabar
> e ela nao voltar pro pago."*

Essa definicao faz sentido? Testamos 3 targets com o mesmo modelo XGBoost
e as mesmas features pra comparar.
""")


# ═══════════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════════

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📐 Definicoes",
    "📊 AUC e Faixas",
    "🏥 Uso Durante o Gratis",
    "🔬 Features e Distribuicao",
    "💡 Veredicto",
])


# ═══════════════════════════════════════════════════════════════════
# TAB 1: DEFINICOES
# ═══════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("### As 3 definicoes de churn testadas")

    st.markdown("""
    | Target | Nome | Definicao | Logica |
    |---|---|---|---|
    | **v4** | Real 30d | Exclui **todos** que voltam em 30 dias | Janela fixa de 30d |
    | **v5** | So pago 30d | Exclui so quem voltou **pago** em 30d | Gratis continua como churn |
    | **Estendido** | Com plano gratis | Espera o desfecho real pos-gratis | Janela variavel (~2 meses) |
    """)

    st.markdown("---")
    st.markdown("### Como cada target trata os 4 destinos")

    # Dados de composicao
    churners_total = int(df_contr["churn_original"].sum())
    desfechos = df_contr[df_contr["churn_original"] == 1]["desfecho_final"].value_counts()

    st.markdown(f"Base: **{churners_total:,}** churners originais")

    # Tabela visual
    dados_desf = {
        "saiu_de_vez":        {"label": "Saiu de vez",              "v4": "CHURN",     "v5": "CHURN",     "ext": "CHURN"},
        "voltou_pago":        {"label": "Voltou pago (direto)",     "v4": "nao churn", "v5": "nao churn", "ext": "nao churn"},
        "gratis_saiu":        {"label": "Gratis → saiu de vez",     "v4": "nao churn*","v5": "CHURN",     "ext": "CHURN"},
        "gratis_voltou_pago": {"label": "Gratis → voltou pro pago", "v4": "nao churn*","v5": "CHURN",     "ext": "nao churn"},
    }

    rows_html = []
    for desf_key, info in dados_desf.items():
        n = int(desfechos.get(desf_key, 0))
        pct = round(100 * n / churners_total, 1) if churners_total > 0 else 0

        def cor_cell(val):
            if val == "CHURN":
                return f"🔴 {val}"
            return f"🟢 {val}"

        rows_html.append({
            "Destino": info["label"],
            "Contratos": f"{n:,}",
            "% Churners": f"{pct}%",
            "v4": cor_cell(info["v4"]),
            "v5": cor_cell(info["v5"]),
            "Estendido": cor_cell(info["ext"]),
        })

    st.dataframe(pd.DataFrame(rows_html), hide_index=True, use_container_width=True)

    st.markdown("""
    *\\*v4 usa janela fixa de 30 dias. Como a migracao pro gratis acontece em ~17 dias,
    a maioria cai dentro da janela e e excluida do churn.*

    ---
    ### A diferenca-chave entre os 3

    O **unico grupo** onde v4 e o target estendido divergem e o
    **gratis → saiu de vez** (~41% dos churners):

    - **v4** exclui esse grupo (porque voltou em 30d, mesmo que pro gratis)
    - **Estendido** inclui como churn (porque no fim saiu de vez)
    - A questao e: as features de **perfil** conseguem prever quem vai sair apos o gratis?
    """)

    # Taxas de churn
    st.markdown("---")
    st.markdown("### Taxa de churn por definicao")

    total_base = len(df_contr)
    metrics = [
        ("Original", df_contr["churn_original"].sum(), "#95a5a6"),
        ("v5 (so pago 30d)", df_contr["churn_v5"].sum(), "#f39c12"),
        ("Estendido (pos-gratis)", df_contr["churn_pm"].sum(), "#3498db"),
        ("v4 (todos 30d)", df_contr["churn_v4"].sum(), "#27ae60"),
    ]

    fig_rates = go.Figure()
    for label, total_churn, cor in metrics:
        rate = round(100 * total_churn / total_base, 1)
        fig_rates.add_trace(go.Bar(
            x=[label], y=[rate],
            marker_color=cor,
            text=f"{rate}%<br>({int(total_churn):,})",
            textposition="outside",
            textfont=dict(size=13),
            showlegend=False,
        ))
    fig_rates.update_layout(
        title="Taxa de churn por definicao de target",
        yaxis=dict(title="Churn (%)", range=[0, 65]),
        height=400,
    )
    st.plotly_chart(fig_rates, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
# TAB 2: AUC E FAIXAS
# ═══════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("### Resultado do XGBoost: AUC 5-fold CV")

    # AUC comparativo
    auc_data = {
        "Original": 0.5901,
        "v5 (so pago 30d)": 0.6023,
        "Estendido (pos-gratis)": 0.6305,
        "v4 (todos 30d)": 0.6353,
    }
    cores_auc = ["#95a5a6", "#f39c12", "#3498db", "#27ae60"]

    fig_auc = go.Figure()
    fig_auc.add_trace(go.Bar(
        x=list(auc_data.keys()),
        y=list(auc_data.values()),
        marker_color=cores_auc,
        text=[f"{v:.4f}" for v in auc_data.values()],
        textposition="outside",
        textfont=dict(size=14),
    ))
    fig_auc.add_shape(type="line", x0=-0.5, x1=3.5, y0=0.6353, y1=0.6353,
                      line=dict(dash="dot", color="green", width=1))
    fig_auc.update_layout(
        title="AUC por definicao de target (mesmo modelo, mesmas features)",
        yaxis=dict(title="AUC", range=[0.55, 0.68]),
        height=420,
    )
    st.plotly_chart(fig_auc, use_container_width=True)

    col_a1, col_a2, col_a3 = st.columns(3)
    col_a1.metric("v4 (melhor)", "0.6353", help="Target: exclui todos que voltam em 30d")
    col_a2.metric("Estendido", "0.6305", delta="-0.0048 vs v4", delta_color="inverse")
    col_a3.metric("v5", "0.6023", delta="-0.0330 vs v4", delta_color="inverse")

    st.markdown("""
    > O target estendido fica **muito proximo do v4** em AUC (diferenca de apenas 0.005).
    > Mas o v4 ainda vence — e com a vantagem de nao precisar esperar 2 meses.
    """)

    # Faixas
    st.markdown("---")
    layout_sel = st.radio(
        "Layout de faixas:", ["5 faixas", "7 faixas"],
        horizontal=True, key="layout_faixas"
    )
    layout_key = layout_sel.replace(" ", "_")

    df_f = df_faixas[df_faixas["layout"] == layout_key].copy()

    CORES = {
        "CRITICO": "#8b0000", "MUITO ALTO": "#d62728", "ALTO": "#ff7f0e",
        "MEDIO": "#ffbb33", "BAIXO": "#2ca02c", "MUITO BAIXO": "#1f77b4", "SEGURO": "#0d3b8b",
    }

    # Grafico por target
    for nome, col_n, col_cr, titulo, cor_linha in [
        ("v4", "contratos_v4", "churn_rate_v4", "Score v4 (exclui todos 30d)", "#27ae60"),
        ("Estendido", "contratos_pm", "churn_rate_pm", "Score Estendido (pos-gratis)", "#3498db"),
        ("v5", "contratos_v5", "churn_rate_v5", "Score v5 (so pago 30d)", "#f39c12"),
    ]:
        fig = go.Figure()

        fig.add_trace(go.Bar(
            x=df_f["faixa"], y=df_f[col_n],
            name="Contratos",
            marker_color=[CORES.get(f, "gray") for f in df_f["faixa"]],
            opacity=0.4,
            text=df_f.apply(
                lambda r: f'{int(r[col_n]):,}\n({round(100*r[col_n]/df_f[col_n].sum(),1)}%)',
                axis=1),
            textposition="outside", textfont=dict(size=10),
        ))

        fig.add_trace(go.Scatter(
            x=df_f["faixa"], y=df_f[col_cr],
            name="Churn (%)", mode="lines+markers+text",
            marker=dict(size=12,
                        color=[CORES.get(f, "gray") for f in df_f["faixa"]],
                        line=dict(width=2, color="white")),
            line=dict(width=3, color="gray", dash="dot"),
            yaxis="y2",
            text=df_f[col_cr].apply(lambda x: f"{x}%"),
            textposition="top center",
            textfont=dict(size=13, color="crimson"),
        ))

        rates_valid = df_f.loc[df_f[col_n] >= 10, col_cr]
        spread = round(rates_valid.max() - rates_valid.min(), 1) if len(rates_valid) >= 2 else 0

        fig.update_layout(
            title=f"{titulo} — {layout_sel} — Spread: {spread} p.p.",
            yaxis=dict(title="Contratos"),
            yaxis2=dict(title="Churn (%)", overlaying="y", side="right", range=[0, 110]),
            legend=dict(orientation="h", y=1.12),
            height=450,
        )
        st.plotly_chart(fig, use_container_width=True)

    # Tabela comparativa
    st.markdown("---")
    st.markdown("#### Tabela comparativa: churn rate por faixa")

    df_tab = df_f[["faixa", "contratos_v4", "churn_rate_v4",
                    "contratos_pm", "churn_rate_pm",
                    "contratos_v5", "churn_rate_v5"]].copy()
    df_tab.columns = [
        "Faixa", "n (v4)", "Churn v4 (%)",
        "n (Estendido)", "Churn Estendido (%)",
        "n (v5)", "Churn v5 (%)",
    ]
    st.dataframe(df_tab, hide_index=True, use_container_width=True)

    # Spreads
    st.markdown("#### Spread por target")
    spreads = {}
    for nome, col_n, col_cr in [
        ("v4", "contratos_v4", "churn_rate_v4"),
        ("Estendido", "contratos_pm", "churn_rate_pm"),
        ("v5", "contratos_v5", "churn_rate_v5"),
    ]:
        rates = df_f.loc[df_f[col_n] >= 10, col_cr]
        spreads[nome] = round(rates.max() - rates.min(), 1) if len(rates) >= 2 else 0

    cs1, cs2, cs3 = st.columns(3)
    cs1.metric("Spread v4", f"{spreads['v4']} p.p.")
    cs2.metric("Spread Estendido", f"{spreads['Estendido']} p.p.",
               delta=f"{spreads['Estendido'] - spreads['v4']:+.1f} vs v4", delta_color="inverse" if spreads['Estendido'] < spreads['v4'] else "normal")
    cs3.metric("Spread v5", f"{spreads['v5']} p.p.",
               delta=f"{spreads['v5'] - spreads['v4']:+.1f} vs v4", delta_color="inverse" if spreads['v5'] < spreads['v4'] else "normal")


# ═══════════════════════════════════════════════════════════════════
# TAB 3: USO DURANTE O GRATIS
# ═══════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("### Os 30% que migram pro gratis usam a rede?")

    st.markdown("""
    Se o plano gratis fosse uma ferramenta de retencao, esperariamos que
    os pacientes usassem a rede durante esse periodo. Investigamos.
    """)

    # KPIs resumo
    total_gratis = int(df_uso_res.iloc[0]["total_migraram_gratis"])
    usaram = int(df_uso_res.iloc[0]["usaram_rede"])
    pct_usaram = float(df_uso_res.iloc[0]["pct_usaram"])
    pct_nao = float(df_uso_res.iloc[0]["pct_nao_usaram"])

    st.markdown("---")
    st.markdown("#### Resultado: a grande maioria nao usa nada")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Migraram pro gratis", f"{total_gratis:,}")
    k2.metric("Usaram a rede", f"{usaram:,}", delta=f"{pct_usaram}%", delta_color="off")
    k3.metric("Nao usaram nada", f"{total_gratis - usaram:,}", delta=f"{pct_nao}%", delta_color="inverse")
    k4.metric("Media itens (quem usou)", f"{df_uso_res.iloc[0]['media_itens']:.1f}")

    # Donut uso vs nao uso
    fig_uso = go.Figure(data=[go.Pie(
        labels=["Nao usaram a rede", "Usaram a rede"],
        values=[total_gratis - usaram, usaram],
        hole=0.55,
        marker_colors=["#e74c3c", "#27ae60"],
        textinfo="label+percent",
        textfont=dict(size=13),
    )])
    fig_uso.update_layout(
        title=f"Uso da rede durante o plano gratis ({total_gratis:,} contratos)",
        height=380, showlegend=False,
        annotations=[dict(text=f"94%<br>sem uso", x=0.5, y=0.5, font_size=16, showarrow=False)],
    )
    st.plotly_chart(fig_uso, use_container_width=True)

    # Por desfecho
    st.markdown("---")
    st.markdown("#### Quem usa a rede durante o gratis volta mais pro pago?")

    row_saiu = df_uso_desf[df_uso_desf["desfecho"] == "saiu_de_vez"].iloc[0]
    row_voltou = df_uso_desf[df_uso_desf["desfecho"] == "voltou_pago"].iloc[0]

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### Saiu de vez")
        st.metric("Contratos", f"{int(row_saiu['contratos']):,}")
        st.metric("Usaram rede", f"{int(row_saiu['usaram_rede']):,}",
                  delta=f"{row_saiu['pct_usaram']}%", delta_color="off")
        st.metric("Media itens (quem usou)", f"{row_saiu['media_itens_quem_usou']:.1f}")

    with col2:
        st.markdown("##### Voltou pro pago")
        st.metric("Contratos", f"{int(row_voltou['contratos']):,}")
        st.metric("Usaram rede", f"{int(row_voltou['usaram_rede']):,}",
                  delta=f"{row_voltou['pct_usaram']}%", delta_color="normal")
        st.metric("Media itens (quem usou)", f"{row_voltou['media_itens_quem_usou']:.1f}")

    # Grafico comparativo
    fig_desf = go.Figure()
    categorias = ["% usaram rede", "Media itens", "Media consultas", "Media especialidades", "Media dias com uso"]
    vals_saiu = [row_saiu["pct_usaram"], row_saiu["media_itens_quem_usou"],
                 row_saiu["media_consultas"], row_saiu["media_especialidades"],
                 row_saiu["media_dias_com_uso"]]
    vals_voltou = [row_voltou["pct_usaram"], row_voltou["media_itens_quem_usou"],
                   row_voltou["media_consultas"], row_voltou["media_especialidades"],
                   row_voltou["media_dias_com_uso"]]

    fig_desf.add_trace(go.Bar(
        x=categorias, y=vals_saiu, name="Saiu de vez",
        marker_color="#e74c3c", opacity=0.7,
        text=[f"{v:.1f}" for v in vals_saiu], textposition="outside",
    ))
    fig_desf.add_trace(go.Bar(
        x=categorias, y=vals_voltou, name="Voltou pro pago",
        marker_color="#27ae60", opacity=0.7,
        text=[f"{v:.1f}" for v in vals_voltou], textposition="outside",
    ))
    fig_desf.update_layout(
        title="Uso durante o gratis: quem saiu vs quem voltou",
        barmode="group", height=420,
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_desf, use_container_width=True)

    st.markdown(f"""
    **Insight:** quem voltou pro pago usou a rede **3.5x mais** ({row_voltou['pct_usaram']}%
    vs {row_saiu['pct_usaram']}%) e com o dobro de itens ({row_voltou['media_itens_quem_usou']:.1f}
    vs {row_saiu['media_itens_quem_usou']:.1f}). O uso durante o gratis e **preditor de retorno**,
    mas nao e captavel pelo score (acontece depois do churn).
    """)

    # Especialidades
    st.markdown("---")
    st.markdown("#### Especialidades mais usadas durante o gratis")

    desf_esp_sel = st.radio("Desfecho:", ["voltou_pago", "saiu_de_vez"],
                            horizontal=True, key="esp_desfecho",
                            format_func=lambda x: "Voltou pro pago" if x == "voltou_pago" else "Saiu de vez")

    df_esp_sel = df_uso_esp[
        (df_uso_esp["desfecho"] == desf_esp_sel) &
        (df_uso_esp["especialidade"].notna()) &
        (df_uso_esp["especialidade"] != "")
    ].nlargest(12, "atendimentos")

    if len(df_esp_sel) > 0:
        fig_esp = go.Figure()
        fig_esp.add_trace(go.Bar(
            y=df_esp_sel["especialidade"],
            x=df_esp_sel["atendimentos"],
            orientation="h",
            marker_color="#3498db",
            text=[f"{int(a):,} ({int(p)} pac.)" for a, p in
                  zip(df_esp_sel["atendimentos"], df_esp_sel["pacientes_distintos"])],
            textposition="outside",
        ))
        fig_esp.update_layout(
            title=f"Top 12 especialidades — {desf_esp_sel.replace('_', ' ')}",
            xaxis_title="Atendimentos",
            yaxis=dict(autorange="reversed"),
            height=450,
        )
        st.plotly_chart(fig_esp, use_container_width=True)

    # Timeline
    st.markdown("---")
    st.markdown("#### Timeline: quando usam durante o gratis")

    ordem_periodo = ["semana_1", "semana_2", "semana_3", "semana_4",
                     "semana_5_6", "semana_7_8", "apos_8_semanas"]
    labels_periodo = ["Sem 1", "Sem 2", "Sem 3", "Sem 4", "Sem 5-6", "Sem 7-8", "8+ sem"]

    fig_time = go.Figure()
    for desf, cor, nome in [
        ("saiu_de_vez", "#e74c3c", "Saiu de vez"),
        ("voltou_pago", "#27ae60", "Voltou pro pago"),
    ]:
        df_t = df_uso_time[df_uso_time["desfecho"] == desf].copy()
        df_t["periodo"] = pd.Categorical(df_t["periodo"], categories=ordem_periodo, ordered=True)
        df_t = df_t.sort_values("periodo")

        fig_time.add_trace(go.Scatter(
            x=labels_periodo[:len(df_t)],
            y=df_t["atendimentos"].values,
            name=nome, mode="lines+markers+text",
            marker=dict(size=10, color=cor),
            line=dict(width=3, color=cor),
            text=[f"{int(v):,}" for v in df_t["atendimentos"].values],
            textposition="top center",
        ))

    fig_time.update_layout(
        title="Atendimentos por semana durante o gratis",
        xaxis_title="Semana desde inicio do gratis",
        yaxis_title="Atendimentos",
        height=420,
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_time, use_container_width=True)

    st.markdown("""
    **Quem volta pro pago** acelera o uso ao longo do tempo — o pico e nas semanas 7-8.
    **Quem sai** tem uso mais baixo e estavel. O uso crescente e sinal de reconversao.
    """)


# ═══════════════════════════════════════════════════════════════════
# TAB 4: FEATURES E DISTRIBUICAO
# ═══════════════════════════════════════════════════════════════════
with tab4:
    st.markdown("### Por que o v4 funciona melhor?")

    st.markdown("""
    Dois fatores explicam a superioridade do v4:
    **distribuicao nas faixas** e **alinhamento entre features e target**.
    """)

    # Distribuicao nas faixas
    st.markdown("---")
    st.markdown("#### Distribuicao de contratos por faixa (5 faixas)")

    df_5 = df_faixas[df_faixas["layout"] == "5_faixas"].copy()
    total_v4 = df_5["contratos_v4"].sum()
    total_pm = df_5["contratos_pm"].sum()
    total_v5 = df_5["contratos_v5"].sum()

    fig_dist = make_subplots(rows=1, cols=3, subplot_titles=["v4", "Estendido", "v5"])

    for i, (col_n, total, cor) in enumerate([
        ("contratos_v4", total_v4, "#27ae60"),
        ("contratos_pm", total_pm, "#3498db"),
        ("contratos_v5", total_v5, "#f39c12"),
    ], 1):
        pcts = [round(100 * n / total, 1) for n in df_5[col_n]]
        fig_dist.add_trace(go.Bar(
            x=df_5["faixa"], y=pcts,
            marker_color=[CORES.get(f, "gray") for f in df_5["faixa"]],
            opacity=0.7,
            text=[f"{p}%" for p in pcts],
            textposition="outside",
            showlegend=False,
        ), row=1, col=i)

    fig_dist.update_layout(height=400, title_text="% da base por faixa de risco")
    fig_dist.update_yaxes(title_text="% da base", range=[0, 70])
    st.plotly_chart(fig_dist, use_container_width=True)

    # Concentracao no MEDIO
    pct_medio_v4 = round(100 * df_5.loc[df_5["faixa"] == "MEDIO", "contratos_v4"].values[0] / total_v4, 1)
    pct_medio_pm = round(100 * df_5.loc[df_5["faixa"] == "MEDIO", "contratos_pm"].values[0] / total_pm, 1)
    pct_medio_v5 = round(100 * df_5.loc[df_5["faixa"] == "MEDIO", "contratos_v5"].values[0] / total_v5, 1)

    cm1, cm2, cm3 = st.columns(3)
    cm1.metric("v4: % no MEDIO", f"{pct_medio_v4}%", help="Quanto menor, melhor a distribuicao")
    cm2.metric("Estendido: % no MEDIO", f"{pct_medio_pm}%",
               delta=f"+{pct_medio_pm - pct_medio_v4:.0f} p.p.", delta_color="inverse")
    cm3.metric("v5: % no MEDIO", f"{pct_medio_v5}%",
               delta=f"+{pct_medio_v5 - pct_medio_v4:.0f} p.p.", delta_color="inverse")

    st.markdown(f"""
    O v4 concentra apenas **{pct_medio_v4}%** no MEDIO, enquanto o estendido
    joga **{pct_medio_pm}%** e o v5 **{pct_medio_v5}%**. Quanto mais concentrado
    no MEDIO, menos util o score e pra priorizar acoes.
    """)

    # Features
    st.markdown("---")
    st.markdown("#### Top features por modelo (gain)")

    feat_data = {
        "v4": [
            ("Sem dependentes", 126.6), ("Senior", 63.1), ("Sem atendimento", 27.3),
            ("3+ dependentes", 26.1), ("2o+ contrato", 14.2), ("Cronico", 13.1),
            ("Jovem", 11.2), ("Plano 6m", 9.5), ("Continuidade medico", 6.8),
            ("Qtd atendimentos", 6.0),
        ],
        "Estendido": [
            ("Sem atendimento", 86.1), ("3+ dependentes", 61.5), ("2o+ contrato", 58.4),
            ("Jovem", 26.6), ("Cronico", 25.2), ("Plano 6m", 21.1),
            ("Qtd atendimentos", 20.4), ("Sem dependentes", 19.1),
            ("Tem atendimento", 17.5), ("Senior", 15.3),
        ],
        "v5": [
            ("2o+ contrato", 71.1), ("Sem atendimento", 66.9), ("Jovem", 29.6),
            ("3+ dependentes", 22.4), ("Plano 6m", 21.6), ("Senior", 14.5),
            ("Qtd atendimentos", 10.7), ("Sem dependentes", 10.0),
            ("Cronico", 7.9), ("NPS", 6.1),
        ],
    }

    col_f1, col_f2, col_f3 = st.columns(3)
    for col_ui, (nome, feats) in zip([col_f1, col_f2, col_f3], feat_data.items()):
        with col_ui:
            st.markdown(f"**{nome}**")
            for feat, gain in feats[:7]:
                bar_len = int(20 * gain / feat_data["v4"][0][1])
                st.text(f"{'█' * bar_len} {feat} ({gain:.0f})")

    st.markdown("""
    ---
    **Observacao:**
    - No v4, a feature dominante e **sem dependentes** (gain 127) — faz sentido:
      quem esta sozinho tem menos vinculo com o plano
    - No estendido e v5, **sem atendimento** domina — reflete que quem nao usa E
      tem falha de pagamento sai, mas o modelo confunde causa (pagamento) com correlacao (uso)
    - O v4 tem features mais interpretaveis e acionaveis pro time de Growth
    """)


# ═══════════════════════════════════════════════════════════════════
# TAB 5: VEREDICTO
# ═══════════════════════════════════════════════════════════════════
with tab5:
    st.markdown("### Veredicto: qual target usar?")

    st.markdown("""
    ---
    #### Comparacao final
    """)

    st.markdown("""
    | Criterio | v4 | Estendido | v5 |
    |---|---|---|---|
    | **AUC (5-fold CV)** | **0.6353** | 0.6305 | 0.6023 |
    | **Spread (5 faixas)** | **76.5 p.p.** | 70.1 p.p. | 72.7 p.p. |
    | **Spread (7 faixas)** | 68.2 p.p. | **88.4 p.p.** | 98.8 p.p.* |
    | **Concentracao MEDIO (5f)** | **17%** | 53% | 65% |
    | **Taxa de churn** | 22.2% | 41.8% | 49.4% |
    | **Quando sabe o target** | **No vencimento** | 2+ meses depois | No vencimento |
    | **Acionavel antes do churn** | **Sim** | Nao | Sim |
    | **Conceito correto** | Parcial | **Sim** | Parcial |

    *\\*v5 em 7 faixas tem spread alto mas com faixas extremas quase vazias (82 no SEGURO)*
    """)

    st.markdown("""
    ---
    #### O dilema

    O target estendido e o **mais correto conceitualmente** — espera o desfecho
    real antes de classificar. Mas:

    1. **Nao melhora o AUC** (0.6305 vs 0.6353) — porque a causa dos 30% que migram
       pro gratis e **falha de pagamento**, nao perfil do paciente
    2. **Concentra no MEDIO** — 53% da base fica na faixa intermediaria, dificultando
       a priorizacao
    3. **Nao e acionavel** — so se sabe o desfecho 2+ meses apos o vencimento,
       quando ja e tarde pra prevenir

    E os dados de uso confirmam: **94% nao usam nada** durante o gratis.
    O plano gratis nao e ferramenta de retencao — e sala de espera pro churn.
    """)

    st.markdown("""
    ---
    #### Recomendacao

    Nao existe uma resposta unica — cada definicao serve um proposito:
    """)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("""
        **Score v4**
        *Para acao operacional*

        - Usar no CRM/Growth pra priorizar
          contato proativo antes do vencimento
        - Melhor AUC e distribuicao
        - Age quando ainda da tempo
        """)

    with col2:
        st.markdown("""
        **Taxa estendida (41.8%)**
        *Para reporte ao comite*

        - Metrica de churn mais justa
          que os 55% ou 22%
        - Reflete o desfecho real
        - Nao como target de modelo,
          mas como KPI de monitoramento
        """)

    with col3:
        st.markdown("""
        **Frente de cobranca**
        *Para os 30% de falha de pagamento*

        - Problema separado do churn de perfil
        - Investigar features de pagamento
          (Adyen/Mundipagg)
        - Modelo especifico de falha
          de cobranca
        """)

    st.markdown("""
    ---
    > **Conclusao:** o target estendido valida a intuicao do Growth — esperar o
    > desfecho real e mais justo. Mas como ferramenta de **predicao e acao**,
    > o v4 continua superior. A recomendacao e usar a **taxa estendida (41.8%)
    > como metrica de reporte** e o **score v4 como ferramenta operacional**,
    > tratando a falha de pagamento como workstream separada.
    """)
