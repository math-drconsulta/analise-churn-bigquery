-- ============================================================================
-- QUERY CC-4: UNIDADE, EVOLUÇÃO TEMPORAL E SCORE — APENAS CREDIT_CARD
-- Base: anl_churn_contratos | Filtro: planos 6+12m + credit_card + sem B2B/COOP
-- ============================================================================

-- 4A) CHURN POR UNIDADE PRINCIPAL
SELECT
  IFNULL(contract_unidade_principal, '(sem consumo)') as unidade,
  COUNT(*) as total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) as churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) as churn_rate,
  ROUND(AVG(IFNULL(qtd_TOTAL_CM, 0) + IFNULL(qtd_TOTAL_EXAMES, 0)), 1) as media_itens
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1
HAVING COUNT(*) >= 50
ORDER BY churn_rate DESC;


-- ============================================================================
-- 4B) EVOLUÇÃO TEMPORAL: churn por mês de vencimento
-- ============================================================================

SELECT
  contract_due_date_month as mes_vencimento,
  CAST(plan_months_duration AS STRING) as duracao,
  COUNT(*) as total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) as churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) as churn_rate
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2
ORDER BY 1, 2;


-- ============================================================================
-- 4C) SCORE DE RISCO DE CHURN — Escala 0-1000 (alto = seguro)
--
-- Metodologia:
--   Regressão linear ponderada (WLS) sobre log-odds de churn dos perfis
--   compostos de 5 variáveis. Coeficientes convertidos para escala 0-1000.
--
-- Modelo: score = 1000 - sum(penalidades)
--   Perfil referência (score 1000): 2o+ contrato, 3+ dep, 51-70 anos, 6m, crônico
--   Cada fator de risco subtrai pontos proporcionais ao seu efeito real.
--
-- Validação:
--   MAE = 1.64 p.p. | Correlação = 0.97 | Monotônico em todas as faixas
--
-- Variáveis REMOVIDAS (vs score anterior):
--   consumo_sn  → confounded com ciclo do contrato (efeito invertido)
--   classe_social → gap < 2 p.p., sem poder discriminante
--   order_source → não testado com rigor
--   unsubscription_sn → tautologia (98.7% de churn se pediu cancelamento)
--   dep_idoso → já capturado por dependentes_per_holder (dupla contagem)
-- ============================================================================

WITH scored AS (
  SELECT
    contract_id,
    churn_renovacao_automatica_sn,
    plan_months_duration,

    -- Score: começa em 1000 (menor risco) e subtrai penalidades
    1000

    -- #1 Idade: jovens têm mais risco (coef WLS: +0.4498 log-odds → -261 pts)
    - CASE
        WHEN titular_idade <= 30 THEN 261   -- ≤30: maior penalidade
        WHEN titular_idade <= 50 THEN 131   -- 31-50: penalidade moderada
        WHEN titular_idade <= 70 THEN 0     -- 51-70: referência
        ELSE -18                            -- 71+: ligeiro bônus (+18 pts)
      END

    -- #2 Dependentes: sem dependentes = mais risco (coef: +0.4232 → -246 pts)
    - CASE
        WHEN dependents_per_holder = 0 THEN 246         -- sem dep: maior penalidade
        WHEN dependents_per_holder IN (1, 2) THEN 134   -- 1-2 dep: intermediário
        ELSE 0                                          -- 3+ dep: referência
      END

    -- #3 Duração: 12m mais arriscado (coef: +0.3525 → -205 pts)
    -- Efeito controlado: 6m=45.0% vs 12m=54.0% no 2o+ contrato (9 p.p.)
    - CASE WHEN plan_months_duration = 12 THEN 205 ELSE 0 END

    -- #4 Contrato: 1o contrato = mais risco (coef: +0.3239 → -188 pts)
    - CASE WHEN account_contract_number = 1 THEN 188 ELSE 0 END

    -- #5 Crônico: não crônico = mais risco (coef: +0.1422 → -83 pts)
    -- Efeito controlado por idade: ~3.5-4.6 p.p. (real para 31+)
    - CASE WHEN titular_main_cronico_sn = 'N' THEN 83 ELSE 0 END

    AS score_churn

  FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
  WHERE plan_months_duration IN (6, 12)
    AND order_payment_method = 'credit_card'
    AND IFNULL(order_source_aj, '') != 'b2b'
    AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
)

SELECT
  CASE
    WHEN score_churn < 200 THEN '1_CRITICO (0-199)'
    WHEN score_churn < 400 THEN '2_ALTO (200-399)'
    WHEN score_churn < 600 THEN '3_MEDIO (400-599)'
    WHEN score_churn < 800 THEN '4_BAIXO (600-799)'
    ELSE '5_MINIMO (800-1000)'
  END as faixa_risco,

  COUNT(*) as total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) as churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) as churn_rate,
  ROUND(AVG(score_churn), 1) as score_medio,
  MIN(score_churn) as score_min,
  MAX(score_churn) as score_max

FROM scored
GROUP BY 1
ORDER BY 1;