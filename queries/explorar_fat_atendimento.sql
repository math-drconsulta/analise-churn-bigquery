-- ============================================================================
-- EXPLORAÇÃO 4: Encontrar a ponte entre fat_atendimento e YALO
-- ============================================================================


-- 1. VIA id_recepcao_item → bi_recepcao_itens → ref_yalo_itens → ref_yalo_subscriptions
-- Testar se fat_atendimento.id_recepcao_item = bi_recepcao_itens.id_item
SELECT
  COUNT(*) AS total_fat,
  COUNT(DISTINCT fa.id_recepcao_item) AS recepcao_items_fat,
  COUNT(DISTINCT ri.id_item) AS match_recepcao,
  COUNT(DISTINCT yi.payment_id) AS match_yalo_itens,
  COUNT(DISTINCT ys.contract_id) AS match_contratos
FROM `airflow-datalake-prod.DATA_LAKE_GOLD.fat_atendimento` fa
LEFT JOIN `airflow-datalake-prod.DRC_DW.bi_recepcao_itens` ri
  ON ri.id_item = fa.id_recepcao_item
LEFT JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_itens` yi
  ON yi.id_item = ri.id_item
LEFT JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  ON ys.payment_id = yi.payment_id AND ys.person_id = yi.person_id
  AND ys.account_type = 'holder'
WHERE fa.atendimento_data >= DATE_SUB(CURRENT_DATE(), INTERVAL 12 MONTH)
  AND fa.atendimento_data != '1900-01-01';


-- 2. ALTERNATIVA: via id_paciente → public_people (por id numérico)
-- Talvez id_paciente da fat seja o id da tabela de pacientes do DRC, não do YALO
SELECT
  COUNT(DISTINCT fa.id_paciente) AS pacientes_fat_12m
FROM `airflow-datalake-prod.DATA_LAKE_GOLD.fat_atendimento` fa
WHERE fa.atendimento_data >= DATE_SUB(CURRENT_DATE(), INTERVAL 12 MONTH)
  AND fa.id_paciente != -1;
