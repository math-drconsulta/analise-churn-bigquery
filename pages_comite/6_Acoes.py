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
    ab_sample_size,
    assign_bands,
    e_value,
    e_value_label,
    fit_wls_per_duracao,
    fit_wls_with_treatment,
    sig_stars,
    z_test_proportions,
)

bands_mode = st.session_state.get("bands_mode", BANDS_MODE_ASYMMETRIC)

st.title("✅ Plano de Ações Growth — Causalidade & Robustez")
st.caption(
    f"Recomendações priorizadas · Cada ação tem efeito ajustado, E-value e plano de medição A/B. "
    f"**Cortes: {BANDS_MODE_LABELS[bands_mode]}** (altere na sidebar)."
)


# ═══════════════════════════════════════════════════════════════════════════
# DADOS + COMPUTAÇÕES BASE
# ═══════════════════════════════════════════════════════════════════════════
@st.cache_data
def load_cruzamento():
    return pd.read_csv("results_comite/storytelling_cruzamento.csv")


@st.cache_data
def load_consumo():
    return pd.read_csv("results_comite/consumo_dentro_perfil.csv")


@st.cache_data
def compute_perfil_to_faixa(mode: str):
    df_crz = load_cruzamento()
    df_crz["duracao"] = df_crz["duracao"].astype(str)
    models = fit_wls_per_duracao(df_crz, WLS_FEATURES_DEFAULT, WLS_REFS_DEFAULT)
    rows = []
    for dur, m in models.items():
        s = assign_bands(m["profiles"], mode=mode)
        for _, r in s.iterrows():
            rows.append({
                "duracao": dur, "ciclo": r["ciclo"], "faixa_etaria": r["faixa_etaria"],
                "cronico": r["cronico"], "composicao_titular": r["composicao_titular"],
                "band": str(r["band"]), "score": int(r["score"]),
            })
    return pd.DataFrame(rows)


@st.cache_data
def compute_stratified_effects():
    """Para cada (duracao, faixa, especialidade): Δ observ + IC + p + E-value."""
    df_cons = load_consumo()
    df_cons["duracao"] = df_cons["duracao"].astype(str)
    perfil_band = compute_perfil_to_faixa(bands_mode)
    key = ["duracao", "ciclo", "faixa_etaria", "cronico", "composicao_titular"]
    df = df_cons.merge(perfil_band[key + ["band"]], on=key, how="inner")

    agg = df.groupby(
        ["duracao", "band", "especialidade", "uso"], as_index=False
    ).agg(
        total_contratos=("total_contratos", "sum"),
        churners=("churners", "sum"),
    )
    agg["churn_rate"] = round(100 * agg["churners"] / agg["total_contratos"], 2)

    wide = agg.pivot_table(
        index=["duracao", "band", "especialidade"],
        columns="uso",
        values=["total_contratos", "churners", "churn_rate"],
        aggfunc="sum",
    ).reset_index()
    wide.columns = ["_".join(str(x) for x in c if x != "").rstrip("_") for c in wide.columns]
    wide = wide.dropna(subset=["churn_rate_usou", "churn_rate_nao_usou"]).reset_index(drop=True)

    def _row_effects(r):
        n1 = int(r["total_contratos_nao_usou"]); x1 = int(r["churners_nao_usou"])
        n2 = int(r["total_contratos_usou"]);     x2 = int(r["churners_usou"])
        t = z_test_proportions(n1, x1, n2, x2)
        # RR de USAR (treated/control)
        p_u = (x2 / n2) if n2 else 0.0
        p_n = (x1 / n1) if n1 else 0.0
        rr = (p_u / p_n) if p_n > 0 else float("nan")
        return pd.Series({
            "delta_pp": round(t["diff"], 2),
            "ci_lo": round(t["ci_lo"], 2),
            "ci_hi": round(t["ci_hi"], 2),
            "p": t["p"],
            "sig": sig_stars(t["p"]),
            "rr": rr,
            "e_value": e_value(rr),
        })

    wide = pd.concat([wide, wide.apply(_row_effects, axis=1)], axis=1)
    wide["n_usou"] = wide["total_contratos_usou"].astype(int)
    wide["n_nao_usou"] = wide["total_contratos_nao_usou"].astype(int)
    wide["pct_usou"] = round(100 * wide["n_usou"] / (wide["n_usou"] + wide["n_nao_usou"]), 1)
    wide["band"] = pd.Categorical(wide["band"], categories=BAND_5_ORDER, ordered=True)
    return wide


