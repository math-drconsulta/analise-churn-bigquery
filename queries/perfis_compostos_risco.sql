-- ============================================================================
-- QUERY CC-2: PERFIS COMPOSTOS DE RISCO — APENAS CREDIT_CARD
-- Base: anl_churn_contratos | Filtro: planos 6+12m + credit_card
-- ============================================================================

-- 2A) CRUZAMENTO 7 VARIÁVEIS: duração × contrato × dependentes × consumo × faixa etária × crônico × classe social
SELECT
  CAST(plan_months_duration AS STRING) as duracao,
  CASE WHEN account_contract_number = 1 THEN '1o' ELSE '2o+' END as contrato,
  CASE
    WHEN dependents_per_holder = 0 THEN 'sem_dep'
    WHEN dependents_per_holder IN (1, 2) THEN '1-2_dep'
    ELSE '3+_dep'
  END as dependentes,
  IFNULL(consumo_sn, 'N') as consumo,
  CASE
    WHEN titular_idade <= 30 THEN '00-30'
    WHEN titular_idade <= 50 THEN '31-50'
    WHEN titular_idade <= 70 THEN '51-70'
    ELSE '71+'
  END as faixa_idade,
  titular_main_cronico_sn as cronico,
  CASE
    WHEN titual_classe_social IN ('A++', 'A+') THEN 'A'
    WHEN titual_classe_social IN ('B1', 'B2') THEN 'B'
    WHEN titual_classe_social IN ('C1', 'C2') THEN 'C'
    WHEN titual_classe_social IN ('D', 'E') THEN 'DE'
    ELSE '(sem)'
  END as classe,

  COUNT(*) as total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) as churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) as churn_rate

FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12)
  AND order_payment_method = 'credit_card'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3, 4, 5, 6, 7
HAVING COUNT(*) >= 100
ORDER BY churn_rate DESC;


-- ============================================================================
-- 2B) TOP 30 MAIOR E MENOR RISCO (descrição legível, volume >= 200)
-- ============================================================================

WITH perfis AS (
  SELECT
    CONCAT(
      CAST(plan_months_duration AS STRING), 'm|',
      CASE WHEN account_contract_number = 1 THEN '1o' ELSE '2o+' END, '|',
      CASE WHEN dependents_per_holder = 0 THEN 'sem_dep' WHEN dependents_per_holder IN (1,2) THEN '1-2dep' ELSE '3+dep' END, '|',
      'cons=', IFNULL(consumo_sn, 'N'), '|',
      CASE WHEN titular_idade <= 30 THEN '<=30' WHEN titular_idade <= 50 THEN '31-50' WHEN titular_idade <= 70 THEN '51-70' ELSE '71+' END, '|',
      'cron=', titular_main_cronico_sn
    ) as perfil,

    CAST(plan_months_duration AS STRING) as duracao,
    CASE WHEN account_contract_number = 1 THEN '1o' ELSE '2o+' END as contrato,
    CASE WHEN dependents_per_holder = 0 THEN 'sem_dep' WHEN dependents_per_holder IN (1,2) THEN '1-2dep' ELSE '3+dep' END as dependentes,
    IFNULL(consumo_sn, 'N') as consumo,
    CASE WHEN titular_idade <= 30 THEN '<=30' WHEN titular_idade <= 50 THEN '31-50' WHEN titular_idade <= 70 THEN '51-70' ELSE '71+' END as faixa_idade,
    titular_main_cronico_sn as cronico,

    COUNT(*) as total_contratos,
    SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) as churners,
    ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) as churn_rate,

    -- Métricas extras
    ROUND(AVG(IFNULL(qtd_TOTAL_CM, 0)), 1) as media_consultas,
    ROUND(AVG(IFNULL(qtd_TOTAL_EXAMES, 0)), 1) as media_exames

  FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
  WHERE plan_months_duration IN (6, 12)
    AND order_payment_method = 'credit_card'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
  GROUP BY 1, 2, 3, 4, 5, 6, 7
  HAVING COUNT(*) >= 200
)

(SELECT 'ALTO_RISCO' as categoria, * FROM perfis ORDER BY churn_rate DESC LIMIT 30)
UNION ALL
(SELECT 'BAIXO_RISCO' as categoria, * FROM perfis ORDER BY churn_rate ASC LIMIT 30);


-- ============================================================================
-- 2C) PERFIS COM UNSUBSCRIPTION EXCLUÍDO (churn "silencioso")
-- Remove quem pediu cancelamento para focar no churn sem aviso
-- ============================================================================

SELECT
  CAST(plan_months_duration AS STRING) as duracao,
  CASE WHEN account_contract_number = 1 THEN '1o' ELSE '2o+' END as contrato,
  CASE WHEN dependents_per_holder = 0 THEN 'sem_dep' WHEN dependents_per_holder IN (1,2) THEN '1-2dep' ELSE '3+dep' END as dependentes,
  IFNULL(consumo_sn, 'N') as consumo,
  CASE WHEN titular_idade <= 30 THEN '<=30' WHEN titular_idade <= 50 THEN '31-50' WHEN titular_idade <= 70 THEN '51-70' ELSE '71+' END as faixa_idade,
  titular_main_cronico_sn as cronico,

  COUNT(*) as total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) as churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) as churn_rate

FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12)
  AND order_payment_method = 'credit_card'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
  AND unsubscription_sn = 'N'  -- exclui quem pediu cancelamento
GROUP BY 1, 2, 3, 4, 5, 6
HAVING COUNT(*) >= 200
ORDER BY churn_rate DESC;