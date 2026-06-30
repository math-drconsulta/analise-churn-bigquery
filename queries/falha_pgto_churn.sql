-- ============================================================================
-- FALHA DE PAGAMENTO → CHURN: VISAO UNIFICADA
--
-- Perguntas:
--   1. Quanto das falhas de pagamento viram churn de fato?
--   2. Qual a proporcao Adyen vs Mundipagg?
--   3. Apos a mudanca Adyen em 15/05, houve melhora? (semanal)
--
-- Rode cada BLOCO separadamente. Saidas sugeridas:
--   BLOCO 1 → results/falha_pgto_diagnostico.csv
--   BLOCO 2 → results/falha_pgto_adyen_vs_mundi.csv
--   BLOCO 3 → results/falha_pgto_semanal.csv
--   BLOCO 4 → results/falha_pgto_motivos.csv
-- ============================================================================


-- ============================================================================
-- BLOCO 1: Diagnostico por contrato — falha de pgto vs churn vs desfecho
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
    ys.person_id,
    ys.contract_due_date,
    TIMESTAMP(ys.contract_due_date, "America/Sao_Paulo") AS contract_due_date_ts,
    ys.plan_months_duration,
    ys.flag_unsubscription,
    ys.days_diff_until_next_contract,
    pi.is_recurrent,
    CASE
      WHEN DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) > 7 THEN 'N'
      ELSE 'S'
    END AS churn_sn,
    CASE
      WHEN ys.days_diff_until_next_contract BETWEEN -30 AND 60 THEN TRUE
      ELSE FALSE
    END AS flag_novo_contrato,
    CASE
      WHEN ys.contract_due_date < '2026-05-15' THEN 'PRE'
      ELSE 'POS'
    END AS periodo,
    -- Semanas: 4 PRE + 6 POS (ate 23/06)
    CASE
      WHEN ys.contract_due_date BETWEEN '2026-04-17' AND '2026-04-23' THEN 'sem_-4 (17-23/abr)'
      WHEN ys.contract_due_date BETWEEN '2026-04-24' AND '2026-04-30' THEN 'sem_-3 (24-30/abr)'
      WHEN ys.contract_due_date BETWEEN '2026-05-01' AND '2026-05-07' THEN 'sem_-2 (01-07/mai)'
      WHEN ys.contract_due_date BETWEEN '2026-05-08' AND '2026-05-14' THEN 'sem_-1 (08-14/mai)'
      WHEN ys.contract_due_date BETWEEN '2026-05-15' AND '2026-05-21' THEN 'sem_+1 (15-21/mai)'
      WHEN ys.contract_due_date BETWEEN '2026-05-22' AND '2026-05-28' THEN 'sem_+2 (22-28/mai)'
      WHEN ys.contract_due_date BETWEEN '2026-05-29' AND '2026-06-04' THEN 'sem_+3 (29/mai-04/jun)'
      WHEN ys.contract_due_date BETWEEN '2026-06-05' AND '2026-06-11' THEN 'sem_+4 (05-11/jun)'
      WHEN ys.contract_due_date BETWEEN '2026-06-12' AND '2026-06-18' THEN 'sem_+5 (12-18/jun)'
      WHEN ys.contract_due_date BETWEEN '2026-06-19' AND '2026-06-23' THEN 'sem_+6 (19-23/jun)'
    END AS semana
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  LEFT JOIN plans_info pi
    ON pi.account_id = ys.account_id
    AND pi.due_date_d = DATE(ys.contract_due_date)
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.contract_due_date BETWEEN '2026-04-17' AND '2026-06-23'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),

-- Tentativas ADYEN
tentativas_adyen AS (
  SELECT
    b.contract_id,
    ae.payment_status,
    CASE WHEN ae.payment_status THEN 'success' ELSE 'failed' END AS outcome,
    JSON_EXTRACT_SCALAR(ae.body, '$.refusalReason') AS refusal_reason,
    'adyen' AS acquirer
  FROM base b
  JOIN `airflow-datalake-prod.yalo.public_adyen_events` ae
    ON ae.account_id = b.account_id
  WHERE ae.created_at >= TIMESTAMP_SUB(b.contract_due_date_ts, INTERVAL 7 DAY)
    AND ae.created_at <= TIMESTAMP_ADD(b.contract_due_date_ts, INTERVAL 30 DAY)
),

