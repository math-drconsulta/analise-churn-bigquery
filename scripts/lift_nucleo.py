"""
Mede o lift de adicionar features do núcleo familiar ao score de churn.

Quatro variantes logísticas individuais (sobre o nucleo_familiar.csv):
  A) BASELINE       — 7 vars do score atual, com dependentes 3-níveis baseado
                      em dep_count_anl (snapshot do contrato, mesma fonte do
                      score em produção).
  B) +COMPOSICAO    — BASELINE + composicao_drc (4 níveis). ⚠️ Mistura duas
                      fontes de "dependente" (dep_count_anl vs qtd_dep_total),
                      o que introduz LEAKAGE: contratos onde os dois divergem
                      (n=9818) têm churn 0,2% — impossível sem vazamento de
                      target (provável: cancelamento de dep em ref_yalo_subscr.
                      só ocorre depois da decisão de renovação). Reportado pra
                      visibilidade, NÃO usar pra produção.
  C) +NUCLEO_FULL   — B + 4 features contínuas. Mesma contaminação do B.
  D) V3_LIMPO       — BASELINE com dependentes baseado em qtd_dep_total (não
                      dep_count_anl) + composicao_drc. Sem leakage. Alinha as
                      fontes — esse é o candidato real pra score v2.

Treino/teste 70/30 estratificado por churn, IRLS à mão (sem sklearn).
Métricas: AUC, Gini, KS, log-loss, lift por decil.
"""
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "results" / "nucleo_familiar.csv"
OUT = ROOT / "results" / "lift_nucleo_score.csv"
OUT_DECIS = ROOT / "results" / "lift_nucleo_decis.csv"

RNG = np.random.default_rng(42)


def stratified_split(y, frac_train=0.7, rng=RNG):
    idx = np.arange(len(y))
    train = []
    test = []
    for cls in np.unique(y):
        mask = np.where(y == cls)[0]
        rng.shuffle(mask)
        cut = int(len(mask) * frac_train)
        train.append(mask[:cut])
        test.append(mask[cut:])
    return np.concatenate(train), np.concatenate(test)


def fit_irls(X, y, max_iter=50, tol=1e-7, ridge=1e-4):
    """Logistic regression via Iteratively Reweighted Least Squares.
    Ridge mínimo (1e-4) só pra estabilizar quando há colinearidade.
    """
    n, p = X.shape
    beta = np.zeros(p)
    for it in range(max_iter):
        eta = X @ beta
        eta = np.clip(eta, -30, 30)
        mu = 1 / (1 + np.exp(-eta))
        W = mu * (1 - mu)
        W = np.maximum(W, 1e-9)
        XtWX = (X.T * W) @ X + ridge * np.eye(p)
        XtWz = X.T @ (W * eta + (y - mu))
        beta_new = np.linalg.solve(XtWX, XtWz)
        if np.max(np.abs(beta_new - beta)) < tol:
            beta = beta_new
            break
        beta = beta_new
    return beta


def predict_proba(X, beta):
    eta = np.clip(X @ beta, -30, 30)
    return 1 / (1 + np.exp(-eta))


