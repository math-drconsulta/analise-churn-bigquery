"""
Pagina 16 — Score v3: Demografico + Experiencia (XGBoost tuned)
================================================================
Compara o score antigo (WLS demografico) com o novo (XGBoost com
features de experiencia). Mostra separacao de faixas, feature
importance e mapa de risco individual.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(page_title="Score v3", page_icon="🎯", layout="wide")
st.title("🎯 Score v3 — Demografico + Experiencia")
st.caption("XGBoost tuned com 4 camadas: perfil + comportamento + SAC + experiencia na clinica")


# ═══════════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════════
@st.cache_data
def load_contratos():
    return pd.read_csv("results/score_v3_contratos.csv")

@st.cache_data
def load_metricas():
    return pd.read_csv("results/score_v3_metricas.csv")

@st.cache_data
def load_importance():
    return pd.read_csv("results/score_v3_importance.csv")

@st.cache_data
def load_faixas():
    return pd.read_csv("results/score_v3_faixas.csv")


try:
    df = load_contratos()
    df_met = load_metricas()
    df_imp = load_importance()
    df_fxs = load_faixas()
except FileNotFoundError as e:
    st.error(f"CSV nao encontrado: {e}. Rode `scripts/salvar_scores_v3.py` primeiro.")
    st.stop()


# ═══════════════════════════════════════════════════════════════════
# CONSTANTES
# ═══════════════════════════════════════════════════════════════════
CORES_FAIXA = {
    "CRITICO": "#8b0000", "ALTO": "#d62728",
    "MEDIO": "#ffbb33", "BAIXO": "#2ca02c", "SEGURO": "#0d3b8b",
}
FAIXA_ORDER = ["CRITICO", "ALTO", "MEDIO", "BAIXO", "SEGURO"]
total = len(df)
churn_global = round(100 * df["churn"].mean(), 1)

# Faixas fixas de 200 pontos (score ja esta em 0-1000)
BINS_SCORE = [-1, 200, 400, 600, 800, 1001]
df["faixa_xgb"] = pd.cut(df["score_xgb"], bins=BINS_SCORE, labels=FAIXA_ORDER)
df["faixa_lr"] = pd.cut(df["score_lr"], bins=BINS_SCORE, labels=FAIXA_ORDER)


# ═══════════════════════════════════════════════════════════════════
# KPIs
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")

auc_lr = float(df_met[df_met["modelo"].str.contains("Logistica Demo")].iloc[0]["auc_cv"])
auc_xgb = float(df_met[df_met["modelo"].str.contains("XGBoost Demo.Exp")].iloc[0]["auc_cv"])
melhora = round(auc_xgb - auc_lr, 4)

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Contratos", f"{total:,}")
k2.metric("Churn global", f"{churn_global}%")
k3.metric("AUC antigo (LR demo)", f"{auc_lr:.4f}")
k4.metric("AUC novo (XGB tuned)", f"{auc_xgb:.4f}",
          delta=f"{melhora:+.4f}", delta_color="normal")
k5.metric("Features", f"{int(df_met[df_met['modelo'].str.contains('XGBoost Demo.Exp')].iloc[0]['n_features'])}")


# ═══════════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════════
tab_faixas, tab_grupos, tab_explorador, tab_compare, tab_scatter, tab_importance, tab_detalhe = st.tabs([
    "📊 Faixas de Score",
    "👥 Grupos por Faixa",
    "🔎 Explorador de Perfis",
    "⚔️ Antes vs Depois",
    "🗺️ Mapa de Risco",
    "🏆 Feature Importance",
    "🔍 Detalhe por Perfil",
])


# ═══════════════════════════════════════════════════════════════════
# TAB 1: FAIXAS DE SCORE (como a pagina 2)
# ═══════════════════════════════════════════════════════════════════
with tab_faixas:
    st.markdown("### Score v3 — Faixas de Risco")

    score_min = int(df["score_xgb"].min())
    score_max = int(df["score_xgb"].max())
    score_med = int(df["score_xgb"].median())

    st.markdown(f"""
    Score de **0** (maior risco) a **1000** (menor risco). Mediana: **{score_med}**.
    Escala normalizada pelo range do modelo (min-max das probabilidades preditas).

    | Faixa | Score | Significado |
    |---|---|---|
    | CRITICO | 0 – 200 | Risco muito alto de churn |
    | ALTO | 201 – 400 | Risco alto |
    | MEDIO | 401 – 600 | Risco moderado |
    | BAIXO | 601 – 800 | Risco baixo |
    | SEGURO | 801 – 1000 | Maior probabilidade de renovar |
    """)

    # Calcular faixas do XGBoost
    faixas_xgb = df.groupby("faixa_xgb", observed=True).agg(
        contratos=("churn", "count"),
        churners=("churn", "sum"),
    ).reindex(FAIXA_ORDER).reset_index()
    faixas_xgb.columns = ["faixa", "contratos", "churners"]
    faixas_xgb = faixas_xgb.dropna(subset=["contratos"])
    faixas_xgb["churn_rate"] = (100 * faixas_xgb["churners"] / faixas_xgb["contratos"]).round(1)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=faixas_xgb["faixa"], y=faixas_xgb["contratos"],
        name="Contratos",
        marker_color=[CORES_FAIXA.get(f, "gray") for f in faixas_xgb["faixa"]],
        opacity=0.4,
        text=faixas_xgb["contratos"].apply(lambda x: f"{int(x):,}"),
        textposition="outside",
    ))
    fig.add_trace(go.Scatter(
        x=faixas_xgb["faixa"], y=faixas_xgb["churn_rate"],
        name="Churn (%)", mode="lines+markers+text",
        marker=dict(size=14,
                    color=[CORES_FAIXA.get(f, "gray") for f in faixas_xgb["faixa"]],
                    line=dict(width=2, color="white")),
        line=dict(width=3, color="gray", dash="dot"),
        yaxis="y2",
        text=faixas_xgb["churn_rate"].apply(lambda x: f"{x}%"),
        textposition="top center", textfont=dict(size=14, color="crimson"),
    ))
    fig.update_layout(
        title="Score v3: Volume e Churn por Faixa",
        yaxis=dict(title="Contratos"),
        yaxis2=dict(title="Churn (%)", overlaying="y", side="right", range=[0, 100]),
        legend=dict(orientation="h", y=1.12), height=480,
    )
    st.plotly_chart(fig, use_container_width=True)

    # KPIs das faixas
    valid_faixas = faixas_xgb[faixas_xgb["contratos"] >= 30]
    if len(valid_faixas) >= 2:
        pior = valid_faixas.iloc[0]
        melhor = valid_faixas.iloc[-1]
        spread = round(pior["churn_rate"] - melhor["churn_rate"], 1)

        k1, k2, k3 = st.columns(3)
        k1.metric("Churn faixa CRITICO/ALTO", f'{pior["churn_rate"]}%',
                  help=f'{int(pior["contratos"]):,} contratos')
        k2.metric("Churn faixa BAIXO/SEGURO", f'{melhor["churn_rate"]}%',
                  help=f'{int(melhor["contratos"]):,} contratos')
        k3.metric("Spread", f"{spread} p.p.",
                  help="Capacidade de separar alto risco de baixo risco")

    # Tabela
    st.dataframe(
        faixas_xgb.rename(columns={
            "faixa": "Faixa", "contratos": "Contratos",
            "churners": "Churners", "churn_rate": "Churn (%)",
        }),
        hide_index=True, use_container_width=True,
    )


# ═══════════════════════════════════════════════════════════════════
# TAB 2: GRUPOS POR FAIXA
# ═══════════════════════════════════════════════════════════════════
FEATURES_GRUPO = [
    ("ciclo", "Ciclo"),
    ("duracao", "Duracao"),
    ("faixa_idade_cat", "Idade"),
    ("faixa_dep", "Dependentes"),
    ("cronico", "Cronico"),
    ("rotatividade_cat", "Rotatividade"),
    ("faixa_nps_cat", "NPS"),
    ("faixa_tempo_cat", "Tempo clinica"),
]

with tab_grupos:
    st.markdown("### Quem esta em cada faixa?")
    st.markdown("""
    Cada faixa agrupa pacientes com diferentes combinacoes de perfil e experiencia.
    Abaixo mostramos os **maiores grupos** dentro de cada faixa — as combinacoes
    mais frequentes e seu churn real.
    """)

    faixa_sel = st.selectbox(
        "Selecione a faixa:", options=FAIXA_ORDER,
        format_func=lambda f: f"{f} ({len(df[df['faixa_xgb']==f]):,} contratos)",
        key="grp_faixa"
    )

    sub = df[df["faixa_xgb"] == faixa_sel].copy()

    if len(sub) == 0:
        st.warning("Sem contratos nessa faixa.")
    else:
        n_faixa = len(sub)
        churn_faixa = round(100 * sub["churn"].mean(), 1)

        st.markdown(f"**{faixa_sel}:** {n_faixa:,} contratos · churn **{churn_faixa}%** · score {int(sub['score_xgb'].min())} a {int(sub['score_xgb'].max())}")

        # Retrato rapido: composicao predominante
        st.markdown("---")
        st.markdown("#### Retrato da faixa")

        comp_cols = st.columns(len(FEATURES_GRUPO))
        for i, (col_name, label) in enumerate(FEATURES_GRUPO):
            with comp_cols[i]:
                st.markdown(f"**{label}**")
                dist = sub[col_name].value_counts(normalize=True).head(4)
                for val, pct in dist.items():
                    pct_100 = round(pct * 100)
                    bar = "█" * (pct_100 // 5)
                    st.caption(f"{val}: {pct_100}% {bar}")

        # Top grupos (combinacoes mais frequentes)
        st.markdown("---")
        st.markdown("#### Maiores grupos dentro da faixa")

        # Agrupar por features principais
        feat_cols = [f[0] for f in FEATURES_GRUPO]
        grupos = sub.groupby(feat_cols).agg(
            n=("churn", "count"),
            ch=("churn", "sum"),
            score_medio=("score_xgb", "mean"),
        ).reset_index()
        grupos["churn_rate"] = (100 * grupos["ch"] / grupos["n"]).round(1)
        grupos["score_medio"] = grupos["score_medio"].round(0).astype(int)
        grupos = grupos[grupos["n"] >= 10].sort_values("n", ascending=False)

        # Mostrar top 15
        top_n = min(15, len(grupos))
        if top_n == 0:
            st.info("Poucos contratos pra formar grupos significativos.")
        else:
            st.markdown(f"**Top {top_n} grupos** (minimo 10 contratos):")

            top_grupos = grupos.head(top_n).copy()
            top_grupos["perfil"] = top_grupos.apply(
                lambda r: " · ".join([f"{r[f[0]]}" for f in FEATURES_GRUPO if str(r[f[0]]) not in ["", "nan"]]),
                axis=1
            )

            fig_grp = go.Figure()
            fig_grp.add_trace(go.Bar(
                y=top_grupos["perfil"].iloc[::-1],
                x=top_grupos["churn_rate"].iloc[::-1],
                orientation="h",
                marker_color=[
                    "#c0392b" if cr > churn_faixa + 5
                    else "#27ae60" if cr < churn_faixa - 5
                    else "#f39c12"
                    for cr in top_grupos["churn_rate"].iloc[::-1]
                ],
                text=top_grupos.apply(
                    lambda r: f'{r["churn_rate"]}% ({int(r["n"]):,} · score {r["score_medio"]})', axis=1
                ).iloc[::-1],
                textposition="outside",
                textfont=dict(size=11),
            ))
            fig_grp.add_vline(x=churn_faixa, line_dash="dash", line_color="gray",
                              annotation_text=f"Media faixa: {churn_faixa}%")
            fig_grp.update_layout(
                title=f"Top {top_n} grupos na faixa {faixa_sel}",
                xaxis_title="Churn (%)",
                height=max(450, top_n * 35 + 100),
                margin=dict(l=20, r=120),
                yaxis=dict(automargin=True),
                xaxis=dict(range=[0, min(100, max(top_grupos["churn_rate"]) + 15)]),
            )
            st.plotly_chart(fig_grp, use_container_width=True)

            # Tabela
            st.dataframe(
                top_grupos[["perfil", "n", "ch", "churn_rate", "score_medio"]].rename(columns={
                    "perfil": "Perfil", "n": "Contratos", "ch": "Churners",
                    "churn_rate": "Churn (%)", "score_medio": "Score medio",
                }),
                hide_index=True, use_container_width=True,
            )

        # Resumo: grupos de maior e menor churn dentro da faixa
        if len(grupos) >= 2:
            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Maior churn dentro da faixa:**")
                pior = grupos.nlargest(3, "churn_rate")
                for _, r in pior.iterrows():
                    perfil = " · ".join([f"{r[f[0]]}" for f in FEATURES_GRUPO if str(r[f[0]]) not in ["", "nan"]])
                    st.markdown(f"- **{r['churn_rate']}%** — {perfil} ({int(r['n'])} contratos)")
            with col2:
                st.markdown("**Menor churn dentro da faixa:**")
                melhor = grupos.nsmallest(3, "churn_rate")
                for _, r in melhor.iterrows():
                    perfil = " · ".join([f"{r[f[0]]}" for f in FEATURES_GRUPO if str(r[f[0]]) not in ["", "nan"]])
                    st.markdown(f"- **{r['churn_rate']}%** — {perfil} ({int(r['n'])} contratos)")


# ═══════════════════════════════════════════════════════════════════
# TAB 3: EXPLORADOR DE PERFIS
# ═══════════════════════════════════════════════════════════════════
with tab_explorador:
    st.markdown("### Explorador de Perfis")
    st.markdown("""
    Monte uma combinacao de caracteristicas e veja em tempo real:
    o churn, o score medio, a faixa de risco e quantos contratos tem.
    """)

    # Selectboxes pra cada feature
    col_selects = st.columns(4)

    filtros = {}
    opcoes_feature = [
        ("ciclo", "Ciclo", 0),
        ("duracao", "Duracao", 0),
        ("faixa_idade_cat", "Idade", 1),
        ("faixa_dep", "Dependentes", 1),
        ("cronico", "Cronico", 2),
        ("canal_simples", "Canal", 2),
        ("rotatividade_cat", "Rotatividade", 3),
        ("faixa_nps_cat", "NPS", 3),
    ]

    for col_name, label, col_idx in opcoes_feature:
        with col_selects[col_idx]:
            vals = ["Todos"] + sorted(df[col_name].dropna().unique().tolist())
            sel = st.selectbox(label, options=vals, key=f"exp_{col_name}")
            if sel != "Todos":
                filtros[col_name] = sel

    # Filtro adicional: tempo na clinica
    col_extra1, col_extra2 = st.columns(2)
    with col_extra1:
        tempo_vals = ["Todos"] + sorted(df["faixa_tempo_cat"].dropna().unique().tolist())
        tempo_sel = st.selectbox("Tempo clinica", options=tempo_vals, key="exp_tempo")
        if tempo_sel != "Todos":
            filtros["faixa_tempo_cat"] = tempo_sel

    # Aplicar filtros
    sub = df.copy()
    for col_name, val in filtros.items():
        sub = sub[sub[col_name] == val]

    # Resultados
    st.markdown("---")

    if len(sub) == 0:
        st.warning("Nenhum contrato com essa combinacao. Tente remover algum filtro.")
    elif len(sub) < 10:
        st.warning(f"Apenas {len(sub)} contratos — amostra muito pequena pra conclusao.")
    else:
        n = len(sub)
        ch = sub["churn"].sum()
        cr = round(100 * ch / n, 1)
        score_med = int(sub["score_xgb"].median())
        score_min = int(sub["score_xgb"].min())
        score_max = int(sub["score_xgb"].max())

        # Faixa predominante
        faixa_pred = sub["faixa_xgb"].value_counts().index[0]

        # Filtros aplicados como texto
        if filtros:
            filtro_txt = " · ".join([f"**{dict(opcoes_feature + [('faixa_tempo_cat', 'Tempo', 0)])[k] if k != 'faixa_tempo_cat' else 'Tempo'}** = {v}" for k, v in filtros.items()])
        else:
            filtro_txt = "Nenhum filtro — base inteira"

        st.markdown(f"**Perfil selecionado:** {filtro_txt}")

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Contratos", f"{n:,}")
        k2.metric("Churn", f"{cr}%",
                  delta=f"{cr - churn_global:+.1f} p.p. vs base",
                  delta_color="inverse" if cr > churn_global else "normal")
        k3.metric("Score mediano", f"{score_med}")
        k4.metric("Score range", f"{score_min} – {score_max}")
        k5.metric("Faixa predominante", faixa_pred)

        # Comparar com a base
        fig_comp = go.Figure()

        fig_comp.add_trace(go.Indicator(
            mode="gauge+number+delta",
            value=cr,
            delta={"reference": churn_global, "valueformat": ".1f", "suffix": " p.p."},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#c0392b" if cr > churn_global else "#27ae60"},
                "steps": [
                    {"range": [0, 40], "color": "#d4efdf"},
                    {"range": [40, 55], "color": "#fef9e7"},
                    {"range": [55, 100], "color": "#fdedec"},
                ],
                "threshold": {
                    "line": {"color": "black", "width": 3},
                    "thickness": 0.8,
                    "value": churn_global,
                },
            },
            title={"text": f"Churn do perfil selecionado<br><span style='font-size:12px'>Base: {churn_global}%</span>"},
        ))
        fig_comp.update_layout(height=300)
        st.plotly_chart(fig_comp, use_container_width=True)

        # Distribuicao de faixas desse perfil
        st.markdown("#### Distribuicao por faixa")
        faixa_dist = sub["faixa_xgb"].value_counts().reindex(FAIXA_ORDER, fill_value=0)
        fig_dist = go.Figure()
        fig_dist.add_trace(go.Bar(
            x=faixa_dist.index.astype(str),
            y=faixa_dist.values,
            marker_color=[CORES_FAIXA.get(f, "gray") for f in faixa_dist.index],
            text=[f"{v:,}" for v in faixa_dist.values],
            textposition="outside",
        ))
        fig_dist.update_layout(
            title="Em quais faixas esse perfil cai",
            yaxis_title="Contratos", height=350,
        )
        st.plotly_chart(fig_dist, use_container_width=True)

        # Se tiver mais de um filtro ativo, mostrar qual pesa mais
        if len(filtros) >= 2:
            st.markdown("#### Qual feature mais pesa nesse perfil?")
            st.caption("Removendo um filtro por vez e vendo quanto o churn muda:")
            for col_name, val in filtros.items():
                sub_sem = df.copy()
                for c2, v2 in filtros.items():
                    if c2 != col_name:
                        sub_sem = sub_sem[sub_sem[c2] == v2]
                n_sem = len(sub_sem)
                cr_sem = round(100 * sub_sem["churn"].mean(), 1) if n_sem > 0 else 0
                delta = round(cr - cr_sem, 1)
                label_feat = col_name
                for f_name, f_label, _ in opcoes_feature:
                    if f_name == col_name:
                        label_feat = f_label
                        break
                st.markdown(
                    f"- Sem filtro de **{label_feat}** ({val}): churn seria {cr_sem}% "
                    f"→ filtro contribui **{delta:+.1f} p.p.**"
                )


# ═══════════════════════════════════════════════════════════════════
# TAB 4: ANTES VS DEPOIS
# ═══════════════════════════════════════════════════════════════════
with tab_compare:
    st.markdown("### Comparacao: Score Antigo vs Novo")

    # Faixas do LR
    faixas_lr = df.groupby("faixa_lr", observed=True).agg(
        contratos=("churn", "count"), churners=("churn", "sum"),
    ).reindex(FAIXA_ORDER).reset_index()
    faixas_lr.columns = ["faixa", "contratos", "churners"]
    faixas_lr = faixas_lr.dropna(subset=["contratos"])
    faixas_lr["churn_rate"] = (100 * faixas_lr["churners"] / faixas_lr["contratos"]).round(1)
    faixas_lr["modelo"] = "Antigo (LR demografico)"

    faixas_xgb_c = faixas_xgb.copy()
    faixas_xgb_c["modelo"] = "Novo (XGB demo+exp)"

    comp = pd.concat([faixas_lr, faixas_xgb_c])

    fig_comp = go.Figure()
    for modelo, cor, offset in [
        ("Antigo (LR demografico)", "#95a5a6", -0.15),
        ("Novo (XGB demo+exp)", "#e74c3c", 0.15),
    ]:
        sub = comp[comp["modelo"] == modelo]
        fig_comp.add_trace(go.Bar(
            x=sub["faixa"], y=sub["churn_rate"],
            name=modelo, marker_color=cor,
            text=sub.apply(lambda r: f'{r["churn_rate"]}%\n({int(r["contratos"]):,})', axis=1),
            textposition="outside", textfont=dict(size=11),
            offsetgroup=modelo,
        ))

    fig_comp.update_layout(
        barmode="group",
        title="Churn por Faixa: Antigo vs Novo",
        yaxis_title="Churn (%)", height=450,
        legend=dict(orientation="h", y=1.1),
        yaxis=dict(range=[0, 100]),
    )
    st.plotly_chart(fig_comp, use_container_width=True)

    # Tabela de metricas
    st.markdown("### Metricas dos Modelos")
    st.dataframe(
        df_met.rename(columns={
            "modelo": "Modelo", "auc_cv": "AUC (CV)",
            "brier": "Brier Score", "n_features": "Features",
        }),
        hide_index=True, use_container_width=True,
    )

    # Calcular spreads pra comparar
    lr_fxs = df.groupby("faixa_lr", observed=True).agg(ch=("churn", "mean")).reset_index()
    lr_fxs["ch"] = (100 * lr_fxs["ch"]).round(1)
    xgb_fxs = df.groupby("faixa_xgb", observed=True).agg(ch=("churn", "mean")).reset_index()
    xgb_fxs["ch"] = (100 * xgb_fxs["ch"]).round(1)

    spread_lr = round(lr_fxs["ch"].max() - lr_fxs["ch"].min(), 1)
    spread_xgb = round(xgb_fxs["ch"].max() - xgb_fxs["ch"].min(), 1)

    st.markdown(f"""
    **O que melhorou (faixas calibradas por quintis):**
    - AUC subiu de {auc_lr:.4f} pra **{auc_xgb:.4f}** (+{melhora:.4f})
    - Spread LR demografico: **{spread_lr} p.p.**
    - Spread XGB demo+exp: **{spread_xgb} p.p.**
    - O XGB separa melhor os extremos usando experiencia na clinica

    **O que nao mudou:**
    - AUC continua modesto (~0.59) — o teto com os dados disponiveis
    - Ciclo do contrato e duracao continuam sendo os preditores dominantes
    """)


# ═══════════════════════════════════════════════════════════════════
# TAB 3: MAPA DE RISCO (SCATTER)
# ═══════════════════════════════════════════════════════════════════
with tab_scatter:
    st.markdown("### Mapa de Risco Individual")
    st.markdown("""
    Cada ponto e um contrato. O eixo X e o score (0 = alto risco, 1000 = seguro).
    O eixo Y e o churn real (0 = renovou, 1 = cancelou). A cor indica a faixa.
    """)

    # Amostra pra nao sobrecarregar o grafico
    sample = df.sample(min(10000, len(df)), random_state=42).copy()

    fig_scatter = go.Figure()
    for faixa in FAIXA_ORDER:
        sub = sample[sample["faixa_xgb"] == faixa]
        if len(sub) == 0:
            continue
        fig_scatter.add_trace(go.Scatter(
            x=sub["score_xgb"],
            y=sub["churn"] + np.random.normal(0, 0.03, len(sub)),  # jitter
            mode="markers",
            marker=dict(size=4, color=CORES_FAIXA[faixa], opacity=0.4),
            name=f"{faixa} ({len(sub):,})",
        ))

    # Faixas de fundo
    for x0, x1, faixa in [(0, 200, "CRITICO"), (200, 400, "ALTO"), (400, 600, "MEDIO"),
                           (600, 800, "BAIXO"), (800, 1000, "SEGURO")]:
        fig_scatter.add_vrect(x0=x0, x1=x1, fillcolor=CORES_FAIXA[faixa],
                              opacity=0.05, line_width=0)
        fig_scatter.add_annotation(x=(x0+x1)/2, y=1.08, text=faixa,
                                    showarrow=False, font=dict(size=10, color=CORES_FAIXA[faixa]))

    fig_scatter.update_layout(
        title="Mapa de Risco: Score vs Churn (amostra de 10k contratos)",
        xaxis_title="Score v3 (0 = risco, 1000 = seguro)",
        yaxis_title="Churn (0 = renovou, 1 = cancelou)",
        height=500,
        legend=dict(orientation="h", y=-0.15),
        yaxis=dict(range=[-0.15, 1.15]),
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

    # Curva de churn por score (binned)
    st.markdown("### Curva de Churn por Score")

    df["score_bin"] = pd.cut(df["score_xgb"], bins=20)
    curve = df.groupby("score_bin", observed=True).agg(
        n=("churn", "count"), ch=("churn", "sum")
    ).reset_index()
    curve["cr"] = (100 * curve["ch"] / curve["n"]).round(1)
    curve["mid"] = curve["score_bin"].apply(lambda x: x.mid)

    fig_curve = go.Figure()
    fig_curve.add_trace(go.Scatter(
        x=curve["mid"], y=curve["cr"],
        mode="lines+markers",
        line=dict(width=3, color="#2c3e50"),
        marker=dict(size=8),
        fill="tozeroy", fillcolor="rgba(44, 62, 80, 0.1)",
    ))
    fig_curve.add_hline(y=churn_global, line_dash="dash", line_color="gray",
                        annotation_text=f"Base: {churn_global}%")
    fig_curve.update_layout(
        title="Churn real por faixa de score (20 bins)",
        xaxis_title="Score v3",
        yaxis_title="Churn (%)", height=400,
        yaxis=dict(range=[0, 100]),
    )
    st.plotly_chart(fig_curve, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
# TAB 4: FEATURE IMPORTANCE
# ═══════════════════════════════════════════════════════════════════
with tab_importance:
    st.markdown("### Feature Importance (XGBoost)")
    st.markdown("""
    Quais variaveis o modelo mais usa pra separar risco alto de baixo.
    O tamanho da barra indica o **ganho medio** — quanto a feature contribui
    pra melhorar as previsoes.
    """)

    # Classificar features por tipo
    def tipo_feature(f):
        exp_keys = ["nps", "tempo", "rotatividade", "prof_por_esp", "nota", "qtd_atendimentos", "tem_atendimento"]
        if any(k in f.lower() for k in exp_keys):
            return "Experiencia"
        return "Demografico"

    df_imp["tipo"] = df_imp["feature"].apply(tipo_feature)

    # Labels amigaveis
    label_map = {
        "ciclo_2o+": "2o+ contrato",
        "duracao_6": "Plano 6 meses",
        "faixa_idade_cat_jovem": "Jovem (ate 30)",
        "faixa_idade_cat_senior": "Senior (50+)",
        "faixa_dep_3+_dep": "3+ dependentes",
        "faixa_dep_sem_dep": "Sem dependentes",
        "cronico_S": "Cronico",
        "canal_simples_presencial": "Canal presencial",
        "rotatividade_cat_continuidade": "Continuidade medica",
        "rotatividade_cat_moderada": "Rotatividade moderada",
        "rotatividade_cat_sem_atend": "Sem atendimento (rotativ.)",
        "faixa_tempo_cat_sem_atend": "Sem atendimento (tempo)",
        "faixa_tempo_cat_longo": "Visita longa (30min+)",
        "faixa_tempo_cat_medio": "Visita media (15-30min)",
        "faixa_nps_cat_promotor": "NPS Promotor (9-10)",
        "faixa_nps_cat_neutro": "NPS Neutro (7-8)",
        "faixa_nps_cat_sem_nps": "Sem NPS",
        "prof_por_esp": "Medicos/especialidade",
        "tempo_clinica_min": "Tempo na clinica (min)",
        "nps_valor": "NPS (numerico)",
        "nota_medico_val": "Nota do medico",
        "nota_atend_val": "Nota do atendimento",
        "qtd_atendimentos": "Qtd atendimentos",
        "tem_atendimento": "Teve atendimento",
    }
    df_imp["label"] = df_imp["feature"].map(label_map).fillna(df_imp["feature"])

    top_n = st.slider("Features a exibir:", 5, len(df_imp), 15, key="imp_n")
    top = df_imp.head(top_n).iloc[::-1]

    fig_imp = go.Figure()
    fig_imp.add_trace(go.Bar(
        y=top["label"], x=top["gain"],
        orientation="h",
        marker_color=[
            "#e74c3c" if t == "Experiencia" else "#3498db"
            for t in top["tipo"].iloc[::-1]  # reversed
        ],
        text=top["tipo"],
        textposition="inside",
        textfont=dict(size=10, color="white"),
    ))
    fig_imp.update_layout(
        title="Feature Importance (gain) — Azul = Demografico, Vermelho = Experiencia",
        xaxis_title="Gain",
        height=max(400, top_n * 30 + 80),
        margin=dict(l=20, r=20),
        yaxis=dict(automargin=True),
    )
    st.plotly_chart(fig_imp, use_container_width=True)

    # Resumo
    gain_demo = df_imp[df_imp["tipo"] == "Demografico"]["gain"].sum()
    gain_exp = df_imp[df_imp["tipo"] == "Experiencia"]["gain"].sum()
    total_gain = gain_demo + gain_exp

    col1, col2 = st.columns(2)
    col1.metric("Contribuicao Demografico", f"{100*gain_demo/total_gain:.0f}%")
    col2.metric("Contribuicao Experiencia", f"{100*gain_exp/total_gain:.0f}%")

    st.markdown(f"""
    **{100*gain_demo/total_gain:.0f}%** do poder preditivo vem de variaveis demograficas
    (ciclo, duracao, idade). **{100*gain_exp/total_gain:.0f}%** vem de experiencia
    (rotatividade, tempo, NPS). As features de experiencia sao complementares —
    nao substituem o perfil, mas adicionam sinais que o perfil sozinho nao captura.
    """)


# ═══════════════════════════════════════════════════════════════════
# TAB 5: DETALHE POR PERFIL
# ═══════════════════════════════════════════════════════════════════
with tab_detalhe:
    st.markdown("### Churn por Perfil dentro de cada Faixa")
    st.markdown("""
    O score v3 separa melhor porque combina perfil com experiencia.
    Aqui mostramos como cada variavel se distribui dentro das faixas.
    """)

    faixa_sel = st.selectbox("Faixa:", options=FAIXA_ORDER, index=1, key="det_faixa")
    sub = df[df["faixa_xgb"] == faixa_sel]

    if len(sub) == 0:
        st.warning("Sem contratos nessa faixa.")
    else:
        n_faixa = len(sub)
        churn_faixa = round(100 * sub["churn"].mean(), 1)
        st.markdown(f"**{faixa_sel}:** {n_faixa:,} contratos, churn {churn_faixa}%")

        # Distribuicao de cada feature
        features_show = [
            ("ciclo", "Ciclo"),
            ("faixa_dep", "Dependentes"),
            ("faixa_idade_cat", "Idade"),
            ("cronico", "Cronico"),
            ("duracao", "Duracao"),
            ("rotatividade_cat", "Rotatividade"),
            ("faixa_nps_cat", "NPS"),
            ("faixa_tempo_cat", "Tempo clinica"),
        ]

        cols = st.columns(4)
        for i, (col_name, label) in enumerate(features_show):
            with cols[i % 4]:
                st.markdown(f"**{label}**")
                dist = sub[col_name].value_counts(normalize=True).round(3) * 100
                for val, pct in dist.items():
                    bar = "█" * int(pct / 5)
                    st.caption(f"{val}: {pct:.0f}% {bar}")

        # Churn por feature dentro da faixa
        st.markdown("---")
        st.markdown("### Churn por feature dentro da faixa")

        var_sel = st.selectbox(
            "Variavel:", options=[f[0] for f in features_show],
            format_func=lambda x: dict(features_show)[x],
            key="det_var"
        )

        grp = sub.groupby(var_sel).agg(
            n=("churn", "count"), ch=("churn", "sum")
        ).reset_index()
        grp["cr"] = (100 * grp["ch"] / grp["n"]).round(1)
        grp = grp[grp["n"] >= 10].sort_values("cr", ascending=True)

        if len(grp) > 0:
            fig_det = go.Figure()
            fig_det.add_trace(go.Bar(
                y=grp[var_sel].astype(str), x=grp["cr"],
                orientation="h",
                marker_color=[
                    "#c0392b" if cr > churn_faixa + 3 else "#27ae60" if cr < churn_faixa - 3
                    else "#f39c12"
                    for cr in grp["cr"]
                ],
                text=grp.apply(lambda r: f'{r["cr"]}% ({int(r["n"]):,})', axis=1),
                textposition="outside",
            ))
            fig_det.add_vline(x=churn_faixa, line_dash="dash", line_color="gray",
                              annotation_text=f"Faixa: {churn_faixa}%")
            fig_det.update_layout(
                title=f"{dict(features_show)[var_sel]} dentro da faixa {faixa_sel}",
                xaxis_title="Churn (%)",
                height=max(250, len(grp) * 40 + 80),
                margin=dict(l=20, r=80),
                yaxis=dict(automargin=True),
            )
            st.plotly_chart(fig_det, use_container_width=True)
