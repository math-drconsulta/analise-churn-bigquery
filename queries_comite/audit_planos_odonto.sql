-- ============================================================================
-- AUDIT: SPLIT DE CHURNERS POR PRESENÇA DE ODONTO NO PLANO
-- Base: anl_churn_contratos (recorte do comitê) + ref_yalo_subscriptions (plan_name)
-- Filtro: planos 6+12m + credit_card + sem B2B + últimos 12 meses
--
-- 2 blocos:
--   A) Distribuição de plan_names (top 30) — pra confirmar o pattern de odonto
--   B) Split do recorte por tem_odonto × duração — % de contratos, churners e churn_rate
-- ============================================================================


-- ============================================================================
-- BLOCO A: TOP 30 plan_names no recorte (para validar a heurística de odonto)
-- ============================================================================

WITH base AS (
  SELECT
    c.contract_id,
    c.churn_renovacao_automatica_sn,
    c.plan_months_duration
  FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` c
  WHERE c.plan_months_duration IN (6, 12)
    AND c.order_payment_method = 'credit_card'
    AND IFNULL(c.order_source_aj, '') != 'b2b'
    AND c.contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
),

sub AS (
  SELECT
    ys.contract_id,
    ANY_VALUE(ys.plan_name) AS plan_name
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
  GROUP BY ys.contract_id
)

SELECT
  s.plan_name,
  CAST(b.plan_months_duration AS STRING) AS duracao,
  COUNT(*) AS total_contratos,
  SUM(CASE WHEN b.churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  ROUND(100.0 * SUM(CASE WHEN b.churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_rate
FROM base b
LEFT JOIN sub s ON s.contract_id = b.contract_id
GROUP BY 1, 2
ORDER BY total_contratos DESC
LIMIT 30;


-- ============================================================================
-- BLOCO B: SPLIT POR PRESENÇA DE ODONTO × DURAÇÃO
-- Heurística: LOWER(plan_name) LIKE '%odonto%'
-- Se o Bloco A mostrar outro pattern (ex: 'odo', 'dental'), ajustar abaixo.
-- ============================================================================

WITH base AS (
  SELECT
    c.contract_id,
    c.churn_renovacao_automatica_sn,
    c.plan_months_duration
  FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` c
  WHERE c.plan_months_duration IN (6, 12)
    AND c.order_payment_method = 'credit_card'
    AND IFNULL(c.order_source_aj, '') != 'b2b'
    AND c.contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
),

sub AS (
  SELECT
    ys.contract_id,
    ANY_VALUE(ys.plan_name) AS plan_name
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
  GROUP BY ys.contract_id
),

joined AS (
  SELECT
    CAST(b.plan_months_duration AS STRING) AS duracao,
    CASE
      WHEN LOWER(IFNULL(s.plan_name, '')) LIKE '%odonto%' THEN 'com_odonto'
      ELSE 'sem_odonto'
    END AS tem_odonto,
    b.churn_renovacao_automatica_sn
  FROM base b
  LEFT JOIN sub s ON s.contract_id = b.contract_id
)

SELECT
  duracao,
  tem_odonto,

  COUNT(*) AS total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) AS churners,

  -- Churn rate da combinação
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_rate,

  -- % de contratos da duração que tem essa flag (composição da base)
  ROUND(100.0 * COUNT(*) /
    SUM(COUNT(*)) OVER (PARTITION BY duracao), 1) AS pct_contratos_da_duracao,

  -- % de CHURNERS da duração que vieram dessa flag (resposta à pergunta principal)
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) /
    SUM(SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END)) OVER (PARTITION BY duracao), 1) AS pct_churners_da_duracao,

  -- % de contratos do total (incluindo ambas durações)
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_contratos_total,

  -- % de churners do total
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) /
    SUM(SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END)) OVER (), 1) AS pct_churners_total

FROM joined
GROUP BY 1, 2
ORDER BY 1, 2;
