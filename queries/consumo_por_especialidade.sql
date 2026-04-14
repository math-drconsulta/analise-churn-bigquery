-- ============================================================================
-- QUERY CC-3: CONSUMO POR ESPECIALIDADE E VOLUME — APENAS CREDIT_CARD
-- Base: anl_churn_contratos | Filtro: planos 6+12m + credit_card
-- ============================================================================

-- 3A) CHURN POR ESPECIALIDADE UTILIZADA (usou vs não usou cada uma)
SELECT 'CM_presencial' as especialidade, CASE WHEN IFNULL(qtd_TOTAL_CM, 0) > 0 THEN 'usou' ELSE 'nao_usou' END as uso,
  COUNT(*) as total, SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) as churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) as churn_rate
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` WHERE plan_months_duration IN (6,12) AND order_payment_method = 'credit_card'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH) GROUP BY 1, 2
UNION ALL
SELECT 'CM_TELE', CASE WHEN IFNULL(qtd_TOTAL_CM_TELE, 0) > 0 THEN 'usou' ELSE 'nao_usou' END,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` WHERE plan_months_duration IN (6,12) AND order_payment_method = 'credit_card'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH) GROUP BY 1, 2
UNION ALL
SELECT 'EXAMES', CASE WHEN IFNULL(qtd_TOTAL_EXAMES, 0) > 0 THEN 'usou' ELSE 'nao_usou' END,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` WHERE plan_months_duration IN (6,12) AND order_payment_method = 'credit_card'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH) GROUP BY 1, 2
UNION ALL
SELECT 'CLINICA_MEDICA', CASE WHEN IFNULL(qtd_TOTAL_CM_CLINICA_MEDICA, 0) > 0 THEN 'usou' ELSE 'nao_usou' END,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` WHERE plan_months_duration IN (6,12) AND order_payment_method = 'credit_card'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH) GROUP BY 1, 2
UNION ALL
SELECT 'GINECOLOGIA', CASE WHEN IFNULL(qtd_TOTAL_CM_GINECOLOGIA, 0) > 0 THEN 'usou' ELSE 'nao_usou' END,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` WHERE plan_months_duration IN (6,12) AND order_payment_method = 'credit_card'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH) GROUP BY 1, 2
UNION ALL
SELECT 'CARDIOLOGISTA', CASE WHEN IFNULL(qtd_TOTAL_CM_CARDIOLOGISTA, 0) > 0 THEN 'usou' ELSE 'nao_usou' END,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` WHERE plan_months_duration IN (6,12) AND order_payment_method = 'credit_card'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH) GROUP BY 1, 2
UNION ALL
SELECT 'DERMATOLOGISTA', CASE WHEN IFNULL(qtd_TOTAL_CM_DERMATOLOGISTA, 0) > 0 THEN 'usou' ELSE 'nao_usou' END,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` WHERE plan_months_duration IN (6,12) AND order_payment_method = 'credit_card'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH) GROUP BY 1, 2
UNION ALL
SELECT 'ENDOCRINOLOGISTA', CASE WHEN IFNULL(qtd_TOTAL_CM_ENDOCRINOLOGISTA, 0) > 0 THEN 'usou' ELSE 'nao_usou' END,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` WHERE plan_months_duration IN (6,12) AND order_payment_method = 'credit_card'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH) GROUP BY 1, 2
UNION ALL
SELECT 'PSIQUIATRIA', CASE WHEN IFNULL(qtd_TOTAL_CM_PSIQUIATRIA, 0) > 0 THEN 'usou' ELSE 'nao_usou' END,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` WHERE plan_months_duration IN (6,12) AND order_payment_method = 'credit_card'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH) GROUP BY 1, 2
UNION ALL
SELECT 'ORTOPEDISTA', CASE WHEN IFNULL(qtd_TOTAL_CM_ORTOPEDISTA, 0) > 0 THEN 'usou' ELSE 'nao_usou' END,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` WHERE plan_months_duration IN (6,12) AND order_payment_method = 'credit_card'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH) GROUP BY 1, 2
UNION ALL
SELECT 'PEDIATRA', CASE WHEN IFNULL(qtd_TOTAL_CM_PEDIATRA, 0) > 0 THEN 'usou' ELSE 'nao_usou' END,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` WHERE plan_months_duration IN (6,12) AND order_payment_method = 'credit_card'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH) GROUP BY 1, 2
UNION ALL
SELECT 'OFTALMOLOGISTA', CASE WHEN IFNULL(qtd_TOTAL_CM_OFTALMOLOGISTA, 0) > 0 THEN 'usou' ELSE 'nao_usou' END,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` WHERE plan_months_duration IN (6,12) AND order_payment_method = 'credit_card'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH) GROUP BY 1, 2
UNION ALL
SELECT 'GASTROENTEROLOGISTA', CASE WHEN IFNULL(qtd_TOTAL_CM_GASTROENTEROLOGISTA, 0) > 0 THEN 'usou' ELSE 'nao_usou' END,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` WHERE plan_months_duration IN (6,12) AND order_payment_method = 'credit_card'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH) GROUP BY 1, 2
UNION ALL
SELECT 'NEUROLOGIA', CASE WHEN IFNULL(qtd_TOTAL_CM_NEUROLOGIA, 0) > 0 THEN 'usou' ELSE 'nao_usou' END,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` WHERE plan_months_duration IN (6,12) AND order_payment_method = 'credit_card'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH) GROUP BY 1, 2
UNION ALL
SELECT 'OTORRINOLARINGOLOGISTA', CASE WHEN IFNULL(qtd_TOTAL_CM_OTORRINOLARINGOLOGISTA, 0) > 0 THEN 'usou' ELSE 'nao_usou' END,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` WHERE plan_months_duration IN (6,12) AND order_payment_method = 'credit_card'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH) GROUP BY 1, 2
UNION ALL
SELECT 'UROLOGISTA', CASE WHEN IFNULL(qtd_TOTAL_CM_UROLOGISTA, 0) > 0 THEN 'usou' ELSE 'nao_usou' END,
  COUNT(*), SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END),
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1)
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` WHERE plan_months_duration IN (6,12) AND order_payment_method = 'credit_card'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH) GROUP BY 1, 2

