import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from comite_scoring import (
    BAND_5_COLORS,
    BAND_5_LABELS,
    BAND_5_ORDER,
    BANDS_MODE_ASYMMETRIC,
    BANDS_MODE_LABELS,
    WLS_FEATURES_DEFAULT,
    WLS_REFS_DEFAULT,
    adjacent_band_tests,
    assign_bands,
    band_summary,
    fit_wls_per_duracao,
    inv_logit,
    ks_data,
    validate_oos,
)

bands_mode = st.session_state.get("bands_mode", BANDS_MODE_ASYMMETRIC)

st.title("🎯 Score e Faixas de Risco")
st.caption(
    f"WLS sobre logit(churn) com 4 variáveis core · score 0-1000 · 5 faixas · "
    f"1 modelo independente por duração · **Cortes: {BANDS_MODE_LABELS[bands_mode]}** "
    f"(altere na sidebar)"
)


@st.cache_data
def load_cruzamento():
    return pd.read_csv("results_comite/storytelling_cruzamento.csv")


@st.cache_data
def fit_models():
    df = load_cruzamento()
    df["duracao"] = df["duracao"].astype(str)
    models = fit_wls_per_duracao(df, features=WLS_FEATURES_DEFAULT, refs=WLS_REFS_DEFAULT)
    return models


try:
    models = fit_models()
except FileNotFoundError:
    st.error(
        "`results_comite/storytelling_cruzamento.csv` não encontrado. "
        "Rode o bloco B de `queries_comite/storytelling_3vars.sql` antes."
    )
    st.stop()

DUR_COLORS = {"6": "#4caf50", "12": "#ff5722"}

# ═══════════════════════════════════════════════════════════════════════════
# KPIs DE TOPO POR DURAÇÃO
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("### Visão geral dos dois modelos")
st.caption(
    "Cada plano (6m vs 12m) tem seu próprio modelo WLS. Os perfis são os mesmos "
    "(ciclo × faixa × crônico), mas os pesos de cada variável variam — "
    "e essa diferença é parte da história a contar."
)

col6, col12 = st.columns(2)
for col, dur in [(col6, "6"), (col12, "12")]:
    if dur not in models:
        col.warning(f"Sem modelo para {dur}m.")
        continue
    with col:
        m = models[dur]
        st.markdown(f"#### Plano {dur} meses")
        k1, k2, k3 = st.columns(3)
        k1.metric("Perfis", f"{m['metrics']['n_perfis']}")
        k2.metric("Contratos", f"{m['metrics']['n_contratos']:,}")
        k3.metric("Churn global", f"{m['metrics']['churn_global']:.1f}%")
        k1, k2, k3 = st.columns(3)
        k1.metric("MAE", f"{m['metrics']['mae']:.2f} p.p.",
                  help="Erro médio absoluto: predito vs observado (ponderado por volume)")
        k2.metric("Correlação", f"{m['metrics']['corr']:.3f}",
                  help="Correlação entre churn predito e observado nos perfis")
        k3.metric("C-index", f"{m['metrics']['c_index']:.3f}",
                  help="Concordância: chance de o score ordenar churner vs retido. ~0.5 = aleatório, ~0.7+ = bom")

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════
# TABELA DE COEFICIENTES (PENALIDADES) — POR DURAÇÃO
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("### Como o score é calculado — penalidades por fator")
st.caption(
    "Cada nível (vs referência de menor risco) subtrai pontos do score. "
    "Sig: *** = p < 0,001, ** = p < 0,01, * = p < 0,05, n.s. = não significativo."
)

ref_text = ", ".join([f"{k}={v}" for k, v in WLS_REFS_DEFAULT.items()])
st.markdown(
    f"**Referência (score 1000) em ambos os modelos:** {ref_text}. "
    f"Esse perfil tem o menor churn esperado dentro de sua duração."
)

tab6, tab12 = st.tabs(["📊 Plano 6 meses", "📊 Plano 12 meses"])

