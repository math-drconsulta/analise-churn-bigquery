"""
Analise aprofundada de reincidentes: CPFs com multiplos contatos no SAC.
Responde: quem liga mais vezes tem mais churn? O que muda por motivo?
"""
import pandas as pd
import numpy as np
import re

def normalizar_cpf(cpf):
    if pd.isna(cpf):
        return None
    c = re.sub(r"[^0-9]", "", str(cpf))
    return c if len(c) == 11 else None

# Carregar SACs
yalo = pd.read_csv("results/sac_SAC_YALO.csv")
yalo["cpf"] = yalo["CPF"].apply(normalizar_cpf)
yalo["data"] = pd.to_datetime(yalo["Hora da cr"], errors="coerce")
yalo["fonte"] = "YALO"
yalo["motivo"] = yalo["O motivo da ligação é ..."].fillna("")
yalo["detalhe"] = yalo["Mais detalhe dessa solicitação"].fillna("")

drc = pd.read_csv("results/sac_SAC_DRC.csv")
drc["cpf"] = drc["CPF"].apply(normalizar_cpf)
drc["data"] = pd.to_datetime(drc["Hora da cr"], errors="coerce")
drc["fonte"] = "DRC"
drc["motivo"] = drc["MOTIVO"].fillna("")
drc["detalhe"] = drc["Submotivo"].fillna("")

# Unir e filtrar CPFs validos
sac = pd.concat([
    yalo[["cpf", "data", "fonte", "motivo", "detalhe"]],
    drc[["cpf", "data", "fonte", "motivo", "detalhe"]],
], ignore_index=True)
sac = sac[sac["cpf"].notna()].copy()

# Carregar churn
churn = pd.read_csv("results/sac_churn_resumo.csv", dtype={"cpf": str})
churn_cpf = churn[["cpf", "churn_sn", "tipo_desfecho", "ciclo"]].drop_duplicates("cpf")
churn_cpf["cpf"] = churn_cpf["cpf"].apply(normalizar_cpf)
churn_cpf = churn_cpf[churn_cpf["cpf"].notna()]

print(f"CPFs SAC: {sac['cpf'].nunique():,}")
print(f"CPFs churn: {churn_cpf['cpf'].nunique():,}")
print(f"Intersecao: {len(set(sac['cpf']) & set(churn_cpf['cpf'])):,}")

# Contar tickets por CPF (ambos os SACs combinados)
tickets_por_cpf = sac.groupby("cpf").agg(
    total_tickets=("cpf", "count"),
    tickets_yalo=("fonte", lambda x: (x == "YALO").sum()),
    tickets_drc=("fonte", lambda x: (x == "DRC").sum()),
    primeiro=("data", "min"),
    ultimo=("data", "max"),
    fontes=("fonte", lambda x: "+".join(sorted(x.unique()))),
    motivos_unicos=("motivo", "nunique"),
).reset_index()

# Merge com churn
merged = tickets_por_cpf.merge(churn_cpf, on="cpf", how="inner")

print(f"Total CPFs com SAC + match churn: {len(merged):,}")
print(f"Churn global desse grupo: {100*merged['churn_sn'].eq('S').mean():.1f}%")

# ═══════════════════════════════════════════════════════════════
# 1. CHURN POR QUANTIDADE DE TICKETS
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print("CHURN POR QUANTIDADE DE TICKETS (YALO + DRC combinados)")
print(f"{'='*60}")

for n in [1, 2, 3, 4, 5, "6-10", "11+"]:
    if isinstance(n, int):
        sub = merged[merged["total_tickets"] == n]
        label = f"{n} ticket{'s' if n > 1 else ' '}"
    elif n == "6-10":
        sub = merged[(merged["total_tickets"] >= 6) & (merged["total_tickets"] <= 10)]
        label = "6-10 tickets"
    else:
        sub = merged[merged["total_tickets"] >= 11]
        label = "11+ tickets"

    if len(sub) == 0:
        continue
    ch = sub["churn_sn"].eq("S").sum()
    cr = round(100 * ch / len(sub), 1)
    bar = "█" * int(cr / 2)
    print(f"  {label:15s}  {cr:5.1f}%  {bar}  ({len(sub):>5,} pacientes, {ch:,} churners)")

