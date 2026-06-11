"""
Analisa o poder preditivo das features de experiencia (fat_atendimento).
Mostra churn rate por faixa de cada feature.
"""
import pandas as pd
import numpy as np

df = pd.read_csv("results/features_experiencia.csv")
df["churn"] = (df["churn_sn"] == "S").astype(int)

total = len(df)
com_atend = (df["qtd_atendimentos"] > 0).sum()
com_nps = (df["qtd_com_nps"] > 0).sum()
com_tempo = (df["qtd_com_tempo"] > 0).sum()

print(f"Total: {total:,} contratos")
print(f"Churn global: {100*df['churn'].mean():.1f}%")
print(f"Com atendimento: {com_atend:,} ({100*com_atend/total:.1f}%)")
print(f"Com NPS: {com_nps:,} ({100*com_nps/total:.1f}%)")
print(f"Com tempo: {com_tempo:,} ({100*com_tempo/total:.1f}%)")

def analise(df_sub, col, label, sort_by_churn=True):
    print(f"\n{'='*65}")
    print(f"{label}")
    print(f"{'='*65}")
    grp = df_sub.groupby(col).agg(
        n=("churn", "count"),
        churners=("churn", "sum"),
    ).reset_index()
    grp["churn_rate"] = (100 * grp["churners"] / grp["n"]).round(1)
    if sort_by_churn:
        grp = grp.sort_values("churn_rate", ascending=False)
    for _, r in grp.iterrows():
        bar = "█" * int(r["churn_rate"] / 2)
        print(f"  {str(r[col]):25s}  {r['churn_rate']:5.1f}%  {bar}  ({int(r['n']):>7,})")
    spread = grp["churn_rate"].max() - grp["churn_rate"].min()
    print(f"  SPREAD: {spread:.1f} p.p.")
    return spread

spreads = {}

# ═══════════════════════════════════════════════════════════════
# 1. NPS
# ═══════════════════════════════════════════════════════════════
spreads["NPS (faixa)"] = analise(df, "faixa_nps", "NPS — FAIXA (promotor/neutro/detrator)")

# NPS numerico (quem tem NPS)
nps_df = df[df["qtd_com_nps"] > 0].copy()
if len(nps_df) > 0:
    nps_df["faixa_nps_num"] = pd.cut(
        nps_df["nps_medio"], bins=[-1, 5, 7, 8, 9, 10.1],
        labels=["0-5", "6-7", "8", "9", "10"]
    )
    spreads["NPS (numerico)"] = analise(nps_df, "faixa_nps_num", "NPS — NOTA NUMERICA (quem tem NPS)")

# ═══════════════════════════════════════════════════════════════
# 2. NOTA DO MEDICO
# ═══════════════════════════════════════════════════════════════
med_df = df[df["nota_medico_media"].notna()].copy()
if len(med_df) > 0:
    med_df["faixa_nota_med"] = pd.cut(
        med_df["nota_medico_media"], bins=[-0.1, 2, 3, 4, 5.1],
        labels=["1-2", "3", "4", "5"]
    )
    spreads["Nota medico"] = analise(med_df, "faixa_nota_med", "NOTA DO MEDICO (1-5)")

# ═══════════════════════════════════════════════════════════════
# 3. NOTA DO ATENDIMENTO
# ═══════════════════════════════════════════════════════════════
atd_df = df[df["nota_atendimento_media"].notna()].copy()
if len(atd_df) > 0:
    atd_df["faixa_nota_atd"] = pd.cut(
        atd_df["nota_atendimento_media"], bins=[-0.1, 2, 3, 4, 5.1],
        labels=["1-2", "3", "4", "5"]
    )
    spreads["Nota atendimento"] = analise(atd_df, "faixa_nota_atd", "NOTA DO ATENDIMENTO (1-5)")

