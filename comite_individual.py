"""Score individual — fundação da Fase 1 (targeting causal).

Diferenças do WLS atual em `comite_scoring.py`:
- Trabalha com dados INDIVIDUAIS (~188k contratos), não perfis agregados (~80).
- Cada contrato recebe seu próprio score (não herdado do perfil).
- Permite features comportamentais (uso de especialidades) sem o confound de agregação.

Implementa 2 pipelines:
- **Logistic (statsmodels):** versão inicial, AUC ~0.59 (mesmo nível do WLS). Mantida por
  defensabilidade analítica (IC dos coefs), útil pra comparar.
- **XGBoost (+ SHAP):** versão escolhida para o pipeline operacional. AUC esperado 0.72+,
  com explicabilidade caso-a-caso via SHAP.

Coexiste com o WLS — não substitui as Páginas 3-6.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import shap
import statsmodels.api as sm
import xgboost as xgb
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO DE FEATURES
# ═══════════════════════════════════════════════════════════════════════════
CATEGORICAL_COLS = [
    "ciclo", "faixa_etaria", "cronico", "composicao_titular",
    "sexo", "classe_social", "canal",
]
BEHAVIORAL_COLS = [
    "tem_odonto",
    "usou_cm", "usou_cm_tele", "usou_exames", "usou_clinica_medica",
    "usou_ginecologia", "usou_cardiologia", "usou_dermatologia",
    "usou_endocrinologia", "usou_psiquiatria", "usou_ortopedia", "usou_pediatria",
]

# Referência (perfil de menor risco) — alinhado com WLS (data-driven) + extensões plausíveis.
# As 4 primeiras foram validadas como rank-1 em churn observado (ver score_audit_validacao_refs.csv).
REFS_DEFAULT = {
    "ciclo": "2o+",
    "faixa_etaria": "71+",
    "cronico": "S",
    "composicao_titular": "com_idoso",
    "sexo": "F",
    "classe_social": "AB",          # se não existir, ajustar
    "canal": "presencial_cfp",       # se não existir, ajustar
}


# ═══════════════════════════════════════════════════════════════════════════
# DESIGN MATRIX
# ═══════════════════════════════════════════════════════════════════════════
def build_design_matrix(
    df: pd.DataFrame,
    refs: dict[str, str] | None = None,
    categorical_cols: list[str] | None = None,
    behavioral_cols: list[str] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Cria matriz de design com one-hot encoding (referência = nível omitido)."""
    refs = refs or REFS_DEFAULT
    categorical_cols = categorical_cols or CATEGORICAL_COLS
    behavioral_cols = behavioral_cols or BEHAVIORAL_COLS

    pieces = [pd.Series(1.0, index=df.index, name="intercept")]
    feature_names = ["intercept"]

    for col in categorical_cols:
        if col not in df.columns:
            continue
        ref = refs.get(col)
        levels = sorted(df[col].astype(str).unique())
        # Auto-fallback: se ref não existir nos dados, usar nível mais frequente
        if ref is None or ref not in levels:
            ref = df[col].astype(str).mode().iloc[0]
        for lvl in levels:
            if lvl == ref:
                continue
            name = f"{col}={lvl}"
            pieces.append(pd.Series((df[col].astype(str) == lvl).astype(float),
                                     name=name, index=df.index))
            feature_names.append(name)

    for col in behavioral_cols:
        if col not in df.columns:
            continue
        pieces.append(df[col].astype(float).rename(col))
        feature_names.append(col)

    X = pd.concat(pieces, axis=1)
    return X, feature_names


