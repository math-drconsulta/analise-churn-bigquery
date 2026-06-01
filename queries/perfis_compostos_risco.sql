-- ============================================================================
-- QUERY CC-2: PERFIS COMPOSTOS DE RISCO — APENAS CREDIT_CARD
-- Base: anl_churn_contratos | Filtro: planos 6+12m + credit_card + sem B2B
--
-- Faixa etária split em 5 buckets: 00-20 (infantil/adolescente),
-- 21-30 (jovem adulto), 31-50, 51-70, 71+. O recorte separa o
-- comportamento infantil (plano pago pelos pais) do jovem adulto.
--
-- Removidas:
--   - consumo_sn: confounded com ciclo do contrato (1o contrato consome mais
--     e churn é alto, gerando falsa associação consumo→churn)
--
-- ----------------------------------------------------------------------------
-- ESTRUTURA DESTE ARQUIVO (4 blocos, cada um exporta para 1 CSV):
--
--   2A   →  results/perfis_compostos_risco_a.csv
--           5 variáveis: duração × contrato × dependentes × idade × crônico
--           Consumido por: pages/4_Perfis_Compostos.py
--
--   2A'  →  results/perfis_compostos_7vars.csv
--           7 variáveis (2A + canal + classe social)
--           Consumido por: pages/2_Risco_e_Evolucao.py (WLS do score)
--
--   2B   →  results/perfis_compostos_risco_b.csv
--           Top 30 maior/menor risco, ranqueado por Wilson 95% CI
--           Consumido por: pages/4_Perfis_Compostos.py (tab Extremos)
--
--   2C   →  results/perfis_compostos_risco_c.csv
--           5 variáveis, exclui unsubscription_sn = 'S' (churn silencioso)
--           Consumido por: pages/4_Perfis_Compostos.py (tab Silencioso)
-- ============================================================================


-- ============================================================================
-- 2A) CRUZAMENTO 5 VARIÁVEIS  →  perfis_compostos_risco_a.csv
-- ============================================================================

SELECT
  CAST(plan_months_duration AS STRING) as duracao,
  CASE WHEN account_contract_number = 1 THEN '1o' ELSE '2o+' END as contrato,
  CASE
    WHEN dependents_per_holder = 0 THEN 'sem_dep'
    WHEN dependents_per_holder IN (1, 2) THEN '1-2_dep'
    ELSE '3+_dep'
  END as dependentes,
  CASE
    WHEN titular_idade <= 20 THEN '00-20'
    WHEN titular_idade <= 30 THEN '21-30'
    WHEN titular_idade <= 50 THEN '31-50'
    WHEN titular_idade <= 70 THEN '51-70'
    ELSE '71+'
  END as faixa_idade,
  titular_main_cronico_sn as cronico,

  COUNT(*) as total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) as churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) as churn_rate

FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12)
  AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3, 4, 5
HAVING COUNT(*) >= 50
ORDER BY churn_rate DESC;


-- ============================================================================
-- 2A') CRUZAMENTO 8 VARIÁVEIS  →  perfis_compostos_7vars.csv
-- 7 variáveis demográficas/contratuais + consumo_sn (score dinâmico).
-- Substitui `dependentes` por `composicao_drc` (solo / so_passivos /
-- so_ativos_drc / passivos_e_ativos). Essa variável captura tanto a
-- presença de dependentes quanto o engajamento deles na DRC.
-- consumo_sn (S/N) indica se o titular usou o plano durante o contrato.
-- Esta é a base que alimenta o WLS do score em pages/2_Risco_e_Evolucao.py
-- ============================================================================

WITH

-- Identifica pacientes que já tiveram QUALQUER atendimento na DRC.
-- Se main_cronico_sn retorna resultado, o paciente é "ativo DRC"
-- (independente de ser crônico ou não). NULL = nunca atendido = passivo.
ate_cron AS (
  SELECT
    ated.id_paciente,
    IFNULL(MAX(cc.main_cronico_sn), 'N') AS main_cronico_sn
  FROM `airflow-datalake-prod.DRC_DW.bi_atendimentos` ated
  LEFT JOIN `airflow-datalake-prod.DRC.atendimentos_diagnosticos` ad
    ON ated.id_atendimento = ad.id_atendimento
  LEFT JOIN (
    SELECT *,
      CASE WHEN CID_Hipertensao_SN = 'S' OR CID_Diabetico_SN = 'S'
           OR CID_Dislipidemia_SN = 'S' THEN 'S' ELSE 'N'
      END AS main_cronico_sn
    FROM `airflow-datalake-prod.DePara_BI.DePara_Classificacao_CIDs_aj`
  ) cc ON ad.cid = cc.CID
  GROUP BY 1
),

