-- ============================================================================
-- RAIO-X MUNDIPAGG — SOLICITACAO PM GROWTH
--
-- Indicadores solicitados:
--   1. Total de clientes ativos / recorrencia ativa (%)
--   2. Clientes em outros status (churn 30d+, suspensos, inativos)
--   3. Distribuicao por tipo de cartao (credito a vista, parcelado, debito)
--   4. Frequencia de cobranca (diaria, semanal, mensal, customizada)
--   5. Taxa de sucesso (ultimos 30 dias)
--   6. Taxa de chargeback (ultimos 90 dias)
--   7. Receita mensal processada (R$)
--
-- Rode cada BLOCO separadamente. Saidas sugeridas:
--   BLOCO 1 → results/mundi_clientes_status.csv
--   BLOCO 2 → results/mundi_tipo_cartao.csv
--   BLOCO 3 → results/mundi_frequencia_cobranca.csv
--   BLOCO 4 → results/mundi_taxa_sucesso_30d.csv
--   BLOCO 5 → results/mundi_chargeback_90d.csv
--   BLOCO 6 → results/mundi_receita_mensal.csv
-- ============================================================================


-- ============================================================================
-- BLOCO 1: Total de clientes e status (ativo, churn, suspenso, inativo)
--
-- Usa public_payment_partner_subscriptions (status da recorrencia)
-- linkado com public_payment_partner_subscription_cycles (ultimo ciclo)
-- ============================================================================
SELECT
  pps.status AS status_subscription,
  COUNT(DISTINCT pps.id) AS subscriptions,
  COUNT(DISTINCT ppa.account_id) AS clientes_distintos,
  ROUND(100.0 * COUNT(DISTINCT ppa.account_id)
    / SUM(COUNT(DISTINCT ppa.account_id)) OVER(), 1) AS pct
FROM `airflow-datalake-prod.yalo.public_payment_partner_subscriptions` pps
LEFT JOIN `airflow-datalake-prod.yalo.public_payment_partner_subscriptions_accounts` ppsa
  ON ppsa.payment_partner_subscription_id = pps.id
LEFT JOIN `airflow-datalake-prod.yalo.public_payment_partner_accounts` ppa
  ON ppa.id = ppsa.payment_partner_account_id
GROUP BY pps.status
ORDER BY clientes_distintos DESC;


-- ============================================================================
-- BLOCO 2: Distribuicao por tipo de cartao
-- (usa tabela PAGAMENTOS.transacoes — campo id_transacao_tipo)
-- Ultimos 90 dias para ter volume representativo
-- ============================================================================
SELECT
  tt.tipo AS tipo_transacao,
  COUNT(*) AS transacoes,
  COUNT(DISTINCT t.customer_id) AS clientes,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) AS pct_transacoes,
  ROUND(SUM(t.valor), 2) AS valor_total
FROM `airflow-datalake-prod.PAGAMENTOS.transacoes` t
JOIN `airflow-datalake-prod.PAGAMENTOS.transacoes_tipos` tt
  ON tt.id_transacao_tipo = t.id_transacao_tipo
WHERE t.stamp_created >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 90 DAY)
GROUP BY tt.tipo
ORDER BY transacoes DESC;


-- ============================================================================
-- BLOCO 3: Frequencia de cobranca
-- Analisa o intervalo entre ciclos de cada subscription
-- ============================================================================
WITH ciclos AS (
  SELECT
    payment_partner_subscription_id,
    created_at,
    LAG(created_at) OVER (
      PARTITION BY payment_partner_subscription_id
      ORDER BY created_at
    ) AS ciclo_anterior
  FROM `airflow-datalake-prod.yalo.public_payment_partner_subscription_cycles`
),
intervalos AS (
  SELECT
    payment_partner_subscription_id,
    TIMESTAMP_DIFF(created_at, ciclo_anterior, DAY) AS dias_entre_ciclos
  FROM ciclos
  WHERE ciclo_anterior IS NOT NULL
)

