import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

from comite_individual import (
    compute_band_summary,
    compute_calibration,
    explain_individual,
    fit_xgb_per_duracao,
    assign_actionable_personas,
)

st.title("🧮 Score Individual — XGBoost + SHAP")
st.caption(
    "Gradient Boosting em **dados individuais** (~188k contratos) com explicabilidade caso-a-caso "
    "via SHAP. Coexiste com o WLS (Páginas 3-6) — este é o pipeline operacional do Growth."
)


@st.cache_data
def load_individual():
    return pd.read_csv("results_comite/dados_individuais.csv")


@st.cache_resource
def fit_models():
    df = load_individual()
    df["duracao"] = df["duracao"].astype(str)
    return fit_xgb_per_duracao(df, cv_folds=5)


try:
    df_full = load_individual()
    with st.spinner("Treinando XGBoost (5-fold CV + best_params Optuna) + SHAP… ~90-120s na primeira execução"):
        models = fit_models()
except FileNotFoundError:
    st.error(
        "`results_comite/dados_individuais.csv` não encontrado. "
        "Rode `queries_comite/dados_individuais.sql` no BigQuery e salve nesse caminho."
    )
    st.stop()

df_full["duracao"] = df_full["duracao"].astype(str)
DUR_COLORS = {"6": "#4caf50", "12": "#ff5722"}
BAND_COLORS = {"CRITICO": "#8b0000", "ALTO": "#d62728", "MEDIO": "#f9a825",
               "BAIXO": "#2ca02c", "SEGURO": "#0d3b8b"}

# WLS baselines (do score_audit_baseline_metricas.csv) — ancoram a comparação
WLS_BENCHMARK = {
    "12": {"auc": 0.580, "ks": 10.5},
    "6":  {"auc": 0.594, "ks": 12.3},
}

# Carrega resumo do tuning Optuna (se já rodado)
TUNED_INFO_PATH = Path("results_comite/xgb_best_params.json")
TUNED_INFO = {}
if TUNED_INFO_PATH.exists():
    with open(TUNED_INFO_PATH) as f:
        TUNED_INFO = json.load(f)


def platt_slope_intercept(y, p):
    """Calibration in the large: ~1 / ~0 = bem calibrado."""
    p_clip = np.clip(p, 1e-6, 1 - 1e-6)
    logit = np.log(p_clip / (1 - p_clip))
    lr = LogisticRegression(fit_intercept=True, solver="lbfgs", max_iter=200)
    lr.fit(logit.reshape(-1, 1), y)
    return float(lr.coef_[0, 0]), float(lr.intercept_[0])


def expected_calibration_error(y, p, n_bins=10):
    df = pd.DataFrame({"y": y, "p": p})
    df["b"] = pd.qcut(df["p"], n_bins, labels=False, duplicates="drop")
    g = df.groupby("b").agg(n=("y", "count"), r=("y", "mean"), pr=("p", "mean"))
    return float((g["n"] / g["n"].sum() * (g["r"] - g["pr"]).abs()).sum() * 100)


def targeting_topk(y, p, pct=0.10):
    """Retorna (churn_rate_top_pp, recall_pct, lift) no top-X% por prob predita."""
    n = len(y)
    k = max(1, int(np.ceil(n * pct)))
    order = np.argsort(-p)
    top = np.asarray(y)[order][:k]
    overall = y.mean()
    rate = top.mean()
    lift = rate / overall if overall > 0 else 0
    recall = top.sum() / max(1, y.sum())
    return float(rate * 100), float(recall * 100), float(lift)


# ═══════════════════════════════════════════════════════════════════════════
# KPIs HONESTOS — TODOS BASEADOS EM OOF (CV out-of-fold)
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("### Performance honesta — 5-fold CV out-of-fold")
st.caption(
    "Todas as métricas abaixo vêm de **predições out-of-fold** (modelo nunca vê o exemplo "
    "que está prevendo). Comparações com o WLS usam os mesmos contratos. "
    "**AUC mede ordenação; ECE / Platt slope medem se a probabilidade é confiável como número.**"
)