@st.cache_data
def compute_adjusted_effects():
    """Score 2.0 — WLS estendido com tratamento, agregado por (duracao, especialidade)."""
    df_cons = load_consumo()
    df_cons["duracao"] = df_cons["duracao"].astype(str)
    rows = []
    for esp in df_cons["especialidade"].unique():
        for dur in ["6", "12"]:
            m = fit_wls_with_treatment(df_cons, esp, dur)
            if m is None:
                continue
            rows.append({
                "duracao": dur, "especialidade": esp,
                "delta_pp_adjusted": m["delta_pp_adjusted"],
                "delta_pp_adj_lo": m["delta_pp_ci_lo"],
                "delta_pp_adj_hi": m["delta_pp_ci_hi"],
                "p_adj": m["p"],
                "sig_adj": m["sig"],
                "rr_adj": m["rr"],
                "e_value_adj": m["e_value"],
            })
    return pd.DataFrame(rows)


try:
    wide = compute_stratified_effects()
    adj = compute_adjusted_effects()
except FileNotFoundError as e:
    st.error(f"CSV não encontrado: `{e.filename}`.")
    st.stop()


# ═══════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════
st.sidebar.markdown("### ⚙️ Parâmetros do cenário")
dur_sel = st.sidebar.radio(
    "Duração:", options=["6", "12"], index=1,
    format_func=lambda x: f"{x} meses", key="acoes_dur",
    help="12m tem mais alavancas significativas — ROI tende a ser maior",
)
eficacia = st.sidebar.slider(
    "Eficácia esperada da ação (% do Δ capturado):",
    min_value=10, max_value=100, value=40, step=5,
)
min_volume = st.sidebar.number_input(
    "Volume mínimo do público (não usou):",
    min_value=100, max_value=10000, value=500, step=100,
)
only_sig = st.sidebar.checkbox(
    "Apenas ações significativas (p < 0,05)", value=True,
)
min_e_value = st.sidebar.slider(
    "E-value mínimo (robustez):",
    min_value=1.0, max_value=3.0, value=1.0, step=0.05,
    help="≥2 = robusto · 1.5-2 = moderado · <1.5 = sensível a confounding",
)

# ═══════════════════════════════════════════════════════════════════════════
# CONSTRÓI TABELA DE AÇÕES
# ═══════════════════════════════════════════════════════════════════════════
f = wide[wide["duracao"] == dur_sel].copy()
f = f[(f["delta_pp"] > 0) & (f["n_nao_usou"] >= min_volume)]
if only_sig:
    f = f[f["p"] < 0.05]
f = f[f["e_value"] >= min_e_value]

# Merge com Δ ajustado (mesmo entre faixas, por especialidade)
adj_d = adj[adj["duracao"] == dur_sel]
f = f.merge(
    adj_d[["especialidade", "delta_pp_adjusted", "delta_pp_adj_lo",
           "delta_pp_adj_hi", "p_adj", "sig_adj", "e_value_adj"]],
    on="especialidade", how="left",
)

# Impacto
f["delta_capturado"] = (f["delta_pp"] * eficacia / 100.0).round(2)
f["churners_evitaveis"] = (f["n_nao_usou"] * f["delta_capturado"] / 100.0).round().astype(int)
f = f.sort_values("churners_evitaveis", ascending=False).reset_index(drop=True)
f["#"] = f.index + 1

# ═══════════════════════════════════════════════════════════════════════════
# KPIs TOPO
# ═══════════════════════════════════════════════════════════════════════════
total_contratos_dur = int(wide[wide["duracao"] == dur_sel]["total_contratos_usou"].sum()
                          + wide[wide["duracao"] == dur_sel]["total_contratos_nao_usou"].sum())