SELECT
  CASE
    WHEN dias_entre_ciclos <= 2  THEN 'diaria'
    WHEN dias_entre_ciclos <= 10 THEN 'semanal'
    WHEN dias_entre_ciclos <= 35 THEN 'mensal'
    ELSE 'customizada'
  END AS frequencia,
  COUNT(*) AS ciclos,
  COUNT(DISTINCT payment_partner_subscription_id) AS subscriptions,
  ROUND(100.0 * COUNT(DISTINCT payment_partner_subscription_id)
    / SUM(COUNT(DISTINCT payment_partner_subscription_id)) OVER(), 1) AS pct_subscriptions,
  ROUND(AVG(dias_entre_ciclos), 1) AS media_dias
FROM intervalos
GROUP BY frequencia
ORDER BY ciclos DESC;


-- ============================================================================
-- BLOCO 4: Taxa de sucesso (ultimos 30 dias)
-- Status A = autorizada, N = negada
-- ============================================================================
SELECT
  COUNT(*) AS total_transacoes,
  COUNTIF(status = 'A') AS autorizadas,
  COUNTIF(status = 'N') AS negadas,
  COUNTIF(status NOT IN ('A', 'N')) AS outros_status,
  ROUND(100.0 * COUNTIF(status = 'A')
    / NULLIF(COUNTIF(status IN ('A', 'N')), 0), 2) AS taxa_sucesso_pct,
  ROUND(100.0 * COUNTIF(status = 'N')
    / NULLIF(COUNTIF(status IN ('A', 'N')), 0), 2) AS taxa_recusa_pct
FROM `airflow-datalake-prod.PAGAMENTOS.transacoes`
WHERE stamp_created >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 30 DAY);


-- ============================================================================
-- BLOCO 5: Taxa de chargeback (ultimos 90 dias)
--
-- A tabela PAGAMENTOS.transacoes_tipos nao tem tipo "chargeback".
-- Estrategia: buscar nos eventos Adyen (notification de CHARGEBACK)
-- e na public_payment_partner_charges (status de chargeback/disputa).
-- ============================================================================

-- 5A: Adyen — notificacoes de chargeback no body
SELECT
  'adyen' AS fonte,
  JSON_EXTRACT_SCALAR(body, '$.eventCode') AS event_code,
  COUNT(*) AS eventos,
  COUNT(DISTINCT account_id) AS clientes
FROM `airflow-datalake-prod.yalo.public_adyen_events`
WHERE created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
  AND (LOWER(JSON_EXTRACT_SCALAR(body, '$.eventCode')) LIKE '%chargeback%'
    OR LOWER(JSON_EXTRACT_SCALAR(body, '$.eventCode')) LIKE '%dispute%')
GROUP BY event_code

UNION ALL

-- 5B: Cancelamento Captura na PAGAMENTOS.transacoes (tipo 4)
-- pode indicar estornos/chargebacks processados
SELECT
  'pagamentos' AS fonte,
  'Cancelamento Captura' AS event_code,
  COUNT(*) AS eventos,
  COUNT(DISTINCT customer_id) AS clientes
FROM `airflow-datalake-prod.PAGAMENTOS.transacoes`
WHERE stamp_created >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 90 DAY)
  AND id_transacao_tipo = 4

ORDER BY eventos DESC;


-- ============================================================================
-- BLOCO 6: Receita mensal processada (R$)
-- Ultimos 12 meses, apenas transacoes autorizadas
-- ============================================================================
SELECT
  FORMAT_DATETIME('%Y-%m', stamp_created) AS mes,
  COUNT(*) AS transacoes_autorizadas,
  COUNT(DISTINCT customer_id) AS clientes_cobrando,
  ROUND(SUM(valor), 2) AS receita_processada_brl,
  ROUND(AVG(valor), 2) AS ticket_medio
FROM `airflow-datalake-prod.PAGAMENTOS.transacoes`
WHERE status = 'A'
  AND stamp_created >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 12 MONTH)
GROUP BY mes
ORDER BY mes;
