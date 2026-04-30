-- ============================================================================
-- QUERY CC-1: SEGMENTAÇÃO UNIVARIADA — APENAS CREDIT_CARD
-- Base: anl_churn_contratos | Filtro: planos 6+12m + credit_card + sem B2B/COOP
-- ============================================================================

-- 1A) CHURN POR DURAÇÃO
SELECT 'plan_months_duration' as dimensao, CAST(plan_months_duration AS STRING) as segmento,
  COUNT(*) as total_contratos, SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) as churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) as churn_rate
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'  -- excluir canal corporativo
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2

UNION ALL

-- 1B) CHURN POR NÚMERO DO CONTRATO
SELECT 'account_contract_number', CASE WHEN account_contract_number = 1 THEN '1o contrato' ELSE '2o+ contrato' END,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'  -- excluir canal corporativo
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2

UNION ALL

-- 1C) CHURN POR FAIXA DE DEPENDENTES
SELECT 'dependentes_faixa',
  CASE WHEN dependents_per_holder = 0 THEN '0 (sem dep.)' WHEN dependents_per_holder IN (1, 2) THEN '1-2 dep.' ELSE '3+ dep.' END,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'  -- excluir canal corporativo
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2

UNION ALL

-- 1D) CHURN POR FAIXA ETÁRIA
SELECT 'titular_faixa_etaria', titular_faixa_etaria,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'  -- excluir canal corporativo
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2

UNION ALL

-- 1E) CHURN POR SEXO
SELECT 'titular_sexo', IFNULL(titular_sexo, '(vazio)'),
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'  -- excluir canal corporativo
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2

UNION ALL

-- 1F) CHURN POR CLASSE SOCIAL
SELECT 'classe_social', IFNULL(titual_classe_social, '(sem dados)'),
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'  -- excluir canal corporativo
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2

UNION ALL

-- 1G) CHURN POR CRÔNICO
SELECT 'titular_cronico', titular_main_cronico_sn,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'  -- excluir canal corporativo
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2

UNION ALL

-- 1H) CHURN POR CONSUMO
SELECT 'consumo_sn', IFNULL(consumo_sn, 'N'),
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'  -- excluir canal corporativo
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2

UNION ALL

-- 1I) CHURN POR ORIGEM
SELECT 'order_source', IFNULL(order_source_aj, '(vazio)'),
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'  -- excluir canal corporativo
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2

UNION ALL

-- 1J) CHURN POR TIPO DE VENDA
SELECT 'contract_sale_type', IFNULL(contract_sale_type, '(vazio)'),
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'  -- excluir canal corporativo
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2

UNION ALL

-- 1K) CHURN POR DEPENDENTE IDOSO
SELECT 'dep_idoso_6099', dependents_per_holder_6099_SN,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'  -- excluir canal corporativo
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2

UNION ALL

-- 1L) CHURN POR DEPENDENTE JOVEM
SELECT 'dep_jovem_0020', dependents_per_holder_0020_SN,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'  -- excluir canal corporativo
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2

UNION ALL

-- 1M) CHURN POR UNSUBSCRIPTION
SELECT 'unsubscription_sn', unsubscription_sn,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'  -- excluir canal corporativo
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2

UNION ALL

-- 1N) CHURN POR CLUSTER
SELECT 'pacientes_cluster', pacientes_cluster,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'  -- excluir canal corporativo
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2

ORDER BY dimensao, churn_rate DESC;