# Subset único: cada perfil aparece N vezes (1 por especialidade). Pegamos o agregado de fato (cruzamento):
df_crz_dur = load_cruzamento()
df_crz_dur = df_crz_dur[df_crz_dur["duracao"].astype(str) == dur_sel]
total_real = int(df_crz_dur["total_contratos"].sum())
churners_real = int(df_crz_dur["churners"].sum())

# Robustas (E-value >= 2)
n_robustas = int((f["e_value"] >= 2.0).sum())
n_moderadas = int(((f["e_value"] >= 1.5) & (f["e_value"] < 2.0)).sum())

publico_total = int(f["n_nao_usou"].sum())
churners_evit_total = int(f["churners_evitaveis"].sum())

st.markdown(f"### Plano para o plano de {dur_sel} meses · eficácia {eficacia}%")
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Contratos da dur.", f"{total_real:,}")
k2.metric("Churners atuais", f"{churners_real:,}")
k3.metric("Ações robustas", f"{n_robustas}", help="E-value ≥ 2.0")
k4.metric("Ações moderadas", f"{n_moderadas}", help="E-value 1.5 a 2.0")
k5.metric(
    "Churners evitáveis", f"{churners_evit_total:,}",
    delta=(f"-{round(100*churners_evit_total/churners_real,1)}%" if churners_real else None),
    delta_color="inverse",
    help="Soma das ações listadas (otimista — pode haver sobreposição entre alvos)",
)

if f.empty:
    st.warning(
        "Nenhuma ação atende aos critérios. Reduza o E-value mínimo ou o volume mínimo."
    )
    st.stop()

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════════════════
tab_plano, tab_robustez, tab_ab = st.tabs([
    "📋 Plano Executivo",
    "🔬 Robustez Causal",
    "🧪 Plano de Medição A/B",
])

# ───────────────────────────────────────────────────────────────────────────
# TAB 1: PLANO EXECUTIVO
# ───────────────────────────────────────────────────────────────────────────
with tab_plano:
    st.markdown("### Ações priorizadas por churners evitáveis")
    st.caption(
        "Cada linha = uma ação Growth. **Δ observ.** é o efeito dentro da faixa (z-test). "
        "**Δ ajustado** vem do Score 2.0 (WLS controlando 4 vars demográficas). "
        "**E-value** mede sensibilidade ao confounding não medido (maior = mais robusto)."
    )

    disp = f[[
        "#", "band", "especialidade", "n_nao_usou", "pct_usou",
        "delta_pp", "ci_lo", "ci_hi", "p", "sig", "e_value",
        "delta_pp_adjusted", "sig_adj", "delta_capturado", "churners_evitaveis",
    ]].copy()

    disp["Faixa"] = disp["band"].map(BAND_5_LABELS).fillna(disp["band"].astype(str))
    disp["Público (N)"] = disp["n_nao_usou"].apply(lambda v: f"{int(v):,}")
    disp["% usou hoje"] = disp["pct_usou"].apply(lambda v: f"{v:.0f}%")
    disp["Δ observ. (p.p.)"] = disp.apply(lambda r: f"+{r['delta_pp']:.1f} {r['sig']}", axis=1)
    disp["IC observ."] = disp.apply(lambda r: f"[{r['ci_lo']:+.1f}, {r['ci_hi']:+.1f}]", axis=1)
    disp["Δ ajustado (Score 2.0)"] = disp.apply(
        lambda r: (f"+{r['delta_pp_adjusted']:.1f} {r['sig_adj']}"
                   if pd.notna(r["delta_pp_adjusted"]) else "—"),
        axis=1,
    )
    disp["E-value"] = disp["e_value"].apply(
        lambda v: f"{v:.2f} {e_value_label(v).split(' ', 1)[0]}"
    )
    disp["Δ capturado"] = disp["delta_capturado"].apply(lambda v: f"+{v:.1f} p.p.")
    disp["Churners evitáveis"] = disp["churners_evitaveis"].apply(lambda v: f"{int(v):,}")

    disp_view = disp[[
        "#", "Faixa", "especialidade", "Público (N)", "% usou hoje",
        "Δ observ. (p.p.)", "IC observ.", "E-value",
        "Δ ajustado (Score 2.0)",
        "Δ capturado", "Churners evitáveis",
    ]].rename(columns={"especialidade": "Especialidade"})

    st.dataframe(disp_view, hide_index=True, use_container_width=True)

    # Ranking visual
    st.markdown("### Top 10 ações por churners evitáveis")
    top = f.head(10).iloc[::-1].copy()
    top["label"] = top.apply(
        lambda r: f"{r['#']}. {BAND_5_LABELS[r['band']]} · {r['especialidade']}", axis=1,
    )
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=top["label"],
        x=top["churners_evitaveis"],
        orientation="h",
        text=top.apply(
            lambda r: f"{int(r['churners_evitaveis']):,} (E={r['e_value']:.2f})", axis=1),
        textposition="outside",
        marker_color=[BAND_5_COLORS[b] for b in top["band"].astype(str)],
    ))
    fig.update_layout(
        title=f"Top 10 ações · plano {dur_sel}m · eficácia {eficacia}%",
        xaxis_title="Churners evitáveis",
        yaxis_title="",
        height=max(420, 40 * len(top) + 80),
        margin=dict(l=20, r=80),
    )
    st.plotly_chart(fig, use_container_width=True)

