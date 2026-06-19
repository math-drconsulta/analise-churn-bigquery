-- Explorar: existe tabela de dimensao de unidade?
-- Tentar encontrar a traducao id_unidade → sigla

-- Opcao 1: tabela de dimensao no DATA_LAKE_GOLD
SELECT *
FROM `airflow-datalake-prod.DATA_LAKE_GOLD.dim_unidade`
LIMIT 10;

-- Opcao 2: se nao existir, extrair da bi_recepcao_itens
-- SELECT DISTINCT id_item, unidade
-- FROM `airflow-datalake-prod.DRC_DW.bi_recepcao_itens`
-- WHERE data >= '2026-01-01'
-- LIMIT 20;