-- Lista dependentes de cada contrato com status DRC.
-- DISTINCT por (contract_id, person_id) para deduplicar múltiplos payments.
-- main_cronico_sn IS NOT NULL → dep é "ativo DRC" (já teve atendimento).
-- main_cronico_sn IS NULL     → dep é "passivo DRC" (nunca atendido).
deps_contrato AS (
  SELECT DISTINCT
    s.contract_id,
    s.person_id,
    ac.main_cronico_sn
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` s
  LEFT JOIN ate_cron ac ON ac.id_paciente = s.id_paciente
  WHERE s.account_type != 'holder'
),

-- Classifica cada contrato pela composição DRC do seu núcleo familiar.
composicao AS (
  SELECT
    contract_id,
    CASE
      WHEN COUNT(*) = 0 THEN 'solo'
      WHEN COUNTIF(main_cronico_sn IS NOT NULL) = 0 THEN 'so_passivos'
      WHEN COUNTIF(main_cronico_sn IS NULL) = 0     THEN 'so_ativos_drc'
      ELSE 'passivos_e_ativos'
    END AS composicao_drc
  FROM deps_contrato
  GROUP BY 1
)

SELECT
  CAST(c.plan_months_duration AS STRING) as duracao,
  CASE WHEN c.account_contract_number = 1 THEN '1o' ELSE '2o+' END as contrato,
  IFNULL(comp.composicao_drc, 'solo') as composicao_drc,
  CASE
    WHEN c.titular_idade <= 20 THEN '00-20'
    WHEN c.titular_idade <= 30 THEN '21-30'
    WHEN c.titular_idade <= 50 THEN '31-50'
    WHEN c.titular_idade <= 70 THEN '51-70'
    ELSE '71+'
  END as faixa_idade,
  c.titular_main_cronico_sn as cronico,
  CASE
    WHEN c.order_source_aj = 'drc_digital' THEN 'digital'
    ELSE 'presencial_cfp'
  END as canal,
  CASE
    WHEN IFNULL(c.titual_classe_social, '(sem dados)') IN ('A++', 'A+', 'B1', 'B2') THEN 'AB'
    ELSE 'CDE'
  END as classe,
  IFNULL(c.consumo_sn, 'N') as consumo_sn,

  COUNT(*) as total_contratos,
  SUM(CASE WHEN c.churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) as churners,
  ROUND(100.0 * SUM(CASE WHEN c.churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) as churn_rate

FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` c
LEFT JOIN composicao comp ON comp.contract_id = c.contract_id
WHERE c.plan_months_duration IN (6, 12)
  AND c.order_payment_method = 'credit_card'
  AND IFNULL(c.order_source_aj, '') != 'b2b'
  AND c.contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
HAVING COUNT(*) >= 50
ORDER BY churn_rate DESC;


-- ============================================================================
-- 2A'') SCORE DE CHURN VOLUNTÁRIO  →  perfis_compostos_voluntario.csv
-- Mesmas 8 variáveis da 2A', mas contando APENAS churners que pediram
-- cancelamento ativo (unsubscription_sn = 'S').
-- Isso isola o churn por DECISÃO do paciente, removendo falhas de pagamento,
-- compras avulsas e erros técnicos.
-- ============================================================================

WITH

ate_cron AS (
  SELECT
    ated.id_paciente,
    IFNULL(MAX(cc.main_cronico_sn), 'N') AS main_cronico_sn
  FROM `airflow-datalake-prod.DRC_DW.bi_atendimentos` ated
  LEFT JOIN `airflow-datalake-prod.DRC.atendimentos_diagnosticos` ad
    ON ated.id_atendimento = ad.id_atendimento
  LEFT JOIN (
    SELECT *,
      CASE WHEN CID_Hipertensao_SN = 'S' OR CID_Diabetico_SN = 'S'
           OR CID_Dislipidemia_SN = 'S' THEN 'S' ELSE 'N'
      END AS main_cronico_sn
    FROM `airflow-datalake-prod.DePara_BI.DePara_Classificacao_CIDs_aj`
  ) cc ON ad.cid = cc.CID
  GROUP BY 1
),