# ═══════════════════════════════════════════════════════════════════════════
# FIT — LOGISTIC REGRESSION COM IC ANALÍTICO
# ═══════════════════════════════════════════════════════════════════════════
def fit_logit(
    df: pd.DataFrame,
    target_col: str = "churn",
    refs: dict[str, str] | None = None,
    categorical_cols: list[str] | None = None,
    behavioral_cols: list[str] | None = None,
) -> dict:
    """Ajusta logistic regression individual (statsmodels.Logit) e devolve coefs + métricas."""
    X, feat_names = build_design_matrix(df, refs, categorical_cols, behavioral_cols)
    y = df[target_col].astype(int).values

    model = sm.Logit(y, X).fit(disp=0, maxiter=200)

    # Predições
    logits = model.predict(X, which="linear")
    probs = 1.0 / (1.0 + np.exp(-logits))

    # Score 0-1000 (alto = seguro). Linear no logit.
    lmin, lmax = float(np.min(logits)), float(np.max(logits))
    if lmax > lmin:
        scores = np.round(1000 * (1 - (logits - lmin) / (lmax - lmin))).astype(int)
    else:
        scores = np.full(len(logits), 500, dtype=int)

    # Tabela de coeficientes com IC e significância
    params = model.params
    se = model.bse
    pvalues = model.pvalues
    conf = model.conf_int(alpha=0.05)
    conf.columns = ["ic_lo", "ic_hi"]

    coefs = pd.DataFrame({
        "feature": params.index,
        "coef": params.values,
        "se": se.values,
        "ic_lo": conf["ic_lo"].values,
        "ic_hi": conf["ic_hi"].values,
        "p": pvalues.values,
    })
    # Odds ratios pra leitura prática
    coefs["odds_ratio"] = np.exp(coefs["coef"])
    coefs["sig"] = coefs["p"].apply(_sig_stars)

    # Métricas
    auc = float(roc_auc_score(y, probs))
    brier = float(brier_score_loss(y, probs))
    ks = compute_ks(y, probs)

    return {
        "model": model,
        "feature_names": feat_names,
        "coefs": coefs,
        "probs": probs,
        "scores": scores,
        "logits": logits,
        "metrics": {
            "auc": auc, "brier": brier, "ks": ks,
            "n_obs": int(len(y)), "n_features": int(X.shape[1]),
            "churn_rate": float(y.mean() * 100),
        },
    }


def fit_per_duracao(
    df: pd.DataFrame,
    refs: dict[str, str] | None = None,
) -> dict[str, dict]:
    """1 modelo por duração — alinhado com o WLS atual."""
    out = {}
    for dur, sub in df.groupby("duracao"):
        out[str(dur)] = fit_logit(sub.reset_index(drop=True), refs=refs)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# MÉTRICAS DE VALIDAÇÃO
# ═══════════════════════════════════════════════════════════════════════════
def compute_ks(y: np.ndarray, probs: np.ndarray, n_bins: int = 10) -> float:
    """KS = máxima diferença entre CDFs de positivos e negativos sobre a prob predita."""
    order = np.argsort(probs)
    y_sorted = np.asarray(y)[order]
    cum_pos = np.cumsum(y_sorted) / max(y_sorted.sum(), 1)
    cum_neg = np.cumsum(1 - y_sorted) / max((1 - y_sorted).sum(), 1)
    return float(np.max(np.abs(cum_pos - cum_neg)) * 100)


def compute_calibration(
    y: np.ndarray, probs: np.ndarray, n_bins: int = 10
) -> pd.DataFrame:
    """Curva de calibração por decis de probabilidade predita."""
    df = pd.DataFrame({"y": y, "p": probs})
    df["decil"] = pd.qcut(df["p"], n_bins, labels=False, duplicates="drop")
    out = df.groupby("decil", as_index=False).agg(
        n=("y", "count"),
        churn_real=("y", "mean"),
        churn_pred=("p", "mean"),
    )
    out["churn_real"] = (out["churn_real"] * 100).round(2)
    out["churn_pred"] = (out["churn_pred"] * 100).round(2)
    out["erro"] = (out["churn_pred"] - out["churn_real"]).round(2)
    return out


def compute_band_summary(
    df: pd.DataFrame, scores: np.ndarray, churn_col: str = "churn",
    bins: list[int] | None = None,
) -> pd.DataFrame:
    """Sumário por faixas de score (alinhado com BAND_5_ORDER do WLS)."""
    bins = bins or [-1, 200, 400, 600, 800, 1001]
    labels = ["CRITICO", "ALTO", "MEDIO", "BAIXO", "SEGURO"]
    band = pd.cut(scores, bins=bins, labels=labels, include_lowest=True)
    g = pd.DataFrame({
        "band": pd.Categorical(band, categories=labels, ordered=True),
        "y": df[churn_col].astype(int).values,
    })
    agg = g.groupby("band", as_index=False, observed=True).agg(
        n=("y", "count"),
        churners=("y", "sum"),
    )
    agg["churn_rate"] = (100 * agg["churners"] / agg["n"]).round(2)
    agg["pct_volume"] = (100 * agg["n"] / agg["n"].sum()).round(1)
    overall = (agg["churners"].sum() / agg["n"].sum()) * 100
    agg["lift"] = (agg["churn_rate"] / overall).round(2) if overall > 0 else 1.0
    return agg


