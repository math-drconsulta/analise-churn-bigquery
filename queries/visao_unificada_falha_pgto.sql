-- ============================================================================
-- VISAO UNIFICADA: FALHA DE PAGAMENTO POR PACIENTE
--
-- Caminho validado:
--   public_adyen_events.psp_reference
--     → ppsc.subscription_cycle_external_id (96.8% match)
--     → pps → ppsa → ppa → public_accounts → public_people (100% match)
--     → ref_yalo_subscriptions (via account_id)
--
-- Rode cada BLOCO separadamente. Saidas sugeridas em results/:
--   BLOCO 1 → results/unif_pgto_por_contrato.csv
--   BLOCO 2 → results/unif_pgto_perfil_falha.csv
--   BLOCO 3 → results/unif_pgto_historico_paciente.csv
--   BLOCO 4 → results/unif_pgto_features_pgto.csv
-- ============================================================================


-- ============================================================================
-- BLOCO 1: Cada contrato com suas tentativas de pagamento enriquecidas
-- Liga adyen_events → cycles → subscriptions → accounts → people → yalo
-- Janela: contratos vencendo abr-jun 2026
-- ============================================================================
WITH base_contratos AS (
  SELECT
    ys.contract_id,
    ys.account_id,
    ys.person_id AS yalo_person_id,
    ys.holder_person_id,
    ys.id_paciente,
    ys.contract_due_date,
    ys.plan_name,
    ys.plan_months_duration,
    ys.account_contract_number,
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
    AND ys.contract_due_date BETWEEN '2026-04-01' AND '2026-06-15'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),

-- Tentativas Adyen enriquecidas via cadeia ppsc → people
adyen_enriquecido AS (
  SELECT
    ae.account_id,
    ae.payment_status,
    ae.acquirer_return_code,
    ae.created_at AS tentativa_ts,
    ae.cycle,
    ae.retry_cycle,
    JSON_EXTRACT_SCALAR(ae.body, '$.pspReference') AS psp_reference,
    JSON_EXTRACT_SCALAR(ae.body, '$.resultCode') AS result_code,
    JSON_EXTRACT_SCALAR(ae.body, '$.refusalReason') AS refusal_reason,
    JSON_EXTRACT_SCALAR(ae.body, '$.refusalReasonCode') AS refusal_code,
    JSON_EXTRACT_SCALAR(ae.body, '$.additionalData.cardFunction') AS card_function,
    JSON_EXTRACT_SCALAR(ae.body, '$.additionalData.fundingSource') AS funding_source,
    JSON_EXTRACT_SCALAR(ae.body, '$.additionalData.issuerCountry') AS issuer_country,
    JSON_EXTRACT_SCALAR(ae.body, '$.additionalData.isCardCommercial') AS is_commercial,
    JSON_EXTRACT_SCALAR(ae.body, '$.additionalData.merchantAdviceCode') AS merchant_advice,
    JSON_EXTRACT_SCALAR(ae.body, '$.additionalData.realtimeAccountUpdaterStatus') AS account_updater_status,
    -- Via cadeia ppsc → pps → ppa → people
    ppsc.id AS cycle_id,
    pps.plan_id AS pps_plan_id,
    pe.id AS people_id,
    pe.cpf,
    pe.gender,
    pe.birth_date
  FROM `airflow-datalake-prod.yalo.public_adyen_events` ae
  -- Join via psp_reference → subscription_cycle_external_id
  LEFT JOIN `airflow-datalake-prod.yalo.public_payment_partner_subscription_cycles` ppsc
    ON ppsc.subscription_cycle_external_id = JSON_EXTRACT_SCALAR(ae.body, '$.pspReference')
  LEFT JOIN `airflow-datalake-prod.yalo.public_payment_partner_subscriptions` pps
    ON pps.id = ppsc.payment_partner_subscription_id
  LEFT JOIN `airflow-datalake-prod.yalo.public_payment_partner_subscriptions_accounts` ppsa
    ON ppsa.payment_partner_subscription_id = pps.id
  LEFT JOIN `airflow-datalake-prod.yalo.public_payment_partner_accounts` ppa
    ON ppa.id = ppsa.payment_partner_account_id
  LEFT JOIN `airflow-datalake-prod.yalo.public_accounts` ac
    ON ac.id = ppa.account_id
  LEFT JOIN `airflow-datalake-prod.yalo.public_people` pe
    ON pe.id = ac.person_id
  WHERE ae.created_at >= TIMESTAMP('2026-03-25')
    AND ae.created_at <= TIMESTAMP('2026-06-25')
)

