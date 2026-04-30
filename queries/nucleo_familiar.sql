-- ============================================================================
-- QUERY: NUCLEO FAMILIAR — features dos dependentes por contrato (v2)
-- Output: results/nucleo_familiar.csv  (1 linha por contrato)
-- Consumido por: pages/7_Nucleo_Familiar.py
--
-- Mudanças vs v1
-- --------------
-- v1 tinha 2 problemas (descobertos na 1a EDA):
--
--   (1) ~26% dos contratos com dep_count_anl > qtd_dep_total: a v1 filtrava
--       s.contract_payment_number = 1 em ref_yalo_subscriptions, dropando
--       dependentes adicionados em payments posteriores. CORREÇÃO: filtro
--       removido; DISTINCT por (contract_id, person_id) já deduplica.
--
--   (2) ~64% dos contratos com pelo menos 1 dep com idade NULL: pacientes_audit
--       só cobre quem tem cadastro/atendimento na DRC. Deps inscritos no plano
--       mas que nunca consumiram não estão lá. A v1 mascarava esses casos no
--       ELSE 'multi_geracional', deixando a categoria inútil.
--       CORREÇÃO: tratar idade ausente e atendimento ausente como categorias
--       explícitas — vira sinal, não bug:
--         - dep_ativo_drc   = tem atendimento (main_cronico_sn não-NULL)
--         - dep_passivo_drc = nunca teve atendimento (main_cronico_sn NULL)
--       Composição etária só é calculada quando TODOS os deps têm idade
--       conhecida — caso contrário marca 'idade_parcial'.
--       Crônico do dep agora tem 3 estados: 'S' / 'N' confirmado / 'desconhecido'.
--
-- Universo (idêntico ao score atual)
-- ----------------------------------
--   - plan_months_duration IN (6, 12)
--   - order_payment_method = 'credit_card'
--   - order_source_aj != 'b2b'
--   - contract_due_date_month nos últimos 12 meses
--
-- Definição de domínio: dependente financeiro = idade < 21 OU idade > 60.
-- ============================================================================

WITH

-- ----------------------------------------------------------------------------
-- 1) Idade por paciente (do cadastro). NULL se paciente não tem dt_nasc
--    em pacientes_audit (caso típico: dep que nunca consumiu na DRC).
-- ----------------------------------------------------------------------------
pac AS (
  SELECT
    id_paciente,
    DATE_DIFF(CURRENT_DATE(), MAX(dt_nasc), YEAR) AS idade
  FROM `airflow-datalake-prod.DRC.pacientes_audit`
  WHERE dt_nasc IS NOT NULL
  GROUP BY 1
),

-- ----------------------------------------------------------------------------
-- 2) Crônico por paciente. Mesma lógica de queries_originais/pacientes.sql.
--    Resultado por id_paciente:
--      'S' = paciente tem CID classificado como Hipertensão/Diabetes/Dislipidemia
--      'N' = paciente tem atendimento mas nenhum CID crônico
--    Pacientes sem atendimento NÃO aparecem aqui — LEFT JOIN devolverá NULL.
-- ----------------------------------------------------------------------------
ate_cron AS (
  SELECT
    ated.id_paciente,
    IFNULL(MAX(cc.main_cronico_sn), 'N') AS main_cronico_sn
  FROM `airflow-datalake-prod.DRC_DW.bi_atendimentos` ated
  LEFT JOIN `airflow-datalake-prod.DRC.atendimentos_diagnosticos` ad
    ON ated.id_atendimento = ad.id_atendimento
  LEFT JOIN (
    SELECT
      *,
      CASE
        WHEN CID_Hipertensao_SN = 'S'
          OR CID_Diabetico_SN = 'S'
          OR CID_Dislipidemia_SN = 'S' THEN 'S'
        ELSE 'N'
      END AS main_cronico_sn
    FROM `airflow-datalake-prod.DePara_BI.DePara_Classificacao_CIDs_aj`
  ) cc ON ad.cid = cc.CID
  GROUP BY 1
),

