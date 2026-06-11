"""
Cruza dados de SAC (YALO + DRC) com a base de churn por CPF.
v2: separa cancelamento dos demais, analisa retencao, reincidentes,
    inclusao vs exclusao de dependentes, e timeline detalhada.

Uso:
  1. Rode queries/cruzamento_sac.sql no BigQuery → results/contratos_com_cpf.csv
  2. Rode este script: .venv/bin/python3 scripts/cruzar_sac_churn.py

Saida:
  - results/sac_churn_resumo.csv          (1 linha por contrato enriquecido)
  - results/sac_churn_metricas.csv        (churn: com SAC vs sem SAC, cancelamento vs outros)
  - results/sac_churn_motivos.csv         (churn por motivo — SEM cancelamentos)
  - results/sac_churn_cancelamentos.csv   (analise de retencao dos que pediram cancelamento)
  - results/sac_churn_unidades.csv        (tickets e churn por unidade)
  - results/sac_churn_timeline.csv        (ticket antes/depois do vencimento)
  - results/sac_churn_reincidentes.csv    (pacientes com multiplos tickets)
  - results/sac_churn_dependentes.csv     (inclusao vs exclusao de dependentes)
"""

import pandas as pd
import numpy as np
import re


def normalizar_cpf(cpf):
    if pd.isna(cpf):
        return None
    cpf_limpo = re.sub(r"[^0-9]", "", str(cpf))
    return cpf_limpo if len(cpf_limpo) == 11 else None


print("=" * 60)
print("CRUZAMENTO SAC × CHURN v2")
print("=" * 60)

# ═══════════════════════════════════════════════════════════════
# CARREGAR DADOS
# ═══════════════════════════════════════════════════════════════
print("\n1. Carregando dados...")

df_churn = pd.read_csv("results/contratos_com_cpf.csv")
df_churn["cpf"] = df_churn["cpf"].apply(normalizar_cpf)
df_churn["contract_due_date"] = pd.to_datetime(df_churn["contract_due_date"])
df_churn["contract_register_date"] = pd.to_datetime(df_churn["contract_register_date"])
# Excluir contratos com vencimento nos ultimos 30 dias (churn pode nao ter sido processado)
corte = pd.Timestamp.now() - pd.Timedelta(days=30)
n_antes = len(df_churn)
df_churn = df_churn[df_churn["contract_due_date"] < corte].copy()
print(f"   Contratos: {n_antes:,} → {len(df_churn):,} (excluidos {n_antes - len(df_churn):,} com vencimento < 30 dias)")
print(f"   Com CPF valido: {df_churn['cpf'].notna().sum():,}")

# SAC YALO
df_yalo = pd.read_csv("results/sac_SAC_YALO.csv")
df_yalo["cpf"] = df_yalo["CPF"].apply(normalizar_cpf)
df_yalo["data_ticket"] = pd.to_datetime(df_yalo["Hora da cr"], errors="coerce")
df_yalo["fonte_sac"] = "YALO"
df_yalo["motivo_raw"] = df_yalo["O motivo da ligação é ..."].fillna("")
df_yalo["detalhe_raw"] = df_yalo["Mais detalhe dessa solicitação"].fillna("")
df_yalo["tipo_raw"] = df_yalo["A solicitação é sobre ...."].fillna("")
df_yalo["assunto"] = df_yalo["Assunto"].fillna("")

# Flag: e cancelamento?
df_yalo["eh_cancelamento"] = (
    df_yalo["motivo_raw"].str.lower().str.contains("cancel|estorno", na=False) |
    df_yalo["assunto"].str.lower().str.contains("cancel", na=False)
)

# Detalhe do motivo de cancelamento
def detalhe_cancelamento_yalo(row):
    if not row["eh_cancelamento"]:
        return ""
    d = str(row["detalhe_raw"]).strip()
    if d and d not in ["", "nan", "Solicitação", "Informação", "Reclamação", "No Product"]:
        return d
    m = str(row["motivo_raw"]).strip()
    return m