# ───────────────────────────────────────────────────────────────────────────
# TAB 2: ROBUSTEZ CAUSAL
# ───────────────────────────────────────────────────────────────────────────
with tab_robustez:
    st.markdown("### Drill de robustez por ação")
    st.caption(
        "Para cada ação top, comparamos Δ observado (dentro da faixa) com Δ ajustado "
        "do Score 2.0 (WLS multivariado), mostramos o E-value e a heterogeneidade do "
        "efeito por subgrupo."
    )

    if f.empty:
        st.info("Sem ações no filtro atual.")
    else:
        action_options = f.head(15).apply(
            lambda r: f"{int(r['#']):2d}. {BAND_5_LABELS[r['band']]} · {r['especialidade']}",
            axis=1,
        ).tolist()
        idx_sel = st.selectbox("Selecione a ação:", options=range(len(action_options)),
                                format_func=lambda i: action_options[i], key="rob_sel")
        row = f.iloc[idx_sel]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Δ observ. (faixa)", f"+{row['delta_pp']:.1f} p.p. {row['sig']}",
                  help=f"IC 95%: [{row['ci_lo']:+.1f}, {row['ci_hi']:+.1f}]")
        if pd.notna(row["delta_pp_adjusted"]):
            c2.metric("Δ ajustado (Score 2.0)",
                      f"+{row['delta_pp_adjusted']:.1f} p.p. {row['sig_adj']}",
                      help=f"IC 95%: [{row['delta_pp_adj_lo']:+.1f}, {row['delta_pp_adj_hi']:+.1f}]")
        else:
            c2.metric("Δ ajustado", "—")
        c3.metric("E-value", f"{row['e_value']:.2f}", help=e_value_label(row["e_value"]))
        c4.metric("RR (uso vs não uso)", f"{row['rr']:.3f}",
                  help="Risco relativo: <1 = uso protege, >1 = uso aumenta risco")

        # Concordância observ x ajustado
        st.markdown("#### Concordância observacional × ajustado")
        if pd.notna(row["delta_pp_adjusted"]):
            ratio = (row["delta_pp_adjusted"] / row["delta_pp"]) if row["delta_pp"] > 0 else 0
            if ratio >= 0.7:
                st.success(
                    f"**Δ ajustado preserva {ratio*100:.0f}% do Δ observado.** Bom sinal de robustez — "
                    f"controlar todas as 4 vars demográficas simultaneamente não atenua muito o efeito."
                )
            elif ratio >= 0.4:
                st.warning(
                    f"**Δ ajustado preserva {ratio*100:.0f}% do Δ observado.** Atenuação moderada — "
                    f"parte do efeito observado vem do mix demográfico, não da especialidade em si."
                )
            else:
                st.error(
                    f"**Δ ajustado preserva apenas {ratio*100:.0f}% do Δ observado.** Atenção: "
                    f"o efeito intra-faixa é amplificado por características demográficas. "
                    f"Cuidado em recomendar essa ação como causal."
                )

        # E-value visual
        st.markdown("#### E-value — sensibilidade ao confounding não medido")
        ev = float(row["e_value"])
        st.markdown(
            f"Para anular o efeito observado, um confounder não medido precisaria estar "
            f"associado a **tanto o uso de {row['especialidade']} quanto ao churn** com força "
            f"mínima de **RR = {ev:.2f}**."
        )
        if ev >= 2.0:
            st.success(
                f"🟢 **Robusto.** Confounders modestos (RR < 2.0) não conseguem anular o efeito. "
                f"Sinal forte de causalidade — vale priorizar a ação."
            )
        elif ev >= 1.5:
            st.warning(
                f"🟡 **Moderado.** Confounders de força ~1.5-2.0 podem explicar o efeito. "
                f"Vale A/B testar pra confirmar antes de escalar a ação."
            )
        else:
            st.error(
                f"🔴 **Sensível.** Confounders modestos (RR ~{ev:.2f}) já anulam o efeito. "
                f"**Não escalar sem A/B test.** O efeito observado pode ser viés."
            )

        # Heterogeneidade — efeito por subgrupo dentro da especialidade e duração
        st.markdown("#### Heterogeneidade — efeito por subgrupo (todas as faixas do plano)")
        het = wide[
            (wide["duracao"] == dur_sel) & (wide["especialidade"] == row["especialidade"])
        ].copy().sort_values("band")
        het_view = het[["band", "n_usou", "n_nao_usou",
                         "churn_rate_usou", "churn_rate_nao_usou",
                         "delta_pp", "ci_lo", "ci_hi", "p", "sig", "e_value"]].copy()
        het_view["IC 95%"] = het_view.apply(
            lambda r: f"[{r['ci_lo']:+.1f}, {r['ci_hi']:+.1f}]", axis=1
        )
        het_view["Δ (p.p.)"] = het_view["delta_pp"].apply(lambda v: f"{v:+.1f}")
        het_view["E-value"] = het_view["e_value"].apply(lambda v: f"{v:.2f}")
        het_view["p-valor"] = het_view["p"].apply(
            lambda v: "<0,001" if v < 0.001 else f"{v:.3f}"
        )
        het_disp = het_view[[
            "band", "n_usou", "n_nao_usou",
            "churn_rate_usou", "churn_rate_nao_usou",
            "Δ (p.p.)", "IC 95%", "p-valor", "sig", "E-value",
        ]].rename(columns={
            "band": "Faixa", "n_usou": "N usou", "n_nao_usou": "N não usou",
            "churn_rate_usou": "Churn usou (%)", "churn_rate_nao_usou": "Churn não usou (%)",
            "sig": "Sig.",
        })
        st.dataframe(het_disp, hide_index=True, use_container_width=True)

        # Forest plot da heterogeneidade
        if len(het) > 1:
            fig_h = go.Figure()
            fig_h.add_trace(go.Scatter(
                x=het["delta_pp"], y=het["band"].astype(str),
                mode="markers",
                marker=dict(
                    size=12,
                    color=[BAND_5_COLORS[b] for b in het["band"].astype(str)],
                    line=dict(width=2, color="white"),
                ),
                error_x=dict(
                    type="data", symmetric=False,
                    array=(het["ci_hi"] - het["delta_pp"]).abs().values,
                    arrayminus=(het["delta_pp"] - het["ci_lo"]).abs().values,
                    color="rgba(0,0,0,0.4)", thickness=2, width=8,
                ),
                showlegend=False,
            ))
            fig_h.add_vline(x=0, line_dash="dash", line_color="gray")
            fig_h.update_layout(
                title=f"Forest plot · {row['especialidade']} (plano {dur_sel}m)",
                xaxis_title="Δ p.p. (positivo = uso reduz churn dentro da faixa)",
                yaxis_title="Faixa do score",
                height=300,
                margin=dict(l=20, r=20, t=50),
            )
            st.plotly_chart(fig_h, use_container_width=True)

