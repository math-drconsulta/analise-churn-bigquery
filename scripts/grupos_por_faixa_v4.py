"""
Analisa os grupos (combinacoes de features) dentro de cada faixa do score v4.
Mostra: composicao predominante + top grupos + churn por grupo.
"""
import pandas as pd
import numpy as np

df = pd.read_csv("results/score_v4_contratos.csv")
for col in df.columns:
    df[col] = df[col].astype(str)
df["churn_real_30d"] = pd.to_numeric(df["churn_real_30d"])
df["churn_original"] = pd.to_numeric(df["churn_original"])
df["score_v4"] = pd.to_numeric(df["score_v4"])
total = len(df)

FEATURES = ["ciclo", "duracao", "cronico", "faixa_dep", "faixa_idade_cat",
            "canal_simples", "faixa_nps_cat", "faixa_tempo_cat", "rotatividade_cat"]

FAIXAS = ["CRITICO", "MUITO ALTO", "ALTO", "MEDIO", "BAIXO", "MUITO BAIXO", "SEGURO"]

print(f"Total: {total:,} contratos")
print(f"Churn real 30d: {100*df['churn_real_30d'].mean():.1f}%")

for faixa in FAIXAS:
    sub = df[df["faixa_7"] == faixa]
    n = len(sub)
    if n == 0:
        continue

    cr = round(100 * sub["churn_real_30d"].mean(), 1)

    print(f"\n{'='*70}")
    print(f"FAIXA: {faixa} — {n:,} contratos ({100*n/total:.1f}%) — Churn real: {cr}%")
    print(f"{'='*70}")

    # Composicao predominante
    print(f"\n  RETRATO (caracteristica dominante por variavel):")
    for feat in FEATURES:
        dist = sub[feat].value_counts(normalize=True).head(3)
        top = dist.index[0]
        pct = round(dist.values[0] * 100, 0)
        extras = ""
        if len(dist) > 1:
            extras = " | " + " | ".join([f"{v}: {round(p*100)}%" for v, p in zip(dist.index[1:], dist.values[1:])])
        print(f"    {feat:20s}  {top:20s} ({pct:.0f}%){extras}")

    # Top 10 grupos (combinacoes mais frequentes)
    if n >= 30:
        print(f"\n  TOP 10 GRUPOS:")
        grupos = sub.groupby(FEATURES).agg(
            n=("churn_real_30d", "count"),
            ch=("churn_real_30d", "sum"),
        ).reset_index()
        grupos["cr"] = (100 * grupos["ch"] / grupos["n"]).round(1)
        grupos["pct_faixa"] = (100 * grupos["n"] / n).round(1)
        grupos = grupos.sort_values("n", ascending=False).head(10)

        for _, r in grupos.iterrows():
            perfil = " · ".join([str(r[f]) for f in FEATURES if str(r[f]) not in ["", "nan"]])
            bar = "█" * int(r["cr"] / 3)
            print(f"    {r['cr']:5.1f}%  {bar:30s}  ({int(r['n']):>5,} = {r['pct_faixa']:4.1f}%)  {perfil}")

    # Churn por feature dentro da faixa
    if n >= 100:
        print(f"\n  CHURN POR FEATURE (dentro da faixa):")
        for feat in FEATURES:
            vals = sub.groupby(feat).agg(n=("churn_real_30d", "count"), ch=("churn_real_30d", "sum")).reset_index()
            vals["cr"] = (100 * vals["ch"] / vals["n"]).round(1)
            vals = vals[vals["n"] >= 10].sort_values("cr", ascending=False)
            if len(vals) >= 2:
                spread = vals["cr"].max() - vals["cr"].min()
                if spread >= 3:  # so mostra se tem spread relevante
                    print(f"    {feat}: ", end="")
                    print(" | ".join([f"{r[feat]}={r['cr']}%" for _, r in vals.iterrows()]))