def auc_roc(y, p):
    """Mann-Whitney based AUC."""
    order = np.argsort(p)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(p) + 1)
    # média dos ranks para empates
    df = pd.DataFrame({"p": p, "r": ranks})
    df["r"] = df.groupby("p")["r"].transform("mean")
    pos = df["r"][y == 1].sum()
    n_pos = (y == 1).sum()
    n_neg = (y == 0).sum()
    return (pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def ks_stat(y, p):
    df = pd.DataFrame({"y": y, "p": p}).sort_values("p")
    cum_pos = (df["y"] == 1).cumsum() / max((y == 1).sum(), 1)
    cum_neg = (df["y"] == 0).cumsum() / max((y == 0).sum(), 1)
    return float((cum_pos - cum_neg).abs().max())


def log_loss(y, p):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def deciles_lift(y, p, n_bins=10):
    df = pd.DataFrame({"y": y, "p": p})
    df["bin"] = pd.qcut(df["p"], n_bins, labels=False, duplicates="drop")
    g = df.groupby("bin").agg(n=("y", "size"), churners=("y", "sum"),
                              p_med=("p", "mean")).reset_index()
    g["churn_obs"] = g["churners"] / g["n"]
    base = df["y"].mean()
    g["lift"] = g["churn_obs"] / base
    return g


SHARED_REFS = {
    "duracao": "6",
    "contrato": "2o+",
    "faixa_idade_titular": "51-70",
    "cronico_titular": "S",
    "canal": "presencial_cfp",
    "classe": "AB",
}


def shared_dummies(df):
    cols, names = [], []
    for var, ref in SHARED_REFS.items():
        for lv in sorted(df[var].astype(str).unique()):
            if lv == ref:
                continue
            cols.append((df[var].astype(str) == lv).astype(float).values)
            names.append(f"{var}={lv}")
    return cols, names


def dependentes_3lvl(df, source="dep_count_anl"):
    """3 níveis: sem_dep / 1-2_dep / 3+_dep (ref=3+).
    source='dep_count_anl' (default — o que o score atual usa) ou 'qtd_dep_total'.
    """
    dep_lvl = pd.cut(df[source].fillna(0),
                     bins=[-0.5, 0.5, 2.5, np.inf],
                     labels=["sem_dep", "1-2_dep", "3+_dep"])
    cols, names = [], []
    for lv in ["sem_dep", "1-2_dep"]:
        cols.append((dep_lvl == lv).astype(float).values)
        names.append(f"dependentes={lv}")
    return cols, names


def composicao_drc_4lvl(df):
    """4 níveis: solo (ref) / so_ativos_drc / passivos_e_ativos / so_passivos."""
    cols, names = [], []
    for lv in ["so_ativos_drc", "passivos_e_ativos", "so_passivos"]:
        cols.append((df["composicao_drc"] == lv).astype(float).values)
        names.append(f"composicao_drc={lv}")
    return cols, names


def dependentes_qtd_when_has(df):
    """Dummy '1-2_dep' usando qtd_dep_total (não dep_count_anl).
    Ref implícita: 3+_dep entre quem tem dep. Pra solo, dummy = 0.
    Combinada com composicao_drc_4lvl (ref=solo), zero colinearidade
    (sem_dep ≡ solo perfeitamente, ambos baseados em qtd_dep_total).
    """
    qtd = df["qtd_dep_total"].fillna(0).astype(int)
    has_dep = df["composicao_drc"] != "solo"
    cols = [((qtd >= 1) & (qtd <= 2) & has_dep).astype(float).values]
    names = ["dependentes_qtd=1-2_dep"]
    return cols, names


def nucleo_extras(df):
    """Features contínuas adicionais do núcleo."""
    cols, names = [], []
    cols.append(df["qtd_dep_cronicos_S"].clip(upper=2).fillna(0).astype(float).values)
    names.append("qtd_dep_cronicos_S_cap2")
    cols.append(df["pct_deps_passivos"].fillna(0).astype(float).values / 100)
    names.append("pct_deps_passivos")
    cols.append(df["qtd_dep_consumiu"].clip(upper=4).fillna(0).astype(float).values)
    names.append("qtd_dep_consumiu_cap4")
    cols.append(df["qtd_especialidades_dep_distintas"].clip(upper=4).fillna(0).astype(float).values)
    names.append("qtd_especialidades_dep_distintas_cap4")
    return cols, names


def nucleo_etario(df):
    """Features etárias dos deps (v4 da query — idade agora 100% coberta).
    Filtra outliers (idade fora de [0, 110]) tratando como NULL e fallback
    pra contagem 0. Usa flags S/N pra entrar separadas (não usar
    tem_dep_financeiro, que mistura jovens e idosos com efeitos opostos).
    """
    cols, names = [], []
    # Detecta contratos com idade implausível e neutraliza-os
    plausivel = ((df["idade_max_dep"].fillna(0) <= 110) &
                 (df["idade_max_dep"].fillna(0) >= 0) &
                 (df["idade_min_dep"].fillna(0) <= 110) &
                 (df["idade_min_dep"].fillna(0) >= 0))
    qjov = df["qtd_dep_jovens"].where(plausivel, 0).fillna(0)
    qid  = df["qtd_dep_idosos"].where(plausivel, 0).fillna(0)
    cols.append((qjov >= 1).astype(float).values)
    names.append("tem_dep_jovem")
    cols.append((qid >= 1).astype(float).values)
    names.append("tem_dep_idoso")
    return cols, names


def build_design(df, variant):
    """variant ∈ {'baseline', 'baseline_qtd', 'plus_composicao', 'plus_full',
                   'v3_limpo', 'v4_etario', 'v4_full'}

    baseline       — replica o score atual (dep_count_anl)
    baseline_qtd   — baseline mas trocando dep_count_anl por qtd_dep_total (sem leakage)
    plus_composicao— baseline + composicao_drc (⚠️ com leakage cadastral)
    plus_full      — plus_composicao + 4 features contínuas (⚠️ com leakage)
    v3_limpo       — baseline_qtd + composicao_drc (proposta limpa)
    v4_etario      — v3_limpo + tem_dep_jovem + tem_dep_idoso (NEW: idade dos deps)
    v4_full        — v4_etario + qtd_dep_cronicos_S + pct_deps_passivos + qtd_dep_consumiu
                     + qtd_especialidades_dep_distintas (versão maximalista limpa)
    """
    cols, names = shared_dummies(df)
    if variant == "baseline":
        c, n = dependentes_3lvl(df, "dep_count_anl"); cols += c; names += n
    elif variant == "baseline_qtd":
        c, n = dependentes_3lvl(df, "qtd_dep_total"); cols += c; names += n
    elif variant == "plus_composicao":
        c, n = dependentes_3lvl(df, "dep_count_anl"); cols += c; names += n
        c, n = composicao_drc_4lvl(df);                cols += c; names += n
    elif variant == "plus_full":
        c, n = dependentes_3lvl(df, "dep_count_anl"); cols += c; names += n
        c, n = composicao_drc_4lvl(df);                cols += c; names += n
        c, n = nucleo_extras(df);                       cols += c; names += n
    elif variant == "v3_limpo":
        c, n = composicao_drc_4lvl(df);        cols += c; names += n
        c, n = dependentes_qtd_when_has(df);   cols += c; names += n
    elif variant == "v4_etario":
        c, n = composicao_drc_4lvl(df);        cols += c; names += n
        c, n = dependentes_qtd_when_has(df);   cols += c; names += n
        c, n = nucleo_etario(df);              cols += c; names += n
    elif variant == "v4_full":
        c, n = composicao_drc_4lvl(df);        cols += c; names += n
        c, n = dependentes_qtd_when_has(df);   cols += c; names += n
        c, n = nucleo_etario(df);              cols += c; names += n
        c, n = nucleo_extras(df);              cols += c; names += n
    else:
        raise ValueError(variant)
    X = np.column_stack([np.ones(len(df))] + cols)
    return X, ["intercept"] + names


def evaluate(beta, X, y, label):
    p = predict_proba(X, beta)
    return {
        "modelo": label,
        "n": len(y),
        "auc": auc_roc(y, p),
        "gini": 2 * auc_roc(y, p) - 1,
        "ks": ks_stat(y, p),
        "log_loss": log_loss(y, p),
        "churn_base": float(y.mean()),
    }, p


def main():
    print(f"[load] {CSV}")
    df = pd.read_csv(CSV, low_memory=False)
    print(f"  shape={df.shape}  churn={df.churner.mean():.4f}")

    y = df["churner"].astype(int).values
    train, test = stratified_split(y)
    print(f"  train n={len(train)}  test n={len(test)}")

    metrics_rows = []
    decis_all = []
    coefs_all = []
    probas_test = {}

    for variant in ["baseline", "baseline_qtd", "plus_composicao", "plus_full", "v3_limpo"]:
        X, names = build_design(df, variant)
        beta = fit_irls(X[train], y[train])
        m_tr, _ = evaluate(beta, X[train], y[train], f"{variant}_train")
        m_te, p_te = evaluate(beta, X[test], y[test], f"{variant}_test")
        metrics_rows += [m_tr, m_te]
        probas_test[variant] = p_te
        coefs_all.append(pd.DataFrame({"variant": variant, "feature": names, "beta": beta}))
        d = deciles_lift(y[test], p_te).assign(modelo=variant)
        decis_all.append(d)

    metrics = pd.DataFrame(metrics_rows)
    coefs = pd.concat(coefs_all, ignore_index=True)
    decis = pd.concat(decis_all, ignore_index=True)

    print("\n=== métricas ===")
    print(metrics.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    base_te = metrics[metrics["modelo"] == "baseline_test"].iloc[0]
    print("\n=== delta vs baseline (test) ===")
    for v in ["baseline_qtd", "plus_composicao", "plus_full", "v3_limpo"]:
        r = metrics[metrics["modelo"] == f"{v}_test"].iloc[0]
        print(f"  {v}:  ΔAUC={r['auc']-base_te['auc']:+.4f}  "
              f"ΔGini={r['gini']-base_te['gini']:+.4f}  "
              f"ΔKS={r['ks']-base_te['ks']:+.4f}  "
              f"Δlog-loss={r['log_loss']-base_te['log_loss']:+.4f}")

    print("\n=== coefs plus_full (top 15 por |beta|) ===")
    sub = coefs[coefs["variant"] == "plus_full"].copy()
    print(sub.reindex(sub["beta"].abs().sort_values(ascending=False).index)
          .head(15)[["feature", "beta"]].to_string(index=False,
                                                    float_format=lambda v: f"{v:+.4f}"))

    print("\n=== coefs v3_limpo (todos, ordenados por |beta|) — proposta de score v2 ===")
    sub = coefs[coefs["variant"] == "v3_limpo"].copy()
    print(sub.reindex(sub["beta"].abs().sort_values(ascending=False).index)
          [["feature", "beta"]].to_string(index=False,
                                          float_format=lambda v: f"{v:+.4f}"))

    print("\n=== lift por decil (test, ordenado por modelo/bin) ===")
    print(decis[["modelo", "bin", "n", "churners", "churn_obs", "lift"]]
          .to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    metrics.to_csv(OUT, index=False)
    decis.to_csv(OUT_DECIS, index=False)
    coefs.to_csv(ROOT / "results" / "lift_nucleo_coefs.csv", index=False)
    print(f"\n[save] {OUT}")
    print(f"[save] {OUT_DECIS}")
    print(f"[save] {ROOT / 'results' / 'lift_nucleo_coefs.csv'}")


if __name__ == "__main__":
    main()