ORDER BY especialidade, uso;


-- ============================================================================
-- 3B) PERFIL DE VOLUME DE CONSUMO × CHURN
-- ============================================================================

SELECT
  CASE
    WHEN IFNULL(consumo_sn, 'N') = 'N' THEN 'A_sem_consumo'
    WHEN IFNULL(qtd_TOTAL_CM, 0) + IFNULL(qtd_TOTAL_EXAMES, 0) + IFNULL(qtd_TOTAL_CM_TELE, 0) <= 3 THEN 'B_baixo (1-3)'
    WHEN IFNULL(qtd_TOTAL_CM, 0) + IFNULL(qtd_TOTAL_EXAMES, 0) + IFNULL(qtd_TOTAL_CM_TELE, 0) <= 8 THEN 'C_medio (4-8)'
    WHEN IFNULL(qtd_TOTAL_CM, 0) + IFNULL(qtd_TOTAL_EXAMES, 0) + IFNULL(qtd_TOTAL_CM_TELE, 0) <= 15 THEN 'D_alto (9-15)'
    ELSE 'E_muito_alto (16+)'
  END as faixa_consumo,

  COUNT(*) as total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) as churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) as churn_rate,

  ROUND(AVG(IFNULL(qtd_TOTAL_CM, 0) + IFNULL(qtd_TOTAL_EXAMES, 0) + IFNULL(qtd_TOTAL_CM_TELE, 0)), 1) as media_itens,

  -- Diversidade de especialidades usadas
  ROUND(AVG(
    (CASE WHEN IFNULL(qtd_TOTAL_CM_CLINICA_MEDICA, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_CM_GINECOLOGIA, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_CM_CARDIOLOGISTA, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_CM_DERMATOLOGISTA, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_CM_ENDOCRINOLOGISTA, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_CM_PSIQUIATRIA, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_CM_ORTOPEDISTA, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_CM_PEDIATRA, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_CM_OFTALMOLOGISTA, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_CM_TELE, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_EXAMES, 0) > 0 THEN 1 ELSE 0 END)
  ), 1) as media_diversidade_servicos

FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12)
  AND order_payment_method = 'credit_card'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1
ORDER BY 1;


-- ============================================================================
-- 3C) DIVERSIDADE DE ESPECIALIDADES × CHURN
-- Quantas especialidades diferentes o paciente usou → impacto no churn
-- ============================================================================

SELECT
  diversidade_servicos,
  COUNT(*) as total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) as churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) as churn_rate
FROM (
  SELECT
    contract_id,
    churn_renovacao_automatica_sn,
    (CASE WHEN IFNULL(qtd_TOTAL_CM_CLINICA_MEDICA, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_CM_GINECOLOGIA, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_CM_CARDIOLOGISTA, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_CM_DERMATOLOGISTA, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_CM_ENDOCRINOLOGISTA, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_CM_GASTROENTEROLOGISTA, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_CM_NEUROLOGIA, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_CM_PSIQUIATRIA, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_CM_ORTOPEDISTA, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_CM_PEDIATRA, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_CM_OFTALMOLOGISTA, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_CM_OTORRINOLARINGOLOGISTA, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_CM_UROLOGISTA, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_CM_TELE, 0) > 0 THEN 1 ELSE 0 END) +
    (CASE WHEN IFNULL(qtd_TOTAL_EXAMES, 0) > 0 THEN 1 ELSE 0 END)
    as diversidade_servicos
  FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
  WHERE plan_months_duration IN (6, 12)
    AND order_payment_method = 'credit_card'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
)
GROUP BY 1
ORDER BY 1;