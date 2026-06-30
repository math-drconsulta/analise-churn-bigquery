-- ============================================================================
-- EXPLORAR JOINS DE PAGAMENTO (v2 — sem sales_adyen)
--
-- sales_adyen era uma CTE do analista. Reconstruimos os campos relevantes
-- direto da public_adyen_events.
--
-- Rode cada BLOCO separadamente. Saidas sugeridas em results/:
--   BLOCO 1 → results/join_pgto_prod_ili_cols.csv
--   BLOCO 2 → results/join_pgto_prod_ili_orders_amostra.csv
--   BLOCO 3 → results/join_pgto_cadeia_mundi_teste.csv
--   BLOCO 4 → results/join_pgto_public_people_cols.csv
--   BLOCO 5 → results/join_pgto_adyen_body_keys.csv
--   BLOCO 6 → results/join_pgto_cadeia_adyen_teste.csv
--   BLOCO 7 → results/join_pgto_prod_ili_payers_amostra.csv
-- ============================================================================


-- ============================================================================
-- BLOCO 1: Colunas das tabelas prod_ili_*
-- ============================================================================
SELECT 'prod_ili_orders' AS tabela, column_name, data_type
FROM `airflow-datalake-prod.yalo`.INFORMATION_SCHEMA.COLUMNS
WHERE table_name = 'prod_ili_orders'

UNION ALL

SELECT 'prod_ili_payment' AS tabela, column_name, data_type
FROM `airflow-datalake-prod.yalo`.INFORMATION_SCHEMA.COLUMNS
WHERE table_name = 'prod_ili_payment'

UNION ALL

SELECT 'prod_ili_payers' AS tabela, column_name, data_type
FROM `airflow-datalake-prod.yalo`.INFORMATION_SCHEMA.COLUMNS
WHERE table_name = 'prod_ili_payers'

UNION ALL

SELECT 'prod_ili_plans' AS tabela, column_name, data_type
FROM `airflow-datalake-prod.yalo`.INFORMATION_SCHEMA.COLUMNS
WHERE table_name = 'prod_ili_plans'

ORDER BY tabela, column_name;


-- ============================================================================
-- BLOCO 2: Amostra de prod_ili_orders (20 linhas)
-- ============================================================================
SELECT *
FROM `airflow-datalake-prod.yalo.prod_ili_orders`
LIMIT 20;


-- ============================================================================
-- BLOCO 3: Teste da cadeia Mundipagg completa
-- ppsc → pps → ppsa → ppa → accounts → people
-- ============================================================================
WITH cycles AS (
  SELECT ppsc.id AS cycle_id, ppsc.payment_partner_subscription_id
  FROM `airflow-datalake-prod.yalo.public_payment_partner_subscription_cycles` ppsc
  LIMIT 100000
)

SELECT
  COUNT(*) AS total_cycles,
  COUNT(pps.id) AS match_pps,
  COUNT(ppsa.payment_partner_subscription_id) AS match_ppsa,
  COUNT(ppa.id) AS match_ppa,
  COUNT(ac.id) AS match_accounts,
  COUNT(pe.id) AS match_people,
  ROUND(100.0 * COUNT(pe.id) / NULLIF(COUNT(*), 0), 1) AS pct_match_people
FROM cycles c
INNER JOIN `airflow-datalake-prod.yalo.public_payment_partner_subscriptions` pps
  ON pps.id = c.payment_partner_subscription_id
LEFT JOIN `airflow-datalake-prod.yalo.public_payment_partner_subscriptions_accounts` ppsa
  ON ppsa.payment_partner_subscription_id = pps.id
LEFT JOIN `airflow-datalake-prod.yalo.public_payment_partner_accounts` ppa
  ON ppa.id = ppsa.payment_partner_account_id
LEFT JOIN `airflow-datalake-prod.yalo.public_accounts` ac
  ON ac.id = ppa.account_id
LEFT JOIN `airflow-datalake-prod.yalo.public_people` pe
  ON pe.id = ac.person_id;


-- ============================================================================
-- BLOCO 4: Colunas de public_people
-- ============================================================================
SELECT column_name, data_type
FROM `airflow-datalake-prod.yalo`.INFORMATION_SCHEMA.COLUMNS
WHERE table_name = 'public_people'
ORDER BY ordinal_position;


