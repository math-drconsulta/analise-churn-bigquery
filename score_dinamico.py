"""
Score Dinamico de Churn v3 — perfil + comportamento + SAC + experiencia.

4 camadas:
  1. Perfil (estatico): quem a pessoa e
  2. Comportamento: uso do plano, pagamento, timing
  3. SAC: historico de contato com atendimento
  4. Experiencia: NPS, rotatividade de medicos, engajamento na clinica

Score final: 0-1000 (alto = mais seguro)
Usado pelo app_operacional.py.
"""

import numpy as np
import pandas as pd


# ═══════════════════════════════════════════════════════════════════
# PENALIDADES DO PERFIL (derivadas do WLS — valores fixos)
# ═══════════════════════════════════════════════════════════════════

SCORE_BASE = 700

PENALIDADES_PERFIL = {
    "ciclo": {
        "1o": -120,
        "2o+": 0,
    },
    "faixa_dependentes": {
        "sem_dep": -100,
        "1-2_dep": -40,
        "3+_dep": 0,
    },
    "cronico": {
        "N": -60,
        "S": 0,
    },
    "perfil_idade": {
        "jovem_00-30": -80,
        "adulto_31-50": -30,
        "senior_51+": 0,
    },
    "duracao": {
        "6": 0,
        "12": -50,
    },
    "canal": {
        "digital": -30,
        "presencial_cfp": 0,
        "drc_digital": -30,
        "drc_cm": 0,
        "drc_cfp": 0,
        "outros": -15,
    },
}


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════

def _safe_int(val, default=0):
    if val is None:
        return default
    try:
        v = float(val)
        return default if np.isnan(v) else int(v)
    except (ValueError, TypeError):
        return default


def _safe_float(val, default=None):
    if val is None:
        return default
    try:
        v = float(val)
        return default if np.isnan(v) else v
    except (ValueError, TypeError):
        return default


# ═══════════════════════════════════════════════════════════════════
# CAMADA 2: COMPORTAMENTO
# ═══════════════════════════════════════════════════════════════════

def calcular_sinal_uso(row):
    total_itens = _safe_int(row.get("total_itens", 0))
    consumiu = str(row.get("consumiu", "N"))
    dias_sem_uso = _safe_float(row.get("dias_sem_uso", None))

    score = 0
    if consumiu == "N" or total_itens == 0:
        score -= 100
    elif total_itens <= 2:
        score -= 30
    elif total_itens >= 5:
        score += 50

    if dias_sem_uso is not None:
        if dias_sem_uso > 120:
            score -= 60
        elif dias_sem_uso > 60:
            score -= 30
        elif dias_sem_uso <= 30:
            score += 30

    return score


def calcular_sinal_pagamento(row):
    falhas = _safe_int(row.get("pgto_falhas_90d", 0))
    tentativas = _safe_int(row.get("pgto_tentativas_90d", 0))

    if tentativas == 0:
        return 0

    taxa_falha = falhas / tentativas
    if falhas >= 3 or taxa_falha > 0.5:
        return -80
    elif falhas >= 1:
        return -40
    else:
        return 20


def calcular_sinal_timing(row):
    dias = _safe_int(row.get("dias_ate_vencimento", 30), default=30)

    if dias < 0:
        return -50
    elif dias <= 7:
        return -30
    elif dias <= 14:
        return -15
    else:
        return 0


def calcular_sinal_cancelamento(row):
    val = row.get("pediu_cancelamento", False)
    if val is True or str(val).lower() == "true":
        return -200
    return 0


# ═══════════════════════════════════════════════════════════════════
# CAMADA 3: SAC (corrigido com dados v3)
# ═══════════════════════════════════════════════════════════════════

