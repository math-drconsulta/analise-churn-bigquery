"""
Investiga o paradoxo dos tempos: quem espera menos churneia mais.
Controla por ciclo (1o vs 2o+) e duracao (6m vs 12m) pra ver
se o efeito e real ou confounding.
"""
import pandas as pd
import numpy as np

df = pd.read_csv("results/tempos_jornada.csv")
df["churn"] = (df["churn_sn"] == "S").astype(int)

print(f"Total: {len(df):,} contratos | Churn: {100*df['churn'].mean():.1f}%")

# Churn por ciclo (referencia)
for ciclo in ["1o", "2o+"]:
    sub = df[df["ciclo"] == ciclo]
    print(f"  {ciclo}: {len(sub):,} contratos, churn {100*sub['churn'].mean():.1f}%")


def analise_controlada(col, label, bins_seg, labels_faixa):
    sub = df[df[col].notna() & (df[col] > 0)].copy()
    if len(sub) < 100:
        print(f"\n  {label}: poucos dados, pulando")
        return

    sub["faixa"] = pd.cut(sub[col], bins=bins_seg, labels=labels_faixa)

    print(f"\n{'='*75}")
    print(f"{label}")
    print(f"{'='*75}")

    # Geral (sem controle)
    print(f"\n  SEM CONTROLE (todos juntos):")
    grp = sub.groupby("faixa", observed=True).agg(
        n=("churn", "count"), ch=("churn", "sum")
    ).reset_index()
    grp["cr"] = (100 * grp["ch"] / grp["n"]).round(1)
    for _, r in grp.iterrows():
        bar = "█" * int(r["cr"] / 2)
        print(f"    {str(r['faixa']):20s}  {r['cr']:5.1f}%  {bar}  ({int(r['n']):>6,})")
    spread_geral = grp["cr"].max() - grp["cr"].min()
    print(f"    SPREAD: {spread_geral:.1f} p.p.")

    # Controlando por ciclo
    for ciclo in ["1o", "2o+"]:
        sub_c = sub[sub["ciclo"] == ciclo]
        if len(sub_c) < 50:
            continue

        print(f"\n  CONTROLADO POR CICLO = {ciclo} ({len(sub_c):,} contratos, churn {100*sub_c['churn'].mean():.1f}%):")
        grp = sub_c.groupby("faixa", observed=True).agg(
            n=("churn", "count"), ch=("churn", "sum")
        ).reset_index()
        grp = grp[grp["n"] >= 30]
        grp["cr"] = (100 * grp["ch"] / grp["n"]).round(1)
        for _, r in grp.iterrows():
            bar = "█" * int(r["cr"] / 2)
            print(f"    {str(r['faixa']):20s}  {r['cr']:5.1f}%  {bar}  ({int(r['n']):>6,})")
        if len(grp) >= 2:
            spread = grp["cr"].max() - grp["cr"].min()
            print(f"    SPREAD: {spread:.1f} p.p.")

    # Controlando por ciclo + duracao
    for ciclo in ["1o", "2o+"]:
        for dur in ["6", "12"]:
            sub_cd = sub[(sub["ciclo"] == ciclo) & (sub["duracao"] == dur)]
            if len(sub_cd) < 100:
                continue

            print(f"\n  CONTROLADO: {ciclo} + {dur}m ({len(sub_cd):,} contratos, churn {100*sub_cd['churn'].mean():.1f}%):")
            grp = sub_cd.groupby("faixa", observed=True).agg(
                n=("churn", "count"), ch=("churn", "sum")
            ).reset_index()
            grp = grp[grp["n"] >= 30]
            grp["cr"] = (100 * grp["ch"] / grp["n"]).round(1)
            for _, r in grp.iterrows():
                bar = "█" * int(r["cr"] / 2)
                print(f"    {str(r['faixa']):20s}  {r['cr']:5.1f}%  {bar}  ({int(r['n']):>6,})")
            if len(grp) >= 2:
                spread = grp["cr"].max() - grp["cr"].min()
                print(f"    SPREAD: {spread:.1f} p.p.")


# ═══════════════════════════════════════════════════════════════
# TESTAR CADA TEMPO CONTROLANDO POR CICLO
# ═══════════════════════════════════════════════════════════════

analise_controlada(
    "tme_consulta_medio",
    "TME CONSULTA — Espera pro medico",
    [-1, 60, 300, 600, 1200, 1800, 999999],
    ["<1min", "1-5min", "5-10min", "10-20min", "20-30min", "30min+"]
)

analise_controlada(
    "espera_senha_ate_consulta_medio",
    "ESPERA REAL — Senha ate consulta",
    [-1, 600, 1200, 1800, 2700, 3600, 999999],
    ["<10min", "10-20min", "20-30min", "30-45min", "45-60min", "60min+"]
)

analise_controlada(
    "tme_total_medio",
    "TME TOTAL — Soma de todas as esperas",
    [-1, 300, 600, 1200, 1800, 999999],
    ["<5min", "5-10min", "10-20min", "20-30min", "30min+"]
)

analise_controlada(
    "tma_consulta_medio",
    "TMA CONSULTA — Tempo com o medico",
    [-1, 300, 600, 900, 1800, 999999],
    ["<5min", "5-10min", "10-15min", "15-30min", "30min+"]
)


# ═══════════════════════════════════════════════════════════════
# RESUMO: O PARADOXO PERSISTE DEPOIS DE CONTROLAR?
# ═══════════════════════════════════════════════════════════════
print(f"\n\n{'='*75}")
print("COMPOSICAO: quem tem espera curta vs longa e qual ciclo?")
print(f"{'='*75}")

sub = df[df["espera_senha_ate_consulta_medio"].notna() & (df["espera_senha_ate_consulta_medio"] > 0)].copy()
sub["faixa_espera"] = pd.cut(
    sub["espera_senha_ate_consulta_medio"],
    bins=[-1, 600, 1800, 3600, 999999],
    labels=["<10min", "10-30min", "30-60min", "60min+"]
)

comp = sub.groupby(["faixa_espera", "ciclo"], observed=True).agg(
    n=("churn", "count")
).reset_index()
comp_total = comp.groupby("faixa_espera", observed=True)["n"].transform("sum")
comp["pct"] = (100 * comp["n"] / comp_total).round(1)

print(f"\n  {'Faixa espera':15s}  {'1o contrato':>15s}  {'2o+ contrato':>15s}")
print(f"  {'-'*50}")
for faixa in ["<10min", "10-30min", "30-60min", "60min+"]:
    row_1o = comp[(comp["faixa_espera"] == faixa) & (comp["ciclo"] == "1o")]
    row_2o = comp[(comp["faixa_espera"] == faixa) & (comp["ciclo"] == "2o+")]
    pct_1o = f'{row_1o.iloc[0]["pct"]}%' if len(row_1o) > 0 else "—"
    pct_2o = f'{row_2o.iloc[0]["pct"]}%' if len(row_2o) > 0 else "—"
    print(f"  {faixa:15s}  {pct_1o:>15s}  {pct_2o:>15s}")
