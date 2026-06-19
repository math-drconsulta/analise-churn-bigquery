-- ============================================================================
-- IMPACTO DA MUDANÇA ADYEN v5 — Usando flag_novo_contrato (validado)
--
-- Métrica: flag_novo_contrato = days_diff_until_next_contract BETWEEN -30 AND 60
-- Significa: o paciente efetivamente CONTRATOU de novo após o vencimento
--
-- Validação: is_recurrent = config do plano (90%+, NÃO é renovação)
--            churn_date_diff = S pra todos (não discrimina)
--            flag_novo_contrato = 18% (compatível com churn ~55%)
--
-- Filtro: somente contratos processados pela Adyen
--
-- 3 outputs:
--   STEP 1: Semanal → results/adyen_v5_semanal.csv
--   STEP 2: Agregado PRE vs POS → results/adyen_v5_resumo.csv
--   STEP 3: Diário → results/adyen_v5_diario.csv
-- ============================================================================


-- ============================================================================
-- STEP 1: SEMANAL
-- ============================================================================

WITH base AS (
  SELECT
    ys.contract_id,
    ys.account_id,
    ys.contract_due_date,
    TIMESTAMP(ys.contract_due_date, "America/Sao_Paulo") AS contract_due_date_ts,
    ys.plan_months_duration,
    CASE WHEN ys.account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo,
    ys.flag_unsubscription,
    ys.days_diff_until_next_contract,

    -- Renovação real: teve próximo contrato em até 60 dias
    CASE
      WHEN ys.days_diff_until_next_contract BETWEEN -30 AND 60 THEN TRUE
      ELSE FALSE
    END AS renovou,

    -- Semana
    CASE
      WHEN ys.contract_due_date BETWEEN '2026-04-24' AND '2026-04-30' THEN '1_PRE sem3 (24-30/abr)'
      WHEN ys.contract_due_date BETWEEN '2026-05-01' AND '2026-05-07' THEN '2_PRE sem2 (01-07/mai)'
      WHEN ys.contract_due_date BETWEEN '2026-05-08' AND '2026-05-14' THEN '3_PRE sem1 (08-14/mai)'
      WHEN ys.contract_due_date BETWEEN '2026-05-15' AND '2026-05-21' THEN '4_POS sem1 (15-21/mai)'
      WHEN ys.contract_due_date BETWEEN '2026-05-22' AND '2026-05-28' THEN '5_POS sem2 (22-28/mai)'
      WHEN ys.contract_due_date BETWEEN '2026-05-29' AND '2026-06-04' THEN '6_POS sem3 (29/mai-04/jun)'
      WHEN ys.contract_due_date BETWEEN '2026-06-05' AND '2026-06-15' THEN '7_POS sem4 (05-15/jun)'
    END AS janela,

    CASE
      WHEN ys.contract_due_date < '2026-05-15' THEN 'PRE'
      ELSE 'POS'
    END AS periodo

  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.contract_due_date BETWEEN '2026-04-24' AND '2026-06-15'
    AND ys.account_due_date_month >= '2026-04-01'
    AND ys.date_month = ys.account_due_date_month
),

-- Filtrar: só contratos com tentativa na Adyen
contratos_adyen AS (
  SELECT DISTINCT b.contract_id
  FROM base b
  INNER JOIN `airflow-datalake-prod.yalo.public_adyen_events` ae
    ON ae.account_id = b.account_id
  WHERE ae.created_at >= TIMESTAMP_SUB(b.contract_due_date_ts, INTERVAL 7 DAY)
    AND ae.created_at <= TIMESTAMP_ADD(b.contract_due_date_ts, INTERVAL 30 DAY)
),

-- Métricas de pagamento Adyen por contrato
adyen_stats AS (
  SELECT
    b.contract_id,
    COUNT(*) AS tentativas,
    COUNTIF(ae.payment_status) AS sucessos,
    COUNTIF(NOT ae.payment_status) AS recusas
  FROM base b
  INNER JOIN `airflow-datalake-prod.yalo.public_adyen_events` ae
    ON ae.account_id = b.account_id
  WHERE ae.created_at >= TIMESTAMP_SUB(b.contract_due_date_ts, INTERVAL 7 DAY)
    AND ae.created_at <= TIMESTAMP_ADD(b.contract_due_date_ts, INTERVAL 30 DAY)
  GROUP BY 1
),

final AS (
  SELECT
    b.*,
    COALESCE(a.tentativas, 0) AS adyen_tentativas,
    COALESCE(a.sucessos, 0) AS adyen_sucessos,
    COALESCE(a.recusas, 0) AS adyen_recusas
  FROM base b
  INNER JOIN contratos_adyen ca ON ca.contract_id = b.contract_id
  LEFT JOIN adyen_stats a ON a.contract_id = b.contract_id
)

