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
    assign_bands,
    fit_wls_per_duracao,
    sig_stars,
    z_test_proportions,
)

bands_mode = st.session_state.get("bands_mode", BANDS_MODE_ASYMMETRIC)

st.title("🔄 Transição entre Faixas — Análise Causal")
st.caption(
    f"Dentro de cada faixa do score, quem usou cada especialidade tem churn diferente? "
    f"Cada comparação é controlada por perfil (4 vars) e testada com z-test bicaudal. "
    f"**Cortes: {BANDS_MODE_LABELS[bands_mode]}** (altere na sidebar)."
)


@st.cache_data
def load_cruzamento():
    return pd.read_csv("results_comite/storytelling_cruzamento.csv")


@st.cache_data
def load_consumo():
    return pd.read_csv("results_comite/consumo_dentro_perfil.csv")


@st.cache_data
def compute_perfil_to_faixa(mode: str):
    """Treina WLS por duração, atribui faixa a cada perfil, retorna mapeamento (perfil → faixa)."""
    df_crz = load_cruzamento()
    df_crz["duracao"] = df_crz["duracao"].astype(str)
    models = fit_wls_per_duracao(df_crz, features=WLS_FEATURES_DEFAULT, refs=WLS_REFS_DEFAULT)
    rows = []
    for dur, m in models.items():
        scored = assign_bands(m["profiles"], mode=mode)
        for _, r in scored.iterrows():
            rows.append({
                "duracao": dur, "ciclo": r["ciclo"], "faixa_etaria": r["faixa_etaria"],
                "cronico": r["cronico"], "composicao_titular": r["composicao_titular"],
                "band": str(r["band"]), "score": int(r["score"]),
            })
    return pd.DataFrame(rows)


try:
    df_cons = load_consumo()
    perfil_band = compute_perfil_to_faixa(bands_mode)
except FileNotFoundError as e:
    st.error(
        f"CSV não encontrado: `{e.filename}`. "
        f"Rode `queries_comite/consumo_dentro_perfil.sql` no BigQuery e salve em "
        f"`results_comite/consumo_dentro_perfil.csv`."
    )
    st.stop()

df_cons["duracao"] = df_cons["duracao"].astype(str)
key_cols = ["duracao", "ciclo", "faixa_etaria", "cronico", "composicao_titular"]
df = df_cons.merge(perfil_band[key_cols + ["band"]], on=key_cols, how="inner")

# ═══════════════════════════════════════════════════════════════════════════
# AGREGA POR (duração, faixa, especialidade, uso) E APLICA Z-TEST
# ═══════════════════════════════════════════════════════════════════════════
agg = df.groupby(["duracao", "band", "especialidade", "uso"], as_index=False).agg(
    total_contratos=("total_contratos", "sum"),
    churners=("churners", "sum"),
)
agg["churn_rate"] = round(100.0 * agg["churners"] / agg["total_contratos"], 1)

wide = agg.pivot_table(
    index=["duracao", "band", "especialidade"],
    columns="uso",
    values=["total_contratos", "churners", "churn_rate"],
    aggfunc="sum",
).reset_index()
wide.columns = ["_".join(str(x) for x in c if x != "").rstrip("_") for c in wide.columns]
wide = wide.dropna(subset=["churn_rate_usou", "churn_rate_nao_usou"]).reset_index(drop=True)


def _ztest(row):
    n1 = int(row["total_contratos_nao_usou"]); x1 = int(row["churners_nao_usou"])
    n2 = int(row["total_contratos_usou"]);     x2 = int(row["churners_usou"])
    t = z_test_proportions(n1, x1, n2, x2)
    return pd.Series({
        "delta_pp": round(t["diff"], 2),
        "ci_lo": round(t["ci_lo"], 2),
        "ci_hi": round(t["ci_hi"], 2),
        "p": t["p"],
        "sig": sig_stars(t["p"]),
    })


wide = pd.concat([wide, wide.apply(_ztest, axis=1)], axis=1)
wide["n_usou"] = wide["total_contratos_usou"].astype(int)
wide["n_nao_usou"] = wide["total_contratos_nao_usou"].astype(int)
wide["pct_usou"] = round(100 * wide["n_usou"] / (wide["n_usou"] + wide["n_nao_usou"]), 1)
wide["band"] = pd.Categorical(wide["band"], categories=BAND_5_ORDER, ordered=True)

