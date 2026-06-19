"""
Score v5: target corrigido com desfecho real (gratis vs pago)

4 targets comparados:
  A: churn_original     — nao renovou = churn
  B: churn_real_30d     — v4, exclui TODOS que voltam em 30d
  D: churn_v5           — exclui so quem voltou PAGO, mantem gratis como churn
  C: churn_real_90d     — exclui todos que voltam em 90d

Requer: results/desfecho_churners.csv (rodar queries/desfecho_churners.sql)
"""
import pandas as pd
import numpy as np
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score
import xgboost as xgb
import warnings
warnings.filterwarnings("ignore")

SEED = 42
N_FOLDS = 5

print("=" * 70)
print("SCORE V5: TARGET CORRIGIDO COM DESFECHO REAL")
print("=" * 70)

# ═══════════════════════════════════════════════════════════════
# 1. CARREGAR
# ═══════════════════════════════════════════════════════════════
print("\n1. Carregando dados...")

df_demo = pd.read_csv("results/contratos_com_cpf.csv", dtype={"cpf": str})
df_exp = pd.read_csv("results/features_experiencia.csv")
df_wb = pd.read_csv("results/winback_voluntario.csv")

try:
    df_desf = pd.read_csv("results/desfecho_churners.csv")
    print(f"   desfecho_churners.csv: {len(df_desf):,} contratos")
    print(f"   Desfechos: {df_desf['desfecho'].value_counts().to_dict()}")
except FileNotFoundError:
    print("\n   ERRO: results/desfecho_churners.csv nao encontrado!")
    print("   Rode a query: queries/desfecho_churners.sql")
    print("   Salve o resultado em: results/desfecho_churners.csv")
    exit(1)

# Merge
df = df_demo.merge(
    df_exp[["contract_id", "qtd_profissionais", "qtd_especialidades",
            "nps_medio", "tempo_total_medio", "qtd_com_nps", "qtd_atendimentos",
            "nota_medico_media", "nota_atendimento_media"]],
    on="contract_id", how="inner"
)
df_wb_cols = df_wb[["contract_id", "retorno_status", "dias_ate_retorno"]].copy()
df = df.merge(df_wb_cols, on="contract_id", how="left")
df = df.merge(df_desf[["contract_id", "desfecho"]], on="contract_id", how="left")

df["contract_due_date"] = pd.to_datetime(df["contract_due_date"])
corte = pd.Timestamp.now() - pd.Timedelta(days=30)
df = df[df["contract_due_date"] < corte].copy()

# ═══════════════════════════════════════════════════════════════
# 2. TARGETS
# ═══════════════════════════════════════════════════════════════
print("\n2. Definindo targets...")

# A: original
df["churn_original"] = (df["churn_sn"] == "S").astype(int)

# B: v4 (exclui todos que voltam em 30d)
df["churn_real_30d"] = df["churn_original"].copy()
df.loc[
    (df["churn_original"] == 1) & (df["retorno_status"] == "voltou") &
    (df["dias_ate_retorno"].notna()) & (df["dias_ate_retorno"] <= 30),
    "churn_real_30d"
] = 0

# C: exclui todos que voltam em 90d
df["churn_real_90d"] = df["churn_original"].copy()
df.loc[
    (df["churn_original"] == 1) & (df["retorno_status"] == "voltou") &
    (df["dias_ate_retorno"].notna()) & (df["dias_ate_retorno"] <= 90),
    "churn_real_90d"
] = 0

# D: v5 — exclui so quem voltou PAGO em 30d, mantem gratis como churn
df["churn_v5"] = df["churn_original"].copy()
df.loc[
    (df["churn_original"] == 1) &
    (df["retorno_status"] == "voltou") &
    (df["dias_ate_retorno"].notna()) &
    (df["dias_ate_retorno"] <= 30) &
    (df["desfecho"] == "voltou_pago"),
    "churn_v5"
] = 0

n = len(df)
for col, label in [
    ("churn_original", "A: Original"),
    ("churn_real_30d", "B: Real 30d (v4)"),
    ("churn_v5",       "D: V5 (so exclui pago)"),
    ("churn_real_90d", "C: Real 90d"),
]:
    rate = 100 * df[col].mean()
    total = df[col].sum()
    print(f"   {label:35s} {total:>7,} churners ({rate:.1f}%)")