-- Tentativas MUNDIPAGG
tentativas_mundi AS (
  SELECT
    b.contract_id,
    ppc.is_success AS payment_status,
    CASE
      WHEN ppc.status = 'paid' THEN 'success'
      WHEN ppc.status = 'failed' THEN 'failed'
      ELSE ppc.status
    END AS outcome,
    ppc.acquirer_message AS refusal_reason,
    'mundipagg' AS acquirer
  FROM base b
  JOIN `airflow-datalake-prod.yalo.public_payment_partner_accounts` ppa
    ON ppa.account_id = b.account_id
  JOIN `airflow-datalake-prod.yalo.public_payment_partner_subscriptions_accounts` ppsa
    ON ppsa.payment_partner_account_id = ppa.id
  JOIN `airflow-datalake-prod.yalo.public_payment_partner_subscriptions` pps
    ON pps.id = ppsa.payment_partner_subscription_id
  JOIN `airflow-datalake-prod.yalo.public_payment_partner_subscription_cycles` ppsc
    ON ppsc.payment_partner_subscription_id = pps.id
  JOIN `airflow-datalake-prod.yalo.public_payment_partner_invoices` ppi
    ON ppi.payment_partner_cycle_id = ppsc.id
  JOIN `airflow-datalake-prod.yalo.public_payment_partner_charges` ppc
    ON ppc.payment_partner_invoice_id = ppi.id
  JOIN `airflow-datalake-prod.yalo.public_acquirer_types` at2
    ON at2.id = pps.acquirer_type_id
    AND at2.id = '63efdc8b-c3ee-d525-9e99-3205ae527000'
  WHERE ppc.created_at >= TIMESTAMP_SUB(b.contract_due_date_ts, INTERVAL 7 DAY)
    AND ppc.created_at <= TIMESTAMP_ADD(b.contract_due_date_ts, INTERVAL 30 DAY)
),

tentativas AS (
  SELECT * FROM tentativas_adyen
  UNION ALL
  SELECT * FROM tentativas_mundi
),

resumo_por_contrato AS (
  SELECT
    contract_id,
    COUNT(*) AS qtd_tentativas,
    COUNTIF(outcome = 'success') AS qtd_sucessos,
    COUNTIF(outcome = 'failed') AS qtd_recusas,
    COUNTIF(acquirer = 'adyen') AS qtd_adyen,
    COUNTIF(acquirer = 'mundipagg') AS qtd_mundi,
    COUNTIF(outcome = 'success' AND acquirer = 'adyen') AS sucesso_adyen,
    COUNTIF(outcome = 'success' AND acquirer = 'mundipagg') AS sucesso_mundi,
    -- Adquirente principal (mais tentativas)
    CASE
      WHEN COUNTIF(acquirer = 'adyen') >= COUNTIF(acquirer = 'mundipagg') AND COUNTIF(acquirer = 'adyen') > 0 THEN 'adyen'
      WHEN COUNTIF(acquirer = 'mundipagg') > 0 THEN 'mundipagg'
      ELSE 'nenhum'
    END AS acquirer_principal
  FROM tentativas
  GROUP BY contract_id
),

diagnosticado AS (
  SELECT
    b.*,
    COALESCE(r.qtd_tentativas, 0) AS qtd_tentativas,
    COALESCE(r.qtd_sucessos, 0) AS qtd_sucessos,
    COALESCE(r.qtd_recusas, 0) AS qtd_recusas,
    COALESCE(r.qtd_adyen, 0) AS qtd_adyen,
    COALESCE(r.qtd_mundi, 0) AS qtd_mundi,
    COALESCE(r.acquirer_principal, 'nenhum') AS acquirer_principal,

    CASE
      WHEN b.churn_sn = 'N' THEN 'renovado'
      WHEN b.flag_unsubscription = TRUE THEN 'cancelou_ativo'
      WHEN COALESCE(r.qtd_recusas, 0) > 0 AND COALESCE(r.qtd_sucessos, 0) = 0
        THEN 'falha_pagamento'
      WHEN COALESCE(r.qtd_sucessos, 0) > 0 AND b.churn_sn = 'S'
        THEN 'cobrado_mas_churnou'
      WHEN COALESCE(r.qtd_tentativas, 0) = 0 AND b.churn_sn = 'S'
        THEN 'sem_tentativa'
      ELSE 'outro'
    END AS diagnostico

  FROM base b
  LEFT JOIN resumo_por_contrato r ON r.contract_id = b.contract_id
)

-- RESULTADO BLOCO 1
SELECT
  diagnostico,
  churn_sn,
  COUNT(*) AS contratos,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) AS pct_total,
  -- dos que falharam, quantos migraram gratis vs saiu de vez
  COUNTIF(churn_sn = 'S') AS churners,
  ROUND(AVG(qtd_tentativas), 1) AS media_tentativas,
  ROUND(AVG(qtd_recusas), 1) AS media_recusas