cols = st.columns(2)
for col, dur in zip(cols, ["6", "12"]):
    if dur not in models:
        continue
    m = models[dur]
    met = m["metrics"]
    y_oof = m["y"]
    p_oof = m["oof_proba"]

    # Métricas honestas (OOF)
    ece = expected_calibration_error(y_oof, p_oof)
    slope, intercept = platt_slope_intercept(y_oof, p_oof)
    rate10, recall10, lift10 = targeting_topk(y_oof, p_oof, pct=0.10)

    # Spread CRITICO→SEGURO usando OOF scores (honesto)
    sub_df = df_full[df_full["duracao"] == dur].reset_index(drop=True)
    bs_oof = compute_band_summary(sub_df, m["oof_scores"])
    crit_oof = float(bs_oof[bs_oof["band"] == "CRITICO"]["churn_rate"].iloc[0]) \
        if "CRITICO" in bs_oof["band"].values else None
    seg_oof = float(bs_oof[bs_oof["band"] == "SEGURO"]["churn_rate"].iloc[0]) \
        if "SEGURO" in bs_oof["band"].values else None
    spread_oof = (crit_oof - seg_oof) if (crit_oof is not None and seg_oof is not None) else None

    wls = WLS_BENCHMARK.get(dur, {})

    with col:
        st.markdown(f"#### Plano {dur} meses")
        k1, k2, k3 = st.columns(3)
        k1.metric(
            "AUC (OOF)", f"{met['auc_cv']:.3f}",
            delta=f"{met['auc_cv'] - wls.get('auc', 0):+.3f} vs WLS",
            help=f"WLS atual: {wls.get('auc', '?')}. Empate técnico — o ganho real está em calibração e SHAP individual, não na ordenação.",
        )
        k2.metric(
            "KS (OOF)", f"{met['ks_cv']:.1f}%",
            delta=f"{met['ks_cv'] - wls.get('ks', 0):+.1f} vs WLS",
        )
        k3.metric(
            "Spread CRÍTICO→SEGURO",
            f"{spread_oof:.1f} p.p." if spread_oof is not None else "—",
            help="Diferença de churn entre cortes 0-200 e 800-1000 do score, em OOF.",
        )

        k4, k5, k6 = st.columns(3)
        k4.metric(
            "ECE", f"{ece:.2f} p.p.",
            help="Expected Calibration Error: erro médio absoluto entre prob predita e churn real. <1 p.p. = excelente.",
        )
        k5.metric(
            "Platt slope", f"{slope:.2f}",
            help="Slope ~1 e intercept ~0 = probabilidade confiável como número absoluto, não só como ranking.",
        )
        k6.metric(
            "Lift top-10%", f"{lift10:.2f}×",
            help=f"Top 10% concentrados pelo score têm churn {rate10:.1f}% (vs {met['churn_rate']:.1f}% global). Recall: {recall10:.1f}% dos churners.",
        )

        # Linha de status com tuning
        tuned_msg = ""
        if dur in TUNED_INFO:
            ti = TUNED_INFO[dur]
            tuned_msg = (
                f" · ⚙️ params tunados via Optuna ({ti['n_trials']} trials, "
                f"Δ AUC vs default: {ti['delta_auc']:+.4f})"
            )
        st.caption(
            f"N = {met['n_obs']:,} · features = {met['n_features']} · "
            f"churn global = {met['churn_rate']:.1f}% · best_iter = {met['best_iter']} "
            f"(folds: {met['best_iter_min']}–{met['best_iter_max']}){tuned_msg}"
        )

st.info(
    "💡 **Como ler a comparação com WLS:** AUC/KS são essencialmente equivalentes — o sinal "
    "demográfico-contratual já está saturado nessas variáveis. O XGBoost ganha em "
    "**(a) probabilidade individual por contrato, (b) explicabilidade caso-a-caso via SHAP, "
    "(c) capacidade de incorporar features comportamentais sem regredir**. Pra subir AUC além de "
    "~0,60 precisamos de variáveis novas (uso longitudinal, recência, pagamento), não de modelo melhor."
)

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════════════════
tab_bands, tab_shap, tab_indiv, tab_perf, tab_trat = st.tabs([
    "📊 Faixas (CRITICO → SEGURO)",
    "🔍 Importância global (SHAP)",
    "👤 Drill por paciente",
    "🎯 Calibração & Performance",
    "👥 Perfis & Tratamento",
])

# ───────────────────────────────────────────────────────────────────────────
# TAB 1: FAIXAS
# ───────────────────────────────────────────────────────────────────────────
with tab_bands:
    st.markdown("### Distribuição em faixas (cortes fixos 0/200/400/600/800/1000)")
    st.caption(
        "Faixas calculadas sobre o **score OOF** (out-of-fold) — cada contrato é pontuado por um "
        "modelo que **não viu** esse contrato no treino. Honesto: nada é otimismo de overfit."
    )

    bcol1, bcol2 = st.columns(2)
    for col, dur in [(bcol1, "6"), (bcol2, "12")]:
        if dur not in models:
            continue
        m = models[dur]
        sub_df = df_full[df_full["duracao"] == dur].reset_index(drop=True)
        bs = compute_band_summary(sub_df, m["oof_scores"])
        with col:
            st.markdown(f"#### Plano {dur}m")

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=bs["band"].astype(str), y=bs["n"], name="Contratos",
                marker_color=[BAND_COLORS[b] for b in bs["band"].astype(str)],
                opacity=0.4,
                text=bs["n"].apply(lambda v: f"{int(v):,}"), textposition="outside",
            ))
            fig.add_trace(go.Scatter(
                x=bs["band"].astype(str), y=bs["churn_rate"],
                name="Churn (%)", mode="lines+markers+text",
                line=dict(width=3, color="crimson"),
                marker=dict(size=12, color=[BAND_COLORS[b] for b in bs["band"].astype(str)],
                            line=dict(width=2, color="white")),
                text=bs["churn_rate"].apply(lambda v: f"{v}%"), textposition="top center",
                textfont=dict(size=11, color="crimson"), yaxis="y2",
            ))
            fig.update_layout(
                title=f"Volume × churn por faixa — {dur}m",
                xaxis=dict(title=""),
                yaxis=dict(title="Contratos", type="log"),
                yaxis2=dict(title="Churn (%)", overlaying="y", side="right", range=[0, 100]),
                height=380, legend=dict(orientation="h", y=1.12),
            )
            st.plotly_chart(fig, use_container_width=True)

            st.dataframe(
                bs.rename(columns={
                    "band": "Faixa", "n": "Contratos", "churners": "Churners",
                    "churn_rate": "Churn (%)", "pct_volume": "% Volume", "lift": "Lift",
                }),
                hide_index=True, use_container_width=True,
            )

