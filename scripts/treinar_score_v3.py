"""
Treina o Score de Churn v3 — modelo calibrado com dados reais.

Compara 3 versoes:
  A. Demografico (7 vars WLS originais)
  B. Demografico + Experiencia (7 vars + rotatividade + NPS + tempo)
  C. XGBoost (todas as features — teto de AUC)

Saida:
  - results/score_v3_metricas.csv      (AUC, KS, Brier de cada modelo)
  - results/score_v3_coeficientes.csv  (coeficientes da regressao logistica)
  - results/score_v3_faixas.csv        (churn por faixa de score — pra comparar com WLS)
  - results/score_v3_comparacao.csv    (antes vs depois por faixa)
"""
import pandas as pd
import numpy as np
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.preprocessing import OneHotEncoder
import statsmodels.api as sm
import warnings
warnings.filterwarnings("ignore")

print("=" * 65)
print("TREINAMENTO DO SCORE V3")
print("=" * 65)

# ═══════════════════════════════════════════════════════════════
# 1. CARREGAR E MERGEAR
# ═══════════════════════════════════════════════════════════════
print("\n1. Carregando dados...")

df_demo = pd.read_csv("results/contratos_com_cpf.csv", dtype={"cpf": str})
df_exp = pd.read_csv("results/features_experiencia.csv")

# Merge por contract_id
df = df_demo.merge(
    df_exp[["contract_id", "qtd_profissionais", "qtd_especialidades",
            "nps_medio", "tempo_total_medio", "qtd_com_nps", "qtd_atendimentos"]],
    on="contract_id", how="inner"
)

# Usar churn do contratos_com_cpf (que tem a definição corrigida)
df["churn"] = (df["churn_sn"] == "S").astype(int)

# Filtrar contratos recentes (excluir ultimos 30 dias)
df["contract_due_date"] = pd.to_datetime(df["contract_due_date"])
corte = pd.Timestamp.now() - pd.Timedelta(days=30)
df = df[df["contract_due_date"] < corte].copy()

print(f"   Contratos apos merge e filtro: {len(df):,}")
print(f"   Churn: {100*df['churn'].mean():.1f}%")
print(f"   Com atendimento: {(df['qtd_atendimentos'] > 0).sum():,} ({100*(df['qtd_atendimentos'] > 0).mean():.1f}%)")
print(f"   Com NPS: {(df['qtd_com_nps'] > 0).sum():,} ({100*(df['qtd_com_nps'] > 0).mean():.1f}%)")


# ═══════════════════════════════════════════════════════════════
# 2. PREPARAR FEATURES
# ═══════════════════════════════════════════════════════════════
print("\n2. Preparando features...")

# Demograficas (categoricas → dummies)
df["duracao"] = df["duracao"].astype(str)
df["ciclo"] = df["ciclo"].fillna("1o")
df["cronico"] = df["cronico"].fillna("N")
df["canal"] = df["canal"].fillna("outros")

df["faixa_dep"] = pd.cut(
    pd.to_numeric(df["dependentes"], errors="coerce").fillna(0),
    bins=[-1, 0, 2, 99], labels=["sem_dep", "1-2_dep", "3+_dep"]
).astype(str)

df["faixa_idade_cat"] = pd.cut(
    pd.to_numeric(df["idade"], errors="coerce").fillna(35),
    bins=[0, 30, 50, 120], labels=["jovem", "adulto", "senior"]
).astype(str)

# Canal simplificado
df["canal_simples"] = df["canal"].apply(
    lambda x: "digital" if "digital" in str(x).lower() else "presencial"
)

# Experiencia (numericas)
df["prof_por_esp"] = np.where(
    df["qtd_especialidades"] > 0,
    df["qtd_profissionais"] / df["qtd_especialidades"],
    0
)
df["rotatividade_alta"] = (df["prof_por_esp"] >= 2).astype(int)
df["nps_preenchido"] = (df["qtd_com_nps"] > 0).astype(int)
df["nps_valor"] = df["nps_medio"].fillna(-1)  # -1 = sem NPS
df["tempo_clinica_min"] = df["tempo_total_medio"].fillna(0) / 60
df["tem_atendimento"] = (df["qtd_atendimentos"] > 0).astype(int)

