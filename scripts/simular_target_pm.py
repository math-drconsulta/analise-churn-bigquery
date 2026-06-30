"""
Simulacao: Target v4 vs v5 vs Proposta PM (Growth)

Proposta PM: "so considerar churn depois que o periodo do gratis acabar.
Se migrou pro gratis e depois voltou pro pago → nao e churn."

Targets comparados:
  v4:  exclui TODOS que voltam em 30d (incluindo migracoes pro gratis)
  v5:  exclui so quem voltou PAGO em 30d (gratis continua como churn)
  PM:  exclui quem voltou pago diretamente + quem voltou pago apos gratis

Requer:
  results/contratos_com_cpf.csv
  results/features_experiencia.csv
  results/winback_voluntario.csv
  results/desfecho_pos_gratis.csv  (rodar queries/desfecho_pos_gratis.sql)
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
print("SIMULACAO: TARGET V4 vs V5 vs PROPOSTA PM (GROWTH)")
print("=" * 70)

# ═══════════════════════════════════════════════════════════════
# 1. CARREGAR
# ═══════════════════════════════════════════════════════════════
print("\n1. Carregando dados...")

df_demo = pd.read_csv("results/contratos_com_cpf.csv", dtype={"cpf": str})
df_exp = pd.read_csv("results/features_experiencia.csv")
df_wb = pd.read_csv("results/winback_voluntario.csv")

try:
    df_desf = pd.read_csv("results/desfecho_pos_gratis.csv")
    print(f"   desfecho_pos_gratis.csv: {len(df_desf):,} contratos")
    print(f"   Desfechos: {df_desf['desfecho_final'].value_counts().to_dict()}")
except FileNotFoundError:
    print("\n   ERRO: results/desfecho_pos_gratis.csv nao encontrado!")
    print("   Rode a query: queries/desfecho_pos_gratis.sql")
    print("   Salve o resultado em: results/desfecho_pos_gratis.csv")
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
df = df.merge(df_desf[["contract_id", "desfecho_final"]], on="contract_id", how="left")

df["contract_due_date"] = pd.to_datetime(df["contract_due_date"])
corte = pd.Timestamp.now() - pd.Timedelta(days=60)
df = df[df["contract_due_date"] < corte].copy()

print(f"   Base final: {len(df):,} contratos")


# ═══════════════════════════════════════════════════════════════
# 2. TARGETS
# ═══════════════════════════════════════════════════════════════
print("\n2. Definindo targets...")

# A: original — nao renovou = churn
df["churn_original"] = (df["churn_sn"] == "S").astype(int)

# B: v4 — exclui todos que voltam em 30d
df["churn_v4"] = df["churn_original"].copy()
df.loc[
    (df["churn_original"] == 1) & (df["retorno_status"] == "voltou") &
    (df["dias_ate_retorno"].notna()) & (df["dias_ate_retorno"] <= 30),
    "churn_v4"
] = 0

# C: v5 — exclui so quem voltou PAGO em 30d
df["churn_v5"] = df["churn_original"].copy()
df.loc[
    (df["churn_original"] == 1) &
    (df["retorno_status"] == "voltou") &
    (df["dias_ate_retorno"].notna()) &
    (df["dias_ate_retorno"] <= 30) &
    (df["desfecho_final"] == "voltou_pago"),
    "churn_v5"
] = 0

# D: PM — exclui quem voltou pago (direto OU via gratis)
df["churn_pm"] = df["churn_original"].copy()
# Quem voltou pago diretamente → nao churn
df.loc[
    (df["churn_original"] == 1) &
    (df["desfecho_final"] == "voltou_pago"),
    "churn_pm"
] = 0
# Quem migrou gratis E depois voltou pago → nao churn
df.loc[
    (df["churn_original"] == 1) &
    (df["desfecho_final"] == "gratis_voltou_pago"),
    "churn_pm"
] = 0
# Quem migrou gratis e saiu → churn (mantido como 1)
# Quem saiu de vez → churn (mantido como 1)

n = len(df)
print()
for col, label in [
    ("churn_original", "A: Original (nao renovou)"),
    ("churn_v4",       "B: v4 (exclui todos 30d)"),
    ("churn_v5",       "C: v5 (so exclui pago 30d)"),
    ("churn_pm",       "D: PM (exclui pago direto + pago via gratis)"),
]:
    total = int(df[col].sum())
    rate = 100 * df[col].mean()
    print(f"   {label:50s} {total:>7,} churners ({rate:.1f}%)")


# ═══════════════════════════════════════════════════════════════
# 3. DETALHE: DE ONDE VEM A DIFERENCA
# ═══════════════════════════════════════════════════════════════
print("\n3. Composicao dos targets (so churners originais)...")

churners = df[df["churn_original"] == 1].copy()
print(f"\n   Total churners originais: {len(churners):,}")
print(f"   Desfecho final:")
for d, cnt in churners["desfecho_final"].value_counts().items():
    pct = 100 * cnt / len(churners)
    v4_val = "nao churn" if d in ["voltou_pago"] else "?"
    v5_val = "nao churn" if d in ["voltou_pago"] else "churn"
    pm_val = "nao churn" if d in ["voltou_pago", "gratis_voltou_pago"] else "churn"

    # v4 depends on timing, not desfecho
    print(f"     {d:30s} {cnt:>7,} ({pct:5.1f}%)")

print()
print("   Como cada target trata os desfechos:")
print(f"   {'Desfecho':30s} {'v4':>10s} {'v5':>10s} {'PM':>10s}")
print(f"   {'-'*30} {'-'*10} {'-'*10} {'-'*10}")
mapping = {
    "saiu_de_vez":          ("CHURN",     "CHURN",     "CHURN"),
    "voltou_pago":          ("nao churn*","nao churn", "nao churn"),
    "gratis_saiu":          ("nao churn*","CHURN",     "CHURN"),
    "gratis_voltou_pago":   ("nao churn*","CHURN",     "nao churn"),
}
for desf, (t_v4, t_v5, t_pm) in mapping.items():
    mask = churners["desfecho_final"] == desf
    n_desf = mask.sum()
    if n_desf > 0:
        print(f"   {desf:30s} {t_v4:>10s} {t_v5:>10s} {t_pm:>10s}   (n={n_desf:,})")

print()
print("   *v4 usa janela de 30 dias, nao desfecho. Maioria das migracoes gratis")
print("    cai dentro dos 30d, entao sao excluidas do churn no v4.")


# ═══════════════════════════════════════════════════════════════
# 4. FEATURES (identicas ao v4/v5)
# ═══════════════════════════════════════════════════════════════
print("\n4. Preparando features...")

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
FEAT_NUM = [
    "prof_por_esp", "tempo_clinica_min", "nps_valor", "nota_medico_val",
    "nota_atend_val", "tem_atendimento", "qtd_atendimentos",
]

X = pd.get_dummies(df[FEAT_CAT], drop_first=True).astype(float)
for col in FEAT_NUM:
    X[col] = df[col].fillna(0).astype(float)

print(f"   Features: {X.shape[1]}")
print(f"   Contratos: {len(X):,}")


# ═══════════════════════════════════════════════════════════════
# 5. CROSS-VALIDATION: COMPARAR TODOS OS TARGETS
# ═══════════════════════════════════════════════════════════════
print("\n5. Cross-validation (5-fold)...\n")

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
    print(f"   {label:50s} AUC = {auc_mean:.4f} (+/- {auc_std:.4f})  rate = {rate:.1f}%")
    return auc_mean


results = {}
for col, label in [
    ("churn_original", "A: Original (nao renovou)"),
    ("churn_v4",       "B: v4 (exclui todos 30d)"),
    ("churn_v5",       "C: v5 (so exclui pago 30d)"),
    ("churn_pm",       "D: PM (exclui pago direto + via gratis)"),
]:
    results[label] = cv_xgb(X, df[col].values, XGB_PARAMS, label)


# ═══════════════════════════════════════════════════════════════
# 6. TREINAR MODELOS FINAIS + FAIXAS (v4, v5, PM)
# ═══════════════════════════════════════════════════════════════
print("\n6. Treinando modelos finais (v4, v5, PM)...")

BINS_5 = [-1, 200, 400, 600, 800, 1001]
LABELS_5 = ["CRITICO", "ALTO", "MEDIO", "BAIXO", "SEGURO"]
BINS_7 = [-1, 143, 286, 429, 571, 714, 857, 1001]
LABELS_7 = ["CRITICO", "MUITO ALTO", "ALTO", "MEDIO", "BAIXO", "MUITO BAIXO", "SEGURO"]


def treinar_modelo(X, y_col, nome):
    y = df[y_col].values
    dtrain = xgb.DMatrix(X, label=y)
    bst = xgb.train(XGB_PARAMS, dtrain, num_boost_round=200, verbose_eval=False)
    prob = bst.predict(dtrain)
    score = (1000 * (prob.max() - prob) / (prob.max() - prob.min())).clip(0, 1000).astype(int)
    df[f"score_{nome}"] = score
    df[f"faixa_5_{nome}"] = pd.cut(score, bins=BINS_5, labels=LABELS_5)
    df[f"faixa_7_{nome}"] = pd.cut(score, bins=BINS_7, labels=LABELS_7)
    return bst


bst_v4 = treinar_modelo(X, "churn_v4", "v4")
bst_v5 = treinar_modelo(X, "churn_v5", "v5")
bst_pm = treinar_modelo(X, "churn_pm", "pm")


# ═══════════════════════════════════════════════════════════════
# 7. COMPARAR FAIXAS LADO A LADO (5 e 7 faixas)
# ═══════════════════════════════════════════════════════════════

rows_faixas_all = []

for layout_name, labels_list, bins_list, faixa_prefix in [
    ("5_faixas", LABELS_5, BINS_5, "faixa_5"),
    ("7_faixas", LABELS_7, BINS_7, "faixa_7"),
]:
    print(f"\n7. Comparacao de faixas — {layout_name.replace('_', ' ')}...\n")

    print(f"   {'Faixa':14s} | {'v4 churn%':>10s} {'v4 n':>8s} | {'v5 churn%':>10s} {'v5 n':>8s} | {'PM churn%':>10s} {'PM n':>8s}")
    print(f"   {'-'*14}-+-{'-'*10}-{'-'*8}-+-{'-'*10}-{'-'*8}-+-{'-'*10}-{'-'*8}")

    for f in labels_list:
        results_row = {"layout": layout_name, "faixa": f}
        line_parts = [f"   {f:14s} |"]

        for nome, target_col in [("v4", "churn_v4"), ("v5", "churn_v5"), ("pm", "churn_pm")]:
            mask = df[f"{faixa_prefix}_{nome}"] == f
            n = mask.sum()
            cr = round(100 * df.loc[mask, target_col].mean(), 1) if n > 0 else 0
            line_parts.append(f" {cr:9.1f}% {n:>7,} |")
            results_row[f"contratos_{nome}"] = n
            results_row[f"churn_rate_{nome}"] = cr

        print("".join(line_parts))
        rows_faixas_all.append(results_row)

    # Spreads
    print()
    for nome, target_col in [("v4", "churn_v4"), ("v5", "churn_v5"), ("pm", "churn_pm")]:
        rates = []
        for f in labels_list:
            mask = df[f"{faixa_prefix}_{nome}"] == f
            if mask.sum() >= 10:
                rates.append(round(100 * df.loc[mask, target_col].mean(), 1))
        spread = max(rates) - min(rates) if len(rates) >= 2 else 0
        print(f"   Spread {nome}: {spread:.1f} p.p.")

# Salvar faixas
df_faixas = pd.DataFrame(rows_faixas_all)
df_faixas.to_csv("results/comparacao_v4_v5_pm_faixas.csv", index=False)


# ═══════════════════════════════════════════════════════════════
# 8. FEATURE IMPORTANCE COMPARADA
# ═══════════════════════════════════════════════════════════════
print("\n8. Top 10 features por modelo...\n")

for nome, bst in [("v4", bst_v4), ("v5", bst_v5), ("PM", bst_pm)]:
    imp = bst.get_score(importance_type="gain")
    top = sorted(imp.items(), key=lambda x: -x[1])[:10]
    print(f"   {nome}:")
    for feat, gain in top:
        print(f"     {feat:35s} {gain:>10.1f}")
    print()


# ═══════════════════════════════════════════════════════════════
# 9. SALVAR CONTRATOS
# ═══════════════════════════════════════════════════════════════
print("9. Salvando resultados...")

cols_out = [
    "contract_id", "churn_original", "churn_v4", "churn_v5", "churn_pm",
    "desfecho_final", "score_v4", "score_v5", "score_pm",
    "faixa_5_v4", "faixa_5_v5", "faixa_5_pm",
    "faixa_7_v4", "faixa_7_v5", "faixa_7_pm",
]
df[cols_out].to_csv("results/comparacao_v4_v5_pm_contratos.csv", index=False)
print(f"   results/comparacao_v4_v5_pm_contratos.csv ({len(df):,} contratos)")
print(f"   results/comparacao_v4_v5_pm_faixas.csv ({len(df_faixas)} linhas)")


# ═══════════════════════════════════════════════════════════════
# RESUMO FINAL
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print("RESUMO FINAL")
print(f"{'='*70}\n")

print("   Definicao dos targets:")
print("   v4:  churn = nao renovou, EXCETO se voltou (qualquer tipo) em 30 dias")
print("   v5:  churn = nao renovou, EXCETO se voltou PAGO em 30 dias")
print("   PM:  churn = nao renovou, EXCETO se voltou pago (direto OU via gratis)")
print()

print("   Resultados (AUC 5-fold CV):")
for label, auc in results.items():
    delta = auc - results["A: Original (nao renovou)"]
    marker = " ◄ MELHOR" if auc == max(results.values()) else ""
    print(f"   {label:50s} AUC = {auc:.4f}  Δ = {delta:+.4f}{marker}")

print()
print("   Diferenca conceitual:")
print("   ┌─────────────────────────────────────────────────────────────────┐")
print("   │ Desfecho               │  v4        │  v5        │  PM         │")
print("   ├─────────────────────────┼────────────┼────────────┼─────────────┤")
print("   │ saiu_de_vez             │  CHURN     │  CHURN     │  CHURN      │")
print("   │ voltou_pago (direto)    │  nao churn │  nao churn │  nao churn  │")
print("   │ gratis → saiu           │  nao churn*│  CHURN     │  CHURN      │")
print("   │ gratis → voltou pago    │  nao churn*│  CHURN     │  nao churn  │")
print("   └─────────────────────────┴────────────┴────────────┴─────────────┘")
print("   *v4 exclui pela janela de 30d (maioria das migracoes cai dentro)")
print()
print("   O target PM fica ENTRE v4 e v5:")
print("   - Concorda com v5 que gratis→saiu e churn")
print("   - Concorda com v4 que gratis→voltou_pago nao e churn")
print("   - Mas espera o desfecho real (2+ meses) em vez de decidir em 30d")
print(f"\n{'='*70}")
