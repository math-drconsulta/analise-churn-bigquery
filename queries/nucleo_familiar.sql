-- ============================================================================
-- QUERY: NUCLEO FAMILIAR — features dos dependentes por contrato (v4)
-- Output: results/nucleo_familiar.csv  (1 linha por contrato)
-- Consumido por: pages/7_Nucleo_Familiar.py
--
-- Mudanças vs v3
-- --------------
-- v4 endereça as 2 limitações expostas pelo audit (queries/audit_dep_count.sql,
-- maio/2026):
--
--   (1) IDADE DOS DEPS — agora vem de ref_yalo_subscriptions.people_birth_date
--       (com fallback pra vw_yalo_vidas.birth_date). v3 usava
--       DRC.pacientes_audit.dt_nasc, que não cobre id_paciente de dependente
--       (cobertura ~0%). people_birth_date está direto na tabela base e tem
--       cobertura ampla, destravando os buckets etários e a definição de
--       dependente financeiro (<21 ou >60).
--
--   (2) LEAKAGE EM dep_count_anl — anl_churn_contratos.dependents_per_holder
--       diverge de qtd_dep_total recalculado em ~5% dos contratos, e nesses
--       contratos o churn é ~0% (correlacionado com contract_churn_status =
--       'renewal'). É campo declarativo do contrato, contaminado pelo
--       desfecho. v4 marca a coluna dep_count_anl no output como ⚠️ leaky
--       (mantém pro consumo da pg 7 não quebrar, mas com aviso). Features
--       derivadas — composicao_drc, qtd_dep_*, etc — usam só qtd_dep_total
--       recalculado (sem leakage).
--
-- Mudanças vs v2
-- --------------
-- v3 adicionou MIX DE ESPECIALIDADES dos dependentes (consumo separado do
-- titular). Motivação: o score atual e a página do núcleo só sabem se o dep
-- é "ativo/passivo/crônico" — não sabem O QUE ele consumiu.
--
-- Path para extrair especialidade do dep:
--   ref_yalo_subscriptions (y, account_type='dependent')
--     → ref_yalo_itens (yi, JOIN em payment_id + person_id) → id_item
--     → bi_recepcao_itens (r, JOIN em id_item) → executante_especialidade
--
-- Janela temporal: atendimentos com
--   date_diff(r.data, y.account_register_date, month) < y.plan_months_duration
--
-- Taxonomia (idêntica à consumo_por_especialidade.sql):
--   produto_grupo='CM' AND unidade != 'TELE'  → 13 especialidades presenciais
--   produto_grupo='CM' AND unidade  = 'TELE'  → CM_TELE
--   produto_grupo='EXAMES'                    → EXAMES
--   demais executante_especialidade em CM      → CM_OUTROS (catch-all)
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
-- 1) Idade por paciente (v4): people_birth_date direto de
--    ref_yalo_subscriptions, com fallback pra vw_yalo_vidas.birth_date para
--    cobertura adicional. NULL só se ambas as fontes forem NULL.
--    Agregação por id_paciente: MAX da data (caso uma pessoa apareça com
--    múltiplas datas — pega a mais recente cadastrada).
-- ----------------------------------------------------------------------------
pac AS (
  WITH bd_subs AS (
    SELECT id_paciente, MAX(people_birth_date) AS bd
    FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions`
    WHERE id_paciente IS NOT NULL AND people_birth_date IS NOT NULL
    GROUP BY 1
  ),
  bd_vidas AS (
    SELECT id_paciente, MAX(birth_date) AS bd
    FROM `airflow-datalake-prod.YALO_DW.vw_yalo_vidas`
    WHERE id_paciente IS NOT NULL AND birth_date IS NOT NULL
    GROUP BY 1
  )
  SELECT
    COALESCE(s.id_paciente, v.id_paciente) AS id_paciente,
    DATE_DIFF(CURRENT_DATE(), COALESCE(s.bd, v.bd), YEAR) AS idade
  FROM bd_subs s
  FULL OUTER JOIN bd_vidas v USING (id_paciente)
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
),

-- ----------------------------------------------------------------------------
-- 4b) Itens consumidos por dependentes — granularidade (contract_id, item).
--     Usa o mesmo path da query original yalo_contratos.sql, mas filtrando
--     account_type = 'dependent' e a janela do plano.
--     Categoriza cada item em uma única "especialidade_norm" para evitar
--     dupla contagem na agregação por contrato.
-- ----------------------------------------------------------------------------
dep_itens AS (
  SELECT
    y.contract_id,
    y.person_id,
    yi.id_item,
    -- Categoria normalizada (mesma taxonomia de consumo_por_especialidade.sql)
    CASE
      WHEN r.produto_grupo = 'EXAMES'                                            THEN 'EXAMES'
      WHEN r.produto_grupo = 'CM' AND r.unidade = 'TELE'                          THEN 'CM_TELE'
      WHEN r.produto_grupo = 'CM' AND r.executante_especialidade = 'CLINICA MEDICA'        THEN 'CM_CLINICA_MEDICA'
      WHEN r.produto_grupo = 'CM' AND r.executante_especialidade = 'GINECOLOGISTA'         THEN 'CM_GINECOLOGIA'
      WHEN r.produto_grupo = 'CM' AND r.executante_especialidade = 'CARDIOLOGISTA'         THEN 'CM_CARDIOLOGISTA'
      WHEN r.produto_grupo = 'CM' AND r.executante_especialidade = 'DERMATOLOGISTA'        THEN 'CM_DERMATOLOGISTA'
      WHEN r.produto_grupo = 'CM' AND r.executante_especialidade = 'ENDOCRINOLOGISTA'      THEN 'CM_ENDOCRINOLOGISTA'
      WHEN r.produto_grupo = 'CM' AND r.executante_especialidade = 'GASTROENTEROLOGISTA'   THEN 'CM_GASTROENTEROLOGISTA'
      WHEN r.produto_grupo = 'CM' AND r.executante_especialidade = 'NEUROLOGIA'            THEN 'CM_NEUROLOGIA'
      WHEN r.produto_grupo = 'CM' AND r.executante_especialidade = 'OFTALMOLOGISTA'        THEN 'CM_OFTALMOLOGISTA'
      WHEN r.produto_grupo = 'CM' AND r.executante_especialidade = 'ORTOPEDISTA'           THEN 'CM_ORTOPEDISTA'
      WHEN r.produto_grupo = 'CM' AND r.executante_especialidade = 'OTORRINOLARINGOLOGISTA' THEN 'CM_OTORRINOLARINGOLOGISTA'
      WHEN r.produto_grupo = 'CM' AND r.executante_especialidade = 'PEDIATRA'              THEN 'CM_PEDIATRA'
      WHEN r.produto_grupo = 'CM' AND r.executante_especialidade = 'PSIQUIATRIA'           THEN 'CM_PSIQUIATRIA'
      WHEN r.produto_grupo = 'CM' AND r.executante_especialidade = 'UROLOGISTA'            THEN 'CM_UROLOGISTA'
      WHEN r.produto_grupo = 'CM'                                                  THEN 'CM_OUTROS'
      ELSE NULL  -- ignora itens sem produto_grupo casável
    END AS especialidade_norm
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` y
  INNER JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_itens` yi
    ON yi.payment_id = y.payment_id AND yi.person_id = y.person_id
  LEFT JOIN `airflow-datalake-prod.DRC_DW.bi_recepcao_itens` r
    ON r.id_item = yi.id_item
  WHERE y.account_type = 'dependent'
    AND r.id_item IS NOT NULL
    AND DATE_DIFF(r.data, y.account_register_date, MONTH) < y.plan_months_duration
),

dep_consumo AS (
  SELECT
    contract_id,

    -- Volume agregado
    COUNT(DISTINCT id_item)                        AS qtd_total_itens_dep,
    COUNT(DISTINCT especialidade_norm)             AS qtd_especialidades_dep_distintas,
    COUNT(DISTINCT IF(especialidade_norm IS NOT NULL, person_id, NULL)) AS qtd_dep_consumiu,

    -- Itens por especialidade (16 colunas)
    COUNT(DISTINCT IF(especialidade_norm = 'CM_CLINICA_MEDICA',        id_item, NULL)) AS qtd_itens_dep_CM_CLINICA_MEDICA,
    COUNT(DISTINCT IF(especialidade_norm = 'CM_GINECOLOGIA',           id_item, NULL)) AS qtd_itens_dep_CM_GINECOLOGIA,
    COUNT(DISTINCT IF(especialidade_norm = 'CM_CARDIOLOGISTA',         id_item, NULL)) AS qtd_itens_dep_CM_CARDIOLOGISTA,
    COUNT(DISTINCT IF(especialidade_norm = 'CM_DERMATOLOGISTA',        id_item, NULL)) AS qtd_itens_dep_CM_DERMATOLOGISTA,
    COUNT(DISTINCT IF(especialidade_norm = 'CM_ENDOCRINOLOGISTA',      id_item, NULL)) AS qtd_itens_dep_CM_ENDOCRINOLOGISTA,
    COUNT(DISTINCT IF(especialidade_norm = 'CM_GASTROENTEROLOGISTA',   id_item, NULL)) AS qtd_itens_dep_CM_GASTROENTEROLOGISTA,
    COUNT(DISTINCT IF(especialidade_norm = 'CM_NEUROLOGIA',            id_item, NULL)) AS qtd_itens_dep_CM_NEUROLOGIA,
    COUNT(DISTINCT IF(especialidade_norm = 'CM_OFTALMOLOGISTA',        id_item, NULL)) AS qtd_itens_dep_CM_OFTALMOLOGISTA,
    COUNT(DISTINCT IF(especialidade_norm = 'CM_ORTOPEDISTA',           id_item, NULL)) AS qtd_itens_dep_CM_ORTOPEDISTA,
    COUNT(DISTINCT IF(especialidade_norm = 'CM_OTORRINOLARINGOLOGISTA', id_item, NULL)) AS qtd_itens_dep_CM_OTORRINOLARINGOLOGISTA,
    COUNT(DISTINCT IF(especialidade_norm = 'CM_PEDIATRA',              id_item, NULL)) AS qtd_itens_dep_CM_PEDIATRA,
    COUNT(DISTINCT IF(especialidade_norm = 'CM_PSIQUIATRIA',           id_item, NULL)) AS qtd_itens_dep_CM_PSIQUIATRIA,
    COUNT(DISTINCT IF(especialidade_norm = 'CM_UROLOGISTA',            id_item, NULL)) AS qtd_itens_dep_CM_UROLOGISTA,
    COUNT(DISTINCT IF(especialidade_norm = 'CM_OUTROS',                id_item, NULL)) AS qtd_itens_dep_CM_OUTROS,
    COUNT(DISTINCT IF(especialidade_norm = 'CM_TELE',                  id_item, NULL)) AS qtd_itens_dep_CM_TELE,
    COUNT(DISTINCT IF(especialidade_norm = 'EXAMES',                   id_item, NULL)) AS qtd_itens_dep_EXAMES
  FROM dep_itens
  GROUP BY 1
),

-- Especialidade onde os deps mais consumiram (top-1 por volume de itens).
-- Empate: ordem alfabética (determinístico).
dep_principal AS (
  SELECT
    contract_id,
    especialidade_norm AS especialidade_principal_dep,
    itens AS qtd_itens_principal_dep
  FROM (
    SELECT
      contract_id,
      especialidade_norm,
      COUNT(DISTINCT id_item) AS itens,
      ROW_NUMBER() OVER (
        PARTITION BY contract_id
        ORDER BY COUNT(DISTINCT id_item) DESC, especialidade_norm
      ) AS rn
    FROM dep_itens
    WHERE especialidade_norm IS NOT NULL
    GROUP BY 1, 2
  )
  WHERE rn = 1
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

  -- ⚠️ LEAKY: anl_churn_contratos.dependents_per_holder está contaminado.
  -- Quando dep_count_anl > qtd_dep_total (~5% da base), churn=0% — correlacionado
  -- com contract_churn_status='renewal' (snapshot pós-decisão). Mantido só
  -- pro sanity check da pg 7. NÃO USAR como feature do score. Use qtd_dep_total.
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

  -- ===== Consumo do dep — agregados =====
  IFNULL(dc.qtd_total_itens_dep, 0)              AS qtd_total_itens_dep,
  IFNULL(dc.qtd_especialidades_dep_distintas, 0) AS qtd_especialidades_dep_distintas,
  IFNULL(dc.qtd_dep_consumiu, 0)                 AS qtd_dep_consumiu,
  dp.especialidade_principal_dep,                                          -- NULL se nenhum dep consumiu
  IFNULL(dp.qtd_itens_principal_dep, 0)          AS qtd_itens_principal_dep,

  -- ===== Consumo do dep — itens por especialidade (16 colunas) =====
  IFNULL(dc.qtd_itens_dep_CM_CLINICA_MEDICA, 0)        AS qtd_itens_dep_CM_CLINICA_MEDICA,
  IFNULL(dc.qtd_itens_dep_CM_GINECOLOGIA, 0)           AS qtd_itens_dep_CM_GINECOLOGIA,
  IFNULL(dc.qtd_itens_dep_CM_CARDIOLOGISTA, 0)         AS qtd_itens_dep_CM_CARDIOLOGISTA,
  IFNULL(dc.qtd_itens_dep_CM_DERMATOLOGISTA, 0)        AS qtd_itens_dep_CM_DERMATOLOGISTA,
  IFNULL(dc.qtd_itens_dep_CM_ENDOCRINOLOGISTA, 0)      AS qtd_itens_dep_CM_ENDOCRINOLOGISTA,
  IFNULL(dc.qtd_itens_dep_CM_GASTROENTEROLOGISTA, 0)   AS qtd_itens_dep_CM_GASTROENTEROLOGISTA,
  IFNULL(dc.qtd_itens_dep_CM_NEUROLOGIA, 0)            AS qtd_itens_dep_CM_NEUROLOGIA,
  IFNULL(dc.qtd_itens_dep_CM_OFTALMOLOGISTA, 0)        AS qtd_itens_dep_CM_OFTALMOLOGISTA,
  IFNULL(dc.qtd_itens_dep_CM_ORTOPEDISTA, 0)           AS qtd_itens_dep_CM_ORTOPEDISTA,
  IFNULL(dc.qtd_itens_dep_CM_OTORRINOLARINGOLOGISTA, 0) AS qtd_itens_dep_CM_OTORRINOLARINGOLOGISTA,
  IFNULL(dc.qtd_itens_dep_CM_PEDIATRA, 0)              AS qtd_itens_dep_CM_PEDIATRA,
  IFNULL(dc.qtd_itens_dep_CM_PSIQUIATRIA, 0)           AS qtd_itens_dep_CM_PSIQUIATRIA,
  IFNULL(dc.qtd_itens_dep_CM_UROLOGISTA, 0)            AS qtd_itens_dep_CM_UROLOGISTA,
  IFNULL(dc.qtd_itens_dep_CM_OUTROS, 0)                AS qtd_itens_dep_CM_OUTROS,
  IFNULL(dc.qtd_itens_dep_CM_TELE, 0)                  AS qtd_itens_dep_CM_TELE,
  IFNULL(dc.qtd_itens_dep_EXAMES, 0)                   AS qtd_itens_dep_EXAMES,

  -- ===== Target =====
  c.churn_renovacao_automatica_sn AS churn_sn,
  CASE WHEN c.churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END AS churner

FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` c
LEFT JOIN nucleo        n  ON n.contract_id  = c.contract_id
LEFT JOIN dep_consumo   dc ON dc.contract_id = c.contract_id
LEFT JOIN dep_principal dp ON dp.contract_id = c.contract_id
WHERE c.plan_months_duration IN (6, 12)
  AND c.order_payment_method = 'credit_card'
  AND IFNULL(c.order_source_aj, '') != 'b2b'
  AND c.contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH);
