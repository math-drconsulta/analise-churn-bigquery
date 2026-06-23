-- ============================================================================
-- EXPLORAR FEATURES DE PAGAMENTO (Frente A — score de falha de pagamento)
--
-- Objetivo: descobrir QUAIS campos pré-vencimento existem nas tabelas de
-- pagamento, pra definir o espaço de features de um modelo de falha de cobranca.
--
-- Rode cada BLOCO separadamente. Saídas sugeridas em results/:
--   BLOCO 1 → results/explorar_pgto_adyen_cols.csv
--   BLOCO 2 → results/explorar_pgto_adyen_body.csv   (amostra do JSON body)
--   BLOCO 3 → results/explorar_pgto_mundi_cols.csv
--   BLOCO 4 → results/explorar_pgto_body_keys.csv     (frequência das chaves do body)
-- ============================================================================


-- ============================================================================
-- BLOCO 1: Colunas da tabela de eventos Adyen
-- ============================================================================
SELECT column_name, data_type
FROM `airflow-datalake-prod.yalo`.INFORMATION_SCHEMA.COLUMNS
WHERE table_name = 'public_adyen_events'
ORDER BY ordinal_position;


-- ============================================================================
-- BLOCO 2: Amostra do JSON `body` — 15 sucessos + 15 recusas
-- (pra ver, na prática, quais campos vêm preenchidos: bandeira, valor,
--  tipo de cartão, bin, paymentMethod, refusalReason, etc.)
-- ============================================================================
WITH amostra AS (
  SELECT
    payment_status,
    body,
    ROW_NUMBER() OVER (PARTITION BY payment_status ORDER BY created_at DESC) AS rn
  FROM `airflow-datalake-prod.yalo.public_adyen_events`
  WHERE created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 DAY)
)
SELECT payment_status, TO_JSON_STRING(body) AS body_json
FROM amostra
WHERE rn <= 15
ORDER BY payment_status, rn;


-- ============================================================================
-- BLOCO 3: Colunas da tabela de cobrancas Mundipagg (acquirer_message etc.)
-- ============================================================================
SELECT column_name, data_type
FROM `airflow-datalake-prod.yalo`.INFORMATION_SCHEMA.COLUMNS
WHERE table_name = 'public_payment_partner_charges'
ORDER BY ordinal_position;


-- ============================================================================
-- BLOCO 4: Frequência das chaves de 1º nível do `body` Adyen
-- (mostra quais campos existem e quão preenchidos estão — só roda se `body`
--  for tipo JSON; se for STRING, use o BLOCO 2 pra inspecionar manualmente)
-- ============================================================================
WITH eventos AS (
  SELECT body
  FROM `airflow-datalake-prod.yalo.public_adyen_events`
  WHERE created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
  LIMIT 50000
),
chaves AS (
  SELECT key
  FROM eventos, UNNEST(`bqutil.fn.json_extract_keys`(TO_JSON_STRING(body))) AS key
)
SELECT key, COUNT(*) AS ocorrencias
FROM chaves
GROUP BY key
ORDER BY ocorrencias DESC;
