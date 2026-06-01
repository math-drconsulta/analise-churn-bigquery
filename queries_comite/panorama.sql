-- ============================================================================
-- COMITÊ-0: PANORAMA — duração × ciclo
-- Base: anl_churn_contratos | Filtro: planos 6+12m + credit_card + sem B2B
--
-- Recorte enxuto para a página de abertura do app comitê:
--   - 4 combinações: (6m × 1o), (6m × 2o+), (12m × 1o), (12m × 2o+)
--   - Mostra tamanho da base e churn rate em cada uma
--
-- Exporta: results_comite/panorama.csv
-- Consumido por: pages_comite/1_Panorama.py
-- ============================================================================

SELECT
  CAST(plan_months_duration AS STRING) AS duracao,
  CASE WHEN account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo,

  COUNT(*) AS total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_rate

FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12)
  AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2
ORDER BY 1, 2;
