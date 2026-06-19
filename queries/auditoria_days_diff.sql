-- ============================================================================
-- AUDITORIA: days_diff_until_next_contract
--
-- 3 checks:
--   STEP 1: Recriar a variavel do zero e comparar com o campo original
--   STEP 2: Amostra detalhada de accounts com retorno 15-21 dias
--   STEP 3: Distribuicao geral — o campo faz sentido?
-- ============================================================================


-- ============================================================================
-- STEP 1: RECRIAR DO ZERO E COMPARAR
-- Arquivo: results/auditoria_days_diff_check.csv
--
-- Para cada contrato, calcular manualmente:
--   gap = proximo_contrato.register_date - este_contrato.due_date
-- E comparar com days_diff_until_next_contract
-- ============================================================================

WITH contratos_ordenados AS (
  SELECT
    ys.account_id,
    ys.contract_id,
    ys.contract_register_date,
    ys.contract_due_date,
    ys.account_due_date,
    ys.plan_months_duration,
    ys.account_contract_number,
    ys.days_diff_until_next_contract,
    ys.payment_method,

    -- Proximo contrato do mesmo account (por register_date)
    LEAD(ys.contract_id) OVER (
      PARTITION BY ys.account_id ORDER BY ys.contract_register_date, ys.contract_id
    ) AS next_contract_id,
    LEAD(ys.contract_register_date) OVER (
      PARTITION BY ys.account_id ORDER BY ys.contract_register_date, ys.contract_id
    ) AS next_register_date,
    LEAD(ys.contract_due_date) OVER (
      PARTITION BY ys.account_id ORDER BY ys.contract_register_date, ys.contract_id
    ) AS next_due_date,

    -- Gap calculado manualmente
    DATE_DIFF(
      LEAD(ys.contract_register_date) OVER (
        PARTITION BY ys.account_id ORDER BY ys.contract_register_date, ys.contract_id
      ),
      ys.contract_due_date,
      DAY
    ) AS gap_calculado

  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 12 MONTH)
    AND ys.contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
)

SELECT
  -- Comparacao: campo original vs calculado
  CASE
    WHEN days_diff_until_next_contract IS NULL AND gap_calculado IS NULL THEN 'ambos_null'
    WHEN days_diff_until_next_contract IS NULL AND gap_calculado IS NOT NULL THEN 'original_null_calculado_existe'
    WHEN days_diff_until_next_contract IS NOT NULL AND gap_calculado IS NULL THEN 'original_existe_calculado_null'
    WHEN ABS(days_diff_until_next_contract - gap_calculado) <= 3 THEN 'batem (diff <= 3d)'
    WHEN ABS(days_diff_until_next_contract - gap_calculado) <= 7 THEN 'proximo (diff 4-7d)'
    WHEN ABS(days_diff_until_next_contract - gap_calculado) <= 30 THEN 'diferente (diff 8-30d)'
    ELSE 'muito_diferente (diff > 30d)'
  END AS comparacao,

  COUNT(*) AS contratos,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) AS pct,

  -- Medias
  ROUND(AVG(days_diff_until_next_contract), 1) AS media_original,
  ROUND(AVG(gap_calculado), 1) AS media_calculado

FROM contratos_ordenados
GROUP BY 1
ORDER BY contratos DESC;


-- ============================================================================
-- STEP 2: AMOSTRA DETALHADA (accounts com retorno 15-21 dias)
-- Arquivo: results/auditoria_days_diff_amostra.csv
--
-- 20 accounts onde days_diff = 15-21, mostrando todos os contratos
-- ============================================================================

WITH exemplos AS (
  SELECT DISTINCT account_id
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions`
  WHERE account_type = 'holder'
    AND payment_method = 'credit_card'
    AND plan_months_duration IN (6, 12)
    AND days_diff_until_next_contract BETWEEN 15 AND 21
    AND contract_due_date BETWEEN '2026-01-01' AND '2026-03-31'
    AND date_month = account_due_date_month
  LIMIT 20
)

SELECT
  ys.account_id,
  ys.contract_id,
  ys.contract_register_date,
  ys.contract_due_date,
  ys.account_due_date,
  ys.plan_months_duration,
  ys.account_contract_number,
  ys.contract_sale_type,
  ys.payment_method,
  ys.plan_name,
  ys.days_diff_until_next_contract,
  ys.flag_unsubscription,
  ys.date_month,

  CASE
    WHEN DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) > 7 THEN 'N'
    ELSE 'S'
  END AS churn_sn

FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
WHERE ys.account_id IN (SELECT account_id FROM exemplos)
  AND ys.account_type = 'holder'
ORDER BY ys.account_id, ys.contract_register_date, ys.date_month;


-- ============================================================================
-- STEP 3: DISTRIBUICAO GERAL DO CAMPO
-- Arquivo: results/auditoria_days_diff_dist.csv
-- ============================================================================

WITH contratos AS (
  SELECT
    days_diff_until_next_contract,
    CASE
      WHEN DATE_DIFF(account_due_date, contract_due_date, DAY) > 7 THEN 'N'
      ELSE 'S'
    END AS churn_sn
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions`
  WHERE account_type = 'holder'
    AND payment_method = 'credit_card'
    AND plan_months_duration IN (6, 12)
    AND plan_name NOT LIKE '%gratis%'
    AND IFNULL(order_source_aj, '') != 'b2b'
    AND contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 12 MONTH)
    AND contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  QUALIFY ROW_NUMBER() OVER (PARTITION BY contract_id ORDER BY date_month DESC) = 1
)

SELECT
  CASE
    WHEN days_diff_until_next_contract IS NULL THEN 'NULL'
    WHEN days_diff_until_next_contract <= 0 THEN 'negativo_ou_zero'
    WHEN days_diff_until_next_contract <= 7 THEN '1-7 dias'
    WHEN days_diff_until_next_contract <= 14 THEN '8-14 dias'
    WHEN days_diff_until_next_contract <= 21 THEN '15-21 dias'
    WHEN days_diff_until_next_contract <= 30 THEN '22-30 dias'
    WHEN days_diff_until_next_contract <= 60 THEN '31-60 dias'
    WHEN days_diff_until_next_contract <= 90 THEN '61-90 dias'
    WHEN days_diff_until_next_contract <= 180 THEN '91-180 dias'
    WHEN days_diff_until_next_contract <= 365 THEN '181-365 dias'
    ELSE '365+ dias'
  END AS faixa_days_diff,

  churn_sn,
  COUNT(*) AS contratos

FROM contratos
GROUP BY 1, 2
ORDER BY 1, 2;
