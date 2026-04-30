-- ============================================================================
-- DEMANDAS DA ÁREA DE NEGÓCIOS — Abril 2026
-- 4 perguntas que precisam de queries novas ou ajustadas
-- ============================================================================


-- ============================================================================
-- DEMANDA 1: DOS 1300 DO DISPARO DE EMAIL, QUANTOS SÃO ANUAIS E SEMESTRAIS?
--
-- RESOLVIDO: A query conversao_apos_falha_pgto.sql agora inclui uma CTE
-- `contrato_original` que busca o último contrato ANTES do disparo.
-- Colunas adicionadas no CSV: duracao_plano_original, plano_original.
-- Não é mais necessário rodar query separada para esta demanda.
-- ============================================================================


-- ============================================================================
-- DEMANDA 2: CANAL SEM B2B — REVER ANÁLISE DE CANAIS
-- Arquivo: results/univariada_canal_sem_b2b.csv
--
-- A análise atual inclui B2B (2.192 contratos, 45,3% churn).
-- B2B distorce a distribuição porque tem comportamento diferente
-- (contratos corporativos, regras diferentes de renovação).
-- ============================================================================

SELECT
  'order_source' AS dimensao,
  IFNULL(order_source_aj, '(vazio)') AS segmento,
  COUNT(*) AS total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_rate
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12)
  AND order_payment_method = 'credit_card'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
  AND IFNULL(order_source_aj, '') != 'b2b'  -- EXCLUIR B2B
GROUP BY 1, 2
ORDER BY churn_rate DESC;


-- ============================================================================
-- DEMANDA 3: ESPECIALIDADES — IDAS PONTUAIS VS RECORRENTES
-- Arquivo: results/especialidade_pontual_vs_recorrente.csv
--
-- A ideia é separar cada especialidade em:
-- - Pontual: paciente usou 1 vez
-- - Recorrente: paciente usou 2+ vezes
-- E ver se o churn muda entre esses dois comportamentos.
-- ============================================================================

SELECT
  especialidade,
  tipo_uso,
  COUNT(*) AS total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_rate
FROM (
  SELECT
    contract_id,
    churn_renovacao_automatica_sn,
    -- CM Presencial
    CASE
      WHEN IFNULL(qtd_TOTAL_CM, 0) = 0 THEN 'nao_usou'
      WHEN qtd_TOTAL_CM = 1 THEN 'pontual'
      ELSE 'recorrente'
    END AS tipo_cm_presencial,
    -- CM Tele
    CASE
      WHEN IFNULL(qtd_TOTAL_CM_TELE, 0) = 0 THEN 'nao_usou'
      WHEN qtd_TOTAL_CM_TELE = 1 THEN 'pontual'
      ELSE 'recorrente'
    END AS tipo_cm_tele,
    -- Exames
    CASE
      WHEN IFNULL(qtd_TOTAL_EXAMES, 0) = 0 THEN 'nao_usou'
      WHEN qtd_TOTAL_EXAMES = 1 THEN 'pontual'
      ELSE 'recorrente'
    END AS tipo_exames,
    -- Clínica Médica
    CASE
      WHEN IFNULL(qtd_TOTAL_CM_CLINICA_MEDICA, 0) = 0 THEN 'nao_usou'
      WHEN qtd_TOTAL_CM_CLINICA_MEDICA = 1 THEN 'pontual'
      ELSE 'recorrente'
    END AS tipo_clinica_medica,
    -- Ginecologia
    CASE
      WHEN IFNULL(qtd_TOTAL_CM_GINECOLOGIA, 0) = 0 THEN 'nao_usou'
      WHEN qtd_TOTAL_CM_GINECOLOGIA = 1 THEN 'pontual'
      ELSE 'recorrente'
    END AS tipo_ginecologia,
    -- Psiquiatria
    CASE
      WHEN IFNULL(qtd_TOTAL_CM_PSIQUIATRIA, 0) = 0 THEN 'nao_usou'
      WHEN qtd_TOTAL_CM_PSIQUIATRIA = 1 THEN 'pontual'
      ELSE 'recorrente'
    END AS tipo_psiquiatria,
    -- Dermatologista
    CASE
      WHEN IFNULL(qtd_TOTAL_CM_DERMATOLOGISTA, 0) = 0 THEN 'nao_usou'
      WHEN qtd_TOTAL_CM_DERMATOLOGISTA = 1 THEN 'pontual'
      ELSE 'recorrente'
    END AS tipo_dermatologista,
    -- Cardiologista
    CASE
      WHEN IFNULL(qtd_TOTAL_CM_CARDIOLOGISTA, 0) = 0 THEN 'nao_usou'
      WHEN qtd_TOTAL_CM_CARDIOLOGISTA = 1 THEN 'pontual'
      ELSE 'recorrente'
    END AS tipo_cardiologista,
    -- Endocrinologista
    CASE
      WHEN IFNULL(qtd_TOTAL_CM_ENDOCRINOLOGISTA, 0) = 0 THEN 'nao_usou'
      WHEN qtd_TOTAL_CM_ENDOCRINOLOGISTA = 1 THEN 'pontual'
      ELSE 'recorrente'
    END AS tipo_endocrinologista,
    -- Ortopedista
    CASE
      WHEN IFNULL(qtd_TOTAL_CM_ORTOPEDISTA, 0) = 0 THEN 'nao_usou'
      WHEN qtd_TOTAL_CM_ORTOPEDISTA = 1 THEN 'pontual'
      ELSE 'recorrente'
    END AS tipo_ortopedista,
    -- Pediatra
    CASE
      WHEN IFNULL(qtd_TOTAL_CM_PEDIATRA, 0) = 0 THEN 'nao_usou'
      WHEN qtd_TOTAL_CM_PEDIATRA = 1 THEN 'pontual'
      ELSE 'recorrente'
    END AS tipo_pediatra
  FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
  WHERE plan_months_duration IN (6, 12)
    AND order_payment_method = 'credit_card'
    AND IFNULL(order_source_aj, '') != 'b2b'
    AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
)
UNPIVOT (
  tipo_uso FOR especialidade IN (
    tipo_cm_presencial AS 'CM_presencial',
    tipo_cm_tele AS 'CM_TELE',
    tipo_exames AS 'EXAMES',
    tipo_clinica_medica AS 'CLINICA_MEDICA',
    tipo_ginecologia AS 'GINECOLOGIA',
    tipo_psiquiatria AS 'PSIQUIATRIA',
    tipo_dermatologista AS 'DERMATOLOGISTA',
    tipo_cardiologista AS 'CARDIOLOGISTA',
    tipo_endocrinologista AS 'ENDOCRINOLOGISTA',
    tipo_ortopedista AS 'ORTOPEDISTA',
    tipo_pediatra AS 'PEDIATRA'
  )
)
WHERE tipo_uso != 'nao_usou'  -- só quem usou pelo menos 1 vez
GROUP BY 1, 2
ORDER BY especialidade, tipo_uso;


