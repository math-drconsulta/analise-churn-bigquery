-- ============================================================================
-- IMPACTO DA MUDANÇA NA ADYEN v3
-- Filtrado: SOMENTE contratos cuja cobrança passou pela Adyen
--
-- A mudança foi interna da Adyen (atualização no sistema de processamento)
-- implementada em 15/05/2026. Queremos medir se a taxa de renovação
-- dos contratos processados pela Adyen mudou.
--
-- Lógica:
--   1. Pegar contratos credit_card com vencimento no período
--   2. Filtrar só os que tiveram tentativa na Adyen (public_adyen_events)
--   3. Comparar PRE (3 semanas antes) vs POS (4 semanas depois)
--
-- 3 outputs:
--   STEP 1: Semanal → results/adyen_v3_semanal.csv
--   STEP 2: Agregado PRE vs POS → results/adyen_v3_resumo.csv
--   STEP 3: Diário → results/adyen_v3_diario.csv
-- ============================================================================


-- ============================================================================
-- STEP 1: SEMANAL
-- ============================================================================

WITH contratos AS (
  SELECT
    ys.contract_id,
    ys.account_id,
    ys.contract_due_date,
    ys.account_due_date,
    ys.plan_months_duration,
    CASE WHEN ys.account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo,
    TIMESTAMP(ys.contract_due_date, "America/Sao_Paulo") AS contract_due_date_ts,

    CASE
      WHEN DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) > 7 THEN 'N'
      ELSE 'S'
    END AS churn_sn,

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
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),

-- Filtrar: só contratos que tiveram tentativa na ADYEN
-- (ao redor do vencimento: 7 dias antes a 30 dias depois)
contratos_adyen AS (
  SELECT DISTINCT c.contract_id
  FROM contratos c
  INNER JOIN `airflow-datalake-prod.yalo.public_adyen_events` ae
    ON ae.account_id = c.account_id
  WHERE ae.created_at >= TIMESTAMP_SUB(c.contract_due_date_ts, INTERVAL 7 DAY)
    AND ae.created_at <= TIMESTAMP_ADD(c.contract_due_date_ts, INTERVAL 30 DAY)
),

base AS (
  SELECT c.*
  FROM contratos c
  INNER JOIN contratos_adyen ca ON ca.contract_id = c.contract_id
)

SELECT
  janela,
  periodo,
  COUNT(*) AS total_contratos,
  SUM(CASE WHEN churn_sn = 'N' THEN 1 ELSE 0 END) AS renovaram,
  SUM(CASE WHEN churn_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  ROUND(100.0 * SUM(CASE WHEN churn_sn = 'N' THEN 1 ELSE 0 END) / COUNT(*), 2) AS taxa_renovacao,
  ROUND(100.0 * SUM(CASE WHEN churn_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 2) AS churn_rate
FROM base
WHERE janela IS NOT NULL
GROUP BY 1, 2
ORDER BY janela;


-- ============================================================================
-- STEP 2: AGREGADO PRE vs POS (só Adyen)
-- ============================================================================

WITH contratos AS (
  SELECT
    ys.contract_id,
    ys.account_id,
    ys.contract_due_date,
    ys.account_due_date,
    TIMESTAMP(ys.contract_due_date, "America/Sao_Paulo") AS contract_due_date_ts,

    CASE
      WHEN DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) > 7 THEN 'N'
      ELSE 'S'
    END AS churn_sn,

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
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),

contratos_adyen AS (
  SELECT DISTINCT c.contract_id
  FROM contratos c
  INNER JOIN `airflow-datalake-prod.yalo.public_adyen_events` ae
    ON ae.account_id = c.account_id
  WHERE ae.created_at >= TIMESTAMP_SUB(c.contract_due_date_ts, INTERVAL 7 DAY)
    AND ae.created_at <= TIMESTAMP_ADD(c.contract_due_date_ts, INTERVAL 30 DAY)
),

base AS (
  SELECT c.*
  FROM contratos c
  INNER JOIN contratos_adyen ca ON ca.contract_id = c.contract_id
)

SELECT
  periodo,
  COUNT(*) AS total_contratos,
  SUM(CASE WHEN churn_sn = 'N' THEN 1 ELSE 0 END) AS renovaram,
  SUM(CASE WHEN churn_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  ROUND(100.0 * SUM(CASE WHEN churn_sn = 'N' THEN 1 ELSE 0 END) / COUNT(*), 2) AS taxa_renovacao,
  ROUND(100.0 * SUM(CASE WHEN churn_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 2) AS churn_rate
FROM base
GROUP BY 1
ORDER BY 1;


-- ============================================================================
-- STEP 3: DIA A DIA (só Adyen)
-- ============================================================================

WITH contratos AS (
  SELECT
    ys.contract_id,
    ys.account_id,
    ys.contract_due_date,
    ys.account_due_date,
    TIMESTAMP(ys.contract_due_date, "America/Sao_Paulo") AS contract_due_date_ts,

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
    AND ys.contract_due_date BETWEEN '2026-04-24' AND '2026-06-15'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),

contratos_adyen AS (
  SELECT DISTINCT c.contract_id
  FROM contratos c
  INNER JOIN `airflow-datalake-prod.yalo.public_adyen_events` ae
    ON ae.account_id = c.account_id
  WHERE ae.created_at >= TIMESTAMP_SUB(c.contract_due_date_ts, INTERVAL 7 DAY)
    AND ae.created_at <= TIMESTAMP_ADD(c.contract_due_date_ts, INTERVAL 30 DAY)
),

base AS (
  SELECT c.*
  FROM contratos c
  INNER JOIN contratos_adyen ca ON ca.contract_id = c.contract_id
)

SELECT
  contract_due_date AS dia,
  CASE WHEN contract_due_date >= '2026-05-15' THEN 'POS' ELSE 'PRE' END AS periodo,
  COUNT(*) AS total_contratos,
  SUM(CASE WHEN churn_sn = 'N' THEN 1 ELSE 0 END) AS renovaram,
  SUM(CASE WHEN churn_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  ROUND(100.0 * SUM(CASE WHEN churn_sn = 'N' THEN 1 ELSE 0 END) / COUNT(*), 2) AS taxa_renovacao
FROM base
GROUP BY 1, 2
ORDER BY 1;
