"""Auditoria do score do comitê — preparação pro comitê.

Cobre 3 eixos:
1) Métricas in-sample do WLS atual (4 vars, refs default), por duração
2) Validação das referências: o nível-ref é realmente o de menor churn observado?
3) Comparação das 3 estratégias de faixas (simétrico/assimétrico/fixo)

Saídas em results_comite/score_audit_*.csv.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from comite_scoring import (  # noqa: E402
    BAND_5_ORDER,
    BANDS_MODE_ASYMMETRIC,
    BANDS_MODE_FIXED,
    BANDS_MODE_SYMMETRIC,
    WLS_FEATURES_DEFAULT,
    WLS_REFS_DEFAULT,
    adjacent_band_tests,
    assign_bands,
    band_summary,
    fit_wls_per_duracao,
    ks_data,
    wilson_ci,
)

OUT = ROOT / "results_comite"
CSV = OUT / "storytelling_cruzamento.csv"

df = pd.read_csv(CSV)
df["duracao"] = df["duracao"].astype(str)
print(f"Linhas (perfis): {len(df)}  |  Contratos: {df['total_contratos'].sum():,}")

# ═══════════════════════════════════════════════════════════════════════════
# 1) BASELINE — métricas do modelo atual
# ═══════════════════════════════════════════════════════════════════════════
models = fit_wls_per_duracao(df, features=WLS_FEATURES_DEFAULT, refs=WLS_REFS_DEFAULT)

baseline_rows = []
for dur, m in models.items():
    met = m["metrics"]
    baseline_rows.append({
        "duracao": f"{dur}m",
        "n_perfis": met["n_perfis"],
        "n_contratos": met["n_contratos"],
        "churn_global_pct": round(met["churn_global"], 2),
        "mae_pp": round(met["mae"], 3),
        "correlacao": round(met["corr"], 4),
        "c_index": round(met["c_index"], 4),
        "gini": round(met["gini"], 4),
        "ref_churn_pp": m["ref_churn_pp"],
        "scale_pts_por_logit": round(m["scale"], 1),
    })
baseline_df = pd.DataFrame(baseline_rows)
baseline_df.to_csv(OUT / "score_audit_baseline_metricas.csv", index=False)
print("\n=== 1) BASELINE — métricas do modelo atual ===")
print(baseline_df.to_string(index=False))

# Calibração por decil de score predito (ponderado por contratos)
calib_rows = []
for dur, m in models.items():
    p = m["profiles"].copy().sort_values("p_pred").reset_index(drop=True)
    w = p["total_contratos"].values.astype(float)
    cum = np.cumsum(w) / w.sum()
    p["decil"] = pd.cut(cum, bins=np.linspace(-1e-6, 1, 11),
                       labels=list(range(1, 11)), include_lowest=True).astype(int)
    g = p.groupby("decil", observed=True).apply(
        lambda x: pd.Series({
            "n_contratos": x["total_contratos"].sum(),
            "n_churners": x["churners"].sum(),
            "churn_obs_pp": round(100 * x["churners"].sum() / x["total_contratos"].sum(), 2),
            "churn_pred_pp": round(
                (x["p_pred"] * x["total_contratos"]).sum() / x["total_contratos"].sum() * 100, 2
            ),
        })
    , include_groups=False).reset_index()
    g["erro_pp"] = (g["churn_pred_pp"] - g["churn_obs_pp"]).round(2)
    g["duracao"] = f"{dur}m"
    calib_rows.append(g)
calib_df = pd.concat(calib_rows, ignore_index=True)[
    ["duracao", "decil", "n_contratos", "n_churners", "churn_obs_pp", "churn_pred_pp", "erro_pp"]
]
calib_df.to_csv(OUT / "score_audit_calibracao_decis.csv", index=False)
print("\n=== 1b) CALIBRAÇÃO POR DECIL DE SCORE ===")
print(calib_df.to_string(index=False))

# Maior erro absoluto por perfil — onde o modelo erra mais
erros_rows = []
for dur, m in models.items():
    p = m["profiles"].copy()
    p["erro_abs"] = p["erro"].abs()
    p["duracao"] = f"{dur}m"
    erros_rows.append(p.nlargest(10, "erro_abs"))
err_df = pd.concat(erros_rows, ignore_index=True)[
    ["duracao", "ciclo", "faixa_etaria", "cronico", "composicao_titular",
     "total_contratos", "churn_rate", "churn_pred", "erro"]
]
err_df.to_csv(OUT / "score_audit_perfis_pior_ajuste.csv", index=False)
print("\n=== 1c) TOP-10 PERFIS COM MAIOR ERRO ABSOLUTO POR DURAÇÃO ===")
print(err_df.to_string(index=False))

# ═══════════════════════════════════════════════════════════════════════════
# 2) VALIDAÇÃO DAS REFERÊNCIAS
# ═══════════════════════════════════════════════════════════════════════════
ref_rows = []
for dur, sub in df.groupby("duracao"):
    for var in WLS_FEATURES_DEFAULT:
        agg = sub.groupby(var, as_index=False).agg(
            total_contratos=("total_contratos", "sum"),
            churners=("churners", "sum"),
        )
        agg["churn_pp"] = round(100 * agg["churners"] / agg["total_contratos"], 2)
        agg = agg.sort_values("churn_pp").reset_index(drop=True)
        ref_atual = WLS_REFS_DEFAULT[var]
        ref_melhor = agg.iloc[0][var]
        ref_atual_row = agg[agg[var].astype(str) == ref_atual]
        if not ref_atual_row.empty:
            churn_ref_atual = float(ref_atual_row["churn_pp"].iloc[0])
        else:
            churn_ref_atual = float("nan")
        churn_ref_melhor = float(agg.iloc[0]["churn_pp"])
        ref_rows.append({
            "duracao": f"{dur}m",
            "variavel": var,
            "ref_atual": ref_atual,
            "churn_ref_atual_pp": churn_ref_atual,
            "ref_melhor_observado": ref_melhor,
            "churn_ref_melhor_pp": churn_ref_melhor,
            "gap_pp": round(churn_ref_atual - churn_ref_melhor, 2),
            "ranking_atual": (
                int(agg[agg[var].astype(str) == ref_atual].index[0]) + 1
                if (agg[var].astype(str) == ref_atual).any() else None
            ),
            "n_niveis": len(agg),
        })
ref_df = pd.DataFrame(ref_rows)
ref_df.to_csv(OUT / "score_audit_validacao_refs.csv", index=False)
print("\n=== 2) VALIDAÇÃO DAS REFERÊNCIAS (ranking 1 = menor churn) ===")
print(ref_df.to_string(index=False))

# Ranking completo dos níveis por var × duração — pra discussão no comitê
ranking_rows = []
for dur, sub in df.groupby("duracao"):
    for var in WLS_FEATURES_DEFAULT:
        agg = sub.groupby(var, as_index=False).agg(
            total_contratos=("total_contratos", "sum"),
            churners=("churners", "sum"),
        )
        agg["churn_pp"] = round(100 * agg["churners"] / agg["total_contratos"], 2)
        agg = agg.sort_values("churn_pp").reset_index(drop=True)
        for i, r in agg.iterrows():
            _, lo, hi = wilson_ci(int(r["total_contratos"]), int(r["churners"]))
            ranking_rows.append({
                "duracao": f"{dur}m",
                "variavel": var,
                "nivel": r[var],
                "rank_churn_asc": i + 1,
                "n_contratos": int(r["total_contratos"]),
                "churn_pp": float(r["churn_pp"]),
                "ic_lo_pp": round(lo, 2),
                "ic_hi_pp": round(hi, 2),
                "eh_ref_atual": "*" if str(r[var]) == WLS_REFS_DEFAULT[var] else "",
            })
ranking_df = pd.DataFrame(ranking_rows)
ranking_df.to_csv(OUT / "score_audit_ranking_niveis.csv", index=False)

# ═══════════════════════════════════════════════════════════════════════════
# 3) COMPARAÇÃO DAS ESTRATÉGIAS DE FAIXAS
# ═══════════════════════════════════════════════════════════════════════════
band_rows = []
adj_rows = []
modes = {
    BANDS_MODE_SYMMETRIC: "simetrico",
    BANDS_MODE_ASYMMETRIC: "assimetrico",
    BANDS_MODE_FIXED: "fixo",
}
for dur, m in models.items():
    for mode_key, mode_name in modes.items():
        try:
            profs = assign_bands(m["profiles"], mode=mode_key)
            bs = band_summary(profs)
        except Exception as e:
            print(f"!! {mode_key} @ {dur}m: {e}")
            continue
        ks = ks_data(bs)
        crit = bs[bs["band"] == "CRITICO"]
        seg = bs[bs["band"] == "SEGURO"]
        spread = (
            round(float(crit["churn_rate"].iloc[0]) - float(seg["churn_rate"].iloc[0]), 1)
            if not crit.empty and not seg.empty else None
        )
        band_rows.append({
            "duracao": f"{dur}m",
            "estrategia": mode_name,
            "n_faixas_preenchidas": int((bs["total_contratos"] > 0).sum()),
            "spread_extremos_pp": spread,
            "ks_max_pp": round(float(ks["ks_pp"].max()), 1),
            "churn_critico_pp": (
                float(crit["churn_rate"].iloc[0]) if not crit.empty else None
            ),
            "churn_seguro_pp": (
                float(seg["churn_rate"].iloc[0]) if not seg.empty else None
            ),
            "vol_critico_pct": (
                float(crit["pct_duracao"].iloc[0]) if not crit.empty else None
            ),
            "vol_seguro_pct": (
                float(seg["pct_duracao"].iloc[0]) if not seg.empty else None
            ),
            "lift_critico": (
                float(crit["lift"].iloc[0]) if not crit.empty else None
            ),
            "lift_seguro": (
                float(seg["lift"].iloc[0]) if not seg.empty else None
            ),
        })

        # Adjacent band z-tests — somos rigorosos com significância
        adj = adjacent_band_tests(bs)
        adj["duracao"] = f"{dur}m"
        adj["estrategia"] = mode_name
        adj_rows.append(adj)

band_df = pd.DataFrame(band_rows)
band_df.to_csv(OUT / "score_audit_comparacao_faixas.csv", index=False)
print("\n=== 3) COMPARAÇÃO DAS 3 ESTRATÉGIAS DE FAIXAS ===")
print(band_df.to_string(index=False))

if adj_rows:
    adj_full = pd.concat(adj_rows, ignore_index=True)[
        ["duracao", "estrategia", "comparacao", "churn_a", "churn_b", "diff_pp", "ic_lo", "ic_hi", "p", "sig"]
    ]
    adj_full.to_csv(OUT / "score_audit_adjacent_tests.csv", index=False)
    print("\n=== 3b) Z-TEST ENTRE FAIXAS ADJACENTES (por estratégia) ===")
    # Imprimir só sinalizando quantas adjacências sig por estratégia
    summary = (
        adj_full.assign(eh_sig=lambda d: (d["p"] < 0.05).astype(int))
        .groupby(["duracao", "estrategia"], as_index=False)["eh_sig"].sum()
        .rename(columns={"eh_sig": "n_adjacencias_sig_p<0.05"})
    )
    print(summary.to_string(index=False))

print("\nCSVs gerados em:", OUT)
for f in sorted(OUT.glob("score_audit_*.csv")):
    print(" -", f.name)
