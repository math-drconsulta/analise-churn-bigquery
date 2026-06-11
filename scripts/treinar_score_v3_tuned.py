"""
Score v3 com tuning de hiperparametros via Optuna.

Treina 3 modelos com busca de hiperparametros:
  A. Logistica Demografica (baseline)
  B. Logistica Demo + Experiencia
  C. XGBoost Demo + Experiencia (com Optuna)
  D. LightGBM se disponivel

Cada modelo: 5-fold StratifiedKFold, metrica = AUC.
XGBoost: 60 trials Optuna com TPE sampler + MedianPruner.
"""
import pandas as pd
import numpy as np
import json
import warnings
from pathlib import Path
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
import xgboost as xgb

warnings.filterwarnings("ignore")

N_FOLDS = 5
SEED = 42

print("=" * 65)
print("SCORE V3 — TUNING COMPLETO")
print("=" * 65)

# ═══════════════════════════════════════════════════════════════
# 1. DADOS
# ═══════════════════════════════════════════════════════════════
print("\n1. Carregando dados...")

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

print(f"   N: {len(df):,} | Churn: {100*df['churn'].mean():.1f}%")

# ═══════════════════════════════════════════════════════════════
# 2. FEATURES
# ═══════════════════════════════════════════════════════════════
print("\n2. Preparando features...")

df["duracao"] = df["duracao"].astype(str)
df["ciclo"] = df["ciclo"].fillna("1o")
df["cronico"] = df["cronico"].fillna("N")
df["canal"] = df["canal"].fillna("outros")
df["canal_simples"] = df["canal"].apply(
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

# Experiencia
df["prof_por_esp"] = np.where(
    df["qtd_especialidades"] > 0,
    df["qtd_profissionais"] / df["qtd_especialidades"], 0
)
df["tempo_clinica_min"] = df["tempo_total_medio"].fillna(0) / 60
df["nps_valor"] = df["nps_medio"].fillna(-1)
df["tem_atendimento"] = (df["qtd_atendimentos"] > 0).astype(int)
df["nota_medico_val"] = df["nota_medico_media"].fillna(-1)
df["nota_atend_val"] = df["nota_atendimento_media"].fillna(-1)

# NPS categorica
df["faixa_nps_cat"] = "sem_nps"
df.loc[(df["nps_valor"] >= 0) & (df["nps_valor"] <= 6), "faixa_nps_cat"] = "detrator"
df.loc[(df["nps_valor"] > 6) & (df["nps_valor"] <= 8), "faixa_nps_cat"] = "neutro"
df.loc[df["nps_valor"] > 8, "faixa_nps_cat"] = "promotor"

# Tempo categorica
df["faixa_tempo_cat"] = "sem_atend"
df.loc[(df["tempo_clinica_min"] > 0) & (df["tempo_clinica_min"] < 15), "faixa_tempo_cat"] = "curto"
df.loc[(df["tempo_clinica_min"] >= 15) & (df["tempo_clinica_min"] < 30), "faixa_tempo_cat"] = "medio"
df.loc[df["tempo_clinica_min"] >= 30, "faixa_tempo_cat"] = "longo"

# Rotatividade categorica
df["rotatividade_cat"] = "sem_atend"
df.loc[(df["qtd_atendimentos"] > 0) & (df["prof_por_esp"] < 1.5), "rotatividade_cat"] = "continuidade"
df.loc[(df["qtd_atendimentos"] > 0) & (df["prof_por_esp"] >= 1.5) & (df["prof_por_esp"] < 2), "rotatividade_cat"] = "moderada"
df.loc[(df["qtd_atendimentos"] > 0) & (df["prof_por_esp"] >= 2), "rotatividade_cat"] = "alta"

# Sets
FEAT_DEMO = ["ciclo", "duracao", "cronico", "faixa_dep", "faixa_idade_cat", "canal_simples"]
FEAT_FULL = FEAT_DEMO + ["faixa_nps_cat", "faixa_tempo_cat", "rotatividade_cat"]

# Pra XGBoost: usar numericas tambem
FEAT_XGB_NUM = [
    "prof_por_esp", "tempo_clinica_min", "nps_valor",
    "nota_medico_val", "nota_atend_val", "tem_atendimento",
    "qtd_atendimentos",
]

def make_X(df_in, feat_cat, feat_num=None):
    X = pd.get_dummies(df_in[feat_cat], drop_first=True).astype(float)
    if feat_num:
        for col in feat_num:
            X[col] = df_in[col].fillna(0).astype(float)
    return X

y = df["churn"].values


# ═══════════════════════════════════════════════════════════════
# 3. CV HELPER
# ═══════════════════════════════════════════════════════════════

def cv_logistic(X, y, C=1.0):
    kf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)
    aucs, briers = [], []
    for tr, val in kf.split(X, y):
        scaler = StandardScaler()
        X_tr = scaler.fit_transform(X.iloc[tr])
        X_val = scaler.transform(X.iloc[val])
        model = LogisticRegression(C=C, max_iter=500, solver="lbfgs", random_state=SEED)
        model.fit(X_tr, y[tr])
        p = model.predict_proba(X_val)[:, 1]
        aucs.append(roc_auc_score(y[val], p))
        briers.append(brier_score_loss(y[val], p))
    return np.mean(aucs), np.std(aucs), np.mean(briers)


