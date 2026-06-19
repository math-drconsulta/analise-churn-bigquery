"""
Testa se adicionar especialidades ao score v4 melhora o AUC.
Compara:
  A: Score v4 atual (demo + experiencia, target real 30d)
  B: Score v4 + especialidades (flags de uso por especialidade)
  C: Score v4 + diversidade (qtd_especialidades_usadas)
  D: Score v4 + especialidades + diversidade (tudo)
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
print("TESTE: ESPECIALIDADES NO SCORE V4")
print("=" * 65)

# ═══════════════════════════════════════════════════════════════
# DADOS
# ═══════════════════════════════════════════════════════════════
df_demo = pd.read_csv("results/contratos_com_cpf.csv", dtype={"cpf": str})
df_exp = pd.read_csv("results/features_experiencia.csv")
df_wb = pd.read_csv("results/winback_voluntario.csv")
df_esp = pd.read_csv("results/especialidades_por_faixa.csv")

# Merge tudo
df = df_demo.merge(
    df_exp[["contract_id", "qtd_profissionais", "qtd_especialidades",
            "nps_medio", "tempo_total_medio", "qtd_com_nps", "qtd_atendimentos",
            "nota_medico_media", "nota_atendimento_media"]],
    on="contract_id", how="inner"
)
df = df.merge(
    df_esp[["contract_id", "churn_real_30d",
            "usou_clinica_medica", "usou_tele", "usou_exames",
            "usou_ginecologia", "usou_cardiologia", "usou_dermatologia",
            "usou_endocrinologia", "usou_gastro", "usou_oftalmo",
            "usou_ortopedia", "usou_pediatria", "usou_psiquiatria",
            "usou_urologia", "usou_neurologia",
            "qtd_especialidades_usadas", "total_atendimentos"]],
    on="contract_id", how="inner"
)

df["contract_due_date"] = pd.to_datetime(df["contract_due_date"])
corte = pd.Timestamp.now() - pd.Timedelta(days=30)
df = df[df["contract_due_date"] < corte].copy()

y = df["churn_real_30d"].values
print(f"\nN: {len(df):,} | Churn real: {100*y.mean():.1f}%")

# ═══════════════════════════════════════════════════════════════
# FEATURES
# ═══════════════════════════════════════════════════════════════
df["duracao"] = df["duracao"].astype(str)
df["ciclo"] = df["ciclo"].fillna("1o")
df["cronico"] = df["cronico"].fillna("N")
df["canal_simples"] = df["canal"].fillna("outros").apply(lambda x: "digital" if "digital" in str(x).lower() else "presencial")
df["faixa_dep"] = pd.cut(pd.to_numeric(df["dependentes"], errors="coerce").fillna(0), bins=[-1,0,2,99], labels=["sem_dep","1-2_dep","3+_dep"]).astype(str)
df["faixa_idade_cat"] = pd.cut(pd.to_numeric(df["idade"], errors="coerce").fillna(35), bins=[0,30,50,120], labels=["jovem","adulto","senior"]).astype(str)
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

# Sets de features
FEAT_CAT = ["ciclo", "duracao", "cronico", "faixa_dep", "faixa_idade_cat", "canal_simples", "faixa_nps_cat", "faixa_tempo_cat", "rotatividade_cat"]
FEAT_NUM_BASE = ["prof_por_esp", "tempo_clinica_min", "nps_valor", "nota_medico_val", "nota_atend_val", "tem_atendimento", "qtd_atendimentos"]

FEAT_ESPECIALIDADES = [
    "usou_clinica_medica", "usou_tele", "usou_exames",
    "usou_ginecologia", "usou_cardiologia", "usou_dermatologia",
    "usou_endocrinologia", "usou_gastro", "usou_oftalmo",
    "usou_ortopedia", "usou_psiquiatria", "usou_urologia", "usou_neurologia",
]
FEAT_DIVERSIDADE = ["qtd_especialidades_usadas", "total_atendimentos"]

def make_X(feat_cat, feat_num):
    X = pd.get_dummies(df[feat_cat], drop_first=True).astype(float)
    for c in feat_num:
        X[c] = df[c].fillna(0).astype(float)
    return X

XGB_PARAMS = {"objective": "binary:logistic", "eval_metric": "auc", "verbosity": 0,
              "max_depth": 4, "learning_rate": 0.08, "subsample": 0.8, "colsample_bytree": 0.8}

# ═══════════════════════════════════════════════════════════════
# TREINAR E COMPARAR
# ═══════════════════════════════════════════════════════════════
def cv_xgb(X, y, label):
    kf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)
    aucs = []
    for tr, val in kf.split(X, y):
        dtrain = xgb.DMatrix(X.iloc[tr], label=y[tr])
        dval = xgb.DMatrix(X.iloc[val], label=y[val])
        bst = xgb.train(XGB_PARAMS, dtrain, num_boost_round=300,
                        evals=[(dval, "val")], early_stopping_rounds=30, verbose_eval=False)
        aucs.append(roc_auc_score(y[val], bst.predict(dval)))
    auc = np.mean(aucs)
    std = np.std(aucs)
    print(f"   {label}: AUC = {auc:.4f} (+/- {std:.4f})  |  {X.shape[1]} features")
    return auc

print("\nTreinando modelos...\n")

# A: Score v4 atual
X_a = make_X(FEAT_CAT, FEAT_NUM_BASE)
auc_a = cv_xgb(X_a, y, "A: Score v4 (demo + experiencia)")

# B: + especialidades
X_b = make_X(FEAT_CAT, FEAT_NUM_BASE + FEAT_ESPECIALIDADES)
auc_b = cv_xgb(X_b, y, "B: + especialidades (flags)")

# C: + diversidade
X_c = make_X(FEAT_CAT, FEAT_NUM_BASE + FEAT_DIVERSIDADE)
auc_c = cv_xgb(X_c, y, "C: + diversidade (qtd esp. + total atend.)")

# D: + tudo
X_d = make_X(FEAT_CAT, FEAT_NUM_BASE + FEAT_ESPECIALIDADES + FEAT_DIVERSIDADE)
auc_d = cv_xgb(X_d, y, "D: + especialidades + diversidade (tudo)")

# ═══════════════════════════════════════════════════════════════
# FAIXAS DO MELHOR MODELO
# ═══════════════════════════════════════════════════════════════
melhor_label = "D"
melhor_auc = auc_d
X_melhor = X_d
if auc_b > auc_d:
    melhor_label = "B"
    melhor_auc = auc_b
    X_melhor = X_b

print(f"\nMelhor modelo: {melhor_label} (AUC = {melhor_auc:.4f})")
print(f"\nGerando faixas do melhor modelo...\n")

dtrain = xgb.DMatrix(X_melhor, label=y)
bst = xgb.train(XGB_PARAMS, dtrain, num_boost_round=200, verbose_eval=False)
prob = bst.predict(dtrain)
score = (1000 * (prob.max() - prob) / (prob.max() - prob.min())).clip(0, 1000).astype(int)

BINS_7 = [-1, 143, 286, 429, 571, 714, 857, 1001]
LABELS_7 = ["CRITICO", "MUITO ALTO", "ALTO", "MEDIO", "BAIXO", "MUITO BAIXO", "SEGURO"]
faixa = pd.cut(score, bins=BINS_7, labels=LABELS_7)

for f in LABELS_7:
    mask = faixa == f
    n = mask.sum()
    if n == 0:
        continue
    cr = round(100 * y[mask].mean(), 1)
    bar = "█" * int(cr / 2)
    print(f"  {f:15s}  {cr:5.1f}%  {bar}  ({n:>7,} = {100*n/len(y):.1f}%)")

valid = [(f, round(100*y[faixa==f].mean(),1)) for f in LABELS_7 if (faixa==f).sum() >= 30]
if len(valid) >= 2:
    spread = max(v[1] for v in valid) - min(v[1] for v in valid)
    print(f"\n  SPREAD: {spread:.1f} p.p.")

# Feature importance
print(f"\nTop 15 features (gain):\n")
importance = bst.get_score(importance_type="gain")
imp_sorted = sorted(importance.items(), key=lambda x: -x[1])[:15]
for feat, gain in imp_sorted:
    bar = "█" * int(gain / imp_sorted[0][1] * 30)
    print(f"  {feat:40s}  {bar}")

# ═══════════════════════════════════════════════════════════════
# RESUMO
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*65}")
print("RESUMO")
print(f"{'='*65}")
print(f"  A: Score v4 atual:             AUC = {auc_a:.4f}")
print(f"  B: + especialidades:           AUC = {auc_b:.4f}  (Δ = {auc_b-auc_a:+.4f})")
print(f"  C: + diversidade:              AUC = {auc_c:.4f}  (Δ = {auc_c-auc_a:+.4f})")
print(f"  D: + tudo:                     AUC = {auc_d:.4f}  (Δ = {auc_d-auc_a:+.4f})")