# ═══════════════════════════════════════════════════════════════
# 3. FEATURES (mesmas do v4)
# ═══════════════════════════════════════════════════════════════
print("\n3. Preparando features...")

df["duracao"] = df["duracao"].astype(str)
df["ciclo"] = df["ciclo"].fillna("1o")
df["cronico"] = df["cronico"].fillna("N")
df["canal_simples"] = df["canal"].fillna("outros").apply(
    lambda x: "digital" if "digital" in str(x).lower() else "presencial"
)
df["faixa_dep"] = pd.cut(
    pd.to_numeric(df["dependentes"], errors="coerce").fillna(0),
    bins=[-1, 0, 2, 99], labels=["sem_dep", "1-2_dep", "3+_dep"]
).astype(str)
df["faixa_idade_cat"] = pd.cut(
    pd.to_numeric(df["idade"], errors="coerce").fillna(35),
    bins=[0, 30, 50, 120], labels=["jovem", "adulto", "senior"]
).astype(str)
df["prof_por_esp"] = np.where(df["qtd_especialidades"] > 0, df["qtd_profissionais"] / df["qtd_especialidades"], 0)
df["tempo_clinica_min"] = df["tempo_total_medio"].fillna(0) / 60
df["nps_valor"] = df["nps_medio"].fillna(-1)
df["tem_atendimento"] = (df["qtd_atendimentos"] > 0).astype(int)
df["nota_medico_val"] = df["nota_medico_media"].fillna(-1)
df["nota_atend_val"] = df["nota_atendimento_media"].fillna(-1)

df["faixa_nps_cat"] = "sem_nps"
df.loc[(df["nps_valor"] >= 0) & (df["nps_valor"] <= 6), "faixa_nps_cat"] = "detrator"
df.loc[(df["nps_valor"] > 6) & (df["nps_valor"] <= 8), "faixa_nps_cat"] = "neutro"
df.loc[df["nps_valor"] > 8, "faixa_nps_cat"] = "promotor"

df["faixa_tempo_cat"] = "sem_atend"
df.loc[(df["tempo_clinica_min"] > 0) & (df["tempo_clinica_min"] < 15), "faixa_tempo_cat"] = "curto"
df.loc[(df["tempo_clinica_min"] >= 15) & (df["tempo_clinica_min"] < 30), "faixa_tempo_cat"] = "medio"
df.loc[df["tempo_clinica_min"] >= 30, "faixa_tempo_cat"] = "longo"

df["rotatividade_cat"] = "sem_atend"
df.loc[(df["qtd_atendimentos"] > 0) & (df["prof_por_esp"] < 1.5), "rotatividade_cat"] = "continuidade"
df.loc[(df["qtd_atendimentos"] > 0) & (df["prof_por_esp"] >= 1.5) & (df["prof_por_esp"] < 2), "rotatividade_cat"] = "moderada"
df.loc[(df["qtd_atendimentos"] > 0) & (df["prof_por_esp"] >= 2), "rotatividade_cat"] = "alta"

FEAT_CAT = ["ciclo", "duracao", "cronico", "faixa_dep", "faixa_idade_cat",
            "canal_simples", "faixa_nps_cat", "faixa_tempo_cat", "rotatividade_cat"]
FEAT_NUM = ["prof_por_esp", "tempo_clinica_min", "nps_valor", "nota_medico_val",
            "nota_atend_val", "tem_atendimento", "qtd_atendimentos"]

X = pd.get_dummies(df[FEAT_CAT], drop_first=True).astype(float)
for col in FEAT_NUM:
    X[col] = df[col].fillna(0).astype(float)

print(f"   Features: {X.shape[1]}")
print(f"   Contratos: {len(X):,}")


# ═══════════════════════════════════════════════════════════════
# 4. CROSS-VALIDATION: COMPARAR TODOS OS TARGETS
# ═══════════════════════════════════════════════════════════════
print("\n4. Cross-validation (5-fold)...\n")