VAR_LABELS_PT = {
    "ciclo": "Ciclo",
    "faixa_etaria": "Faixa etária",
    "cronico": "Crônico",
    "composicao_titular": "Composição",
}
LEVEL_LABELS_PT = {
    "1o": "1o contrato",
    "00-20": "Idade 00-20", "21-30": "Idade 21-30",
    "31-50": "Idade 31-50", "51-70": "Idade 51-70",
    "N": "Não crônico",
    "solo": "Comp. solo",
    "com_crianca": "Comp. com criança",
    "com_ambos": "Comp. com ambos",
}

for tab, dur in [(tab6, "6"), (tab12, "12")]:
    with tab:
        if dur not in models:
            continue
        m = models[dur]
        coefs = m["coefs"].copy()
        # Tira intercepto da tabela de penalidades
        pen = coefs[coefs["pontos"] != 0].copy()
        pen["fator"] = pen.apply(
            lambda r: LEVEL_LABELS_PT.get(r["nivel"], f"{VAR_LABELS_PT.get(r['variavel'], r['variavel'])} = {r['nivel']}"),
            axis=1,
        )

        col_t, col_b = st.columns([3, 4])

        with col_t:
            disp = pen[["variavel", "fator", "pontos", "ic_lo_pts", "ic_hi_pts", "efeito_pp", "p", "sig"]].copy()
            disp["pontos"] = disp["pontos"].apply(lambda v: f"{v:+d}")
            disp["IC 95% pontos"] = disp.apply(lambda r: f"[{int(r['ic_lo_pts']):+d}, {int(r['ic_hi_pts']):+d}]", axis=1)
            disp["efeito_pp"] = disp["efeito_pp"].apply(lambda v: f"{v:+.1f}")
            disp["p"] = disp["p"].apply(lambda v: f"<0,001" if v < 0.001 else f"{v:.3f}")
            disp = disp[["variavel", "fator", "pontos", "IC 95% pontos", "efeito_pp", "p", "sig"]]
            disp.columns = ["Variável", "Fator", "Pontos", "IC 95%", "Δ Churn (p.p.)", "p-valor", "Sig."]
            st.dataframe(disp, hide_index=True, use_container_width=True)
            st.caption(
                f"**Churn base do perfil de referência:** {m['ref_churn_pp']}% · "
                f"Escala: 1 unidade de log-odds = {m['scale']:.1f} pontos"
            )

        with col_b:
            # Gráfico de coeficientes com IC
            pen_sorted = pen.sort_values("pontos")
            fig = go.Figure()
            fig.add_trace(go.Bar(
                y=pen_sorted["fator"],
                x=pen_sorted["pontos"],
                orientation="h",
                marker_color=["#c0392b" if p < -50 else "#e67e22" if p < 0 else "#27ae60"
                              for p in pen_sorted["pontos"]],
                text=pen_sorted.apply(
                    lambda r: f"{int(r['pontos']):+d} pts ({r['sig']})", axis=1),
                textposition="outside",
                showlegend=False,
            ))
            # Barras de IC
            fig.add_trace(go.Scatter(
                y=pen_sorted["fator"], x=pen_sorted["pontos"],
                error_x=dict(
                    type="data", symmetric=False,
                    array=(pen_sorted["ic_hi_pts"] - pen_sorted["pontos"]).abs().values,
                    arrayminus=(pen_sorted["pontos"] - pen_sorted["ic_lo_pts"]).abs().values,
                    color="rgba(0,0,0,0.55)", thickness=2, width=8,
                ),
                mode="markers", marker=dict(size=1, color="rgba(0,0,0,0)"), showlegend=False,
            ))
            fig.add_vline(x=0, line_dash="dash", line_color="gray", line_width=1)
            fig.update_layout(
                title=f"Penalidades — plano {dur}m",
                xaxis_title="Pontos no score (negativo = mais risco)",
                yaxis=dict(automargin=True),
                height=max(300, 50 * len(pen_sorted) + 80),
                margin=dict(l=10, r=80, t=50, b=40),
            )
            st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════