# ───────────────────────────────────────────────────────────────────────────
# TAB 2: SHAP GLOBAL
# ───────────────────────────────────────────────────────────────────────────
with tab_shap:
    st.markdown("### Importância global das features (SHAP)")
    st.caption(
        "**|mean SHAP|** = quanto a feature, em média, move o score de churn (escala log-odds). "
        "Quanto maior, mais influente a feature foi nas predições. "
        "**Direção média** = sinal típico do efeito (+ aumenta risco, − reduz)."
    )

    for dur in ["6", "12"]:
        if dur not in models:
            continue
        st.markdown(f"#### Plano {dur}m")
        imp = models[dur]["global_importance"].head(20).copy()
        imp_sorted = imp.iloc[::-1]
        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=imp_sorted["feature"],
            x=imp_sorted["mean_abs_shap"],
            orientation="h",
            marker_color=["#c0392b" if d > 0 else "#27ae60" for d in imp_sorted["mean_shap"]],
            text=imp_sorted.apply(
                lambda r: f"{r['mean_abs_shap']:.3f} (direção {r['mean_shap']:+.3f})", axis=1),
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>|SHAP|: %{x:.4f}<extra></extra>",
            showlegend=False,
        ))
        fig.update_layout(
            title=f"Top 20 features por importância SHAP — {dur}m",
            xaxis_title="|mean SHAP|",
            yaxis=dict(automargin=True),
            height=max(500, 30 * len(imp_sorted) + 80),
            margin=dict(l=10, r=200, t=50),
        )
        st.plotly_chart(fig, use_container_width=True)

        with st.expander(f"📋 Tabela completa — {dur}m"):
            st.dataframe(
                models[dur]["global_importance"].rename(columns={
                    "feature": "Feature",
                    "mean_abs_shap": "|mean SHAP|",
                    "mean_shap": "Direção média (sinal)",
                }),
                hide_index=True, use_container_width=True,
            )