def cv_xgb(X, y, params):
    kf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)
    aucs = []
    for tr, val in kf.split(X, y):
        dtrain = xgb.DMatrix(X.iloc[tr], label=y[tr])
        dval = xgb.DMatrix(X.iloc[val], label=y[val])
        bst = xgb.train(
            params, dtrain, num_boost_round=500,
            evals=[(dval, "val")], early_stopping_rounds=30,
            verbose_eval=False,
        )
        p = bst.predict(dval)
        aucs.append(roc_auc_score(y[val], p))
    return np.mean(aucs), np.std(aucs)


# ═══════════════════════════════════════════════════════════════
# 4. MODELO A: LOGISTICA DEMOGRAFICA
# ═══════════════════════════════════════════════════════════════
print("\n3. Treinando modelos...\n")

X_a = make_X(df, FEAT_DEMO)

# Tuning do C (regularizacao)
best_c_a, best_auc_a = 1.0, 0
for c in [0.01, 0.1, 0.5, 1.0, 5.0, 10.0]:
    auc, _, _ = cv_logistic(X_a, y, C=c)
    if auc > best_auc_a:
        best_c_a, best_auc_a = c, auc

auc_a, std_a, brier_a = cv_logistic(X_a, y, C=best_c_a)
print(f"   A: Logistica Demografica:  AUC = {auc_a:.4f} (+/- {std_a:.4f})  C={best_c_a}  Brier={brier_a:.4f}")


# ═══════════════════════════════════════════════════════════════
# 5. MODELO B: LOGISTICA DEMO + EXPERIENCIA
# ═══════════════════════════════════════════════════════════════
X_b = make_X(df, FEAT_FULL)

best_c_b, best_auc_b = 1.0, 0
for c in [0.01, 0.1, 0.5, 1.0, 5.0, 10.0]:
    auc, _, _ = cv_logistic(X_b, y, C=c)
    if auc > best_auc_b:
        best_c_b, best_auc_b = c, auc

auc_b, std_b, brier_b = cv_logistic(X_b, y, C=best_c_b)
print(f"   B: Logistica Demo+Exp:     AUC = {auc_b:.4f} (+/- {std_b:.4f})  C={best_c_b}  Brier={brier_b:.4f}")


# ═══════════════════════════════════════════════════════════════
# 6. MODELO C: XGBOOST COM OPTUNA
# ═══════════════════════════════════════════════════════════════
print("\n   Tunando XGBoost com Optuna (60 trials)...")

X_c = make_X(df, FEAT_FULL, FEAT_XGB_NUM)

try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial):
        params = {
            "objective": "binary:logistic",
            "eval_metric": "auc",
            "verbosity": 0,
            "max_depth": trial.suggest_int("max_depth", 3, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 20),
            "gamma": trial.suggest_float("gamma", 0, 5),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-4, 10, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-4, 10, log=True),
        }
        auc, _ = cv_xgb(X_c, y, params)
        return auc

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=SEED),
        pruner=optuna.pruners.MedianPruner(n_warmup_steps=10),
    )
    study.optimize(objective, n_trials=60, show_progress_bar=False)

    best_params_xgb = study.best_params
    best_params_xgb.update({
        "objective": "binary:logistic",
        "eval_metric": "auc",
        "verbosity": 0,
    })

    auc_c, std_c = cv_xgb(X_c, y, best_params_xgb)
    print(f"   C: XGBoost Optuna:         AUC = {auc_c:.4f} (+/- {std_c:.4f})")
    print(f"      Best params: {json.dumps({k: round(v, 4) if isinstance(v, float) else v for k, v in study.best_params.items()})}")

    # Salvar params
    with open("results/score_v3_xgb_params.json", "w") as f:
        json.dump(best_params_xgb, f, indent=2)

