-- ============================================================================
-- WIN-BACK 30D — PERFIL DO RETORNO v2
-- Arquivo: results/winback_30d_completo.csv
--
-- Filtros relaxados no PRÓXIMO contrato:
--   - Removido: payment_method = 'credit_card'
--   - Removido: plan_months_duration IN (6, 12)
--   - Mantido: plan_name NOT LIKE '%gratis%' (exclui trials)
--   - Mantido: order_source_aj != 'b2b' (exclui corporativo)
--
-- Usa LEAD() pra pegar o próximo contrato do mesmo account_id
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
    ys.contract_sale_type,
    ys.plan_name,
    ys.payment_method,
    IFNULL(ys.order_source_aj, 'outros') AS canal,
    ys.flag_unsubscription,

    CASE
      WHEN DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) > 7 THEN 'N'
      ELSE 'S'
    END AS churn_sn

  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    -- Filtros do contrato base (restritivo)
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 36 MONTH)
    AND ys.contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),

-- Todos os contratos possiveis de retorno (filtros relaxados)
todos_retorno AS (
  SELECT
    ys.account_id,
    ys.contract_id,
    ys.contract_register_date,
    ys.plan_months_duration,
    ys.contract_sale_type,
    ys.plan_name,
    ys.payment_method,
    IFNULL(ys.order_source_aj, 'outros') AS canal
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    -- Filtros relaxados: só exclui gratis e B2B
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.contract_register_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 36 MONTH)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),

-- Churners com proximo contrato em ate 30 dias
churners_com_retorno AS (
  SELECT
    tc.*,
    tr.contract_id AS retorno_contract_id,
    tr.contract_register_date AS retorno_register_date,
    tr.plan_months_duration AS retorno_duracao,
    tr.contract_sale_type AS retorno_tipo_venda,
    tr.plan_name AS retorno_plan_name,
    tr.payment_method AS retorno_payment_method,
    tr.canal AS retorno_canal,
    DATE_DIFF(tr.contract_register_date, tc.contract_due_date, DAY) AS dias_ate_retorno
  FROM todos_contratos tc
  INNER JOIN todos_retorno tr
    ON tr.account_id = tc.account_id
    AND tr.contract_register_date > tc.contract_due_date
    AND tr.contract_register_date <= DATE_ADD(tc.contract_due_date, INTERVAL 30 DAY)
    AND tr.contract_id != tc.contract_id
  WHERE tc.churn_sn = 'S'
  -- Se mais de um retorno, pegar o mais proximo
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY tc.contract_id ORDER BY tr.contract_register_date ASC
  ) = 1
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
  retorno_contract_id,
  retorno_register_date,
  dias_ate_retorno,
  CAST(retorno_duracao AS STRING) AS duracao_retorno,
  IFNULL(retorno_tipo_venda, 'desconhecido') AS tipo_venda_retorno,
  retorno_plan_name AS plano_retorno,
  retorno_payment_method AS pagamento_retorno,
  retorno_canal AS canal_retorno,

  -- Mudou?
  CASE WHEN plan_months_duration != retorno_duracao THEN 'mudou' ELSE 'manteve' END AS mudou_duracao,
  CASE WHEN canal != retorno_canal THEN 'mudou' ELSE 'manteve' END AS mudou_canal,
  CASE WHEN payment_method != retorno_payment_method THEN 'mudou' ELSE 'manteve' END AS mudou_pagamento,
  CASE WHEN plan_name != retorno_plan_name THEN 'mudou' ELSE 'manteve' END AS mudou_plano,

  -- Faixa
  CASE
    WHEN dias_ate_retorno <= 7 THEN '0-7d'
    WHEN dias_ate_retorno <= 14 THEN '8-14d'
    WHEN dias_ate_retorno <= 21 THEN '15-21d'
    ELSE '22-30d'
  END AS faixa_retorno

FROM churners_com_retorno
ORDER BY dias_ate_retorno;