# ═══════════════════════════════════════════════════════════════════════════
# SIDEBAR — filtros
# ═══════════════════════════════════════════════════════════════════════════
st.sidebar.markdown("### 🔍 Filtros")
dur_sel = st.sidebar.radio(
    "Duração:", options=["6", "12"], index=0,
    format_func=lambda x: f"{x} meses", key="trans_dur",
)
min_n = st.sidebar.number_input(
    "Mínimo de contratos no 'usou':",
    min_value=30, max_value=5000, value=100, step=50,
    help="Especialidades com poucos usuários têm churn instável.",
)
only_sig = st.sidebar.checkbox(
    "Mostrar apenas significativos (p < 0,05)", value=False,
    help="Filtra para alavancas onde a diferença passa no z-test.",
)

wide_d = wide[(wide["duracao"] == dur_sel) & (wide["n_usou"] >= min_n)].copy()
if only_sig:
    wide_d = wide_d[wide_d["p"] < 0.05]

if wide_d.empty:
    st.warning("Sem dados após filtros. Reduza o mínimo ou desabilite o filtro de significância.")
    st.stop()

# ═══════════════════════════════════════════════════════════════════════════
# HEATMAP — efeito do uso (Δ p.p.) × faixa, com marcadores de significância
# ═══════════════════════════════════════════════════════════════════════════
st.markdown(f"### Mapa do efeito por especialidade × faixa — plano {dur_sel}m")
st.caption(
    "Δ p.p. = churn de quem **não usou** − churn de quem **usou** (dentro da faixa). "
    "Verde = usar reduz churn · Vermelho = usar aumenta. "
    "`*` `**` `***` denotam significância estatística (p < 0,05 / 0,01 / 0,001)."
)

heat = wide_d.pivot_table(
    index="especialidade", columns="band", values="delta_pp", aggfunc="mean", observed=True
)
sig_pivot = wide_d.pivot_table(
    index="especialidade", columns="band", values="sig", aggfunc="first", observed=True
)
heat = heat.reindex(columns=[b for b in BAND_5_ORDER if b in heat.columns])
sig_pivot = sig_pivot.reindex(columns=heat.columns)
heat = heat.reindex(heat.abs().mean(axis=1).sort_values(ascending=False).index)
sig_pivot = sig_pivot.reindex(heat.index)

text_matrix = []
for esp in heat.index:
    row_txt = []
    for b in heat.columns:
        v = heat.loc[esp, b]
        s = sig_pivot.loc[esp, b] if b in sig_pivot.columns else "n.s."
        if pd.isna(v):
            row_txt.append("")
        else:
            sig_mark = s if s and s != "n.s." else ""
            row_txt.append(f"{v:+.1f}{sig_mark}")
    text_matrix.append(row_txt)

fig_heat = go.Figure(go.Heatmap(
    z=heat.values,
    x=[str(c) for c in heat.columns],
    y=heat.index,
    text=text_matrix,
    texttemplate="%{text}",
    colorscale="RdYlGn",
    zmid=0,
    colorbar=dict(title="Δ p.p."),
    hovertemplate="<b>%{y}</b> · %{x}<br>Δ: %{z:.1f} p.p.<extra></extra>",
))
fig_heat.update_layout(
    height=max(380, 30 * len(heat) + 100),
    margin=dict(t=30, b=20),
    xaxis=dict(title=""),
    yaxis=dict(title=""),
)
st.plotly_chart(fig_heat, use_container_width=True)

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════
# TOP ALAVANCAS POR FAIXA
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("### Top alavancas por faixa")
st.caption(
    "Especialidades com maior Δ positivo significativo (p < 0,05) — candidatos a "
    "alavanca de transição (mover cliente da faixa atual para uma mais segura)."
)

faixas_disponiveis = [b for b in BAND_5_ORDER if b in wide_d["band"].unique().tolist()]
cols = st.columns(min(5, len(faixas_disponiveis)))

