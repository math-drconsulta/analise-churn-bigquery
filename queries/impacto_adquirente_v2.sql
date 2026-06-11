-- ============================================================================
-- IMPACTO DA MUDANÇA DE ADQUIRENTE v2 — Atualizado 11/06/2026
-- Data da mudança: 15/05/2026
--
-- PRE: 3 semanas antes (24/abr a 14/mai)
-- POS: 15/mai a 10/jun (~27 dias)
--
-- Responde:
--   1. Aumento medio em p.p. da taxa de renovacao (POS vs media PRE)
--   2. Quantas pessoas retidas a mais isso representa
--
-- 3 queries:
--   STEP 1: Resumo por janela semanal → results/adquirente_v2_semanal.csv
--   STEP 2: Resumo PRE vs POS agregado → results/adquirente_v2_resumo.csv
--   STEP 3: Dia a dia → results/adquirente_v2_diario.csv
-- ============================================================================


-- ============================================================================
-- STEP 1: POR JANELA SEMANAL
-- ============================================================================

WITH base AS (
  SELECT
    ys.contract_id,
    ys.contract_due_date,
    ys.account_due_date,
    ys.plan_months_duration,
    CASE WHEN ys.account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo,

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
      WHEN ys.contract_due_date BETWEEN '2026-06-05' AND '2026-06-11' THEN '7_POS sem4 (05-11/jun)'
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
    AND ys.contract_due_date BETWEEN '2026-04-24' AND '2026-06-11'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
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
-- STEP 2: AGREGADO PRE vs POS (resposta direta pra gerente)
-- ============================================================================

WITH base AS (
  SELECT
    ys.contract_id,
    ys.contract_due_date,
    ys.account_due_date,

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
    AND ys.contract_due_date BETWEEN '2026-04-24' AND '2026-06-11'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
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
-- STEP 3: DIA A DIA
-- ============================================================================

WITH base AS (
  SELECT
    ys.contract_id,
    ys.contract_due_date,
    ys.account_due_date,

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
    AND ys.contract_due_date BETWEEN '2026-04-24' AND '2026-06-11'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
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
