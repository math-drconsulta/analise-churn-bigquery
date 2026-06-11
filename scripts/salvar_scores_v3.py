"""
Salva os scores por contrato (LR demo + XGB tuned) pra uso na pagina 16.
Rode DEPOIS do treinar_score_v3_tuned.py.
Roda rapido — so aplica modelos ja treinados.
"""
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
import xgboost as xgb
import json
import warnings
warnings.filterwarnings("ignore")

SEED = 42

# Carregar e preparar (mesmo codigo do treinar)
df_demo = pd.read_csv("results/contratos_com_cpf.csv", dtype={"cpf": str})
df_exp = pd.read_csv("results/features_experiencia.csv")

df = df_demo.merge(
    df_exp[["contract_id", "qtd_profissionais", "qtd_especialidades",
            "nps_medio", "tempo_total_medio", "qtd_com_nps", "qtd_atendimentos",
            "nota_medico_media", "nota_atendimento_media"]],
    on="contract_id", how="inner"
)
df["churn"] = (df["churn_sn"] == "S").astype(int)
df["contract_due_date"] = pd.to_datetime(df["contract_due_date"])
corte = pd.Timestamp.now() - pd.Timedelta(days=30)
df = df[df["contract_due_date"] < corte].copy()

# Features
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

FEAT_DEMO = ["ciclo", "duracao", "cronico", "faixa_dep", "faixa_idade_cat", "canal_simples"]
FEAT_FULL = FEAT_DEMO + ["faixa_nps_cat", "faixa_tempo_cat", "rotatividade_cat"]
FEAT_NUM = ["prof_por_esp", "tempo_clinica_min", "nps_valor", "nota_medico_val", "nota_atend_val", "tem_atendimento", "qtd_atendimentos"]

def make_X(df_in, feat_cat, feat_num=None):
    X = pd.get_dummies(df_in[feat_cat], drop_first=True).astype(float)
    if feat_num:
        for c in feat_num:
            X[c] = df_in[c].fillna(0).astype(float)
    return X

y = df["churn"].values

# Score A: LR Demografico
X_a = make_X(df, FEAT_DEMO)
scaler_a = StandardScaler()
lr_a = LogisticRegression(C=0.5, max_iter=500, solver="lbfgs", random_state=SEED)
lr_a.fit(scaler_a.fit_transform(X_a), y)
# Reescalar LR tambem pra 0-1000
prob_lr = lr_a.predict_proba(scaler_a.transform(X_a))[:, 1]
prob_lr_min, prob_lr_max = prob_lr.min(), prob_lr.max()
df["score_lr"] = (1000 * (prob_lr_max - prob_lr) / (prob_lr_max - prob_lr_min)).clip(0, 1000).astype(int)

# Score C: XGBoost tuned
X_c = make_X(df, FEAT_FULL, FEAT_NUM)
try:
    with open("results/score_v3_xgb_params.json") as f:
        params = json.load(f)
except FileNotFoundError:
    params = {"objective": "binary:logistic", "eval_metric": "auc", "verbosity": 0,
              "max_depth": 4, "learning_rate": 0.08, "subsample": 0.8, "colsample_bytree": 0.8}

dtrain = xgb.DMatrix(X_c, label=y)
bst = xgb.train(params, dtrain, num_boost_round=300, verbose_eval=False)
# Reescalar pra 0-1000 usando min-max da probabilidade
prob_xgb = bst.predict(xgb.DMatrix(X_c))
prob_min, prob_max = prob_xgb.min(), prob_xgb.max()
# Inverter (prob alta = risco alto = score baixo) e escalar pra 0-1000
df["score_xgb"] = (1000 * (prob_max - prob_xgb) / (prob_max - prob_min)).clip(0, 1000).astype(int)

# Faixas
bins = [-1, 200, 400, 600, 800, 1001]
labels = ["CRITICO", "ALTO", "MEDIO", "BAIXO", "SEGURO"]
df["faixa_lr"] = pd.cut(df["score_lr"], bins=bins, labels=labels)
df["faixa_xgb"] = pd.cut(df["score_xgb"], bins=bins, labels=labels)

# Salvar
cols_out = [
    "contract_id", "ciclo", "duracao", "cronico", "faixa_dep", "faixa_idade_cat",
    "canal_simples", "faixa_nps_cat", "faixa_tempo_cat", "rotatividade_cat",
    "churn", "churn_sn",
    "score_lr", "faixa_lr", "score_xgb", "faixa_xgb",
    "nps_valor", "prof_por_esp", "tempo_clinica_min", "qtd_atendimentos",
]
df[cols_out].to_csv("results/score_v3_contratos.csv", index=False)
print(f"Salvo: results/score_v3_contratos.csv ({len(df):,} contratos)")
