"""
Testa TME_total + TMA_total (2 features em vez de 8).
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

# Carregar
df_demo = pd.read_csv("results/contratos_com_cpf.csv", dtype={"cpf": str})
df_exp = pd.read_csv("results/features_experiencia.csv")
df_wb = pd.read_csv("results/winback_voluntario.csv")
df_tempos = pd.read_csv("results/tempos_jornada.csv")

df = df_demo.merge(
    df_exp[["contract_id", "qtd_profissionais", "qtd_especialidades",
            "nps_medio", "tempo_total_medio", "qtd_com_nps", "qtd_atendimentos",
            "nota_medico_media", "nota_atendimento_media"]],
    on="contract_id", how="inner"
)
df = df.merge(
    df_tempos[["contract_id", "tme_total_medio", "tma_recepcao_medio",
               "tma_preconsulta_medio", "tma_consulta_medio", "tma_posconsulta_medio"]],
    on="contract_id", how="left"
)
df_wb_cols = df_wb[["contract_id", "retorno_status", "dias_ate_retorno"]].copy()
df = df.merge(df_wb_cols, on="contract_id", how="left")

df["contract_due_date"] = pd.to_datetime(df["contract_due_date"])
df = df[df["contract_due_date"] < pd.Timestamp.now() - pd.Timedelta(days=30)].copy()

# Target
df["churn_original"] = (df["churn_sn"] == "S").astype(int)
df["churn_real_30d"] = df["churn_original"].copy()
df.loc[
    (df["churn_original"] == 1) & (df["retorno_status"] == "voltou") &
    (df["dias_ate_retorno"].notna()) & (df["dias_ate_retorno"] <= 30),
    "churn_real_30d"
] = 0

y = df["churn_real_30d"].values

# TMA total = soma das etapas de atendimento
df["tme_total_min"] = df["tme_total_medio"].fillna(0) / 60
df["tma_total_min"] = (
    df["tma_recepcao_medio"].fillna(0) +
    df["tma_preconsulta_medio"].fillna(0) +
    df["tma_consulta_medio"].fillna(0) +
    df["tma_posconsulta_medio"].fillna(0)
) / 60

# Features base
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

FEAT_CAT = ["ciclo", "duracao", "cronico", "faixa_dep", "faixa_idade_cat", "canal_simples", "faixa_nps_cat", "faixa_tempo_cat", "rotatividade_cat"]
FEAT_NUM_BASE = ["prof_por_esp", "tempo_clinica_min", "nps_valor", "nota_medico_val", "nota_atend_val", "tem_atendimento", "qtd_atendimentos"]

def make_X(feat_cat, feat_num):
    X = pd.get_dummies(df[feat_cat], drop_first=True).astype(float)
    for c in feat_num:
        X[c] = df[c].fillna(0).astype(float)
    return X

XGB_PARAMS = {"objective": "binary:logistic", "eval_metric": "auc", "verbosity": 0,
              "max_depth": 4, "learning_rate": 0.08, "subsample": 0.8, "colsample_bytree": 0.8}

def cv_xgb(X, y, label):
    kf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)
    aucs = []
    for tr, val in kf.split(X, y):
        dtrain = xgb.DMatrix(X.iloc[tr], label=y[tr])
        dval = xgb.DMatrix(X.iloc[val], label=y[val])
        bst = xgb.train(XGB_PARAMS, dtrain, num_boost_round=300,
                        evals=[(dval, "val")], early_stopping_rounds=30, verbose_eval=False)
        aucs.append(roc_auc_score(y[val], bst.predict(dval)))
    print(f"   {label}: AUC = {np.mean(aucs):.4f} (+/- {np.std(aucs):.4f})  |  {X.shape[1]} features")
    return np.mean(aucs)

print(f"\nN: {len(df):,} | Churn real: {100*y.mean():.1f}%\n")

auc_a = cv_xgb(make_X(FEAT_CAT, FEAT_NUM_BASE), y, "A: Score v4 (tempo_total apenas)")
auc_b = cv_xgb(make_X(FEAT_CAT, FEAT_NUM_BASE + ["tme_total_min", "tma_total_min"]), y, "B: + TME_total + TMA_total (2 features)")
auc_c = cv_xgb(make_X(FEAT_CAT, [f for f in FEAT_NUM_BASE if f != "tempo_clinica_min"] + ["tme_total_min", "tma_total_min"]), y, "C: TME+TMA substituindo tempo_total")

print(f"\n  A: {auc_a:.4f}")
print(f"  B: {auc_b:.4f}  (Δ = {auc_b-auc_a:+.4f})")
print(f"  C: {auc_c:.4f}  (Δ = {auc_c-auc_a:+.4f})")
