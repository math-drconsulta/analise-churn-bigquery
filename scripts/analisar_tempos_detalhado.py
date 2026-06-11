"""
Analise detalhada: tempos de espera (TME) e atendimento (TMA)
por etapa da jornada × churn.
"""
import pandas as pd
import numpy as np

df = pd.read_csv("results/tempos_jornada.csv")
df["churn"] = (df["churn_sn"] == "S").astype(int)

total = len(df)
print(f"Total: {total:,} contratos")
print(f"Churn global: {100*df['churn'].mean():.1f}%")

# Cobertura
for col, label in [
    ("tme_recepcao_medio", "TME Recepcao"),
    ("tme_preconsulta_medio", "TME Pre-consulta"),
    ("tme_consulta_medio", "TME Consulta"),
    ("tma_consulta_medio", "TMA Consulta"),
    ("espera_senha_ate_consulta_medio", "Espera senha→consulta"),
]:
    n = df[col].notna().sum()
    print(f"  {label:30s}: {n:>7,} ({100*n/total:.1f}%)")

def analise_tempo(col, label, bins_seg, labels_faixa):
    sub = df[df[col].notna() & (df[col] > 0)].copy()
    if len(sub) < 100:
        print(f"\n  {label}: poucos dados ({len(sub)}), pulando")
        return 0

    sub["minutos"] = sub[col] / 60
    sub["faixa"] = pd.cut(sub[col], bins=bins_seg, labels=labels_faixa)

    print(f"\n{'='*65}")
    print(f"{label} (em segundos, exibido em minutos)")
    print(f"{'='*65}")
    print(f"  Mediana: {sub[col].median()/60:.1f} min | Media: {sub[col].mean()/60:.1f} min | N: {len(sub):,}")

    grp = sub.groupby("faixa", observed=True).agg(
        n=("churn", "count"),
        churners=("churn", "sum"),
    ).reset_index()
    grp["churn_rate"] = (100 * grp["churners"] / grp["n"]).round(1)

    for _, r in grp.iterrows():
        bar = "█" * int(r["churn_rate"] / 2)
        print(f"  {str(r['faixa']):20s}  {r['churn_rate']:5.1f}%  {bar}  ({int(r['n']):>7,})")

    spread = grp["churn_rate"].max() - grp["churn_rate"].min()
    print(f"  SPREAD: {spread:.1f} p.p.")
    return spread

spreads = {}

# TME Recepcao (espera pra ser recebido)
spreads["TME Recepcao"] = analise_tempo(
    "tme_recepcao_medio", "TME RECEPCAO — Espera pra ser recebido no balcao",
    [-1, 60, 120, 300, 600, 1200, 999999],
    ["<1min", "1-2min", "2-5min", "5-10min", "10-20min", "20min+"]
)

# TME Pre-consulta (espera pra triagem)
spreads["TME Pre-consulta"] = analise_tempo(
    "tme_preconsulta_medio", "TME PRE-CONSULTA — Espera pra triagem (enfermagem)",
    [-1, 60, 180, 300, 600, 1200, 999999],
    ["<1min", "1-3min", "3-5min", "5-10min", "10-20min", "20min+"]
)

# TME Consulta (espera pro medico)
spreads["TME Consulta"] = analise_tempo(
    "tme_consulta_medio", "TME CONSULTA — Espera pra entrar no medico",
    [-1, 60, 180, 300, 600, 1200, 1800, 999999],
    ["<1min", "1-3min", "3-5min", "5-10min", "10-20min", "20-30min", "30min+"]
)

# TMA Consulta (tempo com o medico)
spreads["TMA Consulta"] = analise_tempo(
    "tma_consulta_medio", "TMA CONSULTA — Tempo com o medico",
    [-1, 300, 600, 900, 1200, 1800, 999999],
    ["<5min", "5-10min", "10-15min", "15-20min", "20-30min", "30min+"]
)

# TME Total (soma das esperas)
spreads["TME Total"] = analise_tempo(
    "tme_total_medio", "TME TOTAL — Soma de todas as esperas",
    [-1, 120, 300, 600, 900, 1200, 1800, 999999],
    ["<2min", "2-5min", "5-10min", "10-15min", "15-20min", "20-30min", "30min+"]
)

# Espera senha ate consulta (timestamps reais)
spreads["Senha→Consulta"] = analise_tempo(
    "espera_senha_ate_consulta_medio",
    "ESPERA REAL — Da senha ate entrar na consulta (timestamps)",
    [-1, 600, 1200, 1800, 2700, 3600, 5400, 999999],
    ["<10min", "10-20min", "20-30min", "30-45min", "45-60min", "60-90min", "90min+"]
)

# TMA Pre-consulta (tempo na triagem)
spreads["TMA Pre-consulta"] = analise_tempo(
    "tma_preconsulta_medio", "TMA PRE-CONSULTA — Tempo na triagem",
    [-1, 120, 300, 600, 900, 999999],
    ["<2min", "2-5min", "5-10min", "10-15min", "15min+"]
)

# Resumo
print(f"\n{'='*65}")
print("RESUMO: SPREAD POR ETAPA DA JORNADA")
print(f"{'='*65}")
for feat, spread in sorted(spreads.items(), key=lambda x: -x[1]):
    bar = "█" * int(spread)
    print(f"  {feat:25s}  {spread:5.1f} p.p.  {bar}")

print(f"\n  {'─'*50}")
print(f"  Referencia:")
print(f"  Medicos/especialidade:    10.0 p.p.")
print(f"  NPS numerico:              8.9 p.p.")
print(f"  Ciclo (demografico):      10.0 p.p.")