-- ============================================================================
-- BLOCO 5: Reconstruir o que seria sales_adyen — campos do body disponiveis
-- Pega 50 eventos recentes e extrai os campos que o join do analista usava
-- ============================================================================
SELECT
  ae.account_id,
  ae.person_id,
  ae.subscription_id,
  ae.payment_status,
  ae.acquirer_return_code,
  JSON_EXTRACT_SCALAR(ae.body, '$.pspReference') AS psp_reference,
  JSON_EXTRACT_SCALAR(ae.body, '$.merchantReference') AS merchant_reference,
  JSON_EXTRACT_SCALAR(ae.body, '$.resultCode') AS result_code,
  JSON_EXTRACT_SCALAR(ae.body, '$.refusalReason') AS refusal_reason,
  -- Campos do additionalData que podem ter CPF ou shopper
  JSON_EXTRACT_SCALAR(ae.body, '$.additionalData.tokenization.shopperReference') AS shopper_reference,
  JSON_EXTRACT_SCALAR(ae.body, '$.additionalData.recurring.shopperReference') AS recurring_shopper_ref,
  JSON_EXTRACT_SCALAR(ae.body, '$.additionalData.shopperReference') AS addata_shopper_ref,
  -- Campos de topo que podem ter shopper
  JSON_EXTRACT_SCALAR(ae.body, '$.shopperReference') AS top_shopper_ref,
  JSON_EXTRACT_SCALAR(ae.body, '$.socialSecurityNumber') AS cpf_body,
  ae.created_at
FROM `airflow-datalake-prod.yalo.public_adyen_events` ae
WHERE ae.created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
ORDER BY ae.created_at DESC
LIMIT 50;


-- ============================================================================
-- BLOCO 6: Teste cadeia Adyen → orders → payers → people
-- Usa shopper_reference extraido do body como link com orderId
-- ============================================================================
WITH adyen_parsed AS (
  SELECT
    ae.account_id,
    ae.person_id,
    ae.payment_status,
    JSON_EXTRACT_SCALAR(ae.body, '$.pspReference') AS psp_reference,
    JSON_EXTRACT_SCALAR(ae.body, '$.additionalData.tokenization.shopperReference') AS shopper_reference,
    JSON_EXTRACT_SCALAR(ae.body, '$.socialSecurityNumber') AS cpf_body,
    ae.created_at
  FROM `airflow-datalake-prod.yalo.public_adyen_events` ae
  WHERE ae.created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
)

SELECT
  COUNT(*) AS total_adyen_events,
  -- Quantos tem shopper_reference preenchido
  COUNTIF(shopper_reference IS NOT NULL) AS com_shopper_ref,
  ROUND(100.0 * COUNTIF(shopper_reference IS NOT NULL) / COUNT(*), 1) AS pct_com_shopper,
  -- Quantos tem CPF no body
  COUNTIF(cpf_body IS NOT NULL) AS com_cpf_body,
  -- Match com orders via shopper_reference = orderId
  COUNT(o.orderId) AS match_orders,
  ROUND(100.0 * COUNT(o.orderId) / NULLIF(COUNT(*), 0), 1) AS pct_match_orders,
  -- Match com payers via orders
  COUNT(pa.payerId) AS match_payers,
  -- Match com people via CPF do payer
  COUNT(pe.id) AS match_people_via_payer,
  -- Match com pps via psp_reference
  COUNT(pps.id) AS match_pps_sub,
  COUNT(ppsc.id) AS match_ppsc_cycle,
  -- Match direto: account_id do adyen → ref_yalo_subscriptions
  COUNT(DISTINCT ap.account_id) AS match_yalo_account
FROM adyen_parsed ap
LEFT JOIN `airflow-datalake-prod.yalo.prod_ili_orders` o
  ON CAST(o.orderId AS STRING) = ap.shopper_reference
LEFT JOIN `airflow-datalake-prod.yalo.prod_ili_payers` pa
  ON pa.payerId = o.payerId
LEFT JOIN `airflow-datalake-prod.yalo.public_people` pe
  ON pe.cpf = pa.cpf
LEFT JOIN `airflow-datalake-prod.yalo.public_payment_partner_subscriptions` pps
  ON pps.subscription_external_id = ap.psp_reference
LEFT JOIN `airflow-datalake-prod.yalo.public_payment_partner_subscription_cycles` ppsc
  ON ppsc.subscription_cycle_external_id = ap.psp_reference;


-- ============================================================================
-- BLOCO 7: Amostra de prod_ili_payers (ver se tem CPF, nome, etc.)
-- ============================================================================
SELECT *
FROM `airflow-datalake-prod.yalo.prod_ili_payers`
LIMIT 20;
