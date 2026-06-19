"""
Analisa especialidades x churn real 30d x faixas do score v4.
"""
import pandas as pd
import numpy as np

# Carregar e mergear
df_esp = pd.read_csv("results/especialidades_por_faixa.csv")
df_score = pd.read_csv("results/score_v4_contratos.csv")

df = df_esp.merge(df_score[["contract_id", "score_v4", "faixa_7"]], on="contract_id", how="inner")
print(f"Total: {len(df):,} contratos")
print(f"Churn real 30d: {100*df['churn_real_30d'].mean():.1f}%")

ESPECIALIDADES = [
    ("usou_clinica_medica", "Clinica Medica"),
    ("usou_tele", "Teleconsulta"),
    ("usou_exames", "Exames"),
    ("usou_ginecologia", "Ginecologia"),
    ("usou_cardiologia", "Cardiologia"),
    ("usou_dermatologia", "Dermatologia"),
    ("usou_endocrinologia", "Endocrinologia"),
    ("usou_gastro", "Gastroenterologia"),
    ("usou_oftalmo", "Oftalmologia"),
    ("usou_ortopedia", "Ortopedia"),
    ("usou_pediatria", "Pediatria"),
    ("usou_psiquiatria", "Psiquiatria"),
    ("usou_urologia", "Urologia"),
    ("usou_neurologia", "Neurologia"),
]

FAIXAS = ["CRITICO", "MUITO ALTO", "ALTO", "MEDIO", "BAIXO", "MUITO BAIXO", "SEGURO"]
churn_base = round(100 * df["churn_real_30d"].mean(), 1)

# ═══════════════════════════════════════════════════════════════
# 1. CHURN REAL POR ESPECIALIDADE (usou vs nao usou)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print(f"1. CHURN REAL 30D POR ESPECIALIDADE (usou vs nao usou)")
print(f"   Base: {churn_base}%")
print(f"{'='*70}\n")

resultados = []
for col, nome in ESPECIALIDADES:
    usou = df[df[col] == 1]
    nao_usou = df[df[col] == 0]
    n_usou = len(usou)
    n_nao = len(nao_usou)
    if n_usou < 30:
        continue
    cr_usou = round(100 * usou["churn_real_30d"].mean(), 1)
    cr_nao = round(100 * nao_usou["churn_real_30d"].mean(), 1)
    delta = round(cr_usou - cr_nao, 1)
    resultados.append({"esp": nome, "n_usou": n_usou, "cr_usou": cr_usou, "cr_nao": cr_nao, "delta": delta})

resultados.sort(key=lambda x: x["delta"])

for r in resultados:
    direcao = "PROTEGE" if r["delta"] < -2 else "NEUTRO" if abs(r["delta"]) <= 2 else "RISCO"
    bar = "█" * abs(int(r["delta"]))
    sinal = "↓" if r["delta"] < 0 else "↑"
    print(f"  {r['esp']:20s}  usou:{r['cr_usou']:5.1f}%  nao:{r['cr_nao']:5.1f}%  Δ={r['delta']:+5.1f}  {sinal}{bar}  ({r['n_usou']:>6,} usaram)  {direcao}")


# ═══════════════════════════════════════════════════════════════
# 2. ESPECIALIDADES POR FAIXA DE SCORE
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print(f"2. % QUE USOU CADA ESPECIALIDADE POR FAIXA")
print(f"{'='*70}\n")

# Header
header = f"{'Especialidade':20s}"
for faixa in FAIXAS:
    n_faixa = len(df[df["faixa_7"] == faixa])
    if n_faixa > 0:
        header += f"  {faixa:>10s}"
print(header)
print("-" * len(header))

for col, nome in ESPECIALIDADES:
    linha = f"{nome:20s}"
    for faixa in FAIXAS:
        sub = df[df["faixa_7"] == faixa]
        if len(sub) == 0:
            continue
        pct = round(100 * sub[col].mean(), 1)
        linha += f"  {pct:>9.1f}%"
    print(linha)

# Totais
linha = f"{'Alguma especialidade':20s}"
for faixa in FAIXAS:
    sub = df[df["faixa_7"] == faixa]
    if len(sub) == 0:
        continue
    pct = round(100 * (sub["total_atendimentos"] > 0).mean(), 1)
    linha += f"  {pct:>9.1f}%"
print(linha)


# ═══════════════════════════════════════════════════════════════
# 3. DIVERSIDADE DE ESPECIALIDADES x CHURN REAL
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print(f"3. DIVERSIDADE DE ESPECIALIDADES × CHURN REAL")
print(f"{'='*70}\n")

df["faixa_diversidade"] = pd.cut(
    df["qtd_especialidades_usadas"], bins=[-1, 0, 1, 2, 3, 99],
    labels=["nenhuma", "1 esp.", "2 esp.", "3 esp.", "4+ esp."]
)

for faixa_d, sub in df.groupby("faixa_diversidade", observed=True):
    n = len(sub)
    if n < 30:
        continue
    cr = round(100 * sub["churn_real_30d"].mean(), 1)
    bar = "█" * int(cr / 2)
    print(f"  {str(faixa_d):12s}  {cr:5.1f}%  {bar}  ({n:>7,} = {100*n/len(df):.1f}%)")


# ═══════════════════════════════════════════════════════════════
# 4. ESPECIALIDADES QUE MAIS DIFERENCIAM AS FAIXAS
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print(f"4. ESPECIALIDADES QUE MAIS DIFERENCIAM ALTO vs SEGURO")
print(f"{'='*70}\n")

alto = df[df["faixa_7"].isin(["CRITICO", "MUITO ALTO", "ALTO"])]
seguro = df[df["faixa_7"].isin(["MUITO BAIXO", "SEGURO"])]

for col, nome in ESPECIALIDADES:
    pct_alto = round(100 * alto[col].mean(), 1) if len(alto) > 0 else 0
    pct_seguro = round(100 * seguro[col].mean(), 1) if len(seguro) > 0 else 0
    diff = round(pct_seguro - pct_alto, 1)
    if abs(diff) >= 3:
        sinal = "↑" if diff > 0 else "↓"
        print(f"  {nome:20s}  ALTO:{pct_alto:5.1f}%  SEGURO:{pct_seguro:5.1f}%  {sinal} {diff:+.1f} p.p.")
