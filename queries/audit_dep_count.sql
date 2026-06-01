-- ============================================================================
-- AUDIT: dep_count_anl vs qtd_dep_total — diagnóstico do leakage
--
-- Contexto: experimento de lift no núcleo (scripts/lift_nucleo.py) descobriu
-- que ~5% dos contratos têm dep_count_anl > qtd_dep_total → churn de 0,2%
-- (vs 58% no resto da base). Suspeita de leakage de target.
--
-- Esta query roda 4 blocos. Saída sugerida:
--   1A → results/audit_dep_count_panorama.csv
--   1B → results/audit_dep_count_schema_subscr.csv
--   1C → results/audit_dep_count_schema_anl.csv
--   1D → results/audit_dep_count_temporal.csv
--   1E → results/audit_dep_count_samples_raw.csv
-- ============================================================================


-- ----------------------------------------------------------------------------
-- 1A) PANORAMA: distribuição da divergência × churn
-- Pergunta: pra cada combinação (dep_anl, dep_sub), quantos contratos e qual
--           o churn? Se hipótese do leakage está certa, dep_anl > dep_sub
--           tem que aparecer com churn ~0%.
-- ----------------------------------------------------------------------------
WITH dep_sub AS (
  SELECT contract_id, COUNT(DISTINCT person_id) AS qtd_dep_total
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions`
  WHERE account_type != 'holder'
  GROUP BY 1
)
SELECT
  c.dependents_per_holder                AS dep_anl,
  IFNULL(d.qtd_dep_total, 0)             AS dep_sub,
  c.dependents_per_holder - IFNULL(d.qtd_dep_total, 0) AS diff,
  COUNT(*)                               AS n_contratos,
  ROUND(100.0 * SUM(CASE WHEN c.churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 2) AS churn_pct
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` c
LEFT JOIN dep_sub d ON d.contract_id = c.contract_id
WHERE c.plan_months_duration IN (6, 12)
  AND c.order_payment_method = 'credit_card'
  AND IFNULL(c.order_source_aj, '') != 'b2b'
  AND c.contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3
ORDER BY n_contratos DESC
LIMIT 100;


-- ----------------------------------------------------------------------------
-- 1B) SCHEMA SCAN — ref_yalo_subscriptions
-- Pergunta: a tabela tem alguma coluna de status/cancelamento do dep? (ex:
--           subscription_active, cancelled_at, end_date, churn_flag) Se tiver,
--           explica por que deps "somem" do count quando o contrato é renovado.
-- ----------------------------------------------------------------------------
SELECT column_name, data_type, is_nullable
FROM `airflow-datalake-prod.YALO_DW.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name = 'ref_yalo_subscriptions'
ORDER BY ordinal_position;


-- ----------------------------------------------------------------------------
-- 1C) SCHEMA SCAN — anl_churn_contratos
-- Pergunta: dependents_per_holder vem de quê? Snapshot original ou recálculo?
-- ----------------------------------------------------------------------------
SELECT column_name, data_type, is_nullable
FROM `airflow-datalake-prod.YALO_DW.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name = 'anl_churn_contratos'
ORDER BY ordinal_position;


-- ----------------------------------------------------------------------------
-- 1D) DISTRIBUIÇÃO TEMPORAL DA DIVERGÊNCIA
-- Pergunta: divergência se concentra em algum due_date_month específico?
--           algum source? Se sim, sugere bug de pipeline em data específica.
--           Se distribuído homogeneamente: comportamental (mudança de plano).
-- ----------------------------------------------------------------------------
WITH dep_sub AS (
  SELECT contract_id, COUNT(DISTINCT person_id) AS qtd_dep_total
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions`
  WHERE account_type != 'holder'
  GROUP BY 1
)
SELECT
  c.contract_due_date_month,
  IFNULL(c.order_source_aj, '(null)') AS source,
  CASE
    WHEN c.dependents_per_holder = IFNULL(d.qtd_dep_total, 0) THEN '00_iguais'
    WHEN c.dependents_per_holder > IFNULL(d.qtd_dep_total, 0) THEN '01_yalo_maior'
    ELSE '02_yalo_menor'
  END AS classe_div,
  COUNT(*) AS n,
  ROUND(100.0 * SUM(CASE WHEN c.churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 2) AS churn_pct
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` c
LEFT JOIN dep_sub d ON d.contract_id = c.contract_id
WHERE c.plan_months_duration IN (6, 12)
  AND c.order_payment_method = 'credit_card'
  AND IFNULL(c.order_source_aj, '') != 'b2b'
  AND c.contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;


-- ----------------------------------------------------------------------------
-- 1E) SAMPLES RAW — 5 contratos divergentes com TODAS suas subscriptions
-- Pergunta: olhando linha por linha, o que distingue os deps que "somem"?
--           tem múltiplos payment_id no mesmo contract? account_register_date
--           muito antigo? account_type estranho?
-- ----------------------------------------------------------------------------
WITH dep_sub AS (
  SELECT contract_id, COUNT(DISTINCT person_id) AS qtd_dep_total
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions`
  WHERE account_type != 'holder'
  GROUP BY 1
),
contratos_alvo AS (
  SELECT c.contract_id
  FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` c
  LEFT JOIN dep_sub d ON d.contract_id = c.contract_id
  WHERE c.plan_months_duration IN (6, 12)
    AND c.order_payment_method = 'credit_card'
    AND IFNULL(c.order_source_aj, '') != 'b2b'
    AND c.contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
    AND c.dependents_per_holder >= IFNULL(d.qtd_dep_total, 0) + 2  -- diferença robusta
  ORDER BY RAND()
  LIMIT 5
)
SELECT s.*
FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` s
WHERE s.contract_id IN (SELECT contract_id FROM contratos_alvo)
ORDER BY s.contract_id, s.payment_id, s.account_type, s.person_id;