-- Resultado: cada contrato com resumo de tentativas
SELECT
  bc.contract_id,
  bc.account_id,
  bc.contract_due_date,
  bc.plan_months_duration,
  bc.account_contract_number,
  bc.churn_sn,
  bc.flag_unsubscription,
  -- Resumo tentativas
  COUNT(ae.psp_reference) AS total_tentativas,
  COUNTIF(ae.payment_status = TRUE) AS sucessos,
  COUNTIF(ae.payment_status = FALSE) AS falhas,
  -- Motivos de recusa (top)
  ARRAY_TO_STRING(
    ARRAY_AGG(DISTINCT ae.refusal_reason IGNORE NULLS ORDER BY ae.refusal_reason LIMIT 3),
    ' | '
  ) AS motivos_recusa,
  -- Timing
  MIN(ae.tentativa_ts) AS primeira_tentativa,
  MAX(ae.tentativa_ts) AS ultima_tentativa,
  TIMESTAMP_DIFF(MAX(ae.tentativa_ts), MIN(ae.tentativa_ts), DAY) AS dias_tentando,
  -- Cycles e retries
  MAX(ae.cycle) AS max_cycle,
  MAX(ae.retry_cycle) AS max_retry_cycle,
  -- Dados do cartao
  MAX(ae.card_function) AS card_function,
  MAX(ae.funding_source) AS funding_source,
  MAX(ae.is_commercial) AS is_commercial,
  MAX(ae.merchant_advice) AS merchant_advice_last,
  MAX(ae.account_updater_status) AS account_updater_status,
  -- Dados do paciente (via cadeia)
  MAX(ae.cpf) AS cpf,
  MAX(ae.gender) AS gender,
  MAX(ae.birth_date) AS birth_date,
  -- Match quality
  COUNTIF(ae.cycle_id IS NOT NULL) AS tentativas_com_match_cycle,
  COUNTIF(ae.people_id IS NOT NULL) AS tentativas_com_match_people
FROM base_contratos bc
LEFT JOIN adyen_enriquecido ae
  ON ae.account_id = bc.account_id
  AND ae.tentativa_ts >= TIMESTAMP_SUB(TIMESTAMP(bc.contract_due_date), INTERVAL 7 DAY)
  AND ae.tentativa_ts <= TIMESTAMP_ADD(TIMESTAMP(bc.contract_due_date), INTERVAL 30 DAY)
GROUP BY 1,2,3,4,5,6,7
ORDER BY bc.contract_due_date;


-- ============================================================================
-- BLOCO 2: Perfil de falha — quem falha vs quem passa
-- Agrupa por diagnostico × perfil demografico
-- ============================================================================
WITH base_contratos AS (
  SELECT
    ys.contract_id,
    ys.account_id,
    ys.contract_due_date,
    ys.plan_months_duration,
    ys.account_contract_number,
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
    AND ys.contract_due_date BETWEEN '2026-04-01' AND '2026-06-15'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),

tentativas AS (
  SELECT
    ae.account_id,
    ae.payment_status,
    JSON_EXTRACT_SCALAR(ae.body, '$.refusalReason') AS refusal_reason,
    JSON_EXTRACT_SCALAR(ae.body, '$.additionalData.cardFunction') AS card_function,
    JSON_EXTRACT_SCALAR(ae.body, '$.additionalData.fundingSource') AS funding_source,
    JSON_EXTRACT_SCALAR(ae.body, '$.additionalData.isCardCommercial') AS is_commercial,
    ae.created_at AS tentativa_ts
  FROM `airflow-datalake-prod.yalo.public_adyen_events` ae
  WHERE ae.created_at >= TIMESTAMP('2026-03-25')
    AND ae.created_at <= TIMESTAMP('2026-06-25')
),

