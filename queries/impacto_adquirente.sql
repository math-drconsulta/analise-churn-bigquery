-- ============================================================================
-- IMPACTO DA MUDANÇA DE ADQUIRENTE — 15/05/2026
--
-- STEP 0: DIAGNÓSTICO — rode isso primeiro pra entender as datas disponíveis
-- ============================================================================

-- 0A) Qual a data mais recente em anl_churn_contratos?
SELECT
  MAX(contract_due_date) AS max_contract_due_date,
  MAX(contract_due_date_month) AS max_contract_due_date_month,
  COUNT(*) AS total_rows
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE order_payment_method = 'credit_card';

-- 0B) Qual a data mais recente em ref_yalo_subscriptions?
SELECT
  MAX(contract_due_date) AS max_contract_due_date,
  MAX(account_due_date) AS max_account_due_date,
  COUNT(*) AS total_rows
FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions`
WHERE account_type = 'holder'
  AND payment_method = 'credit_card'
  AND plan_months_duration IN (6, 12);


-- ============================================================================
-- STEP 1: QUERY PRINCIPAL — usa ref_yalo_subscriptions (dados mais frescos)
-- Arquivo: results/impacto_adquirente.csv
--
-- Lógica de renovação: mesma da anl_churn_contratos
--   Se DATE_DIFF(account_due_date, contract_due_date, DAY) > 7 → NÃO renovou (churn)
--   Senão → renovou
--
-- Janelas de 10 dias:
--   PRE-3:  15/abr a 24/abr
--   PRE-2:  25/abr a 04/mai
--   PRE-1:  05/mai a 14/mai
--   POS:    15/mai a 24/mai
-- ============================================================================

WITH base AS (
  SELECT
    ys.contract_id,
    ys.account_id,
    ys.contract_due_date,
    ys.account_due_date,
    ys.plan_months_duration,
    ys.account_contract_number,
    ys.payment_method,

    -- Mesma definição de churn da anl_churn_contratos
    CASE
      WHEN DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) > 7 THEN 'S'
      ELSE 'N'
    END AS churn_sn,

    -- Janelas
    CASE
      WHEN ys.contract_due_date BETWEEN '2026-04-15' AND '2026-04-24' THEN '1_PRE-3 (15-24/abr)'
      WHEN ys.contract_due_date BETWEEN '2026-04-25' AND '2026-05-04' THEN '2_PRE-2 (25/abr-04/mai)'
      WHEN ys.contract_due_date BETWEEN '2026-05-05' AND '2026-05-14' THEN '3_PRE-1 (05-14/mai)'
      WHEN ys.contract_due_date BETWEEN '2026-05-15' AND '2026-05-24' THEN '4_POS (15-24/mai)'
    END AS janela,

    CASE
      WHEN ys.contract_due_date < '2026-05-15' THEN 'PRE'
      ELSE 'POS'
    END AS periodo

  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.contract_due_date BETWEEN '2026-04-15' AND '2026-05-24'
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
  -- 1 linha por contrato (pegar o holder, contrato mais recente)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id
    ORDER BY ys.contract_due_date DESC
  ) = 1
)

SELECT
  janela,
  periodo,
  COUNT(*) AS total_contratos,
  SUM(CASE WHEN churn_sn = 'N' THEN 1 ELSE 0 END) AS renovaram,
  SUM(CASE WHEN churn_sn = 'S' THEN 1 ELSE 0 END) AS nao_renovaram,
  ROUND(100.0 * SUM(CASE WHEN churn_sn = 'N' THEN 1 ELSE 0 END) / COUNT(*), 2) AS taxa_renovacao,
  ROUND(100.0 * SUM(CASE WHEN churn_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 2) AS churn_rate
FROM base
WHERE janela IS NOT NULL
GROUP BY 1, 2
ORDER BY janela;


-- ============================================================================
-- STEP 2: DETALHADO — quebra por duração e ciclo
-- Arquivo: results/impacto_adquirente_detalhe.csv
-- ============================================================================

WITH base AS (
  SELECT
    ys.contract_id,
    ys.contract_due_date,
    ys.account_due_date,
    ys.plan_months_duration,
    CASE WHEN ys.account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo,

    CASE
      WHEN DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) > 7 THEN 'S'
      ELSE 'N'
    END AS churn_sn,

    CASE
      WHEN ys.contract_due_date BETWEEN '2026-04-15' AND '2026-04-24' THEN '1_PRE-3 (15-24/abr)'
      WHEN ys.contract_due_date BETWEEN '2026-04-25' AND '2026-05-04' THEN '2_PRE-2 (25/abr-04/mai)'
      WHEN ys.contract_due_date BETWEEN '2026-05-05' AND '2026-05-14' THEN '3_PRE-1 (05-14/mai)'
      WHEN ys.contract_due_date BETWEEN '2026-05-15' AND '2026-05-24' THEN '4_POS (15-24/mai)'
    END AS janela

  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.contract_due_date BETWEEN '2026-04-15' AND '2026-05-24'
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id
    ORDER BY ys.contract_due_date DESC
  ) = 1
)

SELECT
  janela,
  CAST(plan_months_duration AS STRING) AS duracao,
  ciclo,
  COUNT(*) AS total_contratos,
  SUM(CASE WHEN churn_sn = 'N' THEN 1 ELSE 0 END) AS renovaram,
  SUM(CASE WHEN churn_sn = 'S' THEN 1 ELSE 0 END) AS nao_renovaram,
  ROUND(100.0 * SUM(CASE WHEN churn_sn = 'N' THEN 1 ELSE 0 END) / COUNT(*), 2) AS taxa_renovacao,
  ROUND(100.0 * SUM(CASE WHEN churn_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 2) AS churn_rate
FROM base
WHERE janela IS NOT NULL
GROUP BY 1, 2, 3
ORDER BY janela, duracao, ciclo;


-- ============================================================================
-- STEP 3: DIA A DIA — curva diária pra ver o "antes e depois" com precisão
-- Arquivo: results/impacto_adquirente_diario.csv
-- ============================================================================

WITH base AS (
  SELECT
    ys.contract_id,
    ys.contract_due_date,
    ys.account_due_date,

    CASE
      WHEN DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) > 7 THEN 'S'
      ELSE 'N'
    END AS churn_sn

  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.contract_due_date BETWEEN '2026-04-15' AND '2026-05-25'
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id
    ORDER BY ys.contract_due_date DESC
  ) = 1
)

SELECT
  contract_due_date AS dia,
  CASE WHEN contract_due_date >= '2026-05-15' THEN 'POS' ELSE 'PRE' END AS periodo,
  COUNT(*) AS total_contratos,
  SUM(CASE WHEN churn_sn = 'N' THEN 1 ELSE 0 END) AS renovaram,
  SUM(CASE WHEN churn_sn = 'S' THEN 1 ELSE 0 END) AS nao_renovaram,
  ROUND(100.0 * SUM(CASE WHEN churn_sn = 'N' THEN 1 ELSE 0 END) / COUNT(*), 2) AS taxa_renovacao
FROM base
GROUP BY 1, 2
ORDER BY 1;