df_yalo["motivo_cancel"] = df_yalo.apply(detalhe_cancelamento_yalo, axis=1)

# Categorizar motivo (SEM cancelamentos)
def categorizar_yalo(row):
    if row["eh_cancelamento"]:
        return "CANCELAMENTO"
    m = (str(row["motivo_raw"]) + " " + str(row["detalhe_raw"])).lower()
    if "integra" in m or "ativ" in m or "não ativou" in m:
        return "Integracao/Ativacao"
    if "inclusão de dependente" in m:
        return "Dependente: inclusao"
    if "exclusão de dependente" in m:
        return "Dependente: exclusao"
    if "agendamento" in m or "agenda" in m or "consulta" in m:
        return "Agendamento"
    if "reclam" in m:
        return "Reclamacao"
    if "renov" in m:
        return "Renovacao"
    if "suporte" in m or "app" in m or "aplicativo" in m or "erro" in m:
        return "Suporte tecnico"
    if "inform" in m or "confirm" in m:
        return "Informacao"
    if "cadastro" in m or "alter" in m:
        return "Cadastro/Alteracao"
    if "nota fiscal" in m:
        return "Nota fiscal"
    return "Outros"

df_yalo["categoria"] = df_yalo.apply(categorizar_yalo, axis=1)
df_yalo = df_yalo[df_yalo["cpf"].notna()].copy()
print(f"   SAC YALO: {len(df_yalo):,} tickets com CPF valido")

# SAC DRC
df_drc = pd.read_csv("results/sac_SAC_DRC.csv")
df_drc["cpf"] = df_drc["CPF"].apply(normalizar_cpf)
df_drc["data_ticket"] = pd.to_datetime(df_drc["Hora da cr"], errors="coerce")
df_drc["fonte_sac"] = "DRC"
df_drc["motivo_raw"] = df_drc["MOTIVO"].fillna("")
df_drc["detalhe_raw"] = df_drc["Submotivo"].fillna("")
df_drc["assunto"] = df_drc["Assunto"].fillna("")
df_drc["eh_cancelamento"] = False  # DRC nao tem cancelamentos de assinatura
df_drc["motivo_cancel"] = ""

def categorizar_drc(row):
    m = (str(row["motivo_raw"]) + " " + str(row["detalhe_raw"])).lower()
    if "agendamento" in m or "agenda" in m:
        return "Agendamento"
    if "atendimento" in m or "conduta" in m or "postura" in m:
        return "Atendimento/Conduta"
    if "exame" in m or "resultado" in m or "laudo" in m:
        return "Exames/Resultados"
    if "documento" in m or "receita" in m or "atestado" in m:
        return "Documentos"
    if "estorno" in m or "financeiro" in m or "reembolso" in m:
        return "Financeiro/Estorno"
    if "reclam" in m:
        return "Reclamacao geral"
    if "suporte" in m or "app" in m:
        return "Suporte tecnico"
    if "solicita" in m:
        return "Solicitacao geral"
    return "Outros DRC"

df_drc["categoria"] = df_drc.apply(categorizar_drc, axis=1)
df_drc = df_drc[df_drc["cpf"].notna()].copy()
print(f"   SAC DRC: {len(df_drc):,} tickets com CPF valido")


# ═══════════════════════════════════════════════════════════════
# AGREGAR POR CPF
# ═══════════════════════════════════════════════════════════════
print("\n2. Agregando por CPF...")

cols_sac = ["cpf", "data_ticket", "fonte_sac", "categoria", "eh_cancelamento", "motivo_cancel"]
df_sac = pd.concat([df_yalo[cols_sac], df_drc[cols_sac]], ignore_index=True)

sac_por_cpf = df_sac.groupby("cpf").agg(
    qtd_tickets=("cpf", "count"),
    primeiro_ticket=("data_ticket", "min"),
    ultimo_ticket=("data_ticket", "max"),
    teve_cancelamento=("eh_cancelamento", "max"),
    tickets_cancel=("eh_cancelamento", "sum"),
    categorias=("categoria", lambda x: " | ".join(sorted(x.unique()))),
    categoria_principal=("categoria", lambda x: x.value_counts().index[0]),
    fontes=("fonte_sac", lambda x: "+".join(sorted(x.unique()))),
).reset_index()

