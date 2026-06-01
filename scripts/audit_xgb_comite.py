"""Auditoria do XGBoost da Página 7 — preparação pro comitê.

Mede 5 dimensões além do que a Página 7 já mostra:
1) Discriminação honesta (AUC_train vs AUC_cv → gap = overfit)
2) Calibração formal (Brier, ECE, slope/intercept de Platt)
3) Estabilidade entre folds (best_iter, AUC por fold)
4) Targeting real: lift e recall em top-5% / top-10% / top-20% (CV out-of-fold)
5) Features SHAP top — sinaliza se há dominância suspeita ou possível leakage

Saídas em results_comite/xgb_audit_*.csv.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from comite_individual import (  # noqa: E402
    XGB_PARAMS_DEFAULT,
    _build_features_xgb,
    compute_ks,
    fit_xgb,
)

OUT = ROOT / "results_comite"
CSV = OUT / "dados_individuais.csv"

df = pd.read_csv(CSV)
df["duracao"] = df["duracao"].astype(str)
print(f"N = {len(df):,} contratos · churn global = {df['churn'].mean()*100:.1f}%")


def expected_calibration_error(y, p, n_bins=10):
    """ECE: média ponderada |p_real - p_pred| em bins quantílicos da prob predita."""
    df = pd.DataFrame({"y": y, "p": p})
    df["b"] = pd.qcut(df["p"], n_bins, labels=False, duplicates="drop")
    g = df.groupby("b").agg(
        n=("y", "count"),
        real=("y", "mean"),
        pred=("p", "mean"),
    )
    return float((g["n"] / g["n"].sum() * (g["real"] - g["pred"]).abs()).sum() * 100)


def platt_slope_intercept(y, p):
    """Calibration in the large: ajusta logistic 1-feature sobre logit(p) → y.
    slope ~1 e intercept ~0 = bem calibrado. slope <1 = overconfident, >1 = underconfident."""
    p_clip = np.clip(p, 1e-6, 1 - 1e-6)
    logit = np.log(p_clip / (1 - p_clip))
    # Regressão logística simples com 1 feature + intercepto
    from sklearn.linear_model import LogisticRegression
    lr = LogisticRegression(fit_intercept=True, solver="lbfgs", max_iter=200)
    lr.fit(logit.reshape(-1, 1), y)
    return float(lr.coef_[0, 0]), float(lr.intercept_[0])


def targeting_metrics(y, p, top_pcts=(0.05, 0.10, 0.20)):
    """Para cada top-X% por prob predita: %churners capturados (recall) e lift."""
    out = []
    n = len(y)
    overall = y.mean()
    order = np.argsort(-p)
    y_sorted = np.asarray(y)[order]
    for pct in top_pcts:
        k = max(1, int(np.ceil(n * pct)))
        top_y = y_sorted[:k]
        recall = top_y.sum() / max(1, y_sorted.sum())
        rate = top_y.mean()
        lift = rate / overall if overall > 0 else 0
        out.append({
            "top_pct": f"{int(pct*100)}%", "n_top": k, "churn_rate_top_pp": round(100 * rate, 2),
            "recall_pct": round(100 * recall, 2), "lift": round(lift, 2),
        })
    return pd.DataFrame(out)


# ═══════════════════════════════════════════════════════════════════════════
# 1) Treinar com instrumentação ampliada (5-fold CV + métricas in-sample)
# ═══════════════════════════════════════════════════════════════════════════
N_FOLDS = 5

baseline_rows = []
fold_rows = []
target_rows = []
calib_rows = []

for dur, sub in df.groupby("duracao"):
    sub = sub.reset_index(drop=True)
    X, feat_names = _build_features_xgb(sub)
    y = sub["churn"].astype(int).values

    params = {**XGB_PARAMS_DEFAULT}
    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=42)
    oof = np.zeros(len(y))
    best_iters = []
    auc_per_fold = []

    for fold, (tr_idx, va_idx) in enumerate(skf.split(X, y)):
        clf = xgb.XGBClassifier(**params)
        clf.fit(
            X.iloc[tr_idx], y[tr_idx],
            eval_set=[(X.iloc[va_idx], y[va_idx])],
            verbose=False,
        )
        p_va = clf.predict_proba(X.iloc[va_idx])[:, 1]
        oof[va_idx] = p_va
        auc_va = float(roc_auc_score(y[va_idx], p_va))
        bi = int(getattr(clf, "best_iteration", clf.n_estimators) or clf.n_estimators)
        best_iters.append(bi)
        auc_per_fold.append(auc_va)
        fold_rows.append({
            "duracao": f"{dur}m", "fold": fold + 1,
            "n_train": int(len(tr_idx)), "n_val": int(len(va_idx)),
            "auc_val": round(auc_va, 4),
            "best_iter": bi,
        })

    # Treino final em tudo, SEM early stopping (mesmo padrão do código atual)
    params_final = {k: v for k, v in params.items() if k != "early_stopping_rounds"}
    model_final = xgb.XGBClassifier(**params_final)
    model_final.fit(X, y, verbose=False)
    p_train_final = model_final.predict_proba(X)[:, 1]

    # Modelo "honesto" — treino final usando média de best_iter (sem rodar até 600)
    avg_best = int(np.mean(best_iters))
    params_honest = {**params_final, "n_estimators": avg_best}
    model_honest = xgb.XGBClassifier(**params_honest)
    model_honest.fit(X, y, verbose=False)
    p_train_honest = model_honest.predict_proba(X)[:, 1]

    # Métricas
    auc_cv = float(roc_auc_score(y, oof))
    auc_train_full = float(roc_auc_score(y, p_train_final))
    auc_train_honest = float(roc_auc_score(y, p_train_honest))
    brier_cv = float(brier_score_loss(y, oof))
    brier_train = float(brier_score_loss(y, p_train_final))
    ks_cv = compute_ks(y, oof)
    ece = expected_calibration_error(y, oof, n_bins=10)
    slope, intercept = platt_slope_intercept(y, oof)
    ll_cv = float(log_loss(y, np.clip(oof, 1e-6, 1 - 1e-6)))

    baseline_rows.append({
        "duracao": f"{dur}m",
        "n_obs": int(len(y)),
        "n_features": int(X.shape[1]),
        "churn_rate_pp": round(100 * y.mean(), 2),
        "auc_cv": round(auc_cv, 4),
        "auc_train_n600": round(auc_train_full, 4),
        "gap_train_cv": round(auc_train_full - auc_cv, 4),
        "auc_train_honest_avgBI": round(auc_train_honest, 4),
        "gap_honest_cv": round(auc_train_honest - auc_cv, 4),
        "ks_cv_pp": round(ks_cv, 2),
        "brier_cv": round(brier_cv, 4),
        "brier_train": round(brier_train, 4),
        "logloss_cv": round(ll_cv, 4),
        "ece_pp": round(ece, 3),
        "platt_slope": round(slope, 3),
        "platt_intercept": round(intercept, 3),
        "best_iter_mean": int(np.mean(best_iters)),
        "best_iter_min": int(np.min(best_iters)),
        "best_iter_max": int(np.max(best_iters)),
        "auc_per_fold_std": round(float(np.std(auc_per_fold)), 4),
    })

    # Targeting (CV oof)
    tgt = targeting_metrics(y, oof)
    tgt["duracao"] = f"{dur}m"
    target_rows.append(tgt)

    # Calibração por decil OOF
    cal = pd.DataFrame({"y": y, "p": oof})
    cal["decil"] = pd.qcut(cal["p"], 10, labels=False, duplicates="drop")
    g = cal.groupby("decil", as_index=False).agg(
        n=("y", "count"),
        churn_real_pp=("y", lambda v: 100 * v.mean()),
        churn_pred_pp=("p", lambda v: 100 * v.mean()),
    )
    g["erro_pp"] = (g["churn_pred_pp"] - g["churn_real_pp"]).round(2)
    g["churn_real_pp"] = g["churn_real_pp"].round(2)
    g["churn_pred_pp"] = g["churn_pred_pp"].round(2)
    g["duracao"] = f"{dur}m"
    calib_rows.append(g)


baseline_df = pd.DataFrame(baseline_rows)
fold_df = pd.DataFrame(fold_rows)
target_df = pd.concat(target_rows, ignore_index=True)
calib_df = pd.concat(calib_rows, ignore_index=True)

baseline_df.to_csv(OUT / "xgb_audit_baseline_metricas.csv", index=False)
fold_df.to_csv(OUT / "xgb_audit_folds.csv", index=False)
target_df.to_csv(OUT / "xgb_audit_targeting.csv", index=False)
calib_df.to_csv(OUT / "xgb_audit_calibracao_decis.csv", index=False)

print("\n=== 1) BASELINE — MÉTRICAS (CV out-of-fold = honesto) ===")
print(baseline_df.to_string(index=False))

print("\n=== 2) ESTABILIDADE ENTRE FOLDS ===")
print(fold_df.to_string(index=False))

print("\n=== 3) TARGETING — top X% por prob predita (CV OOF) ===")
print(target_df.to_string(index=False))

print("\n=== 4) CALIBRAÇÃO POR DECIL (OOF) ===")
print(calib_df.to_string(index=False))

# ═══════════════════════════════════════════════════════════════════════════
# 5) SHAP — top features (já gerado pelo fit_xgb, vamos só consolidar)
# ═══════════════════════════════════════════════════════════════════════════
print("\nTreinando modelo final + SHAP por duração para top features (pode levar ~30s)...")
shap_rows = []
for dur, sub in df.groupby("duracao"):
    sub = sub.reset_index(drop=True)
    fitted = fit_xgb(sub, cv_folds=3)  # cv_folds=3 só pra ser rápido — vamos usar o SHAP
    imp = fitted["global_importance"].head(15).copy()
    imp["duracao"] = f"{dur}m"
    imp["rank"] = range(1, len(imp) + 1)
    shap_rows.append(imp[["duracao", "rank", "feature", "mean_abs_shap", "mean_shap"]])
shap_df = pd.concat(shap_rows, ignore_index=True).round(4)
shap_df.to_csv(OUT / "xgb_audit_shap_top.csv", index=False)
print("\n=== 5) TOP 15 FEATURES POR SHAP ===")
print(shap_df.to_string(index=False))

print("\nCSVs gerados em:", OUT)
for f in sorted(OUT.glob("xgb_audit_*.csv")):
    print(" -", f.name)