# ═══════════════════════════════════════════════════════════════
# 4. TEMPO TOTAL NA CLINICA
# ═══════════════════════════════════════════════════════════════
tempo_df = df[df["qtd_com_tempo"] > 0].copy()
if len(tempo_df) > 0:
    # Converter pra minutos
    tempo_df["tempo_total_min"] = tempo_df["tempo_total_medio"] / 60
    tempo_df["faixa_tempo"] = pd.cut(
        tempo_df["tempo_total_min"], bins=[-1, 15, 30, 60, 90, 120, 9999],
        labels=["<15min", "15-30min", "30-60min", "60-90min", "90-120min", "120min+"]
    )
    spreads["Tempo total"] = analise(tempo_df, "faixa_tempo", "TEMPO TOTAL NA CLINICA (minutos)", sort_by_churn=False)

# ═══════════════════════════════════════════════════════════════
# 5. TEMPO NA RECEPCAO
# ═══════════════════════════════════════════════════════════════
rec_df = df[df["tempo_recepcao_medio"].notna() & (df["tempo_recepcao_medio"] > 0)].copy()
if len(rec_df) > 0:
    rec_df["tempo_rec_min"] = rec_df["tempo_recepcao_medio"] / 60
    rec_df["faixa_rec"] = pd.cut(
        rec_df["tempo_rec_min"], bins=[-1, 1, 2, 5, 10, 9999],
        labels=["<1min", "1-2min", "2-5min", "5-10min", "10min+"]
    )
    spreads["Tempo recepcao"] = analise(rec_df, "faixa_rec", "TEMPO NA RECEPCAO (minutos)", sort_by_churn=False)

# ═══════════════════════════════════════════════════════════════
# 6. ROTATIVIDADE DE PROFISSIONAIS
# ═══════════════════════════════════════════════════════════════
spreads["Rotatividade"] = analise(df, "padrao_profissional", "PADRAO PROFISSIONAL (rotatividade vs continuidade)")

# Profissionais por atendimento
prof_df = df[df["qtd_atendimentos"] > 0].copy()
if len(prof_df) > 0:
    prof_df["prof_por_esp"] = prof_df["qtd_profissionais"] / prof_df["qtd_especialidades"].clip(lower=1)
    prof_df["faixa_prof"] = pd.cut(
        prof_df["prof_por_esp"], bins=[-0.1, 1, 1.5, 2, 99],
        labels=["1 med/esp", "1-1.5 med/esp", "1.5-2 med/esp", "2+ med/esp"]
    )
    spreads["Medicos por especialidade"] = analise(prof_df, "faixa_prof", "MEDICOS POR ESPECIALIDADE (rotatividade)")

# ═══════════════════════════════════════════════════════════════
# 7. ENCAMINHAMENTO
# ═══════════════════════════════════════════════════════════════
df["encaminhamento_label"] = df["teve_encaminhamento"].map({0: "Sem encaminhamento", 1: "Com encaminhamento"}).fillna("Sem atendimento")
spreads["Encaminhamento"] = analise(df, "encaminhamento_label", "ENCAMINHAMENTO MEDICO")

# ═══════════════════════════════════════════════════════════════
# RESUMO
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*65}")
print("RESUMO: SPREAD DE CADA FEATURE DE EXPERIENCIA")
print(f"{'='*65}")
for feat, spread in sorted(spreads.items(), key=lambda x: -x[1]):
    bar = "█" * int(spread)
    print(f"  {feat:30s}  {spread:5.1f} p.p.  {bar}")

# Comparar com features demograficas
print(f"\n  {'─'*50}")
print(f"  Pra referencia (features demograficas do score WLS):")
print(f"  Ciclo (1o vs 2o+):           ~10 p.p.")
print(f"  Dependentes (0 vs 3+):       ~10 p.p.")
print(f"  Idade (21-30 vs 61-70):      ~13 p.p.")
print(f"  Cronico (N vs S):            ~ 6 p.p.")