# Flag: so cancelamento, so outros, ou ambos
sac_por_cpf["tipo_contato"] = sac_por_cpf.apply(
    lambda r: "So cancelamento" if r["tickets_cancel"] == r["qtd_tickets"]
    else "Cancelamento + outros" if r["teve_cancelamento"]
    else "Outros (sem cancelamento)",
    axis=1
)

print(f"   CPFs unicos no SAC: {len(sac_por_cpf):,}")
print(f"   - So cancelamento: {(sac_por_cpf['tipo_contato'] == 'So cancelamento').sum():,}")
print(f"   - Cancel + outros: {(sac_por_cpf['tipo_contato'] == 'Cancelamento + outros').sum():,}")
print(f"   - Outros: {(sac_por_cpf['tipo_contato'] == 'Outros (sem cancelamento)').sum():,}")


# ═══════════════════════════════════════════════════════════════
# MERGE COM CHURN
# ═══════════════════════════════════════════════════════════════
print("\n3. Cruzando com base de churn...")

df_merged = df_churn.merge(sac_por_cpf, on="cpf", how="left")
df_merged["teve_sac"] = df_merged["qtd_tickets"].notna().astype(int)
df_merged["qtd_tickets"] = df_merged["qtd_tickets"].fillna(0).astype(int)
df_merged["tipo_contato"] = df_merged["tipo_contato"].fillna("Sem SAC")
df_merged["teve_cancelamento"] = df_merged["teve_cancelamento"].fillna(False)
df_merged["categoria_principal"] = df_merged["categoria_principal"].fillna("Sem SAC")

# Dias entre primeiro ticket e vencimento
df_merged["dias_ticket_vs_venc"] = np.where(
    df_merged["primeiro_ticket"].notna(),
    (df_merged["contract_due_date"] - pd.to_datetime(df_merged["primeiro_ticket"])).dt.days,
    np.nan
)

match_count = df_merged["teve_sac"].sum()
total = len(df_merged)
print(f"   Total contratos: {total:,}")
print(f"   Com SAC: {match_count:,} ({100*match_count/total:.1f}%)")


# ═══════════════════════════════════════════════════════════════
# GERAR CSVs
# ═══════════════════════════════════════════════════════════════
print("\n4. Gerando CSVs...")

# --- 1. Resumo por contrato ---
df_merged.to_csv("results/sac_churn_resumo.csv", index=False)
print(f"   sac_churn_resumo.csv: {len(df_merged):,} linhas")

# --- 2. Metricas: 4 grupos ---
def calc_metricas(grupo_df, nome):
    n = len(grupo_df)
    if n == 0:
        return None
    ch = (grupo_df["churn_sn"] == "S").sum()
    ativo = (grupo_df["tipo_desfecho"] == "churn_ativo").sum()
    silen = (grupo_df["tipo_desfecho"] == "churn_silencioso").sum()
    ret = (grupo_df["tipo_desfecho"] == "retido").sum()
    return {
        "grupo": nome, "contratos": n, "churners": ch,
        "churn_rate": round(100 * ch / n, 2),
        "retidos": ret, "pct_retidos": round(100 * ret / n, 1),
        "churn_ativo": ativo, "churn_silencioso": silen,
        "ticket_medio": round(grupo_df["qtd_tickets"].mean(), 1),
    }

metricas = [
    calc_metricas(df_merged[df_merged["tipo_contato"] == "Sem SAC"], "Sem SAC"),
    calc_metricas(df_merged[df_merged["tipo_contato"] == "Outros (sem cancelamento)"], "SAC (sem cancelamento)"),
    calc_metricas(df_merged[df_merged["tipo_contato"] == "So cancelamento"], "SAC (so cancelamento)"),
    calc_metricas(df_merged[df_merged["tipo_contato"] == "Cancelamento + outros"], "SAC (cancel + outros)"),
]
metricas = [m for m in metricas if m]
pd.DataFrame(metricas).to_csv("results/sac_churn_metricas.csv", index=False)
print(f"   sac_churn_metricas.csv")