FROM diagnosticado
WHERE semana IS NOT NULL
GROUP BY diagnostico, churn_sn
ORDER BY contratos DESC;


-- ============================================================================
-- BLOCO 2: Proporcao Adyen vs Mundipagg (por semana)
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
    CASE WHEN DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) > 7 THEN 'N' ELSE 'S' END AS churn_sn,
    CASE WHEN ys.contract_due_date < '2026-05-15' THEN 'PRE' ELSE 'POS' END AS periodo,
    CASE
      WHEN ys.contract_due_date BETWEEN '2026-04-17' AND '2026-04-23' THEN 'sem_-4'
      WHEN ys.contract_due_date BETWEEN '2026-04-24' AND '2026-04-30' THEN 'sem_-3'
      WHEN ys.contract_due_date BETWEEN '2026-05-01' AND '2026-05-07' THEN 'sem_-2'
      WHEN ys.contract_due_date BETWEEN '2026-05-08' AND '2026-05-14' THEN 'sem_-1'
      WHEN ys.contract_due_date BETWEEN '2026-05-15' AND '2026-05-21' THEN 'sem_+1'
      WHEN ys.contract_due_date BETWEEN '2026-05-22' AND '2026-05-28' THEN 'sem_+2'
      WHEN ys.contract_due_date BETWEEN '2026-05-29' AND '2026-06-04' THEN 'sem_+3'
      WHEN ys.contract_due_date BETWEEN '2026-06-05' AND '2026-06-11' THEN 'sem_+4'
      WHEN ys.contract_due_date BETWEEN '2026-06-12' AND '2026-06-18' THEN 'sem_+5'
      WHEN ys.contract_due_date BETWEEN '2026-06-19' AND '2026-06-23' THEN 'sem_+6'
    END AS semana
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  LEFT JOIN plans_info pi ON pi.account_id = ys.account_id AND pi.due_date_d = DATE(ys.contract_due_date)
  WHERE ys.account_type = 'holder' AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12) AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.contract_due_date BETWEEN '2026-04-17' AND '2026-06-23'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),
tent_adyen AS (
  SELECT b.contract_id, 'adyen' AS acquirer,
    CASE WHEN ae.payment_status THEN 'success' ELSE 'failed' END AS outcome
  FROM base b
  JOIN `airflow-datalake-prod.yalo.public_adyen_events` ae ON ae.account_id = b.account_id
  WHERE ae.created_at >= TIMESTAMP_SUB(b.contract_due_date_ts, INTERVAL 7 DAY)
    AND ae.created_at <= TIMESTAMP_ADD(b.contract_due_date_ts, INTERVAL 30 DAY)
),
tent_mundi AS (
  SELECT b.contract_id, 'mundipagg' AS acquirer,
    CASE WHEN ppc.status = 'paid' THEN 'success' ELSE 'failed' END AS outcome
  FROM base b
  JOIN `airflow-datalake-prod.yalo.public_payment_partner_accounts` ppa ON ppa.account_id = b.account_id
  JOIN `airflow-datalake-prod.yalo.public_payment_partner_subscriptions_accounts` ppsa ON ppsa.payment_partner_account_id = ppa.id
  JOIN `airflow-datalake-prod.yalo.public_payment_partner_subscriptions` pps ON pps.id = ppsa.payment_partner_subscription_id
  JOIN `airflow-datalake-prod.yalo.public_payment_partner_subscription_cycles` ppsc ON ppsc.payment_partner_subscription_id = pps.id
  JOIN `airflow-datalake-prod.yalo.public_payment_partner_invoices` ppi ON ppi.payment_partner_cycle_id = ppsc.id
  JOIN `airflow-datalake-prod.yalo.public_payment_partner_charges` ppc ON ppc.payment_partner_invoice_id = ppi.id
  JOIN `airflow-datalake-prod.yalo.public_acquirer_types` at2 ON at2.id = pps.acquirer_type_id AND at2.id = '63efdc8b-c3ee-d525-9e99-3205ae527000'
  WHERE ppc.created_at >= TIMESTAMP_SUB(b.contract_due_date_ts, INTERVAL 7 DAY)
    AND ppc.created_at <= TIMESTAMP_ADD(b.contract_due_date_ts, INTERVAL 30 DAY)
),
tentativas AS (
  SELECT * FROM tent_adyen UNION ALL SELECT * FROM tent_mundi
),
por_contrato AS (
  SELECT
    contract_id,
    COUNTIF(acquirer = 'adyen') AS tent_adyen,
    COUNTIF(acquirer = 'mundipagg') AS tent_mundi,
    COUNTIF(acquirer = 'adyen' AND outcome = 'success') AS suc_adyen,
    COUNTIF(acquirer = 'mundipagg' AND outcome = 'success') AS suc_mundi,
    COUNTIF(acquirer = 'adyen' AND outcome = 'failed') AS fail_adyen,
    COUNTIF(acquirer = 'mundipagg' AND outcome = 'failed') AS fail_mundi
  FROM tentativas
  GROUP BY contract_id
)

