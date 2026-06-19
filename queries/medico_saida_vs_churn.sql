-- ============================================================================
-- MEDICO SAI → PACIENTE CHURNEIA?
-- Arquivo: results/medico_saida_vs_churn.csv
--
-- Cruza: saida de medicos da rede com churn dos pacientes que
-- consultaram com eles nos ultimos 6 meses antes da saida.
--
-- Logica:
--   1. Identificar medicos que sairam (data_ultima_escala nos ultimos 18m)
--   2. Encontrar pacientes YALO que consultaram com esses medicos
--      nos 6 meses antes da saida
--   3. Verificar se esses pacientes churaram mais que os que
--      consultaram com medicos que ficaram
-- ============================================================================

WITH medicos_saida AS (
  -- Medicos que sairam: ultima escala nos ultimos 18 meses
  SELECT
    esc.id_profissional,
    MAX(esc.data) AS data_ultima_escala,
    MAX(esc.especialidade) AS especialidade_principal
  FROM `airflow-datalake-prod.DRC_DW.bi_escalas` esc
  WHERE esc.ativo_sn = 'S'
    AND esc.id_profissional IS NOT NULL
  GROUP BY esc.id_profissional
  HAVING MAX(esc.data) BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 18 MONTH)
                           AND DATE_SUB(CURRENT_DATE(), INTERVAL 2 MONTH)
  -- Exclui ultimos 2 meses: podem ser medicos ativos que so nao tem escala futura ainda
),

medicos_ativos AS (
  -- Medicos que ficaram: ultima escala nos ultimos 2 meses (ainda ativos)
  SELECT
    esc.id_profissional,
    MAX(esc.data) AS data_ultima_escala
  FROM `airflow-datalake-prod.DRC_DW.bi_escalas` esc
  WHERE esc.ativo_sn = 'S'
    AND esc.id_profissional IS NOT NULL
  GROUP BY esc.id_profissional
  HAVING MAX(esc.data) >= DATE_SUB(CURRENT_DATE(), INTERVAL 2 MONTH)
),

-- Contratos YALO com churn
contratos AS (
  SELECT
    ys.contract_id,
    ys.account_id,
    ys.person_id,
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
    AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 18 MONTH)
    AND ys.contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ys.contract_id ORDER BY ys.date_month DESC) = 1
),

-- Todos os payment_ids
todos_payments AS (
  SELECT DISTINCT contract_id, payment_id, person_id
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions`
  WHERE account_type = 'holder'
    AND contract_id IN (SELECT contract_id FROM contratos)
),

-- Atendimentos: qual paciente consultou com qual medico
atendimentos AS (
  SELECT DISTINCT
    c.contract_id,
    c.contract_due_date,
    c.churn_sn,
    c.days_diff_until_next_contract,
    fa.id_profissional,
    fa.atendimento_data
  FROM contratos c
  INNER JOIN todos_payments tp ON tp.contract_id = c.contract_id
  INNER JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_itens` yi
    ON yi.payment_id = tp.payment_id AND yi.person_id = tp.person_id
  INNER JOIN `airflow-datalake-prod.DRC_DW.bi_recepcao_itens` ri
    ON ri.id_item = yi.id_item
  INNER JOIN `airflow-datalake-prod.DATA_LAKE_GOLD.fat_atendimento` fa
    ON fa.id_recepcao_item = ri.id_item
  WHERE fa.atendimento_data >= c.contract_register_date
    AND fa.atendimento_data <= c.contract_due_date
    AND fa.id_profissional IS NOT NULL
    AND fa.id_profissional != -1
),

-- Classificar cada contrato: consultou com medico que SAIU ou que FICOU?
contrato_medico AS (
  SELECT
    a.contract_id,
    a.contract_due_date,
    a.churn_sn,
    a.days_diff_until_next_contract,

    -- Teve medico que saiu?
    MAX(CASE WHEN ms.id_profissional IS NOT NULL THEN 1 ELSE 0 END) AS teve_medico_saiu,

    -- Quantos medicos diferentes consultou
    COUNT(DISTINCT a.id_profissional) AS qtd_medicos,

    -- Quantos desses sairam
    COUNT(DISTINCT CASE WHEN ms.id_profissional IS NOT NULL THEN a.id_profissional END) AS qtd_medicos_sairam

  FROM atendimentos a
  LEFT JOIN medicos_saida ms ON ms.id_profissional = a.id_profissional
  GROUP BY 1, 2, 3, 4
)

SELECT
  CASE WHEN teve_medico_saiu = 1 THEN 'Medico saiu' ELSE 'Medico ficou' END AS status_medico,
  COUNT(*) AS total_contratos,

  -- Churn original
  SUM(CASE WHEN churn_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  ROUND(100.0 * SUM(CASE WHEN churn_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 2) AS churn_rate,

  -- Churn real 30d
  SUM(CASE WHEN churn_sn = 'S'
       AND (days_diff_until_next_contract IS NULL OR days_diff_until_next_contract > 30 OR days_diff_until_next_contract <= 0)
       THEN 1 ELSE 0 END) AS churn_real,
  ROUND(100.0 * SUM(CASE WHEN churn_sn = 'S'
       AND (days_diff_until_next_contract IS NULL OR days_diff_until_next_contract > 30 OR days_diff_until_next_contract <= 0)
       THEN 1 ELSE 0 END) / COUNT(*), 2) AS churn_real_rate,

  -- Medias
  ROUND(AVG(qtd_medicos), 1) AS media_medicos,
  ROUND(AVG(qtd_medicos_sairam), 1) AS media_medicos_sairam

FROM contrato_medico
GROUP BY 1
ORDER BY 1;
