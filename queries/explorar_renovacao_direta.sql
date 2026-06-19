-- ============================================================================
-- EXPLORAR: campos de renovacao em public_account_plans
-- Entender is_recurrent, is_current e outros campos disponiveis
-- ============================================================================


-- 1. COLUNAS DA TABELA
SELECT column_name, data_type
FROM `airflow-datalake-prod.yalo.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name = 'public_account_plans'
ORDER BY ordinal_position;


-- 2. AMOSTRA com foco nos campos de renovacao
-- SELECT
--   account_id,
--   DATE(due_date) AS due_date,
--   DATE(created_at) AS created_at,
--   is_recurrent,
--   status,
--   plan_name
-- FROM `airflow-datalake-prod.yalo.public_account_plans`
-- WHERE DATE(due_date) BETWEEN '2026-05-01' AND '2026-06-11'
-- LIMIT 20;


-- 3. DISTRIBUICAO de is_recurrent pra contratos recentes
-- SELECT
--   is_recurrent,
--   COUNT(*) AS total,
--   MIN(DATE(due_date)) AS min_due,
--   MAX(DATE(due_date)) AS max_due
-- FROM `airflow-datalake-prod.yalo.public_account_plans`
-- WHERE DATE(due_date) BETWEEN '2026-04-24' AND '2026-06-11'
-- GROUP BY 1;
