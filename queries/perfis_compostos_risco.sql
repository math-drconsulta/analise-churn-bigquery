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
-- 2A') CRUZAMENTO 7 VARIÁVEIS  →  perfis_compostos_7vars.csv
-- Adiciona canal (digital vs presencial/cfp) e classe social colapsada (AB vs CDE)
-- Esta é a base que alimenta o WLS do score em pages/2_Risco_e_Evolucao.py
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
  CASE
    WHEN order_source_aj = 'drc_digital' THEN 'digital'
    ELSE 'presencial_cfp'
  END as canal,
  CASE
    WHEN IFNULL(titual_classe_social, '(sem dados)') IN ('A++', 'A+', 'B1', 'B2') THEN 'AB'
    ELSE 'CDE'
  END as classe,

  COUNT(*) as total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) as churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) as churn_rate

FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12)
  AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3, 4, 5, 6, 7
HAVING COUNT(*) >= 50
ORDER BY churn_rate DESC;


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
