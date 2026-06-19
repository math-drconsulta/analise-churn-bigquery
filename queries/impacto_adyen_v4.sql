-- ============================================================================
-- IMPACTO DA MUDANÇA ADYEN v4 — Usando dados diretos de pagamento
--
-- Baseado na query de motivos_churn (estrutura validada)
-- Adaptado pro período PRE/POS da mudança Adyen (15/mai/2026)
--
-- Métricas diretas (sem proxy):
--   - is_recurrent: flag de renovação automática
--   - payment_status: taxa de aprovação Adyen
--   - refusal_reason: motivos de recusa
--   - diagnostico: classificação completa do desfecho
--
-- 3 outputs:
--   STEP 1: Resumo PRE vs POS → results/adyen_v4_resumo.csv
--   STEP 2: Taxa aprovação Adyen PRE vs POS → results/adyen_v4_aprovacao.csv
--   STEP 3: Motivos de recusa PRE vs POS → results/adyen_v4_recusas.csv
-- ============================================================================


-- ============================================================================
-- STEP 1: RESUMO PRE vs POS (com is_recurrent e diagnostico)
-- ============================================================================

WITH plans_info AS (
  SELECT
    account_id,
    DATE(due_date) AS due_date_d,
    is_recurrent
  FROM `airflow-datalake-prod.yalo.public_account_plans`
  WHERE DATE(due_date) BETWEEN '2026-04-01' AND '2026-06-30'
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
    TIMESTAMP(ys.contract_due_date, "America/Sao_Paulo") AS contract_due_date_ts,
    ys.plan_months_duration,
    ys.payment_method,
    pi.is_recurrent,
    ys.flag_unsubscription,
    ys.days_diff_until_next_contract,
    CASE
      WHEN ys.days_diff_until_next_contract BETWEEN -30 AND 60 THEN TRUE
      ELSE FALSE
    END AS flag_novo_contrato,

    -- Periodo
    CASE
      WHEN ys.contract_due_date < '2026-05-15' THEN 'PRE'
      ELSE 'POS'
    END AS periodo,

    -- Semana
    CASE
      WHEN ys.contract_due_date BETWEEN '2026-04-24' AND '2026-04-30' THEN '1_PRE sem3'
      WHEN ys.contract_due_date BETWEEN '2026-05-01' AND '2026-05-07' THEN '2_PRE sem2'
      WHEN ys.contract_due_date BETWEEN '2026-05-08' AND '2026-05-14' THEN '3_PRE sem1'
      WHEN ys.contract_due_date BETWEEN '2026-05-15' AND '2026-05-21' THEN '4_POS sem1'
      WHEN ys.contract_due_date BETWEEN '2026-05-22' AND '2026-05-28' THEN '5_POS sem2'
      WHEN ys.contract_due_date BETWEEN '2026-05-29' AND '2026-06-04' THEN '6_POS sem3'
      WHEN ys.contract_due_date BETWEEN '2026-06-05' AND '2026-06-15' THEN '7_POS sem4'
    END AS janela

  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  LEFT JOIN plans_info pi
    ON pi.account_id = ys.account_id
    AND pi.due_date_d = DATE(ys.contract_due_date)
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.account_due_date_month >= '2026-04-01'
    AND ys.date_month = ys.account_due_date_month
    AND ys.contract_due_date BETWEEN '2026-04-24' AND '2026-06-15'
),

tentativas_adyen AS (
  SELECT
    b.account_id, b.contract_id,
    ae.created_at AS event_date,
    CASE WHEN ae.payment_status THEN 'success' ELSE 'failed' END AS outcome,
    JSON_EXTRACT_SCALAR(ae.body, '$.resultCode') AS status_detail,
    JSON_EXTRACT_SCALAR(ae.body, '$.refusalReason') AS refusal_reason
  FROM base b
  JOIN `airflow-datalake-prod.yalo.public_adyen_events` ae
    ON ae.account_id = b.account_id
  WHERE ae.created_at >= TIMESTAMP_SUB(b.contract_due_date_ts, INTERVAL 7 DAY)
    AND ae.created_at <= TIMESTAMP_ADD(b.contract_due_date_ts, INTERVAL 30 DAY)
),

resumo_adyen AS (
  SELECT
    account_id, contract_id,
    COUNT(*) AS qtd_tentativas,
    COUNTIF(outcome = 'success') AS qtd_sucessos,
    COUNTIF(outcome = 'failed') AS qtd_recusas
  FROM tentativas_adyen
  GROUP BY 1, 2
),

-- Classificar: contrato passou pela Adyen?
base_com_adyen AS (
  SELECT
    b.*,
    COALESCE(ra.qtd_tentativas, 0) AS adyen_tentativas,
    COALESCE(ra.qtd_sucessos, 0) AS adyen_sucessos,
    COALESCE(ra.qtd_recusas, 0) AS adyen_recusas,
    CASE WHEN ra.qtd_tentativas > 0 THEN TRUE ELSE FALSE END AS processado_adyen
  FROM base b
  LEFT JOIN resumo_adyen ra
    ON ra.account_id = b.account_id AND ra.contract_id = b.contract_id
)

