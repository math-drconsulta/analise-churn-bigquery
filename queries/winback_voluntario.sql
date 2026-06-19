-- ============================================================================
-- WIN-BACK VOLUNTÁRIO: quem churna e volta?
--
-- Faixas de retorno:
--   Até 30 dias | 31-60 | 61-90 | 91-180 (6m) | 181-365 (1 ano) | 366-730 (2 anos)
--
-- Para capturar retornos de até 2 anos, precisamos de contratos que
-- venceram há pelo menos 2 anos (pra ter janela completa).
--
-- 2 outputs:
--   STEP 1: Por contrato (detalhado) → results/winback_voluntario.csv
--   STEP 2: Resumo agregado → results/winback_resumo.csv
-- ============================================================================


-- ============================================================================
-- STEP 1: DETALHADO (1 linha por contrato que churnou)
-- ============================================================================

WITH contratos AS (
  SELECT
    ys.account_id,
    ys.contract_id,
    ys.contract_register_date,
    ys.contract_due_date,
    ys.plan_months_duration,
    ys.account_contract_number,
    ys.contract_sale_type,
    ys.days_diff_until_next_contract,
    IFNULL(ys.order_source_aj, 'outros') AS canal,

    -- Churn (definicao correta)
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
    -- 3 anos de historia pra capturar retornos de ate 2 anos
    AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 36 MONTH)
    -- Excluir ultimos 30 dias (churn nao processado)
    AND ys.contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id
    ORDER BY ys.date_month DESC
  ) = 1
)

SELECT
  contract_id,
  account_id,
  contract_register_date,
  contract_due_date,
  CAST(plan_months_duration AS STRING) AS duracao,
  CASE WHEN account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo,
  IFNULL(contract_sale_type, 'desconhecido') AS tipo_venda,
  canal,
  days_diff_until_next_contract,

  -- Voltou?
  CASE
    WHEN days_diff_until_next_contract > 0 AND days_diff_until_next_contract <= 730
    THEN 'voltou'
    ELSE 'nao_voltou'
  END AS retorno_status,

  -- Faixa de retorno
  CASE
    WHEN days_diff_until_next_contract IS NULL THEN 'nao_voltou'
    WHEN days_diff_until_next_contract <= 0 THEN 'nao_voltou'
    WHEN days_diff_until_next_contract <= 30 THEN '01_ate_30_dias'
    WHEN days_diff_until_next_contract <= 60 THEN '02_31_a_60_dias'
    WHEN days_diff_until_next_contract <= 90 THEN '03_61_a_90_dias'
    WHEN days_diff_until_next_contract <= 180 THEN '04_91_a_180_dias'
    WHEN days_diff_until_next_contract <= 365 THEN '05_181_a_365_dias'
    WHEN days_diff_until_next_contract <= 730 THEN '06_366_a_730_dias'
    ELSE 'nao_voltou'
  END AS faixa_retorno,

  -- Quanto tempo ficou fora (dias)
  CASE
    WHEN days_diff_until_next_contract > 0 AND days_diff_until_next_contract <= 730
    THEN days_diff_until_next_contract
  END AS dias_ate_retorno

FROM contratos
WHERE churn_sn = 'S'
ORDER BY contract_due_date DESC;


-- ============================================================================
-- STEP 2: RESUMO AGREGADO
-- ============================================================================

WITH contratos AS (
  SELECT
    ys.account_id,
    ys.contract_id,
    ys.contract_due_date,
    ys.plan_months_duration,
    ys.account_contract_number,
    ys.contract_sale_type,
    ys.days_diff_until_next_contract,

    CASE
      WHEN DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) > 7 THEN 'N'
      ELSE 'S'
    END AS churn_sn,

    -- Ano de vencimento (pra ver evolucao temporal)
    EXTRACT(YEAR FROM ys.contract_due_date) AS ano_vencimento

  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 36 MONTH)
    AND ys.contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id
    ORDER BY ys.date_month DESC
  ) = 1
),

churners AS (
  SELECT * FROM contratos WHERE churn_sn = 'S'
)

SELECT
  CAST(plan_months_duration AS STRING) AS duracao,
  CASE WHEN account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo,

  COUNT(*) AS total_churners,

  -- Taxa de retorno total (ate 2 anos)
  COUNTIF(days_diff_until_next_contract > 0 AND days_diff_until_next_contract <= 730) AS voltaram_total,
  ROUND(100.0 * COUNTIF(days_diff_until_next_contract > 0 AND days_diff_until_next_contract <= 730) / COUNT(*), 1) AS taxa_retorno_total,

  -- Por faixa de tempo
  COUNTIF(days_diff_until_next_contract > 0 AND days_diff_until_next_contract <= 30) AS ret_ate_30d,
  COUNTIF(days_diff_until_next_contract > 30 AND days_diff_until_next_contract <= 60) AS ret_31_60d,
  COUNTIF(days_diff_until_next_contract > 60 AND days_diff_until_next_contract <= 90) AS ret_61_90d,
  COUNTIF(days_diff_until_next_contract > 90 AND days_diff_until_next_contract <= 180) AS ret_91_180d,
  COUNTIF(days_diff_until_next_contract > 180 AND days_diff_until_next_contract <= 365) AS ret_181_365d,
  COUNTIF(days_diff_until_next_contract > 365 AND days_diff_until_next_contract <= 730) AS ret_366_730d,

  -- Tempo medio de retorno (de quem voltou)
  ROUND(AVG(CASE
    WHEN days_diff_until_next_contract > 0 AND days_diff_until_next_contract <= 730
    THEN days_diff_until_next_contract
  END), 0) AS dias_retorno_medio,

  -- Curva de retorno acumulado
  ROUND(100.0 * COUNTIF(days_diff_until_next_contract > 0 AND days_diff_until_next_contract <= 30) / COUNT(*), 1) AS pct_acum_30d,
  ROUND(100.0 * COUNTIF(days_diff_until_next_contract > 0 AND days_diff_until_next_contract <= 60) / COUNT(*), 1) AS pct_acum_60d,
  ROUND(100.0 * COUNTIF(days_diff_until_next_contract > 0 AND days_diff_until_next_contract <= 90) / COUNT(*), 1) AS pct_acum_90d,
  ROUND(100.0 * COUNTIF(days_diff_until_next_contract > 0 AND days_diff_until_next_contract <= 180) / COUNT(*), 1) AS pct_acum_180d,
  ROUND(100.0 * COUNTIF(days_diff_until_next_contract > 0 AND days_diff_until_next_contract <= 365) / COUNT(*), 1) AS pct_acum_365d,
  ROUND(100.0 * COUNTIF(days_diff_until_next_contract > 0 AND days_diff_until_next_contract <= 730) / COUNT(*), 1) AS pct_acum_730d

FROM churners
GROUP BY 1, 2
ORDER BY 1, 2;
