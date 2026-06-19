-- ============================================================================
-- PERFIL DE QUEM VOLTA EM 30 DIAS
-- Arquivo: results/winback_30d_perfil.csv
--
-- Para cada contrato que churnou e voltou em até 30 dias, traz:
--   - Dados do contrato que churnou (ciclo, duracao, canal)
--   - Dados do contrato de RETORNO (tipo_venda, duracao, canal)
--   - Dias ate voltar
--   - Se mudou de plano, canal ou duracao
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
    ys.plan_name,
    ys.days_diff_until_next_contract,
    IFNULL(ys.order_source_aj, 'outros') AS canal,
    ys.flag_unsubscription,

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
    AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 36 MONTH)
    AND ys.contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),

-- Churners que voltaram em até 30 dias
churners_30d AS (
  SELECT *
  FROM contratos
  WHERE churn_sn = 'S'
    AND days_diff_until_next_contract > 0
    AND days_diff_until_next_contract <= 30
),

-- Próximo contrato (o de retorno)
proximo_contrato AS (
  SELECT
    ys.account_id,
    ys.contract_id AS contract_id_retorno,
    ys.contract_register_date AS retorno_register_date,
    ys.plan_months_duration AS retorno_duracao,
    ys.contract_sale_type AS retorno_tipo_venda,
    ys.plan_name AS retorno_plan_name,
    IFNULL(ys.order_source_aj, 'outros') AS retorno_canal,
    ys.account_contract_number AS retorno_contract_number
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
)

SELECT
  c.contract_id,
  c.account_id,
  c.contract_due_date,
  CAST(c.plan_months_duration AS STRING) AS duracao_original,
  CASE WHEN c.account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo_original,
  IFNULL(c.contract_sale_type, 'desconhecido') AS tipo_venda_original,
  c.canal AS canal_original,
  c.flag_unsubscription AS pediu_cancelamento,
  c.days_diff_until_next_contract AS dias_ate_retorno,

  -- Contrato de retorno
  pc.contract_id_retorno,
  pc.retorno_register_date,
  CAST(pc.retorno_duracao AS STRING) AS duracao_retorno,
  IFNULL(pc.retorno_tipo_venda, 'desconhecido') AS tipo_venda_retorno,
  pc.retorno_canal AS canal_retorno,

  -- Mudou algo?
  CASE WHEN c.plan_months_duration != pc.retorno_duracao THEN 'mudou' ELSE 'manteve' END AS mudou_duracao,
  CASE WHEN c.canal != pc.retorno_canal THEN 'mudou' ELSE 'manteve' END AS mudou_canal,

  -- Classificacao do retorno
  CASE
    WHEN c.days_diff_until_next_contract <= 7 THEN 'retorno_imediato_0-7d'
    WHEN c.days_diff_until_next_contract <= 14 THEN 'retorno_rapido_8-14d'
    WHEN c.days_diff_until_next_contract <= 21 THEN 'retorno_medio_15-21d'
    ELSE 'retorno_tardio_22-30d'
  END AS faixa_retorno_detalhe

FROM churners_30d c
-- Pegar o próximo contrato do mesmo account
LEFT JOIN proximo_contrato pc
  ON pc.account_id = c.account_id
  AND pc.retorno_register_date > c.contract_due_date
  AND pc.retorno_register_date <= DATE_ADD(c.contract_due_date, INTERVAL 30 DAY)
-- Se tiver mais de um proximo, pegar o mais proximo
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY c.contract_id
  ORDER BY pc.retorno_register_date ASC
) = 1

ORDER BY c.days_diff_until_next_contract;