# COMPARATIVO DE PENALIDADES 6m vs 12m
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("### Comparativo dos coeficientes: 6m vs 12m")
st.caption(
    "Mesmo fator pode pesar diferente em cada plano. Diferenças grandes sugerem que "
    "o driver age via mecanismo distinto nos dois ciclos contratuais."
)

cmp_rows = []
for dur in ["6", "12"]:
    if dur not in models:
        continue
    for _, r in models[dur]["coefs"].iterrows():
        if r["pontos"] == 0:
            continue
        cmp_rows.append({
            "fator": LEVEL_LABELS_PT.get(r["nivel"], f"{r['variavel']}={r['nivel']}"),
            "duracao": f"{dur}m",
            "pontos": r["pontos"],
            "sig": r["sig"],
        })
cmp_df = pd.DataFrame(cmp_rows)
if not cmp_df.empty:
    fig_cmp = px.bar(
        cmp_df, x="pontos", y="fator", color="duracao",
        barmode="group", orientation="h",
        text=cmp_df.apply(lambda r: f"{int(r['pontos']):+d} ({r['sig']})", axis=1),
        color_discrete_map={"6m": DUR_COLORS["6"], "12m": DUR_COLORS["12"]},
        labels={"pontos": "Pontos no score", "fator": "", "duracao": "Plano"},
    )
    fig_cmp.add_vline(x=0, line_dash="dash", line_color="gray")
    fig_cmp.update_traces(textposition="outside")
    fig_cmp.update_layout(
        height=max(350, 45 * (len(cmp_df) // 2) + 100),
        margin=dict(t=30),
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_cmp, use_container_width=True)

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════
# 5 FAIXAS DE RISCO — POR DURAÇÃO
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("### As 5 faixas de risco")
st.caption(
    "Cortes em **quintis ponderados por volume**: cada faixa carrega ~20% dos contratos da duração. "
    "Cada faixa mostra IC 95% (Wilson) e lift sobre o churn global do plano."
)

for dur in ["6", "12"]:
    if dur not in models:
        continue
    m = models[dur]
    profs = assign_bands(m["profiles"], mode=bands_mode)
    bs = band_summary(profs)
    ks = ks_data(bs)

    st.markdown(f"#### Plano {dur} meses · churn global {m['metrics']['churn_global']:.1f}%")

    # KPIs CRITICO vs SEGURO
    crit = bs[bs["band"] == "CRITICO"]
    seg = bs[bs["band"] == "SEGURO"]
    if not crit.empty and not seg.empty:
        spread = round(float(crit["churn_rate"].iloc[0]) - float(seg["churn_rate"].iloc[0]), 1)
        ks_max = float(ks["ks_pp"].max())
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Churn CRITICO", f"{crit['churn_rate'].iloc[0]}%",
                  help=f"IC 95%: [{crit['ic_lo'].iloc[0]}, {crit['ic_hi'].iloc[0]}]")
        c2.metric("Churn SEGURO", f"{seg['churn_rate'].iloc[0]}%",
                  help=f"IC 95%: [{seg['ic_lo'].iloc[0]}, {seg['ic_hi'].iloc[0]}]")
        c3.metric("Spread extremos", f"{spread} p.p.",
                  help="Capacidade do score de separar pior vs melhor faixa")
        c4.metric("KS máximo", f"{ks_max:.1f}%",
                  help="Maior separação entre distribuição de churners e retidos ao longo das faixas")

    # Gráfico principal: barras de volume + linha de churn por faixa
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=bs["band"].astype(str),
        y=bs["total_contratos"],
        name="Contratos",
        marker_color=[BAND_5_COLORS[b] for b in bs["band"].astype(str)],
        opacity=0.45,
        text=bs["total_contratos"].apply(lambda v: f"{v:,}"),
        textposition="outside",
    ))
    fig.add_trace(go.Scatter(
        x=bs["band"].astype(str),
        y=bs["churn_rate"],
        name="Churn (%)",
        mode="lines+markers+text",
        line=dict(width=3, color="crimson"),
        marker=dict(size=12, color=[BAND_5_COLORS[b] for b in bs["band"].astype(str)],
                    line=dict(width=2, color="white")),
        text=bs["churn_rate"].apply(lambda v: f"{v}%"),
        textposition="top center",
        textfont=dict(size=12, color="crimson"),
        yaxis="y2",
        error_y=dict(
            type="data", symmetric=False,
            array=(bs["ic_hi"] - bs["churn_rate"]).values,
            arrayminus=(bs["churn_rate"] - bs["ic_lo"]).values,
            color="rgba(220,20,60,0.4)", thickness=1.5, width=6,
        ),
    ))
    fig.update_layout(
        title=f"Volume e churn por faixa — {dur}m",
        xaxis=dict(title=""),
        yaxis=dict(title="Contratos", showgrid=False),
        yaxis2=dict(title="Churn (%)", overlaying="y", side="right", range=[0, 100]),
        height=420,
        legend=dict(orientation="h", y=1.12),
        margin=dict(t=60),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Tabela detalhada
    bs_display = bs[
        ["band", "total_contratos", "churners", "churn_rate", "ic_lo", "ic_hi", "lift", "pct_duracao", "score_min", "score_max", "n_perfis"]
    ].copy()
    bs_display["IC 95%"] = bs_display.apply(lambda r: f"[{r['ic_lo']}, {r['ic_hi']}]", axis=1)
    bs_display["Score range"] = bs_display.apply(lambda r: f"{int(r['score_min'])}–{int(r['score_max'])}", axis=1)
    bs_display = bs_display[["band", "total_contratos", "churners", "churn_rate", "IC 95%", "lift", "pct_duracao", "Score range", "n_perfis"]]
    bs_display.columns = ["Faixa", "Contratos", "Churners", "Churn (%)", "IC 95%", "Lift", "% Duração", "Score", "# Perfis"]
    st.dataframe(bs_display, hide_index=True, use_container_width=True)

    # Z-tests entre faixas adjacentes
    with st.expander(f"📐 Diferença entre faixas adjacentes ({dur}m) — z-test"):
        adj = adjacent_band_tests(bs)
        adj_display = adj.copy()
        adj_display["Diferença"] = adj_display["diff_pp"].apply(lambda v: f"{v:+.1f} p.p.")
        adj_display["IC 95%"] = adj_display.apply(lambda r: f"[{r['ic_lo']:+.1f}, {r['ic_hi']:+.1f}]", axis=1)
        adj_display["p-valor"] = adj_display["p"].apply(lambda v: f"<0,001" if v < 0.001 else f"{v:.3f}")
        adj_display = adj_display[["comparacao", "churn_a", "churn_b", "Diferença", "IC 95%", "p-valor", "sig"]]
        adj_display.columns = ["Comparação", "Churn A", "Churn B", "Diferença", "IC 95%", "p-valor", "Sig."]
        st.dataframe(adj_display, hide_index=True, use_container_width=True)
        st.caption("Faixas adjacentes com p < 0,05 confirmam que o score discrimina nesse corte.")

    st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════
# CALIBRAÇÃO E SEPARAÇÃO (KS)
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("### Validação visual: calibração e separação")
st.caption(
    "**Calibração**: predito vs observado por perfil — deve cair na diagonal. "
    "**KS**: separação entre acumulado de churners e retidos ao longo das faixas — deve ser ampla."
)

cal_col, ks_col = st.columns(2)

with cal_col:
    fig_cal = go.Figure()
    for dur in ["6", "12"]:
        if dur not in models:
            continue
        p = models[dur]["profiles"]
        fig_cal.add_trace(go.Scatter(
            x=p["churn_pred"], y=p["churn_rate"],
            mode="markers",
            name=f"{dur} meses",
            marker=dict(
                size=np.sqrt(p["total_contratos"]) / 2,
                color=DUR_COLORS[dur], opacity=0.55, line=dict(width=0.5, color="white"),
                sizemin=4,
            ),
        ))
    fig_cal.add_trace(go.Scatter(
        x=[30, 80], y=[30, 80], mode="lines",
        line=dict(dash="dash", color="gray"), name="Calibração perfeita",
    ))
    fig_cal.update_layout(
        title="Calibração: churn predito vs observado",
        xaxis=dict(title="Churn predito (%)"),
        yaxis=dict(title="Churn observado (%)"),
        height=400,
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_cal, use_container_width=True)

with ks_col:
    fig_ks = go.Figure()
    for dur in ["6", "12"]:
        if dur not in models:
            continue
        m = models[dur]
        profs = assign_bands(m["profiles"], mode=bands_mode)
        bs = band_summary(profs)
        ks = ks_data(bs)
        fig_ks.add_trace(go.Scatter(
            x=ks["band"].astype(str), y=ks["cum_churn_pct"],
            mode="lines+markers", name=f"{dur}m churners",
            line=dict(color=DUR_COLORS[dur], width=2.5),
        ))
        fig_ks.add_trace(go.Scatter(
            x=ks["band"].astype(str), y=ks["cum_ret_pct"],
            mode="lines+markers", name=f"{dur}m retidos",
            line=dict(color=DUR_COLORS[dur], width=2.5, dash="dot"),
        ))
    fig_ks.update_layout(
        title="Curva KS: acumulado por faixa",
        xaxis=dict(title=""),
        yaxis=dict(title="Acumulado (%)", range=[0, 105]),
        height=400,
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_ks, use_container_width=True)

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════
# VALIDAÇÃO OUT-OF-SAMPLE — SPLIT TEMPORAL 6m+6m
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("### 🧪 Validação out-of-sample — split temporal")
st.caption(
    "Treinamos o WLS na **janela antiga (meses -12 a -7)** e validamos na **recente (meses -6 a -1)**. "
    "Se MAE_test ≈ MAE_train e os coefs ficam estáveis, o score envelhece bem."
)


@st.cache_data
def load_oos():
    train_path = "results_comite/storytelling_cruzamento_train.csv"
    test_path = "results_comite/storytelling_cruzamento_test.csv"
    try:
        df_tr = pd.read_csv(train_path)
        df_te = pd.read_csv(test_path)
        df_tr["duracao"] = df_tr["duracao"].astype(str)
        df_te["duracao"] = df_te["duracao"].astype(str)
        return df_tr, df_te
    except FileNotFoundError:
        return None, None


df_train_oos, df_test_oos = load_oos()
if df_train_oos is None:
    st.info(
        "📂 CSVs OOS ainda não gerados. "
        "Rode `queries_comite/storytelling_3vars_oos.sql` no BigQuery e salve como "
        "`results_comite/storytelling_cruzamento_train.csv` (Bloco A) e "
        "`storytelling_cruzamento_test.csv` (Bloco B)."
    )
else:
    oos = validate_oos(
        df_train_oos, df_test_oos,
        features=WLS_FEATURES_DEFAULT, refs=WLS_REFS_DEFAULT,
    )

    # KPIs train × test por duração
    for dur in ["6", "12"]:
        if dur not in oos:
            continue
        mt = oos[dur]["metrics_train"]
        me = oos[dur]["metrics_test"]
        st.markdown(f"#### Plano {dur} meses")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "MAE train → test",
            f"{me['mae']:.2f} p.p.",
            f"{me['mae'] - mt['mae']:+.2f} vs train",
            help="Erro médio absoluto. Diferença pequena = score generaliza.",
        )
        c2.metric(
            "C-index train → test",
            f"{me['c_index']:.3f}",
            f"{me['c_index'] - mt['c_index']:+.3f} vs train",
            help="Ordenação no test usando coefs do train.",
        )
        c3.metric(
            "Churn global test",
            f"{me['churn_global']:.1f}%",
            f"{me['churn_global'] - mt['churn_global']:+.1f} vs train",
            help="Compara baseline entre as duas janelas.",
        )
        c4.metric("Contratos test", f"{me['n_contratos']:,}")

        # Estabilidade dos coefs
        stab = oos[dur]["coef_stability"]
        if not stab.empty:
            stab_show = stab[stab["variavel"] != "(intercepto)"].copy()
            stab_show["fator"] = stab_show["variavel"] + " = " + stab_show["nivel"].astype(str)
            stab_show = stab_show[[
                "fator", "pts_train", "pts_test", "delta_pts",
                "log_odds_train", "log_odds_test", "z_delta", "delta_sig",
            ]]
            stab_show.columns = [
                "Fator", "Pts train", "Pts test", "Δ pts",
                "β train", "β test", "z(Δ)", "Sig. Δ",
            ]
            stab_show["β train"] = stab_show["β train"].round(3)
            stab_show["β test"] = stab_show["β test"].round(3)
            with st.expander(f"📐 Estabilidade dos coefs — plano {dur}m", expanded=False):
                st.dataframe(stab_show, hide_index=True, use_container_width=True)
                st.caption(
                    "**Sig. Δ = n.s.** significa que o coeficiente não mudou de forma "
                    "estatisticamente significativa entre as duas janelas — score estável. "
                    "Asteriscos (* / ** / ***) sinalizam deriva real."
                )

    st.caption(
        "Limite: 6 meses são um intervalo curto pra avaliar deriva. "
        "Se a equipe tiver histórico mais longo (>24m), vale rodar rolling com janelas trimestrais."
    )

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════
# CAVEATS METODOLÓGICOS
# ═══════════════════════════════════════════════════════════════════════════
with st.expander("📖 Metodologia e limitações", expanded=False):
    st.markdown(f"""
    **Modelo:** Regressão Linear Ponderada (WLS) sobre logit(churn) dos perfis.
    Pesos = volume de contratos por perfil. Matematicamente equivalente a regressão
    logística com dados agrupados (Berkson's method).

    **Variáveis ({len(WLS_FEATURES_DEFAULT)} core):** `{", ".join(WLS_FEATURES_DEFAULT)}`.
    Estrutura modular em `comite_scoring.py` — para adicionar mais (ex: composicao_drc,
    canal, classe), passe `features` e `refs` em `fit_wls(...)`. Não exige reescrever a página.

    **Por que 1 modelo por duração?** A tese executiva é comparar 6m vs 12m em paralelo.
    Modelos separados permitem que os pesos variem entre planos (e essa variação é parte
    do insight que vai pro comitê).

    **5 faixas em quintis ponderados:** cada faixa carrega ~20% dos contratos do plano.
    Cortes saem dos próprios dados, então variam entre 6m e 12m (mostrados em "Score range").

    **Score 0-1000:** linear sobre logit predito, invertido — 1000 = perfil de menor risco
    (referência), 0 = perfil de maior risco da duração. Cada unidade de log-odds vale uma
    quantidade de pontos que aparece na seção de penalidades.

    **Limitações conhecidas:**
    - **C-index moderado (~0.57-0.59):** com 3 variáveis demográfico-contratuais, esse é o
      teto razoável. O app antigo, com 8 vars, fica em ~0.60 — adicionar `composicao_drc`,
      `canal` e `classe` provavelmente leva o c-index para ~0.62-0.65.
    - **Sem dados comportamentais no score:** consumo, recência, histórico de pagamento
      ficam de fora. Esses sinais separam melhor *dentro* do mesmo perfil — exatamente o
      que a Página 4 (Transição) explora.
    - **Snapshot único:** cada contrato é observado uma vez. Estrutura modular permite
      evoluir para mês-a-mês depois.

    **Próxima página:** *Hábitos e Transição* — entender o que move um cliente entre faixas.
    """)
