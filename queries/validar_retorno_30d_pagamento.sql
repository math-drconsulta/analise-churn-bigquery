-- ============================================================================
-- VALIDACAO: O retorno em 15-21 dias e retentativa de pagamento
-- ou recontratacao consciente?
--
-- Logica:
--   1. Pegar contratos com days_diff = 15-21 (os "retornos")
--   2. Verificar: o proximo contrato e do MESMO account_id (extensao)
--      ou de um account_id DIFERENTE (recontratacao)?
--   3. Verificar nas tentativas Adyen se houve pagamento bem-sucedido
--      entre o vencimento e o retorno
--
-- 3 outputs:
--   STEP 1: E o mesmo account ou outro? → results/validar_retorno_tipo.csv
--   STEP 2: Teve pagamento Adyen no periodo? → results/validar_retorno_pgto.csv
--   STEP 3: Amostra detalhada → results/validar_retorno_amostra.csv
-- ============================================================================


-- ============================================================================
-- STEP 1: O proximo contrato e do MESMO account_id ou de OUTRO?
-- ============================================================================

WITH contratos AS (
  SELECT
    ys.account_id,
    ys.contract_id,
    ys.person_id,
    ys.contract_register_date,
    ys.contract_due_date,
    ys.account_due_date,
    ys.plan_months_duration,
    ys.account_contract_number,
    ys.contract_sale_type,
    ys.days_diff_until_next_contract,
    ys.payment_method,
    ys.plan_name,

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
    AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 12 MONTH)
    AND ys.contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
    AND ys.days_diff_until_next_contract BETWEEN 1 AND 30
    AND ys.date_month = ys.account_due_date_month
),

-- Encontrar o proximo contrato da mesma PESSOA (como o pipeline faz)
proximo_contrato AS (
  SELECT
    ys.person_id,
    ys.account_id AS next_account_id,
    ys.contract_id AS next_contract_id,
    ys.contract_register_date AS next_register_date,
    ys.plan_months_duration AS next_duracao,
    ys.contract_sale_type AS next_sale_type,
    ys.plan_name AS next_plan_name,
    ys.payment_method AS next_payment_method
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),

cruzado AS (
  SELECT
    c.*,
    pc.next_account_id,
    pc.next_contract_id,
    pc.next_register_date,
    pc.next_duracao,
    pc.next_sale_type,
    pc.next_plan_name,
    pc.next_payment_method,

    -- E o mesmo account ou outro?
    CASE
      WHEN pc.next_account_id = c.account_id THEN 'mesmo_account'
      WHEN pc.next_account_id IS NOT NULL THEN 'outro_account'
      ELSE 'sem_proximo'
    END AS tipo_retorno,

    -- Dias calculados
    DATE_DIFF(pc.next_register_date, c.contract_due_date, DAY) AS dias_calculados

  FROM contratos c
  LEFT JOIN proximo_contrato pc
    ON pc.person_id = c.person_id
    AND pc.next_register_date > c.contract_due_date
    AND pc.next_register_date <= DATE_ADD(c.contract_due_date, INTERVAL 30 DAY)
    AND pc.next_contract_id != c.contract_id
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY c.contract_id ORDER BY pc.next_register_date ASC
  ) = 1
)

SELECT
  tipo_retorno,
  COUNT(*) AS contratos,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) AS pct,

  -- Quando e outro account: mudou de plano?
  COUNTIF(tipo_retorno = 'outro_account' AND plan_name != next_plan_name) AS mudou_plano,
  COUNTIF(tipo_retorno = 'outro_account' AND payment_method != next_payment_method) AS mudou_pagamento,

  -- Sale type do proximo
  COUNTIF(next_sale_type = 'first_contract') AS next_first,
  COUNTIF(next_sale_type = 'renewal') AS next_renewal,
  COUNTIF(next_sale_type = 'reactivation') AS next_reactivation,

  -- Dias medio
  ROUND(AVG(days_diff_until_next_contract), 1) AS days_diff_medio,
  ROUND(AVG(dias_calculados), 1) AS dias_calculados_medio

FROM cruzado
GROUP BY 1
ORDER BY contratos DESC;


-- ============================================================================
-- STEP 2: PAGAMENTO ADYEN NO PERIODO DO RETORNO
-- Para contratos com days_diff = 15-21: houve pagamento Adyen
-- bem-sucedido entre o vencimento e o retorno?
-- ============================================================================