XGB_PARAMS = {
    "objective": "binary:logistic", "eval_metric": "auc", "verbosity": 0,
    "max_depth": 4, "learning_rate": 0.08, "subsample": 0.8, "colsample_bytree": 0.8,
}

def cv_xgb(X, y, params, label):
    kf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)
    aucs = []
    for tr, val in kf.split(X, y):
        dtrain = xgb.DMatrix(X.iloc[tr], label=y[tr])
        dval = xgb.DMatrix(X.iloc[val], label=y[val])
        bst = xgb.train(params, dtrain, num_boost_round=300,
                        evals=[(dval, "val")], early_stopping_rounds=30,
                        verbose_eval=False)
        p = bst.predict(dval)
        aucs.append(roc_auc_score(y[val], p))
    auc_mean = np.mean(aucs)
    auc_std = np.std(aucs)
    print(f"   {label:35s} AUC = {auc_mean:.4f} (+/- {auc_std:.4f})  |  rate = {100*y.mean():.1f}%")
    return auc_mean

results = {}
for col, label in [
    ("churn_original", "A: Original"),
    ("churn_real_30d", "B: Real 30d (v4)"),
    ("churn_v5",       "D: V5 (so exclui pago)"),
    ("churn_real_90d", "C: Real 90d"),
]:
    results[label] = cv_xgb(X, df[col].values, XGB_PARAMS, label)


# ═══════════════════════════════════════════════════════════════
# 5. TREINAR MODELO FINAL V5 + FAIXAS
# ═══════════════════════════════════════════════════════════════
print("\n5. Treinando modelo final v5...")

y_v5 = df["churn_v5"].values
dtrain = xgb.DMatrix(X, label=y_v5)
bst = xgb.train(XGB_PARAMS, dtrain, num_boost_round=200, verbose_eval=False)
prob = bst.predict(dtrain)
score = (1000 * (prob.max() - prob) / (prob.max() - prob.min())).clip(0, 1000).astype(int)

# Faixas
BINS_5 = [-1, 200, 400, 600, 800, 1001]
LABELS_5 = ["CRITICO", "ALTO", "MEDIO", "BAIXO", "SEGURO"]
BINS_7 = [-1, 143, 286, 429, 571, 714, 857, 1001]
LABELS_7 = ["CRITICO", "MUITO ALTO", "ALTO", "MEDIO", "BAIXO", "MUITO BAIXO", "SEGURO"]

df["score_v5"] = score
df["faixa_5"] = pd.cut(score, bins=BINS_5, labels=LABELS_5)
df["faixa_7"] = pd.cut(score, bins=BINS_7, labels=LABELS_7)


# ═══════════════════════════════════════════════════════════════
# 6. COMPARAR FAIXAS: V4 vs V5
# ═══════════════════════════════════════════════════════════════
print("\n6. Comparando faixas...\n")

# Tambem treinar v4 pra comparar lado a lado
y_v4 = df["churn_real_30d"].values
dtrain_v4 = xgb.DMatrix(X, label=y_v4)
bst_v4 = xgb.train(XGB_PARAMS, dtrain_v4, num_boost_round=200, verbose_eval=False)
prob_v4 = bst_v4.predict(dtrain_v4)
score_v4 = (1000 * (prob_v4.max() - prob_v4) / (prob_v4.max() - prob_v4.min())).clip(0, 1000).astype(int)
df["score_v4"] = score_v4
df["faixa_5_v4"] = pd.cut(score_v4, bins=BINS_5, labels=LABELS_5)
df["faixa_7_v4"] = pd.cut(score_v4, bins=BINS_7, labels=LABELS_7)

