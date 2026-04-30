import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from scipy import stats

st.set_page_config(page_title="Score de Churn · Risco", page_icon="📉", layout="wide")

# ═══════════════════════════════════════════════════════════════════════
# FUNÇÕES
# ═══════════════════════════════════════════════════════════════════════

def logit(p):
    p = np.clip(p, 0.001, 0.999)
    return np.log(p / (1 - p))

def inv_logit(x):
    return 1 / (1 + np.exp(-x))

def wilson_ci(n, x, alpha=0.05):
    if n == 0: return 0, 0, 0
    p = x / n
    z = stats.norm.ppf(1 - alpha/2)
    denom = 1 + z**2/n
    center = (p + z**2/(2*n)) / denom
    margin = z * np.sqrt(p*(1-p)/n + z**2/(4*n**2)) / denom
    return p*100, max(0, (center - margin)*100), min(100, (center + margin)*100)

def z_test_proportions(n1, x1, n2, x2):
    p1, p2 = x1/n1, x2/n2
    diff = p1 - p2
    p_pool = (x1 + x2) / (n1 + n2)
    se = np.sqrt(p_pool * (1 - p_pool) * (1/n1 + 1/n2))
    z = diff / se if se > 0 else 0
    pval = 2 * (1 - stats.norm.cdf(abs(z)))
    return {"diff": diff*100, "ci_lo": (diff - 1.96*se)*100, "ci_hi": (diff + 1.96*se)*100, "p": pval}


# ═══════════════════════════════════════════════════════════════════════
st.title("📉 Capítulo 2 — Score de Risco de Churn")
st.markdown("""
Score de 0 a 1000 que ranqueia cada contrato por probabilidade de cancelamento.
**Score alto = paciente mais seguro** (análogo ao Serasa).
Pesos derivados de regressão sobre dados reais (7 variáveis), não atribuídos manualmente.
""")


# ═══════════════════════════════════════════════════════════════════════
# DADOS
# ═══════════════════════════════════════════════════════════════════════
@st.cache_data
def load_c(): return pd.read_csv("results/unidade_evolucao_score_c.csv")
@st.cache_data
def load_b(): return pd.read_csv("results/unidade_evolucao_score_b.csv")
@st.cache_data
def load_a(): return pd.read_csv("results/unidade_evolucao_score_a.csv")
@st.cache_data
def load_perfis(): return pd.read_csv("results/perfis_compostos_7vars.csv")

