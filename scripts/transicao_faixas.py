"""
Estudo de transicao entre faixas: quais features mudar pra mover
contratos pra faixas melhores.

Para cada faixa (ALTO, MEDIO, BAIXO):
  1. Pega todos os contratos
  2. Para cada feature acionavel, simula a mudanca pro melhor valor
  3. Re-preve o score com XGBoost
  4. Conta quantos migram pra faixa melhor
  5. Rankeia por impacto

Saida: results/transicao_faixas.csv
"""
import pandas as pd
import numpy as np
import xgboost as xgb
import warnings
warnings.filterwarnings("ignore")

SEED = 42

print("=" * 70)
print("ESTUDO DE TRANSICAO ENTRE FAIXAS")
print("=" * 70)

# ═══════════════════════════════════════════════════════════════
# DADOS E MODELO (mesmo do score v4)
# ═══════════════════════════════════════════════════════════════
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
df = df[df["contract_due_date"] < pd.Timestamp.now() - pd.Timedelta(days=30)].copy()

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

def make_X(data):
    X = pd.get_dummies(data[FEAT_CAT], drop_first=True).astype(float)
    for c in FEAT_NUM:
        X[c] = data[c].fillna(0).astype(float)
    return X

XGB_PARAMS = {"objective": "binary:logistic", "eval_metric": "auc", "verbosity": 0,
              "max_depth": 4, "learning_rate": 0.08, "subsample": 0.8, "colsample_bytree": 0.8}

# Treinar modelo
y = df["churn_real_30d"].values
X_original = make_X(df)
feature_columns = X_original.columns.tolist()

dtrain = xgb.DMatrix(X_original, label=y)
bst = xgb.train(XGB_PARAMS, dtrain, num_boost_round=200, verbose_eval=False)

# Score e faixa original
prob_orig = bst.predict(dtrain)
prob_min, prob_max = prob_orig.min(), prob_orig.max()
score_orig = (1000 * (prob_max - prob_orig) / (prob_max - prob_min)).clip(0, 1000).astype(int)

BINS_5 = [-1, 200, 400, 600, 800, 1001]
LABELS_5 = ["CRITICO", "ALTO", "MEDIO", "BAIXO", "SEGURO"]

BINS_7 = [-1, 143, 286, 429, 571, 714, 857, 1001]
LABELS_7 = ["CRITICO", "MUITO ALTO", "ALTO", "MEDIO", "BAIXO", "MUITO BAIXO", "SEGURO"]

df["score_orig"] = score_orig
df["faixa_5"] = pd.cut(score_orig, bins=BINS_5, labels=LABELS_5)
df["faixa_7"] = pd.cut(score_orig, bins=BINS_7, labels=LABELS_7)

print(f"\nN: {len(df):,} | Churn real: {100*y.mean():.1f}%\n")

# ═══════════════════════════════════════════════════════════════
# SIMULACOES: mudar cada feature pro melhor valor
# ═══════════════════════════════════════════════════════════════

# Features acionaveis e seus "melhores" valores
SIMULACOES = [
    # (feature, descricao, valor_melhor, como_aplicar)
    ("ciclo", "1o → 2o+ (sobreviver ao primeiro ciclo)", "2o+", "cat"),
    ("cronico", "N → S (acompanhamento cronico)", "S", "cat"),
    ("faixa_dep", "sem_dep → 1-2_dep (adicionar dependente)", "1-2_dep", "cat"),
    ("faixa_dep", "sem_dep → 3+_dep (familia completa)", "3+_dep", "cat"),
    ("faixa_nps_cat", "detrator/neutro/sem → promotor (NPS 9+)", "promotor", "cat"),
    ("rotatividade_cat", "alta/sem_atend → continuidade (mesmo medico)", "continuidade", "cat"),
    ("faixa_tempo_cat", "sem_atend/curto → longo (engajamento)", "longo", "cat"),
    ("faixa_idade_cat", "jovem → adulto (envelhecimento natural)", "adulto", "cat"),
    ("duracao", "12 → 6 (plano semestral)", "6", "cat"),
]

resultados = []