# ── Features set A: so demograficas ──
FEATURES_A = ["ciclo", "duracao", "cronico", "faixa_dep", "faixa_idade_cat", "canal_simples"]

# ── Features set B: demograficas + experiencia ──
FEATURES_B_CAT = FEATURES_A.copy()
FEATURES_B_NUM = ["rotatividade_alta", "nps_preenchido", "tem_atendimento"]

# NPS como categorica (sem nps / detrator / neutro / promotor)
df["faixa_nps_cat"] = "sem_nps"
df.loc[(df["nps_valor"] >= 0) & (df["nps_valor"] <= 6), "faixa_nps_cat"] = "detrator"
df.loc[(df["nps_valor"] > 6) & (df["nps_valor"] <= 8), "faixa_nps_cat"] = "neutro"
df.loc[df["nps_valor"] > 8, "faixa_nps_cat"] = "promotor"

# Tempo como categorica
df["faixa_tempo_cat"] = "sem_atend"
df.loc[(df["tempo_clinica_min"] > 0) & (df["tempo_clinica_min"] < 15), "faixa_tempo_cat"] = "curto"
df.loc[(df["tempo_clinica_min"] >= 15) & (df["tempo_clinica_min"] < 30), "faixa_tempo_cat"] = "medio"
df.loc[df["tempo_clinica_min"] >= 30, "faixa_tempo_cat"] = "longo"

# Rotatividade como categorica
df["rotatividade_cat"] = "sem_atend"
df.loc[(df["qtd_atendimentos"] > 0) & (df["prof_por_esp"] < 1.5), "rotatividade_cat"] = "continuidade"
df.loc[(df["qtd_atendimentos"] > 0) & (df["prof_por_esp"] >= 1.5) & (df["prof_por_esp"] < 2), "rotatividade_cat"] = "moderada"
df.loc[(df["qtd_atendimentos"] > 0) & (df["prof_por_esp"] >= 2), "rotatividade_cat"] = "alta"

FEATURES_B_FULL = FEATURES_A + ["faixa_nps_cat", "faixa_tempo_cat", "rotatividade_cat"]


# ═══════════════════════════════════════════════════════════════
# 3. FUNCAO DE TREINAMENTO E AVALIACAO
# ═══════════════════════════════════════════════════════════════

def preparar_X(df_in, features_cat):
    """Cria dummies pra features categoricas, removendo a primeira de cada (referencia)."""
    return pd.get_dummies(df_in[features_cat], drop_first=True).astype(float)


def treinar_e_avaliar(df_in, features_cat, nome):
    """Treina regressao logistica com CV e retorna metricas."""
    X = preparar_X(df_in, features_cat)
    y = df_in["churn"].values

    # Cross-validation
    kf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    aucs, briers = [], []

    for train_idx, val_idx in kf.split(X, y):
        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y[train_idx], y[val_idx]

        X_train_c = sm.add_constant(X_train)
        X_val_c = sm.add_constant(X_val)

        model = sm.Logit(y_train, X_train_c).fit(disp=0, maxiter=100)
        y_pred = model.predict(X_val_c)

        auc = roc_auc_score(y_val, y_pred)
        brier = brier_score_loss(y_val, y_pred)

        aucs.append(auc)
        briers.append(brier)

    # Modelo final (em toda a base pra pegar coeficientes)
    X_full = sm.add_constant(preparar_X(df_in, features_cat))
    model_final = sm.Logit(y, X_full).fit(disp=0, maxiter=100)

    return {
        "nome": nome,
        "auc_cv": round(np.mean(aucs), 4),
        "auc_std": round(np.std(aucs), 4),
        "brier_cv": round(np.mean(briers), 4),
        "n": len(df_in),
        "n_features": X.shape[1],
        "model": model_final,
        "X_cols": list(X.columns),
    }


