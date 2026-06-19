-- ============================================================================
-- MIGRACAO PRO GRATIS: quem sao, quanto tempo ficam, voltam pro pago?
--
-- 3 outputs:
--   STEP 1: Perfil de quem migra pro gratis vs quem sai de vez
--   STEP 2: O que acontece depois do gratis (volta pro pago? sai?)
--   STEP 3: Tempo no gratis antes de sair ou voltar
-- ============================================================================


-- ============================================================================
-- STEP 1: PERFIL — quem migra pro gratis vs quem sai de vez
-- Arquivo: results/migracao_gratis_perfil.csv
-- ============================================================================

WITH contratos_pago AS (
  SELECT
    ys.account_id,
    ys.contract_id,
    ys.person_id,
    ys.contract_register_date,
    ys.contract_due_date,
    ys.plan_months_duration,
    ys.account_contract_number,
    ys.days_diff_until_next_contract,
    ys.plan_name,
    IFNULL(ys.order_source_aj, 'outros') AS canal,
    ys.flag_unsubscription,

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
    AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 18 MONTH)
    AND ys.contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
    AND ys.date_month = ys.account_due_date_month
),

-- Proximo contrato da mesma pessoa (qualquer tipo, incluindo gratis)
proximo AS (
  SELECT
    ys.person_id,
    ys.account_id AS next_account_id,
    ys.contract_id AS next_contract_id,
    ys.contract_register_date AS next_register_date,
    ys.contract_due_date AS next_due_date,
    ys.plan_name AS next_plan_name,
    ys.plan_months_duration AS next_duracao,
    ys.payment_method AS next_payment_method,
    CASE WHEN LOWER(ys.plan_name) LIKE '%gratis%' THEN TRUE ELSE FALSE END AS next_is_gratis
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ys.contract_id ORDER BY ys.date_month DESC) = 1
),

-- Churners com classificacao: migrou gratis, saiu de vez, ou voltou pro pago
churners AS (
  SELECT
    cp.*,
    p.next_account_id,
    p.next_contract_id,
    p.next_register_date,
    p.next_due_date,
    p.next_plan_name,
    p.next_duracao,
    p.next_payment_method,
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
  QUALIFY ROW_NUMBER() OVER (PARTITION BY cp.contract_id ORDER BY p.next_register_date ASC) = 1
)

SELECT
  desfecho,
  COUNT(*) AS contratos,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) AS pct,

  -- Perfil
  ROUND(100.0 * COUNTIF(account_contract_number = 1) / COUNT(*), 1) AS pct_1o_contrato,
  ROUND(100.0 * COUNTIF(plan_months_duration = 12) / COUNT(*), 1) AS pct_12m,
  ROUND(100.0 * COUNTIF(flag_unsubscription) / COUNT(*), 1) AS pct_pediu_cancelamento,

  -- Timing
  ROUND(AVG(dias_ate_proximo), 0) AS media_dias_ate_proximo,
  ROUND(AVG(CASE WHEN desfecho = 'migrou_gratis' THEN dias_ate_proximo END), 0) AS media_dias_gratis,

  -- Canal
  ROUND(100.0 * COUNTIF(canal LIKE '%digital%') / COUNT(*), 1) AS pct_digital

FROM churners
GROUP BY 1
ORDER BY contratos DESC;


-- ============================================================================
-- STEP 2: DEPOIS DO GRATIS — volta pro pago? quanto tempo fica?
-- Arquivo: results/migracao_gratis_depois.csv
-- ============================================================================

WITH contratos_pago AS (
  SELECT
    ys.contract_id,
    ys.person_id,
    ys.contract_due_date,
    ys.plan_months_duration
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 18 MONTH)
    AND ys.contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
    AND ys.date_month = ys.account_due_date_month
    AND DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) <= 7  -- churners
),

-- Proximo contrato = gratis
proximo_gratis AS (
  SELECT
    ys.person_id,
    ys.contract_id AS gratis_contract_id,
    ys.contract_register_date AS gratis_register_date,
    ys.contract_due_date AS gratis_due_date,
    ys.plan_name AS gratis_plan_name,
    DATE_DIFF(ys.contract_due_date, ys.contract_register_date, DAY) AS dias_no_gratis
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND LOWER(ys.plan_name) LIKE '%gratis%'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ys.contract_id ORDER BY ys.date_month DESC) = 1
),