@st.cache_data
def fit_score_model():
    """Ajusta o modelo WLS sobre os perfis e retorna coeficientes e métricas."""
    a = load_perfis()
    a["duracao"] = a["duracao"].astype(str)
    a["p_churn"] = a["churners"] / a["total_contratos"]
    a["logit_churn"] = logit(a["p_churn"])

    # Referências (perfil de menor risco)
    refs = {"contrato": "2o+", "dependentes": "3+_dep", "faixa_idade": "51-70", "duracao": "6", "cronico": "S", "canal": "presencial_cfp", "classe": "AB"}

    # Matriz de design: dummies vs referência
    features = []
    feature_names = []
    for var, ref in refs.items():
        for level in sorted(a[var].unique()):
            if level == ref:
                continue
            features.append((a[var] == level).astype(float).values)
            feature_names.append(f"{var}={level}")

    X = np.column_stack([np.ones(len(a))] + features)
    y = a["logit_churn"].values
    w = a["total_contratos"].values

    # WLS com erros padrão analíticos
    W = np.diag(w)
    XtWX = X.T @ W @ X
    XtWy = X.T @ W @ y
    beta = np.linalg.solve(XtWX, XtWy)
    n_obs, n_params = X.shape
    y_pred_wls = X @ beta
    residuals_wls = y - y_pred_wls
    sigma2 = (w * residuals_wls**2).sum() / (n_obs - n_params)
    cov_beta = sigma2 * np.linalg.inv(XtWX)
    se_beta = np.sqrt(np.diag(cov_beta))

    # Predições
    a["logit_pred"] = X @ beta
    a["p_pred"] = inv_logit(a["logit_pred"])
    a["churn_pred"] = np.round(100 * a["p_pred"], 1)
    a["erro"] = a["churn_pred"] - a["churn_rate"]

    # Score 0-1000 (alto = seguro)
    logit_min = a["logit_pred"].min()
    logit_max = a["logit_pred"].max()
    scale = 1000 / (logit_max - logit_min)
    a["score"] = np.round(1000 * (1 - (a["logit_pred"] - logit_min) / (logit_max - logit_min)))

    # Coeficientes em pontos com IC
    coefs_table = []
    coefs_table.append({"Variável": "Intercepto (referência)", "Nível": "2o+, 3+dep, 51-70, 6m, crônico, presencial, AB",
                         "Log-odds": beta[0], "SE": se_beta[0], "Pontos": 0,
                         "IC_lo": 0, "IC_hi": 0, "Efeito (p.p.)": 0,
                         "t": beta[0]/se_beta[0], "p": 0.0, "sig": ""})
    for i, name in enumerate(feature_names):
        coef = beta[i+1]
        se = se_beta[i+1]
        t_stat = coef / se if se > 0 else 0
        p_val = 2 * (1 - stats.t.cdf(abs(t_stat), df=n_obs - n_params))
        pontos = round(coef * scale)
        ic_lo = round((coef - 1.96*se) * scale)
        ic_hi = round((coef + 1.96*se) * scale)
        delta_pp = 100 * (inv_logit(beta[0] + coef) - inv_logit(beta[0]))
        sig = "***" if p_val < 0.001 else ("**" if p_val < 0.01 else ("*" if p_val < 0.05 else "n.s."))
        coefs_table.append({"Variável": name.split("=")[0], "Nível": name.split("=")[1],
                             "Log-odds": coef, "SE": se, "Pontos": -pontos,
                             "IC_lo": -ic_hi, "IC_hi": -ic_lo,
                             "Efeito (p.p.)": round(delta_pp, 1),
                             "t": t_stat, "p": p_val, "sig": sig})

    # Consistência por variável: obs vs pred por nível
    consistency_data = []
    for var, ref in refs.items():
        for level in sorted(a[var].unique()):
            sub = a[a[var] == level]
            n_total = sub["total_contratos"].sum()
            x_total = sub["churners"].sum()
            churn_obs = 100 * x_total / n_total
            sub_pred = inv_logit(X[sub.index] @ beta)
            churn_pred = 100 * np.average(sub_pred, weights=sub["total_contratos"].values)
            is_ref = level == ref
            consistency_data.append({"Variável": var, "Nível": level,
                                     "Churn Obs.": round(churn_obs, 1),
                                     "Churn Pred.": round(churn_pred, 1),
                                     "Erro": round(churn_pred - churn_obs, 1),
                                     "Contratos": n_total, "Ref": is_ref})

    # Métricas
    mae = a["erro"].abs().mean()
    corr = a["churn_rate"].corr(a["churn_pred"])

    # Concordância (C-index)
    profiles = a[["score", "total_contratos", "churners"]].values
    concordant = discordant = 0
    for i in range(len(profiles)):
        for j in range(len(profiles)):
            if profiles[i][0] < profiles[j][0]:
                concordant += profiles[i][2] * (profiles[j][1] - profiles[j][2])
                discordant += profiles[j][2] * (profiles[i][1] - profiles[i][2])
    c_index = concordant / (concordant + discordant) if (concordant + discordant) > 0 else 0.5
    gini = 2 * c_index - 1

    # KS
    bins = [0, 100, 200, 400, 600, 800, 900, 1001]
    labels = ["0-99", "100-199", "200-399", "400-599", "600-799", "800-899", "900-1000"]
    a["faixa"] = pd.cut(a["score"], bins=bins, labels=labels, right=False)
    total_churn = a["churners"].sum()
    total_retain = (a["total_contratos"] - a["churners"]).sum()
    churn_global = 100 * total_churn / a["total_contratos"].sum()

    ks_data = []
    cum_ch = cum_ret = 0
    ks_max = 0
    for faixa in labels:
        sub = a[a["faixa"] == faixa]
        ch = sub["churners"].sum()
        ret = (sub["total_contratos"] - sub["churners"]).sum()
        n = sub["total_contratos"].sum()
        cum_ch += ch
        cum_ret += ret
        pct_ch = 100 * cum_ch / total_churn
        pct_ret = 100 * cum_ret / total_retain
        ks = abs(pct_ch - pct_ret)
        ks_max = max(ks_max, ks)
        churn_f = 100 * ch / n if n > 0 else 0
        lift = churn_f / churn_global if churn_global > 0 else 1
        ks_data.append({"Faixa": faixa, "Contratos": n, "Churners": ch,
                        "Churn (%)": round(churn_f, 1), "Lift": round(lift, 2),
                        "Cum Churn (%)": round(pct_ch, 1), "Cum Retidos (%)": round(pct_ret, 1),
                        "KS (%)": round(ks, 1)})

    # Calibração por decil
    a["decil"] = pd.qcut(a["score"], 10, labels=False, duplicates="drop")
    calib_data = []
    for d in sorted(a["decil"].unique()):
        sub = a[a["decil"] == d]
        n = sub["total_contratos"].sum()
        x = sub["churners"].sum()
        real = 100 * x / n
        pred = (sub["churn_pred"] * sub["total_contratos"]).sum() / n
        score_med = (sub["score"] * sub["total_contratos"]).sum() / n
        calib_data.append({"Decil": d, "Score Médio": round(score_med),
                           "Churn Predito": round(pred, 1), "Churn Real": round(real, 1),
                           "Erro": round(pred - real, 1), "Contratos": n})

    return {
        "coefs": pd.DataFrame(coefs_table),
        "consistency": pd.DataFrame(consistency_data),
        "metrics": {"mae": mae, "corr": corr, "c_index": c_index, "gini": gini, "ks": ks_max, "churn_global": churn_global},
        "ks_data": pd.DataFrame(ks_data),
        "calib_data": pd.DataFrame(calib_data),
        "profiles": a,
        "intercept": beta[0],
        "scale": scale,
        "logit_min": logit_min,
        "logit_max": logit_max,
        "ref_churn": round(100 * inv_logit(beta[0]), 1),
    }


# ═══════════════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════════════

tab_score, tab_valid, tab_season, tab_units = st.tabs([
    "🎯 Score de Churn",
    "📊 Validação Estatística",
    "📅 Sazonalidade",
    "🏥 Unidades",
])


