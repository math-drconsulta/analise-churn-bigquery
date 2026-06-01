"""Lógica de score, faixas e validação do app comitê.

Estrutura modular: `fit_wls` aceita qualquer conjunto de features/refs, então
adicionar variáveis ao perfil composto no futuro não exige reescrever a página.

Estratégia:
- Score WLS sobre logit(churn) — equivalente a regressão logística com dados agrupados
  (Berkson's method), apropriado quando trabalhamos com perfis (não dados individuais).
- 1 modelo independente por duração (6m e 12m), refletindo a tese da análise paralela.
- Score 0-1000 (alto = seguro), 5 faixas em quintis ponderados por volume.
- Métricas de validação: MAE, correlação, c-index, KS, calibração, lift.

Funções antigas (`assign_buckets_within`, `score_cruzamento`, etc.) mantidas por
compatibilidade enquanto Páginas 4-5 (Hábitos, Ações) ainda as consomem. Serão
removidas quando essas páginas migrarem para o novo score.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTES — 5 FAIXAS DO SCORE COMITÊ
# ═══════════════════════════════════════════════════════════════════════════
BAND_5_ORDER = ["CRITICO", "ALTO", "MEDIO", "BAIXO", "SEGURO"]
BAND_5_LABELS = {
    "CRITICO": "🔴 Crítico",
    "ALTO": "🟠 Alto",
    "MEDIO": "🟡 Médio",
    "BAIXO": "🟢 Baixo",
    "SEGURO": "🔵 Seguro",
}
BAND_5_COLORS = {
    "CRITICO": "#8b0000",
    "ALTO": "#d62728",
    "MEDIO": "#f9a825",
    "BAIXO": "#2ca02c",
    "SEGURO": "#0d3b8b",
}

# Configuração padrão do score comitê — 4 variáveis core.
# Para adicionar mais variáveis (ex: canal, classe), passe explicitamente
# `features` e `refs` em `fit_wls(...)`.
WLS_FEATURES_DEFAULT = ["ciclo", "faixa_etaria", "cronico", "composicao_titular"]
WLS_REFS_DEFAULT = {
    "ciclo": "2o+",                     # menor churn observado (54,0% / 44,8%) — rank 1
    "faixa_etaria": "71+",              # menor churn observado (54,6% / 45,5%) — rank 1
    "cronico": "S",                     # menor churn observado (53,6% / 46,0%) — rank 1
    "composicao_titular": "com_idoso",  # menor churn observado (53,7% / 45,6%) — rank 1
}


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS NUMÉRICOS
# ═══════════════════════════════════════════════════════════════════════════
def logit(p):
    p = np.clip(p, 0.001, 0.999)
    return np.log(p / (1 - p))


def inv_logit(x):
    return 1 / (1 + np.exp(-x))


def wilson_ci(n: int, x: int, alpha: float = 0.05) -> tuple[float, float, float]:
    """IC de Wilson para proporção binomial. Retorna (p%, lo%, hi%)."""
    if n == 0:
        return 0.0, 0.0, 0.0
    p = x / n
    z = stats.norm.ppf(1 - alpha / 2)
    denom = 1 + z ** 2 / n
    center = (p + z ** 2 / (2 * n)) / denom
    margin = z * np.sqrt(p * (1 - p) / n + z ** 2 / (4 * n ** 2)) / denom
    return p * 100, max(0, (center - margin) * 100), min(100, (center + margin) * 100)


def z_test_proportions(n1: int, x1: int, n2: int, x2: int) -> dict:
    """Z-test bicaudal para diferença de proporções (em p.p.)."""
    if n1 == 0 or n2 == 0:
        return {"diff": 0, "ci_lo": 0, "ci_hi": 0, "p": 1.0, "z": 0, "p1": 0, "p2": 0}
    p1, p2 = x1 / n1, x2 / n2
    diff = p1 - p2
    p_pool = (x1 + x2) / (n1 + n2)
    se = np.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2)) if p_pool > 0 else 0
    z = diff / se if se > 0 else 0
    pval = 2 * (1 - stats.norm.cdf(abs(z)))
    return {
        "diff": diff * 100, "ci_lo": (diff - 1.96 * se) * 100, "ci_hi": (diff + 1.96 * se) * 100,
        "z": z, "p": pval, "p1": p1 * 100, "p2": p2 * 100,
    }


def sig_stars(p: float) -> str:
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return "n.s."


# ═══════════════════════════════════════════════════════════════════════════
# WLS — SCORE POR DURAÇÃO
# ═══════════════════════════════════════════════════════════════════════════
def fit_wls(
    df_dur: pd.DataFrame,
    features: list[str] | None = None,
    refs: dict[str, str] | None = None,
) -> dict:
    """Ajusta WLS sobre logit(churn) usando perfis compostos de UMA duração.

    Espera colunas: cada feature em `features`, `total_contratos`, `churners`, `churn_rate`.

    Retorna dict com beta, SE, predições, score (0-1000), tabela de coefs e métricas.
    """
    if features is None:
        features = WLS_FEATURES_DEFAULT
    if refs is None:
        refs = WLS_REFS_DEFAULT

    a = df_dur.copy().reset_index(drop=True)
    a["p_churn"] = a["churners"] / a["total_contratos"]
    a["logit_churn"] = logit(a["p_churn"])

    # Monta matriz de design: para cada feature, 1 dummy por nível != referência
    feat_arrays, feat_names = [], []
    for var in features:
        ref = refs.get(var)
        if ref is None:
            raise ValueError(f"Faltando referência para '{var}' em refs={refs}")
        for level in sorted(a[var].astype(str).unique()):
            if level == ref:
                continue
            feat_arrays.append((a[var].astype(str) == level).astype(float).values)
            feat_names.append(f"{var}={level}")

    if len(feat_arrays) == 0:
        raise ValueError("Nenhum nível além da referência — modelo não identificado.")

    X = np.column_stack([np.ones(len(a))] + feat_arrays)
    y = a["logit_churn"].values
    w = a["total_contratos"].values.astype(float)

    # WLS via equações normais ponderadas
    XtWX = X.T @ (w[:, None] * X)
    XtWy = X.T @ (w * y)
    beta = np.linalg.solve(XtWX, XtWy)
    n_obs, n_params = X.shape

    y_pred = X @ beta
    residuals = y - y_pred
    sigma2 = (w * residuals ** 2).sum() / max(n_obs - n_params, 1)
    cov_beta = sigma2 * np.linalg.inv(XtWX)
    se_beta = np.sqrt(np.diag(cov_beta))

    a["logit_pred"] = y_pred
    a["p_pred"] = inv_logit(y_pred)
    a["churn_pred"] = np.round(100 * a["p_pred"], 1)
    a["erro"] = a["churn_pred"] - a["churn_rate"]

    # Score 0-1000: maior = mais seguro
    lmin, lmax = float(a["logit_pred"].min()), float(a["logit_pred"].max())
    scale = 1000 / (lmax - lmin) if lmax > lmin else 1
    a["score"] = np.round(1000 * (1 - (a["logit_pred"] - lmin) / (lmax - lmin))).astype(int)

    # Tabela de coeficientes com IC + significância
    coefs_rows = []
    coefs_rows.append({
        "variavel": "(intercepto)", "nivel": "ref",
        "log_odds": float(beta[0]), "se": float(se_beta[0]),
        "pontos": 0, "ic_lo_pts": 0, "ic_hi_pts": 0,
        "efeito_pp": 0.0,
        "t": float(beta[0] / se_beta[0]) if se_beta[0] > 0 else 0,
        "p": 0.0, "sig": "",
    })
    base_logit = float(beta[0])
    for i, name in enumerate(feat_names):
        coef = float(beta[i + 1])
        se = float(se_beta[i + 1])
        t_stat = coef / se if se > 0 else 0
        p_val = 2 * (1 - stats.t.cdf(abs(t_stat), df=max(n_obs - n_params, 1)))
        # Pontos no score (negativo porque score alto = seguro; coef > 0 em logit_churn = mais churn = score MENOR)
        pts = -round(coef * scale)
        ic_lo = -round((coef + 1.96 * se) * scale)
        ic_hi = -round((coef - 1.96 * se) * scale)
        delta_pp = 100 * (inv_logit(base_logit + coef) - inv_logit(base_logit))
        var, lvl = name.split("=", 1)
        coefs_rows.append({
            "variavel": var, "nivel": lvl,
            "log_odds": coef, "se": se,
            "pontos": pts, "ic_lo_pts": ic_lo, "ic_hi_pts": ic_hi,
            "efeito_pp": round(delta_pp, 1),
            "t": t_stat, "p": p_val, "sig": sig_stars(p_val),
        })

    coefs_df = pd.DataFrame(coefs_rows)

    # Métricas básicas
    mae = float((a["erro"].abs() * w).sum() / w.sum())
    corr = float(a["churn_rate"].corr(a["churn_pred"]))

    # Concordância (c-index aproximado nos perfis, ponderado por churners × retidos)
    scores = a["score"].values
    totais = a["total_contratos"].values
    churners = a["churners"].values
    retidos = totais - churners
    concordant = discordant = 0.0
    for i in range(len(a)):
        for j in range(len(a)):
            if scores[i] < scores[j]:  # perfil i é mais arriscado (score menor)
                concordant += churners[i] * retidos[j]
                discordant += churners[j] * retidos[i]
    c_index = concordant / (concordant + discordant) if (concordant + discordant) > 0 else 0.5

    base_churn_pp = round(100 * inv_logit(base_logit), 1)

    return {
        "profiles": a,
        "coefs": coefs_df,
        "feat_names": feat_names,
        "beta": beta,
        "se_beta": se_beta,
        "logit_min": lmin,
        "logit_max": lmax,
        "scale": scale,
        "intercept_logit": base_logit,
        "ref_churn_pp": base_churn_pp,
        "metrics": {
            "mae": mae,
            "corr": corr,
            "c_index": float(c_index),
            "gini": float(2 * c_index - 1),
            "n_perfis": len(a),
            "n_contratos": int(w.sum()),
            "n_churners": int(churners.sum()),
            "churn_global": float(100 * churners.sum() / w.sum()),
        },
    }


def fit_wls_per_duracao(
    df_crz: pd.DataFrame,
    features: list[str] | None = None,
    refs: dict[str, str] | None = None,
) -> dict[str, dict]:
    """Aplica `fit_wls` independentemente a cada duração. Retorna {duracao: model_dict}."""
    return {
        str(dur): fit_wls(sub, features=features, refs=refs)
        for dur, sub in df_crz.groupby("duracao")
    }


def _predict_from_coefs(
    df_target: pd.DataFrame,
    model_source: dict,
    features: list[str],
    refs: dict[str, str],
) -> pd.DataFrame:
    """Aplica os coefs de `model_source` (treinado em outra janela) aos perfis de `df_target`.

    Útil pra OOS: prediz churn no test usando os pesos do train.
    Perfis em `df_target` cuja combinação de níveis não existia no train herdam apenas
    os efeitos de cada nível individualmente — combinações nunca vistas saem do logit base
    + soma das dummies isoladas.
    """
    out = df_target.copy().reset_index(drop=True)
    feat_names = model_source["feat_names"]
    beta = model_source["beta"]

    logit_pred = np.full(len(out), float(beta[0]))  # intercepto
    for i, name in enumerate(feat_names):
        var, lvl = name.split("=", 1)
        mask = (out[var].astype(str) == lvl).values
        logit_pred = logit_pred + mask * float(beta[i + 1])
    out["logit_pred"] = logit_pred
    out["p_pred"] = inv_logit(logit_pred)
    out["churn_pred"] = np.round(100 * out["p_pred"], 1)
    out["p_churn"] = out["churners"] / out["total_contratos"]
    out["erro"] = out["churn_pred"] - out["churn_rate"]
    return out


def validate_oos(
    df_train: pd.DataFrame,
    df_test: pd.DataFrame,
    features: list[str] | None = None,
    refs: dict[str, str] | None = None,
) -> dict[str, dict]:
    """Valida o WLS out-of-sample: treina em `df_train`, prediz em `df_test`.

    Retorna por duração: métricas in-sample (train), out-of-sample (test) e
    estabilidade dos coeficientes (refit em test pra comparar magnitudes).

    Keys retornadas por duração:
      - metrics_train, metrics_test (mae, corr, c_index sobre os perfis de cada janela)
      - coef_stability (DataFrame com coef_train, coef_test, delta, |delta|/SE_train)
      - n_perfis_train, n_perfis_test, n_perfis_only_test (cobertura)
    """
    if features is None:
        features = WLS_FEATURES_DEFAULT
    if refs is None:
        refs = WLS_REFS_DEFAULT

    results = {}
    train_models = fit_wls_per_duracao(df_train, features=features, refs=refs)
    test_models = fit_wls_per_duracao(df_test, features=features, refs=refs)

    for dur, m_train in train_models.items():
        sub_test = df_test[df_test["duracao"].astype(str) == str(dur)].copy()
        if sub_test.empty:
            continue
        pred = _predict_from_coefs(sub_test, m_train, features, refs)

        # Métricas OOS (no test, com predições do train)
        w = pred["total_contratos"].values.astype(float)
        mae_test = float((pred["erro"].abs() * w).sum() / w.sum())
        corr_test = float(pred["churn_rate"].corr(pred["churn_pred"]))

        # C-index OOS via score (predito) vs churners/retidos do test
        scale = m_train["scale"]
        lmin = m_train["logit_min"]
        lmax = m_train["logit_max"]
        pred["score"] = np.clip(
            np.round(1000 * (1 - (pred["logit_pred"] - lmin) / (lmax - lmin))),
            -1000, 2000,
        ).astype(int)
        scores = pred["score"].values
        totais = pred["total_contratos"].values
        churners = pred["churners"].values
        retidos = totais - churners
        concordant = discordant = 0.0
        for i in range(len(pred)):
            for j in range(len(pred)):
                if scores[i] < scores[j]:
                    concordant += churners[i] * retidos[j]
                    discordant += churners[j] * retidos[i]
        c_oos = (
            concordant / (concordant + discordant)
            if (concordant + discordant) > 0 else 0.5
        )

        # Estabilidade dos coefs: train vs test (refit)
        m_test = test_models.get(str(dur))
        if m_test is None:
            coef_stab = pd.DataFrame()
        else:
            c_train = m_train["coefs"][["variavel", "nivel", "log_odds", "se", "pontos", "sig"]].rename(
                columns={"log_odds": "log_odds_train", "se": "se_train",
                         "pontos": "pts_train", "sig": "sig_train"}
            )
            c_test = m_test["coefs"][["variavel", "nivel", "log_odds", "se", "pontos", "sig"]].rename(
                columns={"log_odds": "log_odds_test", "se": "se_test",
                         "pontos": "pts_test", "sig": "sig_test"}
            )
            coef_stab = c_train.merge(c_test, on=["variavel", "nivel"], how="outer")
            coef_stab["delta_log_odds"] = (
                coef_stab["log_odds_test"] - coef_stab["log_odds_train"]
            ).round(3)
            coef_stab["delta_pts"] = (
                coef_stab["pts_test"] - coef_stab["pts_train"]
            )
            # Z-score do delta usando SE combinado (raiz quadrada da soma dos SE²)
            se_pool = np.sqrt(coef_stab["se_train"] ** 2 + coef_stab["se_test"] ** 2)
            coef_stab["z_delta"] = (coef_stab["delta_log_odds"] / se_pool).round(2)
            coef_stab["delta_sig"] = coef_stab["z_delta"].abs().apply(
                lambda z: "***" if z >= 3.29 else "**" if z >= 2.58
                else "*" if z >= 1.96 else "n.s."
            )

        results[str(dur)] = {
            "metrics_train": m_train["metrics"],
            "metrics_test": {
                "mae": mae_test,
                "corr": corr_test,
                "c_index": float(c_oos),
                "gini": float(2 * c_oos - 1),
                "n_perfis": len(pred),
                "n_contratos": int(w.sum()),
                "n_churners": int(churners.sum()),
                "churn_global": float(100 * churners.sum() / w.sum()),
            },
            "coef_stability": coef_stab,
            "pred_test": pred,
        }

    return results


# ═══════════════════════════════════════════════════════════════════════════
# FAIXAS — 3 estratégias de corte do score em 5 níveis
# ═══════════════════════════════════════════════════════════════════════════
BANDS_MODE_SYMMETRIC = "quintis_simetricos"     # 20/20/20/20/20
BANDS_MODE_ASYMMETRIC = "quintis_assimetricos"  # 10/15/25/25/25 (default — maior spread em 12m)
BANDS_MODE_FIXED = "cortes_fixos"               # 0-200/200-400/400-600/600-800/800+

BANDS_MODE_LABELS = {
    BANDS_MODE_SYMMETRIC: "Quintis ponderados (20/20/20/20/20)",
    BANDS_MODE_ASYMMETRIC: "Quintis assimétricos (10/15/25/25/25)",
    BANDS_MODE_FIXED: "Cortes fixos por score (0-200/.../800+)",
}


def assign_bands_5(profiles: pd.DataFrame, score_col: str = "score",
                   weight_col: str = "total_contratos") -> pd.DataFrame:
    """Quintis ponderados (cada faixa ~20% do volume). Default histórico."""
    g = profiles.copy().sort_values(score_col).reset_index(drop=True)
    w = g[weight_col].to_numpy().astype(float)
    cum = np.cumsum(w) / w.sum()
    bands = pd.cut(
        cum, bins=[-0.001, 0.2, 0.4, 0.6, 0.8, 1.001],
        labels=BAND_5_ORDER, include_lowest=True,
    )
    g["band"] = bands.astype(str)
    g["band"] = pd.Categorical(g["band"], categories=BAND_5_ORDER, ordered=True)
    return g


def assign_bands_asymmetric(profiles: pd.DataFrame, score_col: str = "score",
                            weight_col: str = "total_contratos") -> pd.DataFrame:
    """Quintis assimétricos: CRITICO 10%, ALTO 15%, MEDIO 25%, BAIXO 25%, SEGURO 25%.

    Concentra perfis mais arriscados no CRITICO, puxando o spread dos extremos.
    """
    g = profiles.copy().sort_values(score_col).reset_index(drop=True)
    w = g[weight_col].to_numpy().astype(float)
    cum = np.cumsum(w) / w.sum()
    bands = pd.cut(
        cum, bins=[-0.001, 0.10, 0.25, 0.50, 0.75, 1.001],
        labels=BAND_5_ORDER, include_lowest=True,
    )
    g["band"] = bands.astype(str)
    g["band"] = pd.Categorical(g["band"], categories=BAND_5_ORDER, ordered=True)
    return g


def assign_bands_fixed(profiles: pd.DataFrame, score_col: str = "score",
                       weight_col: str = "total_contratos") -> pd.DataFrame:
    """Cortes fixos por valor de score: <200=CRITICO, 200-399=ALTO, 400-599=MEDIO,
    600-799=BAIXO, ≥800=SEGURO. Faixas podem ficar bem desiguais em volume."""
    g = profiles.copy()

    def to_band(s: float) -> str:
        if s < 200:
            return "CRITICO"
        if s < 400:
            return "ALTO"
        if s < 600:
            return "MEDIO"
        if s < 800:
            return "BAIXO"
        return "SEGURO"

    g["band"] = g[score_col].apply(to_band)
    g["band"] = pd.Categorical(g["band"], categories=BAND_5_ORDER, ordered=True)
    return g


def assign_bands(profiles: pd.DataFrame, mode: str = BANDS_MODE_SYMMETRIC,
                 score_col: str = "score",
                 weight_col: str = "total_contratos") -> pd.DataFrame:
    """Dispatcher de estratégias de cortes. Use `mode` para escolher."""
    if mode == BANDS_MODE_ASYMMETRIC:
        return assign_bands_asymmetric(profiles, score_col, weight_col)
    if mode == BANDS_MODE_FIXED:
        return assign_bands_fixed(profiles, score_col, weight_col)
    return assign_bands_5(profiles, score_col, weight_col)


def band_summary(scored_with_bands: pd.DataFrame) -> pd.DataFrame:
    """Para 1 duração já com 'band': N, churners, churn_rate, % volume, score range, IC Wilson."""
    agg = scored_with_bands.groupby("band", as_index=False, observed=True).agg(
        total_contratos=("total_contratos", "sum"),
        churners=("churners", "sum"),
        n_perfis=("score", "count"),
        score_min=("score", "min"),
        score_max=("score", "max"),
    )
    agg["churn_rate"] = round(100.0 * agg["churners"] / agg["total_contratos"], 1)
    tot = agg["total_contratos"].sum()
    agg["pct_duracao"] = round(100.0 * agg["total_contratos"] / tot, 1) if tot else 0
    agg["lift"] = round(agg["churn_rate"] / (100.0 * agg["churners"].sum() / tot), 2) if tot else 1.0

    wlo, whi = [], []
    for _, r in agg.iterrows():
        _, lo, hi = wilson_ci(int(r["total_contratos"]), int(r["churners"]))
        wlo.append(round(lo, 1))
        whi.append(round(hi, 1))
    agg["ic_lo"] = wlo
    agg["ic_hi"] = whi
    agg["band"] = pd.Categorical(agg["band"], categories=BAND_5_ORDER, ordered=True)
    return agg.sort_values("band").reset_index(drop=True)


def ks_data(band_summary_df: pd.DataFrame) -> pd.DataFrame:
    """Cumulativo de churners e retidos por faixa (do CRITICO ao SEGURO) → KS."""
    df = band_summary_df.copy().sort_values("band").reset_index(drop=True)
    df["retidos"] = df["total_contratos"] - df["churners"]
    total_ch = df["churners"].sum()
    total_ret = df["retidos"].sum()
    df["cum_churn_pct"] = round(100.0 * df["churners"].cumsum() / total_ch, 1) if total_ch else 0
    df["cum_ret_pct"] = round(100.0 * df["retidos"].cumsum() / total_ret, 1) if total_ret else 0
    df["ks_pp"] = (df["cum_churn_pct"] - df["cum_ret_pct"]).abs().round(1)
    return df


# ═══════════════════════════════════════════════════════════════════════════
# CAUSALIDADE — E-VALUE E SCORE 2.0 (WLS COM TRATAMENTO)
# ═══════════════════════════════════════════════════════════════════════════
def e_value(rr: float) -> float:
    """E-value (VanderWeele & Ding, 2017) para um Risk Ratio observado.

    Interpretação: força mínima de associação (em escala RR) que um confounder não
    medido precisaria ter com TANTO o tratamento QUANTO o desfecho para explicar
    completamente o efeito observado.

    - E-value > 2: relativamente robusto a confounders não medidos
    - E-value 1.5-2: moderado, vale sensibilidade
    - E-value < 1.5: sensível, efeito pode ser confounding

    `rr` pode ser <1 (protetor) ou >1 (deletério). A fórmula é invariante.
    """
    if rr <= 0 or np.isnan(rr):
        return float("nan")
    rr_eff = max(rr, 1.0 / rr)
    return float(rr_eff + (rr_eff * (rr_eff - 1)) ** 0.5)


def e_value_label(ev: float) -> str:
    """Classifica E-value qualitativamente."""
    if np.isnan(ev):
        return "—"
    if ev >= 2.0:
        return "🟢 Robusto"
    if ev >= 1.5:
        return "🟡 Moderado"
    return "🔴 Sensível"


def fit_wls_with_treatment(
    df_cons: pd.DataFrame,
    especialidade: str,
    duracao: str,
    features: list[str] | None = None,
    refs: dict[str, str] | None = None,
) -> dict | None:
    """Score 2.0: WLS estendido com tratamento (uso da especialidade) como covariável.

    Treina 1 modelo por (duracao × especialidade) sobre `consumo_dentro_perfil`,
    onde cada perfil aparece 2 vezes (usou + nao_usou). O coeficiente da dummy
    `uso=usou` é o **efeito ajustado** controlando as 4 vars demográficas.

    Retorna dict com coef, SE, p, Δ p.p. ajustado, RR, E-value, e o modelo completo.
    `None` se faltar dados.
    """
    if features is None:
        features = WLS_FEATURES_DEFAULT
    if refs is None:
        refs = WLS_REFS_DEFAULT

    sub = df_cons[
        (df_cons["especialidade"] == especialidade)
        & (df_cons["duracao"].astype(str) == str(duracao))
    ].copy()
    if len(sub) < 4:
        return None

    extended_features = list(features) + ["uso"]
    extended_refs = {**refs, "uso": "nao_usou"}

    try:
        model = fit_wls(sub, features=extended_features, refs=extended_refs)
    except Exception:
        return None

    trt_row = model["coefs"][
        (model["coefs"]["variavel"] == "uso") & (model["coefs"]["nivel"] == "usou")
    ]
    if trt_row.empty:
        return None

    trt = trt_row.iloc[0]
    log_or = float(trt["log_odds"])
    se = float(trt["se"])

    base_logit = model["intercept_logit"]
    base_p = inv_logit(base_logit)
    treated_p = inv_logit(base_logit + log_or)
    delta_pp_adjusted = 100 * (base_p - treated_p)  # positivo: uso reduz churn
    rr = float(treated_p / base_p) if base_p > 0 else float("nan")

    # IC do efeito em p.p. via delta-method em torno do log-odds
    lo_logit = log_or - 1.96 * se
    hi_logit = log_or + 1.96 * se
    delta_lo = 100 * (base_p - inv_logit(base_logit + hi_logit))
    delta_hi = 100 * (base_p - inv_logit(base_logit + lo_logit))

    return {
        "duracao": str(duracao),
        "especialidade": especialidade,
        "log_or": log_or,
        "se": se,
        "p": float(trt["p"]),
        "sig": str(trt["sig"]),
        "delta_pp_adjusted": round(delta_pp_adjusted, 2),
        "delta_pp_ci_lo": round(delta_lo, 2),
        "delta_pp_ci_hi": round(delta_hi, 2),
        "rr": rr,
        "e_value": e_value(rr),
        "model": model,
    }


def ab_sample_size(p_baseline: float, delta_pp: float,
                   alpha: float = 0.05, power: float = 0.8) -> int:
    """Tamanho amostral por braço para detectar `delta_pp` com `alpha`/`power` dados.

    Fórmula clássica para diferença de proporções (z-test bicaudal):
        n = ((z_{α/2} + z_{β})² · 2·p̄·(1−p̄)) / δ²
    """
    p_base = p_baseline / 100.0
    delta = delta_pp / 100.0
    if delta <= 0 or p_base <= 0 or p_base >= 1:
        return 0
    p_treated = max(min(p_base - delta, 0.999), 0.001)
    p_bar = (p_base + p_treated) / 2.0
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_beta = stats.norm.ppf(power)
    n = ((z_alpha + z_beta) ** 2 * 2 * p_bar * (1 - p_bar)) / (delta ** 2)
    return int(np.ceil(n))


def adjacent_band_tests(band_summary_df: pd.DataFrame) -> pd.DataFrame:
    """Z-test entre faixas adjacentes do score (CRITICO vs ALTO, ALTO vs MEDIO, etc.)."""
    df = band_summary_df.copy().sort_values("band").reset_index(drop=True)
    rows = []
    for i in range(len(df) - 1):
        r1 = df.iloc[i]
        r2 = df.iloc[i + 1]
        t = z_test_proportions(
            int(r1["total_contratos"]), int(r1["churners"]),
            int(r2["total_contratos"]), int(r2["churners"]),
        )
        rows.append({
            "comparacao": f"{r1['band']} vs {r2['band']}",
            "churn_a": round(t["p1"], 1),
            "churn_b": round(t["p2"], 1),
            "diff_pp": round(t["diff"], 1),
            "ic_lo": round(t["ci_lo"], 1),
            "ic_hi": round(t["ci_hi"], 1),
            "p": t["p"],
            "sig": sig_stars(t["p"]),
        })
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════════
# LEGADO — funções dos 3-buckets (mantidas enquanto Páginas 4-5 ainda usam)
# ═══════════════════════════════════════════════════════════════════════════
BUCKET_ORDER = ["alto", "medio", "baixo"]
BUCKET_LABELS = {
    "alto": "🔴 Alto risco",
    "medio": "🟡 Médio risco",
    "baixo": "🟢 Baixo risco",
}
BUCKET_COLORS = {
    "alto": "#d32f2f",
    "medio": "#f9a825",
    "baixo": "#388e3c",
}


def weighted_quantiles(values: np.ndarray, weights: np.ndarray, qs):
    order = np.argsort(values)
    v = values[order]
    w = weights[order].astype(float)
    cum = np.cumsum(w) / w.sum()
    return np.interp(qs, cum, v)


def assign_buckets_within(group: pd.DataFrame) -> pd.DataFrame:
    g = group.copy()
    c1, c2 = weighted_quantiles(
        g["churn_rate"].to_numpy(),
        g["total_contratos"].to_numpy(),
        [1 / 3, 2 / 3],
    )

    def to_bucket(r: float) -> str:
        if r <= c1:
            return "baixo"
        if r <= c2:
            return "medio"
        return "alto"

    g["bucket"] = g["churn_rate"].apply(to_bucket)
    g["score"] = g["churn_rate"]
    return g


def score_cruzamento(df: pd.DataFrame) -> pd.DataFrame:
    return pd.concat(
        [assign_buckets_within(sub) for _, sub in df.groupby("duracao")],
        ignore_index=False,
    )


def cortes_por_duracao(df: pd.DataFrame) -> dict[str, tuple[float, float]]:
    return {
        str(dur): tuple(
            weighted_quantiles(
                sub["churn_rate"].to_numpy(),
                sub["total_contratos"].to_numpy(),
                [1 / 3, 2 / 3],
            )
        )
        for dur, sub in df.groupby("duracao")
    }


def bucket_summary(scored: pd.DataFrame) -> pd.DataFrame:
    agg = scored.groupby(["duracao", "bucket"], as_index=False).agg(
        total_contratos=("total_contratos", "sum"),
        churners=("churners", "sum"),
        n_perfis=("churn_rate", "count"),
    )
    agg["churn_rate"] = round(100.0 * agg["churners"] / agg["total_contratos"], 1)
    tot_dur = agg.groupby("duracao")["total_contratos"].transform("sum")
    agg["pct_duracao"] = round(100.0 * agg["total_contratos"] / tot_dur, 1)
    agg["bucket"] = pd.Categorical(agg["bucket"], categories=BUCKET_ORDER, ordered=True)
    return agg.sort_values(["duracao", "bucket"])