def calcular_sinal_sac(row):
    """Sinal baseado no historico de SAC.

    Dados corrigidos (v3):
    - SAC sem cancelamento: 48.2% churn (ABAIXO da base 54.4%) → SAC protege
    - Exclusao dependente: 20.2% churn → paciente ficando, sinal positivo
    - Integracao resolvida: 34.3% churn → SAC resolveu, sinal positivo
    - Cancelamento: 68.6% churn → maioria sai
    """
    teve_sac = _safe_int(row.get("sac_teve_sac", 0))
    if not teve_sac:
        return 0

    score = 0
    tipo_contato = str(row.get("sac_tipo_contato", ""))
    categoria = str(row.get("sac_categoria_principal", ""))

    # Exclusao de dependente: 20.2% churn — muito abaixo da base → PROTEGE
    if "exclusao" in categoria.lower():
        score += 80

    # Integracao/ativacao resolvida: 34.3% churn — abaixo da base → SAC resolveu
    elif "integracao" in categoria.lower() or "ativacao" in categoria.lower():
        score += 50

    # Reclamacao/agendamento: ~50-51% churn — proximo da base mas abaixo
    elif "reclam" in categoria.lower() or "agendamento" in categoria.lower():
        score += 10

    # Financeiro/estorno: 58% churn — acima da base → risco
    elif "financeiro" in categoria.lower() or "estorno" in categoria.lower():
        score -= 20

    # Pediu cancelamento: 68.6% churn → alto risco
    if "cancelamento" in tipo_contato.lower():
        score -= 80

    # Reincidente (multiplos tickets) — leve protecao (engajamento)
    qtd_tickets = _safe_int(row.get("sac_qtd_tickets", 0))
    if qtd_tickets >= 3:
        score += 10
    elif qtd_tickets >= 2:
        score += 5

    return score


# ═══════════════════════════════════════════════════════════════════
# CAMADA 4: EXPERIENCIA (fat_atendimento)
# ═══════════════════════════════════════════════════════════════════

def calcular_sinal_experiencia(row):
    """Sinal baseado na experiencia real do paciente na clinica.

    3 features validadas:
    1. Rotatividade de medicos: 10 p.p. de spread (53.4% → 63.4%)
    2. NPS: 8.9 p.p. de spread (50.1% → 59.0%)
    3. Tempo na clinica (engajamento): 8.5 p.p. de spread controlado
    """
    score = 0

    # --- 1. Rotatividade de medicos ---
    # Spread: 1 med/esp = 53.4% → 2+ med/esp = 63.4% (10 p.p.)
    qtd_prof = _safe_int(row.get("exp_qtd_profissionais", 0))
    qtd_esp = _safe_int(row.get("exp_qtd_especialidades", 0))

    if qtd_esp > 0 and qtd_prof > 0:
        prof_por_esp = qtd_prof / qtd_esp
        if prof_por_esp >= 2.0:
            score -= 80    # alta rotatividade — risco forte
        elif prof_por_esp >= 1.5:
            score -= 40    # rotatividade moderada
        elif prof_por_esp <= 1.0:
            score += 20    # continuidade — bom sinal

    # --- 2. NPS ---
    # Spread: NPS 0-5 = 59.0% → NPS 9 = 50.1% (8.9 p.p.)
    nps = _safe_float(row.get("exp_nps_medio"))
    if nps is not None:
        if nps <= 5:
            score -= 60    # detrator forte
        elif nps <= 7:
            score -= 25    # neutro/detrator leve
        elif nps >= 9:
            score += 40    # promotor
        else:
            score += 10    # nota 8 — levemente positivo

    # --- 3. Tempo na clinica como proxy de engajamento ---
    # Spread controlado por ciclo: <10min = 63.4% → 30-45min = 55.0% (8.4 p.p.)
    # Direcao: mais tempo = mais engajado = menos churn
    tempo_total = _safe_float(row.get("exp_tempo_total_medio"))
    if tempo_total is not None and tempo_total > 0:
        tempo_min = tempo_total / 60  # converter segundos pra minutos
        if tempo_min < 10:
            score -= 40    # visita muito curta — pouco engajamento
        elif tempo_min < 20:
            score -= 15
        elif tempo_min >= 30:
            score += 30    # visita longa — engajado
        elif tempo_min >= 20:
            score += 10

    return score


# ═══════════════════════════════════════════════════════════════════
# FUNCAO PRINCIPAL
# ═══════════════════════════════════════════════════════════════════

