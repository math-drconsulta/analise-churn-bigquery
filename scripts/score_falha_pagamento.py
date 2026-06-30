"""
Score de Falha de Pagamento — v1
=================================
Combina features de perfil (score v4) com features de pagamento (Adyen)
pra prever churn, incluindo o churn involuntario por falha de cartao.

Compara:
  A: Score v4 (so perfil)
  B: Score v4 + features de pagamento
  C: So features de pagamento

Requer:
  results/contratos_com_cpf.csv
  results/features_experiencia.csv
  results/winback_voluntario.csv
  results/unif_pgto_features_pgto.csv
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
print("SCORE DE FALHA DE PAGAMENTO — v1")
print("=" * 70)


# ═══════════════════════════════════════════════════════════════
# 1. CARREGAR
# ═══════════════════════════════════════════════════════════════
print("\n1. Carregando dados...")

df_demo = pd.read_csv("results/contratos_com_cpf.csv", dtype={"cpf": str})
df_exp = pd.read_csv("results/features_experiencia.csv")
df_wb = pd.read_csv("results/winback_voluntario.csv")
df_pgto = pd.read_csv("results/unif_pgto_features_pgto.csv")

print(f"   contratos_com_cpf:      {len(df_demo):,}")
print(f"   features_experiencia:   {len(df_exp):,}")
print(f"   winback_voluntario:     {len(df_wb):,}")
print(f"   features_pagamento:     {len(df_pgto):,}")

# Merge base (perfil)
df = df_demo.merge(
    df_exp[["contract_id", "qtd_profissionais", "qtd_especialidades",
            "nps_medio", "tempo_total_medio", "qtd_com_nps", "qtd_atendimentos",
            "nota_medico_media", "nota_atendimento_media"]],
    on="contract_id", how="inner"
)
df_wb_cols = df_wb[["contract_id", "retorno_status", "dias_ate_retorno"]].copy()
df = df.merge(df_wb_cols, on="contract_id", how="left")

# Merge features pagamento
df_pgto_cols = df_pgto[[
    "contract_id", "total_tentativas", "sucessos", "falhas",
    "dias_antes_1a_tentativa", "dias_apos_ultima_tentativa", "janela_tentativas_dias",
    "max_cycle", "max_retry",
    "n_refused_generico", "n_saldo_insuficiente", "n_blocked_retry",
    "n_fraude", "n_cartao_restrito", "n_cartao_vencido",
    "n_cartao_invalido", "n_cartao_bloqueado",
    "n_advice_new_account", "n_advice_retry_after", "mix_sucesso_falha",
]].copy()
df = df.merge(df_pgto_cols, on="contract_id", how="left")

# Filtrar contratos com tempo suficiente
df["contract_due_date"] = pd.to_datetime(df["contract_due_date"])
corte = pd.Timestamp.now() - pd.Timedelta(days=30)
df = df[df["contract_due_date"] < corte].copy()

print(f"   Base final (com merge): {len(df):,}")

# Quantos tem features de pagamento
tem_pgto = (df["total_tentativas"].notna() & (df["total_tentativas"] > 0)).sum()
print(f"   Com features pagamento: {tem_pgto:,} ({round(100*tem_pgto/len(df),1)}%)")


# ═══════════════════════════════════════════════════════════════
# 2. TARGET
# ═══════════════════════════════════════════════════════════════
print("\n2. Definindo target...")

# Target v4 (exclui todos que voltam em 30d)
df["churn_original"] = (df["churn_sn"] == "S").astype(int)
df["churn_v4"] = df["churn_original"].copy()
df.loc[
    (df["churn_original"] == 1) & (df["retorno_status"] == "voltou") &
    (df["dias_ate_retorno"].notna()) & (df["dias_ate_retorno"] <= 30),
    "churn_v4"
] = 0

rate_orig = 100 * df["churn_original"].mean()
rate_v4 = 100 * df["churn_v4"].mean()
print(f"   Churn original: {rate_orig:.1f}%")
print(f"   Churn v4:       {rate_v4:.1f}%")


# ═══════════════════════════════════════════════════════════════
# 3. FEATURES
# ═══════════════════════════════════════════════════════════════
print("\n3. Preparando features...")

# --- Features de perfil (mesmas do v4) ---
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
df["prof_por_esp"] = np.where(
    df["qtd_especialidades"] > 0,
    df["qtd_profissionais"] / df["qtd_especialidades"], 0
)
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

FEAT_CAT = [
    "ciclo", "duracao", "cronico", "faixa_dep", "faixa_idade_cat",
    "canal_simples", "faixa_nps_cat", "faixa_tempo_cat", "rotatividade_cat",
]
FEAT_NUM_PERFIL = [
    "prof_por_esp", "tempo_clinica_min", "nps_valor", "nota_medico_val",
    "nota_atend_val", "tem_atendimento", "qtd_atendimentos",
]

# --- Features de pagamento ---
FEAT_NUM_PGTO = [
    "total_tentativas", "sucessos", "falhas",
    "janela_tentativas_dias", "max_cycle", "max_retry",
    "n_refused_generico", "n_saldo_insuficiente", "n_blocked_retry",
    "n_fraude", "n_cartao_restrito", "n_cartao_vencido",
    "n_cartao_invalido", "n_cartao_bloqueado",
    "n_advice_new_account", "n_advice_retry_after", "mix_sucesso_falha",
]

# Features derivadas de pagamento
df["tem_tentativa_pgto"] = (df["total_tentativas"].fillna(0) > 0).astype(int)
df["taxa_falha_pgto"] = np.where(
    df["total_tentativas"].fillna(0) > 0,
    df["falhas"].fillna(0) / df["total_tentativas"],
    -1  # sem tentativa
)
df["so_falha"] = ((df["falhas"].fillna(0) > 0) & (df["sucessos"].fillna(0) == 0)).astype(int)

FEAT_NUM_PGTO_EXTRA = ["tem_tentativa_pgto", "taxa_falha_pgto", "so_falha"]

# Montar X para cada cenario
X_cat = pd.get_dummies(df[FEAT_CAT], drop_first=True).astype(float)

X_perfil = X_cat.copy()
for col in FEAT_NUM_PERFIL:
    X_perfil[col] = df[col].fillna(0).astype(float)

X_pgto = pd.DataFrame()
for col in FEAT_NUM_PGTO + FEAT_NUM_PGTO_EXTRA:
    X_pgto[col] = df[col].fillna(0).astype(float)

X_completo = pd.concat([X_perfil, X_pgto], axis=1)

print(f"   Features perfil:   {X_perfil.shape[1]}")
print(f"   Features pagamento: {X_pgto.shape[1]}")
print(f"   Features completo: {X_completo.shape[1]}")


# ═══════════════════════════════════════════════════════════════
# 4. CROSS-VALIDATION: 3 CENARIOS
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
        bst = xgb.train(
            params, dtrain, num_boost_round=300,
            evals=[(dval, "val")], early_stopping_rounds=30,
            verbose_eval=False,
        )
        p = bst.predict(dval)
        aucs.append(roc_auc_score(y[val], p))
    auc_mean = np.mean(aucs)
    auc_std = np.std(aucs)
    rate = 100 * y.mean()
    print(f"   {label:45s} AUC = {auc_mean:.4f} (+/- {auc_std:.4f})  rate = {rate:.1f}%")
    return auc_mean


y_v4 = df["churn_v4"].values
y_orig = df["churn_original"].values

print("   --- Target: churn_v4 (exclui 30d) ---")
results_v4 = {}
results_v4["A: So perfil (v4 baseline)"] = cv_xgb(X_perfil, y_v4, XGB_PARAMS, "A: So perfil (v4 baseline)")
results_v4["B: Perfil + pagamento"] = cv_xgb(X_completo, y_v4, XGB_PARAMS, "B: Perfil + pagamento")
results_v4["C: So pagamento"] = cv_xgb(X_pgto, y_v4, XGB_PARAMS, "C: So pagamento")

print()
print("   --- Target: churn_original (sem exclusao) ---")
results_orig = {}
results_orig["A: So perfil"] = cv_xgb(X_perfil, y_orig, XGB_PARAMS, "A: So perfil")
results_orig["B: Perfil + pagamento"] = cv_xgb(X_completo, y_orig, XGB_PARAMS, "B: Perfil + pagamento")
results_orig["C: So pagamento"] = cv_xgb(X_pgto, y_orig, XGB_PARAMS, "C: So pagamento")


# ═══════════════════════════════════════════════════════════════
# 5. FEATURE IMPORTANCE
# ═══════════════════════════════════════════════════════════════
print("\n5. Feature importance (modelo completo, target v4)...")

dtrain_full = xgb.DMatrix(X_completo, label=y_v4)
bst_full = xgb.train(XGB_PARAMS, dtrain_full, num_boost_round=200, verbose_eval=False)

imp = bst_full.get_score(importance_type="gain")
top = sorted(imp.items(), key=lambda x: -x[1])[:20]

print(f"\n   Top 20 features (gain):")
for i, (feat, gain) in enumerate(top, 1):
    tag = " *** PGTO" if feat in FEAT_NUM_PGTO + FEAT_NUM_PGTO_EXTRA else ""
    print(f"   {i:2d}. {feat:40s} {gain:>10.1f}{tag}")


# ═══════════════════════════════════════════════════════════════
# 6. ANALISE POR SUBGRUPO: COM vs SEM TENTATIVA ADYEN
# ═══════════════════════════════════════════════════════════════
print("\n6. AUC por subgrupo...")

mask_com = df["tem_tentativa_pgto"] == 1
mask_sem = df["tem_tentativa_pgto"] == 0

for mask, label in [(mask_com, "Com tentativa Adyen"), (mask_sem, "Sem tentativa Adyen")]:
    n = mask.sum()
    if n < 100:
        continue
    y_sub = df.loc[mask, "churn_v4"].values

    # Perfil
    X_sub_perfil = X_perfil.loc[mask]
    X_sub_completo = X_completo.loc[mask]

    print(f"\n   {label} (n={n:,}, churn={100*y_sub.mean():.1f}%):")
    cv_xgb(X_sub_perfil, y_sub, XGB_PARAMS, f"   So perfil")
    cv_xgb(X_sub_completo, y_sub, XGB_PARAMS, f"   Perfil + pagamento")


# ═══════════════════════════════════════════════════════════════
# 7. TREINAR MODELO FINAL + FAIXAS
# ═══════════════════════════════════════════════════════════════
print("\n7. Treinando modelo final (perfil + pagamento, target v4)...")

prob = bst_full.predict(dtrain_full)
score = (1000 * (prob.max() - prob) / (prob.max() - prob.min())).clip(0, 1000).astype(int)

BINS_5 = [-1, 200, 400, 600, 800, 1001]
LABELS_5 = ["CRITICO", "ALTO", "MEDIO", "BAIXO", "SEGURO"]

df["score_pgto"] = score
df["faixa_pgto"] = pd.cut(score, bins=BINS_5, labels=LABELS_5)

# Tambem treinar v4 puro pra comparar faixas
dtrain_v4 = xgb.DMatrix(X_perfil, label=y_v4)
bst_v4 = xgb.train(XGB_PARAMS, dtrain_v4, num_boost_round=200, verbose_eval=False)
prob_v4 = bst_v4.predict(dtrain_v4)
score_v4 = (1000 * (prob_v4.max() - prob_v4) / (prob_v4.max() - prob_v4.min())).clip(0, 1000).astype(int)
df["score_v4_ref"] = score_v4
df["faixa_v4_ref"] = pd.cut(score_v4, bins=BINS_5, labels=LABELS_5)

print("\n   Comparacao de faixas (5 faixas):\n")
print(f"   {'Faixa':12s} | {'v4 churn%':>10s} {'v4 n':>8s} | {'v4+pgto churn%':>14s} {'v4+pgto n':>10s}")
print(f"   {'-'*12}-+-{'-'*10}-{'-'*8}-+-{'-'*14}-{'-'*10}")

rows_faixas = []
for f in LABELS_5:
    mask_v4 = df["faixa_v4_ref"] == f
    mask_pg = df["faixa_pgto"] == f
    n_v4 = mask_v4.sum()
    n_pg = mask_pg.sum()
    cr_v4 = round(100 * df.loc[mask_v4, "churn_v4"].mean(), 1) if n_v4 > 0 else 0
    cr_pg = round(100 * df.loc[mask_pg, "churn_v4"].mean(), 1) if n_pg > 0 else 0
    print(f"   {f:12s} | {cr_v4:9.1f}% {n_v4:>7,} | {cr_pg:13.1f}% {n_pg:>9,}")
    rows_faixas.append({"faixa": f, "contratos_v4": n_v4, "churn_rate_v4": cr_v4,
                        "contratos_pgto": n_pg, "churn_rate_pgto": cr_pg})

# Spreads
for nome, faixa_col, target_col in [("v4", "faixa_v4_ref", "churn_v4"), ("v4+pgto", "faixa_pgto", "churn_v4")]:
    rates = []
    for f in LABELS_5:
        mask = df[faixa_col] == f
        if mask.sum() >= 10:
            rates.append(round(100 * df.loc[mask, target_col].mean(), 1))
    spread = max(rates) - min(rates) if len(rates) >= 2 else 0
    print(f"   Spread {nome}: {spread:.1f} p.p.")


# ═══════════════════════════════════════════════════════════════
# 8. SALVAR
# ═══════════════════════════════════════════════════════════════
print("\n8. Salvando resultados...")

cols_out = [
    "contract_id", "churn_original", "churn_v4",
    "score_v4_ref", "faixa_v4_ref", "score_pgto", "faixa_pgto",
    "tem_tentativa_pgto", "total_tentativas", "falhas", "so_falha",
]
df[cols_out].to_csv("results/score_pgto_contratos.csv", index=False)

df_faixas = pd.DataFrame(rows_faixas)
df_faixas.to_csv("results/score_pgto_faixas.csv", index=False)

print(f"   results/score_pgto_contratos.csv ({len(df):,} contratos)")
print(f"   results/score_pgto_faixas.csv ({len(df_faixas)} linhas)")


# ═══════════════════════════════════════════════════════════════
# RESUMO
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print("RESUMO")
print(f"{'='*70}\n")

print("   Target: churn_v4 (exclui retornos em 30d)")
print()
print("   AUC (5-fold CV):")
for label, auc in results_v4.items():
    delta = auc - results_v4["A: So perfil (v4 baseline)"]
    marker = " <<< MELHOR" if auc == max(results_v4.values()) else ""
    print(f"   {label:45s} AUC = {auc:.4f}  Δ = {delta:+.4f}{marker}")

print()
print("   Interpretacao:")
print("   - Se B > A: features de pagamento MELHORAM o score")
print("   - Se C competitivo: pagamento sozinho ja e preditivo")
print("   - Subgrupo 'com Adyen': onde o ganho se concentra")
print(f"\n{'='*70}")