por_contrato AS (
  SELECT
    bc.contract_id,
    bc.churn_sn,
    bc.flag_unsubscription,
    bc.plan_months_duration,
    bc.account_contract_number,
    COUNT(t.payment_status) AS tentativas,
    COUNTIF(t.payment_status = TRUE) AS sucessos,
    COUNTIF(t.payment_status = FALSE) AS falhas,
    MAX(t.card_function) AS card_function,
    MAX(t.funding_source) AS funding_source,
    MAX(t.is_commercial) AS is_commercial,
    -- Diagnostico
    CASE
      WHEN bc.churn_sn = 'N' THEN 'renovado'
      WHEN bc.flag_unsubscription = TRUE THEN 'cancelou_ativo'
      WHEN COUNTIF(t.payment_status = FALSE) > 0 AND COUNTIF(t.payment_status = TRUE) = 0
        THEN 'falha_pagamento'
      WHEN COUNTIF(t.payment_status = TRUE) > 0 AND bc.churn_sn = 'S'
        THEN 'cobrado_mas_churnou'
      WHEN COUNT(t.payment_status) = 0 AND bc.churn_sn = 'S'
        THEN 'sem_tentativa'
      ELSE 'outro'
    END AS diagnostico
  FROM base_contratos bc
  LEFT JOIN tentativas t
    ON t.account_id = bc.account_id
    AND t.tentativa_ts >= TIMESTAMP_SUB(TIMESTAMP(bc.contract_due_date), INTERVAL 7 DAY)
    AND t.tentativa_ts <= TIMESTAMP_ADD(TIMESTAMP(bc.contract_due_date), INTERVAL 30 DAY)
  GROUP BY 1,2,3,4,5
)

-- Resultado: perfil por diagnostico
SELECT
  diagnostico,
  COUNT(*) AS contratos,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) AS pct_total,
  -- Perfil de pagamento
  ROUND(AVG(tentativas), 1) AS media_tentativas,
  ROUND(AVG(falhas), 1) AS media_falhas,
  -- Por duracao
  ROUND(100.0 * COUNTIF(plan_months_duration = 6) / COUNT(*), 1) AS pct_6m,
  ROUND(100.0 * COUNTIF(plan_months_duration = 12) / COUNT(*), 1) AS pct_12m,
  -- Por ciclo
  ROUND(100.0 * COUNTIF(account_contract_number = 1) / COUNT(*), 1) AS pct_1o_contrato,
  -- Card function
  ROUND(100.0 * COUNTIF(card_function = 'Consumer') / NULLIF(COUNTIF(card_function IS NOT NULL), 0), 1) AS pct_consumer,
  -- Funding source
  ROUND(100.0 * COUNTIF(funding_source = 'CREDIT') / NULLIF(COUNTIF(funding_source IS NOT NULL), 0), 1) AS pct_credit,
  ROUND(100.0 * COUNTIF(funding_source = 'DEBIT') / NULLIF(COUNTIF(funding_source IS NOT NULL), 0), 1) AS pct_debit
FROM por_contrato
GROUP BY diagnostico
ORDER BY contratos DESC;


-- ============================================================================
-- BLOCO 3: Historico do paciente — pacientes com falhas recorrentes
-- Quantos contratos anteriores o paciente teve, quantas falhas no historico
-- ============================================================================
WITH contratos_recentes AS (
  SELECT
    ys.contract_id,
    ys.account_id,
    ys.holder_person_id,
    ys.contract_due_date,
    ys.account_contract_number,
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
    AND ys.contract_due_date BETWEEN '2026-04-01' AND '2026-06-15'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),

