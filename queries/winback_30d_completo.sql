-- ============================================================================
-- WIN-BACK 30 DIAS — PERFIL COMPLETO + CONSISTENCIA MENSAL
--
-- 2 outputs:
--   STEP 1: Perfil do retorno (contrato que churnou × contrato de volta)
--           → results/winback_30d_completo.csv
--   STEP 2: Consistencia mensal (taxa de retorno 30d por mes de vencimento)
--           → results/winback_30d_mensal.csv
-- ============================================================================


-- ============================================================================
-- STEP 1: PERFIL COMPLETO
-- Estrategia: ordenar todos os contratos de cada account_id por data
-- e pegar o PROXIMO contrato depois do que churnou.
-- ============================================================================

WITH todos_contratos AS (
  -- Todos os contratos (sem filtro de churn), pra encontrar o "proximo"
  SELECT
    ys.account_id,
    ys.contract_id,
    ys.contract_register_date,
    ys.contract_due_date,
    ys.account_due_date,
    ys.plan_months_duration,
    ys.account_contract_number,
    ys.contract_sale_type,
    ys.plan_name,
    ys.payment_method,
    IFNULL(ys.order_source_aj, 'outros') AS canal,
    ys.flag_unsubscription,
    ys.days_diff_until_next_contract,

    CASE
      WHEN DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) > 7 THEN 'N'
      ELSE 'S'
    END AS churn_sn,

    -- Proximo contrato do mesmo account (por data de registro)
    LEAD(ys.contract_id) OVER (
      PARTITION BY ys.account_id ORDER BY ys.contract_register_date, ys.contract_id
    ) AS next_contract_id,
    LEAD(ys.contract_register_date) OVER (
      PARTITION BY ys.account_id ORDER BY ys.contract_register_date, ys.contract_id
    ) AS next_register_date,
    LEAD(ys.contract_due_date) OVER (
      PARTITION BY ys.account_id ORDER BY ys.contract_register_date, ys.contract_id
    ) AS next_due_date,
    LEAD(ys.plan_months_duration) OVER (
      PARTITION BY ys.account_id ORDER BY ys.contract_register_date, ys.contract_id
    ) AS next_duracao,
    LEAD(ys.contract_sale_type) OVER (
      PARTITION BY ys.account_id ORDER BY ys.contract_register_date, ys.contract_id
    ) AS next_tipo_venda,
    LEAD(ys.plan_name) OVER (
      PARTITION BY ys.account_id ORDER BY ys.contract_register_date, ys.contract_id
    ) AS next_plan_name,
    LEAD(IFNULL(ys.order_source_aj, 'outros')) OVER (
      PARTITION BY ys.account_id ORDER BY ys.contract_register_date, ys.contract_id
    ) AS next_canal

  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 36 MONTH)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),

-- Filtrar: churners que voltaram em ate 30 dias
churners_30d AS (
  SELECT *
  FROM todos_contratos
  WHERE churn_sn = 'S'
    AND next_contract_id IS NOT NULL
    AND DATE_DIFF(next_register_date, contract_due_date, DAY) BETWEEN 0 AND 30
    AND contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
)

SELECT
  contract_id,
  account_id,
  contract_due_date,

  -- Contrato que churnou
  CAST(plan_months_duration AS STRING) AS duracao_original,
  CASE WHEN account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo_original,
  IFNULL(contract_sale_type, 'desconhecido') AS tipo_venda_original,
  canal AS canal_original,
  plan_name AS plano_original,
  flag_unsubscription AS pediu_cancelamento,

  -- Contrato de retorno
  next_contract_id AS contrato_retorno_id,
  next_register_date AS retorno_data,
  DATE_DIFF(next_register_date, contract_due_date, DAY) AS dias_ate_retorno,
  CAST(next_duracao AS STRING) AS duracao_retorno,
  IFNULL(next_tipo_venda, 'desconhecido') AS tipo_venda_retorno,
  next_canal AS canal_retorno,
  next_plan_name AS plano_retorno,

  -- Mudou?
  CASE WHEN plan_months_duration != next_duracao THEN 'mudou' ELSE 'manteve' END AS mudou_duracao,
  CASE WHEN canal != next_canal THEN 'mudou' ELSE 'manteve' END AS mudou_canal,
  CASE WHEN plan_name != next_plan_name THEN 'mudou' ELSE 'manteve' END AS mudou_plano,

  -- Faixa detalhe
  CASE
    WHEN DATE_DIFF(next_register_date, contract_due_date, DAY) <= 7 THEN '0-7d'
    WHEN DATE_DIFF(next_register_date, contract_due_date, DAY) <= 14 THEN '8-14d'
    WHEN DATE_DIFF(next_register_date, contract_due_date, DAY) <= 21 THEN '15-21d'
    ELSE '22-30d'
  END AS faixa_retorno

FROM churners_30d
ORDER BY contract_due_date DESC;


-- ============================================================================
-- STEP 2: CONSISTENCIA MENSAL
-- O padrao de ~30% se repete mes a mes?
-- ============================================================================

WITH todos_contratos AS (
  SELECT
    ys.account_id,
    ys.contract_id,
    ys.contract_register_date,
    ys.contract_due_date,
    ys.account_due_date,
    ys.plan_months_duration,
    ys.account_contract_number,
    ys.days_diff_until_next_contract,

    CASE
      WHEN DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) > 7 THEN 'N'
      ELSE 'S'
    END AS churn_sn,

    DATE_TRUNC(ys.contract_due_date, MONTH) AS mes_vencimento

  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    -- 2 anos + margem de 30d pra retorno
    AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 MONTH)
    AND ys.contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
)

SELECT
  mes_vencimento,
  COUNT(*) AS total_contratos,

  -- Churn original
  COUNTIF(churn_sn = 'S') AS churners,
  ROUND(100.0 * COUNTIF(churn_sn = 'S') / COUNT(*), 1) AS churn_rate,

  -- Dos churners, quantos voltaram em 30d
  COUNTIF(churn_sn = 'S' AND days_diff_until_next_contract > 0 AND days_diff_until_next_contract <= 30) AS voltaram_30d,

  -- Taxa de retorno 30d (sobre churners)
  ROUND(100.0 *
    COUNTIF(churn_sn = 'S' AND days_diff_until_next_contract > 0 AND days_diff_until_next_contract <= 30) /
    NULLIF(COUNTIF(churn_sn = 'S'), 0),
  1) AS pct_retorno_30d,

  -- Churn "real" (excluindo retorno 30d)
  COUNTIF(churn_sn = 'S') -
    COUNTIF(churn_sn = 'S' AND days_diff_until_next_contract > 0 AND days_diff_until_next_contract <= 30) AS churn_real,

  ROUND(100.0 * (
    COUNTIF(churn_sn = 'S') -
    COUNTIF(churn_sn = 'S' AND days_diff_until_next_contract > 0 AND days_diff_until_next_contract <= 30)
  ) / COUNT(*), 1) AS churn_real_rate

FROM todos_contratos
GROUP BY 1
ORDER BY 1;
