-- ============================================================================
-- COMITÊ-3: DADOS INDIVIDUAIS PARA SCORE + UPLIFT CAUSAL
-- Base: anl_churn_contratos + ref_yalo_subscriptions (plan_name)
-- Recorte: planos 6+12m + credit_card + sem B2B + últimos 12 meses
--
-- 1 linha = 1 contrato (~188k linhas)
--
-- Features incluídas:
--   Identificadores:    contract_id, account_id
--   Target:             churn (0/1)
--   Demográficas:       ciclo, faixa_etaria, cronico, composicao_titular, sexo, classe_social
--   Contratuais:        duracao, canal, tem_odonto
--   Comportamentais:    usou_{cm, cm_tele, exames, clinica_medica, ginecologia,
--                              cardiologia, dermatologia, endocrinologia, psiquiatria,
--                              ortopedia, pediatria}  (S/N por especialidade)
--
-- Exporta: results_comite/dados_individuais.csv
-- Consumido por: pages_comite/7_Score_Individual.py + comite_individual.py
-- ============================================================================

WITH base AS (
  SELECT
    c.contract_id,
    c.account_id,

    -- Target
    CASE WHEN c.churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END AS churn,

    -- Demográficas
    CASE WHEN c.account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo,
    CASE
      WHEN c.titular_idade <= 20 THEN '00-20'
      WHEN c.titular_idade <= 30 THEN '21-30'
      WHEN c.titular_idade <= 50 THEN '31-50'
      WHEN c.titular_idade <= 70 THEN '51-70'
      ELSE '71+'
    END AS faixa_etaria,
    IFNULL(c.titular_main_cronico_sn, 'N') AS cronico,
    CASE
      WHEN IFNULL(c.dependents_per_holder_0020_SN, 'N') = 'S'
       AND IFNULL(c.dependents_per_holder_6099_SN, 'N') = 'S' THEN 'com_ambos'
      WHEN IFNULL(c.dependents_per_holder_0020_SN, 'N') = 'S' THEN 'com_crianca'
      WHEN IFNULL(c.dependents_per_holder_6099_SN, 'N') = 'S' THEN 'com_idoso'
      ELSE 'solo'
    END AS composicao_titular,
    IFNULL(c.titular_sexo, 'I') AS sexo,
    IFNULL(c.titual_classe_social, '(sem dados)') AS classe_social,

    -- Contratuais
    CAST(c.plan_months_duration AS STRING) AS duracao,
    IFNULL(c.order_source_aj, 'outros') AS canal,

    -- Comportamentais — flag binária (usou ao menos 1 vez no contrato)
    CASE WHEN IFNULL(c.qtd_TOTAL_CM, 0)                 > 0 THEN 1 ELSE 0 END AS usou_cm,
    CASE WHEN IFNULL(c.qtd_TOTAL_CM_TELE, 0)            > 0 THEN 1 ELSE 0 END AS usou_cm_tele,
    CASE WHEN IFNULL(c.qtd_TOTAL_EXAMES, 0)             > 0 THEN 1 ELSE 0 END AS usou_exames,
    CASE WHEN IFNULL(c.qtd_TOTAL_CM_CLINICA_MEDICA, 0)  > 0 THEN 1 ELSE 0 END AS usou_clinica_medica,
    CASE WHEN IFNULL(c.qtd_TOTAL_CM_GINECOLOGIA, 0)     > 0 THEN 1 ELSE 0 END AS usou_ginecologia,
    CASE WHEN IFNULL(c.qtd_TOTAL_CM_CARDIOLOGISTA, 0)   > 0 THEN 1 ELSE 0 END AS usou_cardiologia,
    CASE WHEN IFNULL(c.qtd_TOTAL_CM_DERMATOLOGISTA, 0)  > 0 THEN 1 ELSE 0 END AS usou_dermatologia,
    CASE WHEN IFNULL(c.qtd_TOTAL_CM_ENDOCRINOLOGISTA, 0) > 0 THEN 1 ELSE 0 END AS usou_endocrinologia,
    CASE WHEN IFNULL(c.qtd_TOTAL_CM_PSIQUIATRIA, 0)     > 0 THEN 1 ELSE 0 END AS usou_psiquiatria,
    CASE WHEN IFNULL(c.qtd_TOTAL_CM_ORTOPEDISTA, 0)     > 0 THEN 1 ELSE 0 END AS usou_ortopedia,
    CASE WHEN IFNULL(c.qtd_TOTAL_CM_PEDIATRA, 0)        > 0 THEN 1 ELSE 0 END AS usou_pediatria

  FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` c
  WHERE c.plan_months_duration IN (6, 12)
    AND c.order_payment_method = 'credit_card'
    AND IFNULL(c.order_source_aj, '') != 'b2b'
    AND c.contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
),

planos AS (
  -- 1 plan_name por contract_id (qualquer um — costuma ser único pelo contrato)
  SELECT
    ys.contract_id,
    ANY_VALUE(ys.plan_name) AS plan_name
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
  GROUP BY ys.contract_id
)

SELECT
  b.contract_id,
  b.account_id,
  b.churn,

  -- Demográficas
  b.ciclo,
  b.faixa_etaria,
  b.cronico,
  b.composicao_titular,
  b.sexo,
  b.classe_social,

  -- Contratuais
  b.duracao,
  b.canal,
  CASE WHEN LOWER(IFNULL(p.plan_name, '')) LIKE '%odonto%' THEN 1 ELSE 0 END AS tem_odonto,

  -- Comportamentais
  b.usou_cm,
  b.usou_cm_tele,
  b.usou_exames,
  b.usou_clinica_medica,
  b.usou_ginecologia,
  b.usou_cardiologia,
  b.usou_dermatologia,
  b.usou_endocrinologia,
  b.usou_psiquiatria,
  b.usou_ortopedia,
  b.usou_pediatria

FROM base b
LEFT JOIN planos p ON p.contract_id = b.contract_id;
