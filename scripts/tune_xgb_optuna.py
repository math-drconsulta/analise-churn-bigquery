"""Tuning de hiperparâmetros do XGBoost com Optuna.

Estratégia:
- 5-fold StratifiedKFold dentro de cada trial → objetivo = AUC OOF médio
- MedianPruner: derruba trials que estão visivelmente pior que a mediana
- Search space conservador (sem extremos absurdos que destruiriam calibração)
- 1 study por duração — refletindo a arquitetura "1 modelo por plano"
- Output: results_comite/xgb_best_params.json
- Comparação honesta com baseline (XGB_PARAMS_DEFAULT corrigido pelo fix de best_iter)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import optuna
import pandas as pd
import xgboost as xgb
from optuna.pruners import MedianPruner
from optuna.samplers import TPESampler
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from comite_individual import (  # noqa: E402
    XGB_PARAMS_DEFAULT,
    _build_features_xgb,
)

OUT = ROOT / "results_comite"
CSV = OUT / "dados_individuais.csv"
N_TRIALS = 80
N_FOLDS = 5
SEED = 42

# Silenciar Optuna excessivo
optuna.logging.set_verbosity(optuna.logging.WARNING)


def objective(trial: optuna.Trial, X: pd.DataFrame, y: np.ndarray) -> float:
    """Objetivo: AUC OOF médio em 5 folds. Maior = melhor."""
    params = {
        "objective": "binary:logistic",
        "eval_metric": "auc",
        "tree_method": "hist",
        "random_state": SEED,
        "n_estimators": 800,  # ceiling alto, early stopping decide
        "early_stopping_rounds": 40,
        # Search space — conservador, sem extremos
        "max_depth": trial.suggest_int("max_depth", 3, 8),
        "learning_rate": trial.suggest_float("learning_rate", 0.02, 0.15, log=True),
        "min_child_weight": trial.suggest_int("min_child_weight", 5, 80),
        "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
        "gamma": trial.suggest_float("gamma", 0.0, 5.0),
        "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 5.0, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 5.0, log=True),
    }

    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)
    aucs = []
    for fold, (tr_idx, va_idx) in enumerate(skf.split(X, y)):
        clf = xgb.XGBClassifier(**params)
        clf.fit(
            X.iloc[tr_idx], y[tr_idx],
            eval_set=[(X.iloc[va_idx], y[va_idx])],
            verbose=False,
        )
        p_va = clf.predict_proba(X.iloc[va_idx])[:, 1]
        auc = float(roc_auc_score(y[va_idx], p_va))
        aucs.append(auc)
        # Pruning: avalia AUC médio parcial após cada fold
        trial.report(float(np.mean(aucs)), step=fold)
        if trial.should_prune():
            raise optuna.TrialPruned()
    return float(np.mean(aucs))


def tune_duracao(df_dur: pd.DataFrame, dur: str) -> dict:
    """Roda study Optuna para 1 duração. Retorna dict com best_params + métricas."""
    X, feat_names = _build_features_xgb(df_dur)
    y = df_dur["churn"].astype(int).values

    # Baseline (params atuais)
    base_params = {**XGB_PARAMS_DEFAULT}
    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)
    base_aucs = []
    base_best_iters = []
    for tr_idx, va_idx in skf.split(X, y):
        clf = xgb.XGBClassifier(**base_params)
        clf.fit(
            X.iloc[tr_idx], y[tr_idx],
            eval_set=[(X.iloc[va_idx], y[va_idx])],
            verbose=False,
        )
        p = clf.predict_proba(X.iloc[va_idx])[:, 1]
        base_aucs.append(float(roc_auc_score(y[va_idx], p)))
        bi = int(getattr(clf, "best_iteration", clf.n_estimators) or clf.n_estimators)
        base_best_iters.append(bi)
    base_auc = float(np.mean(base_aucs))

    print(f"  Baseline AUC ({dur}m, 5 folds): {base_auc:.4f}  best_iter avg: {int(np.mean(base_best_iters))}")
    print(f"  Iniciando study Optuna — {N_TRIALS} trials com MedianPruner...")

    study = optuna.create_study(
        direction="maximize",
        sampler=TPESampler(seed=SEED, n_startup_trials=15),
        pruner=MedianPruner(n_startup_trials=15, n_warmup_steps=2),
        study_name=f"xgb_dur_{dur}m",
    )

    t0 = time.time()
    study.optimize(lambda t: objective(t, X, y), n_trials=N_TRIALS, show_progress_bar=False)
    elapsed = time.time() - t0

    best_params = study.best_params
    best_auc = study.best_value

    # Re-treinar com best_params pra capturar best_iter médio
    full_params = {
        "objective": "binary:logistic",
        "eval_metric": "auc",
        "tree_method": "hist",
        "random_state": SEED,
        "n_estimators": 800,
        "early_stopping_rounds": 40,
        **best_params,
    }
    best_iters = []
    for tr_idx, va_idx in skf.split(X, y):
        clf = xgb.XGBClassifier(**full_params)
        clf.fit(
            X.iloc[tr_idx], y[tr_idx],
            eval_set=[(X.iloc[va_idx], y[va_idx])],
            verbose=False,
        )
        bi = int(getattr(clf, "best_iteration", clf.n_estimators) or clf.n_estimators)
        best_iters.append(bi)

    avg_best_iter = int(np.mean(best_iters))
    print(f"  ✓ Best AUC ({dur}m): {best_auc:.4f}  delta vs baseline: {best_auc - base_auc:+.4f}  "
          f"({elapsed:.0f}s · {len(study.trials)} trials · best_iter avg: {avg_best_iter})")

    return {
        "duracao": f"{dur}m",
        "baseline_auc": round(base_auc, 4),
        "best_auc": round(best_auc, 4),
        "delta_auc": round(best_auc - base_auc, 4),
        "elapsed_sec": round(elapsed, 1),
        "n_trials": len(study.trials),
        "n_pruned": sum(1 for t in study.trials if t.state == optuna.trial.TrialState.PRUNED),
        "best_params": best_params,
        "avg_best_iter": avg_best_iter,
    }


def main():
    if not CSV.exists():
        print(f"❌ {CSV} não encontrado. Rode queries_comite/dados_individuais.sql antes.")
        sys.exit(1)

    df = pd.read_csv(CSV)
    df["duracao"] = df["duracao"].astype(str)
    print(f"N total = {len(df):,} · churn global = {df['churn'].mean()*100:.1f}%\n")

    results = []
    for dur, sub in df.groupby("duracao"):
        sub = sub.reset_index(drop=True)
        print(f"━━━ Plano {dur}m (n={len(sub):,}) ━━━")
        r = tune_duracao(sub, str(dur))
        results.append(r)
        print()

    # Salvar best_params consolidado
    summary = {r["duracao"].replace("m", ""): r for r in results}
    out_path = OUT / "xgb_best_params.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"✓ best_params salvos em: {out_path}")

    # Resumo final
    df_summary = pd.DataFrame([
        {
            "duracao": r["duracao"],
            "baseline_auc": r["baseline_auc"],
            "tuned_auc": r["best_auc"],
            "delta_auc": f"{r['delta_auc']:+.4f}",
            "n_trials": r["n_trials"],
            "n_pruned": r["n_pruned"],
            "elapsed_sec": r["elapsed_sec"],
            "avg_best_iter": r["avg_best_iter"],
        }
        for r in results
    ])
    print("\n=== RESUMO ===")
    print(df_summary.to_string(index=False))


if __name__ == "__main__":
    main()