# ───────────────────────────────────────────────────────────────────────────
# TAB 3: DRILL POR PACIENTE
# ───────────────────────────────────────────────────────────────────────────
with tab_indiv:
    st.markdown("### Drill por paciente — explicação do score (SHAP)")
    st.caption(
        "Para CADA paciente, mostramos os top fatores que mais elevam ou reduzem seu risco. "
        "Defensável caso-a-caso ao comitê — 'o modelo viu X, Y, Z e por isso colocou em CRITICO'."
    )

    dur_e = st.radio("Duração:", ["6", "12"], horizontal=True,
                       format_func=lambda x: f"{x}m", key="drill_dur")

    if dur_e in models:
        m = models[dur_e]
        sub_df = df_full[df_full["duracao"] == dur_e].reset_index(drop=True)
        sub_df = sub_df.assign(score=m["scores"], churn_prob=m["probs"])

        choice = st.radio("Selecionar paciente:",
                            options=["Top 10 maior risco", "Top 10 menor risco", "Por contract_id"],
                            horizontal=True, key="drill_choice")

        candidates = None
        if choice == "Top 10 maior risco":
            candidates = sub_df.nsmallest(10, "score")
        elif choice == "Top 10 menor risco":
            candidates = sub_df.nlargest(10, "score")
        else:
            cid = st.text_input("Digite o contract_id:")
            if cid:
                cid_str = cid.strip()
                candidates = sub_df[sub_df["contract_id"].astype(str) == cid_str]
                if candidates.empty:
                    st.warning(f"contract_id `{cid_str}` não encontrado nesta duração.")

        if candidates is not None and not candidates.empty:
            options = candidates.apply(
                lambda r: f"contract_id={r['contract_id']} · score={int(r['score'])} · "
                          f"prob={r['churn_prob']:.2f} · churn_real={int(r['churn'])}",
                axis=1,
            ).tolist()
            sel_idx_in_candidates = st.selectbox(
                "Paciente:", options=range(len(options)),
                format_func=lambda i: options[i], key="patient_sel",
            )
            patient_row = candidates.iloc[sel_idx_in_candidates]
            patient_row_idx = patient_row.name  # índice no sub_df

            # KPIs do paciente
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Score", f"{int(patient_row['score'])}")
            c2.metric("Prob. churn predita", f"{patient_row['churn_prob']*100:.1f}%")
            c3.metric("Churn observado", "SIM" if patient_row["churn"] == 1 else "NÃO")
            c4.metric("Contract ID", str(patient_row["contract_id"]))

            # Perfil
            st.markdown("**Perfil do paciente:**")
            perfil_cols = ["ciclo", "faixa_etaria", "cronico", "composicao_titular",
                           "sexo", "classe_social", "canal", "tem_odonto"]
            perfil_cols = [c for c in perfil_cols if c in patient_row.index]
            perfil_data = pd.DataFrame({c: [patient_row[c]] for c in perfil_cols})
            st.dataframe(perfil_data, hide_index=True, use_container_width=True)

            # Especialidades usadas
            esp_cols = [c for c in patient_row.index if c.startswith("usou_")]
            used = [c.replace("usou_", "") for c in esp_cols if patient_row[c] == 1]
            st.markdown(
                f"**Especialidades utilizadas:** {', '.join(used) if used else '(nenhuma)'}"
            )

            # Top 10 features SHAP que mais influenciam o score deste paciente
            st.markdown("### Top 10 fatores que mais influenciam o score deste paciente")
            shap_row = explain_individual(m, patient_row_idx, top_k=10)
            shap_row["impacto"] = shap_row["contribuicao"].apply(
                lambda v: "⬆️ aumenta risco" if v > 0 else "⬇️ reduz risco"
            )
            shap_row["valor"] = shap_row["valor"].apply(
                lambda v: f"{int(v)}" if isinstance(v, (int, np.integer, float)) and float(v).is_integer() else f"{v:.2f}"
            )

            fig = go.Figure()
            shap_sorted = shap_row.iloc[::-1]
            fig.add_trace(go.Bar(
                y=shap_sorted["feature"],
                x=shap_sorted["contribuicao"],
                orientation="h",
                marker_color=["#c0392b" if v > 0 else "#27ae60" for v in shap_sorted["contribuicao"]],
                text=shap_sorted.apply(
                    lambda r: f"{r['contribuicao']:+.3f} (valor={r['valor']})", axis=1),
                textposition="outside",
                showlegend=False,
            ))
            fig.add_vline(x=0, line_dash="dash", line_color="gray")
            fig.update_layout(
                title=f"Contribuição SHAP — paciente {patient_row['contract_id']}",
                xaxis_title="Contribuição ao log-odds de churn (positivo = aumenta risco)",
                yaxis=dict(automargin=True),
                height=420, margin=dict(l=10, r=150, t=50),
            )
            st.plotly_chart(fig, use_container_width=True)

            st.dataframe(
                shap_row.rename(columns={
                    "feature": "Feature",
                    "valor": "Valor",
                    "contribuicao": "Contribuição (log-odds)",
                    "impacto": "Impacto",
                }),
                hide_index=True, use_container_width=True,
            )