-- ============================================================================
-- DEMANDA 4: RENOVAÇÃO AUTOMÁTICA POR GRUPO DE CONSUMO
-- Arquivo: results/renovacao_por_consumo.csv
--
-- Quantos pacientes EFETIVAMENTE renovaram (churn_renovacao_automatica_sn = 'N')
-- dentro de cada faixa de consumo? Focando em quem paga com cartão de crédito.
--
-- A pergunta é: "quem paga com cartão e de fato renovou?"
-- ============================================================================

SELECT
  CASE
    WHEN IFNULL(consumo_sn, 'N') = 'N' THEN 'A_sem_consumo'
    WHEN IFNULL(qtd_TOTAL_CM, 0) + IFNULL(qtd_TOTAL_EXAMES, 0) + IFNULL(qtd_TOTAL_CM_TELE, 0) <= 3 THEN 'B_baixo (1-3)'
    WHEN IFNULL(qtd_TOTAL_CM, 0) + IFNULL(qtd_TOTAL_EXAMES, 0) + IFNULL(qtd_TOTAL_CM_TELE, 0) <= 8 THEN 'C_medio (4-8)'
    WHEN IFNULL(qtd_TOTAL_CM, 0) + IFNULL(qtd_TOTAL_EXAMES, 0) + IFNULL(qtd_TOTAL_CM_TELE, 0) <= 15 THEN 'D_alto (9-15)'
    ELSE 'E_muito_alto (16+)'
  END AS faixa_consumo,

  COUNT(*) AS total_contratos,

  -- Quem renovou (NÃO deu churn)
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'N' THEN 1 ELSE 0 END) AS renovaram,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'N' THEN 1 ELSE 0 END) / COUNT(*), 1) AS taxa_renovacao_pct,

  -- Quem deu churn
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_rate,

  -- Duração do plano
  SUM(CASE WHEN plan_months_duration = 6 AND churn_renovacao_automatica_sn = 'N' THEN 1 ELSE 0 END) AS renovaram_6m,
  SUM(CASE WHEN plan_months_duration = 12 AND churn_renovacao_automatica_sn = 'N' THEN 1 ELSE 0 END) AS renovaram_12m,

  -- Média de itens usados entre os que renovaram vs churners
  ROUND(AVG(CASE WHEN churn_renovacao_automatica_sn = 'N'
    THEN IFNULL(qtd_TOTAL_CM, 0) + IFNULL(qtd_TOTAL_EXAMES, 0) + IFNULL(qtd_TOTAL_CM_TELE, 0) END), 1) AS media_itens_renovados,
  ROUND(AVG(CASE WHEN churn_renovacao_automatica_sn = 'S'
    THEN IFNULL(qtd_TOTAL_CM, 0) + IFNULL(qtd_TOTAL_EXAMES, 0) + IFNULL(qtd_TOTAL_CM_TELE, 0) END), 1) AS media_itens_churners

FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12)
  AND order_payment_method = 'credit_card'  -- SÓ CARTÃO DE CRÉDITO
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1
ORDER BY 1;