deps_contrato AS (
  SELECT DISTINCT
    s.contract_id,
    s.person_id,
    ac.main_cronico_sn
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` s
  LEFT JOIN ate_cron ac ON ac.id_paciente = s.id_paciente
  WHERE s.account_type != 'holder'
),

composicao AS (
  SELECT
    contract_id,
    CASE
      WHEN COUNT(*) = 0 THEN 'solo'
      WHEN COUNTIF(main_cronico_sn IS NOT NULL) = 0 THEN 'so_passivos'
      WHEN COUNTIF(main_cronico_sn IS NULL) = 0     THEN 'so_ativos_drc'
      ELSE 'passivos_e_ativos'
    END AS composicao_drc
  FROM deps_contrato
  GROUP BY 1
)

SELECT
  CAST(c.plan_months_duration AS STRING) as duracao,
  CASE WHEN c.account_contract_number = 1 THEN '1o' ELSE '2o+' END as contrato,
  IFNULL(comp.composicao_drc, 'solo') as composicao_drc,
  CASE
    WHEN c.titular_idade <= 20 THEN '00-20'
    WHEN c.titular_idade <= 30 THEN '21-30'
    WHEN c.titular_idade <= 50 THEN '31-50'
    WHEN c.titular_idade <= 70 THEN '51-70'
    ELSE '71+'
  END as faixa_idade,
  c.titular_main_cronico_sn as cronico,
  CASE
    WHEN c.order_source_aj = 'drc_digital' THEN 'digital'
    ELSE 'presencial_cfp'
  END as canal,
  CASE
    WHEN IFNULL(c.titual_classe_social, '(sem dados)') IN ('A++', 'A+', 'B1', 'B2') THEN 'AB'
    ELSE 'CDE'
  END as classe,
  IFNULL(c.consumo_sn, 'N') as consumo_sn,

  COUNT(*) as total_contratos,
  SUM(CASE WHEN c.unsubscription_sn = 'S' THEN 1 ELSE 0 END) as churners_voluntarios,
  ROUND(100.0 * SUM(CASE WHEN c.unsubscription_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) as churn_voluntario_rate,
  -- Também incluir churn total para comparação
  SUM(CASE WHEN c.churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) as churners_total,
  ROUND(100.0 * SUM(CASE WHEN c.churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) as churn_total_rate

FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` c
LEFT JOIN composicao comp ON comp.contract_id = c.contract_id
WHERE c.plan_months_duration IN (6, 12)
  AND c.order_payment_method = 'credit_card'
  AND IFNULL(c.order_source_aj, '') != 'b2b'
  AND c.contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
HAVING COUNT(*) >= 50
ORDER BY churn_voluntario_rate DESC;


-- ============================================================================
-- 2B) TOP 30 MAIOR E MENOR RISCO  →  perfis_compostos_risco_b.csv
--
-- Ranking por Wilson 95% CI (não pelo ponto estimado de churn_rate):
--   ALTO_RISCO  → ordenado por wilson_lo DESC. Pega perfis com churn alto
--                 cuja banda inferior do IC ainda é alta — evita selecionar
--                 perfis pequenos com churn extremo só por acaso amostral.
--   BAIXO_RISCO → ordenado por wilson_hi ASC. Mesma lógica invertida —
--                 perfis com churn baixo confirmadamente baixo.
--
-- Wilson 95%: lo, hi = ((x + 1.9208) ± 1.96 * sqrt(x(n-x)/n + 0.9604)) / (n + 3.8416)
-- Estrutura de 5 variáveis (igual a 2A) + perfil concatenado + métricas extras.
-- ============================================================================

