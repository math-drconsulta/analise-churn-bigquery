-- ============================================================================
-- QUERY CC-1T: SEGMENTAÇÃO UNIVARIADA COM DIMENSÃO TEMPORAL
-- Base: anl_churn_contratos | Filtro: planos 6+12m + credit_card + sem B2B
--
-- Esta versão adiciona contract_due_date_month como coluna de agrupamento
-- para permitir filtragem por período no dashboard Streamlit.
-- ============================================================================

SELECT
  contract_due_date_month AS mes_vencimento,
  'plan_months_duration' AS dimensao,
  CAST(plan_months_duration AS STRING) AS segmento,
  COUNT(*) AS total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_rate
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3

UNION ALL

SELECT contract_due_date_month, 'account_contract_number',
  CASE WHEN account_contract_number = 1 THEN '1o contrato' ELSE '2o+ contrato' END,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3

UNION ALL

SELECT contract_due_date_month, 'dependentes_faixa',
  CASE WHEN dependents_per_holder = 0 THEN '0 (sem dep.)' WHEN dependents_per_holder IN (1, 2) THEN '1-2 dep.' ELSE '3+ dep.' END,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3

UNION ALL

SELECT contract_due_date_month, 'titular_faixa_etaria', titular_faixa_etaria,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3

UNION ALL

SELECT contract_due_date_month, 'titular_sexo', IFNULL(titular_sexo, '(vazio)'),
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3

UNION ALL

SELECT contract_due_date_month, 'classe_social', IFNULL(titual_classe_social, '(sem dados)'),
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3

UNION ALL

SELECT contract_due_date_month, 'titular_cronico', titular_main_cronico_sn,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3

UNION ALL

SELECT contract_due_date_month, 'consumo_sn', IFNULL(consumo_sn, 'N'),
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3

UNION ALL

SELECT contract_due_date_month, 'order_source', IFNULL(order_source_aj, '(vazio)'),
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3

UNION ALL

SELECT contract_due_date_month, 'contract_sale_type', IFNULL(contract_sale_type, '(vazio)'),
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3

UNION ALL

SELECT contract_due_date_month, 'dep_idoso_6099', dependents_per_holder_6099_SN,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3

UNION ALL

SELECT contract_due_date_month, 'dep_jovem_0020', dependents_per_holder_0020_SN,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3

UNION ALL

SELECT contract_due_date_month, 'unsubscription_sn', unsubscription_sn,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3

UNION ALL

SELECT contract_due_date_month, 'pacientes_cluster', pacientes_cluster,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12) AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3

ORDER BY dimensao, mes_vencimento, churn_rate DESC;
