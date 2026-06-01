"""Validação out-of-sample do score: treina em janela antiga, valida em recente.

Pré-requisito: rodar `queries_comite/storytelling_3vars_oos.sql` no BigQuery
e salvar:
  - results_comite/storytelling_cruzamento_train.csv  (Bloco A — meses [-12m,-7m])
  - results_comite/storytelling_cruzamento_test.csv   (Bloco B — meses  [-6m,-1m])

Saída: results_comite/score_audit_oos_*.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from comite_scoring import (  # noqa: E402
    WLS_FEATURES_DEFAULT,
    WLS_REFS_DEFAULT,
    validate_oos,
)

OUT = ROOT / "results_comite"
TRAIN_CSV = OUT / "storytelling_cruzamento_train.csv"
TEST_CSV = OUT / "storytelling_cruzamento_test.csv"

if not TRAIN_CSV.exists() or not TEST_CSV.exists():
    print(
        "❌ CSVs OOS não encontrados.\n"
        f"   Esperado: {TRAIN_CSV.name} e {TEST_CSV.name}\n"
        "   Rode `queries_comite/storytelling_3vars_oos.sql` no BigQuery primeiro."
    )
    sys.exit(1)

df_train = pd.read_csv(TRAIN_CSV)
df_test = pd.read_csv(TEST_CSV)
df_train["duracao"] = df_train["duracao"].astype(str)
df_test["duracao"] = df_test["duracao"].astype(str)

print(f"Train: {len(df_train)} perfis · {df_train['total_contratos'].sum():,} contratos")
print(f"Test : {len(df_test)} perfis · {df_test['total_contratos'].sum():,} contratos")

results = validate_oos(df_train, df_test, WLS_FEATURES_DEFAULT, WLS_REFS_DEFAULT)

# ═══════════════════════════════════════════════════════════════════════════
# Comparativo de métricas train × test
# ═══════════════════════════════════════════════════════════════════════════
rows = []
for dur, r in results.items():
    mt = r["metrics_train"]
    me = r["metrics_test"]
    rows.append({
        "duracao": f"{dur}m",
        "janela": "train",
        "n_perfis": mt["n_perfis"],
        "n_contratos": mt["n_contratos"],
        "churn_global_pp": round(mt["churn_global"], 2),
        "mae_pp": round(mt["mae"], 3),
        "corr": round(mt["corr"], 4),
        "c_index": round(mt["c_index"], 4),
    })
    rows.append({
        "duracao": f"{dur}m",
        "janela": "test (OOS)",
        "n_perfis": me["n_perfis"],
        "n_contratos": me["n_contratos"],
        "churn_global_pp": round(me["churn_global"], 2),
        "mae_pp": round(me["mae"], 3),
        "corr": round(me["corr"], 4),
        "c_index": round(me["c_index"], 4),
    })
metrics_df = pd.DataFrame(rows)
metrics_df.to_csv(OUT / "score_audit_oos_metricas.csv", index=False)
print("\n=== MÉTRICAS TRAIN × TEST (OOS) ===")
print(metrics_df.to_string(index=False))

# ═══════════════════════════════════════════════════════════════════════════
# Estabilidade dos coeficientes
# ═══════════════════════════════════════════════════════════════════════════
stab_rows = []
for dur, r in results.items():
    stab = r["coef_stability"].copy()
    if stab.empty:
        continue
    stab["duracao"] = f"{dur}m"
    stab_rows.append(stab)
if stab_rows:
    stab_df = pd.concat(stab_rows, ignore_index=True)
    stab_df = stab_df[[
        "duracao", "variavel", "nivel",
        "log_odds_train", "log_odds_test", "delta_log_odds",
        "pts_train", "pts_test", "delta_pts",
        "z_delta", "delta_sig", "sig_train", "sig_test",
    ]]
    stab_df.to_csv(OUT / "score_audit_oos_estabilidade_coefs.csv", index=False)
    print("\n=== ESTABILIDADE DOS COEFICIENTES (delta_sig n.s. = coef estável) ===")
    pretty = stab_df[stab_df["variavel"] != "(intercepto)"]
    print(pretty.to_string(index=False))

print("\nCSVs gerados em:", OUT)
for f in sorted(OUT.glob("score_audit_oos_*.csv")):
    print(" -", f.name)