def _sig_stars(p: float) -> str:
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return "n.s."


# ═══════════════════════════════════════════════════════════════════════════
# PIPELINE XGBOOST + SHAP — operacional (Caminho C)
# ═══════════════════════════════════════════════════════════════════════════
XGB_PARAMS_DEFAULT = {
    "objective": "binary:logistic",
    "max_depth": 5,
    "learning_rate": 0.08,
    "subsample": 0.85,
    "colsample_bytree": 0.85,
    "min_child_weight": 10,
    "reg_lambda": 1.0,
    "eval_metric": "auc",
    "tree_method": "hist",
    "n_estimators": 600,
    "early_stopping_rounds": 40,
    "random_state": 42,
}


# ───────────────────────────────────────────────────────────────────────────
# Best params do tuning Optuna (results_comite/xgb_best_params.json)
# Gerado por scripts/tune_xgb_optuna.py
# ───────────────────────────────────────────────────────────────────────────
def load_tuned_params(duracao: str) -> dict | None:
    """Carrega best_params do study Optuna se existirem, senão retorna None.

    Args:
        duracao: '6' ou '12'.

    Returns:
        dict de params XGBoost prontos pra usar em fit_xgb(..., params=...), ou None.
    """
    import json
    from pathlib import Path
    path = Path(__file__).parent / "results_comite" / "xgb_best_params.json"
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)
    key = str(duracao).replace("m", "")
    if key not in data:
        return None
    entry = data[key]
    return {
        "objective": "binary:logistic",
        "eval_metric": "auc",
        "tree_method": "hist",
        "random_state": 42,
        "n_estimators": 800,
        "early_stopping_rounds": 40,
        **entry["best_params"],
    }

# Canais com volume residual que causam separação perfeita em logistic — não atrapalham
# XGBoost mas vale agrupar pra evitar dummies inúteis.
CANAL_RARE = {"psycoai", "coop"}


def _build_features_xgb(
    df: pd.DataFrame,
    drop_canal_rare: bool = True,
) -> tuple[pd.DataFrame, list[str]]:
    """One-hot encoding com dropna; alinhado entre treino/predict via colunas."""
    out = df.copy()
    if drop_canal_rare and "canal" in out.columns:
        out["canal"] = out["canal"].where(~out["canal"].isin(CANAL_RARE), "outros")
    cat_cols = [c for c in CATEGORICAL_COLS if c in out.columns]
    beh_cols = [c for c in BEHAVIORAL_COLS if c in out.columns]
    X = pd.get_dummies(out[cat_cols + beh_cols], columns=cat_cols, drop_first=False, dtype=float)
    return X, X.columns.tolist()