# --- 3. Motivos (SEM cancelamentos) ---
outros = df_merged[(df_merged["teve_sac"] == 1) & (~df_merged["teve_cancelamento"])]
motivos = []
for cat, grp in outros.groupby("categoria_principal"):
    n = len(grp)
    if n < 10:
        continue
    ch = (grp["churn_sn"] == "S").sum()
    motivos.append({
        "categoria": cat, "contratos": n, "churners": ch,
        "churn_rate": round(100 * ch / n, 2),
        "ticket_medio": round(grp["qtd_tickets"].mean(), 1),
    })
pd.DataFrame(motivos).sort_values("churn_rate", ascending=False).to_csv(
    "results/sac_churn_motivos.csv", index=False
)
print(f"   sac_churn_motivos.csv")

# --- 4. Cancelamentos: analise de retencao ---
canceladores = df_merged[df_merged["teve_cancelamento"] == True].copy()
if len(canceladores) > 0:
    n_cancel = len(canceladores)
    churnou = (canceladores["churn_sn"] == "S").sum()
    retido = (canceladores["churn_sn"] == "N").sum()

    # Motivos detalhados do cancelamento (do SAC YALO)
    cancel_motivos = df_yalo[df_yalo["eh_cancelamento"]].groupby("motivo_cancel").size()
    cancel_motivos = cancel_motivos.reset_index(name="tickets").sort_values("tickets", ascending=False)

    # Cruzar motivo do cancelamento com churn
    cancel_cpf_motivo = df_yalo[df_yalo["eh_cancelamento"]][["cpf", "motivo_cancel"]].drop_duplicates("cpf")
    canceladores_m = canceladores.merge(cancel_cpf_motivo, on="cpf", how="left")

    cancel_por_motivo = []
    for motivo, grp in canceladores_m.groupby("motivo_cancel"):
        if pd.isna(motivo) or str(motivo).strip() == "" or len(grp) < 5:
            continue
        n = len(grp)
        ch = (grp["churn_sn"] == "S").sum()
        cancel_por_motivo.append({
            "motivo_cancelamento": motivo, "contratos": n,
            "churnou": ch, "retido": n - ch,
            "churn_rate": round(100 * ch / n, 1),
            "taxa_retencao": round(100 * (n - ch) / n, 1),
        })

    df_cancel = pd.DataFrame(cancel_por_motivo).sort_values("contratos", ascending=False)
    df_cancel.to_csv("results/sac_churn_cancelamentos.csv", index=False)
    print(f"   sac_churn_cancelamentos.csv: {n_cancel:,} contratos ({churnou} churnou, {retido} retido)")

# --- 5. Unidades ---
if "unidade_principal" in df_merged.columns:
    unidades = []
    for uni, grp in df_merged.groupby("unidade_principal"):
        if pd.isna(uni) or str(uni).strip() == "" or len(grp) < 30:
            continue
        n = len(grp)
        ch = (grp["churn_sn"] == "S").sum()
        com_sac = grp["teve_sac"].sum()
        com_cancel = grp["teve_cancelamento"].sum()
        unidades.append({
            "unidade": uni, "contratos": n,
            "churners": ch, "churn_rate": round(100 * ch / n, 2),
            "com_sac": com_sac, "pct_com_sac": round(100 * com_sac / n, 2),
            "com_cancelamento": int(com_cancel),
        })
    pd.DataFrame(unidades).sort_values("churn_rate", ascending=False).to_csv(
        "results/sac_churn_unidades.csv", index=False
    )
    print(f"   sac_churn_unidades.csv")