except ImportError:
    print("   Optuna nao disponivel — tunando XGBoost manualmente...")
    configs = [
        {"max_depth": 3, "learning_rate": 0.05, "subsample": 0.8, "colsample_bytree": 0.8},
        {"max_depth": 4, "learning_rate": 0.08, "subsample": 0.8, "colsample_bytree": 0.8},
        {"max_depth": 5, "learning_rate": 0.08, "subsample": 0.7, "colsample_bytree": 0.7},
        {"max_depth": 6, "learning_rate": 0.05, "subsample": 0.8, "colsample_bytree": 0.8},
        {"max_depth": 4, "learning_rate": 0.03, "subsample": 0.9, "colsample_bytree": 0.9},
        {"max_depth": 5, "learning_rate": 0.1, "subsample": 0.8, "colsample_bytree": 0.7, "min_child_weight": 5},
        {"max_depth": 3, "learning_rate": 0.08, "subsample": 0.9, "colsample_bytree": 0.8, "min_child_weight": 10},
        {"max_depth": 7, "learning_rate": 0.05, "subsample": 0.7, "colsample_bytree": 0.6, "reg_alpha": 1, "reg_lambda": 5},
    ]
    best_auc_manual = 0
    best_cfg = configs[0]
    for cfg in configs:
        params = {"objective": "binary:logistic", "eval_metric": "auc", "verbosity": 0}
        params.update(cfg)
        auc, _ = cv_xgb(X_c, y, params)
        if auc > best_auc_manual:
            best_auc_manual = auc
            best_cfg = cfg
        print(f"     depth={cfg.get('max_depth')} lr={cfg.get('learning_rate')} → AUC={auc:.4f}")

    best_params_xgb = {"objective": "binary:logistic", "eval_metric": "auc", "verbosity": 0}
    best_params_xgb.update(best_cfg)
    auc_c, std_c = cv_xgb(X_c, y, best_params_xgb)
    print(f"\n   C: XGBoost (manual):       AUC = {auc_c:.4f} (+/- {std_c:.4f})")


# ═══════════════════════════════════════════════════════════════
# 7. MODELO D: XGBOOST SO DEMOGRAFICO (pra comparar justo)
# ═══════════════════════════════════════════════════════════════
print("\n   Comparacao justa: XGBoost so demografico...")
X_d = make_X(df, FEAT_DEMO)
auc_d, std_d = cv_xgb(X_d, y, best_params_xgb)
print(f"   D: XGBoost Demo only:      AUC = {auc_d:.4f} (+/- {std_d:.4f})")


# ═══════════════════════════════════════════════════════════════
# 8. GERAR SCORES E FAIXAS DO MELHOR MODELO
# ═══════════════════════════════════════════════════════════════
print("\n4. Gerando scores com XGBoost tuned...")

# Treinar modelo final em toda a base
dtrain_full = xgb.DMatrix(X_c, label=y)
bst_final = xgb.train(best_params_xgb, dtrain_full, num_boost_round=300, verbose_eval=False)
df["prob_xgb"] = bst_final.predict(xgb.DMatrix(X_c))
df["score_xgb"] = (1000 * (1 - df["prob_xgb"])).clip(0, 1000).astype(int)

# Faixas
bins = [-1, 200, 400, 600, 800, 1001]
labels_faixa = ["CRITICO", "ALTO", "MEDIO", "BAIXO", "SEGURO"]
df["faixa_xgb"] = pd.cut(df["score_xgb"], bins=bins, labels=labels_faixa)

# Comparar tambem com logistica demografica
scaler = StandardScaler()
X_a_scaled = scaler.fit_transform(X_a)
lr_a = LogisticRegression(C=best_c_a, max_iter=500, solver="lbfgs", random_state=SEED)
lr_a.fit(X_a_scaled, y)
df["prob_lr_a"] = lr_a.predict_proba(X_a_scaled)[:, 1]
df["score_lr_a"] = (1000 * (1 - df["prob_lr_a"])).clip(0, 1000).astype(int)
df["faixa_lr_a"] = pd.cut(df["score_lr_a"], bins=bins, labels=labels_faixa)

