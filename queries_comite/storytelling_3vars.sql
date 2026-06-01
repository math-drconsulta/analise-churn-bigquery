-- ============================================================================
-- COMITÊ-1: STORYTELLING 4 VARIÁVEIS — APENAS CREDIT_CARD
-- Base: anl_churn_contratos | Filtro: planos 6+12m + credit_card + sem B2B
--
-- Variáveis core do app comitê (4):
--   - ciclo               (account_contract_number = 1 vs >1)
--   - faixa_etaria        (5 buckets: 00-20, 21-30, 31-50, 51-70, 71+)
--   - cronico             (titular_main_cronico_sn: S/N)
--   - composicao_titular  (solo / com_crianca / com_idoso / com_ambos)
--       solo:        sem deps OU só deps adultos (21-60 anos)
--       com_crianca: tem dep <21 anos
--       com_idoso:   tem dep >60 anos
--       com_ambos:   tem dep jovem E idoso
--
-- Eixo de comparação: duracao (plan_months_duration = 6 ou 12)
--
-- BLOCOS:
--   A → results_comite/storytelling_univariada.csv  (4 dimensões × duração)
--   B → results_comite/storytelling_cruzamento.csv  (4 vars × duração)
-- ============================================================================


-- ============================================================================
-- BLOCO A: UNIVARIADAS POR DURAÇÃO  →  storytelling_univariada.csv
-- ============================================================================

-- A1) CICLO
SELECT
  'ciclo' AS dimensao,
  CAST(plan_months_duration AS STRING) AS duracao,
  CASE WHEN account_contract_number = 1 THEN '1o' ELSE '2o+' END AS segmento,
  COUNT(*) AS total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_rate
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3

UNION ALL

-- A2) FAIXA ETÁRIA (5 buckets)
SELECT
  'faixa_etaria',
  CAST(plan_months_duration AS STRING),
  CASE
    WHEN titular_idade <= 20 THEN '00-20'
    WHEN titular_idade <= 30 THEN '21-30'
    WHEN titular_idade <= 50 THEN '31-50'
    WHEN titular_idade <= 70 THEN '51-70'
    ELSE '71+'
  END,
  COUNT(*),
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3

UNION ALL

-- A3) CRÔNICO (S/N)
SELECT
  'cronico',
  CAST(plan_months_duration AS STRING),
  IFNULL(titular_main_cronico_sn, 'N'),
  COUNT(*),
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3

UNION ALL

-- A4) COMPOSIÇÃO DO TITULAR
SELECT
  'composicao_titular',
  CAST(plan_months_duration AS STRING),
  CASE
    WHEN IFNULL(dependents_per_holder_0020_SN, 'N') = 'S' AND IFNULL(dependents_per_holder_6099_SN, 'N') = 'S' THEN 'com_ambos'
    WHEN IFNULL(dependents_per_holder_0020_SN, 'N') = 'S'                                       THEN 'com_crianca'
    WHEN IFNULL(dependents_per_holder_6099_SN, 'N') = 'S'                                       THEN 'com_idoso'
    ELSE 'solo'
  END,
  COUNT(*),
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3

ORDER BY dimensao, duracao, segmento;


-- ============================================================================
-- BLOCO B: CRUZAMENTO 4 VARIÁVEIS × DURAÇÃO  →  storytelling_cruzamento.csv
-- Cada linha = 1 perfil (duracao × ciclo × faixa × cronico × composicao_titular)
-- HAVING >= 30 para evitar combinações com base muito rala
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
GROUP BY 1, 2, 3, 4, 5
HAVING COUNT(*) >= 30
ORDER BY duracao, churn_rate DESC;
