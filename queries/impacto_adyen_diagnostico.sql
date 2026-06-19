-- ============================================================================
-- IMPACTO ADYEN — DIAGNÓSTICO COMPLETO
-- Arquivo: results/adyen_diagnostico.csv
--
-- Baseado na query original de motivos_churn (validada).
-- Classifica cada contrato em: Renovado, Cancelado, Recusado, Erro, etc.
-- Compara a DISTRIBUIÇÃO de diagnósticos PRE vs POS.
--
-- A pergunta certa: "a distribuição de desfechos mudou após a mudança Adyen?"
-- Especificamente: "a taxa de pagamento recusado caiu?"
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
    ys.plan_name,
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
      WHEN ys.contract_due_date < '2026-05-15' THEN 'PRE'
      ELSE 'POS'
    END AS periodo,

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

-- Tentativas ADYEN
tentativas_adyen AS (
  SELECT
    b.account_id, b.contract_id,
    ae.created_at AS event_date,
    CASE WHEN ae.payment_status THEN 'success' ELSE 'failed' END AS outcome,
    JSON_EXTRACT_SCALAR(ae.body, '$.refusalReason') AS refusal_reason
  FROM base b
  JOIN `airflow-datalake-prod.yalo.public_adyen_events` ae
    ON ae.account_id = b.account_id
  WHERE ae.created_at >= TIMESTAMP_SUB(b.contract_due_date_ts, INTERVAL 7 DAY)
    AND ae.created_at <= TIMESTAMP_ADD(b.contract_due_date_ts, INTERVAL 30 DAY)
),

-- Tentativas MUNDIPAGG
tentativas_mundi AS (
  SELECT
    b.account_id, b.contract_id,
    ppc.created_at AS event_date,
    CASE
      WHEN ppc.status = 'paid' THEN 'success'
      WHEN ppc.status = 'failed' THEN 'failed'
      ELSE ppc.status
    END AS outcome,
    ppc.acquirer_message AS refusal_reason
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
  SELECT *, 'adyen' AS acquirer FROM tentativas_adyen
  UNION ALL
  SELECT *, 'mundipagg' AS acquirer FROM tentativas_mundi
),

resumo_tentativas AS (
  SELECT
    account_id, contract_id,
    COUNT(*) AS qtd_tentativas,
    COUNTIF(outcome = 'success') AS qtd_sucessos,
    COUNTIF(outcome = 'failed') AS qtd_recusas,
    COUNTIF(outcome = 'success' AND acquirer = 'adyen') AS qtd_sucessos_adyen,
    COUNTIF(outcome = 'success' AND acquirer = 'mundipagg') AS qtd_sucessos_mundi,
    COUNTIF(acquirer = 'adyen') AS qtd_adyen,
    COUNTIF(acquirer = 'mundipagg') AS qtd_mundi
  FROM tentativas
  GROUP BY 1, 2
),

-- Diagnostico por contrato
diagnosticado AS (
  SELECT
    b.contract_id,
    b.contract_due_date,
    b.periodo,
    b.janela,
    b.is_recurrent,
    b.flag_novo_contrato,
    b.flag_unsubscription,
    COALESCE(rt.qtd_tentativas, 0) AS qtd_tentativas,
    COALESCE(rt.qtd_sucessos, 0) AS qtd_sucessos,
    COALESCE(rt.qtd_recusas, 0) AS qtd_recusas,
    COALESCE(rt.qtd_adyen, 0) AS qtd_adyen,
    COALESCE(rt.qtd_mundi, 0) AS qtd_mundi,

    CASE
      WHEN b.flag_novo_contrato = TRUE
        THEN 'Renovado'
      WHEN b.flag_unsubscription = TRUE
        THEN 'Cancelado (pediu)'
      WHEN b.is_recurrent = FALSE
        THEN 'Compra avulsa'
      WHEN COALESCE(rt.qtd_sucessos_adyen, 0) > 0
        THEN 'ERRO: Cobrado Adyen mas nao renovou'
      WHEN COALESCE(rt.qtd_sucessos_mundi, 0) > 0
        THEN 'ERRO: Cobrado Mundi mas nao renovou'
      WHEN COALESCE(rt.qtd_recusas, 0) > 0
        THEN 'Pagamento recusado'
      WHEN COALESCE(rt.qtd_tentativas, 0) = 0
        THEN 'Sem tentativa de cobranca'
      ELSE 'Investigar'
    END AS diagnostico,

    -- Flag: passou pela Adyen?
    CASE WHEN COALESCE(rt.qtd_adyen, 0) > 0 THEN TRUE ELSE FALSE END AS processado_adyen

  FROM base b
  LEFT JOIN resumo_tentativas rt
    ON rt.account_id = b.account_id AND rt.contract_id = b.contract_id
)

-- RESULTADO: distribuicao de diagnosticos por periodo e semana
-- Filtrado: só contratos que passaram pela Adyen
SELECT
  janela,
  periodo,
  diagnostico,
  COUNT(*) AS total,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(PARTITION BY janela), 2) AS pct_da_semana
FROM diagnosticado
WHERE janela IS NOT NULL
  AND processado_adyen = TRUE
GROUP BY 1, 2, 3
ORDER BY janela, total DESC;