print("\n5. Comparacao de faixas:\n")

for nome, col_faixa in [
    ("Logistica Demografica (A)", "faixa_lr_a"),
    ("XGBoost Demo+Exp tuned (C)", "faixa_xgb"),
]:
    print(f"   {nome}:")
    grp = df.groupby(col_faixa, observed=True).agg(
        n=("churn", "count"), ch=("churn", "sum")
    ).reindex(labels_faixa).reset_index()
    grp.columns = ["faixa", "n", "ch"]
    grp = grp.dropna(subset=["n"])
    grp["cr"] = (100 * grp["ch"] / grp["n"]).round(1)
    for _, r in grp.iterrows():
        if r["n"] > 0:
            bar = "█" * int(r["cr"] / 2)
            print(f"     {r['faixa']:10s}  {r['cr']:5.1f}%  {bar}  ({int(r['n']):>7,})")
    valid = grp[grp["n"] >= 30]
    if len(valid) >= 2:
        spread = valid["cr"].max() - valid["cr"].min()
        print(f"     SPREAD: {spread:.1f} p.p.\n")
    else:
        print()

# Feature importance XGBoost
print("6. Feature importance (XGBoost):\n")
importance = bst_final.get_score(importance_type="gain")
imp_df = pd.DataFrame([
    {"feature": k, "gain": v} for k, v in importance.items()
]).sort_values("gain", ascending=False)

for _, r in imp_df.head(15).iterrows():
    bar = "█" * int(r["gain"] / imp_df["gain"].max() * 30)
    print(f"   {r['feature']:35s}  {bar}")


# ═══════════════════════════════════════════════════════════════
# 9. SALVAR
# ═══════════════════════════════════════════════════════════════
print("\n7. Salvando...")

metricas = pd.DataFrame([
    {"modelo": "A: Logistica Demo", "auc_cv": round(auc_a, 4), "brier": round(brier_a, 4), "n_features": X_a.shape[1]},
    {"modelo": "B: Logistica Demo+Exp", "auc_cv": round(auc_b, 4), "brier": round(brier_b, 4), "n_features": X_b.shape[1]},
    {"modelo": "C: XGBoost Demo+Exp tuned", "auc_cv": round(auc_c, 4), "n_features": X_c.shape[1]},
    {"modelo": "D: XGBoost Demo only", "auc_cv": round(auc_d, 4), "n_features": X_d.shape[1]},
])
metricas.to_csv("results/score_v3_metricas.csv", index=False)
imp_df.to_csv("results/score_v3_importance.csv", index=False)

# Faixas
faixas = []
for nome, col in [("LR_Demo", "faixa_lr_a"), ("XGB_Demo+Exp", "faixa_xgb")]:
    grp = df.groupby(col, observed=True).agg(n=("churn", "count"), ch=("churn", "sum")).reindex(labels_faixa).reset_index()
    grp.columns = ["faixa", "n", "ch"]
    grp["cr"] = (100 * grp["ch"] / grp["n"]).round(1)
    grp["modelo"] = nome
    faixas.append(grp)
pd.concat(faixas).to_csv("results/score_v3_faixas.csv", index=False)

print("   score_v3_metricas.csv")
print("   score_v3_importance.csv")
print("   score_v3_faixas.csv")
print("   score_v3_xgb_params.json")

# ═══════════════════════════════════════════════════════════════
# RESUMO
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*65}")
print("RESUMO FINAL")
print(f"{'='*65}")
print(f"   A: Logistica Demografica:     AUC = {auc_a:.4f}")
print(f"   B: Logistica Demo+Exp:        AUC = {auc_b:.4f}  (melhora: {auc_b-auc_a:+.4f})")
print(f"   C: XGBoost Demo+Exp tuned:    AUC = {auc_c:.4f}  (melhora: {auc_c-auc_a:+.4f})")
print(f"   D: XGBoost Demo only:         AUC = {auc_d:.4f}  (melhora: {auc_d-auc_a:+.4f})")
print(f"\n   Ganho da experiencia (C vs D): {auc_c-auc_d:+.4f}")
print(f"   Ganho do XGB vs Logistica:     {auc_c-auc_b:+.4f}")
