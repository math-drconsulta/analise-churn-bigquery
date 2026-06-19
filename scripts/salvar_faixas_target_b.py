"""
Salva os scores e faixas (5 e 7) do Target B (churn real 30d) pra dashboard.
"""
import pandas as pd
import numpy as np
import xgboost as xgb
import warnings
warnings.filterwarnings("ignore")

SEED = 42

# Carregar e preparar (mesmo codigo)
df_demo = pd.read_csv("results/contratos_com_cpf.csv", dtype={"cpf": str})
df_exp = pd.read_csv("results/features_experiencia.csv")
df_wb = pd.read_csv("results/winback_voluntario.csv")

df = df_demo.merge(
    df_exp[["contract_id", "qtd_profissionais", "qtd_especialidades",
            "nps_medio", "tempo_total_medio", "qtd_com_nps", "qtd_atendimentos",
            "nota_medico_media", "nota_atendimento_media"]],
    on="contract_id", how="inner"
)
df_wb_cols = df_wb[["contract_id", "retorno_status", "dias_ate_retorno"]].copy()
df = df.merge(df_wb_cols, on="contract_id", how="left")

df["contract_due_date"] = pd.to_datetime(df["contract_due_date"])
corte = pd.Timestamp.now() - pd.Timedelta(days=30)
df = df[df["contract_due_date"] < corte].copy()

# Targets
df["churn_original"] = (df["churn_sn"] == "S").astype(int)
df["churn_real_30d"] = df["churn_original"].copy()
df.loc[
    (df["churn_original"] == 1) & (df["retorno_status"] == "voltou") &
    (df["dias_ate_retorno"].notna()) & (df["dias_ate_retorno"] <= 30),
    "churn_real_30d"
] = 0

# Features
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
FEAT_NUM = ["prof_por_esp", "tempo_clinica_min", "nps_valor", "nota_medico_val", "nota_atend_val", "tem_atendimento", "qtd_atendimentos"]

X = pd.get_dummies(df[FEAT_CAT], drop_first=True).astype(float)
for col in FEAT_NUM:
    X[col] = df[col].fillna(0).astype(float)

XGB_PARAMS = {"objective": "binary:logistic", "eval_metric": "auc", "verbosity": 0,
              "max_depth": 4, "learning_rate": 0.08, "subsample": 0.8, "colsample_bytree": 0.8}

# Treinar com target B
y = df["churn_real_30d"].values
dtrain = xgb.DMatrix(X, label=y)
bst = xgb.train(XGB_PARAMS, dtrain, num_boost_round=200, verbose_eval=False)
prob = bst.predict(dtrain)
score = (1000 * (prob.max() - prob) / (prob.max() - prob.min())).clip(0, 1000).astype(int)

# 5 faixas
BINS_5 = [-1, 200, 400, 600, 800, 1001]
LABELS_5 = ["CRITICO", "ALTO", "MEDIO", "BAIXO", "SEGURO"]

# 7 faixas
BINS_7 = [-1, 143, 286, 429, 571, 714, 857, 1001]
LABELS_7 = ["CRITICO", "MUITO ALTO", "ALTO", "MEDIO", "BAIXO", "MUITO BAIXO", "SEGURO"]

faixa_5 = pd.cut(score, bins=BINS_5, labels=LABELS_5)
faixa_7 = pd.cut(score, bins=BINS_7, labels=LABELS_7)

# Salvar faixas pra dashboard
resultados = []
for n_faixas, faixa, labels in [("5_faixas", faixa_5, LABELS_5), ("7_faixas", faixa_7, LABELS_7)]:
    for f in labels:
        mask = faixa == f
        n = int(mask.sum())
        if n == 0:
            continue
        ch = int(y[mask].sum())
        cr = round(100 * ch / n, 1)
        resultados.append({
            "layout": n_faixas, "faixa": f, "contratos": n,
            "churners": ch, "churn_rate": cr, "pct_base": round(100 * n / len(y), 1)
        })

pd.DataFrame(resultados).to_csv("results/score_v4_faixas.csv", index=False)
print(f"Salvo: results/score_v4_faixas.csv ({len(resultados)} linhas)")

# Salvar tambem o churn original por faixa (pra comparar)
resultados_orig = []
y_orig = df["churn_original"].values
for n_faixas, faixa, labels in [("5_faixas", faixa_5, LABELS_5), ("7_faixas", faixa_7, LABELS_7)]:
    for f in labels:
        mask = faixa == f
        n = int(mask.sum())
        if n == 0:
            continue
        ch = int(y_orig[mask].sum())
        cr = round(100 * ch / n, 1)
        resultados_orig.append({
            "layout": n_faixas, "faixa": f, "contratos": n,
            "churners": ch, "churn_rate": cr, "pct_base": round(100 * n / len(y_orig), 1)
        })

pd.DataFrame(resultados_orig).to_csv("results/score_v4_faixas_original.csv", index=False)
print(f"Salvo: results/score_v4_faixas_original.csv")
