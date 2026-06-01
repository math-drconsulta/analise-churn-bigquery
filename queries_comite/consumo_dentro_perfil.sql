-- ============================================================================
-- COMITÊ-2: CONSUMO DE ESPECIALIDADES DENTRO DE PERFIL — APENAS CREDIT_CARD
-- Base: anl_churn_contratos | Filtro: planos 6+12m + credit_card + sem B2B
--
-- Por que "dentro de perfil"?
--   O consumo é confounded com o ciclo do contrato (1o contrato consome mais e
--   tem churn maior). Comparar "usou vs não usou" no agregado dá leitura errada.
--   Aqui controlamos por 4 vars do perfil (ciclo × faixa × crônico × composicao_titular)
--   × duração — só depois a página agrega por bucket de risco.
--
-- Especialidades cobertas (11):
--   CM_presencial, CM_tele, exames, clinica_medica,
--   ginecologia, cardiologia, dermatologia, endocrinologia,
--   psiquiatria, ortopedia, pediatria
--
-- Saída (long format):
--   duracao, ciclo, faixa_etaria, cronico, composicao_titular,
--   especialidade, uso, total_contratos, churners, churn_rate
--
-- Exporta: results_comite/consumo_dentro_perfil.csv
-- Consumido por: pages_comite/5_Transicao_Faixas.py
-- ============================================================================

WITH base AS (
  SELECT
    CAST(plan_months_duration AS STRING) AS duracao,
    CASE WHEN account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo,
    CASE
      WHEN titular_idade <= 20 THEN '00-20'
      WHEN titular_idade <= 30 THEN '21-30'
      WHEN titular_idade <= 50 THEN '31-50'
      WHEN titular_idade <= 70 THEN '51-70'
      ELSE '71+'
    END AS faixa_etaria,
    IFNULL(titular_main_cronico_sn, 'N') AS cronico,
    CASE
      WHEN IFNULL(dependents_per_holder_0020_SN, 'N') = 'S' AND IFNULL(dependents_per_holder_6099_SN, 'N') = 'S' THEN 'com_ambos'
      WHEN IFNULL(dependents_per_holder_0020_SN, 'N') = 'S'                                       THEN 'com_crianca'
      WHEN IFNULL(dependents_per_holder_6099_SN, 'N') = 'S'                                       THEN 'com_idoso'
      ELSE 'solo'
    END AS composicao_titular,
    churn_renovacao_automatica_sn,

    IFNULL(qtd_TOTAL_CM, 0)                 AS q_cm,
    IFNULL(qtd_TOTAL_CM_TELE, 0)            AS q_cm_tele,
    IFNULL(qtd_TOTAL_EXAMES, 0)             AS q_exames,
    IFNULL(qtd_TOTAL_CM_CLINICA_MEDICA, 0)  AS q_clinica,
    IFNULL(qtd_TOTAL_CM_GINECOLOGIA, 0)     AS q_gin,
    IFNULL(qtd_TOTAL_CM_CARDIOLOGISTA, 0)   AS q_card,
    IFNULL(qtd_TOTAL_CM_DERMATOLOGISTA, 0)  AS q_derm,
    IFNULL(qtd_TOTAL_CM_ENDOCRINOLOGISTA, 0) AS q_endo,
    IFNULL(qtd_TOTAL_CM_PSIQUIATRIA, 0)     AS q_psiq,
    IFNULL(qtd_TOTAL_CM_ORTOPEDISTA, 0)     AS q_ort,
    IFNULL(qtd_TOTAL_CM_PEDIATRA, 0)        AS q_ped

  FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
  WHERE plan_months_duration IN (6, 12)
    AND order_payment_method = 'credit_card'
    AND IFNULL(order_source_aj, '') != 'b2b'
    AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
),

unpivoted AS (
  SELECT
    duracao, ciclo, faixa_etaria, cronico, composicao_titular, churn_renovacao_automatica_sn,
    esp.especialidade,
    IF(esp.qtd > 0, 'usou', 'nao_usou') AS uso
  FROM base, UNNEST([
    STRUCT('CM_presencial'    AS especialidade, q_cm        AS qtd),
    STRUCT('CM_tele'          AS especialidade, q_cm_tele   AS qtd),
    STRUCT('exames'           AS especialidade, q_exames    AS qtd),
    STRUCT('clinica_medica'   AS especialidade, q_clinica   AS qtd),
    STRUCT('ginecologia'      AS especialidade, q_gin       AS qtd),
    STRUCT('cardiologia'      AS especialidade, q_card      AS qtd),
    STRUCT('dermatologia'     AS especialidade, q_derm      AS qtd),
    STRUCT('endocrinologia'   AS especialidade, q_endo      AS qtd),
    STRUCT('psiquiatria'      AS especialidade, q_psiq      AS qtd),
    STRUCT('ortopedia'        AS especialidade, q_ort       AS qtd),
    STRUCT('pediatria'        AS especialidade, q_ped       AS qtd)
  ]) AS esp
)

SELECT
  duracao,
  ciclo,
  faixa_etaria,
  cronico,
  composicao_titular,
  especialidade,
  uso,
  COUNT(*) AS total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_rate

FROM unpivoted
GROUP BY 1, 2, 3, 4, 5, 6, 7
HAVING COUNT(*) >= 30
ORDER BY duracao, especialidade, ciclo, faixa_etaria, cronico, composicao_titular, uso;