-- ----------------------------------------------------------------------------
-- 3) Lista dependentes de cada contrato com idade e crônico.
--    SEM filtro contract_payment_number=1 (correção v2). DISTINCT por
--    (contract_id, person_id) deduplica pessoas em múltiplos payments.
--
--    Os 3 valores possíveis para main_cronico_sn aqui:
--      'S'  → dep tem atendimento e diagnóstico crônico
--      'N'  → dep tem atendimento mas sem CID crônico
--      NULL → dep nunca teve atendimento na DRC (passivo)
-- ----------------------------------------------------------------------------
deps_contrato AS (
  SELECT DISTINCT
    s.contract_id,
    s.person_id,
    s.id_paciente,
    pac.idade,
    ac.main_cronico_sn
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` s
  LEFT JOIN pac          ON pac.id_paciente = s.id_paciente
  LEFT JOIN ate_cron ac  ON ac.id_paciente = s.id_paciente
  WHERE s.account_type != 'holder'
),

-- ----------------------------------------------------------------------------
-- 4) Agrega features do núcleo por contrato
-- ----------------------------------------------------------------------------
nucleo AS (
  SELECT
    contract_id,

    -- Total
    COUNT(*) AS qtd_dep_total,

    -- Engajamento DRC
    COUNTIF(main_cronico_sn IS NOT NULL) AS qtd_dep_ativos_drc,
    COUNTIF(main_cronico_sn IS NULL)     AS qtd_dep_passivos_drc,

    -- Disponibilidade de idade
    COUNTIF(idade IS NOT NULL) AS qtd_dep_idade_conhecida,
    COUNTIF(idade IS NULL)     AS qtd_dep_idade_desconhecida,

    -- Buckets etários (deps sem idade caem fora destes counts)
    COUNTIF(idade < 21)               AS qtd_dep_jovens,        -- <21 (financeiro jovem)
    COUNTIF(idade > 60)               AS qtd_dep_idosos,        -- >60 (financeiro idoso)
    COUNTIF(idade BETWEEN 21 AND 60)  AS qtd_dep_adultos,       -- 21-60 (econ. ativos)
    COUNTIF(idade < 21 OR idade > 60) AS qtd_dep_financeiros,

    -- Crônico em 3 estados
    COUNTIF(main_cronico_sn = 'S')   AS qtd_dep_cronicos_S,
    COUNTIF(main_cronico_sn = 'N')   AS qtd_dep_cronicos_N_confirmado,
    COUNTIF(main_cronico_sn IS NULL) AS qtd_dep_cronicos_desconhecido,

    -- Idade
    MIN(idade)            AS idade_min_dep,
    MAX(idade)            AS idade_max_dep,
    ROUND(AVG(idade), 1)  AS idade_media_dep
  FROM deps_contrato
  GROUP BY 1
)

-- ----------------------------------------------------------------------------
-- 5) JOIN final com anl_churn_contratos (universo do score) + churn target
-- ----------------------------------------------------------------------------
SELECT
  c.contract_id,

  -- Atributos do contrato/titular (já no score)
  CAST(c.plan_months_duration AS STRING) AS duracao,
  CASE WHEN c.account_contract_number = 1 THEN '1o' ELSE '2o+' END AS contrato,
  CASE
    WHEN c.titular_idade <= 20 THEN '00-20'
    WHEN c.titular_idade <= 30 THEN '21-30'
    WHEN c.titular_idade <= 50 THEN '31-50'
    WHEN c.titular_idade <= 70 THEN '51-70'
    ELSE '71+'
  END AS faixa_idade_titular,
  c.titular_main_cronico_sn AS cronico_titular,
  CASE WHEN c.order_source_aj = 'drc_digital' THEN 'digital' ELSE 'presencial_cfp' END AS canal,
  CASE
    WHEN IFNULL(c.titual_classe_social, '(sem dados)') IN ('A++','A+','B1','B2') THEN 'AB'
    ELSE 'CDE'
  END AS classe,

  -- Sanity check: agora deve bater (ou estar muito próximo de) qtd_dep_total
  c.dependents_per_holder AS dep_count_anl,

  -- ===== Núcleo: contagens =====
  IFNULL(n.qtd_dep_total, 0)                  AS qtd_dep_total,
  IFNULL(n.qtd_dep_ativos_drc, 0)             AS qtd_dep_ativos_drc,
  IFNULL(n.qtd_dep_passivos_drc, 0)           AS qtd_dep_passivos_drc,
  IFNULL(n.qtd_dep_idade_conhecida, 0)        AS qtd_dep_idade_conhecida,
  IFNULL(n.qtd_dep_idade_desconhecida, 0)     AS qtd_dep_idade_desconhecida,
  IFNULL(n.qtd_dep_jovens, 0)                 AS qtd_dep_jovens,
  IFNULL(n.qtd_dep_idosos, 0)                 AS qtd_dep_idosos,
  IFNULL(n.qtd_dep_adultos, 0)                AS qtd_dep_adultos,
  IFNULL(n.qtd_dep_financeiros, 0)            AS qtd_dep_financeiros,
  IFNULL(n.qtd_dep_cronicos_S, 0)             AS qtd_dep_cronicos_S,
  IFNULL(n.qtd_dep_cronicos_N_confirmado, 0)  AS qtd_dep_cronicos_N_confirmado,
  IFNULL(n.qtd_dep_cronicos_desconhecido, 0)  AS qtd_dep_cronicos_desconhecido,

  -- % de deps passivos DRC sobre o total de deps (NULL para 'solo')
  CASE
    WHEN IFNULL(n.qtd_dep_total, 0) = 0 THEN NULL
    ELSE ROUND(100.0 * n.qtd_dep_passivos_drc / n.qtd_dep_total, 1)
  END AS pct_deps_passivos,

  -- ===== Núcleo: flags S/N =====
  CASE WHEN IFNULL(n.qtd_dep_total, 0)        > 0 THEN 'S' ELSE 'N' END AS tem_dep,
  CASE WHEN IFNULL(n.qtd_dep_financeiros, 0)  > 0 THEN 'S' ELSE 'N' END AS tem_dep_financeiro,
  CASE WHEN IFNULL(n.qtd_dep_jovens, 0)       > 0 THEN 'S' ELSE 'N' END AS tem_dep_jovem,
  CASE WHEN IFNULL(n.qtd_dep_idosos, 0)       > 0 THEN 'S' ELSE 'N' END AS tem_dep_idoso,
  CASE WHEN IFNULL(n.qtd_dep_passivos_drc, 0) > 0 THEN 'S' ELSE 'N' END AS tem_dep_passivo,

  -- ===== Crônico do dep: 3 estados =====
  -- 'S'           = pelo menos 1 dep com diagnóstico crônico confirmado
  -- 'N'           = nenhum dep crônico, mas pelo menos 1 dep com atendimento
  -- 'desconhecido' = todos os deps são passivos DRC — sem informação clínica
  -- NULL          = solo (sem deps)
  CASE
    WHEN IFNULL(n.qtd_dep_total, 0) = 0           THEN NULL
    WHEN n.qtd_dep_cronicos_S > 0                 THEN 'S'
    WHEN n.qtd_dep_cronicos_N_confirmado > 0      THEN 'N'
    ELSE 'desconhecido'
  END AS tem_dep_cronico,

  -- ===== Composição DRC do núcleo (sempre definida) =====
  CASE
    WHEN IFNULL(n.qtd_dep_total, 0) = 0   THEN 'solo'
    WHEN n.qtd_dep_ativos_drc = 0         THEN 'so_passivos'
    WHEN n.qtd_dep_passivos_drc = 0       THEN 'so_ativos_drc'
    ELSE 'passivos_e_ativos'
  END AS composicao_drc,

  -- ===== Composição etária (apenas quando todos os deps têm idade conhecida) =====
  -- 'idade_parcial' = há ao menos 1 dep com idade desconhecida → não dá pra
  -- categorizar etariamente o núcleo todo. NULL = solo.
  CASE
    WHEN IFNULL(n.qtd_dep_total, 0) = 0       THEN NULL
    WHEN n.qtd_dep_idade_desconhecida > 0     THEN 'idade_parcial'
    WHEN n.qtd_dep_jovens > 0  AND n.qtd_dep_idosos = 0 AND n.qtd_dep_adultos = 0 THEN 'so_jovens'
    WHEN n.qtd_dep_idosos > 0  AND n.qtd_dep_jovens = 0 AND n.qtd_dep_adultos = 0 THEN 'so_idosos'
    WHEN n.qtd_dep_adultos > 0 AND n.qtd_dep_jovens = 0 AND n.qtd_dep_idosos = 0 THEN 'so_adultos'
    WHEN n.qtd_dep_jovens > 0  AND n.qtd_dep_idosos > 0 AND n.qtd_dep_adultos = 0 THEN 'jovens_e_idosos'
    WHEN n.qtd_dep_jovens > 0  AND n.qtd_dep_adultos > 0 AND n.qtd_dep_idosos = 0 THEN 'jovens_e_adultos'
    WHEN n.qtd_dep_idosos > 0  AND n.qtd_dep_adultos > 0 AND n.qtd_dep_jovens = 0 THEN 'idosos_e_adultos'
    ELSE 'multi_geracional'  -- jovens + idosos + adultos
  END AS composicao_etaria,

  -- Idades extremas (apenas para deps com idade conhecida; NULL se nenhum)
  n.idade_min_dep,
  n.idade_max_dep,
  n.idade_media_dep,

  -- ===== Target =====
  c.churn_renovacao_automatica_sn AS churn_sn,
  CASE WHEN c.churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END AS churner

FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` c
LEFT JOIN nucleo n ON n.contract_id = c.contract_id
WHERE c.plan_months_duration IN (6, 12)
  AND c.order_payment_method = 'credit_card'
  AND IFNULL(c.order_source_aj, '') != 'b2b'
  AND c.contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH);