for col_widget, bkt in zip(cols, faixas_disponiveis):
    with col_widget:
        st.markdown(f"#### {BAND_5_LABELS[bkt]}")
        sub = wide_d[(wide_d["band"] == bkt) & (wide_d["p"] < 0.05) & (wide_d["delta_pp"] > 0)]
        sub = sub.sort_values("delta_pp", ascending=False).head(4)

        if sub.empty:
            st.caption("Sem alavancas com efeito significativo nesta faixa.")
            continue

        for _, r in sub.iterrows():
            st.markdown(
                f"""<div style="border-left: 4px solid {BAND_5_COLORS[bkt]}; padding: 7px 10px; margin: 5px 0; background-color: rgba(0,0,0,0.02);">
<b>{r['especialidade']}</b><br>
<small>
Usou: <b>{r['churn_rate_usou']:.1f}%</b> · Não usou: <b>{r['churn_rate_nao_usou']:.1f}%</b><br>
Δ: <span style="color:#388e3c; font-weight:bold">+{r['delta_pp']:.1f} p.p. {r['sig']}</span><br>
IC 95%: [{r['ci_lo']:+.1f}, {r['ci_hi']:+.1f}]<br>
Público (não usou): {int(r['n_nao_usou']):,} ({100 - r['pct_usou']:.0f}% da faixa)
</small>
</div>""",
                unsafe_allow_html=True,
            )

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════
# DRILL POR ESPECIALIDADE — gráfico de churn usou vs não usou por faixa
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("### Drill por especialidade")
esp_sel = st.selectbox(
    "Selecione a especialidade:",
    options=sorted(wide_d["especialidade"].unique()),
    key="trans_esp",
)

sub_esp = wide_d[wide_d["especialidade"] == esp_sel].copy().sort_values("band")

fig_esp = go.Figure()
fig_esp.add_trace(go.Bar(
    name="Não usou",
    x=sub_esp["band"].astype(str),
    y=sub_esp["churn_rate_nao_usou"],
    text=sub_esp["churn_rate_nao_usou"].apply(lambda v: f"{v:.1f}%"),
    textposition="outside",
    marker_color="#90a4ae",
))
fig_esp.add_trace(go.Bar(
    name="Usou",
    x=sub_esp["band"].astype(str),
    y=sub_esp["churn_rate_usou"],
    text=sub_esp["churn_rate_usou"].apply(lambda v: f"{v:.1f}%"),
    textposition="outside",
    marker_color="#1565c0",
))
fig_esp.update_layout(
    title=f"{esp_sel} · plano {dur_sel}m — churn usou vs não usou por faixa",
    barmode="group",
    xaxis=dict(title="Faixa do score"),
    yaxis=dict(title="Churn (%)", range=[0, 100]),
    height=400,
    legend=dict(orientation="h", y=1.12),
)
st.plotly_chart(fig_esp, use_container_width=True)

tbl = sub_esp[["band", "n_usou", "n_nao_usou", "pct_usou",
               "churn_rate_usou", "churn_rate_nao_usou",
               "delta_pp", "ci_lo", "ci_hi", "p", "sig"]].copy()
tbl["IC 95%"] = tbl.apply(lambda r: f"[{r['ci_lo']:+.1f}, {r['ci_hi']:+.1f}]", axis=1)
tbl["p-valor"] = tbl["p"].apply(lambda v: "<0,001" if v < 0.001 else f"{v:.3f}")
tbl["Δ (p.p.)"] = tbl["delta_pp"].apply(lambda v: f"{v:+.1f}")
tbl = tbl[["band", "n_usou", "n_nao_usou", "pct_usou",
           "churn_rate_usou", "churn_rate_nao_usou",
           "Δ (p.p.)", "IC 95%", "p-valor", "sig"]]
tbl.columns = ["Faixa", "N usou", "N não usou", "% usou",
               "Churn usou (%)", "Churn não usou (%)",
               "Δ (p.p.)", "IC 95%", "p-valor", "Sig."]
st.dataframe(tbl, hide_index=True, use_container_width=True)

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════
# COMPARATIVO ENTRE DURAÇÕES (resumo executivo)
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("### Comparativo entre durações: especialidades consistentes")
st.caption(
    "Especialidades cujo efeito (Δ médio significativo) aparece em **ambas as durações** "
    "são os candidatos mais robustos a ações de retenção."
)


def avg_delta_per_dur(sub: pd.DataFrame) -> pd.Series:
    s = sub[(sub["p"] < 0.05) & (sub["delta_pp"] > 0)]
    if s.empty:
        return pd.Series({"avg_delta": np.nan, "n_faixas_sig": 0})
    w = s["n_nao_usou"].astype(float)
    avg = float((s["delta_pp"] * w).sum() / w.sum()) if w.sum() > 0 else np.nan
    return pd.Series({"avg_delta": round(avg, 1), "n_faixas_sig": len(s)})


