"""
Drivers de cada faixa (5 e 7 faixas): o que define e diferencia cada nivel.
"""
import pandas as pd
import numpy as np

df = pd.read_csv("results/score_v4_contratos.csv")
for col in df.columns:
    if col not in ["churn_original", "churn_real_30d", "score_v4"]:
        df[col] = df[col].astype(str)
df["churn_real_30d"] = pd.to_numeric(df["churn_real_30d"])
df["score_v4"] = pd.to_numeric(df["score_v4"])

FEATURES = ["ciclo", "duracao", "cronico", "faixa_dep", "faixa_idade_cat",
            "canal_simples", "faixa_nps_cat", "faixa_tempo_cat", "rotatividade_cat"]

LABELS_AMIGAVEIS = {
    "ciclo": "Ciclo", "duracao": "Duracao", "cronico": "Cronico",
    "faixa_dep": "Dependentes", "faixa_idade_cat": "Idade",
    "canal_simples": "Canal", "faixa_nps_cat": "NPS",
    "faixa_tempo_cat": "Tempo clinica", "rotatividade_cat": "Rotatividade",
}

VALOR_PROTEGE = {
    "ciclo": "2o+", "duracao": "6", "cronico": "S",
    "faixa_dep": "3+_dep", "faixa_idade_cat": "senior",
    "canal_simples": "presencial", "faixa_nps_cat": "promotor",
    "faixa_tempo_cat": "longo", "rotatividade_cat": "continuidade",
}
VALOR_RISCO = {
    "ciclo": "1o", "duracao": "12", "cronico": "N",
    "faixa_dep": "sem_dep", "faixa_idade_cat": "jovem",
    "canal_simples": "digital", "faixa_nps_cat": "sem_nps",
    "faixa_tempo_cat": "sem_atend", "rotatividade_cat": "alta",
}

LAYOUTS = [
    ("5_faixas", "faixa_5", ["CRITICO", "ALTO", "MEDIO", "BAIXO", "SEGURO"]),
    ("7_faixas", "faixa_7", ["CRITICO", "MUITO ALTO", "ALTO", "MEDIO", "BAIXO", "MUITO BAIXO", "SEGURO"]),
]

total = len(df)
print(f"Total: {total:,} contratos\n")

resultados_drivers = []

for layout_name, faixa_col, faixas_lista in LAYOUTS:
    print(f"\n{'#'*70}")
    print(f"LAYOUT: {layout_name.upper()}")
    print(f"{'#'*70}")

    # 1. DRIVERS POR FAIXA
    for faixa in faixas_lista:
        sub = df[df[faixa_col] == faixa]
        n = len(sub)
        if n < 10:
            continue

        cr = round(100 * sub["churn_real_30d"].mean(), 1)
        score_med = int(sub["score_v4"].median())

        print(f"\n{'='*70}")
        print(f"{faixa} — {n:,} contratos ({100*n/total:.1f}%) — Churn real: {cr}% — Score mediano: {score_med}")
        print(f"{'='*70}")

        print(f"\n  {'Feature':20s}  {'Risco':>15s}  {'Protege':>15s}  {'Driver?':>10s}")
        print(f"  {'-'*65}")

        drivers_risco = []
        drivers_protege = []

        for feat in FEATURES:
            val_risco = VALOR_RISCO[feat]
            val_protege = VALOR_PROTEGE[feat]

            pct_risco = round(100 * (sub[feat] == val_risco).mean(), 1)
            pct_protege = round(100 * (sub[feat] == val_protege).mean(), 1)

            pct_risco_base = round(100 * (df[feat] == val_risco).mean(), 1)
            pct_protege_base = round(100 * (df[feat] == val_protege).mean(), 1)

            delta_risco = round(pct_risco - pct_risco_base, 1)
            delta_protege = round(pct_protege - pct_protege_base, 1)

            is_driver = ""
            if delta_risco > 15:
                is_driver = "RISCO ↑"
                drivers_risco.append((feat, val_risco, pct_risco, delta_risco))
            elif delta_risco < -15:
                is_driver = "risco ↓"
            if delta_protege > 15:
                is_driver = "PROTEGE ↑"
                drivers_protege.append((feat, val_protege, pct_protege, delta_protege))
            elif delta_protege < -15:
                is_driver = "protege ↓"

            print(f"  {LABELS_AMIGAVEIS[feat]:20s}  {val_risco}={pct_risco}%{' ':>3s}  {val_protege}={pct_protege}%{' ':>3s}  {is_driver}")

            resultados_drivers.append({
                "layout": layout_name, "faixa": faixa, "feature": feat,
                "val_risco": val_risco, "pct_risco": pct_risco, "delta_risco": delta_risco,
                "val_protege": val_protege, "pct_protege": pct_protege, "delta_protege": delta_protege,
            })

        if drivers_risco or drivers_protege:
            print(f"\n  DRIVERS desta faixa:")
            for feat, val, pct, delta in sorted(drivers_risco, key=lambda x: -x[3]):
                print(f"    ↑ RISCO: {LABELS_AMIGAVEIS[feat]} = {val} ({pct}%, +{delta} p.p. vs base)")
            for feat, val, pct, delta in sorted(drivers_protege, key=lambda x: -x[3]):
                print(f"    ↑ PROTEGE: {LABELS_AMIGAVEIS[feat]} = {val} ({pct}%, +{delta} p.p. vs base)")

        print()

    # 2. CONTRASTE ENTRE FAIXAS ADJACENTES
    print(f"\n  CONTRASTE ENTRE FAIXAS ADJACENTES ({layout_name})")
    print(f"  {'='*60}")

    faixas_com_volume = [f for f in faixas_lista if len(df[df[faixa_col] == f]) >= 100]

    for i in range(len(faixas_com_volume) - 1):
        faixa_pior = faixas_com_volume[i]
        faixa_melhor = faixas_com_volume[i + 1]

        sub_pior = df[df[faixa_col] == faixa_pior]
        sub_melhor = df[df[faixa_col] == faixa_melhor]

        cr_pior = round(100 * sub_pior["churn_real_30d"].mean(), 1)
        cr_melhor = round(100 * sub_melhor["churn_real_30d"].mean(), 1)

        print(f"\n  {faixa_pior} ({cr_pior}%) → {faixa_melhor} ({cr_melhor}%): o que muda?")

        diferencas = []
        for feat in FEATURES:
            for val in df[feat].unique():
                pct_pior = round(100 * (sub_pior[feat] == val).mean(), 1)
                pct_melhor = round(100 * (sub_melhor[feat] == val).mean(), 1)
                delta = round(pct_melhor - pct_pior, 1)
                if abs(delta) >= 5:
                    diferencas.append((feat, val, pct_pior, pct_melhor, delta))

        diferencas.sort(key=lambda x: -abs(x[4]))
        for feat, val, pct_p, pct_m, delta in diferencas[:6]:
            sinal = "↑" if delta > 0 else "↓"
            print(f"    {LABELS_AMIGAVEIS[feat]:15s} = {val:15s}  {faixa_pior}:{pct_p:5.1f}%  →  {faixa_melhor}:{pct_m:5.1f}%  {sinal} {delta:+.1f} p.p.")

# Salvar
pd.DataFrame(resultados_drivers).to_csv("results/drivers_por_faixa.csv", index=False)
print(f"\nSalvo: results/drivers_por_faixa.csv ({len(resultados_drivers)} linhas)")
