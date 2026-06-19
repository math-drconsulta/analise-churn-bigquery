-- ============================================================================
-- MEDICOS DA REDE — Cadastro + Movimentacao Mensal
-- Adaptado de MySQL para BigQuery
-- Arquivo: results/medicos_rede.csv
-- ============================================================================

WITH escalas_profissional AS (
  SELECT
    esc.id_profissional,
    MIN(esc.data) AS data_primeira_escala,
    MAX(esc.data) AS data_ultima_escala,
    STRING_AGG(DISTINCT esc.especialidade) AS especialidades_atuacao,
    STRING_AGG(DISTINCT CASE WHEN uni.unidade != 'TELE' THEN uni.uf END) AS estados_atuacao,
    STRING_AGG(DISTINCT CASE WHEN uni.unidade != 'TELE' THEN uni.micro_regional END) AS micros_atuacao,
    SUM(CASE WHEN uni.unidade = 'TELE' THEN slots_total ELSE 0 END) AS slots_telemed
  FROM `airflow-datalake-prod.DRC_DW.bi_escalas` esc
  LEFT JOIN `airflow-datalake-prod.DRC_DW.bi_unidades` uni
    ON uni.id_unidade = esc.id_unidade
  WHERE esc.ativo_sn = 'S'
    AND esc.id_profissional IS NOT NULL
  GROUP BY esc.id_profissional
),

profissionais_base AS (
  SELECT
    pro.id_profissional,
    pro.nome AS profissional,
    pro.sexo,
    pro.dt_nasc,
    pro.id_tipo_profissional,
    prt.tipo_profissional,
    pro.ativo_sn AS profissional_ativo_sn,
    pro.dt_inicio AS data_cadastro_s2,
    pro.head_sn,
    pro.lauda_sn,
    pro.faculdade,
    pro.ano_formatura,
    pro.local_residencia,
    pro.ano_conclusao_residencia,
    pro.formacao_outros,
    pro.mestrado_sn,
    pro.doutorado_sn,
    COALESCE(pcs.descricao, 'Pendente') AS contrato_status,
    ep.data_primeira_escala,
    ep.data_ultima_escala,
    ep.especialidades_atuacao,
    ep.estados_atuacao,
    ep.micros_atuacao,
    ep.slots_telemed
  FROM `airflow-datalake-prod.DRC.profissionais` pro
  LEFT JOIN `airflow-datalake-prod.DRC.profissionais_tipo` prt
    ON prt.id_tipo_profissional = pro.id_tipo_profissional
  LEFT JOIN `airflow-datalake-prod.DRC.profissional_contrato_status` pcs
    ON pcs.id_contrato_status = pro.status_assinatura
  LEFT JOIN escalas_profissional ep
    ON ep.id_profissional = pro.id_profissional
  WHERE pro.id_tipo_profissional NOT IN ('E', 'N')
    AND ep.id_profissional IS NOT NULL
),

-- Especialidade principal (a com mais minutos de escala)
especialidade_principal AS (
  SELECT
    id_profissional,
    especialidade
  FROM (
    SELECT
      id_profissional,
      especialidade,
      SUM(minutos) AS minutos,
      ROW_NUMBER() OVER (PARTITION BY id_profissional ORDER BY SUM(minutos) DESC) AS rn
    FROM `airflow-datalake-prod.DRC_DW.bi_escalas`
    WHERE ativo_sn = 'S'
      AND id_profissional IS NOT NULL
    GROUP BY id_profissional, especialidade
  )
  WHERE rn = 1
),

-- Gerar meses entre primeira e ultima escala
meses AS (
  SELECT
    pb.id_profissional,
    DATE_TRUNC(dt, MONTH) AS anomes
  FROM profissionais_base pb,
  UNNEST(GENERATE_DATE_ARRAY(
    DATE_TRUNC(pb.data_primeira_escala, MONTH),
    DATE_TRUNC(pb.data_ultima_escala, MONTH),
    INTERVAL 1 MONTH
  )) AS dt
)

SELECT
  pb.id_profissional,
  pb.profissional,
  pb.sexo,
  pb.dt_nasc,
  pb.id_tipo_profissional,
  pb.tipo_profissional,
  pb.profissional_ativo_sn,
  pb.data_cadastro_s2,
  pb.head_sn,
  pb.lauda_sn,
  pb.faculdade,
  pb.ano_formatura,
  pb.local_residencia,
  pb.ano_conclusao_residencia,
  pb.formacao_outros,
  pb.mestrado_sn,
  pb.doutorado_sn,
  pb.contrato_status,
  ep.especialidade,
  pb.data_primeira_escala,
  pb.data_ultima_escala,
  FORMAT_DATE('%Y%m', m.anomes) AS anomes,
  CASE
    WHEN FORMAT_DATE('%Y%m', pb.data_ultima_escala) = FORMAT_DATE('%Y%m', m.anomes) THEN 'Saida'
    WHEN FORMAT_DATE('%Y%m', pb.data_primeira_escala) = FORMAT_DATE('%Y%m', m.anomes) THEN 'Entrada'
    ELSE 'Ativo'
  END AS movimentacao,
  pb.estados_atuacao,
  pb.especialidades_atuacao,
  pb.micros_atuacao,
  CASE WHEN pb.slots_telemed > 0 THEN 'Faz TELEMED' ELSE 'Nao faz TELEMED' END AS telemed_atuacao

FROM meses m
JOIN profissionais_base pb ON pb.id_profissional = m.id_profissional
LEFT JOIN especialidade_principal ep ON ep.id_profissional = pb.id_profissional

ORDER BY pb.id_profissional, m.anomes;
