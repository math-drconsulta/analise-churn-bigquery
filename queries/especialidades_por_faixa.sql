-- ============================================================================
-- ESPECIALIDADES CONSUMIDAS POR FAIXA DE SCORE
-- Arquivo: results/especialidades_por_faixa.csv
--
-- Para cada contrato do universo de churn, identifica quais especialidades
-- foram usadas via fat_atendimento. Cruza com o score v4 pra ver
-- quais especialidades predominam em cada faixa.
--
-- Também calcula churn real 30d por especialidade (usou vs nao usou).
-- ============================================================================

WITH contratos AS (
  SELECT
    ys.contract_id,
    ys.account_id,
    ys.contract_register_date,
    ys.contract_due_date,
    ys.plan_months_duration,
    ys.account_contract_number,
    ys.days_diff_until_next_contract,

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
    AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 12 MONTH)
    AND ys.contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),

-- Todos os payment_ids por contrato
todos_payments AS (
  SELECT DISTINCT contract_id, payment_id, person_id
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions`
  WHERE account_type = 'holder'
    AND contract_id IN (SELECT contract_id FROM contratos)
),

-- Especialidades usadas por contrato (via fat_atendimento)
uso_especialidade AS (
  SELECT
    c.contract_id,
    CASE
      WHEN ri.produto_grupo = 'EXAMES' THEN 'EXAMES'
      WHEN ri.produto_grupo = 'CM' AND ri.unidade = 'TELE' THEN 'CM_TELE'
      WHEN ri.produto_grupo = 'CM' AND ri.executante_especialidade = 'CLINICA MEDICA' THEN 'CLINICA_MEDICA'
      WHEN ri.produto_grupo = 'CM' AND ri.executante_especialidade = 'GINECOLOGISTA' THEN 'GINECOLOGIA'
      WHEN ri.produto_grupo = 'CM' AND ri.executante_especialidade = 'CARDIOLOGISTA' THEN 'CARDIOLOGIA'
      WHEN ri.produto_grupo = 'CM' AND ri.executante_especialidade = 'DERMATOLOGISTA' THEN 'DERMATOLOGIA'
      WHEN ri.produto_grupo = 'CM' AND ri.executante_especialidade = 'ENDOCRINOLOGISTA' THEN 'ENDOCRINOLOGIA'
      WHEN ri.produto_grupo = 'CM' AND ri.executante_especialidade = 'GASTROENTEROLOGISTA' THEN 'GASTROENTEROLOGIA'
      WHEN ri.produto_grupo = 'CM' AND ri.executante_especialidade = 'OFTALMOLOGISTA' THEN 'OFTALMOLOGIA'
      WHEN ri.produto_grupo = 'CM' AND ri.executante_especialidade = 'ORTOPEDISTA' THEN 'ORTOPEDIA'
      WHEN ri.produto_grupo = 'CM' AND ri.executante_especialidade = 'PEDIATRA' THEN 'PEDIATRIA'
      WHEN ri.produto_grupo = 'CM' AND ri.executante_especialidade = 'PSIQUIATRIA' THEN 'PSIQUIATRIA'
      WHEN ri.produto_grupo = 'CM' AND ri.executante_especialidade = 'UROLOGISTA' THEN 'UROLOGIA'
      WHEN ri.produto_grupo = 'CM' AND ri.executante_especialidade = 'NEUROLOGIA' THEN 'NEUROLOGIA'
      WHEN ri.produto_grupo = 'CM' THEN 'CM_OUTROS'
      ELSE 'OUTROS'
    END AS especialidade,
    COUNT(*) AS qtd_atendimentos
  FROM contratos c
  INNER JOIN todos_payments tp ON tp.contract_id = c.contract_id
  INNER JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_itens` yi
    ON yi.payment_id = tp.payment_id AND yi.person_id = tp.person_id
  INNER JOIN `airflow-datalake-prod.DRC_DW.bi_recepcao_itens` ri
    ON ri.id_item = yi.id_item
  WHERE ri.data >= c.contract_register_date
    AND ri.data <= c.contract_due_date
    AND ri.data IS NOT NULL
    AND ri.produto_grupo IS NOT NULL
  GROUP BY 1, 2
)

SELECT
  c.contract_id,
  CAST(c.plan_months_duration AS STRING) AS duracao,
  CASE WHEN c.account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo,
  c.churn_sn,

  -- Churn real 30d
  CASE
    WHEN c.churn_sn = 'N' THEN 0
    WHEN c.days_diff_until_next_contract > 0 AND c.days_diff_until_next_contract <= 30 THEN 0
    ELSE 1
  END AS churn_real_30d,

  -- Flags de uso por especialidade (1 = usou, 0 = nao usou)
  MAX(CASE WHEN ue.especialidade = 'CLINICA_MEDICA' THEN 1 ELSE 0 END) AS usou_clinica_medica,
  MAX(CASE WHEN ue.especialidade = 'CM_TELE' THEN 1 ELSE 0 END) AS usou_tele,
  MAX(CASE WHEN ue.especialidade = 'EXAMES' THEN 1 ELSE 0 END) AS usou_exames,
  MAX(CASE WHEN ue.especialidade = 'GINECOLOGIA' THEN 1 ELSE 0 END) AS usou_ginecologia,
  MAX(CASE WHEN ue.especialidade = 'CARDIOLOGIA' THEN 1 ELSE 0 END) AS usou_cardiologia,
  MAX(CASE WHEN ue.especialidade = 'DERMATOLOGIA' THEN 1 ELSE 0 END) AS usou_dermatologia,
  MAX(CASE WHEN ue.especialidade = 'ENDOCRINOLOGIA' THEN 1 ELSE 0 END) AS usou_endocrinologia,
  MAX(CASE WHEN ue.especialidade = 'GASTROENTEROLOGIA' THEN 1 ELSE 0 END) AS usou_gastro,
  MAX(CASE WHEN ue.especialidade = 'OFTALMOLOGIA' THEN 1 ELSE 0 END) AS usou_oftalmo,
  MAX(CASE WHEN ue.especialidade = 'ORTOPEDIA' THEN 1 ELSE 0 END) AS usou_ortopedia,
  MAX(CASE WHEN ue.especialidade = 'PEDIATRIA' THEN 1 ELSE 0 END) AS usou_pediatria,
  MAX(CASE WHEN ue.especialidade = 'PSIQUIATRIA' THEN 1 ELSE 0 END) AS usou_psiquiatria,
  MAX(CASE WHEN ue.especialidade = 'UROLOGIA' THEN 1 ELSE 0 END) AS usou_urologia,
  MAX(CASE WHEN ue.especialidade = 'NEUROLOGIA' THEN 1 ELSE 0 END) AS usou_neurologia,
  MAX(CASE WHEN ue.especialidade = 'CM_OUTROS' THEN 1 ELSE 0 END) AS usou_cm_outros,

  -- Total de especialidades distintas usadas
  COUNT(DISTINCT ue.especialidade) AS qtd_especialidades_usadas,

  -- Total de atendimentos
  COALESCE(SUM(ue.qtd_atendimentos), 0) AS total_atendimentos

FROM contratos c
LEFT JOIN uso_especialidade ue ON ue.contract_id = c.contract_id
GROUP BY 1, 2, 3, 4, 5
ORDER BY c.contract_id;
