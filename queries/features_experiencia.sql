-- ============================================================================
-- FEATURES DE EXPERIÊNCIA DO PACIENTE — baseadas em fat_atendimento
-- Arquivo: results/features_experiencia.csv
--
-- OBJETIVO: Extrair features que medem a EXPERIENCIA do paciente durante
-- o contrato, baseadas nos dados reais de atendimento.
-- Essas features capturam os drivers #1, #5, #6, #7 da pesquisa qualitativa.
--
-- FEATURES POR CONTRATO:
--   1. nps_medio              — NPS medio dos atendimentos (0-10)
--   2. nps_minimo             — pior NPS do contrato
--   3. nota_medico_media      — nota do medico (1-5)
--   4. nota_atendimento_media — nota do atendimento (1-5)
--   5. tempo_total_medio_seg  — tempo medio total na clinica (segundos)
--   6. tempo_recepcao_medio   — tempo medio na recepcao (segundos)
--   7. tempo_consulta_medio   — tempo medio da consulta (segundos)
--   8. qtd_profissionais      — quantos medicos diferentes atenderam
--   9. qtd_unidades           — quantas unidades diferentes visitou
--  10. qtd_especialidades     — quantas especialidades usou
--  11. qtd_atendimentos       — total de atendimentos no contrato
--  12. teve_atraso             — paciente atrasou em algum atendimento (S/N)
--  13. teve_encaminhamento     — foi encaminhado pra outra especialidade (S/N)
--
-- JOIN VALIDADO:
--   fat_atendimento (id_recepcao_item)
--     → bi_recepcao_itens (id_item)
--       → ref_yalo_itens (payment_id + person_id)
--         → ref_yalo_subscriptions (contract_id)
--
-- Match confirmado: 253K atendimentos ligados a contratos YALO (12 meses)
-- ============================================================================

WITH contratos AS (
  -- Base: contratos YALO vencidos nos ultimos 12 meses (mesmos filtros do projeto)
  SELECT
    ys.contract_id,
    ys.account_id,
    ys.person_id,
    ys.contract_register_date,
    ys.contract_due_date,
    ys.plan_months_duration,
    ys.account_contract_number,

    -- Churn (definicao CORRETA: > 7 dias = renovou = N)
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
    PARTITION BY ys.contract_id
    ORDER BY ys.date_month DESC
  ) = 1
),

-- Todos os payment_ids por contrato (pra nao perder itens)
todos_payments AS (
  SELECT DISTINCT
    ys.contract_id,
    ys.payment_id,
    ys.person_id
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.contract_id IN (SELECT contract_id FROM contratos)
),

-- Atendimentos ligados a contratos YALO via cadeia de JOINs
atendimentos AS (
  SELECT
    c.contract_id,
    c.contract_register_date,
    c.contract_due_date,
    fa.id_atendimento,
    fa.atendimento_data,
    fa.id_profissional,
    fa.id_unidade,
    fa.id_especialidade,

    -- Tempos (filtrar valores invalidos: -1 = sem dados)
    CASE WHEN fa.atendimento_tm_total > 0 THEN fa.atendimento_tm_total END AS tempo_total,
    CASE WHEN fa.atendimento_tma_recepcao > 0 THEN fa.atendimento_tma_recepcao END AS tempo_recepcao,
    CASE WHEN fa.atendimento_tma_consulta > 0 THEN fa.atendimento_tma_consulta END AS tempo_consulta,

    -- NPS e notas (filtrar -1)
    CASE WHEN fa.qualidade_nps_nota != -1 THEN fa.qualidade_nps_nota END AS nps,
    CASE WHEN fa.qualidade_sms_medico_nota != -1 THEN fa.qualidade_sms_medico_nota END AS nota_medico,
    CASE WHEN fa.qualidade_sms_atendimento_nota != -1 THEN fa.qualidade_sms_atendimento_nota END AS nota_atendimento,

    -- Flags
    fa.atendimento_atraso_paciente_sn,
    fa.encaminhamento_medico_sn

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
  c.contract_id,
  c.contract_register_date,
  c.contract_due_date,
  CAST(c.plan_months_duration AS STRING) AS duracao,
  CASE WHEN c.account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo,
  c.churn_sn,

  -- Contagens
  COUNT(a.id_atendimento) AS qtd_atendimentos,
  COUNT(DISTINCT a.id_profissional) AS qtd_profissionais,
  COUNT(DISTINCT a.id_unidade) AS qtd_unidades,
  COUNT(DISTINCT a.id_especialidade) AS qtd_especialidades,

  -- NPS (so atendimentos com NPS preenchido)
  ROUND(AVG(a.nps), 1) AS nps_medio,
  MIN(a.nps) AS nps_minimo,
  MAX(a.nps) AS nps_maximo,
  COUNT(a.nps) AS qtd_com_nps,

  -- Notas
  ROUND(AVG(a.nota_medico), 2) AS nota_medico_media,
  ROUND(AVG(a.nota_atendimento), 2) AS nota_atendimento_media,

  -- Tempos (em segundos)
  ROUND(AVG(a.tempo_total)) AS tempo_total_medio,
  ROUND(AVG(a.tempo_recepcao)) AS tempo_recepcao_medio,
  ROUND(AVG(a.tempo_consulta)) AS tempo_consulta_medio,
  COUNT(a.tempo_total) AS qtd_com_tempo,

  -- Flags agregadas
  MAX(CASE WHEN a.atendimento_atraso_paciente_sn = 'S' THEN 1 ELSE 0 END) AS teve_atraso,
  MAX(CASE WHEN a.encaminhamento_medico_sn = 'S' THEN 1 ELSE 0 END) AS teve_encaminhamento,

  -- Features derivadas
  CASE
    WHEN COUNT(a.id_atendimento) = 0 THEN 'sem_atendimento'
    WHEN COUNT(DISTINCT a.id_profissional) > COUNT(DISTINCT a.id_especialidade) THEN 'rotatividade'
    ELSE 'continuidade'
  END AS padrao_profissional,

  CASE
    WHEN AVG(a.nps) IS NULL THEN 'sem_nps'
    WHEN AVG(a.nps) >= 9 THEN 'promotor'
    WHEN AVG(a.nps) >= 7 THEN 'neutro'
    ELSE 'detrator'
  END AS faixa_nps

FROM contratos c
LEFT JOIN atendimentos a ON a.contract_id = c.contract_id
GROUP BY
  c.contract_id, c.contract_register_date, c.contract_due_date,
  c.plan_months_duration, c.account_contract_number, c.churn_sn

ORDER BY c.contract_due_date DESC;