def fit_xgb(
    df: pd.DataFrame,
    target_col: str = "churn",
    cv_folds: int = 5,
    params: dict | None = None,
    seed: int = 42,
    duracao: str | None = None,
) -> dict:
    """Ajusta XGBoost com validação cruzada estratificada (AUC honesto) +
    treino final em toda a base. Calcula SHAP values na base completa.

    Args:
        duracao: '6' ou '12'. Se passado e existir xgb_best_params.json para essa
            duração, usa os params tunados por Optuna automaticamente.

    Estratégia anti-overfit do modelo final: usa a média de best_iteration dos folds
    como n_estimators no fit final (sem early stopping, porque não há eval_set).
    Sem isso, o modelo final treina 600 árvores fixas e fica muito mais overfittado
    que o CV mediu (gap AUC train-CV ~0.058 → ~0.014 com correção).
    """
    if params is None:
        tuned = load_tuned_params(duracao) if duracao is not None else None
        params = tuned if tuned else dict(XGB_PARAMS_DEFAULT)
    else:
        params = {**XGB_PARAMS_DEFAULT, **params}

    X, feat_names = _build_features_xgb(df)
    y = df[target_col].astype(int).values

    # CV pra AUC out-of-fold honesto
    oof_proba = np.zeros(len(y))
    best_iters: list[int] = []
    auc_per_fold: list[float] = []
    skf = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=seed)
    for fold, (tr_idx, va_idx) in enumerate(skf.split(X, y)):
        clf = xgb.XGBClassifier(**params)
        clf.fit(
            X.iloc[tr_idx], y[tr_idx],
            eval_set=[(X.iloc[va_idx], y[va_idx])],
            verbose=False,
        )
        p_va = clf.predict_proba(X.iloc[va_idx])[:, 1]
        oof_proba[va_idx] = p_va
        bi = int(getattr(clf, "best_iteration", clf.n_estimators) or clf.n_estimators)
        best_iters.append(bi)
        auc_per_fold.append(float(roc_auc_score(y[va_idx], p_va)))

    auc_cv = float(roc_auc_score(y, oof_proba))
    brier_cv = float(brier_score_loss(y, oof_proba))
    ks_cv = compute_ks(y, oof_proba)

    # Modelo final: usa média de best_iter dos folds como n_estimators fixo.
    # Garante que o modelo servido tem a mesma capacidade que o CV mediu.
    avg_best_iter = max(int(np.mean(best_iters)), 1)
    params_final = {
        k: v for k, v in params.items() if k != "early_stopping_rounds"
    }
    params_final["n_estimators"] = avg_best_iter
    model = xgb.XGBClassifier(**params_final)
    model.fit(X, y, verbose=False)
    probs = model.predict_proba(X)[:, 1]

    # Score 0-1000 (alto = seguro), invertendo probabilidade — IN-SAMPLE
    # (modelo final). Use para drill individual e SHAP.
    logit_p = np.log(np.clip(probs, 1e-6, 1 - 1e-6) / (1 - np.clip(probs, 1e-6, 1 - 1e-6)))
    lmin, lmax = float(logit_p.min()), float(logit_p.max())
    if lmax > lmin:
        scores = np.round(1000 * (1 - (logit_p - lmin) / (lmax - lmin))).astype(int)
    else:
        scores = np.full(len(probs), 500, dtype=int)

    # Score 0-1000 OUT-OF-FOLD — use para qualquer métrica de targeting/faixas
    # que será apresentada ao comitê. Não vaza informação de treino.
    oof_logit = np.log(np.clip(oof_proba, 1e-6, 1 - 1e-6) / (1 - np.clip(oof_proba, 1e-6, 1 - 1e-6)))
    olmin, olmax = float(oof_logit.min()), float(oof_logit.max())
    if olmax > olmin:
        oof_scores = np.round(1000 * (1 - (oof_logit - olmin) / (olmax - olmin))).astype(int)
    else:
        oof_scores = np.full(len(oof_proba), 500, dtype=int)

    # SHAP values na base completa (TreeExplainer = rápido)
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X)
    shap_expected = float(explainer.expected_value)

    # Importância global por feature (média do |SHAP|)
    global_imp = pd.DataFrame({
        "feature": feat_names,
        "mean_abs_shap": np.abs(shap_values).mean(axis=0),
        "mean_shap": shap_values.mean(axis=0),
    }).sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)

    return {
        "model": model,
        "feature_names": feat_names,
        "X": X,
        "y": y,
        "probs": probs,
        "scores": scores,
        "oof_proba": oof_proba,
        "oof_scores": oof_scores,
        "shap_values": shap_values,
        "shap_expected": shap_expected,
        "global_importance": global_imp,
        "metrics": {
            "auc_cv": auc_cv,
            "brier_cv": brier_cv,
            "ks_cv": ks_cv,
            "auc_per_fold_std": float(np.std(auc_per_fold)),
            "n_obs": int(len(y)),
            "n_features": int(X.shape[1]),
            "churn_rate": float(y.mean() * 100),
            "best_iter": avg_best_iter,
            "best_iter_min": int(min(best_iters)),
            "best_iter_max": int(max(best_iters)),
        },
    }