# ═══════════════════════════════════════════════════════════════
# 4. TREINAR MODELOS
# ═══════════════════════════════════════════════════════════════
print("\n3. Treinando modelos...\n")

# Modelo A: so demograficas
res_a = treinar_e_avaliar(df, FEATURES_A, "A: Demografico (7 vars)")
print(f"   {res_a['nome']}: AUC = {res_a['auc_cv']} (+/- {res_a['auc_std']}), {res_a['n_features']} features")

# Modelo B: demograficas + experiencia
res_b = treinar_e_avaliar(df, FEATURES_B_FULL, "B: Demografico + Experiencia")
print(f"   {res_b['nome']}: AUC = {res_b['auc_cv']} (+/- {res_b['auc_std']}), {res_b['n_features']} features")

# Modelo C: XGBoost (teto)
try:
    import xgboost as xgb

    X_xgb = preparar_X(df, FEATURES_B_FULL)
    y_xgb = df["churn"].values

    kf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    aucs_xgb = []
    for train_idx, val_idx in kf.split(X_xgb, y_xgb):
        dtrain = xgb.DMatrix(X_xgb.iloc[train_idx], label=y_xgb[train_idx])
        dval = xgb.DMatrix(X_xgb.iloc[val_idx], label=y_xgb[val_idx])
        params = {"objective": "binary:logistic", "eval_metric": "auc",
                  "max_depth": 5, "learning_rate": 0.08, "verbosity": 0}
        bst = xgb.train(params, dtrain, num_boost_round=200,
                        evals=[(dval, "val")], early_stopping_rounds=30, verbose_eval=False)
        y_pred_xgb = bst.predict(dval)
        aucs_xgb.append(roc_auc_score(y_xgb[val_idx], y_pred_xgb))

    auc_xgb = round(np.mean(aucs_xgb), 4)
    print(f"   C: XGBoost: AUC = {auc_xgb} (+/- {round(np.std(aucs_xgb), 4)})")
except ImportError:
    auc_xgb = None
    print("   C: XGBoost nao disponivel")


# ═══════════════════════════════════════════════════════════════
# 5. COEFICIENTES DO MODELO B
# ═══════════════════════════════════════════════════════════════
print("\n4. Coeficientes do modelo B (Demografico + Experiencia):\n")

model_b = res_b["model"]
coefs = pd.DataFrame({
    "variavel": model_b.params.index,
    "coef": model_b.params.values,
    "se": model_b.bse.values,
    "z": model_b.tvalues.values,
    "p": model_b.pvalues.values,
    "odds_ratio": np.exp(model_b.params.values),
})
coefs["sig"] = coefs["p"].apply(
    lambda p: "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "n.s."
)
coefs["coef"] = coefs["coef"].round(4)
coefs["se"] = coefs["se"].round(4)
coefs["odds_ratio"] = coefs["odds_ratio"].round(4)

for _, r in coefs.iterrows():
    print(f"   {r['variavel']:35s}  coef={r['coef']:+.4f}  OR={r['odds_ratio']:.3f}  {r['sig']}")


# ═══════════════════════════════════════════════════════════════
# 6. GERAR SCORES E FAIXAS
# ═══════════════════════════════════════════════════════════════
print("\n5. Gerando scores e faixas...")

# Score A (demografico)
X_a = sm.add_constant(preparar_X(df, FEATURES_A))
df["prob_a"] = res_a["model"].predict(X_a)
df["score_a"] = (1000 * (1 - df["prob_a"])).clip(0, 1000).astype(int)

# Score B (demografico + experiencia)
X_b = sm.add_constant(preparar_X(df, FEATURES_B_FULL))
df["prob_b"] = res_b["model"].predict(X_b)
df["score_b"] = (1000 * (1 - df["prob_b"])).clip(0, 1000).astype(int)

