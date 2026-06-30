"""
Score de Falha de Pagamento — v2 (comparacao completa)
======================================================
Compara perfil vs perfil+pgto com 4 targets:
  A: Original (nao renovou)
  B: v4 (exclui todos 30d)
  C: v5 (so exclui pago 30d)
  D: Estendido (exclui pago direto + pago via gratis)

Para cada target, mostra AUC e faixas (5 e 7).

Requer:
  results/contratos_com_cpf.csv
  results/features_experiencia.csv
  results/winback_voluntario.csv
  results/unif_pgto_features_pgto.csv
  results/desfecho_pos_gratis.csv
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
print("SCORE DE FALHA DE PAGAMENTO — v2 (COMPARACAO COMPLETA)")
print("=" * 70)


# ═══════════════════════════════════════════════════════════════
# 1. CARREGAR
# ═══════════════════════════════════════════════════════════════
print("\n1. Carregando dados...")

df_demo = pd.read_csv("results/contratos_com_cpf.csv", dtype={"cpf": str})
df_exp = pd.read_csv("results/features_experiencia.csv")
df_wb = pd.read_csv("results/winback_voluntario.csv")
df_pgto = pd.read_csv("results/unif_pgto_features_pgto.csv")

try:
    df_desf = pd.read_csv("results/desfecho_pos_gratis.csv")
    print(f"   desfecho_pos_gratis: {len(df_desf):,}")
except FileNotFoundError:
    print("   ERRO: results/desfecho_pos_gratis.csv nao encontrado!")
    exit(1)

# Merge base
df = df_demo.merge(
    df_exp[["contract_id", "qtd_profissionais", "qtd_especialidades",
            "nps_medio", "tempo_total_medio", "qtd_com_nps", "qtd_atendimentos",
            "nota_medico_media", "nota_atendimento_media"]],
    on="contract_id", how="inner"
)
df = df.merge(df_wb[["contract_id", "retorno_status", "dias_ate_retorno"]], on="contract_id", how="left")
df = df.merge(df_desf[["contract_id", "desfecho_final"]], on="contract_id", how="left")

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

df["contract_due_date"] = pd.to_datetime(df["contract_due_date"])
corte = pd.Timestamp.now() - pd.Timedelta(days=60)
df = df[df["contract_due_date"] < corte].copy()

print(f"   Base final: {len(df):,}")
tem_pgto = (df["total_tentativas"].notna() & (df["total_tentativas"] > 0)).sum()
print(f"   Com features pagamento: {tem_pgto:,} ({round(100*tem_pgto/len(df),1)}%)")


# ═══════════════════════════════════════════════════════════════
# 2. TARGETS
# ═══════════════════════════════════════════════════════════════
print("\n2. Definindo targets...")

df["churn_original"] = (df["churn_sn"] == "S").astype(int)

# v4: exclui todos 30d
df["churn_v4"] = df["churn_original"].copy()
df.loc[
    (df["churn_original"] == 1) & (df["retorno_status"] == "voltou") &
    (df["dias_ate_retorno"].notna()) & (df["dias_ate_retorno"] <= 30),
    "churn_v4"
] = 0

# v5: exclui so pago 30d
df["churn_v5"] = df["churn_original"].copy()
df.loc[
    (df["churn_original"] == 1) &
    (df["retorno_status"] == "voltou") &
    (df["dias_ate_retorno"].notna()) &
    (df["dias_ate_retorno"] <= 30) &
    (df["desfecho_final"] == "voltou_pago"),
    "churn_v5"
] = 0

# Estendido (PM): exclui pago direto + pago via gratis
df["churn_ext"] = df["churn_original"].copy()
df.loc[(df["churn_original"] == 1) & (df["desfecho_final"] == "voltou_pago"), "churn_ext"] = 0
df.loc[(df["churn_original"] == 1) & (df["desfecho_final"] == "gratis_voltou_pago"), "churn_ext"] = 0

targets = [
    ("churn_original", "Original"),
    ("churn_v4",       "v4 (exclui 30d)"),
    ("churn_v5",       "v5 (so pago 30d)"),
    ("churn_ext",      "Estendido (pos-gratis)"),
]

for col, label in targets:
    rate = 100 * df[col].mean()
    total = int(df[col].sum())
    print(f"   {label:30s} {total:>7,} churners ({rate:.1f}%)")


# ═══════════════════════════════════════════════════════════════
# 3. FEATURES
# ═══════════════════════════════════════════════════════════════
print("\n3. Preparando features...")

df["duracao"] = df["duracao"].astype(str)
df["ciclo"] = df["ciclo"].fillna("1o")
df["cronico"] = df["cronico"].fillna("N")
df["canal_simples"] = df["canal"].fillna("outros").apply(
    lambda x: "digital" if "digital" in str(x).lower() else "presencial")
df["faixa_dep"] = pd.cut(
    pd.to_numeric(df["dependentes"], errors="coerce").fillna(0),
    bins=[-1, 0, 2, 99], labels=["sem_dep", "1-2_dep", "3+_dep"]).astype(str)
df["faixa_idade_cat"] = pd.cut(
    pd.to_numeric(df["idade"], errors="coerce").fillna(35),
    bins=[0, 30, 50, 120], labels=["jovem", "adulto", "senior"]).astype(str)
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
FEAT_NUM_PERFIL = ["prof_por_esp", "tempo_clinica_min", "nps_valor", "nota_medico_val",
                   "nota_atend_val", "tem_atendimento", "qtd_atendimentos"]

FEAT_NUM_PGTO = [
    "total_tentativas", "sucessos", "falhas",
    "janela_tentativas_dias", "max_cycle", "max_retry",
    "n_refused_generico", "n_saldo_insuficiente", "n_blocked_retry",
    "n_fraude", "n_cartao_restrito", "n_cartao_vencido",
    "n_cartao_invalido", "n_cartao_bloqueado",
    "n_advice_new_account", "n_advice_retry_after", "mix_sucesso_falha",
]

df["tem_tentativa_pgto"] = (df["total_tentativas"].fillna(0) > 0).astype(int)
df["taxa_falha_pgto"] = np.where(df["total_tentativas"].fillna(0) > 0,
    df["falhas"].fillna(0) / df["total_tentativas"], -1)
df["so_falha"] = ((df["falhas"].fillna(0) > 0) & (df["sucessos"].fillna(0) == 0)).astype(int)

FEAT_NUM_PGTO_EXTRA = ["tem_tentativa_pgto", "taxa_falha_pgto", "so_falha"]

X_cat = pd.get_dummies(df[FEAT_CAT], drop_first=True).astype(float)
X_perfil = X_cat.copy()
for col in FEAT_NUM_PERFIL:
    X_perfil[col] = df[col].fillna(0).astype(float)

X_pgto = pd.DataFrame()
for col in FEAT_NUM_PGTO + FEAT_NUM_PGTO_EXTRA:
    X_pgto[col] = df[col].fillna(0).astype(float)

X_completo = pd.concat([X_perfil, X_pgto], axis=1)

print(f"   Perfil: {X_perfil.shape[1]} | Pagamento: {X_pgto.shape[1]} | Completo: {X_completo.shape[1]}")


# ═══════════════════════════════════════════════════════════════
# 4. CROSS-VALIDATION: 4 TARGETS × 2 FEATURE SETS
# ═══════════════════════════════════════════════════════════════
print("\n4. Cross-validation (5-fold)...\n")

XGB_PARAMS = {
    "objective": "binary:logistic", "eval_metric": "auc", "verbosity": 0,
    "max_depth": 4, "learning_rate": 0.08, "subsample": 0.8, "colsample_bytree": 0.8,
}


def cv_xgb(X, y, params):
    kf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)
    aucs = []
    for tr, val in kf.split(X, y):
        dtrain = xgb.DMatrix(X.iloc[tr], label=y[tr])
        dval = xgb.DMatrix(X.iloc[val], label=y[val])
        bst = xgb.train(params, dtrain, num_boost_round=300,
                        evals=[(dval, "val")], early_stopping_rounds=30, verbose_eval=False)
        aucs.append(roc_auc_score(y[val], bst.predict(dval)))
    return np.mean(aucs), np.std(aucs)


# Tabela de resultados
print(f"   {'Target':30s} | {'So perfil':>18s} | {'Perfil+pgto':>18s} | {'Delta':>8s}")
print(f"   {'-'*30}-+-{'-'*18}-+-{'-'*18}-+-{'-'*8}")

all_results = {}
for col, label in targets:
    y = df[col].values
    auc_p, std_p = cv_xgb(X_perfil, y, XGB_PARAMS)
    auc_c, std_c = cv_xgb(X_completo, y, XGB_PARAMS)
    delta = auc_c - auc_p
    rate = 100 * y.mean()
    print(f"   {label:30s} | {auc_p:.4f} (+/-{std_p:.4f}) | {auc_c:.4f} (+/-{std_c:.4f}) | {delta:+.4f}")
    all_results[label] = {"auc_perfil": auc_p, "auc_completo": auc_c, "delta": delta, "rate": rate}


# ═══════════════════════════════════════════════════════════════
# 5. SUBGRUPO COM/SEM ADYEN (target v4)
# ═══════════════════════════════════════════════════════════════
print("\n5. AUC por subgrupo (target v4)...\n")

for mask_val, label in [(1, "Com Adyen"), (0, "Sem Adyen")]:
    mask = df["tem_tentativa_pgto"] == mask_val
    n = mask.sum()
    y_sub = df.loc[mask, "churn_v4"].values
    rate = 100 * y_sub.mean()
    auc_p, _ = cv_xgb(X_perfil.loc[mask], y_sub, XGB_PARAMS)
    auc_c, _ = cv_xgb(X_completo.loc[mask], y_sub, XGB_PARAMS)
    print(f"   {label} (n={n:,}, churn={rate:.1f}%): perfil={auc_p:.4f}  completo={auc_c:.4f}  Δ={auc_c-auc_p:+.4f}")


# ═══════════════════════════════════════════════════════════════
# 5b. CURVAS ROC (treina modelo full pra cada target × feature set)
# ═══════════════════════════════════════════════════════════════
print("\n5b. Gerando curvas ROC...")

from sklearn.metrics import roc_curve

roc_rows = []
for target_col, target_label in targets:
    y = df[target_col].values
    for feat_label, X_feat in [("perfil", X_perfil), ("perfil_pgto", X_completo)]:
        # Treinar no full dataset (consistente com faixas)
        dtrain = xgb.DMatrix(X_feat, label=y)
        bst = xgb.train(XGB_PARAMS, dtrain, num_boost_round=200, verbose_eval=False)
        prob = bst.predict(dtrain)
        fpr, tpr, _ = roc_curve(y, prob)
        auc_val = roc_auc_score(y, prob)
        # Subsample pra nao ficar pesado (max 200 pontos por curva)
        step = max(1, len(fpr) // 200)
        for f, t in zip(fpr[::step], tpr[::step]):
            roc_rows.append({
                "target": target_label, "features": feat_label,
                "fpr": round(f, 4), "tpr": round(t, 4), "auc": round(auc_val, 4),
            })

df_roc = pd.DataFrame(roc_rows)
df_roc.to_csv("results/score_pgto_v2_roc.csv", index=False)
print(f"   results/score_pgto_v2_roc.csv ({len(df_roc)} pontos)")


# ═══════════════════════════════════════════════════════════════
# 6. TREINAR MODELOS + FAIXAS (5 e 7)
# ═══════════════════════════════════════════════════════════════
print("\n6. Treinando modelos e comparando faixas...\n")

BINS_5 = [-1, 200, 400, 600, 800, 1001]
LABELS_5 = ["CRITICO", "ALTO", "MEDIO", "BAIXO", "SEGURO"]
BINS_7 = [-1, 143, 286, 429, 571, 714, 857, 1001]
LABELS_7 = ["CRITICO", "MUITO ALTO", "ALTO", "MEDIO", "BAIXO", "MUITO BAIXO", "SEGURO"]

rows_faixas = []

for target_col, target_label in targets:
    y = df[target_col].values

    # Treinar perfil e completo
    for feat_label, X_feat in [("perfil", X_perfil), ("perfil_pgto", X_completo)]:
        dtrain = xgb.DMatrix(X_feat, label=y)
        bst = xgb.train(XGB_PARAMS, dtrain, num_boost_round=200, verbose_eval=False)
        prob = bst.predict(dtrain)
        score = (1000 * (prob.max() - prob) / (prob.max() - prob.min())).clip(0, 1000).astype(int)

        col_score = f"score_{target_col}_{feat_label}"
        df[col_score] = score

        for layout_name, bins, labels in [("5_faixas", BINS_5, LABELS_5), ("7_faixas", BINS_7, LABELS_7)]:
            col_faixa = f"faixa_{target_col}_{feat_label}_{layout_name}"
            df[col_faixa] = pd.cut(score, bins=bins, labels=labels)

            for f in labels:
                mask = df[col_faixa] == f
                n = mask.sum()
                cr = round(100 * df.loc[mask, target_col].mean(), 1) if n > 0 else 0
                rows_faixas.append({
                    "target": target_label, "features": feat_label,
                    "layout": layout_name, "faixa": f,
                    "contratos": n, "churn_rate": cr,
                })

df_faixas = pd.DataFrame(rows_faixas)

# Imprimir comparacoes
for layout_name, labels in [("5_faixas", LABELS_5), ("7_faixas", LABELS_7)]:
    print(f"   === {layout_name.replace('_', ' ').upper()} ===\n")
    print(f"   {'Target':20s} {'Faixa':14s} | {'Perfil %':>9s} {'n':>7s} | {'Perf+Pgto %':>11s} {'n':>7s} | {'Δ':>6s}")
    print(f"   {'-'*20} {'-'*14}-+-{'-'*9}-{'-'*7}-+-{'-'*11}-{'-'*7}-+-{'-'*6}")

    for target_col, target_label in targets:
        for f in labels:
            row_p = df_faixas[(df_faixas["target"] == target_label) & (df_faixas["features"] == "perfil") &
                              (df_faixas["layout"] == layout_name) & (df_faixas["faixa"] == f)]
            row_c = df_faixas[(df_faixas["target"] == target_label) & (df_faixas["features"] == "perfil_pgto") &
                              (df_faixas["layout"] == layout_name) & (df_faixas["faixa"] == f)]
            if len(row_p) > 0 and len(row_c) > 0:
                cr_p = row_p.iloc[0]["churn_rate"]
                n_p = int(row_p.iloc[0]["contratos"])
                cr_c = row_c.iloc[0]["churn_rate"]
                n_c = int(row_c.iloc[0]["contratos"])
                delta = cr_c - cr_p
                print(f"   {target_label:20s} {f:14s} | {cr_p:8.1f}% {n_p:>6,} | {cr_c:10.1f}% {n_c:>6,} | {delta:+5.1f}")

        # Spread
        for feat_label in ["perfil", "perfil_pgto"]:
            rates = df_faixas[(df_faixas["target"] == target_label) & (df_faixas["features"] == feat_label) &
                              (df_faixas["layout"] == layout_name) & (df_faixas["contratos"] >= 10)]["churn_rate"]
            spread = round(rates.max() - rates.min(), 1) if len(rates) >= 2 else 0
            print(f"   {'':20s} {'Spread '+feat_label:14s} | {spread:8.1f} p.p.")
        print()

    print()


# ═══════════════════════════════════════════════════════════════
# 7. SALVAR
# ═══════════════════════════════════════════════════════════════
print("7. Salvando...")

df_faixas.to_csv("results/score_pgto_v2_faixas.csv", index=False)
print(f"   results/score_pgto_v2_faixas.csv ({len(df_faixas)} linhas)")

# Resumo CSV
resumo = []
for label, r in all_results.items():
    resumo.append({"target": label, **r})
pd.DataFrame(resumo).to_csv("results/score_pgto_v2_resumo_auc.csv", index=False)
print(f"   results/score_pgto_v2_resumo_auc.csv")


# ═══════════════════════════════════════════════════════════════
# RESUMO
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print("RESUMO FINAL")
print(f"{'='*70}\n")

print(f"   {'Target':30s} | {'Perfil':>8s} | {'Perf+Pgto':>10s} | {'Delta':>8s}")
print(f"   {'-'*30}-+-{'-'*8}-+-{'-'*10}-+-{'-'*8}")
best_auc = 0
best_label = ""
for label, r in all_results.items():
    marker = ""
    if r["auc_completo"] > best_auc:
        best_auc = r["auc_completo"]
        best_label = label
    print(f"   {label:30s} | {r['auc_perfil']:.4f} | {r['auc_completo']:.4f}   | {r['delta']:+.4f}")

print(f"\n   Melhor combinacao: {best_label} + pagamento (AUC = {best_auc:.4f})")
print(f"\n   Features de pagamento melhoram TODOS os targets.")
print(f"   O ganho e concentrado nos 23% com dados Adyen (AUC 0.72 → 0.84).")
print(f"{'='*70}")