# ───────────────────────────────────────────────────────────────────────────
# TAB 4: CALIBRAÇÃO E PERFORMANCE
# ───────────────────────────────────────────────────────────────────────────
with tab_perf:
    st.markdown("### Calibração por decis (out-of-fold)")
    st.caption(
        "Probabilidade predita (CV out-of-fold) vs churn real, agrupados em 10 decis. "
        "Pontos próximos da diagonal = modelo bem calibrado."
    )

    ccol1, ccol2 = st.columns(2)
    for col, dur in [(ccol1, "6"), (ccol2, "12")]:
        if dur not in models:
            continue
        m = models[dur]
        y = df_full[df_full["duracao"] == dur]["churn"].values
        cal = compute_calibration(y, m["oof_proba"], n_bins=10)
        with col:
            st.markdown(f"#### Plano {dur}m")
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=cal["churn_pred"], y=cal["churn_real"],
                mode="markers+text",
                marker=dict(size=cal["n"] / cal["n"].max() * 25 + 8, color=DUR_COLORS[dur]),
                text=cal["decil"].apply(lambda d: f"d{int(d)+1}"),
                textposition="top center", textfont=dict(size=9),
                name="Decis",
            ))
            lo = float(min(cal["churn_pred"].min(), cal["churn_real"].min())) - 3
            hi = float(max(cal["churn_pred"].max(), cal["churn_real"].max())) + 3
            fig.add_trace(go.Scatter(
                x=[lo, hi], y=[lo, hi], mode="lines",
                line=dict(dash="dash", color="gray"), name="Calibração perfeita",
            ))
            fig.update_layout(
                title=f"Calibração — {dur}m",
                xaxis=dict(title="Churn predito (%)", range=[lo, hi]),
                yaxis=dict(title="Churn real (%)", range=[lo, hi]),
                height=380, legend=dict(orientation="h", y=1.1),
            )
            st.plotly_chart(fig, use_container_width=True)

            st.dataframe(
                cal.rename(columns={
                    "decil": "Decil", "n": "Contratos",
                    "churn_pred": "Predito (%)", "churn_real": "Real (%)", "erro": "Erro (p.p.)",
                }),
                hide_index=True, use_container_width=True,
            )

    st.markdown("---")
    st.markdown("### Histograma de probabilidades preditas (churners vs retidos) — OOF")
    st.caption(
        "Distribuições calculadas com prob OOF. Quanto mais separadas, melhor a discriminação."
    )

    for dur in ["6", "12"]:
        if dur not in models:
            continue
        m = models[dur]
        sub_df = df_full[df_full["duracao"] == dur].reset_index(drop=True)
        sub_df = sub_df.assign(churn_prob=m["oof_proba"])
        st.markdown(f"#### Plano {dur}m")
        fig = px.histogram(
            sub_df, x="churn_prob", color="churn", nbins=50,
            barmode="overlay", opacity=0.6,
            color_discrete_map={0: "#27ae60", 1: "#c0392b"},
            labels={"churn_prob": "Probabilidade de churn predita (OOF)", "churn": "Churn real"},
        )
        fig.update_layout(height=320, legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.markdown("### ⚖️ Comparação direta WLS vs XGBoost")
    st.caption(
        "Mesma base, mesmas durações, métricas comparáveis. **Não há ganho de discriminação geral** "
        "— o que muda é granularidade (perfil → contrato), calibração e explicabilidade individual."
    )

    cmp_rows = []
    for dur in ["6", "12"]:
        if dur not in models:
            continue
        m = models[dur]
        y_oof = m["y"]
        p_oof = m["oof_proba"]
        ece = expected_calibration_error(y_oof, p_oof)
        slope, _ = platt_slope_intercept(y_oof, p_oof)
        _, _, lift10 = targeting_topk(y_oof, p_oof, pct=0.10)
        wls = WLS_BENCHMARK.get(dur, {})
        cmp_rows.append({
            "Duração": f"{dur}m",
            "Métrica": "AUC / C-index",
            "WLS": f"{wls.get('auc', '?'):.3f}",
            "XGBoost (OOF)": f"{m['metrics']['auc_cv']:.3f}",
            "Δ": f"{m['metrics']['auc_cv'] - wls.get('auc', 0):+.3f}",
        })
        cmp_rows.append({
            "Duração": f"{dur}m",
            "Métrica": "KS (p.p.)",
            "WLS": f"{wls.get('ks', '?'):.1f}",
            "XGBoost (OOF)": f"{m['metrics']['ks_cv']:.1f}",
            "Δ": f"{m['metrics']['ks_cv'] - wls.get('ks', 0):+.1f}",
        })
        cmp_rows.append({
            "Duração": f"{dur}m",
            "Métrica": "Calibração (ECE p.p.)",
            "WLS": "~1.2",
            "XGBoost (OOF)": f"{ece:.2f}",
            "Δ": "—",
        })
        cmp_rows.append({
            "Duração": f"{dur}m",
            "Métrica": "Granularidade",
            "WLS": "perfil agregado (~70 perfis)",
            "XGBoost (OOF)": f"contrato individual ({len(y_oof):,})",
            "Δ": "—",
        })
        cmp_rows.append({
            "Duração": f"{dur}m",
            "Métrica": "Explicabilidade caso",
            "WLS": "coef × indicador",
            "XGBoost (OOF)": "SHAP por contrato",
            "Δ": "—",
        })
    st.dataframe(pd.DataFrame(cmp_rows), hide_index=True, use_container_width=True)

st.markdown("---")
with st.expander("📖 Metodologia · XGBoost + SHAP + tuning Optuna", expanded=False):
    tuning_block = ""
    if TUNED_INFO:
        rows = []
        for dur in ["6", "12"]:
            if dur in TUNED_INFO:
                ti = TUNED_INFO[dur]
                bp = ti["best_params"]
                rows.append(
                    f"- **{ti['duracao']}**: AUC baseline {ti['baseline_auc']:.4f} → "
                    f"tunado {ti['best_auc']:.4f} ({ti['delta_auc']:+.4f}) · "
                    f"{ti['n_trials']} trials, {ti['n_pruned']} pruned · "
                    f"`max_depth={bp['max_depth']}` `lr={bp['learning_rate']:.3f}` "
                    f"`min_child_weight={bp['min_child_weight']}` "
                    f"`gamma={bp['gamma']:.2f}` `reg_λ={bp['reg_lambda']:.3f}`"
                )
        tuning_block = "\n".join(rows)

    st.markdown(f"""
    **Modelo:** XGBoost (gradient boosting de árvores) — 1 modelo por duração.

    **Hiperparâmetros:** auto-carregados de `results_comite/xgb_best_params.json`
    (saída de `scripts/tune_xgb_optuna.py`). Fallback para `XGB_PARAMS_DEFAULT` se
    o arquivo não existir.

    **Tuning Optuna (5-fold CV + MedianPruner):**
{tuning_block if tuning_block else '    - Ainda não rodado. Rode `uv run python scripts/tune_xgb_optuna.py` para tunar.'}

    **Anti-overfit do modelo final:** o `n_estimators` do modelo servido é a média de
    `best_iteration` dos 5 folds (não 600 fixo). Reduz o gap AUC train-CV de ~0,058
    para ~0,014 — o modelo servido tem a mesma capacidade que o CV mediu.

    **Validação:** AUC out-of-fold de 5-fold stratified CV. Treino final usa toda a base
    com `n_estimators = avg(best_iter_folds)` pra estabilidade das predições e SHAP values.

    **SHAP (SHapley Additive exPlanations):**
    - **Global:** importância média (|SHAP|) e sinal médio de cada feature.
    - **Individual:** decomposição do score de UM paciente em contribuições por feature.
    - Vantagem vs feature importance clássica do XGBoost: SHAP respeita interações e tem
      interpretação aditiva consistente (soma das contribuições = log-odds final).

    **Sobre o AUC similar ao WLS — sendo honesto:** o XGBoost **não ganha** em ordenação geral.
    AUC OOF fica em ~0,58-0,60, mesmo intervalo do WLS. Tunamos 80 trials com Optuna e o teto
    confirmou-se como ~0,60. O ganho real do XGBoost é:
    - **Granularidade**: cada contrato tem sua própria probabilidade (não herdada do perfil).
    - **Calibração**: ECE ~0,4 p.p. e Platt slope ~1,02 — a probabilidade é confiável como número.
    - **SHAP individual**: defesa caso-a-caso (essencial pra targeting operacional do Growth).
    Pra subir AUC além de 0,60 precisamos de **variáveis novas** (uso longitudinal, recência,
    histórico de pagamento, suporte), não de modelo melhor.

    **Próximo passo (Fase 2):** uplift causal por especialidade — pra cada paciente, estimar
    quanto cada ação reduziria seu churn. T-learner com XGBoost (1 modelo tratado, 1 controle)
    por especialidade.

    **Caveats:**
    - XGBoost é menos defensável que logistic em "linguagem de coeficiente". SHAP é o substituto
      mas exige explicação ao comitê.
    - Black-box parcial: SHAP explica decisões, mas não dá teste estatístico clássico.
      Pra defender efeitos causais, A/B test é necessário (próxima etapa do Plano de Ações).
    - Lift top-10% é ~1,25× — útil pra priorizar, modesto pra acionar isoladamente. Combine
      com SHAP individual para entender o "porquê" de cada caso.
    """)


# ───────────────────────────────────────────────────────────────────────────
# TAB 5: PERSONAS ACIONÁVEIS
# ───────────────────────────────────────────────────────────────────────────
with tab_trat:
    st.markdown("### 👥 Estratégia de Targeting Causal: Personas Acionáveis")
    st.caption(
        "Traduzimos o score de probabilidade individual do XGBoost e o comportamento "
        "de consumo dos clientes em **5 Perfis (Personas) com Playbooks de Growth e CRM específicos**."
    )

    dur_p = st.radio(
        "Selecione o plano para visualização das Personas:",
        ["6", "12"],
        horizontal=True,
        format_func=lambda x: f"Plano {x} meses",
        key="persona_dur"
    )

    if dur_p in models:
        m = models[dur_p]
        sub_df = df_full[df_full["duracao"] == dur_p].reset_index(drop=True)
        
        # Atribuir scores operacionais (in-sample)
        sub_df = sub_df.assign(score=m["scores"], churn_prob=m["probs"])
        sub_df["persona"] = assign_actionable_personas(sub_df, sub_df["score"])
        
        total_n = len(sub_df)
        
        # Agrupamento para a tabela de resumo
        summary = sub_df.groupby("persona").agg(
            contratos=("churn", "count"),
            churners=("churn", "sum"),
            churn_rate=("churn", "mean")
        ).reset_index()
        
        summary["pct_base"] = summary["contratos"] / total_n

        # Playbooks breves para a tabela consolidada
        playbook_rec = {
            "1. Fantasma do Onboarding": "Boas-vindas ativo / Agendamento assistido no 1º ciclo",
            "2. Crônico Desengajado": "Retorno preventivo facilitado e desconto em farmácias",
            "3. Churn Silencioso (Ex-Ativo)": "Cupom para especialidades eletivas / Telemedicina",
            "4. Risco Financeiro / Geral": "Validação de cartão / Pix recorrente e suporte financeiro",
            "5. Seguro / Baixo Risco": "Upgrade familiar / Upsell Odonto e Member-Get-Member"
        }
        summary["Recomendação"] = summary["persona"].map(playbook_rec)

        # 1. Tabela Consolidada com Design Premium (st.dataframe)
        st.markdown("#### 📊 Painel Geral das Personas")
        st.dataframe(
            summary.rename(columns={
                "persona": "Persona",
                "contratos": "Volume (N)",
                "pct_base": "% da Base",
                "churners": "Cancelamentos",
                "churn_rate": "Taxa de Churn",
            }),
            column_config={
                "Persona": st.column_config.TextColumn("👥 Persona", width="medium"),
                "Volume (N)": st.column_config.NumberColumn("🔢 Volume (N)", format="%d"),
                "% da Base": st.column_config.NumberColumn("📊 % da Base", format="%.1%"),
                "Cancelamentos": st.column_config.NumberColumn("❌ Churners", format="%d"),
                "Taxa de Churn": st.column_config.ProgressColumn(
                    "📉 Churn Rate",
                    format="%.2f%%",
                    min_value=0.0,
                    max_value=1.0
                ),
                "Recomendação": st.column_config.TextColumn("🎯 Playbook Recomendado", width="large")
            },
            hide_index=True,
            use_container_width=True
        )

        st.markdown("---")

        # 2. Gráfico Plotly de Eixo Duplo Y (Volume vs. Churn Rate)
        st.markdown("#### 📈 Risco vs. Representatividade")
        
        fig_pers = go.Figure()
        
        # Eixo Y1: Volume da Base (Barras)
        # Paleta de cores moderna e profissional
        colors = ["#ff9f43", "#ff6b6b", "#48dbfb", "#ee5253", "#1dd1a1"]
        fig_pers.add_trace(go.Bar(
            x=summary["persona"],
            y=summary["contratos"],
            name="Volume (N)",
            yaxis="y1",
            marker_color=colors,
            opacity=0.7,
            text=summary["contratos"].apply(lambda v: f"{int(v):,}"),
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>Contratos: %{y:,}<extra></extra>"
        ))
        
        # Eixo Y2: Taxa de Churn em porcentagem (Linha)
        fig_pers.add_trace(go.Scatter(
            x=summary["persona"],
            y=summary["churn_rate"] * 100,
            name="Churn Real (%)",
            yaxis="y2",
            mode="lines+markers+text",
            line=dict(color="#0d3b8b", width=4),
            marker=dict(size=10, symbol="circle", color="#0d3b8b", line=dict(color="white", width=2)),
            text=(summary["churn_rate"] * 100).apply(lambda v: f"{v:.1f}%"),
            textposition="top center",
            textfont=dict(color="#0d3b8b", size=11, bold=True),
            hovertemplate="<b>%{x}</b><br>Churn Rate: %{y:.2f}%<extra></extra>"
        ))
        
        fig_pers.update_layout(
            title=dict(
                text=f"Volume de Contratos vs. Taxa de Churn Real por Persona ({dur_p}m)",
                font=dict(size=16)
            ),
            xaxis=dict(title=""),
            yaxis=dict(
                title="Volume de Contratos (N)",
                side="left",
                showgrid=True,
                gridcolor="rgba(0,0,0,0.05)"
            ),
            yaxis2=dict(
                title="Taxa de Churn Real (%)",
                side="right",
                overlaying="y",
                range=[0, max(summary["churn_rate"] * 100) + 10],
                showgrid=False
            ),
            legend=dict(orientation="h", y=1.12, x=0.25),
            height=400,
            margin=dict(l=10, r=10, t=60, b=10)
        )
        st.plotly_chart(fig_pers, use_container_width=True)

        st.markdown("---")

        # 3. Playbooks Detalhados e Exportação CSV (st.expander)
        st.markdown("#### 🎯 Playbooks Estratégicos & Ação de CRM")
        st.caption(
            "Expanda cada perfil para visualizar o diagnóstico de Churn, canais de contato preferenciais e "
            "fazer o download da lista de contratos elegíveis para campanhas no WhatsApp/CRM."
        )

        # Dados detalhados de cada persona
        playbooks_detail = {
            "1. Fantasma do Onboarding": {
                "comportamento": "Contratos novos de 1º ciclo que assinaram mas não realizaram nenhuma consulta presencial/telemedicina ou exames. Indício clássico de barreira no onboarding ou esquecimento do benefício.",
                "canal": "💬 WhatsApp Ativo (Automatizado) & SMS nos primeiros 15 dias da assinatura.",
                "growth": "Fornecer uma jornada de ativação guiada. Oferecer agendamento facilitado via chat de Clínico Geral, Pediatria ou Ginecologia (especialidades porta-de-entrada). Se necessário, conceder incentivo ou isenção em coparticipação na 1ª consulta.",
            },
            "2. Crônico Desengajado": {
                "comportamento": "Pacientes crônicos identificados (cronico == 'S') com alto risco de churn. Embora já tenham consumido no passado, estão desengajados de consultas e exames de rotina, quebrando a linha de cuidado.",
                "canal": "📞 Ligação Humanizada (Outbound) de enfermeiros/concierges de saúde + WhatsApp.",
                "growth": "Campanha focada em 'Retomada de Cuidado'. Apresentar os riscos da descontinuidade do tratamento e agendar um retorno com o médico especialista de preferência. Oferecer parcerias com redes de farmácias com descontos agressivos em medicamentos de uso contínuo.",
            },
            "3. Churn Silencioso (Ex-Ativo)": {
                "comportamento": "Clientes de médio risco (score entre 400 e 599) que já utilizaram os serviços no passado mas cuja frequência esfriou. Estão sob risco de churn passivo nas datas de renovação ou cobrança por falta de uso recente.",
                "canal": "📧 E-mail Marketing educativo com novidades + WhatsApp com benefícios.",
                "growth": "Nutrição de conteúdo focado em bem-estar e prevenção. Oferta de consultas check-up preventivas gratuitas ou cupons exclusivos para especialidades de bem-estar (Ex: Nutrição, Dermatologia, Psicologia) com agendamento facilitado.",
            },
            "4. Risco Financeiro / Geral": {
                "comportamento": "Contratos de alto risco (score < 400) que não são novos nem crônicos. A dor costuma ser inadimplência involuntária (falhas de cartão de crédito recorrentes) ou desengajamento operacional geral por má experiência no app ou clínicas.",
                "canal": "💬 WhatsApp (Régua Transacional amigável) + E-mail estruturado.",
                "growth": "Campanha preventiva de atualização de dados de pagamento antes da cobrança (régua pré-vencimento). Oferecer opções mais estáveis como PIX recorrente ou boleto com desconto de adimplência. Disponibilizar canal ágil de suporte financeiro no WhatsApp para contornar cartões recusados.",
            },
            "5. Seguro / Baixo Risco": {
                "comportamento": "Clientes com alto score (>= 600) e baixíssimo churn. Alta percepção de valor, uso regular das clínicas e promotores da marca dr.consulta.",
                "canal": "📲 Push Notification no app e E-mail de relacionamento.",
                "growth": "Fidelização e Expansão. Campanhas de Upsell (Ex: upgrade para plano Odonto familiar, inclusão de dependentes com descontos progressivos) e Member-Get-Member (indicação de amigos em troca de cashback ou isenção de mensalidade).",
            }
        }

        for persona_name, p_data in playbooks_detail.items():
            # Filtrar dataframe desta persona
            persona_df = sub_df[sub_df["persona"] == persona_name].reset_index(drop=True)
            p_n = len(persona_df)
            p_pct = (p_n / total_n) * 100
            p_churn_rate = persona_df["churn"].mean() * 100
            
            expander_title = f"{persona_name} (N = {p_n:,} | {p_pct:.1f}% da base | Churn: {p_churn_rate:.1f}%)"
            
            with st.expander(expander_title):
                st.markdown(f"**🔴 Diagnóstico de Churn:** {p_data['comportamento']}")
                st.markdown(f"**📢 Canal de Contato:** {p_data['canal']}")
                st.markdown(f"**🚀 Tese de Growth & Playbook:** {p_data['growth']}")
                
                # Preparar colunas importantes para exportação
                export_cols = [
                    "contract_id", "account_id", "score", "churn_prob", 
                    "ciclo", "faixa_etaria", "cronico", "sexo", 
                    "classe_social", "canal", "usou_cm", "usou_exames"
                ]
                # Garantir que todas as colunas existem antes de exportar
                available_cols = [c for c in export_cols if c in persona_df.columns]
                csv_data = persona_df[available_cols].copy()
                csv_data = csv_data.rename(columns={
                    "score": "score_xgb",
                    "churn_prob": "probabilidade_churn"
                })
                
                # Converter para CSV
                csv_bytes = csv_data.to_csv(index=False).encode('utf-8')
                
                file_name_clean = persona_name.lower().replace(".", "").replace(" / ", "_").replace(" (", "_").replace(")", "").replace(" ", "_")
                
                st.download_button(
                    label=f"📥 Baixar CSV - {persona_name} ({p_n:,} clientes)",
                    data=csv_bytes,
                    file_name=f"churn_growth_{file_name_clean}_plano_{dur_p}m.csv",
                    mime="text/csv",
                    key=f"dl_{dur_p}_{file_name_clean}"
                )