-- Depois do gratis: voltou pro pago?
pos_gratis AS (
  SELECT
    ys.person_id,
    ys.contract_id AS pos_contract_id,
    ys.contract_register_date AS pos_register_date,
    ys.plan_name AS pos_plan_name,
    ys.payment_method AS pos_payment_method,
    CASE WHEN LOWER(ys.plan_name) LIKE '%gratis%' THEN TRUE ELSE FALSE END AS pos_is_gratis
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND NOT LOWER(ys.plan_name) LIKE '%gratis%'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ys.contract_id ORDER BY ys.date_month DESC) = 1
),

jornada AS (
  SELECT
    cp.contract_id,
    cp.contract_due_date,
    pg.gratis_contract_id,
    pg.gratis_register_date,
    pg.gratis_due_date,
    pg.dias_no_gratis,
    pg.gratis_plan_name,
    ppg.pos_contract_id,
    ppg.pos_register_date,
    ppg.pos_plan_name,

    CASE
      WHEN pg.gratis_contract_id IS NULL THEN 'sem_gratis'
      WHEN ppg.pos_contract_id IS NOT NULL THEN 'gratis_depois_pago'
      WHEN pg.gratis_due_date < CURRENT_DATE() THEN 'gratis_depois_saiu'
      ELSE 'ainda_no_gratis'
    END AS jornada_status

  FROM contratos_pago cp
  LEFT JOIN proximo_gratis pg
    ON pg.person_id = cp.person_id
    AND pg.gratis_register_date > cp.contract_due_date
    AND pg.gratis_register_date <= DATE_ADD(cp.contract_due_date, INTERVAL 60 DAY)
  LEFT JOIN pos_gratis ppg
    ON ppg.person_id = cp.person_id
    AND ppg.pos_register_date > pg.gratis_due_date
    AND ppg.pos_register_date <= DATE_ADD(pg.gratis_due_date, INTERVAL 365 DAY)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY cp.contract_id
    ORDER BY pg.gratis_register_date ASC, ppg.pos_register_date ASC
  ) = 1
)

SELECT
  jornada_status,
  COUNT(*) AS contratos,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) AS pct,
  ROUND(AVG(dias_no_gratis), 0) AS media_dias_no_gratis

FROM jornada
GROUP BY 1
ORDER BY contratos DESC;


-- ============================================================================
-- STEP 3: TIMING — quando migram pro gratis (distribuicao de dias)
-- Arquivo: results/migracao_gratis_timing.csv
-- ============================================================================

WITH contratos_pago AS (
  SELECT
    ys.contract_id,
    ys.person_id,
    ys.contract_due_date,
    ys.days_diff_until_next_contract
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 18 MONTH)
    AND ys.contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
    AND ys.date_month = ys.account_due_date_month
    AND DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) <= 7
    AND ys.days_diff_until_next_contract BETWEEN 1 AND 30
),

proximo_gratis AS (
  SELECT
    ys.person_id,
    ys.contract_register_date AS gratis_register_date,
    ys.plan_name AS gratis_plan_name
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND LOWER(ys.plan_name) LIKE '%gratis%'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ys.contract_id ORDER BY ys.date_month DESC) = 1
),

com_gratis AS (
  SELECT
    cp.*,
    pg.gratis_register_date,
    pg.gratis_plan_name,
    DATE_DIFF(pg.gratis_register_date, cp.contract_due_date, DAY) AS dias_ate_gratis,
    CASE WHEN pg.gratis_register_date IS NOT NULL THEN 'migrou_gratis' ELSE 'nao_migrou' END AS status
  FROM contratos_pago cp
  LEFT JOIN proximo_gratis pg
    ON pg.person_id = cp.person_id
    AND pg.gratis_register_date > cp.contract_due_date
    AND pg.gratis_register_date <= DATE_ADD(cp.contract_due_date, INTERVAL 30 DAY)
  QUALIFY ROW_NUMBER() OVER (PARTITION BY cp.contract_id ORDER BY pg.gratis_register_date ASC) = 1
)

SELECT
  status,
  CASE
    WHEN dias_ate_gratis IS NULL THEN 'sem_gratis'
    WHEN dias_ate_gratis <= 7 THEN '0-7 dias'
    WHEN dias_ate_gratis <= 14 THEN '8-14 dias'
    WHEN dias_ate_gratis <= 21 THEN '15-21 dias'
    ELSE '22-30 dias'
  END AS faixa_dias,
  COUNT(*) AS contratos,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) AS pct,
  ROUND(AVG(days_diff_until_next_contract), 1) AS media_days_diff

FROM com_gratis
GROUP BY 1, 2
ORDER BY 1, 2;