# ───────────────────────────────────────────────────────────────────────────
# TAB 3: PLANO DE MEDIÇÃO A/B
# ───────────────────────────────────────────────────────────────────────────
with tab_ab:
    st.markdown("### Plano de medição A/B")
    st.caption(
        "Tamanho amostral por braço para detectar um Δ esperado com poder estatístico padrão. "
        "Use isso para dimensionar pilotos da ação no público real."
    )

    cols_in = st.columns(4)
    base_pct = cols_in[0].number_input("Churn base (%)", min_value=10.0, max_value=90.0,
                                        value=55.0, step=1.0,
                                        help="Churn esperado no grupo controle (não tratado).")
    delta_pp_ab = cols_in[1].number_input("Δ a detectar (p.p.)", min_value=0.5, max_value=15.0,
                                            value=3.0, step=0.5,
                                            help="Diferença mínima que você quer ser capaz de detectar.")
    alpha = cols_in[2].selectbox("α (significância)", options=[0.05, 0.01, 0.10],
                                   index=0, help="Probabilidade de falso positivo.")
    power = cols_in[3].selectbox("Power (1-β)", options=[0.80, 0.90, 0.95],
                                   index=0, help="Probabilidade de detectar o efeito se ele existe.")

    n_per_arm = ab_sample_size(base_pct, delta_pp_ab, alpha=alpha, power=power)
    n_total = 2 * n_per_arm

    # Vencimentos por mês — estimativa simples a partir do total
    vencimentos_por_mes = total_real / 12 if total_real > 0 else 0
    meses_para_coletar = (n_total / vencimentos_por_mes) if vencimentos_por_mes > 0 else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("N por braço", f"{n_per_arm:,}")
    c2.metric("N total", f"{n_total:,}")
    c3.metric("Meses para coletar", f"{meses_para_coletar:.1f}",
              help=f"Assumindo ~{int(vencimentos_por_mes):,} vencimentos/mês no plano {dur_sel}m.")

    # Pré-povoar com a ação top para mostrar plano específico
    if not f.empty:
        st.markdown("---")
        st.markdown("#### Plano específico para as 3 ações top")

        top3 = f.head(3).copy()
        for _, r in top3.iterrows():
            with st.expander(
                f"#{int(r['#'])} · {BAND_5_LABELS[r['band']]} · {r['especialidade']} "
                f"(Δ esperado: +{r['delta_pp']:.1f} p.p.)",
                expanded=False,
            ):
                # Calcula sample size pra essa ação
                base_a = (r["churn_rate_nao_usou"] + r["churn_rate_usou"]) / 2
                n_arm_a = ab_sample_size(base_a, r["delta_pp"], alpha=alpha, power=power)
                publico_disp = int(r["n_nao_usou"])
                cobertura = (n_arm_a / publico_disp * 100) if publico_disp > 0 else 0

                ca, cb, cc = st.columns(3)
                ca.metric("N por braço", f"{n_arm_a:,}")
                cb.metric("Público disponível", f"{publico_disp:,}",
                          help="Quem ainda não usou a especialidade na faixa")
                cc.metric("% do público necessário",
                          f"{cobertura:.1f}%",
                          delta=("✅ Viável" if cobertura <= 100 else "⚠️ Insuficiente"),
                          delta_color="off")

                st.markdown(f"""
                **Como rodar:**
                1. **Listar elegíveis:** clientes no plano {dur_sel}m, na faixa {row['band'] if 'row' in dir() else r['band']}, que ainda não usaram {r['especialidade']}.
                2. **Aleatorizar 50/50** entre grupo tratado e controle ({n_arm_a:,} por braço).
                3. **Intervenção:** régua de engajamento direcionada a {r['especialidade']} (SMS/WhatsApp/ligação) no grupo tratado.
                4. **Janela de observação:** até o próximo vencimento de contrato.
                5. **Métrica primária:** taxa de churn (não renovação automática) ao fim do contrato.
                6. **Análise:** z-test bicaudal de proporções, α={alpha}, com IC 95% da diferença.
                """)

    st.markdown("---")
    with st.expander("📐 Como interpretar e usar o A/B", expanded=False):
        st.markdown(f"""
        **Premissas da fórmula:**
        - Z-test bicaudal para diferença de proporções
        - Mesmo N nos dois braços (alocação 50/50)
        - Variância estimada via média das duas proporções

        **Sample size é o N por braço** — você precisa de 2N elegíveis no total.
        Se o tamanho é maior que o público disponível, **reduza o critério** (E-value mínimo)
        ou aceite poder estatístico menor, ou rode em ondas (várias safras).

        **O que medir:**
        - **Primária:** churn no fim do contrato (mesmo definição do score: `churn_renovacao_automatica_sn = S`).
        - **Secundárias:** consumo da especialidade tratada (engajamento real), satisfação NPS.

        **Cuidados:**
        - **Aleatorização real:** não escolher quem ganha a intervenção — usar hash ou random seed.
        - **Pré-registrar a análise:** decidir antes da coleta qual será o teste estatístico
          e o critério de significância. Evita p-hacking.
        - **Intent-to-treat:** analisar todos os elegíveis no grupo tratado, mesmo os que não receberam a ação. Isso preserva a aleatorização.

        **Validação cruzada com E-value:**
        Se a ação tem E-value baixo (sensível), o A/B é **essencial** antes de escalar.
        Se E-value é alto (robusto), o A/B confirma e dá tamanho de efeito real para projeção financeira.
        """)

