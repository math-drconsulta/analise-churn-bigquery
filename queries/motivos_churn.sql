WITH plans_info AS (
  SELECT
    account_id,
    DATE(due_date) AS due_date_d,
    is_recurrent
  FROM `airflow-datalake-prod.yalo.public_account_plans`
  WHERE DATE(due_date) BETWEEN '2025-05-01' AND '2026-04-30'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY account_id, DATE(due_date)
    ORDER BY created_at DESC
  ) = 1
),

base AS (
  SELECT
    ys.account_id,
    ys.person_id,
    ypp.cpf,
    ys.contract_id,
    ys.account_register_date,
    ys.account_due_date,
    ys.contract_register_date,
    ys.contract_due_date,
    TIMESTAMP(ys.contract_due_date, "America/Sao_Paulo") AS contract_due_date_ts,
    ys.plan_b2type,
    ys.plan_name,
    ys.plan_months_duration,
    ys.payment_method,
    pi.is_recurrent,
    ys.flag_7days_cancellation_account,
    ys.flag_unsubscription,
    ys.unsubscription_date,
    ys.days_diff_until_next_contract,
    CASE 
      WHEN ys.days_diff_until_next_contract BETWEEN -30 AND 60 THEN TRUE 
      ELSE FALSE 
    END AS flag_novo_contrato
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  LEFT JOIN `airflow-datalake-prod.yalo.public_people` ypp
    ON ypp.id = ys.person_id
  LEFT JOIN plans_info pi
    ON  pi.account_id = ys.account_id
    AND pi.due_date_d = DATE(ys.contract_due_date)
  WHERE TRUE
    AND account_due_date_month BETWEEN '2025-05-01' AND '2026-04-01'
    AND date_month = account_due_date_month
    AND account_type = 'holder'
    AND plan_name NOT LIKE '%gratis%'
),

tentativas_adyen AS (
  SELECT
    b.account_id, b.contract_id,
    ae.created_at AS event_date, 'adyen' AS acquirer,
    CASE WHEN ae.payment_status THEN 'success' ELSE 'failed' END AS outcome,
    JSON_EXTRACT_SCALAR(ae.body, '$.resultCode')    AS status_detail,
    JSON_EXTRACT_SCALAR(ae.body, '$.refusalReason') AS refusal_reason,
    CAST(ae.acquirer_return_code AS STRING)         AS return_code
  FROM base b
  JOIN `airflow-datalake-prod.yalo.public_adyen_events` ae
    ON ae.account_id = b.account_id
  WHERE ae.created_at >= TIMESTAMP_SUB(b.contract_due_date_ts, INTERVAL 7 DAY)
    AND ae.created_at <= TIMESTAMP_ADD(b.contract_due_date_ts, INTERVAL 30 DAY)
),

tentativas_mundi AS (
  SELECT
    b.account_id, b.contract_id,
    ppc.created_at AS event_date, 'mundipagg' AS acquirer,
    CASE 
      WHEN ppc.status = 'paid'   THEN 'success'
      WHEN ppc.status = 'failed' THEN 'failed'
      ELSE ppc.status
    END AS outcome,
    ppc.status            AS status_detail,
    ppc.acquirer_message  AS refusal_reason,
    CAST(NULL AS STRING)  AS return_code
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

resumo_tentativas AS (
  SELECT
    account_id, contract_id,
    COUNT(*) AS qtd_tentativas,
    COUNTIF(outcome = 'success') AS qtd_sucessos,
    COUNTIF(outcome = 'failed')  AS qtd_recusas,
    COUNTIF(outcome = 'success' AND acquirer = 'adyen')     AS qtd_sucessos_adyen,
    COUNTIF(outcome = 'success' AND acquirer = 'mundipagg') AS qtd_sucessos_mundi,
    ARRAY_AGG(
      STRUCT(event_date, acquirer, outcome, status_detail, refusal_reason, return_code)
      ORDER BY event_date DESC LIMIT 1
    )[OFFSET(0)] AS ultima
  FROM tentativas
  GROUP BY account_id, contract_id
)

SELECT
  DATE_TRUNC(b.account_due_date, MONTH) AS mes_referencia,
  b.account_id, b.cpf, b.contract_id,
  b.account_register_date, b.account_due_date,
  b.contract_register_date, b.contract_due_date,
  b.plan_b2type, b.plan_name, b.plan_months_duration,
  b.payment_method, b.is_recurrent,
  b.flag_7days_cancellation_account,
  b.flag_unsubscription, b.unsubscription_date,
  b.days_diff_until_next_contract, b.flag_novo_contrato,

  COALESCE(rt.qtd_tentativas, 0) AS qtd_tentativas,
  COALESCE(rt.qtd_sucessos, 0)   AS qtd_sucessos,
  COALESCE(rt.qtd_recusas, 0)    AS qtd_recusas,

  rt.ultima.event_date     AS ultima_tentativa_data,
  rt.ultima.acquirer       AS ultima_tentativa_adquirente,
  rt.ultima.outcome        AS ultima_tentativa_outcome,
  rt.ultima.status_detail  AS ultima_tentativa_status_detalhe,
  rt.ultima.refusal_reason AS ultima_tentativa_motivo_recusa,
  rt.ultima.return_code    AS ultima_tentativa_codigo_retorno,

  CASE
    -- 1. Renovou: tudo certo
    WHEN b.flag_novo_contrato = TRUE
        THEN 'Renovado: Continuou'

    -- 2. Cancelamento explícito
    WHEN b.flag_unsubscription = TRUE
        THEN 'Vencido Corretamente: Cancelado'

    -- 3. Compra avulsa não-recorrente
    WHEN b.is_recurrent = FALSE
        THEN 'Vencido Corretamente: Compra Avulsa Não-Recorrente'

    -- 4. Pagamento manual (boleto, pix, débito) — depende do usuário pagar
    WHEN b.payment_method IN ('boleto','pix','debit_card')
        THEN 'Vencido Corretamente: Meio de Pagamento Manual'

    -- 5. Cobrou com sucesso mas o contrato não renovou — ERRO TÉCNICO
    WHEN COALESCE(rt.qtd_sucessos_adyen, 0) > 0
        THEN 'ERRO TÉCNICO: Cobrado (Adyen) mas não renovado'

    WHEN COALESCE(rt.qtd_sucessos_mundi, 0) > 0
        THEN 'ERRO TÉCNICO: Cobrado (Mundipagg) mas não renovado'

    -- 6. Cobrança recusada — vencido corretamente
    WHEN COALESCE(rt.qtd_recusas, 0) > 0
        THEN 'Vencido Corretamente: Pagamento Recusado'

    -- 7. Nenhuma tentativa na janela — ALERTA
    WHEN COALESCE(rt.qtd_tentativas, 0) = 0
        THEN 'ALERTA: Nenhuma tentativa recente encontrada'

    ELSE 'Investigar Manualmente'
  END AS diagnostico

FROM base b
LEFT JOIN resumo_tentativas rt
  ON  rt.account_id  = b.account_id
  AND rt.contract_id = b.contract_id
ORDER BY b.account_id, b.contract_due_date