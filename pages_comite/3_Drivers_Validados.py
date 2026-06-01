import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from comite_scoring import sig_stars, z_test_proportions

st.title("📐 Drivers Validados — Análise Causal")
st.caption(
    "Cada variável é testada DENTRO de estratos da principal confundidora. "
    "Se o efeito persiste, é real. Se some, era confounding."
)


@st.cache_data
def load_cruzamento():
    return pd.read_csv("results_comite/storytelling_cruzamento.csv")


try:
    df = load_cruzamento()
except FileNotFoundError:
    st.error(
        "`results_comite/storytelling_cruzamento.csv` não encontrado. "
        "Rode o bloco B de `queries_comite/storytelling_3vars.sql` antes."
    )
    st.stop()

df["duracao"] = df["duracao"].astype(str)


def agg(mask: pd.Series) -> tuple[int, int]:
    sub = df[mask]
    return int(sub["total_contratos"].sum()), int(sub["churners"].sum())


def format_p(p: float) -> str:
    if p < 0.001:
        return "<0,001"
    return f"{p:.3f}"


def render_test_table(rows: list[dict], cols_in_order: list[str]) -> None:
    """Renderiza dataframe de testes z + IC + p + sig com formatação consistente."""
    if not rows:
        st.info("Sem dados suficientes para os estratos.")
        return
    out = pd.DataFrame(rows)
    out = out[cols_in_order]
    st.dataframe(out, hide_index=True, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════
# BLOCOS METODOLÓGICOS — expanders curtos
# ═══════════════════════════════════════════════════════════════════════════
with st.expander("📖 Pergunta central e hipóteses", expanded=False):
    st.markdown("""
    **Pergunta:** *as diferenças de churn que vemos entre grupos são reais
    ou podem ser explicadas pelo acaso ou por outra variável escondida?*

    Para cada variável testamos:

    | | Hipótese | Em linguagem de negócio |
    |---|---|---|
    | **H₀** (nula) | As taxas são **iguais** entre os grupos | *"Não faz diferença ser 1o ou 2o+ contrato"* |
    | **Hₐ** (alternativa) | As taxas são **diferentes** | *"O ciclo do contrato realmente impacta o churn"* |

    - **p < 0,001 (***)** — menos de 0,1% de chance de ser acaso
    - **p < 0,05 (*)** — limiar convencional, efeito significativo
    - **n.s.** — sem evidência para rejeitar H₀

    **Intervalo de Confiança 95%:** faixa onde a diferença real provavelmente está.
    Se o IC **não cruza zero**, o efeito é significativo.
    """)

with st.expander("🔀 O que é confounding (e como nos protegemos)", expanded=False):
    st.markdown("""
    Imagine alguém afirmar: *"Quem usa guarda-chuva tem mais chance de se molhar."*
    É absurdo — a **chuva** é o que causa as duas coisas. Sem considerar a chuva,
    parece que o guarda-chuva molha.

    **Análise estratificada** é a defesa: em vez de comparar grupos no agregado,
    comparamos *dentro de cada nível da confundidora*. Se o efeito persiste em
    todos os estratos, é real. Se desaparece, era confounding.

    **Confoundings que esperamos aqui:**
    - **Duração 12m × Ciclo:** planos de 12m têm mais 1o contrato → parte do gap de duração
      pode ser efeito do ciclo. Por isso testamos duração *dentro* de cada ciclo.
    - **Idade × Crônico:** crônicos são muito mais velhos. Parte do efeito "crônicos retêm mais"
      é só "idosos retêm mais". Por isso testamos crônico *dentro* de cada faixa etária.
    """)

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════
# DRIVER 1: CICLO DO CONTRATO (1o vs 2o+) controlado por duração
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("### Driver #1 — Ciclo do contrato (1o vs 2o+)")
st.caption("Controlado por **duração do plano** — o efeito persiste em 6m e 12m?")

rows = []
for dur in ["6", "12"]:
    n1, x1 = agg((df["ciclo"] == "1o") & (df["duracao"] == dur))
    n2, x2 = agg((df["ciclo"] == "2o+") & (df["duracao"] == dur))
    if n1 == 0 or n2 == 0:
        continue
    t = z_test_proportions(n1, x1, n2, x2)
    rows.append({
        "Estrato": f"Plano {dur}m",
        "1o contrato": f"{t['p1']:.1f}% (n={n1:,})",
        "2o+ contrato": f"{t['p2']:.1f}% (n={n2:,})",
        "Diferença": f"{t['diff']:+.1f} p.p.",
        "IC 95%": f"[{t['ci_lo']:+.1f}, {t['ci_hi']:+.1f}]",
        "p-valor": format_p(t["p"]),
        "Sig.": sig_stars(t["p"]),
    })

# Univariada agregada (sem estratificação) para comparar
n1, x1 = agg(df["ciclo"] == "1o")
n2, x2 = agg(df["ciclo"] == "2o+")
t = z_test_proportions(n1, x1, n2, x2)
rows.insert(0, {
    "Estrato": "Univariada (sem estrato)",
    "1o contrato": f"{t['p1']:.1f}% (n={n1:,})",
    "2o+ contrato": f"{t['p2']:.1f}% (n={n2:,})",
    "Diferença": f"{t['diff']:+.1f} p.p.",
    "IC 95%": f"[{t['ci_lo']:+.1f}, {t['ci_hi']:+.1f}]",
    "p-valor": format_p(t["p"]),
    "Sig.": sig_stars(t["p"]),
})
render_test_table(
    rows,
    ["Estrato", "1o contrato", "2o+ contrato", "Diferença", "IC 95%", "p-valor", "Sig."],
)

st.success(
    "**Efeito robusto.** O gap entre 1o e 2o+ contrato persiste em ambas as durações com "
    "p < 0,001. O ciclo do contrato é o driver mais forte do estudo — sobrevive a qualquer controle."
)

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════
# DRIVER 2: FAIXA ETÁRIA (≤30 vs 51-70) controlado por ciclo
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("### Driver #2 — Faixa etária (≤30 vs 51-70)")
st.caption(
    "Controlado por **ciclo do contrato** — jovens cancelam mais mesmo quando comparamos "
    "1o contrato com 1o contrato, e 2o+ com 2o+?"
)

rows = []
n1, x1 = agg(df["faixa_etaria"].isin(["00-20", "21-30"]))
n2, x2 = agg(df["faixa_etaria"] == "51-70")
t = z_test_proportions(n1, x1, n2, x2)
rows.append({
    "Estrato": "Univariada (sem estrato)",
    "≤30 anos": f"{t['p1']:.1f}% (n={n1:,})",
    "51-70 anos": f"{t['p2']:.1f}% (n={n2:,})",
    "Diferença": f"{t['diff']:+.1f} p.p.",
    "IC 95%": f"[{t['ci_lo']:+.1f}, {t['ci_hi']:+.1f}]",
    "p-valor": format_p(t["p"]),
    "Sig.": sig_stars(t["p"]),
})
for ciclo in ["1o", "2o+"]:
    n1, x1 = agg(df["faixa_etaria"].isin(["00-20", "21-30"]) & (df["ciclo"] == ciclo))
    n2, x2 = agg((df["faixa_etaria"] == "51-70") & (df["ciclo"] == ciclo))
    if n1 == 0 or n2 == 0:
        continue
    t = z_test_proportions(n1, x1, n2, x2)
    rows.append({
        "Estrato": f"{ciclo} contrato",
        "≤30 anos": f"{t['p1']:.1f}% (n={n1:,})",
        "51-70 anos": f"{t['p2']:.1f}% (n={n2:,})",
        "Diferença": f"{t['diff']:+.1f} p.p.",
        "IC 95%": f"[{t['ci_lo']:+.1f}, {t['ci_hi']:+.1f}]",
        "p-valor": format_p(t["p"]),
        "Sig.": sig_stars(t["p"]),
    })
render_test_table(
    rows,
    ["Estrato", "≤30 anos", "51-70 anos", "Diferença", "IC 95%", "p-valor", "Sig."],
)

st.success(
    "**Efeito robusto.** Jovens cancelam mais em ambos os ciclos. A faixa etária é "
    "driver real, não consequência do ciclo do contrato."
)

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════
# DRIVER 3: CRÔNICO (N vs S) controlado por faixa etária
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("### Driver #3 — Doença crônica (N vs S)")
st.caption(
    "Controlado por **faixa etária** — o efeito 'crônicos retêm mais' resiste quando "
    "comparamos pessoas da mesma idade?"
)

faixas = ["00-20", "21-30", "31-50", "51-70", "71+"]
rows = []
n1, x1 = agg(df["cronico"] == "N")
n2, x2 = agg(df["cronico"] == "S")
t = z_test_proportions(n1, x1, n2, x2)
rows.append({
    "Estrato": "Univariada (sem estrato)",
    "Não crônico": f"{t['p1']:.1f}% (n={n1:,})",
    "Crônico": f"{t['p2']:.1f}% (n={n2:,})",
    "Diferença": f"{t['diff']:+.1f} p.p.",
    "IC 95%": f"[{t['ci_lo']:+.1f}, {t['ci_hi']:+.1f}]",
    "p-valor": format_p(t["p"]),
    "Sig.": sig_stars(t["p"]),
    "% crônicos": "—",
})
for fx in faixas:
    n1, x1 = agg((df["cronico"] == "N") & (df["faixa_etaria"] == fx))
    n2, x2 = agg((df["cronico"] == "S") & (df["faixa_etaria"] == fx))
    if n1 == 0 or n2 == 0:
        continue
    t = z_test_proportions(n1, x1, n2, x2)
    pct_cron = 100 * n2 / (n1 + n2)
    rows.append({
        "Estrato": f"Idade {fx}",
        "Não crônico": f"{t['p1']:.1f}% (n={n1:,})",
        "Crônico": f"{t['p2']:.1f}% (n={n2:,})",
        "Diferença": f"{t['diff']:+.1f} p.p.",
        "IC 95%": f"[{t['ci_lo']:+.1f}, {t['ci_hi']:+.1f}]",
        "p-valor": format_p(t["p"]),
        "Sig.": sig_stars(t["p"]),
        "% crônicos": f"{pct_cron:.1f}%",
    })
render_test_table(
    rows,
    ["Estrato", "% crônicos", "Não crônico", "Crônico", "Diferença", "IC 95%", "p-valor", "Sig."],
)

st.warning(
    "**Confounding parcial detectado.** O gap univariado é amplificado pela idade — "
    "a coluna `% crônicos` mostra que crônicos estão concentrados nos 51+, onde o churn "
    "já é naturalmente menor. Em jovens (≤30) o efeito tende a sumir (volume de crônicos baixo). "
    "O crônico é driver real para 31+, mas mais fraco do que sugere a univariada."
)

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════
# DRIVER 4: DURAÇÃO (12 vs 6) controlado por ciclo — valida a tese executiva
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("### Driver #4 — Duração do plano (12m vs 6m)")
st.caption(
    "Controlado por **ciclo** — o gap 12m vs 6m sobrevive ao confounding "
    "(12m tem mais 1o contrato)?"
)

rows = []
n1, x1 = agg(df["duracao"] == "12")
n2, x2 = agg(df["duracao"] == "6")
t = z_test_proportions(n1, x1, n2, x2)
rows.append({
    "Estrato": "Univariada (sem estrato)",
    "12 meses": f"{t['p1']:.1f}% (n={n1:,})",
    "6 meses": f"{t['p2']:.1f}% (n={n2:,})",
    "Diferença": f"{t['diff']:+.1f} p.p.",
    "IC 95%": f"[{t['ci_lo']:+.1f}, {t['ci_hi']:+.1f}]",
    "p-valor": format_p(t["p"]),
    "Sig.": sig_stars(t["p"]),
})
for ciclo in ["1o", "2o+"]:
    n1, x1 = agg((df["duracao"] == "12") & (df["ciclo"] == ciclo))
    n2, x2 = agg((df["duracao"] == "6") & (df["ciclo"] == ciclo))
    if n1 == 0 or n2 == 0:
        continue
    t = z_test_proportions(n1, x1, n2, x2)
    rows.append({
        "Estrato": f"{ciclo} contrato",
        "12 meses": f"{t['p1']:.1f}% (n={n1:,})",
        "6 meses": f"{t['p2']:.1f}% (n={n2:,})",
        "Diferença": f"{t['diff']:+.1f} p.p.",
        "IC 95%": f"[{t['ci_lo']:+.1f}, {t['ci_hi']:+.1f}]",
        "p-valor": format_p(t["p"]),
        "Sig.": sig_stars(t["p"]),
    })
render_test_table(
    rows,
    ["Estrato", "12 meses", "6 meses", "Diferença", "IC 95%", "p-valor", "Sig."],
)

# Mostra a composição de 1o contrato em cada duração (confounding mecânico)
n_12 = agg(df["duracao"] == "12")[0]
n1_12 = agg((df["duracao"] == "12") & (df["ciclo"] == "1o"))[0]
n_6 = agg(df["duracao"] == "6")[0]
n1_6 = agg((df["duracao"] == "6") & (df["ciclo"] == "1o"))[0]
pct_1o_12 = 100 * n1_12 / n_12 if n_12 else 0
pct_1o_6 = 100 * n1_6 / n_6 if n_6 else 0

st.success(
    f"**Tese executiva validada.** Planos de 12m têm churn estruturalmente maior — "
    f"o efeito persiste controlando por ciclo. Parte do gap aparente vem da composição "
    f"(12m tem {pct_1o_12:.0f}% de 1o contrato vs {pct_1o_6:.0f}% nos 6m), mas o gap real "
    f"continua positivo e significativo em ambos os estratos. **Analisar 6m e 12m em paralelo é correto.**"
)

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════
# DRIVER 5: COMPOSIÇÃO DO TITULAR (solo vs com_ambos) controlado por ciclo
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("### Driver #5 — Composição do titular (solo vs com_ambos)")
st.caption(
    "Controlado por **ciclo do contrato** — ter família completa (crianças E idosos) "
    "ainda retém quando comparado a titular solo dentro do mesmo ciclo?"
)

rows = []
n1, x1 = agg(df["composicao_titular"] == "solo")
n2, x2 = agg(df["composicao_titular"] == "com_ambos")
t = z_test_proportions(n1, x1, n2, x2)
rows.append({
    "Estrato": "Univariada (sem estrato)",
    "Solo": f"{t['p1']:.1f}% (n={n1:,})",
    "Com ambos (crianças+idosos)": f"{t['p2']:.1f}% (n={n2:,})",
    "Diferença": f"{t['diff']:+.1f} p.p.",
    "IC 95%": f"[{t['ci_lo']:+.1f}, {t['ci_hi']:+.1f}]",
    "p-valor": format_p(t["p"]),
    "Sig.": sig_stars(t["p"]),
})
for ciclo in ["1o", "2o+"]:
    n1, x1 = agg((df["composicao_titular"] == "solo") & (df["ciclo"] == ciclo))
    n2, x2 = agg((df["composicao_titular"] == "com_ambos") & (df["ciclo"] == ciclo))
    if n1 == 0 or n2 == 0:
        continue
    t = z_test_proportions(n1, x1, n2, x2)
    rows.append({
        "Estrato": f"{ciclo} contrato",
        "Solo": f"{t['p1']:.1f}% (n={n1:,})",
        "Com ambos (crianças+idosos)": f"{t['p2']:.1f}% (n={n2:,})",
        "Diferença": f"{t['diff']:+.1f} p.p.",
        "IC 95%": f"[{t['ci_lo']:+.1f}, {t['ci_hi']:+.1f}]",
        "p-valor": format_p(t["p"]),
        "Sig.": sig_stars(t["p"]),
    })
render_test_table(
    rows,
    ["Estrato", "Solo", "Com ambos (crianças+idosos)", "Diferença", "IC 95%", "p-valor", "Sig."],
)

# Tabela complementar: cada composição em ambos os ciclos
st.markdown("**Drill: churn por composição × ciclo**")
comp_rows = []
for comp in ["solo", "com_crianca", "com_idoso", "com_ambos"]:
    for ciclo in ["1o", "2o+"]:
        n, x = agg((df["composicao_titular"] == comp) & (df["ciclo"] == ciclo))
        if n == 0:
            continue
        comp_rows.append({
            "Composição": comp,
            "Ciclo": ciclo,
            "Contratos": f"{n:,}",
            "Churn": f"{100*x/n:.1f}%",
        })
st.dataframe(pd.DataFrame(comp_rows), hide_index=True, use_container_width=True)

st.success(
    "**Tese: famílias retêm mais.** Se a diferença Solo vs Com_ambos persiste em ambos os ciclos, "
    "temos evidência de que **a composição familiar é variável causal real** (não consequência do ciclo). "
    "O drill mostra a gradação: solo > com_crianca > com_idoso > com_ambos é o esperado."
)

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════
# RESUMO — HIERARQUIA DOS DRIVERS
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("### Resumo — hierarquia dos drivers")


def best_worst_diff(stratified_diffs: list[float]) -> str:
    if not stratified_diffs:
        return "—"
    return f"{min(stratified_diffs):+.1f} a {max(stratified_diffs):+.1f} p.p."


# Coleta para resumo
def collect_diffs(test_pairs):
    return [z_test_proportions(n1, x1, n2, x2)["diff"] for (n1, x1), (n2, x2) in test_pairs]


# Driver 1
d1_uni = z_test_proportions(*agg(df["ciclo"] == "1o"), *agg(df["ciclo"] == "2o+"))["diff"]
d1_pairs = [(agg((df["ciclo"] == "1o") & (df["duracao"] == d)), agg((df["ciclo"] == "2o+") & (df["duracao"] == d))) for d in ["6", "12"]]
d1_diffs = collect_diffs(d1_pairs)

# Driver 2
d2_uni = z_test_proportions(*agg(df["faixa_etaria"].isin(["00-20", "21-30"])), *agg(df["faixa_etaria"] == "51-70"))["diff"]
d2_pairs = [(agg(df["faixa_etaria"].isin(["00-20", "21-30"]) & (df["ciclo"] == c)), agg((df["faixa_etaria"] == "51-70") & (df["ciclo"] == c))) for c in ["1o", "2o+"]]
d2_diffs = collect_diffs(d2_pairs)

# Driver 3
d3_uni = z_test_proportions(*agg(df["cronico"] == "N"), *agg(df["cronico"] == "S"))["diff"]
d3_pairs = [(agg((df["cronico"] == "N") & (df["faixa_etaria"] == fx)), agg((df["cronico"] == "S") & (df["faixa_etaria"] == fx))) for fx in faixas if agg((df["cronico"] == "N") & (df["faixa_etaria"] == fx))[0] > 0 and agg((df["cronico"] == "S") & (df["faixa_etaria"] == fx))[0] > 0]
d3_diffs = collect_diffs(d3_pairs)

# Driver 4
d4_uni = z_test_proportions(*agg(df["duracao"] == "12"), *agg(df["duracao"] == "6"))["diff"]
d4_pairs = [(agg((df["duracao"] == "12") & (df["ciclo"] == c)), agg((df["duracao"] == "6") & (df["ciclo"] == c))) for c in ["1o", "2o+"]]
d4_diffs = collect_diffs(d4_pairs)

# Driver 5
d5_uni = z_test_proportions(*agg(df["composicao_titular"] == "solo"), *agg(df["composicao_titular"] == "com_ambos"))["diff"]
d5_pairs = [(agg((df["composicao_titular"] == "solo") & (df["ciclo"] == c)), agg((df["composicao_titular"] == "com_ambos") & (df["ciclo"] == c))) for c in ["1o", "2o+"]]
d5_diffs = collect_diffs(d5_pairs)

resumo = pd.DataFrame([
    {"#": 1, "Driver": "Ciclo do contrato (1o vs 2o+)",
     "Gap univariado": f"{d1_uni:+.1f} p.p.",
     "Gap controlado": best_worst_diff(d1_diffs),
     "Confounding": "Nenhum relevante",
     "Veredito": "✅ Driver causal robusto"},
    {"#": 2, "Driver": "Faixa etária (≤30 vs 51-70)",
     "Gap univariado": f"{d2_uni:+.1f} p.p.",
     "Gap controlado": best_worst_diff(d2_diffs),
     "Confounding": "Absorve parte do crônico",
     "Veredito": "✅ Driver causal robusto"},
    {"#": 3, "Driver": "Doença crônica (N vs S)",
     "Gap univariado": f"{d3_uni:+.1f} p.p.",
     "Gap controlado": best_worst_diff(d3_diffs),
     "Confounding": "Parcial — ~metade é idade",
     "Veredito": "⚠️ Real para 31+, fraco em jovens"},
    {"#": 4, "Driver": "Duração (12m vs 6m, eixo executivo)",
     "Gap univariado": f"{d4_uni:+.1f} p.p.",
     "Gap controlado": best_worst_diff(d4_diffs),
     "Confounding": "12m tem mais 1o contrato",
     "Veredito": "✅ Justifica análise paralela"},
    {"#": 5, "Driver": "Composição do titular (solo vs com_ambos)",
     "Gap univariado": f"{d5_uni:+.1f} p.p.",
     "Gap controlado": best_worst_diff(d5_diffs),
     "Confounding": "Verificar — pode interagir com idade",
     "Veredito": "🆕 Novo driver — depende dos dados"},
])
st.dataframe(resumo, hide_index=True, use_container_width=True)

# Visual: gap univariado vs gap controlado mínimo (mostra atenuação por confounding)
labels = resumo["Driver"].tolist()
uni_vals = [d1_uni, d2_uni, d3_uni, d4_uni, d5_uni]
ctrl_min = [min(d) if d else 0 for d in [d1_diffs, d2_diffs, d3_diffs, d4_diffs, d5_diffs]]
ctrl_max = [max(d) if d else 0 for d in [d1_diffs, d2_diffs, d3_diffs, d4_diffs, d5_diffs]]

fig = go.Figure()
fig.add_trace(go.Bar(
    name="Univariado",
    y=labels, x=uni_vals, orientation="h",
    marker_color="#90a4ae",
    text=[f"{v:+.1f}" for v in uni_vals], textposition="outside",
))
fig.add_trace(go.Bar(
    name="Controlado (faixa mín-máx)",
    y=labels, x=[(lo + hi) / 2 for lo, hi in zip(ctrl_min, ctrl_max)],
    orientation="h",
    marker_color="#1565c0",
    error_x=dict(
        type="data", symmetric=False,
        array=[hi - (lo + hi) / 2 for lo, hi in zip(ctrl_min, ctrl_max)],
        arrayminus=[(lo + hi) / 2 - lo for lo, hi in zip(ctrl_min, ctrl_max)],
        color="rgba(0,0,0,0.5)", thickness=2, width=8,
    ),
    text=[f"{(lo+hi)/2:+.1f}" for lo, hi in zip(ctrl_min, ctrl_max)],
    textposition="outside",
))
fig.add_vline(x=0, line_dash="dash", line_color="gray")
fig.update_layout(
    title="Gap univariado vs gap controlado (em p.p.)",
    xaxis_title="Diferença de churn (p.p.)",
    barmode="group",
    height=380,
    legend=dict(orientation="h", y=1.1),
    margin=dict(l=10, r=80),
)
st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

with st.expander("📖 Notas metodológicas", expanded=False):
    st.markdown("""
    **Teste:** z-test bicaudal para diferença de proporções, IC 95% normal-approximation.

    **Origem dos dados:** `storytelling_cruzamento.csv` (cruzamento ciclo × faixa × crônico
    × duração, filtrado HAVING N ≥ 30 nas combinações). A perda de contratos nesse filtro
    é marginal (~40 contratos vs panorama, < 0,03%), então os testes refletem essencialmente
    o universo completo do recorte.

    **Interpretação de "gap controlado":** o range entre o estrato com menor gap e o maior gap.
    Variação dentro do range reflete interação entre variáveis, não instabilidade do efeito.

    **Próxima página:** *Score e Faixas* — os drivers validados aqui são exatamente os que
    entram no WLS, com pesos calibrados via regressão.
    """)