st.markdown("---")
with st.expander("📖 Metodologia · Score 2.0 e E-value", expanded=False):
    st.markdown("""
    **Score 2.0 (WLS estendido):**
    Treinamos UM modelo por (duração × especialidade) sobre `consumo_dentro_perfil`:
    `logit(churn) ~ ciclo + faixa_etaria + crônico + composicao_titular + uso(especialidade)`.
    O coeficiente da dummy `uso=usou` é o **efeito ajustado** controlando todas as 4 variáveis
    demográficas simultaneamente. Se o efeito ajustado preserva o efeito observado dentro da
    faixa, ganhamos evidência cruzada de que a associação não é só artefato da estratificação.

    **E-value (VanderWeele & Ding, 2017):**
    Quantifica a sensibilidade do resultado a confounding não medido. Especificamente:
    é a **menor força de associação** (em escala de Risk Ratio) que um confounder não medido
    precisaria ter com **tanto o tratamento quanto o desfecho** para explicar completamente
    o efeito observado.

    | E-value | Interpretação |
    |---|---|
    | ≥ 2.0 | 🟢 **Robusto.** Confounders modestos não anulam o efeito |
    | 1.5 - 2.0 | 🟡 **Moderado.** Vale A/B para confirmar |
    | < 1.5 | 🔴 **Sensível.** Não escalar sem A/B |

    **Tab A/B:** complementa a evidência observacional. Como temos snapshot (sem desenho
    experimental), o A/B é o único caminho pra confirmar causalidade. Os tamanhos amostrais
    indicam quanto público preciso pra detectar o Δ esperado com poder estatístico padrão.

    **Limitações importantes pro comitê:**
    1. **Confounders não medidos persistem.** Severidade clínica, motivação pessoal, eventos
       de vida — nenhum desses está no perfil. E-value baixo é o sintoma disso.
    2. **Snapshot único:** não distinguimos quem usou ANTES vs DEPOIS da decisão de churn.
       A/B com observação prospectiva resolve.
    3. **Heterogeneidade não interagida:** o Score 2.0 assume efeito constante entre perfis.
       A tabela de heterogeneidade mostra que isso pode não ser verdade — refletir
       interações é trabalho futuro.
    """)
