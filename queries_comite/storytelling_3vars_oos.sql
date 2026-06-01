-- ============================================================================
-- COMITÊ-1-OOS: STORYTELLING 4 VARS — split temporal pra validação out-of-sample
-- Base: anl_churn_contratos | Filtro: planos 6+12m + credit_card + sem B2B
--
-- Mesmo cruzamento do bloco B de `storytelling_3vars.sql`, mas dividido em
-- duas janelas de 6 meses pra avaliar estabilidade do modelo:
--
--   - TRAIN  → contract_due_date_month em [-12m, -7m]  (6 meses mais antigos)
--   - TEST   → contract_due_date_month em [-6m,  -1m]  (6 meses mais recentes)
--
-- Premissa: as duas janelas têm o mesmo tipo de cliente (mesmo filtro/critério),
-- então diferenças entre coefs de train e test refletem deriva temporal real
-- (ou ruído amostral, se diferenças forem pequenas).
--
-- BLOCOS:
--   A → results_comite/storytelling_cruzamento_train.csv  (janela antiga)
--   B → results_comite/storytelling_cruzamento_test.csv   (janela recente)
-- ============================================================================


-- ============================================================================
-- BLOCO A: TRAIN — meses [-12m, -7m]
-- ============================================================================
SELECT
  CAST(plan_months_duration AS STRING) AS duracao,
  CASE WHEN account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo,
  CASE
    WHEN titular_idade <= 20 THEN '00-20'
    WHEN titular_idade <= 30 THEN '21-30'
    WHEN titular_idade <= 50 THEN '31-50'
    WHEN titular_idade <= 70 THEN '51-70'
    ELSE '71+'
  END AS faixa_etaria,
  IFNULL(titular_main_cronico_sn, 'N') AS cronico,
  CASE
    WHEN IFNULL(dependents_per_holder_0020_SN, 'N') = 'S' AND IFNULL(dependents_per_holder_6099_SN, 'N') = 'S' THEN 'com_ambos'
    WHEN IFNULL(dependents_per_holder_0020_SN, 'N') = 'S'                                       THEN 'com_crianca'
    WHEN IFNULL(dependents_per_holder_6099_SN, 'N') = 'S'                                       THEN 'com_idoso'
    ELSE 'solo'
  END AS composicao_titular,

  COUNT(*) AS total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_rate

FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12)
  AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
  AND contract_due_date_month <  DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 6  MONTH)
GROUP BY 1, 2, 3, 4, 5
HAVING COUNT(*) >= 30
ORDER BY duracao, churn_rate DESC;


-- ============================================================================
-- BLOCO B: TEST — meses [-6m, -1m]
-- ============================================================================
SELECT
  CAST(plan_months_duration AS STRING) AS duracao,
  CASE WHEN account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo,
  CASE
    WHEN titular_idade <= 20 THEN '00-20'
    WHEN titular_idade <= 30 THEN '21-30'
    WHEN titular_idade <= 50 THEN '31-50'
    WHEN titular_idade <= 70 THEN '51-70'
    ELSE '71+'
  END AS faixa_etaria,
  IFNULL(titular_main_cronico_sn, 'N') AS cronico,
  CASE
    WHEN IFNULL(dependents_per_holder_0020_SN, 'N') = 'S' AND IFNULL(dependents_per_holder_6099_SN, 'N') = 'S' THEN 'com_ambos'
    WHEN IFNULL(dependents_per_holder_0020_SN, 'N') = 'S'                                       THEN 'com_crianca'
    WHEN IFNULL(dependents_per_holder_6099_SN, 'N') = 'S'                                       THEN 'com_idoso'
    ELSE 'solo'
  END AS composicao_titular,

  COUNT(*) AS total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_rate

FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12)
  AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 6 MONTH)
GROUP BY 1, 2, 3, 4, 5
HAVING COUNT(*) >= 30
ORDER BY duracao, churn_rate DESC;