for layout_name, bins, labels, faixa_col, faixas_analisar in [
    ("5_faixas", BINS_5, LABELS_5, "faixa_5", ["ALTO", "MEDIO", "BAIXO"]),
    ("7_faixas", BINS_7, LABELS_7, "faixa_7", ["ALTO", "MEDIO", "BAIXO", "MUITO BAIXO"]),
]:
    FAIXA_RANK = {f: i for i, f in enumerate(labels)}

    print(f"\n{'#'*70}")
    print(f"LAYOUT: {layout_name.upper()}")
    print(f"{'#'*70}")

    for faixa in faixas_analisar:
        sub = df[df[faixa_col] == faixa].copy()
        n_faixa = len(sub)
        if n_faixa < 30:
            continue

        churn_faixa = round(100 * sub["churn_real_30d"].mean(), 1)
        print(f"\n{'='*70}")
        print(f"FAIXA: {faixa} — {n_faixa:,} contratos — Churn real: {churn_faixa}%")
        print(f"{'='*70}")

        for feat, desc, melhor_val, tipo in SIMULACOES:
            if tipo == "cat":
                afetados_mask = sub[feat].astype(str) != melhor_val
            else:
                continue

            n_afetados = afetados_mask.sum()
            if n_afetados < 10:
                continue

            sub_sim = sub.copy()
            sub_sim.loc[afetados_mask, feat] = melhor_val

            X_sim = make_X(sub_sim)
            for col in feature_columns:
                if col not in X_sim.columns:
                    X_sim[col] = 0
            X_sim = X_sim[feature_columns]

            prob_sim = bst.predict(xgb.DMatrix(X_sim))
            score_sim = (1000 * (prob_max - prob_sim) / (prob_max - prob_min)).clip(0, 1000).astype(int)
            faixa_sim = pd.cut(score_sim, bins=bins, labels=labels)

            faixa_orig_afetados = sub.loc[afetados_mask, faixa_col].values
            faixa_sim_afetados = np.array(faixa_sim[afetados_mask])

            migraram = sum(
                FAIXA_RANK.get(str(novo), 0) > FAIXA_RANK.get(str(orig), 0)
                for orig, novo in zip(faixa_orig_afetados, faixa_sim_afetados)
            )
            pct_migraram = round(100 * migraram / n_afetados, 1) if n_afetados > 0 else 0

            score_antes = int(sub.loc[afetados_mask, "score_orig"].mean())
            score_depois = int(score_sim[afetados_mask].mean())
            delta_score = score_depois - score_antes

            churn_afetados = round(100 * sub.loc[afetados_mask, "churn_real_30d"].mean(), 1)

            destinos = {}
            for orig, novo in zip(faixa_orig_afetados, faixa_sim_afetados):
                if FAIXA_RANK.get(str(novo), 0) > FAIXA_RANK.get(str(orig), 0):
                    destinos[str(novo)] = destinos.get(str(novo), 0) + 1

            destino_txt = ", ".join([f"{k}({v})" for k, v in sorted(destinos.items(), key=lambda x: -x[1])[:3]]) if destinos else "-"

            resultados.append({
                "layout": layout_name, "faixa": faixa, "feature": feat, "mudanca": desc,
                "afetados": n_afetados, "migraram": migraram, "pct_migraram": pct_migraram,
                "score_antes": score_antes, "score_depois": score_depois, "delta_score": delta_score,
                "churn_afetados": churn_afetados, "destinos": destino_txt,
            })

            if migraram > 0:
                print(f"\n  {desc}")
                print(f"    Afetados: {n_afetados:,} | Migraram: {migraram:,} ({pct_migraram}%)")
                print(f"    Score: {score_antes} → {score_depois} ({delta_score:+d} pts)")
                print(f"    Destinos: {destino_txt}")

        # Ranking por impacto
        faixa_resultados = [r for r in resultados if r["layout"] == layout_name and r["faixa"] == faixa and r["migraram"] > 0]
        if faixa_resultados:
            faixa_resultados.sort(key=lambda x: -x["migraram"])
            print(f"\n  RANKING DE IMPACTO (por contratos migrados):")
            for i, r in enumerate(faixa_resultados[:5]):
                print(f"    {i+1}. {r['mudanca']}")
                print(f"       {r['migraram']:,} migram ({r['pct_migraram']}%) | Score {r['delta_score']:+d} pts | → {r['destinos']}")

# Salvar
df_res = pd.DataFrame(resultados)
df_res.to_csv("results/transicao_faixas.csv", index=False)
print(f"\nSalvo: results/transicao_faixas.csv ({len(df_res)} simulacoes)")
