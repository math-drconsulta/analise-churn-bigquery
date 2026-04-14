-- ============================================================================
-- QUERY CC-4: UNIDADE, EVOLUÇÃO TEMPORAL E SCORE — APENAS CREDIT_CARD
-- Base: anl_churn_contratos | Filtro: planos 6+12m + credit_card
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
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2
ORDER BY 1, 2;


-- ============================================================================
-- 4C) VALIDAÇÃO DO SCORE DE RISCO (versão credit_card)
-- ============================================================================

WITH scored AS (
  SELECT
    contract_id,
    churn_renovacao_automatica_sn,
    plan_months_duration,
    (
      -- Número do contrato: 1o tem mais risco
      CASE WHEN account_contract_number = 1 THEN 15 ELSE 0 END

      -- Dependentes: sem dependentes = mais risco
      + CASE WHEN dependents_per_holder = 0 THEN 15
             WHEN dependents_per_holder IN (1, 2) THEN 8
             ELSE 0 END

      -- Idade: jovens (21-30) têm mais risco
      + CASE WHEN titular_idade <= 30 THEN 15
             WHEN titular_idade <= 40 THEN 10
             WHEN titular_idade <= 50 THEN 5
             ELSE 0 END

      -- Consumo: paradoxo — quem consome mais churna mais
      + CASE WHEN IFNULL(consumo_sn, 'N') = 'S' THEN 10 ELSE 0 END

      -- Crônico: não crônico = mais risco
      + CASE WHEN titular_main_cronico_sn = 'N' THEN 10 ELSE 0 END

      -- Origem: drc_cm tem mais risco
      + CASE WHEN order_source_aj = 'drc_cm' THEN 5
             WHEN order_source_aj = 'b2b' THEN -10
             ELSE 0 END

      -- Dependente idoso reduz risco
      + CASE WHEN dependents_per_holder_6099_SN = 'S' THEN -10 ELSE 0 END

      -- Pediu cancelamento
      + CASE WHEN unsubscription_sn = 'S' THEN 25 ELSE 0 END

      -- Classe social
      + CASE WHEN titual_classe_social IN ('D', 'E') THEN 5
             WHEN titual_classe_social IS NULL THEN 3
             ELSE 0 END
    ) as score_risco
  FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
  WHERE plan_months_duration IN (6, 12)
    AND order_payment_method = 'credit_card'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
)

SELECT
  CASE
    WHEN score_risco >= 55 THEN '1_CRITICO (55+)'
    WHEN score_risco >= 40 THEN '2_ALTO (40-54)'
    WHEN score_risco >= 25 THEN '3_MEDIO (25-39)'
    WHEN score_risco >= 10 THEN '4_BAIXO (10-24)'
    ELSE '5_MINIMO (0-9)'
  END as faixa_risco,

  COUNT(*) as total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) as churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) as churn_rate,
  ROUND(AVG(score_risco), 1) as score_medio,
  MIN(score_risco) as score_min,
  MAX(score_risco) as score_max

FROM scored
GROUP BY 1
ORDER BY 1;