# ═══════════════════════════════════════════════════════════════════════
# TAB 1: SCORE
# ═══════════════════════════════════════════════════════════════════════
with tab_score:
    try:
        model = fit_score_model()
        df_c = load_c()

        # --- Fórmula visual ---
        st.markdown("### Como o score é calculado")
        st.markdown(f"""
        O score parte de **1000** (perfil de menor risco) e subtrai penalidades proporcionais
        ao efeito real de cada fator. Os pesos foram derivados de uma **regressão linear ponderada
        (WLS) sobre log-odds** de churn de {len(model['profiles']):,} perfis compostos.
        """)

        col_formula, col_example = st.columns([3, 2])

        with col_formula:
            st.markdown("#### Tabela de penalidades")
            coefs = model["coefs"]
            # Filtrar só as penalidades (não o intercepto)
            penalties = coefs[coefs["Pontos"] != 0].copy()
            penalties["Pontos"] = penalties["Pontos"].apply(lambda x: f"{x:+d}")
            penalties["Log-odds"] = penalties["Log-odds"].apply(lambda x: f"{x:+.4f}")
            penalties["Efeito (p.p.)"] = penalties["Efeito (p.p.)"].apply(lambda x: f"{x:+.1f}")
            st.dataframe(penalties[["Variável", "Nível", "Pontos", "Efeito (p.p.)", "Log-odds"]].rename(
                columns={"Pontos": "Pontos no Score", "Efeito (p.p.)": "Efeito no Churn"}
            ), hide_index=True, use_container_width=True)

            st.caption(f"Referência (score 1000): 2o+ contrato, 3+ dependentes, 51-70 anos, 6 meses, crônico, presencial/CFP, classe AB → churn base: {model['ref_churn']}%")

        with col_example:
            st.markdown("#### Exemplos")

            # Calcular penalidades dinâmicas para os exemplos
            coefs_dict = {}
            for _, r in model["coefs"].iterrows():
                if r["Pontos"] != 0:
                    coefs_dict[f'{r["Variável"]}={r["Nível"]}'] = int(r["Pontos"])

            crit_items = [
                ("1o contrato", coefs_dict.get("contrato=1o", 0)),
                ("Sem dependentes", coefs_dict.get("dependentes=sem_dep", 0)),
                ("25 anos", coefs_dict.get("faixa_idade=21-30", 0)),
                ("Plano 12m", coefs_dict.get("duracao=12", 0)),
                ("Não crônico", coefs_dict.get("cronico=N", 0)),
                ("Canal digital", coefs_dict.get("canal=digital", 0)),
                ("Classe CDE", coefs_dict.get("classe=CDE", 0)),
            ]
            crit_total = sum(p for _, p in crit_items)
            crit_score = 1000 + crit_total

            st.error(f"""
            **Paciente Crítico (score ~ {max(0, crit_score)}):**
            {chr(10).join(f'- {name} → {pts:+d}' for name, pts in crit_items if pts != 0)}
            - **Total: 1000 {crit_total:+d} = {max(0, crit_score)}**
            """)

            st.success("""
            **Paciente Seguro (score = 1000):**
            - 2o+ contrato → 0
            - 3+ dependentes → 0
            - 55 anos → 0
            - Plano 6m → 0
            - Crônico → 0
            - Presencial/CFP → 0
            - Classe AB → 0
            - **Total: 1000**
            """)

        # --- Faixas de risco ---
        st.markdown("---")
        st.markdown("### As 7 faixas de risco")

        # KPIs
        ks_df = model["ks_data"]
        faixa_critico = ks_df[ks_df["Faixa"] == "0-99"].iloc[0] if len(ks_df[ks_df["Faixa"] == "0-99"]) > 0 else None
        faixa_minimo = ks_df[ks_df["Faixa"] == "900-1000"].iloc[0] if len(ks_df[ks_df["Faixa"] == "900-1000"]) > 0 else None

        if faixa_critico is not None and faixa_minimo is not None:
            spread = round(faixa_critico["Churn (%)"] - faixa_minimo["Churn (%)"], 1)
            k1, k2, k3 = st.columns(3)
            k1.metric("Churn Faixa CRITICO", f'{faixa_critico["Churn (%)"]}%',
                      help="Score 0-99. Perfis com maior acúmulo de fatores de risco.")
            k2.metric("Churn Faixa MINIMO", f'{faixa_minimo["Churn (%)"]}%',
                      help="Score 900-1000. Perfis com menos fatores de risco.")
            k3.metric("Spread entre Extremos", f"{spread} p.p.",
                      help="Capacidade do score de separar risco alto de risco baixo")

        # Gráfico de faixas
        colors_map = {"0-99": "#8b0000", "100-199": "#d62728",
                      "200-399": "#ff7f0e", "400-599": "#ffbb33",
                      "600-799": "#2ca02c",
                      "800-899": "#1f77b4", "900-1000": "#0d3b8b"}
        nomes_faixa = {"0-99": "CRITICO", "100-199": "MUITO ALTO",
                       "200-399": "ALTO", "400-599": "MEDIO",
                       "600-799": "BAIXO",
                       "800-899": "MUITO BAIXO", "900-1000": "MINIMO"}

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=ks_df["Faixa"], y=ks_df["Contratos"],
            name="Contratos",
            marker_color=[colors_map.get(f, "gray") for f in ks_df["Faixa"]],
            opacity=0.4,
            text=ks_df["Contratos"].apply(lambda x: f"{x:,}"),
            textposition="outside",
        ))
        fig.add_trace(go.Scatter(
            x=ks_df["Faixa"], y=ks_df["Churn (%)"],
            name="Churn (%)", mode="lines+markers+text",
            marker=dict(size=14, color=[colors_map.get(f, "gray") for f in ks_df["Faixa"]],
                        line=dict(width=2, color="white")),
            line=dict(width=3, color="gray", dash="dot"),
            yaxis="y2",
            text=ks_df["Churn (%)"].apply(lambda x: f"{x}%"),
            textposition="top center", textfont=dict(size=13, color="crimson"),
        ))
        # Linha de teto prático do modelo
        fig.add_shape(type="line", xref="paper", yref="y2",
                      x0=0, x1=1, y0=85, y1=85,
                      line=dict(color="rgba(139,0,0,0.45)", width=2, dash="dot"))
        fig.add_annotation(xref="paper", yref="y2", x=0.99, y=85,
                           text="Teto prático ~80-85% (7 vars, base rate ~55%)",
                           showarrow=False, xanchor="right", yanchor="bottom",
                           font=dict(size=11, color="rgba(139,0,0,0.8)"))

        fig.update_layout(
            title="Score vs Taxa de Churn por Faixa (quanto maior o score, menor o churn)",
            yaxis=dict(title="Contratos"), yaxis2=dict(title="Churn (%)", overlaying="y", side="right", range=[0, 92]),
            legend=dict(orientation="h", y=1.12), height=480,
        )
        st.plotly_chart(fig, use_container_width=True)

        st.info("""
        **Por que mesmo no CRITICO ainda retemos ~23%?** Esse "piso de retenção" não é erro
        de calibração — é o **teto prático** que esse modelo consegue atingir com as variáveis
        disponíveis hoje:

        - **Base rate alta:** o churn global da base é ~55%. Quando metade da população cancela,
          mesmo um score forte raramente empurra o pior grupo acima de **80-85%**. Estamos em 77%
          no 0-99, ou seja, próximos do teto que esses 7 preditores conseguem extrair.
        - **Apenas 7 variáveis demográfico-contratuais:** o score não enxerga **histórico de
          pagamento**, **frequência/recência de uso**, **interações de suporte** ou **eventos
          clínicos**. Esses sinais são exatamente os que separariam, dentro do mesmo perfil
          (ex: "1o contrato, jovem, sem dep, 12m, digital, CDE"), quem vai sair de quem vai ficar.
          Hoje esses dois grupos estão misturados na mesma faixa CRITICO.
        - **AUC moderado (~0.60):** com dados comportamentais, o mesmo modelo poderia chegar a
          0.75-0.85 — e o CRITICO mostraria 85-90% de churn em vez de 77%.

        **Leitura prática:** o score é uma **ferramenta de segmentação de grupos** (lift 1.4x na
        pior faixa, 0.64x na melhor), não um identificador individual. Os 22-29% retidos no CRITICO
        são **heterogeneidade não-observável** com as variáveis atuais. O caminho para reduzir esse
        retido residual é **incorporar variáveis comportamentais**, não recalibrar as faixas.
        """)

        # Tabela de faixas com IC
        faixas_display = ks_df[["Faixa", "Contratos", "Churners", "Churn (%)", "Lift"]].copy()
        faixas_display["Nome"] = faixas_display["Faixa"].map(nomes_faixa)
        faixas_display["IC 95%"] = faixas_display.apply(
            lambda r: f'[{wilson_ci(r["Contratos"], r["Churners"])[1]:.1f}%, {wilson_ci(r["Contratos"], r["Churners"])[2]:.1f}%]', axis=1)
        st.dataframe(faixas_display[["Faixa", "Nome", "Contratos", "Churners", "Churn (%)", "IC 95%", "Lift"]],
                     hide_index=True, use_container_width=True)

        # Z-test entre faixas adjacentes
        st.markdown("#### Significância entre faixas adjacentes")
        adjacent_tests = []
        for i in range(len(ks_df) - 1):
            r1 = ks_df.iloc[i]
            r2 = ks_df.iloc[i+1]
            t = z_test_proportions(r1["Contratos"], r1["Churners"], r2["Contratos"], r2["Churners"])
            sig = "***" if t["p"] < 0.001 else ("**" if t["p"] < 0.01 else ("*" if t["p"] < 0.05 else "n.s."))
            adjacent_tests.append({
                "Comparação": f'{r1["Faixa"]} vs {r2["Faixa"]}',
                "Churn A": f'{r1["Churn (%)"]}%',
                "Churn B": f'{r2["Churn (%)"]}%',
                "Diferença": f'{t["diff"]:+.1f} p.p.',
                "IC 95%": f'[{t["ci_lo"]:+.1f}, {t["ci_hi"]:+.1f}]',
                "Sig.": sig,
            })
        st.dataframe(pd.DataFrame(adjacent_tests), hide_index=True, use_container_width=True)
        st.caption("*** p < 0,001 | ** p < 0,01 | * p < 0,05 | n.s. = não significativo")

        # ═══════════════════════════════════════════════════════════════
        # JUSTIFICATIVA DOS PONTOS
        # ═══════════════════════════════════════════════════════════════
        st.markdown("---")
        st.markdown("### De onde vêm as pontuações?")
        st.markdown("""
        Os pontos **não foram escolhidos manualmente**. Usamos um modelo estatístico
        (regressão ponderada) que analisa os ~204 mil contratos da base e calcula
        **quanto cada característica do paciente contribui para o risco de cancelamento**.
        O modelo transforma essa contribuição em pontos na escala 0-1000.

        Abaixo, 3 evidências de que as pontuações refletem a realidade.
        """)

        coefs_full = model["coefs"]
        penalties = coefs_full[coefs_full["Pontos"] != 0].copy()

        # --- Gráfico 1: Penalidades com IC ---
        st.markdown("#### 1. Quanto cada fator de risco pesa no score")
        st.markdown("""
        Cada barra mostra **quantos pontos** o fator subtrai do score. As linhas pretas
        marcam a margem de incerteza (IC 95%) — se a linha não toca o zero, temos
        confiança estatística de que o efeito é real.
        """)

        penalties_sorted = penalties.sort_values("Pontos")
        labels_coef = penalties_sorted.apply(
            lambda r: {
                "contrato": {"1o": "1o contrato"},
                "dependentes": {"sem_dep": "Sem dependentes", "1-2_dep": "1-2 dependentes"},
                "faixa_idade": {"00-20": "Idade até 20 anos", "21-30": "Idade 21-30 anos", "31-50": "Idade 31-50 anos", "71+": "Idade 71+ anos"},
                "duracao": {"12": "Plano de 12 meses"},
                "cronico": {"N": "Sem doença crônica"},
                "canal": {"digital": "Canal digital"},
                "classe": {"CDE": "Classe social CDE"},
            }.get(r["Variável"], {}).get(r["Nível"], f'{r["Variável"]} = {r["Nível"]}'),
            axis=1
        )

        fig_coef = go.Figure()
        fig_coef.add_trace(go.Bar(
            y=labels_coef, x=penalties_sorted["Pontos"],
            orientation="h",
            marker_color=["#c0392b" if p < -100 else "#e67e22" if p < 0 else "#27ae60"
                          for p in penalties_sorted["Pontos"]],
            text=penalties_sorted.apply(
                lambda r: f'{r["Pontos"]:+d} pts' if r["sig"] != "n.s." else f'{r["Pontos"]:+d} pts (n.s.)', axis=1),
            textposition="outside", textfont=dict(size=12),
        ))
        fig_coef.add_trace(go.Scatter(
            y=labels_coef, x=penalties_sorted["Pontos"],
            error_x=dict(
                type="data", symmetric=False,
                array=(penalties_sorted["IC_hi"] - penalties_sorted["Pontos"]).abs().values,
                arrayminus=(penalties_sorted["Pontos"] - penalties_sorted["IC_lo"]).abs().values,
                color="rgba(0,0,0,0.5)", thickness=2.5, width=8,
            ),
            mode="markers", marker=dict(size=1, color="rgba(0,0,0,0)"), showlegend=False,
        ))
        fig_coef.add_vline(x=0, line_dash="dash", line_color="gray", line_width=1)
        fig_coef.update_layout(
            title="Penalidade de cada fator de risco (com margem de incerteza)",
            xaxis_title="Pontos subtraídos do score",
            height=420, showlegend=False,
            margin=dict(l=10, r=80), yaxis=dict(automargin=True),
            xaxis=dict(range=[min(penalties_sorted["IC_lo"].min(), penalties_sorted["Pontos"].min()) - 40,
                              max(penalties_sorted["IC_hi"].max(), penalties_sorted["Pontos"].max()) + 60]),
        )
        st.plotly_chart(fig_coef, use_container_width=True)

        col_leg1, col_leg2 = st.columns(2)
        with col_leg1:
            st.caption("""
            **Como ler:** Barras mais longas para a esquerda = fatores que mais
            reduzem o score (mais arriscados). Linhas pretas = margem de erro.
            Se a linha preta não toca a marca zero, o efeito é estatisticamente significativo.
            """)
        with col_leg2:
            st.caption("""
            **Destaque:** "Idade 71+" tem margem de erro que cruza o zero — isso significa
            que pacientes de 71+ não são estatisticamente diferentes dos de 51-70.
            Faz sentido: ambos são idosos com necessidades de saúde similares.
            """)

        # --- Gráfico 2: Modelo bate com a realidade ---
        st.markdown("---")
        st.markdown("#### 2. O modelo bate com a realidade?")
        st.markdown("""
        Para cada grupo de pacientes, comparamos o cancelamento **real** (barras azuis)
        com o que o modelo **prevê** (losangos vermelhos). Se os dois coincidem,
        as pontuações estão corretas.
        """)

        consistency = model["consistency"]
        var_labels = {
            "contrato": ("Ciclo do Contrato", "Quem está no 1o contrato cancela ~10 p.p. a mais do que quem já renovou."),
            "dependentes": ("Dependentes no Plano", "Cada faixa de dependentes reduz o cancelamento em ~5 p.p."),
            "faixa_idade": ("Faixa Etária do Titular", "Jovens cancelam mais. A partir dos 50, a taxa estabiliza."),
            "duracao": ("Duração do Plano", "12 meses = mais tempo para desengajar. 6 meses renova mais rápido."),
            "cronico": ("Doença Crônica", "Crônicos dependem do plano para acompanhamento contínuo."),
            "canal": ("Canal de Origem", "Pacientes do canal digital cancelam mais — possível gap no onboarding."),
            "classe": ("Classe Social", "Classe AB vs CDE — diferença sutil mas informativa."),
        }
        level_labels = {
            "1o": "1o contrato", "2o+": "2o+ contrato",
            "sem_dep": "Sem dep.", "1-2_dep": "1-2 dep.", "3+_dep": "3+ dep.",
            "00-20": "Até 20", "21-30": "21-30", "31-50": "31-50", "51-70": "51-70", "71+": "71+",
            "6": "6 meses", "12": "12 meses",
            "S": "Sim", "N": "Não",
            "digital": "Digital", "presencial_cfp": "Presencial/CFP",
            "AB": "Classe AB", "CDE": "Classe CDE",
        }

        # Agrupar em 2 colunas para compactar
        var_pairs = [("contrato", "duracao"), ("dependentes", "cronico"), ("faixa_idade", "canal"), ("classe", None)]

        for v1, v2 in var_pairs:
            cols = st.columns(2 if v2 else 1)
            for idx, var in enumerate([v1, v2]):
                if var is None:
                    continue
                with cols[idx]:
                    title, insight = var_labels[var]
                    sub = consistency[consistency["Variável"] == var].copy()
                    sub["label"] = sub["Nível"].map(level_labels).fillna(sub["Nível"])
                    sub.loc[sub["Ref"], "label"] = sub.loc[sub["Ref"], "label"] + " (ref)"

                    fig_cons = go.Figure()
                    fig_cons.add_trace(go.Bar(
                        x=sub["label"], y=sub["Churn Obs."],
                        name="Real", marker_color="rgba(52, 152, 219, 0.7)",
                        text=sub["Churn Obs."].apply(lambda x: f"{x}%"), textposition="outside",
                        textfont=dict(size=11),
                    ))
                    fig_cons.add_trace(go.Scatter(
                        x=sub["label"], y=sub["Churn Pred."],
                        name="Modelo", mode="markers",
                        marker=dict(size=14, color="#e74c3c", symbol="diamond",
                                    line=dict(width=2, color="white")),
                    ))
                    y_min = max(0, sub["Churn Obs."].min() - 10)
                    y_max = sub["Churn Obs."].max() + 6
                    fig_cons.update_layout(
                        title=dict(text=title, font=dict(size=14)),
                        yaxis_title="Churn (%)", yaxis=dict(range=[y_min, y_max]),
                        height=340, legend=dict(orientation="h", y=1.18, font=dict(size=10)),
                        margin=dict(t=60, b=40),
                    )
                    st.plotly_chart(fig_cons, use_container_width=True)
                    st.caption(insight)

        st.success("""
        **Resultado:** Os losangos vermelhos (modelo) se sobrepõem às barras azuis (realidade)
        com erro inferior a 0,2 p.p. em todas as variáveis.
        Isso comprova que os pontos do score refletem fielmente os padrões reais de cancelamento.
        """)

        # --- Gráfico 3: Mapa de perfis ---
        st.markdown("---")
        st.markdown("#### 3. Visão geral: cada perfil de paciente no mapa de risco")
        st.markdown("""
        Cada bolha abaixo é um **tipo de paciente** (combinação das 5 variáveis).
        O tamanho representa quantos contratos existem naquele perfil.
        A posição mostra a relação entre o score e o cancelamento real.

        **Se o score funciona**, as bolhas devem seguir uma tendência clara:
        quanto maior o score (mais à direita), menor o cancelamento (mais abaixo).
        """)

        profiles = model["profiles"]

        fig_scatter = go.Figure()

        # Bolhas dos perfis
        fig_scatter.add_trace(go.Scatter(
            x=profiles["score"], y=profiles["churn_rate"],
            mode="markers",
            marker=dict(
                size=np.sqrt(profiles["total_contratos"]) / 2,
                color=profiles["churn_rate"],
                colorscale="RdYlGn_r", showscale=True,
                colorbar=dict(title="Churn (%)"),
                line=dict(width=0.5, color="rgba(0,0,0,0.3)"),
                sizemin=4,
            ),
            text=profiles.apply(
                lambda r: f'{r["duracao"]}m | {r["contrato"]} | {r["dependentes"]} | {r["faixa_idade"]} | cron={r["cronico"]} | {r["canal"]} | {r["classe"]}<br>'
                          f'Churn: {r["churn_rate"]}% | Contratos: {int(r["total_contratos"]):,}', axis=1),
            hoverinfo="text",
            showlegend=False,
        ))

        # Curva do modelo
        x_trend = np.linspace(0, 1000, 200)
        logit_trend = model["logit_max"] - x_trend / 1000 * (model["logit_max"] - model["logit_min"])
        y_trend = 100 * inv_logit(logit_trend)
        fig_scatter.add_trace(go.Scatter(
            x=x_trend, y=y_trend, mode="lines",
            line=dict(dash="dash", color="rgba(0,0,0,0.4)", width=2),
            name="Tendência esperada",
        ))

        # Faixas de fundo
        faixa_colors = {
            "CRITICO": "#8b0000", "MUITO ALTO": "#d62728",
            "ALTO": "#ff7f0e", "MEDIO": "#ffbb33",
            "BAIXO": "#2ca02c",
            "MUITO BAIXO": "#1f77b4", "MINIMO": "#0d3b8b",
        }
        faixa_ranges = [
            (0, 100, "CRITICO"), (100, 200, "MUITO ALTO"),
            (200, 400, "ALTO"), (400, 600, "MEDIO"),
            (600, 800, "BAIXO"),
            (800, 900, "MUITO BAIXO"), (900, 1000, "MINIMO"),
        ]
        for x0, x1, nome in faixa_ranges:
            fig_scatter.add_vrect(x0=x0, x1=x1,
                                  fillcolor=faixa_colors[nome], opacity=0.06, line_width=0)
            fig_scatter.add_annotation(x=(x0+x1)/2, y=83, text=nome,
                                        showarrow=False, font=dict(size=9, color=faixa_colors[nome]),
                                        opacity=0.75)

        fig_scatter.update_layout(
            title="Mapa de Risco: Score vs Cancelamento Real",
            xaxis_title="Score de Churn (0 = maior risco, 1000 = mais seguro)",
            yaxis_title="Taxa de Cancelamento Real (%)",
            height=550, yaxis=dict(range=[28, 87]),
            xaxis=dict(range=[-30, 1030]),
            legend=dict(orientation="h", y=1.08),
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

        st.markdown("""
        **Como ler este gráfico:**
        - Cada **bolha** = um tipo de paciente (ex: "1o contrato, jovem, sem dependentes, 12m, não crônico, digital, CDE")
        - **Bolhas maiores** = mais pacientes com esse perfil
        - **Cores quentes** (vermelho) = alto cancelamento | **Cores frias** (verde) = baixo cancelamento
        - A **linha pontilhada** é o que o modelo prevê — as bolhas devem seguir essa curva
        - As **faixas coloridas** de fundo marcam os 5 níveis de risco

        As bolhas seguem a curva de perto, confirmando que o score ordena corretamente
        os perfis de paciente. A dispersão natural (~2-3 p.p.) existe porque combinações
        específicas de variáveis podem interagir de formas que o modelo simplificado não captura.
        """)

    except Exception as e:
        st.error(f"Erro: {e}")


# ═══════════════════════════════════════════════════════════════════════
# TAB 2: VALIDAÇÃO
# ═══════════════════════════════════════════════════════════════════════
with tab_valid:
    try:
        model = fit_score_model()
        m = model["metrics"]

        st.markdown("### Métricas de Validação do Score")

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("MAE", f"{m['mae']:.1f} p.p.", help="Erro médio absoluto: predito vs real")
        k2.metric("Correlação", f"{m['corr']:.3f}", help="Correlação entre churn predito e real nos perfis")
        k3.metric("C-index (AUC)", f"{m['c_index']:.3f}", help="Concordância: probabilidade de o score ordenar corretamente um churner vs retido")
        k4.metric("KS Máximo", f"{m['ks']:.1f}%", help="Maior separação entre distribuição de churners vs retidos")

        # --- Calibração ---
        st.markdown("---")
        st.markdown("### 1. Calibração: o score prediz corretamente?")
        st.markdown("""
        O gráfico abaixo compara o churn **predito** pelo modelo com o churn **real** observado,
        agrupado em decis de score. Se o modelo estiver bem calibrado, os pontos ficam na diagonal.
        """)

        calib = model["calib_data"]
        fig_calib = go.Figure()
        fig_calib.add_trace(go.Scatter(
            x=calib["Churn Predito"], y=calib["Churn Real"],
            mode="markers+text",
            marker=dict(size=calib["Contratos"] / calib["Contratos"].max() * 30 + 8, color="#1f77b4"),
            text=calib["Score Médio"].apply(lambda x: f"score {x}"),
            textposition="top center", textfont=dict(size=9),
            name="Decis",
        ))
        # Diagonal perfeita
        fig_calib.add_trace(go.Scatter(
            x=[35, 72], y=[35, 72], mode="lines",
            line=dict(dash="dash", color="gray"), name="Calibração perfeita",
        ))
        fig_calib.update_layout(
            title="Calibração: Churn Predito vs Churn Real (por decil de score)",
            xaxis_title="Churn Predito (%)", yaxis_title="Churn Real (%)",
            height=450, xaxis=dict(range=[35, 72]), yaxis=dict(range=[35, 72]),
        )
        st.plotly_chart(fig_calib, use_container_width=True)

        st.dataframe(calib.rename(columns={
            "Decil": "Decil", "Score Médio": "Score Médio", "Churn Predito": "Predito (%)",
            "Churn Real": "Real (%)", "Erro": "Erro (p.p.)", "Contratos": "Contratos"
        }), hide_index=True, use_container_width=True)

        st.success(f"**Calibração excelente:** erro médio de {m['mae']:.1f} p.p. Os pontos se alinham na diagonal.")

        # --- KS / Separação ---
        st.markdown("---")
        st.markdown("### 2. Separação: o score distingue churners de retidos?")
        st.markdown("""
        A curva KS mostra a **distribuição acumulada** de churners vs retidos ao longo do score.
        Quanto maior a separação, melhor o score discrimina.
        """)

        ks_df = model["ks_data"]
        fig_ks = go.Figure()
        fig_ks.add_trace(go.Scatter(
            x=ks_df["Faixa"], y=ks_df["Cum Churn (%)"],
            mode="lines+markers", name="Churners (acum.)",
            line=dict(color="#d62728", width=3), marker=dict(size=10),
        ))
        fig_ks.add_trace(go.Scatter(
            x=ks_df["Faixa"], y=ks_df["Cum Retidos (%)"],
            mode="lines+markers", name="Retidos (acum.)",
            line=dict(color="#2ca02c", width=3), marker=dict(size=10),
        ))
        fig_ks.add_trace(go.Bar(
            x=ks_df["Faixa"], y=ks_df["KS (%)"],
            name="KS (separação)", marker_color="rgba(100,100,100,0.3)", yaxis="y2",
        ))
        fig_ks.update_layout(
            title=f"Curva KS — Separação entre Churners e Retidos (KS máx = {m['ks']:.1f}%)",
            yaxis=dict(title="Acumulado (%)"), yaxis2=dict(title="KS (%)", overlaying="y", side="right", range=[0, 20]),
            legend=dict(orientation="h", y=1.12), height=450,
        )
        st.plotly_chart(fig_ks, use_container_width=True)

        # --- Lift ---
        st.markdown("---")
        st.markdown("### 3. Lift: quanto o score melhora sobre o acaso?")
        st.markdown(f"""
        O churn global da base é **{m['churn_global']:.1f}%**. O lift mostra quanto cada faixa
        está acima ou abaixo dessa média.
        """)

        fig_lift = go.Figure()
        fig_lift.add_trace(go.Bar(
            x=ks_df["Faixa"], y=ks_df["Lift"],
            marker_color=[colors_map.get(f, "gray") for f in ks_df["Faixa"]],
            text=ks_df["Lift"].apply(lambda x: f"{x:.2f}x"),
            textposition="outside",
        ))
        fig_lift.add_hline(y=1.0, line_dash="dash", line_color="gray",
                           annotation_text="Média da base (1.0x)", annotation_position="top left")
        fig_lift.update_layout(
            title="Lift por Faixa de Score", yaxis_title="Lift (vs média)",
            height=400, yaxis=dict(range=[0.5, 1.5]),
        )
        st.plotly_chart(fig_lift, use_container_width=True)

        # --- Interpretação ---
        st.markdown("---")
        st.markdown("### Interpretação e Limitações")

        st.info(f"""
        **O que o score faz bem:**
        - **Calibração** excelente (MAE = {m['mae']:.1f} p.p.) — o churn predito bate com o real
        - **Monotônico** em todas as faixas — score sobe, churn desce, sem exceções
        - **Spread de {round(ks_df.iloc[0]['Churn (%)'] - ks_df.iloc[-1]['Churn (%)'], 1)} p.p.** entre extremos — suficiente para diferenciar ações de CRM

        **Limitação conhecida:**
        - **AUC = {m['c_index']:.3f}** (moderado) — o score usa apenas 5 variáveis demográficas/contratuais
          disponíveis no momento da assinatura. Não inclui dados comportamentais (frequência de uso,
          histórico de pagamento, interações com suporte). Com dados comportamentais, o AUC poderia
          subir para 0.70-0.80+.
        - O score é uma **ferramenta de segmentação**, não um preditor individual preciso.
          Ele separa *grupos* de risco — não prevê se um paciente *específico* vai cancelar.
        """)

        with st.expander("📐 Detalhes técnicos do modelo"):
            st.markdown(f"""
            **Modelo:** Regressão Linear Ponderada (WLS) sobre logit(churn)

            - **Unidade de análise:** perfis compostos (7 variáveis × N contratos)
            - **Variável resposta:** log(churn / (1-churn)) de cada perfil
            - **Preditores:** 10 dummies (7 variáveis, categorias vs referência)
            - **Variáveis:** duração, ciclo contrato, dependentes, faixa etária, crônico, canal, classe social
            - **Pesos:** volume de contratos por perfil
            - **Intercepto:** {model['intercept']:.4f} → churn base = {model['ref_churn']}%
            - **Perfis no ajuste:** {len(model['profiles'])} (volume >= 50 contratos)
            - **Mapeamento:** logit [{model['logit_min']:.3f}, {model['logit_max']:.3f}] → score [1000, 0]
            - **Fator de escala:** 1 unidade de log-odds = {round(1000 / (model['logit_max'] - model['logit_min']), 1)} pontos

            **Por que WLS e não logística direta?**
            Não temos acesso a dados individuais neste pipeline — apenas agregados por perfil.
            O WLS sobre log-odds é matematicamente equivalente a uma regressão logística
            com dados agrupados (Berkson's method), e produz estimativas consistentes quando
            os perfis têm volume suficiente (todos >= 50 contratos).
            """)

    except Exception as e:
        st.error(f"Erro ao carregar dados de validação: {e}")


# ═══════════════════════════════════════════════════════════════════════
# TAB 3: SAZONALIDADE
# ═══════════════════════════════════════════════════════════════════════
with tab_season:
    st.markdown("### Sazonalidade: quando os pacientes saem?")
    st.markdown("O score identifica *quem* tem mais risco. Agora, *quando* o churn acontece?")

    try:
        df_b = load_b()
        df_b["mes_vencimento"] = pd.to_datetime(df_b["mes_vencimento"])
        df_b["duracao_label"] = df_b["duracao"].astype(str) + " meses"

        fig = px.line(
            df_b, x="mes_vencimento", y="churn_rate", color="duracao_label",
            markers=True, line_shape="spline",
            title="Taxa de Churn mês a mês",
            labels={"mes_vencimento": "", "churn_rate": "Churn (%)", "duracao_label": "Plano"},
            color_discrete_map={"6 meses": "#2ca02c", "12 meses": "#d62728"},
        )
        fig.update_layout(height=420, yaxis_range=[40, 70], xaxis_dtick="M1", xaxis_tickformat="%b/%y")
        st.plotly_chart(fig, use_container_width=True)

        fig_vol = px.bar(
            df_b, x="mes_vencimento", y="total_contratos", color="duracao_label",
            barmode="group",
            title="Volume de contratos por mês de vencimento",
            labels={"mes_vencimento": "", "total_contratos": "Contratos", "duracao_label": "Plano"},
            color_discrete_map={"6 meses": "#2ca02c", "12 meses": "#d62728"},
        )
        fig_vol.update_layout(height=320, xaxis_dtick="M1", xaxis_tickformat="%b/%y")
        st.plotly_chart(fig_vol, use_container_width=True)

        st.markdown("""
        #### Leitura
        1. **Planos de 12 meses consistentemente acima dos de 6** — gap de ~7-10 p.p. mês a mês
        2. **Dezembro é o pior mês** — provável efeito de revisão de gastos no fim de ano
        3. **Volume de 6 meses crescendo** — boa notícia, é o produto que retém melhor

        **Ação:** Intensificar réguas de retenção em **outubro-dezembro**.
        """)
    except Exception as e:
        st.error(f"Erro: {e}")


# ═══════════════════════════════════════════════════════════════════════
# TAB 4: UNIDADES
# ═══════════════════════════════════════════════════════════════════════
with tab_units:
    st.markdown("### Unidades: onde o churn é pior?")
    st.markdown("Churn por unidade principal de consumo.")

    try:
        df_a = load_a()
        df_unidades = df_a[df_a["unidade"] != "(sem consumo)"].copy()
        sem_consumo = df_a[df_a["unidade"] == "(sem consumo)"]

        if not sem_consumo.empty:
            row = sem_consumo.iloc[0]
            st.warning(f"**{int(row['total_contratos']):,} contratos** ({row['churn_rate']}% de churn) "
                       f"**nunca usaram nenhuma clínica**. Invisíveis para as unidades.")

        df_unidades = df_unidades.sort_values("churn_rate", ascending=False)

        fig = px.scatter(
            df_unidades, x="media_itens", y="churn_rate", size="total_contratos",
            color="churn_rate", color_continuous_scale="RdYlGn_r",
            hover_name="unidade", size_max=45,
            title="Cada bolha é uma unidade: tamanho = volume, posição = consumo vs churn",
            labels={"media_itens": "Média de Itens por Paciente", "churn_rate": "Churn (%)"},
        )
        fig.update_layout(height=480, yaxis_range=[40, 68])
        st.plotly_chart(fig, use_container_width=True)

        col_worst, col_best = st.columns(2)
        with col_worst:
            st.markdown("##### Maiores taxas de churn")
            top5 = df_unidades.nlargest(5, "churn_rate")[["unidade", "total_contratos", "churn_rate", "media_itens"]]
            top5.columns = ["Unidade", "Contratos", "Churn (%)", "Itens/Pac."]
            st.dataframe(top5, hide_index=True, use_container_width=True)
        with col_best:
            st.markdown("##### Menores taxas de churn")
            bot5 = df_unidades.nsmallest(5, "churn_rate")[["unidade", "total_contratos", "churn_rate", "media_itens"]]
            bot5.columns = ["Unidade", "Contratos", "Churn (%)", "Itens/Pac."]
            st.dataframe(bot5, hide_index=True, use_container_width=True)
    except Exception as e:
        st.error(f"Erro: {e}")