WITH contratos_15_21 AS (
  SELECT
    ys.account_id,
    ys.contract_id,
    ys.contract_due_date,
    TIMESTAMP(ys.contract_due_date, "America/Sao_Paulo") AS contract_due_date_ts,
    ys.days_diff_until_next_contract
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 12 MONTH)
    AND ys.contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
    AND ys.days_diff_until_next_contract BETWEEN 15 AND 21
    AND ys.date_month = ys.account_due_date_month
),

pagamentos_adyen AS (
  SELECT
    c.contract_id,
    c.days_diff_until_next_contract,
    c.contract_due_date,
    COUNT(*) AS tentativas_periodo,
    COUNTIF(ae.payment_status) AS sucessos_periodo,
    COUNTIF(NOT ae.payment_status) AS falhas_periodo,
    MIN(CASE WHEN ae.payment_status THEN ae.created_at END) AS primeiro_sucesso,
    DATE_DIFF(
      DATE(MIN(CASE WHEN ae.payment_status THEN ae.created_at END)),
      c.contract_due_date,
      DAY
    ) AS dias_ate_primeiro_sucesso
  FROM contratos_15_21 c
  LEFT JOIN `airflow-datalake-prod.yalo.public_adyen_events` ae
    ON ae.account_id = c.account_id
    AND ae.created_at >= TIMESTAMP_SUB(c.contract_due_date_ts, INTERVAL 7 DAY)
    AND ae.created_at <= TIMESTAMP_ADD(c.contract_due_date_ts, INTERVAL 30 DAY)
  GROUP BY 1, 2, 3
)

SELECT
  CASE
    WHEN sucessos_periodo > 0 AND dias_ate_primeiro_sucesso BETWEEN 0 AND 30
    THEN 'Pagamento Adyen no periodo'
    WHEN sucessos_periodo > 0 AND dias_ate_primeiro_sucesso < 0
    THEN 'Pagamento Adyen ANTES do vencimento'
    WHEN tentativas_periodo > 0 AND sucessos_periodo = 0
    THEN 'So falhas Adyen no periodo'
    WHEN tentativas_periodo = 0
    THEN 'Sem tentativa Adyen'
    ELSE 'Outro'
  END AS situacao_pagamento,

  COUNT(*) AS contratos,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) AS pct,
  ROUND(AVG(dias_ate_primeiro_sucesso), 1) AS media_dias_ate_sucesso,
  ROUND(AVG(days_diff_until_next_contract), 1) AS media_days_diff

FROM pagamentos_adyen
GROUP BY 1
ORDER BY contratos DESC;


-- ============================================================================
-- STEP 3: AMOSTRA (20 contratos com days_diff 15-21)
-- Mostra contrato atual + proximo + pagamentos
-- ============================================================================

WITH contratos_15_21 AS (
  SELECT
    ys.account_id,
    ys.contract_id,
    ys.person_id,
    ys.contract_register_date,
    ys.contract_due_date,
    ys.account_due_date,
    ys.plan_months_duration,
    ys.days_diff_until_next_contract,
    ys.contract_sale_type,
    ys.plan_name
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.days_diff_until_next_contract BETWEEN 15 AND 21
    AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 6 MONTH)
    AND ys.contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
    AND ys.date_month = ys.account_due_date_month
  LIMIT 20
),

proximo AS (
  SELECT
    ys.person_id,
    ys.account_id AS next_account_id,
    ys.contract_id AS next_contract_id,
    ys.contract_register_date AS next_register_date,
    ys.contract_due_date AS next_due_date,
    ys.contract_sale_type AS next_sale_type,
    ys.plan_name AS next_plan_name
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ys.contract_id ORDER BY ys.date_month DESC) = 1
)

SELECT
  c.contract_id,
  c.account_id,
  c.person_id,
  c.contract_register_date,
  c.contract_due_date,
  c.account_due_date,
  c.days_diff_until_next_contract,
  c.contract_sale_type,
  c.plan_name,

  p.next_account_id,
  p.next_contract_id,
  p.next_register_date,
  p.next_due_date,
  p.next_sale_type,
  p.next_plan_name,

  CASE WHEN c.account_id = p.next_account_id THEN 'MESMO account' ELSE 'OUTRO account' END AS tipo,
  DATE_DIFF(p.next_register_date, c.contract_due_date, DAY) AS gap_dias

FROM contratos_15_21 c
LEFT JOIN proximo p
  ON p.person_id = c.person_id
  AND p.next_register_date > c.contract_due_date
  AND p.next_register_date <= DATE_ADD(c.contract_due_date, INTERVAL 30 DAY)
  AND p.next_contract_id != c.contract_id
QUALIFY ROW_NUMBER() OVER (PARTITION BY c.contract_id ORDER BY p.next_register_date ASC) = 1

ORDER BY c.contract_due_date;