def fit_xgb_per_duracao(
    df: pd.DataFrame,
    target_col: str = "churn",
    cv_folds: int = 5,
    params: dict | None = None,
) -> dict[str, dict]:
    """1 modelo XGBoost por duração.

    Cada duração tenta auto-carregar seus best_params do Optuna se existirem.
    Se `params` for passado explicitamente, sobrescreve o autoload.
    """
    out = {}
    for dur, sub in df.groupby("duracao"):
        out[str(dur)] = fit_xgb(
            sub.reset_index(drop=True),
            target_col=target_col,
            cv_folds=cv_folds,
            params=params,
            duracao=str(dur),
        )
    return out


def explain_individual(
    fitted: dict, row_idx: int, top_k: int = 5
) -> pd.DataFrame:
    """Para 1 paciente: top-K features que mais contribuem (positivo = aumenta risco,
    negativo = reduz). Defensável caso-a-caso ao comitê."""
    shap_values = fitted["shap_values"][row_idx]
    feat_names = fitted["feature_names"]
    X_row = fitted["X"].iloc[row_idx]
    df_imp = pd.DataFrame({
        "feature": feat_names,
        "valor": X_row.values,
        "contribuicao": shap_values,
    })
    df_imp["abs"] = df_imp["contribuicao"].abs()
    df_imp = df_imp.sort_values("abs", ascending=False).head(top_k)
    df_imp = df_imp.drop(columns=["abs"]).reset_index(drop=True)
    return df_imp


def assign_actionable_personas(df: pd.DataFrame, scores: np.ndarray) -> pd.Series:
    """Classifica os contratos em 5 Personas Acionáveis de forma exaustiva e mutuamente exclusiva.

    Regras de Segmentação:
    1. 1. Fantasma do Onboarding: Score < 400, ciclo == '1o', usou_cm == 0, usou_exames == 0.
    2. 2. Crônico Desengajado: Score < 400, cronico == 'S', (usou_cm == 1 ou usou_exames == 1).
    3. 3. Churn Silencioso (Ex-Ativo): Score entre 400 e 599.
    4. 4. Risco Financeiro / Geral: Score < 400, e não enquadrado nos perfis 1 ou 2.
    5. 5. Seguro / Baixo Risco: Score >= 600.
    """
    scores = np.asarray(scores)
    personas = pd.Series(index=df.index, dtype='object')

    # Mascaras de Score
    risk_high = scores < 400
    risk_med = (scores >= 400) & (scores < 600)
    risk_low = scores >= 600

    # Fallback seguro para colunas
    usou_cm = df['usou_cm'] if 'usou_cm' in df.columns else pd.Series(0, index=df.index)
    usou_exames = df['usou_exames'] if 'usou_exames' in df.columns else pd.Series(0, index=df.index)
    ciclo = df['ciclo'] if 'ciclo' in df.columns else pd.Series('2o+', index=df.index)
    cronico = df['cronico'] if 'cronico' in df.columns else pd.Series('N', index=df.index)

    # Mascaras de Comportamento
    is_first_cycle = ciclo.astype(str) == '1o'
    is_chronic = cronico.astype(str) == 'S'
    no_usage = (usou_cm == 0) & (usou_exames == 0)
    any_usage = (usou_cm == 1) | (usou_exames == 1)

    # Aplicação das regras
    personas.loc[risk_low] = "5. Seguro / Baixo Risco"
    personas.loc[risk_med] = "3. Churn Silencioso (Ex-Ativo)"

    # Para risco alto (score < 400)
    onboarding_ghost = risk_high & is_first_cycle & no_usage
    chronic_disengaged = risk_high & is_chronic & any_usage

    personas.loc[onboarding_ghost] = "1. Fantasma do Onboarding"
    personas.loc[chronic_disengaged] = "2. Crônico Desengajado"

    # O restante do risco alto cai no financeiro / geral
    general_financial = risk_high & ~(onboarding_ghost | chronic_disengaged)
    personas.loc[general_financial] = "4. Risco Financeiro / Geral"

    # Garantia de preenchimento de nulos
    personas = personas.fillna("5. Seguro / Baixo Risco")

    return personas

