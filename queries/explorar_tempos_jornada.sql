-- ============================================================================
-- TEMPOS DE ESPERA (TME) E ATENDIMENTO (TMA) POR ETAPA × CHURN
-- Arquivo: results/tempos_jornada.csv
--
-- Analisa cada etapa da jornada do paciente na clinica:
--   1. Recepcao: TME (espera pra ser recebido) + TMA (tempo no balcao)
--   2. Pre-consulta: TME (espera pra triagem) + TMA (tempo com enfermagem)
--   3. Consulta: TME (espera pro medico) + TMA (tempo com medico)
--   4. Pos-consulta: TMA (retorno ao balcao)
--
-- TME = Tempo Medio de Espera (o que o paciente sente)
-- TMA = Tempo Medio de Atendimento (o que o profissional gasta)
--
-- Cruza com churn via cadeia fat_atendimento → bi_recepcao → yalo_itens → yalo_subscriptions
-- ============================================================================

WITH contratos AS (
  SELECT
    ys.contract_id,
    ys.contract_register_date,
    ys.contract_due_date,
    ys.plan_months_duration,
    ys.account_contract_number,
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

todos_payments AS (
  SELECT DISTINCT contract_id, payment_id, person_id
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions`
  WHERE account_type = 'holder'
    AND contract_id IN (SELECT contract_id FROM contratos)
),

atendimentos AS (
  SELECT
    c.contract_id,
    c.churn_sn,
    CAST(c.plan_months_duration AS STRING) AS duracao,
    CASE WHEN c.account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo,

    -- TME (espera) por etapa — filtrar -1
    CASE WHEN fa.atendimento_tme_recepcao > 0 THEN fa.atendimento_tme_recepcao END AS tme_recepcao,
    CASE WHEN fa.atendimento_tme_preconsulta > 0 THEN fa.atendimento_tme_preconsulta END AS tme_preconsulta,
    CASE WHEN fa.atendimento_tme_consulta > 0 THEN fa.atendimento_tme_consulta END AS tme_consulta,

    -- TMA (atendimento) por etapa
    CASE WHEN fa.atendimento_tma_recepcao > 0 THEN fa.atendimento_tma_recepcao END AS tma_recepcao,
    CASE WHEN fa.atendimento_tma_preconsulta > 0 THEN fa.atendimento_tma_preconsulta END AS tma_preconsulta,
    CASE WHEN fa.atendimento_tma_consulta > 0 THEN fa.atendimento_tma_consulta END AS tma_consulta,
    CASE WHEN fa.atendimento_tma_posconsulta > 0 THEN fa.atendimento_tma_posconsulta END AS tma_posconsulta,

    -- Tempo total
    CASE WHEN fa.atendimento_tm_total > 0 THEN fa.atendimento_tm_total END AS tm_total,

    -- Timestamps pra calcular espera real (senha ate consulta)
    fa.atendimento_stamp_senha,
    fa.atendimento_stamp_consulta_ini

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
    AND fa.atendimento_data != '1900-01-01'
)

SELECT
  contract_id,
  churn_sn,
  duracao,
  ciclo,

  -- Medias por contrato (em segundos)
  COUNT(*) AS qtd_atendimentos,

  -- TME (espera)
  ROUND(AVG(tme_recepcao)) AS tme_recepcao_medio,
  ROUND(AVG(tme_preconsulta)) AS tme_preconsulta_medio,
  ROUND(AVG(tme_consulta)) AS tme_consulta_medio,
  ROUND(AVG(COALESCE(tme_recepcao, 0) + COALESCE(tme_preconsulta, 0) + COALESCE(tme_consulta, 0))) AS tme_total_medio,

  -- TMA (atendimento)
  ROUND(AVG(tma_recepcao)) AS tma_recepcao_medio,
  ROUND(AVG(tma_preconsulta)) AS tma_preconsulta_medio,
  ROUND(AVG(tma_consulta)) AS tma_consulta_medio,
  ROUND(AVG(tma_posconsulta)) AS tma_posconsulta_medio,

  -- Tempo total
  ROUND(AVG(tm_total)) AS tm_total_medio,

  -- Espera senha ate consulta (quando disponivel)
  ROUND(AVG(
    CASE
      WHEN atendimento_stamp_senha IS NOT NULL
       AND atendimento_stamp_consulta_ini IS NOT NULL
       AND atendimento_stamp_consulta_ini > atendimento_stamp_senha
      THEN TIMESTAMP_DIFF(atendimento_stamp_consulta_ini, atendimento_stamp_senha, SECOND)
    END
  )) AS espera_senha_ate_consulta_medio,

  -- Contagem de preenchimento
  COUNTIF(tme_recepcao IS NOT NULL) AS qtd_com_tme_rec,
  COUNTIF(tme_preconsulta IS NOT NULL) AS qtd_com_tme_pre,
  COUNTIF(tme_consulta IS NOT NULL) AS qtd_com_tme_con,
  COUNTIF(atendimento_stamp_senha IS NOT NULL AND atendimento_stamp_consulta_ini IS NOT NULL) AS qtd_com_stamps

FROM atendimentos
GROUP BY 1, 2, 3, 4
ORDER BY contract_id;