WITH perfis AS (
  SELECT
    CONCAT(
      CAST(plan_months_duration AS STRING), 'm|',
      CASE WHEN account_contract_number = 1 THEN '1o' ELSE '2o+' END, '|',
      CASE WHEN dependents_per_holder = 0 THEN 'sem_dep' WHEN dependents_per_holder IN (1,2) THEN '1-2dep' ELSE '3+dep' END, '|',
      CASE
        WHEN titular_idade <= 20 THEN '00-20'
        WHEN titular_idade <= 30 THEN '21-30'
        WHEN titular_idade <= 50 THEN '31-50'
        WHEN titular_idade <= 70 THEN '51-70'
        ELSE '71+'
      END, '|',
      'cron=', titular_main_cronico_sn
    ) as perfil,

    CAST(plan_months_duration AS STRING) as duracao,
    CASE WHEN account_contract_number = 1 THEN '1o' ELSE '2o+' END as contrato,
    CASE WHEN dependents_per_holder = 0 THEN 'sem_dep' WHEN dependents_per_holder IN (1,2) THEN '1-2dep' ELSE '3+dep' END as dependentes,
    CASE
      WHEN titular_idade <= 20 THEN '00-20'
      WHEN titular_idade <= 30 THEN '21-30'
      WHEN titular_idade <= 50 THEN '31-50'
      WHEN titular_idade <= 70 THEN '51-70'
      ELSE '71+'
    END as faixa_idade,
    titular_main_cronico_sn as cronico,

    COUNT(*) as total_contratos,
    SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) as churners,
    ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) as churn_rate,

    -- Métricas extras de consumo (informativas, não usadas no agrupamento)
    ROUND(AVG(IFNULL(qtd_TOTAL_CM, 0)), 1) as media_consultas,
    ROUND(AVG(IFNULL(qtd_TOTAL_EXAMES, 0)), 1) as media_exames

  FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
  WHERE plan_months_duration IN (6, 12)
    AND order_payment_method = 'credit_card'
    AND IFNULL(order_source_aj, '') != 'b2b'
    AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
  GROUP BY 1, 2, 3, 4, 5, 6
  HAVING COUNT(*) >= 100
),

wilson AS (
  SELECT
    *,
    ROUND(100 * SAFE_DIVIDE(
      (churners + 1.9208) - 1.96 * SQRT(SAFE_DIVIDE(churners * (total_contratos - churners), total_contratos) + 0.9604),
      total_contratos + 3.8416
    ), 1) as wilson_lo,
    ROUND(100 * SAFE_DIVIDE(
      (churners + 1.9208) + 1.96 * SQRT(SAFE_DIVIDE(churners * (total_contratos - churners), total_contratos) + 0.9604),
      total_contratos + 3.8416
    ), 1) as wilson_hi
  FROM perfis
)

(SELECT 'ALTO_RISCO' as categoria, * FROM wilson ORDER BY wilson_lo DESC LIMIT 30)
UNION ALL
(SELECT 'BAIXO_RISCO' as categoria, * FROM wilson ORDER BY wilson_hi ASC LIMIT 30);


-- ============================================================================
-- 2C) PERFIS COM UNSUBSCRIPTION EXCLUÍDO  →  perfis_compostos_risco_c.csv
-- Remove quem pediu cancelamento para focar no churn sem aviso (silencioso).
-- 5 variáveis (mesma estrutura de 2A).
-- ============================================================================

SELECT
  CAST(plan_months_duration AS STRING) as duracao,
  CASE WHEN account_contract_number = 1 THEN '1o' ELSE '2o+' END as contrato,
  CASE
    WHEN dependents_per_holder = 0 THEN 'sem_dep'
    WHEN dependents_per_holder IN (1, 2) THEN '1-2_dep'
    ELSE '3+_dep'
  END as dependentes,
  CASE
    WHEN titular_idade <= 20 THEN '00-20'
    WHEN titular_idade <= 30 THEN '21-30'
    WHEN titular_idade <= 50 THEN '31-50'
    WHEN titular_idade <= 70 THEN '51-70'
    ELSE '71+'
  END as faixa_idade,
  titular_main_cronico_sn as cronico,

  COUNT(*) as total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) as churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) as churn_rate

FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12)
  AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
  AND unsubscription_sn = 'N'  -- exclui quem pediu cancelamento
GROUP BY 1, 2, 3, 4, 5
HAVING COUNT(*) >= 50
ORDER BY churn_rate DESC;