# --- 6. Timeline ---
timeline = []
faixas = [
    ((-999, -60), "60+ dias antes"),
    ((-60, -30), "30-60 dias antes"),
    ((-30, -7), "7-30 dias antes"),
    ((-7, 0), "0-7 dias antes"),
    ((0, 7), "0-7 dias depois"),
    ((7, 30), "7-30 dias depois"),
    ((30, 999), "30+ dias depois"),
]
for (lo, hi), label in faixas:
    for tipo in ["Outros (sem cancelamento)", "So cancelamento"]:
        sub = df_merged[
            (df_merged["dias_ticket_vs_venc"] >= lo) &
            (df_merged["dias_ticket_vs_venc"] < hi) &
            (df_merged["tipo_contato"] == tipo)
        ]
        n = len(sub)
        if n == 0:
            continue
        ch = (sub["churn_sn"] == "S").sum()
        timeline.append({
            "janela": label, "tipo_contato": tipo,
            "contratos": n, "churners": ch,
            "churn_rate": round(100 * ch / n, 2),
        })
pd.DataFrame(timeline).to_csv("results/sac_churn_timeline.csv", index=False)
print(f"   sac_churn_timeline.csv")

# --- 7. Reincidentes ---
reincidentes = sac_por_cpf[sac_por_cpf["qtd_tickets"] >= 2].copy()
reinc_merged = reincidentes.merge(
    df_churn[["cpf", "churn_sn", "tipo_desfecho", "contract_due_date"]].drop_duplicates("cpf"),
    on="cpf", how="inner"
)
reinc_agg = []
for n_tickets in [2, 3, "4+"]:
    if n_tickets == "4+":
        sub = reinc_merged[reinc_merged["qtd_tickets"] >= 4]
    else:
        sub = reinc_merged[reinc_merged["qtd_tickets"] == n_tickets]
    n = len(sub)
    if n == 0:
        continue
    ch = (sub["churn_sn"] == "S").sum()
    reinc_agg.append({
        "tickets": str(n_tickets), "pacientes": n,
        "churners": ch, "churn_rate": round(100 * ch / n, 1),
    })
pd.DataFrame(reinc_agg).to_csv("results/sac_churn_reincidentes.csv", index=False)
print(f"   sac_churn_reincidentes.csv")

# --- 8. Dependentes: inclusao vs exclusao ---
dep_yalo = df_yalo[df_yalo["categoria"].str.contains("Dependente")].copy()
if len(dep_yalo) > 0:
    dep_merged = dep_yalo[["cpf", "categoria"]].drop_duplicates("cpf").merge(
        df_churn[["cpf", "churn_sn", "tipo_desfecho"]].drop_duplicates("cpf"),
        on="cpf", how="inner"
    )
    dep_agg = []
    for cat, grp in dep_merged.groupby("categoria"):
        n = len(grp)
        ch = (grp["churn_sn"] == "S").sum()
        dep_agg.append({
            "tipo_dependente": cat, "contratos": n,
            "churners": ch, "churn_rate": round(100 * ch / n, 1),
        })
    pd.DataFrame(dep_agg).to_csv("results/sac_churn_dependentes.csv", index=False)
    print(f"   sac_churn_dependentes.csv")


# ═══════════════════════════════════════════════════════════════
# RESUMO FINAL
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("RESUMO")
print("=" * 60)

for m in metricas:
    print(f"\n  {m['grupo']}:")
    print(f"    Contratos: {m['contratos']:,}")
    print(f"    Churn: {m['churn_rate']}%")
    print(f"    Retidos: {m['pct_retidos']}%")

if len(canceladores) > 0:
    print(f"\n  RETENCAO DE CANCELAMENTOS:")
    print(f"    Pediram cancelamento: {n_cancel:,}")
    print(f"    Churnou de fato: {churnou:,} ({100*churnou/n_cancel:.1f}%)")
    print(f"    Retido (nao saiu): {retido:,} ({100*retido/n_cancel:.1f}%)")

print("\nArquivos gerados em results/sac_churn_*.csv")
