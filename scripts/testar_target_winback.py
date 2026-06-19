"""
Testa se redefinir o target do modelo (excluindo quem volta em 30d)
melhora o AUC.

3 targets:
  A: churn original (nao renovou = churn)
  B: churn real 30d (nao renovou E nao voltou em 30 dias)
  C: churn real 90d (nao renovou E nao voltou em 90 dias)

Modelo: XGBoost com as mesmas features do score v3.
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

print("=" * 65)
print("TESTE: REDEFINICAO DO TARGET COM WIN-BACK")
print("=" * 65)

# ═══════════════════════════════════════════════════════════════
# 1. CARREGAR E MERGEAR
# ═══════════════════════════════════════════════════════════════
print("\n1. Carregando dados...")

df_demo = pd.read_csv("results/contratos_com_cpf.csv", dtype={"cpf": str})
df_exp = pd.read_csv("results/features_experiencia.csv")
df_wb = pd.read_csv("results/winback_voluntario.csv")

# Merge demo + experiencia
df = df_demo.merge(
    df_exp[["contract_id", "qtd_profissionais", "qtd_especialidades",
            "nps_medio", "tempo_total_medio", "qtd_com_nps", "qtd_atendimentos",
            "nota_medico_media", "nota_atendimento_media"]],
    on="contract_id", how="inner"
)

# Merge com winback (pra ter dias_ate_retorno e faixa_retorno)
df_wb_cols = df_wb[["contract_id", "retorno_status", "faixa_retorno", "dias_ate_retorno"]].copy()
df = df.merge(df_wb_cols, on="contract_id", how="left")

# Target original
df["churn_original"] = (df["churn_sn"] == "S").astype(int)

# Target B: churn real 30d (churnou E nao voltou em 30 dias)
df["churn_real_30d"] = df["churn_original"].copy()
df.loc[
    (df["churn_original"] == 1) &
    (df["retorno_status"] == "voltou") &
    (df["dias_ate_retorno"].notna()) &
    (df["dias_ate_retorno"] <= 30),
    "churn_real_30d"
] = 0

# Target C: churn real 90d (churnou E nao voltou em 90 dias)
df["churn_real_90d"] = df["churn_original"].copy()
df.loc[
    (df["churn_original"] == 1) &
    (df["retorno_status"] == "voltou") &
    (df["dias_ate_retorno"].notna()) &
    (df["dias_ate_retorno"] <= 90),
    "churn_real_90d"
] = 0

# Filtrar recentes
df["contract_due_date"] = pd.to_datetime(df["contract_due_date"])
corte = pd.Timestamp.now() - pd.Timedelta(days=30)
df = df[df["contract_due_date"] < corte].copy()

n_total = len(df)
print(f"   Contratos: {n_total:,}")
print(f"   Churn original:  {df['churn_original'].sum():,} ({100*df['churn_original'].mean():.1f}%)")
print(f"   Churn real 30d:  {df['churn_real_30d'].sum():,} ({100*df['churn_real_30d'].mean():.1f}%)")
print(f"   Churn real 90d:  {df['churn_real_90d'].sum():,} ({100*df['churn_real_90d'].mean():.1f}%)")
print(f"   Removidos (voltaram 30d): {df['churn_original'].sum() - df['churn_real_30d'].sum():,}")
print(f"   Removidos (voltaram 90d): {df['churn_original'].sum() - df['churn_real_90d'].sum():,}")


# ═══════════════════════════════════════════════════════════════
# 2. FEATURES (mesmas do score v3)
# ═══════════════════════════════════════════════════════════════
print("\n2. Preparando features...")

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


# ═══════════════════════════════════════════════════════════════
# 3. TREINAR E COMPARAR
# ═══════════════════════════════════════════════════════════════
print("\n3. Treinando modelos...\n")

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
    print(f"   {label}: AUC = {auc_mean:.4f} (+/- {auc_std:.4f})  |  target rate = {100*y.mean():.1f}%")
    return auc_mean, auc_std

# Target A: original
auc_a, std_a = cv_xgb(X, df["churn_original"].values, XGB_PARAMS, "A: Churn original")

# Target B: real 30d
auc_b, std_b = cv_xgb(X, df["churn_real_30d"].values, XGB_PARAMS, "B: Churn real 30d (exclui quem volta em 30d)")

# Target C: real 90d
auc_c, std_c = cv_xgb(X, df["churn_real_90d"].values, XGB_PARAMS, "C: Churn real 90d (exclui quem volta em 90d)")


# ═══════════════════════════════════════════════════════════════
# 4. COMPARAR FAIXAS DE SCORE
# ═══════════════════════════════════════════════════════════════
print("\n4. Comparando separacao das faixas...\n")

for target_col, label in [
    ("churn_original", "A: Original"),
    ("churn_real_30d", "B: Real 30d"),
    ("churn_real_90d", "C: Real 90d"),
]:
    y = df[target_col].values
    dtrain = xgb.DMatrix(X, label=y)
    bst = xgb.train(XGB_PARAMS, dtrain, num_boost_round=200, verbose_eval=False)
    prob = bst.predict(dtrain)
    score = (1000 * (prob.max() - prob) / (prob.max() - prob.min())).clip(0, 1000).astype(int)

    bins = [-1, 200, 400, 600, 800, 1001]
    labels_faixa = ["CRITICO", "ALTO", "MEDIO", "BAIXO", "SEGURO"]
    faixa = pd.cut(score, bins=bins, labels=labels_faixa)

    print(f"   {label}:")
    rates = []
    for f in labels_faixa:
        mask = faixa == f
        n = mask.sum()
        if n < 10:
            continue
        cr = round(100 * y[mask].mean(), 1)
        rates.append(cr)
        bar = "█" * int(cr / 2)
        print(f"     {f:10s}  {cr:5.1f}%  {bar}  ({n:>7,})")
    if len(rates) >= 2:
        spread = max(rates) - min(rates)
        print(f"     SPREAD: {spread:.1f} p.p.\n")


# ═══════════════════════════════════════════════════════════════
# RESUMO
# ═══════════════════════════════════════════════════════════════
print(f"{'='*65}")
print("RESUMO")
print(f"{'='*65}")
print(f"   A: Original           AUC = {auc_a:.4f}  |  target = {100*df['churn_original'].mean():.1f}%")
print(f"   B: Real 30d           AUC = {auc_b:.4f}  |  target = {100*df['churn_real_30d'].mean():.1f}%  |  Δ = {auc_b-auc_a:+.4f}")
print(f"   C: Real 90d           AUC = {auc_c:.4f}  |  target = {100*df['churn_real_90d'].mean():.1f}%  |  Δ = {auc_c-auc_a:+.4f}")
print()
if auc_b > auc_a + 0.005:
    print("   CONCLUSAO: Redefinir target MELHORA o modelo — o win-back era ruido.")
elif auc_b < auc_a - 0.005:
    print("   CONCLUSAO: Redefinir target PIORA o modelo — quem volta em 30d tem perfil diferente.")
else:
    print("   CONCLUSAO: Sem diferenca significativa — o target nao e o limitador do AUC.")
