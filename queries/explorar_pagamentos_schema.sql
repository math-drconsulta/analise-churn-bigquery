-- ============================================================================
-- EXPLORAR SCHEMA PAGAMENTOS
--
-- Objetivo: descobrir a estrutura e conteudo das tabelas do schema PAGAMENTOS
-- pra avaliar se complementam/substituem os dados de Adyen e Mundipagg.
--
-- Rode cada BLOCO separadamente. Saidas sugeridas em results/:
--   BLOCO 1 → results/explorar_pgto_transacoes_cols.csv
--   BLOCO 2 → results/explorar_pgto_transacoes_tipos_cols.csv
--   BLOCO 3 → results/explorar_pgto_transacoes_status_cols.csv
--   BLOCO 4 → results/explorar_pgto_transacoes_amostra.csv
--   BLOCO 5 → results/explorar_pgto_transacoes_tipos_amostra.csv
--   BLOCO 6 → results/explorar_pgto_transacoes_status_amostra.csv
--   BLOCO 7 → results/explorar_pgto_transacoes_volume.csv
-- ============================================================================


-- ============================================================================
-- BLOCO 1: Colunas da tabela transacoes
-- ============================================================================
SELECT column_name, data_type, is_nullable
FROM `airflow-datalake-prod.PAGAMENTOS`.INFORMATION_SCHEMA.COLUMNS
WHERE table_name = 'transacoes'
ORDER BY ordinal_position;


-- ============================================================================
-- BLOCO 2: Colunas da tabela transacoes_tipos
-- ============================================================================
SELECT column_name, data_type, is_nullable
FROM `airflow-datalake-prod.PAGAMENTOS`.INFORMATION_SCHEMA.COLUMNS
WHERE table_name = 'transacoes_tipos'
ORDER BY ordinal_position;


-- ============================================================================
-- BLOCO 3: Colunas da tabela transacoes_status
-- ============================================================================
SELECT column_name, data_type, is_nullable
FROM `airflow-datalake-prod.PAGAMENTOS`.INFORMATION_SCHEMA.COLUMNS
WHERE table_name = 'transacoes_status'
ORDER BY ordinal_position;


-- ============================================================================
-- BLOCO 4: Amostra de transacoes (20 linhas)
-- ============================================================================
SELECT *
FROM `airflow-datalake-prod.PAGAMENTOS.transacoes`
LIMIT 20;


-- ============================================================================
-- BLOCO 5: Todos os tipos de transacao
-- ============================================================================
SELECT *
FROM `airflow-datalake-prod.PAGAMENTOS.transacoes_tipos`
ORDER BY 1;


-- ============================================================================
-- BLOCO 6: Todos os status de transacao
-- ============================================================================
SELECT *
FROM `airflow-datalake-prod.PAGAMENTOS.transacoes_status`
ORDER BY 1;


-- ============================================================================
-- BLOCO 7: Volume total e contagem de valores distintos por coluna-chave
-- (rode apos o BLOCO 1 pra saber quais colunas existem)
-- ============================================================================
SELECT
  COUNT(*) AS total_linhas
FROM `airflow-datalake-prod.PAGAMENTOS.transacoes`;
