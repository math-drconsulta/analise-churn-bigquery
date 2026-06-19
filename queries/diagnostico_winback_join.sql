-- ============================================================================
-- DIAGNOSTICO: por que o JOIN nao encontra o proximo contrato?
-- Pega 10 account_ids que sabemos que voltaram em 30d e mostra
-- TODOS os contratos desses accounts pra entender a estrutura.
-- ============================================================================

-- 1. Pegar 10 accounts que tem days_diff_until_next_contract entre 1 e 30
WITH exemplos AS (
  SELECT account_id, contract_id, contract_register_date, contract_due_date,
         days_diff_until_next_contract, plan_months_duration, plan_name, payment_method
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions`
  WHERE account_type = 'holder'
    AND payment_method = 'credit_card'
    AND plan_months_duration IN (6, 12)
    AND days_diff_until_next_contract BETWEEN 1 AND 30
    AND contract_due_date BETWEEN '2026-01-01' AND '2026-03-31'
    AND date_month = account_due_date_month
  QUALIFY ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY contract_due_date DESC) = 1
  LIMIT 10
)

-- 2. Mostrar TODOS os contratos desses accounts
SELECT
  ys.account_id,
  ys.contract_id,
  ys.contract_register_date,
  ys.contract_due_date,
  ys.account_due_date,
  ys.plan_months_duration,
  ys.plan_name,
  ys.payment_method,
  ys.account_contract_number,
  ys.contract_sale_type,
  IFNULL(ys.order_source_aj, 'outros') AS canal,
  ys.days_diff_until_next_contract,
  ys.date_month
FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
WHERE ys.account_id IN (SELECT account_id FROM exemplos)
  AND ys.account_type = 'holder'
ORDER BY ys.account_id, ys.contract_register_date, ys.date_month;