-- RESULTADO: só contratos Adyen, agrupado por periodo e semana
SELECT
  janela,
  periodo,
  COUNT(*) AS total_contratos,

  -- Renovação por is_recurrent (campo direto)
  COUNTIF(is_recurrent = TRUE) AS renovaram_recurrent,
  ROUND(100.0 * COUNTIF(is_recurrent = TRUE) / COUNT(*), 2) AS taxa_renovacao_recurrent,

  -- Renovação por flag_novo_contrato (proxy days_diff)
  COUNTIF(flag_novo_contrato = TRUE) AS renovaram_flag,
  ROUND(100.0 * COUNTIF(flag_novo_contrato = TRUE) / COUNT(*), 2) AS taxa_renovacao_flag,

  -- Cancelamento explicito
  COUNTIF(flag_unsubscription = TRUE) AS cancelaram,

  -- Adyen: taxa de aprovação
  SUM(adyen_tentativas) AS adyen_total_tentativas,
  SUM(adyen_sucessos) AS adyen_total_sucessos,
  SUM(adyen_recusas) AS adyen_total_recusas,
  ROUND(100.0 * SUM(adyen_sucessos) / NULLIF(SUM(adyen_tentativas), 0), 2) AS adyen_taxa_aprovacao,

  -- Sem tentativa (nenhuma cobrança registrada)
  COUNTIF(adyen_tentativas = 0) AS sem_tentativa

FROM base_com_adyen
WHERE janela IS NOT NULL
  AND processado_adyen = TRUE  -- só Adyen
GROUP BY 1, 2
ORDER BY janela;


-- ============================================================================
-- STEP 2: TAXA DE APROVAÇÃO ADYEN — PRE vs POS agregado
-- ============================================================================

WITH plans_info AS (
  SELECT account_id, DATE(due_date) AS due_date_d, is_recurrent
  FROM `airflow-datalake-prod.yalo.public_account_plans`
  WHERE DATE(due_date) BETWEEN '2026-04-01' AND '2026-06-30'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY account_id, DATE(due_date) ORDER BY created_at DESC) = 1
),

base AS (
  SELECT
    ys.account_id, ys.contract_id, ys.contract_due_date,
    TIMESTAMP(ys.contract_due_date, "America/Sao_Paulo") AS contract_due_date_ts,
    pi.is_recurrent,
    CASE WHEN ys.contract_due_date < '2026-05-15' THEN 'PRE' ELSE 'POS' END AS periodo
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  LEFT JOIN plans_info pi ON pi.account_id = ys.account_id AND pi.due_date_d = DATE(ys.contract_due_date)
  WHERE ys.account_type = 'holder' AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12) AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.account_due_date_month >= '2026-04-01' AND ys.date_month = ys.account_due_date_month
    AND ys.contract_due_date BETWEEN '2026-04-24' AND '2026-06-15'
),

tentativas AS (
  SELECT
    b.contract_id, b.periodo,
    CASE WHEN ae.payment_status THEN 'success' ELSE 'failed' END AS outcome,
    JSON_EXTRACT_SCALAR(ae.body, '$.refusalReason') AS refusal_reason
  FROM base b
  JOIN `airflow-datalake-prod.yalo.public_adyen_events` ae
    ON ae.account_id = b.account_id
  WHERE ae.created_at >= TIMESTAMP_SUB(b.contract_due_date_ts, INTERVAL 7 DAY)
    AND ae.created_at <= TIMESTAMP_ADD(b.contract_due_date_ts, INTERVAL 30 DAY)
)

SELECT
  periodo,
  COUNT(*) AS total_tentativas,
  COUNTIF(outcome = 'success') AS sucessos,
  COUNTIF(outcome = 'failed') AS recusas,
  ROUND(100.0 * COUNTIF(outcome = 'success') / COUNT(*), 2) AS taxa_aprovacao,
  ROUND(100.0 * COUNTIF(outcome = 'failed') / COUNT(*), 2) AS taxa_recusa
FROM tentativas
GROUP BY 1
ORDER BY 1;


-- ============================================================================
-- STEP 3: MOTIVOS DE RECUSA ADYEN — PRE vs POS
-- ============================================================================

WITH plans_info AS (
  SELECT account_id, DATE(due_date) AS due_date_d, is_recurrent
  FROM `airflow-datalake-prod.yalo.public_account_plans`
  WHERE DATE(due_date) BETWEEN '2026-04-01' AND '2026-06-30'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY account_id, DATE(due_date) ORDER BY created_at DESC) = 1
),

base AS (
  SELECT
    ys.account_id, ys.contract_id, ys.contract_due_date,
    TIMESTAMP(ys.contract_due_date, "America/Sao_Paulo") AS contract_due_date_ts,
    CASE WHEN ys.contract_due_date < '2026-05-15' THEN 'PRE' ELSE 'POS' END AS periodo
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  LEFT JOIN plans_info pi ON pi.account_id = ys.account_id AND pi.due_date_d = DATE(ys.contract_due_date)
  WHERE ys.account_type = 'holder' AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12) AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.account_due_date_month >= '2026-04-01' AND ys.date_month = ys.account_due_date_month
    AND ys.contract_due_date BETWEEN '2026-04-24' AND '2026-06-15'
),

tentativas AS (
  SELECT
    b.periodo,
    CASE WHEN ae.payment_status THEN 'success' ELSE 'failed' END AS outcome,
    IFNULL(JSON_EXTRACT_SCALAR(ae.body, '$.refusalReason'), '(sem motivo)') AS refusal_reason
  FROM base b
  JOIN `airflow-datalake-prod.yalo.public_adyen_events` ae
    ON ae.account_id = b.account_id
  WHERE ae.created_at >= TIMESTAMP_SUB(b.contract_due_date_ts, INTERVAL 7 DAY)
    AND ae.created_at <= TIMESTAMP_ADD(b.contract_due_date_ts, INTERVAL 30 DAY)
    AND NOT ae.payment_status  -- só recusas
)

SELECT
  periodo,
  refusal_reason,
  COUNT(*) AS total,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(PARTITION BY periodo), 2) AS pct_das_recusas
FROM tentativas
GROUP BY 1, 2
HAVING COUNT(*) >= 5
ORDER BY periodo, total DESC;