-- RESULTADO BLOCO 2
SELECT
  b.semana,
  b.periodo,
  COUNT(DISTINCT b.contract_id) AS contratos,
  -- Proporcao de contratos com tentativas por acquirer
  COUNT(DISTINCT CASE WHEN pc.tent_adyen > 0 THEN b.contract_id END) AS contratos_adyen,
  COUNT(DISTINCT CASE WHEN pc.tent_mundi > 0 THEN b.contract_id END) AS contratos_mundi,
  COUNT(DISTINCT CASE WHEN COALESCE(pc.tent_adyen,0) = 0 AND COALESCE(pc.tent_mundi,0) = 0 THEN b.contract_id END) AS sem_tentativa,
  -- Taxas de aprovacao
  SAFE_DIVIDE(SUM(pc.suc_adyen), NULLIF(SUM(pc.tent_adyen), 0)) AS taxa_aprov_adyen,
  SAFE_DIVIDE(SUM(pc.suc_mundi), NULLIF(SUM(pc.tent_mundi), 0)) AS taxa_aprov_mundi,
  -- Churn
  COUNTIF(b.churn_sn = 'S') AS churners,
  ROUND(100.0 * COUNTIF(b.churn_sn = 'S') / COUNT(*), 1) AS taxa_churn
FROM base b
LEFT JOIN por_contrato pc ON pc.contract_id = b.contract_id
WHERE b.semana IS NOT NULL
GROUP BY b.semana, b.periodo
ORDER BY b.semana;


-- ============================================================================
-- BLOCO 3: Evolucao semanal — taxa de falha e taxa de churn (pre/pos 15/05)
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
    ys.flag_unsubscription,
    CASE WHEN DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) > 7 THEN 'N' ELSE 'S' END AS churn_sn,
    CASE WHEN ys.contract_due_date < '2026-05-15' THEN 'PRE' ELSE 'POS' END AS periodo,
    CASE
      WHEN ys.contract_due_date BETWEEN '2026-04-17' AND '2026-04-23' THEN 'sem_-4'
      WHEN ys.contract_due_date BETWEEN '2026-04-24' AND '2026-04-30' THEN 'sem_-3'
      WHEN ys.contract_due_date BETWEEN '2026-05-01' AND '2026-05-07' THEN 'sem_-2'
      WHEN ys.contract_due_date BETWEEN '2026-05-08' AND '2026-05-14' THEN 'sem_-1'
      WHEN ys.contract_due_date BETWEEN '2026-05-15' AND '2026-05-21' THEN 'sem_+1'
      WHEN ys.contract_due_date BETWEEN '2026-05-22' AND '2026-05-28' THEN 'sem_+2'
      WHEN ys.contract_due_date BETWEEN '2026-05-29' AND '2026-06-04' THEN 'sem_+3'
      WHEN ys.contract_due_date BETWEEN '2026-06-05' AND '2026-06-11' THEN 'sem_+4'
      WHEN ys.contract_due_date BETWEEN '2026-06-12' AND '2026-06-18' THEN 'sem_+5'
      WHEN ys.contract_due_date BETWEEN '2026-06-19' AND '2026-06-23' THEN 'sem_+6'
    END AS semana
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  LEFT JOIN plans_info pi ON pi.account_id = ys.account_id AND pi.due_date_d = DATE(ys.contract_due_date)
  WHERE ys.account_type = 'holder' AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12) AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.contract_due_date BETWEEN '2026-04-17' AND '2026-06-23'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),
tent_adyen AS (
  SELECT b.contract_id,
    CASE WHEN ae.payment_status THEN 'success' ELSE 'failed' END AS outcome
  FROM base b
  JOIN `airflow-datalake-prod.yalo.public_adyen_events` ae ON ae.account_id = b.account_id
  WHERE ae.created_at >= TIMESTAMP_SUB(b.contract_due_date_ts, INTERVAL 7 DAY)
    AND ae.created_at <= TIMESTAMP_ADD(b.contract_due_date_ts, INTERVAL 30 DAY)
),
por_contrato AS (
  SELECT
    contract_id,
    COUNT(*) AS tentativas,
    COUNTIF(outcome = 'success') AS sucessos,
    COUNTIF(outcome = 'failed') AS falhas
  FROM tent_adyen
  GROUP BY contract_id
)

