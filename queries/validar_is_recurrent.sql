-- ============================================================================
-- VALIDAR: o que is_recurrent realmente significa?
-- Cruzar is_recurrent com o diagnostico completo pra entender
-- ============================================================================

WITH plans_info AS (
  SELECT
    account_id,
    DATE(due_date) AS due_date_d,
    is_recurrent
  FROM `airflow-datalake-prod.yalo.public_account_plans`
  WHERE DATE(due_date) BETWEEN '2026-04-01' AND '2026-04-30'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY account_id, DATE(due_date)
    ORDER BY created_at DESC
  ) = 1
),

base AS (
  SELECT
    ys.account_id,
    ys.contract_id,
    ys.contract_due_date,
    ys.account_due_date,
    ys.plan_months_duration,
    ys.payment_method,
    pi.is_recurrent,
    ys.flag_unsubscription,
    ys.days_diff_until_next_contract,
    CASE
      WHEN ys.days_diff_until_next_contract BETWEEN -30 AND 60 THEN TRUE
      ELSE FALSE
    END AS flag_novo_contrato,
    CASE
      WHEN DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) > 7 THEN 'N'
      ELSE 'S'
    END AS churn_date_diff
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  LEFT JOIN plans_info pi
    ON pi.account_id = ys.account_id
    AND pi.due_date_d = DATE(ys.contract_due_date)
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.account_due_date_month = '2026-04-01'
    AND ys.date_month = '2026-04-01'
)

SELECT
  is_recurrent,
  flag_novo_contrato,
  churn_date_diff,
  flag_unsubscription,
  COUNT(*) AS total
FROM base
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2, 3, 4;