-- Contratos anteriores (dedup)
contratos_anteriores_dedup AS (
  SELECT
    h.contract_id,
    h.holder_person_id,
    h.contract_due_date,
    h.account_due_date
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` h
  WHERE h.account_type = 'holder'
    AND h.payment_method = 'credit_card'
    AND h.plan_name NOT LIKE '%gratis%'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY h.contract_id ORDER BY h.date_month DESC
  ) = 1
),

historico AS (
  SELECT
    cr.contract_id AS contrato_atual,
    cr.churn_sn AS churn_atual,
    COUNT(DISTINCT h.contract_id) AS contratos_anteriores,
    COUNTIF(DATE_DIFF(h.account_due_date, h.contract_due_date, DAY) <= 7) AS churns_anteriores
  FROM contratos_recentes cr
  LEFT JOIN contratos_anteriores_dedup h
    ON h.holder_person_id = cr.holder_person_id
    AND h.contract_due_date < cr.contract_due_date
  GROUP BY 1, 2
)

-- Resultado: churn atual vs historico de falhas
SELECT
  CASE
    WHEN contratos_anteriores = 0 THEN '0_primeiro_contrato'
    WHEN churns_anteriores = 0 THEN '1_nunca_churnou'
    WHEN churns_anteriores = 1 THEN '2_churnou_1x'
    ELSE '3_churnou_2x+'
  END AS perfil_historico,
  churn_atual,
  COUNT(*) AS contratos,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(PARTITION BY churn_atual), 1) AS pct_do_grupo
FROM historico
GROUP BY perfil_historico, churn_atual
ORDER BY churn_atual, perfil_historico;


-- ============================================================================
-- BLOCO 4: Features de pagamento pra modelo
-- Uma linha por contrato com features extraidas das tentativas
-- ============================================================================
WITH base_contratos AS (
  SELECT
    ys.contract_id,
    ys.account_id,
    ys.contract_due_date,
    ys.plan_months_duration,
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
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),

tentativas AS (
  SELECT
    ae.account_id,
    ae.payment_status,
    ae.cycle,
    ae.retry_cycle,
    ae.created_at AS tentativa_ts,
    JSON_EXTRACT_SCALAR(ae.body, '$.refusalReason') AS refusal_reason,
    JSON_EXTRACT_SCALAR(ae.body, '$.refusalReasonCode') AS refusal_code,
    JSON_EXTRACT_SCALAR(ae.body, '$.additionalData.merchantAdviceCode') AS merchant_advice
  FROM `airflow-datalake-prod.yalo.public_adyen_events` ae
  WHERE ae.created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 600 DAY)
)

SELECT
  bc.contract_id,
  bc.churn_sn,
  bc.plan_months_duration,
  bc.contract_due_date,
  -- Volume
  COUNT(t.payment_status) AS total_tentativas,
  COUNTIF(t.payment_status = TRUE) AS sucessos,
  COUNTIF(t.payment_status = FALSE) AS falhas,
  -- Timing
  TIMESTAMP_DIFF(MIN(t.tentativa_ts), TIMESTAMP(bc.contract_due_date), DAY) AS dias_antes_1a_tentativa,
  TIMESTAMP_DIFF(MAX(t.tentativa_ts), TIMESTAMP(bc.contract_due_date), DAY) AS dias_apos_ultima_tentativa,
  TIMESTAMP_DIFF(MAX(t.tentativa_ts), MIN(t.tentativa_ts), DAY) AS janela_tentativas_dias,
  -- Cycles
  MAX(t.cycle) AS max_cycle,
  MAX(t.retry_cycle) AS max_retry,
  -- Motivos (flags binarias)
  COUNTIF(t.refusal_reason = 'Refused') AS n_refused_generico,
  COUNTIF(t.refusal_reason = 'Not enough balance') AS n_saldo_insuficiente,
  COUNTIF(t.refusal_reason LIKE '%Adyen%retry%') AS n_blocked_retry,
  COUNTIF(t.refusal_reason = 'Issuer Suspected Fraud') AS n_fraude,
  COUNTIF(t.refusal_reason = 'Restricted Card') AS n_cartao_restrito,
  COUNTIF(t.refusal_reason = 'Expired Card') AS n_cartao_vencido,
  COUNTIF(t.refusal_reason = 'Invalid Card Number') AS n_cartao_invalido,
  COUNTIF(t.refusal_reason = 'Blocked Card') AS n_cartao_bloqueado,
  -- Merchant advice (sinal de retry)
  COUNTIF(t.merchant_advice LIKE '%New account%') AS n_advice_new_account,
  COUNTIF(t.merchant_advice LIKE '%Retry after%') AS n_advice_retry_after,
  -- Teve pelo menos 1 sucesso antes de falhar?
  CASE
    WHEN COUNTIF(t.payment_status = TRUE) > 0 AND COUNTIF(t.payment_status = FALSE) > 0 THEN 1
    ELSE 0
  END AS mix_sucesso_falha
FROM base_contratos bc
LEFT JOIN tentativas t
  ON t.account_id = bc.account_id
  AND t.tentativa_ts >= TIMESTAMP_SUB(TIMESTAMP(bc.contract_due_date), INTERVAL 7 DAY)
  AND t.tentativa_ts <= TIMESTAMP_ADD(TIMESTAMP(bc.contract_due_date), INTERVAL 30 DAY)
GROUP BY 1,2,3,4
ORDER BY bc.contract_id;
