"""
Analisa o poder preditivo de cada feature comportamental.
Mostra churn rate por faixa de cada feature.
"""
import pandas as pd
import numpy as np

df = pd.read_csv("results/features_comportamentais.csv")
print(f"Total: {len(df):,} contratos")
print(f"Churn global: {100*df['churn_sn'].eq('S').mean():.1f}%")
print(f"Com uso (total_itens > 0): {(df['total_itens'] > 0).sum():,} ({100*(df['total_itens'] > 0).mean():.1f}%)")
print(f"Sem uso: {(df['total_itens'] == 0).sum():,}")

def analise(col, label):
    print(f"\n{'='*60}")
    print(f"{label} ({col})")
    print(f"{'='*60}")
    grp = df.groupby(col).agg(
        n=("churn_sn", "count"),
        churners=("churn_sn", lambda x: (x == "S").sum()),
    ).reset_index()
    grp["churn_rate"] = (100 * grp["churners"] / grp["n"]).round(1)
    grp["pct_base"] = (100 * grp["n"] / len(df)).round(1)
    grp = grp.sort_values("churn_rate", ascending=False)
    for _, r in grp.iterrows():
        bar = "█" * int(r["churn_rate"] / 2)
        print(f"  {str(r[col]):25s}  {r['churn_rate']:5.1f}%  {bar}  ({int(r['n']):>7,} = {r['pct_base']}%)")

analise("faixa_uso", "VOLUME DE USO")
analise("faixa_onboarding", "ONBOARDING (tempo ate 1o uso)")
analise("tendencia_uso", "TRAJETORIA (uso caindo?)")
analise("faixa_dispersao", "DISPERSAO GEOGRAFICA (unidades)")

# Features numericas: faixas customizadas
print(f"\n{'='*60}")
print("RECENCIA (dias desde ultimo uso)")
print(f"{'='*60}")
com_uso = df[df["total_itens"] > 0].copy()
com_uso["faixa_recencia"] = pd.cut(
    com_uso["dias_desde_ultimo_uso"],
    bins=[-1, 30, 60, 90, 120, 180, 9999],
    labels=["0-30d", "31-60d", "61-90d", "91-120d", "121-180d", "180d+"]
)
grp = com_uso.groupby("faixa_recencia", observed=True).agg(
    n=("churn_sn", "count"),
    churners=("churn_sn", lambda x: (x == "S").sum()),
).reset_index()
grp["churn_rate"] = (100 * grp["churners"] / grp["n"]).round(1)
for _, r in grp.iterrows():
    bar = "█" * int(r["churn_rate"] / 2)
    print(f"  {str(r['faixa_recencia']):25s}  {r['churn_rate']:5.1f}%  {bar}  ({int(r['n']):>7,})")

print(f"\n{'='*60}")
print("FREQUENCIA (itens por mes)")
print(f"{'='*60}")
com_uso["faixa_freq"] = pd.cut(
    com_uso["itens_por_mes"],
    bins=[-0.01, 0.5, 1, 2, 3, 999],
    labels=["<0.5/mes", "0.5-1/mes", "1-2/mes", "2-3/mes", "3+/mes"]
)
grp = com_uso.groupby("faixa_freq", observed=True).agg(
    n=("churn_sn", "count"),
    churners=("churn_sn", lambda x: (x == "S").sum()),
).reset_index()
grp["churn_rate"] = (100 * grp["churners"] / grp["n"]).round(1)
for _, r in grp.iterrows():
    bar = "█" * int(r["churn_rate"] / 2)
    print(f"  {str(r['faixa_freq']):25s}  {r['churn_rate']:5.1f}%  {bar}  ({int(r['n']):>7,})")

print(f"\n{'='*60}")
print("ESPECIALIDADES (diversidade)")
print(f"{'='*60}")
com_uso["faixa_esp"] = pd.cut(
    com_uso["qtd_especialidades"],
    bins=[-1, 1, 2, 3, 99],
    labels=["1 esp.", "2 esp.", "3 esp.", "4+ esp."]
)
grp = com_uso.groupby("faixa_esp", observed=True).agg(
    n=("churn_sn", "count"),
    churners=("churn_sn", lambda x: (x == "S").sum()),
).reset_index()
grp["churn_rate"] = (100 * grp["churners"] / grp["n"]).round(1)
for _, r in grp.iterrows():
    bar = "█" * int(r["churn_rate"] / 2)
    print(f"  {str(r['faixa_esp']):25s}  {r['churn_rate']:5.1f}%  {bar}  ({int(r['n']):>7,})")

# Resumo: spread de cada feature
print(f"\n{'='*60}")
print("RESUMO: SPREAD DE CADA FEATURE (max - min churn)")
print(f"{'='*60}")
for col, label in [
    ("faixa_uso", "Volume de uso"),
    ("faixa_onboarding", "Onboarding"),
    ("tendencia_uso", "Trajetória"),
    ("faixa_dispersao", "Dispersão"),
]:
    grp = df.groupby(col).agg(ch=("churn_sn", lambda x: 100*(x=="S").mean())).reset_index()
    spread = grp["ch"].max() - grp["ch"].min()
    print(f"  {label:25s}  spread = {spread:.1f} p.p.  (min {grp['ch'].min():.1f}% — max {grp['ch'].max():.1f}%)")

# Recencia e frequencia (com uso)
for col, label, bins, labs in [
    ("dias_desde_ultimo_uso", "Recência", [-1,30,60,90,120,180,9999], ["0-30","31-60","61-90","91-120","121-180","180+"]),
    ("itens_por_mes", "Frequência", [-0.01,0.5,1,2,3,999], ["<0.5","0.5-1","1-2","2-3","3+"]),
]:
    temp = com_uso.copy()
    temp["fx"] = pd.cut(temp[col], bins=bins, labels=labs)
    grp = temp.groupby("fx", observed=True).agg(ch=("churn_sn", lambda x: 100*(x=="S").mean())).reset_index()
    spread = grp["ch"].max() - grp["ch"].min()
    print(f"  {label:25s}  spread = {spread:.1f} p.p.  (min {grp['ch'].min():.1f}% — max {grp['ch'].max():.1f}%)")
