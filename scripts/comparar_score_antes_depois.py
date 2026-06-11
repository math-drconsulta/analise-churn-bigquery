"""
Compara o score ANTES (so perfil) vs DEPOIS (perfil + recencia + onboarding).
Mostra se adicionar as features comportamentais melhora a separacao das faixas.
"""
import pandas as pd
import numpy as np

df = pd.read_csv("results/features_comportamentais.csv")
df["churn"] = (df["churn_sn"] == "S").astype(int)
df["duracao"] = df["duracao"].astype(str)

print(f"Base: {len(df):,} contratos | Churn: {100*df['churn'].mean():.1f}%")

# ═══════════════════════════════════════════════════════════════
# SCORE A: SO PERFIL (mesmo peso do score_dinamico.py)
# ═══════════════════════════════════════════════════════════════
PENALIDADES = {
    "ciclo":    {"1o": -120, "2o+": 0},
    "duracao":  {"6": 0, "12": -50},
}

df["score_perfil"] = 700
for var, mapa in PENALIDADES.items():
    if var in df.columns:
        for nivel, pts in mapa.items():
            df.loc[df[var].astype(str) == str(nivel), "score_perfil"] += pts

# ═══════════════════════════════════════════════════════════════
# SCORE B: PERFIL + RECENCIA + ONBOARDING
# ═══════════════════════════════════════════════════════════════

def sinal_recencia(dias):
    """Baseado no spread real: 37.3% (0-30d) vs 55.5% (31-60d) = 18 p.p."""
    if pd.isna(dias):
        return 0  # sem uso registrado — neutro
    dias = int(dias)
    if dias <= 30:
        return +80    # usou recentemente — protege
    elif dias <= 60:
        return -100   # parou recentemente — zona de perigo
    elif dias <= 120:
        return -50    # inativo moderado
    elif dias <= 180:
        return -30
    else:
        return 0      # inativo cronico — volta ao neutro

def sinal_onboarding(dias):
    """Baseado no spread real: 43.3% (0-7d) vs 50.3% (31-90d) = 7 p.p."""
    if pd.isna(dias):
        return -40    # nunca usou
    dias = int(dias)
    if dias <= 7:
        return +40    # rapido — bom sinal
    elif dias <= 30:
        return +15
    elif dias <= 90:
        return -20    # lento
    else:
        return -40    # muito lento

df["sinal_recencia"] = df["dias_desde_ultimo_uso"].apply(sinal_recencia)
df["sinal_onboarding"] = df["dias_ate_primeiro_uso"].apply(sinal_onboarding)

df["score_completo"] = (df["score_perfil"] + df["sinal_recencia"] + df["sinal_onboarding"]).clip(0, 1000)


# ═══════════════════════════════════════════════════════════════
# COMPARAR FAIXAS
# ═══════════════════════════════════════════════════════════════

def analisar_score(col, titulo):
    bins = [-1, 200, 400, 600, 800, 1001]
    labels = ["CRITICO (0-200)", "ALTO (200-400)", "MEDIO (400-600)", "BAIXO (600-800)", "SEGURO (800-1000)"]
    df["faixa"] = pd.cut(df[col], bins=bins, labels=labels)

    print(f"\n{'='*70}")
    print(f"{titulo}")
    print(f"{'='*70}")

    resultado = []
    for faixa in labels:
        sub = df[df["faixa"] == faixa]
        n = len(sub)
        if n == 0:
            continue
        ch = sub["churn"].sum()
        cr = round(100 * ch / n, 1)
        bar = "█" * int(cr / 2)
        resultado.append({"faixa": faixa, "n": n, "churn": cr})
        print(f"  {faixa:25s}  {cr:5.1f}%  {bar}  ({n:>7,} contratos = {100*n/len(df):.1f}%)")

    if len(resultado) >= 2:
        spread = max(r["churn"] for r in resultado) - min(r["churn"] for r in resultado)
        print(f"\n  SPREAD: {spread:.1f} p.p. (pior faixa - melhor faixa)")

    return resultado

res_antes = analisar_score("score_perfil", "SCORE A: SO PERFIL (ciclo + duracao)")
res_depois = analisar_score("score_completo", "SCORE B: PERFIL + RECENCIA + ONBOARDING")


# ═══════════════════════════════════════════════════════════════
# RESUMO DA MELHORIA
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print("COMPARACAO")
print(f"{'='*70}")

spread_a = max(r["churn"] for r in res_antes) - min(r["churn"] for r in res_antes)
spread_b = max(r["churn"] for r in res_depois) - min(r["churn"] for r in res_depois)
melhora = spread_b - spread_a

print(f"  Spread ANTES (so perfil):           {spread_a:.1f} p.p.")
print(f"  Spread DEPOIS (perfil + comportam.): {spread_b:.1f} p.p.")
print(f"  Melhora:                             {melhora:+.1f} p.p.")
print()

if melhora > 3:
    print("  RESULTADO: Adicionar recencia e onboarding MELHORA a separacao do score.")
    print(f"  O score consegue separar {spread_b:.1f} p.p. entre a melhor e pior faixa,")
    print(f"  vs {spread_a:.1f} p.p. usando so perfil.")
elif melhora > 0:
    print("  RESULTADO: Melhora leve. As features comportamentais adicionam pouco")
    print("  ao que o perfil ja captura.")
else:
    print("  RESULTADO: Sem melhora. As features comportamentais nao adicionam")
    print("  poder preditivo alem do perfil.")

# Detalhe: onde a recencia faz diferenca
print(f"\n{'='*70}")
print("DETALHE: RECENCIA DENTRO DE CADA FAIXA DE PERFIL")
print("(mostra se recencia separa DENTRO do mesmo perfil)")
print(f"{'='*70}")

bins_perfil = [-1, 400, 600, 1001]
labels_perfil = ["Perfil ALTO RISCO", "Perfil MEDIO", "Perfil BAIXO RISCO"]
df["faixa_perfil"] = pd.cut(df["score_perfil"], bins=bins_perfil, labels=labels_perfil)

for fp in labels_perfil:
    sub = df[df["faixa_perfil"] == fp]
    if len(sub) == 0:
        continue
    print(f"\n  {fp} ({len(sub):,} contratos, churn medio {100*sub['churn'].mean():.1f}%):")

    # Dentro desse perfil, qual o efeito da recencia?
    com_uso = sub[sub["total_itens"] > 0]
    if len(com_uso) == 0:
        print("    Sem dados de uso nesse perfil")
        continue

    for faixa_rec, lo, hi in [
        ("Usou <30d", -1, 31),
        ("Parou 31-60d", 31, 61),
        ("Parou 61-120d", 61, 121),
        ("Parou 120d+", 121, 9999),
    ]:
        sub_rec = com_uso[(com_uso["dias_desde_ultimo_uso"] >= lo) & (com_uso["dias_desde_ultimo_uso"] < hi)]
        n = len(sub_rec)
        if n < 30:
            continue
        cr = round(100 * sub_rec["churn"].mean(), 1)
        bar = "█" * int(cr / 2)
        print(f"    {faixa_rec:20s}  {cr:5.1f}%  {bar}  ({n:>6,})")