-- RESULTADO BLOCO 3: evolucao semanal focada em Adyen
SELECT
  b.semana,
  b.periodo,
  COUNT(*) AS contratos,
  -- Contratos com tentativa Adyen
  COUNT(DISTINCT pc.contract_id) AS com_tentativa_adyen,
  -- Taxa de aprovacao Adyen (por tentativa)
  ROUND(100.0 * SAFE_DIVIDE(SUM(pc.sucessos), SUM(pc.tentativas)), 1) AS taxa_aprov_adyen_pct,
  -- Contratos onde Adyen NUNCA aprovou
  COUNTIF(COALESCE(pc.sucessos, 0) = 0 AND COALESCE(pc.falhas, 0) > 0) AS so_falha_adyen,
  ROUND(100.0 * COUNTIF(COALESCE(pc.sucessos, 0) = 0 AND COALESCE(pc.falhas, 0) > 0)
    / NULLIF(COUNT(DISTINCT pc.contract_id), 0), 1) AS pct_so_falha_adyen,
  -- Churn e cancelamento
  COUNTIF(b.churn_sn = 'S') AS churners,
  ROUND(100.0 * COUNTIF(b.churn_sn = 'S') / COUNT(*), 1) AS taxa_churn_pct,
  COUNTIF(b.flag_unsubscription = TRUE) AS cancelamentos_ativos,
  -- Churn SEM cancelamento ativo (provavel falha de pagamento)
  COUNTIF(b.churn_sn = 'S' AND COALESCE(b.flag_unsubscription, FALSE) = FALSE) AS churn_involuntario,
  ROUND(100.0 * COUNTIF(b.churn_sn = 'S' AND COALESCE(b.flag_unsubscription, FALSE) = FALSE)
    / COUNT(*), 1) AS taxa_churn_involuntario_pct
FROM base b
LEFT JOIN por_contrato pc ON pc.contract_id = b.contract_id
WHERE b.semana IS NOT NULL
GROUP BY b.semana, b.periodo
ORDER BY b.semana;


-- ============================================================================
-- BLOCO 4: Top motivos de recusa Adyen — PRE vs POS
-- ============================================================================
WITH base AS (
  SELECT
    ys.account_id, ys.contract_id, ys.contract_due_date,
    TIMESTAMP(ys.contract_due_date, "America/Sao_Paulo") AS contract_due_date_ts,
    CASE WHEN ys.contract_due_date < '2026-05-15' THEN 'PRE' ELSE 'POS' END AS periodo
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder' AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12) AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.contract_due_date BETWEEN '2026-04-17' AND '2026-06-23'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),
recusas AS (
  SELECT
    b.periodo,
    COALESCE(
      JSON_EXTRACT_SCALAR(ae.body, '$.refusalReason'),
      'Sem motivo informado'
    ) AS motivo,
    JSON_EXTRACT_SCALAR(ae.body, '$.refusalReasonCode') AS motivo_code
  FROM base b
  JOIN `airflow-datalake-prod.yalo.public_adyen_events` ae
    ON ae.account_id = b.account_id
  WHERE ae.payment_status = FALSE
    AND ae.created_at >= TIMESTAMP_SUB(b.contract_due_date_ts, INTERVAL 7 DAY)
    AND ae.created_at <= TIMESTAMP_ADD(b.contract_due_date_ts, INTERVAL 30 DAY)
)

-- RESULTADO BLOCO 4
SELECT
  motivo,
  motivo_code,
  COUNTIF(periodo = 'PRE') AS recusas_pre,
  COUNTIF(periodo = 'POS') AS recusas_pos,
  COUNT(*) AS total,
  ROUND(100.0 * COUNTIF(periodo = 'PRE') / NULLIF(
    (SELECT COUNT(*) FROM recusas WHERE periodo = 'PRE'), 0), 1) AS pct_pre,
  ROUND(100.0 * COUNTIF(periodo = 'POS') / NULLIF(
    (SELECT COUNT(*) FROM recusas WHERE periodo = 'POS'), 0), 1) AS pct_pos
FROM recusas
GROUP BY motivo, motivo_code
HAVING total >= 10
ORDER BY total DESC;