for layout, bins, labels, faixa_col_v5, faixa_col_v4 in [
    ("5 faixas", BINS_5, LABELS_5, "faixa_5", "faixa_5_v4"),
    ("7 faixas", BINS_7, LABELS_7, "faixa_7", "faixa_7_v4"),
]:
    print(f"   --- {layout} ---")
    print(f"   {'Faixa':12s} | {'V4 churn%':>10s} {'V4 n':>8s} | {'V5 churn%':>10s} {'V5 n':>8s} | {'Δ':>6s}")
    print(f"   {'-'*12}-+-{'-'*10}-{'-'*8}-+-{'-'*10}-{'-'*8}-+-{'-'*6}")

    rates_v4 = []
    rates_v5 = []
    for f in labels:
        # V4: usa target v4 (churn_real_30d) com score v4
        mask_v4 = df[faixa_col_v4] == f
        n_v4 = mask_v4.sum()
        cr_v4 = round(100 * df.loc[mask_v4, "churn_real_30d"].mean(), 1) if n_v4 > 0 else 0

        # V5: usa target v5 (churn_v5) com score v5
        mask_v5 = df[faixa_col_v5] == f
        n_v5 = mask_v5.sum()
        cr_v5 = round(100 * df.loc[mask_v5, "churn_v5"].mean(), 1) if n_v5 > 0 else 0

        delta = round(cr_v5 - cr_v4, 1)
        print(f"   {f:12s} | {cr_v4:9.1f}% {n_v4:>7,} | {cr_v5:9.1f}% {n_v5:>7,} | {delta:+5.1f}")
        if n_v4 >= 10:
            rates_v4.append(cr_v4)
        if n_v5 >= 10:
            rates_v5.append(cr_v5)

    spread_v4 = max(rates_v4) - min(rates_v4) if len(rates_v4) >= 2 else 0
    spread_v5 = max(rates_v5) - min(rates_v5) if len(rates_v5) >= 2 else 0
    print(f"   SPREAD:       | {spread_v4:9.1f} p.p.          | {spread_v5:9.1f} p.p.          | {spread_v5-spread_v4:+5.1f}")
    print()


# ═══════════════════════════════════════════════════════════════
# 7. SALVAR CSVs
# ═══════════════════════════════════════════════════════════════
print("7. Salvando resultados...")

# Contratos individuais
cols_out = [
    "contract_id", "ciclo", "duracao", "cronico", "faixa_dep", "faixa_idade_cat",
    "canal_simples", "faixa_nps_cat", "faixa_tempo_cat", "rotatividade_cat",
    "desfecho", "churn_original", "churn_real_30d", "churn_v5",
    "score_v4", "score_v5", "faixa_5", "faixa_7",
]
df[cols_out].to_csv("results/score_v5_contratos.csv", index=False)
print(f"   results/score_v5_contratos.csv ({len(df):,} contratos)")

# Faixas agregadas
rows = []
for layout, faixa_col, labels_list in [
    ("5_faixas", "faixa_5", LABELS_5),
    ("7_faixas", "faixa_7", LABELS_7),
]:
    for f in labels_list:
        mask = df[faixa_col] == f
        n = mask.sum()
        if n == 0:
            continue
        churners = df.loc[mask, "churn_v5"].sum()
        cr = round(100 * churners / n, 1)
        pct_base = round(100 * n / len(df), 1)

        # Tambem mostrar churn original e v4 pra comparacao
        cr_orig = round(100 * df.loc[mask, "churn_original"].mean(), 1)
        cr_v4 = round(100 * df.loc[mask, "churn_real_30d"].mean(), 1)

        rows.append({
            "layout": layout, "faixa": f,
            "contratos": n, "churners_v5": int(churners),
            "churn_rate_v5": cr,
            "churn_rate_v4": cr_v4,
            "churn_rate_original": cr_orig,
            "pct_base": pct_base,
        })

df_faixas = pd.DataFrame(rows)
df_faixas.to_csv("results/score_v5_faixas.csv", index=False)
print(f"   results/score_v5_faixas.csv ({len(df_faixas)} linhas)")


# ═══════════════════════════════════════════════════════════════
# RESUMO
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print("RESUMO")
print(f"{'='*70}")
for label, auc in results.items():
    delta = auc - results["A: Original"]
    print(f"   {label:35s} AUC = {auc:.4f}  Δ = {delta:+.4f}")
print()
print("   V5 exclui do churn APENAS quem voltou pro PAGO em 30 dias.")
print("   Quem migrou pro gratis continua como churn (82% saem depois).")
print(f"{'='*70}")