resumo = (
    wide[wide["n_usou"] >= min_n]
    .groupby(["especialidade", "duracao"], group_keys=False)
    .apply(avg_delta_per_dur)
    .reset_index()
)
pivot_dur = resumo.pivot_table(
    index="especialidade", columns="duracao", values=["avg_delta", "n_faixas_sig"], aggfunc="sum"
)
pivot_dur.columns = ["_".join(map(str, c)) for c in pivot_dur.columns]
pivot_dur = pivot_dur.reset_index().fillna(0)

mask = (pivot_dur.get("n_faixas_sig_6", 0) > 0) | (pivot_dur.get("n_faixas_sig_12", 0) > 0)
pivot_dur = pivot_dur[mask].copy()

if not pivot_dur.empty:
    pivot_dur["consistencia"] = (
        (pivot_dur.get("n_faixas_sig_6", 0) > 0) & (pivot_dur.get("n_faixas_sig_12", 0) > 0)
    )
    pivot_dur = pivot_dur.sort_values(
        ["consistencia", "avg_delta_6", "avg_delta_12"], ascending=[False, False, False]
    )

    disp = pivot_dur.copy()
    disp["Δ médio 6m"] = disp.get("avg_delta_6", 0).apply(lambda v: f"+{v:.1f}" if v > 0 else "—")
    disp["Δ médio 12m"] = disp.get("avg_delta_12", 0).apply(lambda v: f"+{v:.1f}" if v > 0 else "—")
    disp["# faixas sig 6m"] = disp.get("n_faixas_sig_6", 0).astype(int)
    disp["# faixas sig 12m"] = disp.get("n_faixas_sig_12", 0).astype(int)
    disp["Consistência"] = disp["consistencia"].map({True: "✅ Ambas durações", False: "Só uma duração"})

    st.dataframe(
        disp[["especialidade", "Δ médio 6m", "# faixas sig 6m",
              "Δ médio 12m", "# faixas sig 12m", "Consistência"]]
            .rename(columns={"especialidade": "Especialidade"}),
        hide_index=True, use_container_width=True,
    )
else:
    st.info("Nenhuma especialidade com efeito significativo no recorte atual.")

st.markdown("---")

with st.expander("📖 Metodologia · o que estamos medindo de fato", expanded=False):
    st.markdown("""
    **Controle do confound consumo × ciclo:**
    O agregado bruto "usou vs não usou" é enviesado — 1o contrato consome mais E cancela mais.
    Esta análise primeiro agrega o churn dentro de cada perfil (ciclo × faixa etária × crônico),
    onde o ciclo já está controlado, e só depois rola pra faixa do score. O Δ exibido é o efeito
    **dentro de perfis homogêneos**.

    **Teste:** z-test bicaudal para diferença de proporções, IC 95% normal-approximation,
    nível convencional p < 0,05. Aplicado em cada combinação (duração × faixa × especialidade).

    **Interpretação do Δ:**
    - **Δ positivo significativo (*)**: usar a especialidade está associado a menor churn
      dentro da faixa. Candidato a **alavanca de retenção / transição** — encorajar o uso
      pode mover o cliente para uma faixa de menor risco.
    - **Δ negativo significativo**: usar está associado a maior churn. Possíveis causas:
      consulta motivada por insatisfação clínica, ou problema crônico complexo que correlaciona
      com baixo engajamento — não é uma alavanca, é um sinal.
    - **n.s.**: sem evidência. Pode ser falta de poder estatístico (volume baixo) ou efeito
      genuinamente nulo.

    **Limitações conhecidas (importante reconhecer no comitê):**
    1. **Causalidade ainda é parcial.** Mesmo controlando por perfil demográfico, podem existir
       fatores não observados (severidade clínica, intensidade do problema, motivação pessoal)
       que afetam tanto a busca por especialidade quanto a decisão de não renovar. Para ir além,
       seria necessário A/B testar a intervenção (encorajar uso de X em metade do público alvo).
    2. **Snapshot único.** Cada contrato é observado uma vez — não sabemos se o uso veio antes
       ou depois da decisão de churn. Estrutura modular permite migrar pra mês-a-mês depois.
    3. **Especialidades com pouco volume** têm CIs largos. O filtro de "mínimo de contratos
       que usaram" mitiga isso.

    **Resumo executivo:** prioriza especialidades cujo efeito aparece em **ambas as durações** —
    robustez cross-plano é o indicador mais forte de que a alavanca é genuína (não artefato
    de mix específico de uma duração).
    """)
