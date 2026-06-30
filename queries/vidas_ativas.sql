-- ============================================================================
-- VIDAS ATIVAS NA BASE YALO
--
-- Rode cada BLOCO separadamente. Saidas sugeridas:
--   BLOCO 1 → results/vidas_resumo.csv
--   BLOCO 2 → results/vidas_por_plano.csv
--   BLOCO 3 → results/vidas_por_metodo_pgto.csv
-- ============================================================================


-- ============================================================================
-- BLOCO 1: Resumo — titulares vs dependentes (contratos ativos hoje)
-- ============================================================================
WITH snapshot AS (
  SELECT *
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions`
  WHERE CAST(account_due_date AS DATE) >= CURRENT_DATE()
    AND CAST(contract_register_date AS DATE) <= CURRENT_DATE()
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY contract_id ORDER BY date_month DESC
  ) = 1
)
SELECT
  account_type,
  COUNT(DISTINCT contract_id) AS contratos,
  COUNT(DISTINCT person_id) AS pessoas,
  COUNT(DISTINCT account_id) AS accounts
FROM snapshot
GROUP BY account_type
ORDER BY account_type;


-- ============================================================================
-- BLOCO 2: Por tipo de plano (nome, duracao, gratis vs pago)
-- ============================================================================
WITH snapshot AS (
  SELECT *
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions`
  WHERE CAST(account_due_date AS DATE) >= CURRENT_DATE()
    AND CAST(contract_register_date AS DATE) <= CURRENT_DATE()
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY contract_id ORDER BY date_month DESC
  ) = 1
)
SELECT
  account_type,
  plan_name,
  plan_months_duration,
  CASE WHEN LOWER(plan_name) LIKE '%gratis%' THEN 'gratis' ELSE 'pago' END AS tipo_plano,
  payment_method,
  COUNT(DISTINCT contract_id) AS contratos,
  COUNT(DISTINCT person_id) AS pessoas
FROM snapshot
GROUP BY 1, 2, 3, 4, 5
ORDER BY pessoas DESC;


-- ============================================================================
-- BLOCO 3: Resumo agregado — pago vs gratis, titular vs dependente
-- ============================================================================
WITH snapshot AS (
  SELECT *
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions`
  WHERE CAST(account_due_date AS DATE) >= CURRENT_DATE()
    AND CAST(contract_register_date AS DATE) <= CURRENT_DATE()
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY contract_id ORDER BY date_month DESC
  ) = 1
)
SELECT
  account_type,
  CASE WHEN LOWER(plan_name) LIKE '%gratis%' THEN 'gratis' ELSE 'pago' END AS tipo_plano,
  payment_method,
  COUNT(DISTINCT contract_id) AS contratos,
  COUNT(DISTINCT person_id) AS pessoas,
  COUNT(DISTINCT account_id) AS accounts
FROM snapshot
GROUP BY 1, 2, 3
ORDER BY pessoas DESC;