def calcular_score_dinamico(df: pd.DataFrame) -> pd.DataFrame:
    """
    Recebe o DataFrame da query operacional e retorna com colunas adicionais:
    - score_perfil: camada 1 (demografico)
    - score_uso: camada 2a (uso do plano)
    - score_pgto: camada 2b (pagamento)
    - score_timing: camada 2c (proximidade do vencimento)
    - score_cancel: camada 2d (pedido de cancelamento)
    - score_sac: camada 3 (historico SAC)
    - score_exp: camada 4 (experiencia na clinica)
    - score_total: score final (0-1000)
    - risco: classificacao textual
    - acao_sugerida: acao recomendada
    """
    df = df.copy()

    # Converter pediu_cancelamento
    if "pediu_cancelamento" in df.columns:
        df["pediu_cancelamento"] = df["pediu_cancelamento"].astype(str).str.lower() == "true"

    # Preencher NaN em colunas categoricas
    for col in ["perfil_idade", "canal", "faixa_dependentes", "cronico", "ciclo", "duracao", "consumiu"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)

    # Preencher NaN em colunas numericas
    for col in ["total_itens", "dias_sem_uso", "pgto_falhas_90d", "pgto_tentativas_90d",
                "pgto_sucessos_90d", "dias_ate_vencimento"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # ── Camada 1: Perfil ──
    df["score_perfil"] = SCORE_BASE
    for var, mapa in PENALIDADES_PERFIL.items():
        if var in df.columns:
            for nivel, pts in mapa.items():
                mask = df[var] == str(nivel)
                df.loc[mask, "score_perfil"] = df.loc[mask, "score_perfil"] + pts

    # ── Camada 2: Comportamento ──
    df["score_uso"] = df.apply(calcular_sinal_uso, axis=1).astype(int)
    df["score_pgto"] = df.apply(calcular_sinal_pagamento, axis=1).astype(int)
    df["score_timing"] = df.apply(calcular_sinal_timing, axis=1).astype(int)
    df["score_cancel"] = df.apply(calcular_sinal_cancelamento, axis=1).astype(int)

    # ── Camada 3: SAC ──
    df["score_sac"] = df.apply(calcular_sinal_sac, axis=1).astype(int)

    # ── Camada 4: Experiencia ──
    df["score_exp"] = df.apply(calcular_sinal_experiencia, axis=1).astype(int)

    # ── Score total ──
    df["score_total"] = (
        df["score_perfil"]
        + df["score_uso"]
        + df["score_pgto"]
        + df["score_timing"]
        + df["score_cancel"]
        + df["score_sac"]
        + df["score_exp"]
    ).clip(0, 1000).astype(int)

    # ── Classificacao de risco ──
    df["risco"] = pd.cut(
        df["score_total"],
        bins=[-1, 200, 400, 600, 800, 1001],
        labels=["CRITICO", "ALTO", "MEDIO", "BAIXO", "SEGURO"],
    )

    # ── Acao sugerida ──
    def sugerir_acao(row):
        if row.get("pediu_cancelamento", False):
            return "Entrevista de retencao urgente"
        if row.get("urgencia") == "VENCIDO":
            return "Win-back: contato imediato"

        acoes = []

        # Sinais de experiencia (prioridade alta)
        nps = _safe_float(row.get("exp_nps_medio"))
        if nps is not None and nps <= 5:
            acoes.append("NPS detrator: contato pos-consulta urgente")

        qtd_prof = _safe_int(row.get("exp_qtd_profissionais", 0))
        qtd_esp = _safe_int(row.get("exp_qtd_especialidades", 0))
        if qtd_esp > 0 and qtd_prof > 0 and (qtd_prof / qtd_esp) >= 2:
            acoes.append("Rotatividade alta: garantir mesmo medico na proxima")

        # Sinais SAC
        sac_cat = str(row.get("sac_categoria_principal", ""))
        if "integracao" in sac_cat.lower() or "ativacao" in sac_cat.lower():
            acoes.append("SAC: integracao falha — resolver ativacao em 24h")

        # Sinais operacionais
        if _safe_int(row.get("pgto_falhas_90d", 0)) >= 1:
            acoes.append("Atualizar meio de pagamento")
        if str(row.get("consumiu", "N")) == "N" or _safe_int(row.get("total_itens", 0)) == 0:
            acoes.append("Onboarding: agendar 1a consulta")
        if _safe_float(row.get("dias_sem_uso"), 0) > 90:
            acoes.append("Re-engajamento: lembrar beneficios")
        if _safe_int(row.get("dias_ate_vencimento", 60), 60) <= 30:
            acoes.append("Regua pre-vencimento")

        if not acoes:
            if row.get("score_total", 500) >= 600:
                return "Monitorar (baixo risco)"
            return "Acompanhamento padrao"

        return " + ".join(acoes)

    df["acao_sugerida"] = df.apply(sugerir_acao, axis=1)

    return df
