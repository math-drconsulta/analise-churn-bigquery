-- ============================================================================
-- DESFECHO POR CONTRATO: classifica cada churner em 3 destinos
--
-- Para cada contrato que churnou, identifica o proximo contrato
-- da mesma pessoa e classifica:
--   saiu_de_vez:    nenhum proximo contrato em 12 meses
--   migrou_gratis:  proximo contrato e gratis
--   voltou_pago:    proximo contrato e pago
--
-- Output: results/desfecho_churners.csv
-- ============================================================================

WITH contratos_pago AS (
  SELECT
    ys.contract_id,
    ys.person_id,
    ys.contract_due_date,
    ys.account_due_date,
    ys.plan_months_duration,
    ys.account_contract_number,
    ys.days_diff_until_next_contract,

    CASE
      WHEN DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) > 7 THEN 'N'
      ELSE 'S'
    END AS churn_sn

  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 36 MONTH)
    AND ys.contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id
    ORDER BY ys.date_month DESC
  ) = 1
),

-- Proximo contrato da mesma pessoa (qualquer tipo)
proximo AS (
  SELECT
    ys.person_id,
    ys.contract_id AS next_contract_id,
    ys.contract_register_date AS next_register_date,
    ys.plan_name AS next_plan_name,
    CASE WHEN LOWER(ys.plan_name) LIKE '%gratis%' THEN TRUE ELSE FALSE END AS next_is_gratis
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ys.contract_id ORDER BY ys.date_month DESC) = 1
),

churners AS (
  SELECT
    cp.contract_id,
    cp.days_diff_until_next_contract,
    p.next_contract_id,
    p.next_register_date,
    p.next_is_gratis,
    DATE_DIFF(p.next_register_date, cp.contract_due_date, DAY) AS dias_ate_proximo,

    CASE
      WHEN p.next_contract_id IS NULL THEN 'saiu_de_vez'
      WHEN p.next_is_gratis THEN 'migrou_gratis'
      ELSE 'voltou_pago'
    END AS desfecho

  FROM contratos_pago cp
  LEFT JOIN proximo p
    ON p.person_id = cp.person_id
    AND p.next_register_date > cp.contract_due_date
    AND p.next_register_date <= DATE_ADD(cp.contract_due_date, INTERVAL 365 DAY)
    AND p.next_contract_id != cp.contract_id
  WHERE cp.churn_sn = 'S'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY cp.contract_id
    ORDER BY p.next_register_date ASC
  ) = 1
)

SELECT
  contract_id,
  desfecho,
  dias_ate_proximo,
  next_is_gratis
FROM churners
ORDER BY contract_id;