SELECT
  janela,
  periodo,
  COUNT(*) AS total_contratos,

  -- Renovação real (flag_novo_contrato)
  COUNTIF(renovou) AS renovaram,
  ROUND(100.0 * COUNTIF(renovou) / COUNT(*), 2) AS taxa_renovacao,

  -- Churn
  COUNTIF(NOT renovou) AS churners,
  ROUND(100.0 * COUNTIF(NOT renovou) / COUNT(*), 2) AS churn_rate,

  -- Cancelamento explícito
  COUNTIF(flag_unsubscription) AS cancelaram,

  -- Adyen
  SUM(adyen_tentativas) AS adyen_tentativas,
  SUM(adyen_sucessos) AS adyen_sucessos,
  SUM(adyen_recusas) AS adyen_recusas,
  ROUND(100.0 * SUM(adyen_sucessos) / NULLIF(SUM(adyen_tentativas), 0), 2) AS adyen_taxa_aprovacao

FROM final
WHERE janela IS NOT NULL
GROUP BY 1, 2
ORDER BY janela;


-- ============================================================================
-- STEP 2: AGREGADO PRE vs POS
-- ============================================================================

WITH base AS (
  SELECT
    ys.contract_id,
    ys.account_id,
    ys.contract_due_date,
    TIMESTAMP(ys.contract_due_date, "America/Sao_Paulo") AS contract_due_date_ts,
    ys.days_diff_until_next_contract,
    CASE
      WHEN ys.days_diff_until_next_contract BETWEEN -30 AND 60 THEN TRUE
      ELSE FALSE
    END AS renovou,
    CASE
      WHEN ys.contract_due_date < '2026-05-15' THEN 'PRE'
      ELSE 'POS'
    END AS periodo
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.contract_due_date BETWEEN '2026-04-24' AND '2026-06-15'
    AND ys.account_due_date_month >= '2026-04-01'
    AND ys.date_month = ys.account_due_date_month
),

contratos_adyen AS (
  SELECT DISTINCT b.contract_id
  FROM base b
  INNER JOIN `airflow-datalake-prod.yalo.public_adyen_events` ae
    ON ae.account_id = b.account_id
  WHERE ae.created_at >= TIMESTAMP_SUB(b.contract_due_date_ts, INTERVAL 7 DAY)
    AND ae.created_at <= TIMESTAMP_ADD(b.contract_due_date_ts, INTERVAL 30 DAY)
)

SELECT
  periodo,
  COUNT(*) AS total_contratos,
  COUNTIF(renovou) AS renovaram,
  COUNTIF(NOT renovou) AS churners,
  ROUND(100.0 * COUNTIF(renovou) / COUNT(*), 2) AS taxa_renovacao,
  ROUND(100.0 * COUNTIF(NOT renovou) / COUNT(*), 2) AS churn_rate
FROM base b
INNER JOIN contratos_adyen ca ON ca.contract_id = b.contract_id
GROUP BY 1
ORDER BY 1;


-- ============================================================================
-- STEP 3: DIA A DIA
-- ============================================================================

WITH base AS (
  SELECT
    ys.contract_id,
    ys.account_id,
    ys.contract_due_date,
    TIMESTAMP(ys.contract_due_date, "America/Sao_Paulo") AS contract_due_date_ts,
    ys.days_diff_until_next_contract,
    CASE
      WHEN ys.days_diff_until_next_contract BETWEEN -30 AND 60 THEN TRUE
      ELSE FALSE
    END AS renovou
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.contract_due_date BETWEEN '2026-04-24' AND '2026-06-15'
    AND ys.account_due_date_month >= '2026-04-01'
    AND ys.date_month = ys.account_due_date_month
),

contratos_adyen AS (
  SELECT DISTINCT b.contract_id
  FROM base b
  INNER JOIN `airflow-datalake-prod.yalo.public_adyen_events` ae
    ON ae.account_id = b.account_id
  WHERE ae.created_at >= TIMESTAMP_SUB(b.contract_due_date_ts, INTERVAL 7 DAY)
    AND ae.created_at <= TIMESTAMP_ADD(b.contract_due_date_ts, INTERVAL 30 DAY)
)

SELECT
  b.contract_due_date AS dia,
  CASE WHEN b.contract_due_date >= '2026-05-15' THEN 'POS' ELSE 'PRE' END AS periodo,
  COUNT(*) AS total_contratos,
  COUNTIF(b.renovou) AS renovaram,
  COUNTIF(NOT b.renovou) AS churners,
  ROUND(100.0 * COUNTIF(b.renovou) / COUNT(*), 2) AS taxa_renovacao
FROM base b
INNER JOIN contratos_adyen ca ON ca.contract_id = b.contract_id
GROUP BY 1, 2
ORDER BY 1;
