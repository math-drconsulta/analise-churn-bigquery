-- ============================================================================
-- EXPLORAR PAGAMENTOS — APROFUNDAMENTO
--
-- Objetivo: entender id_gateway, distribuicao de status, volume por tipo,
-- e como linkar com ref_yalo_subscriptions.
--
-- Rode cada BLOCO separadamente. Saidas sugeridas em results/:
--   BLOCO 1 → results/pgto_gateways.csv
--   BLOCO 2 → results/pgto_status_por_tipo.csv
--   BLOCO 3 → results/pgto_volume_mensal.csv
--   BLOCO 4 → results/pgto_origens.csv
--   BLOCO 5 → results/pgto_checkout_keys.csv
--   BLOCO 6 → results/pgto_link_yalo.csv
--   BLOCO 7 → results/pgto_tokens_cartao.csv
-- ============================================================================


-- ============================================================================
-- BLOCO 1: Quais gateways existem e quanto processam
-- ============================================================================
SELECT
  id_gateway,
  COUNT(*) AS transacoes,
  COUNT(DISTINCT customer_id) AS clientes_distintos,
  COUNTIF(status = 'A') AS autorizadas,
  COUNTIF(status = 'N') AS negadas,
  COUNTIF(status = 'P') AS pendentes,
  COUNTIF(status = 'K') AS checkout_criado,
  COUNTIF(status = 'E') AS enviado_mundi,
  COUNTIF(status = 'T') AS pre_auth_transferida,
  ROUND(100.0 * COUNTIF(status = 'A') / NULLIF(COUNTIF(status IN ('A', 'N')), 0), 1) AS taxa_aprov_pct,
  MIN(stamp_created) AS primeira_transacao,
  MAX(stamp_created) AS ultima_transacao
FROM `airflow-datalake-prod.PAGAMENTOS.transacoes`
GROUP BY id_gateway
ORDER BY transacoes DESC;


-- ============================================================================
-- BLOCO 2: Distribuicao de status por tipo de transacao
-- ============================================================================
SELECT
  tt.tipo,
  t.status,
  ts.descricao AS status_descricao,
  COUNT(*) AS transacoes,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(PARTITION BY tt.tipo), 1) AS pct_do_tipo
FROM `airflow-datalake-prod.PAGAMENTOS.transacoes` t
JOIN `airflow-datalake-prod.PAGAMENTOS.transacoes_tipos` tt
  ON tt.id_transacao_tipo = t.id_transacao_tipo
JOIN `airflow-datalake-prod.PAGAMENTOS.transacoes_status` ts
  ON ts.status = t.status
GROUP BY tt.tipo, t.status, ts.descricao
ORDER BY tt.tipo, transacoes DESC;


-- ============================================================================
-- BLOCO 3: Volume mensal (ultimos 12 meses) por gateway e status
-- ============================================================================
SELECT
  FORMAT_DATETIME('%Y-%m', stamp_created) AS mes,
  id_gateway,
  COUNT(*) AS transacoes,
  COUNTIF(status = 'A') AS autorizadas,
  COUNTIF(status = 'N') AS negadas,
  ROUND(100.0 * COUNTIF(status = 'A') / NULLIF(COUNTIF(status IN ('A', 'N')), 0), 1) AS taxa_aprov_pct,
  ROUND(SUM(CASE WHEN status = 'A' THEN valor ELSE 0 END), 2) AS valor_autorizado,
  ROUND(SUM(CASE WHEN status = 'N' THEN valor ELSE 0 END), 2) AS valor_negado
FROM `airflow-datalake-prod.PAGAMENTOS.transacoes`
WHERE stamp_created >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 12 MONTH)
GROUP BY mes, id_gateway
ORDER BY mes, id_gateway;


-- ============================================================================
-- BLOCO 4: Valores distintos de 'origem' (pra entender o que significa)
-- ============================================================================
SELECT
  origem,
  COUNT(*) AS transacoes,
  COUNT(DISTINCT customer_id) AS clientes,
  MIN(stamp_created) AS primeira,
  MAX(stamp_created) AS ultima
FROM `airflow-datalake-prod.PAGAMENTOS.transacoes`
GROUP BY origem
ORDER BY transacoes DESC;


-- ============================================================================
-- BLOCO 5: Checkout keys — canais de venda
-- ============================================================================
SELECT
  checkout_key,
  COUNT(*) AS transacoes,
  COUNTIF(status = 'A') AS autorizadas,
  COUNTIF(status = 'N') AS negadas,
  ROUND(100.0 * COUNTIF(status = 'A') / NULLIF(COUNTIF(status IN ('A', 'N')), 0), 1) AS taxa_aprov_pct
FROM `airflow-datalake-prod.PAGAMENTOS.transacoes`
WHERE stamp_created >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 6 MONTH)
GROUP BY checkout_key
HAVING transacoes >= 10
ORDER BY transacoes DESC;


-- ============================================================================
-- BLOCO 6: Tentativa de link com ref_yalo_subscriptions
-- Testa customer_id = person_id, id_portal_usuario, id_paciente
-- ============================================================================
WITH amostra_yalo AS (
  SELECT DISTINCT
    person_id,
    id_paciente,
    account_id
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions`
  WHERE contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 MONTH)
    AND account_type = 'holder'
    AND payment_method = 'credit_card'
  LIMIT 50000
),
amostra_pgto AS (
  SELECT DISTINCT customer_id
  FROM `airflow-datalake-prod.PAGAMENTOS.transacoes`
  WHERE stamp_created >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 3 MONTH)
)

SELECT
  'customer_id = person_id' AS tentativa_join,
  COUNT(*) AS matches
FROM amostra_pgto p
JOIN amostra_yalo y ON p.customer_id = y.person_id

UNION ALL

SELECT
  'customer_id = id_paciente' AS tentativa_join,
  COUNT(*) AS matches
FROM amostra_pgto p
JOIN amostra_yalo y ON p.customer_id = CAST(y.id_paciente AS STRING)

UNION ALL

SELECT
  'customer_id = account_id' AS tentativa_join,
  COUNT(*) AS matches
FROM amostra_pgto p
JOIN amostra_yalo y ON p.customer_id = y.account_id;


-- ============================================================================
-- BLOCO 7: Tokens de cartao — quantos cartoes por paciente, troca de cartao
-- ============================================================================
SELECT
  CASE
    WHEN cartoes = 1 THEN '1 cartao'
    WHEN cartoes = 2 THEN '2 cartoes'
    WHEN cartoes = 3 THEN '3 cartoes'
    ELSE '4+ cartoes'
  END AS faixa_cartoes,
  COUNT(*) AS pacientes,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) AS pct
FROM (
  SELECT
    customer_id,
    COUNT(DISTINCT id_tokens_cartoes_paciente) AS cartoes
  FROM `airflow-datalake-prod.PAGAMENTOS.transacoes`
  WHERE stamp_created >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 12 MONTH)
    AND id_tokens_cartoes_paciente IS NOT NULL
    AND id_tokens_cartoes_paciente > 0
  GROUP BY customer_id
)
GROUP BY faixa_cartoes
ORDER BY faixa_cartoes;