# ═══════════════════════════════════════════════════════════════
# 2. CHURN POR FONTE (só YALO, só DRC, ambos)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print("CHURN POR FONTE DO CONTATO")
print(f"{'='*60}")

for fonte, sub in merged.groupby("fontes"):
    n = len(sub)
    if n < 10:
        continue
    ch = sub["churn_sn"].eq("S").sum()
    cr = round(100 * ch / n, 1)
    bar = "█" * int(cr / 2)
    print(f"  {fonte:15s}  {cr:5.1f}%  {bar}  ({n:>5,} pacientes)")

# ═══════════════════════════════════════════════════════════════
# 3. REINCIDENTES QUE LIGARAM PRA YALO E DRC
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print("PACIENTES QUE CONTATARAM YALO + DRC (ambos)")
print(f"{'='*60}")

ambos = merged[merged["fontes"] == "DRC+YALO"]
if len(ambos) > 0:
    print(f"  Total: {len(ambos):,}")
    print(f"  Churn: {100*ambos['churn_sn'].eq('S').mean():.1f}%")
    print(f"  Tickets medio: {ambos['total_tickets'].mean():.1f}")
    print(f"  Tickets max: {ambos['total_tickets'].max()}")

# ═══════════════════════════════════════════════════════════════
# 4. INTERVALO ENTRE TICKETS (frequencia de contato)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print("INTERVALO ENTRE PRIMEIRO E ULTIMO TICKET")
print(f"{'='*60}")

reincidentes = merged[merged["total_tickets"] >= 2].copy()
reincidentes["dias_span"] = (reincidentes["ultimo"] - reincidentes["primeiro"]).dt.days

for faixa, lo, hi in [("Mesmo dia", -1, 1), ("1-7 dias", 1, 8), ("8-30 dias", 8, 31),
                        ("31-60 dias", 31, 61), ("61+ dias", 61, 9999)]:
    sub = reincidentes[(reincidentes["dias_span"] >= lo) & (reincidentes["dias_span"] < hi)]
    if len(sub) == 0:
        continue
    ch = sub["churn_sn"].eq("S").sum()
    cr = round(100 * ch / len(sub), 1)
    bar = "█" * int(cr / 2)
    print(f"  {faixa:15s}  {cr:5.1f}%  {bar}  ({len(sub):>5,} pacientes)")

# ═══════════════════════════════════════════════════════════════
# 5. CHURN POR CICLO × QUANTIDADE DE TICKETS
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print("CHURN POR CICLO × TICKETS")
print(f"{'='*60}")

merged["faixa_tickets"] = pd.cut(
    merged["total_tickets"], bins=[0, 1, 2, 3, 5, 999],
    labels=["1", "2", "3", "4-5", "6+"]
)

for ciclo in ["1o", "2o+"]:
    print(f"\n  {ciclo} contrato:")
    sub_ciclo = merged[merged["ciclo"] == ciclo]
    for faixa, sub in sub_ciclo.groupby("faixa_tickets", observed=True):
        n = len(sub)
        if n < 5:
            continue
        ch = sub["churn_sn"].eq("S").sum()
        cr = round(100 * ch / n, 1)
        bar = "█" * int(cr / 2)
        print(f"    {str(faixa):10s}  {cr:5.1f}%  {bar}  ({n:>5,} pac.)")

# ═══════════════════════════════════════════════════════════════
# 6. TOP REINCIDENTES: perfil dos que mais ligam
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print("TOP 20 REINCIDENTES (mais tickets)")
print(f"{'='*60}")

top = merged.nlargest(20, "total_tickets")
for _, r in top.iterrows():
    status = "CHURNOU" if r["churn_sn"] == "S" else "RETIDO"
    print(f"  CPF ***{str(r['cpf'])[-4:]}  {int(r['total_tickets']):3d} tickets  "
          f"YALO:{int(r['tickets_yalo'])} DRC:{int(r['tickets_drc'])}  "
          f"{r['fontes']:10s}  {status}  {r['ciclo']}")