# Faixas
bins = [-1, 200, 400, 600, 800, 1001]
labels = ["CRITICO", "ALTO", "MEDIO", "BAIXO", "SEGURO"]
df["faixa_a"] = pd.cut(df["score_a"], bins=bins, labels=labels)
df["faixa_b"] = pd.cut(df["score_b"], bins=bins, labels=labels)


# ═══════════════════════════════════════════════════════════════
# 7. COMPARAR FAIXAS
# ═══════════════════════════════════════════════════════════════
print("\n6. Comparacao de faixas:\n")

for nome_score, col_faixa, col_score in [
    ("A: Demografico", "faixa_a", "score_a"),
    ("B: Demo + Experiencia", "faixa_b", "score_b"),
]:
    print(f"   {nome_score}:")
    grp = df.groupby(col_faixa, observed=True).agg(
        n=("churn", "count"), ch=("churn", "sum")
    ).reindex(labels).reset_index()
    grp.columns = ["faixa", "n", "ch"]
    grp["cr"] = (100 * grp["ch"] / grp["n"]).round(1)

    for _, r in grp.iterrows():
        if r["n"] > 0:
            bar = "█" * int(r["cr"] / 2)
            print(f"     {r['faixa']:10s}  {r['cr']:5.1f}%  {bar}  ({int(r['n']):>7,})")

    spread = grp["cr"].max() - grp["cr"].min()
    print(f"     SPREAD: {spread:.1f} p.p.\n")


# ═══════════════════════════════════════════════════════════════
# 8. SALVAR RESULTADOS
# ═══════════════════════════════════════════════════════════════
print("7. Salvando resultados...")

# Metricas
metricas = pd.DataFrame([
    {"modelo": res_a["nome"], "auc_cv": res_a["auc_cv"], "auc_std": res_a["auc_std"],
     "brier_cv": res_a["brier_cv"], "n_features": res_a["n_features"], "n": res_a["n"]},
    {"modelo": res_b["nome"], "auc_cv": res_b["auc_cv"], "auc_std": res_b["auc_std"],
     "brier_cv": res_b["brier_cv"], "n_features": res_b["n_features"], "n": res_b["n"]},
])
if auc_xgb:
    metricas = pd.concat([metricas, pd.DataFrame([
        {"modelo": "C: XGBoost", "auc_cv": auc_xgb, "n_features": res_b["n_features"], "n": len(df)}
    ])], ignore_index=True)
metricas.to_csv("results/score_v3_metricas.csv", index=False)

# Coeficientes
coefs.to_csv("results/score_v3_coeficientes.csv", index=False)

# Faixas
faixas_list = []
for nome_score, col_faixa in [("Demografico", "faixa_a"), ("Demo+Experiencia", "faixa_b")]:
    grp = df.groupby(col_faixa, observed=True).agg(
        n=("churn", "count"), ch=("churn", "sum")
    ).reindex(labels).reset_index()
    grp.columns = ["faixa", "n", "ch"]
    grp["cr"] = (100 * grp["ch"] / grp["n"]).round(1)
    grp["modelo"] = nome_score
    faixas_list.append(grp)
pd.concat(faixas_list).to_csv("results/score_v3_faixas.csv", index=False)

print("   score_v3_metricas.csv")
print("   score_v3_coeficientes.csv")
print("   score_v3_faixas.csv")


# ═══════════════════════════════════════════════════════════════
# RESUMO
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*65}")
print("RESUMO")
print(f"{'='*65}")
print(f"   Modelo A (Demografico):       AUC = {res_a['auc_cv']}")
print(f"   Modelo B (Demo+Experiencia):  AUC = {res_b['auc_cv']}")
if auc_xgb:
    print(f"   Modelo C (XGBoost):           AUC = {auc_xgb}")
print(f"   Melhora A→B:                  {res_b['auc_cv'] - res_a['auc_cv']:+.4f}")
if auc_xgb:
    print(f"   Melhora A→C:                  {auc_xgb - res_a['auc_cv']:+.4f}")
