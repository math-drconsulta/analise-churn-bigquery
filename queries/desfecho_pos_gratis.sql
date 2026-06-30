-- ============================================================================
-- DESFECHO POS-GRATIS: pra cada churner que migrou pro gratis,
-- identifica se depois voltou pro pago ou saiu de vez.
--
-- Complementa o desfecho_churners.csv com a coluna desfecho_final:
--   saiu_de_vez            — nunca teve proximo contrato
--   voltou_pago            — proximo contrato ja era pago (sem passar pelo gratis)
--   gratis_voltou_pago     — migrou gratis e DEPOIS voltou pro pago
--   gratis_saiu            — migrou gratis e DEPOIS saiu de vez
--
-- Output: results/desfecho_pos_gratis.csv
-- ============================================================================

WITH contratos_pago AS (
  SELECT
    ys.contract_id,
    ys.person_id,
    ys.contract_due_date,
    ys.account_due_date,
    ys.plan_months_duration

  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 18 MONTH)
    AND ys.contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 60 DAY)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),

churners AS (
  SELECT * FROM contratos_pago
  WHERE DATE_DIFF(account_due_date, contract_due_date, DAY) <= 7
),

-- Todos os contratos futuros de cada pessoa (snapshot mais recente)
futuros AS (
  SELECT
    ys.person_id,
    ys.contract_id AS fut_contract_id,
    ys.contract_register_date AS fut_register_date,
    ys.contract_due_date AS fut_due_date,
    ys.plan_name AS fut_plan_name,
    LOWER(ys.plan_name) LIKE '%gratis%' AS fut_is_gratis
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),

-- Primeiro proximo contrato (qualquer tipo)
primeiro_proximo AS (
  SELECT
    c.contract_id,
    c.person_id,
    c.contract_due_date,
    f.fut_contract_id,
    f.fut_register_date,
    f.fut_due_date,
    f.fut_plan_name,
    f.fut_is_gratis,
    DATE_DIFF(f.fut_register_date, c.contract_due_date, DAY) AS dias_ate_proximo
  FROM churners c
  LEFT JOIN futuros f
    ON f.person_id = c.person_id
    AND f.fut_register_date > c.contract_due_date
    AND f.fut_register_date <= DATE_ADD(c.contract_due_date, INTERVAL 365 DAY)
    AND f.fut_contract_id != c.contract_id
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY c.contract_id ORDER BY f.fut_register_date ASC
  ) = 1
),

-- Pra quem migrou gratis: busca o contrato DEPOIS do gratis
pos_gratis AS (
  SELECT
    pp.contract_id,
    f2.fut_contract_id AS pos_gratis_contract_id,
    f2.fut_plan_name AS pos_gratis_plan_name,
    f2.fut_is_gratis AS pos_gratis_is_gratis,
    DATE_DIFF(f2.fut_register_date, pp.fut_due_date, DAY) AS dias_pos_gratis
  FROM primeiro_proximo pp
  JOIN futuros f2
    ON f2.person_id = pp.person_id
    AND f2.fut_register_date > pp.fut_register_date
    AND f2.fut_register_date <= DATE_ADD(pp.fut_due_date, INTERVAL 90 DAY)
    AND f2.fut_contract_id != pp.fut_contract_id
    AND f2.fut_contract_id != pp.contract_id
  WHERE pp.fut_is_gratis = TRUE
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY pp.contract_id ORDER BY f2.fut_register_date ASC
  ) = 1
)

SELECT
  pp.contract_id,
  CASE
    WHEN pp.fut_contract_id IS NULL THEN 'saiu_de_vez'
    WHEN pp.fut_is_gratis = FALSE THEN 'voltou_pago'
    WHEN pp.fut_is_gratis = TRUE AND pg.pos_gratis_contract_id IS NOT NULL
      AND pg.pos_gratis_is_gratis = FALSE THEN 'gratis_voltou_pago'
    WHEN pp.fut_is_gratis = TRUE THEN 'gratis_saiu'
  END AS desfecho_final,
  pp.dias_ate_proximo,
  pp.fut_is_gratis AS primeiro_is_gratis,
  pg.dias_pos_gratis
FROM primeiro_proximo pp
LEFT JOIN pos_gratis pg ON pg.contract_id = pp.contract_id
ORDER BY pp.contract_id;
