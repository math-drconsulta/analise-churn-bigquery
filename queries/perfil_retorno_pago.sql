-- ============================================================================
-- PERFIL DOS 18% QUE VOLTAM PRO PAGO APOS GRATIS
--
-- Entender quem sao, pra que plano voltam, se churnaram de novo,
-- quanto tempo ficaram no gratis, e se mudaram metodo de pagamento.
--
-- Rode cada BLOCO separadamente. Saidas sugeridas:
--   BLOCO 1 → results/retorno_pago_perfil.csv
--   BLOCO 2 → results/retorno_pago_plano.csv
--   BLOCO 3 → results/retorno_pago_rechurn.csv
--   BLOCO 4 → results/retorno_pago_timing.csv
--   BLOCO 5 → results/retorno_pago_metodo_pgto.csv
-- ============================================================================


-- ============================================================================
-- CTE BASE: churners que migraram pro gratis e depois voltaram pro pago
-- (reutilizada em todos os blocos)
-- ============================================================================

-- BLOCO 1: Perfil demografico — quem volta vs quem sai apos gratis
-- ============================================================================
WITH contratos_pagos AS (
  SELECT
    ys.contract_id,
    ys.account_id,
    ys.person_id,
    ys.holder_person_id,
    ys.id_paciente,
    ys.contract_due_date,
    ys.account_due_date,
    ys.plan_name AS plano_original,
    ys.plan_months_duration AS duracao_original,
    ys.payment_method AS metodo_original,
    ys.account_contract_number AS ciclo_original,
    ys.holder_birth_date,
    ys.total_accounts_dependents AS dependentes,
    ys.canal
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 18 MONTH)
    AND ys.contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) <= 7
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),

-- Proximo contrato gratis
proximo_gratis AS (
  SELECT
    cp.contract_id AS contrato_churn_id,
    cp.holder_person_id,
    cp.id_paciente,
    cp.contract_due_date AS data_churn,
    cp.plano_original,
    cp.duracao_original,
    cp.metodo_original,
    cp.ciclo_original,
    cp.holder_birth_date,
    cp.dependentes,
    cp.canal,
    ng.contract_id AS contrato_gratis_id,
    ng.contract_register_date AS gratis_inicio,
    ng.contract_due_date AS gratis_fim,
    ng.plan_name AS plano_gratis,
    DATE_DIFF(ng.contract_register_date, cp.contract_due_date, DAY) AS dias_ate_gratis
  FROM contratos_pagos cp
  JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ng
    ON ng.holder_person_id = cp.holder_person_id
    AND ng.contract_register_date > cp.contract_due_date
    AND ng.contract_register_date <= DATE_ADD(cp.contract_due_date, INTERVAL 60 DAY)
    AND LOWER(ng.plan_name) LIKE '%gratis%'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ng.contract_id ORDER BY ng.date_month DESC
  ) = 1
  AND ROW_NUMBER() OVER (
    PARTITION BY cp.contract_id ORDER BY ng.contract_register_date
  ) = 1
),

-- Contrato pos-gratis (pago ou nao)
pos_gratis AS (
  SELECT
    pg.*,
    pp.contract_id AS contrato_pos_id,
    pp.plan_name AS plano_pos,
    pp.plan_months_duration AS duracao_pos,
    pp.payment_method AS metodo_pos,
    pp.contract_register_date AS pos_inicio,
    pp.contract_due_date AS pos_fim,
    pp.account_due_date AS pos_account_due,
    DATE_DIFF(pp.contract_register_date, pg.gratis_fim, DAY) AS dias_gratis_ate_pago,
    DATE_DIFF(pg.gratis_fim, pg.gratis_inicio, DAY) AS dias_no_gratis,
    CASE
      WHEN pp.contract_id IS NOT NULL AND LOWER(pp.plan_name) NOT LIKE '%gratis%' THEN 'voltou_pago'
      ELSE 'saiu_de_vez'
    END AS desfecho
  FROM proximo_gratis pg
  LEFT JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` pp
    ON pp.holder_person_id = pg.holder_person_id
    AND pp.contract_register_date > pg.gratis_inicio
    AND pp.contract_register_date <= DATE_ADD(pg.gratis_fim, INTERVAL 90 DAY)
    AND LOWER(pp.plan_name) NOT LIKE '%gratis%'
    AND pp.account_type = 'holder'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY pp.contract_id ORDER BY pp.date_month DESC
  ) = 1
  AND ROW_NUMBER() OVER (
    PARTITION BY pg.contrato_churn_id ORDER BY pp.contract_register_date
  ) = 1
)

-- RESULTADO BLOCO 1: perfil demografico
SELECT
  desfecho,
  COUNT(*) AS contratos,
  -- Idade (calculada a partir de birth_date)
  ROUND(AVG(DATE_DIFF(CURRENT_DATE(), CAST(holder_birth_date AS DATE), YEAR)), 1) AS media_idade,
  -- Dependentes
  ROUND(AVG(IFNULL(dependentes, 0)), 1) AS media_dependentes,
  COUNTIF(IFNULL(dependentes, 0) = 0) AS sem_dependentes,
  ROUND(100.0 * COUNTIF(IFNULL(dependentes, 0) = 0) / COUNT(*), 1) AS pct_sem_dep,
  -- Duracao original
  COUNTIF(duracao_original = 6) AS plano_6m,
  ROUND(100.0 * COUNTIF(duracao_original = 6) / COUNT(*), 1) AS pct_6m,
  COUNTIF(duracao_original = 12) AS plano_12m,
  ROUND(100.0 * COUNTIF(duracao_original = 12) / COUNT(*), 1) AS pct_12m,
  -- Ciclo
  COUNTIF(ciclo_original = 1) AS primeiro_contrato,
  ROUND(100.0 * COUNTIF(ciclo_original = 1) / COUNT(*), 1) AS pct_1o_contrato,
  -- Canal
  COUNTIF(LOWER(IFNULL(canal, '')) LIKE '%digital%') AS canal_digital,
  ROUND(100.0 * COUNTIF(LOWER(IFNULL(canal, '')) LIKE '%digital%') / COUNT(*), 1) AS pct_digital,
  -- Timing
  ROUND(AVG(dias_no_gratis), 1) AS media_dias_no_gratis,
  ROUND(AVG(dias_ate_gratis), 1) AS media_dias_ate_gratis
FROM pos_gratis
GROUP BY desfecho
ORDER BY desfecho;


-- ============================================================================
-- BLOCO 2: Pra que plano voltam? Mesmo ou diferente?
-- ============================================================================
WITH contratos_pagos AS (
  SELECT ys.contract_id, ys.holder_person_id, ys.id_paciente,
    ys.contract_due_date, ys.account_due_date,
    ys.plan_name AS plano_original, ys.plan_months_duration AS duracao_original,
    ys.payment_method AS metodo_original
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder' AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12) AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 18 MONTH)
    AND ys.contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) <= 7
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ys.contract_id ORDER BY ys.date_month DESC) = 1
),
proximo_gratis AS (
  SELECT cp.contract_id AS contrato_churn_id, cp.holder_person_id,
    cp.plano_original, cp.duracao_original, cp.metodo_original,
    ng.contract_register_date AS gratis_inicio, ng.contract_due_date AS gratis_fim
  FROM contratos_pagos cp
  JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ng
    ON ng.holder_person_id = cp.holder_person_id
    AND ng.contract_register_date > cp.contract_due_date
    AND ng.contract_register_date <= DATE_ADD(cp.contract_due_date, INTERVAL 60 DAY)
    AND LOWER(ng.plan_name) LIKE '%gratis%'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ng.contract_id ORDER BY ng.date_month DESC) = 1
  AND ROW_NUMBER() OVER (PARTITION BY cp.contract_id ORDER BY ng.contract_register_date) = 1
),
voltaram_pago AS (
  SELECT pg.*, pp.plan_name AS plano_pos, pp.plan_months_duration AS duracao_pos,
    pp.payment_method AS metodo_pos
  FROM proximo_gratis pg
  JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` pp
    ON pp.holder_person_id = pg.holder_person_id
    AND pp.contract_register_date > pg.gratis_inicio
    AND pp.contract_register_date <= DATE_ADD(pg.gratis_fim, INTERVAL 90 DAY)
    AND LOWER(pp.plan_name) NOT LIKE '%gratis%'
    AND pp.account_type = 'holder'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY pp.contract_id ORDER BY pp.date_month DESC) = 1
  AND ROW_NUMBER() OVER (PARTITION BY pg.contrato_churn_id ORDER BY pp.contract_register_date) = 1
)

SELECT
  plano_original,
  duracao_original,
  plano_pos,
  duracao_pos,
  CASE WHEN plano_original = plano_pos THEN 'mesmo_plano' ELSE 'plano_diferente' END AS mudou_plano,
  CASE WHEN duracao_original = duracao_pos THEN 'mesma_duracao' ELSE 'duracao_diferente' END AS mudou_duracao,
  COUNT(*) AS contratos
FROM voltaram_pago
GROUP BY 1, 2, 3, 4, 5, 6
ORDER BY contratos DESC
LIMIT 30;


-- ============================================================================
-- BLOCO 3: Quem voltou pro pago churnou de novo?
-- ============================================================================
WITH contratos_pagos AS (
  SELECT ys.contract_id, ys.holder_person_id, ys.contract_due_date, ys.account_due_date
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder' AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12) AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 18 MONTH)
    AND ys.contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) <= 7
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ys.contract_id ORDER BY ys.date_month DESC) = 1
),
proximo_gratis AS (
  SELECT cp.contract_id AS contrato_churn_id, cp.holder_person_id,
    cp.contract_due_date AS data_churn,
    ng.contract_register_date AS gratis_inicio, ng.contract_due_date AS gratis_fim
  FROM contratos_pagos cp
  JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ng
    ON ng.holder_person_id = cp.holder_person_id
    AND ng.contract_register_date > cp.contract_due_date
    AND ng.contract_register_date <= DATE_ADD(cp.contract_due_date, INTERVAL 60 DAY)
    AND LOWER(ng.plan_name) LIKE '%gratis%'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ng.contract_id ORDER BY ng.date_month DESC) = 1
  AND ROW_NUMBER() OVER (PARTITION BY cp.contract_id ORDER BY ng.contract_register_date) = 1
),
voltaram_pago AS (
  SELECT pg.contrato_churn_id, pg.holder_person_id, pg.data_churn,
    pp.contract_id AS contrato_retorno_id,
    pp.contract_due_date AS retorno_due_date,
    pp.account_due_date AS retorno_account_due,
    DATE_DIFF(pp.account_due_date, pp.contract_due_date, DAY) AS dias_extensao_retorno
  FROM proximo_gratis pg
  JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` pp
    ON pp.holder_person_id = pg.holder_person_id
    AND pp.contract_register_date > pg.gratis_inicio
    AND pp.contract_register_date <= DATE_ADD(pg.gratis_fim, INTERVAL 90 DAY)
    AND LOWER(pp.plan_name) NOT LIKE '%gratis%'
    AND pp.account_type = 'holder'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY pp.contract_id ORDER BY pp.date_month DESC) = 1
  AND ROW_NUMBER() OVER (PARTITION BY pg.contrato_churn_id ORDER BY pp.contract_register_date) = 1
)

SELECT
  CASE
    WHEN CAST(retorno_due_date AS DATE) > CURRENT_DATE() THEN 'contrato_ainda_vigente'
    WHEN dias_extensao_retorno > 7 THEN 'renovou_novamente'
    ELSE 'churnou_de_novo'
  END AS desfecho_retorno,
  COUNT(*) AS contratos,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) AS pct
FROM voltaram_pago
GROUP BY desfecho_retorno
ORDER BY contratos DESC;


-- ============================================================================
-- BLOCO 4: Timing — quanto tempo no gratis antes de voltar
-- ============================================================================
WITH contratos_pagos AS (
  SELECT ys.contract_id, ys.holder_person_id, ys.contract_due_date, ys.account_due_date
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder' AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12) AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 18 MONTH)
    AND ys.contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) <= 7
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ys.contract_id ORDER BY ys.date_month DESC) = 1
),
proximo_gratis AS (
  SELECT cp.contract_id AS contrato_churn_id, cp.holder_person_id,
    ng.contract_register_date AS gratis_inicio, ng.contract_due_date AS gratis_fim
  FROM contratos_pagos cp
  JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ng
    ON ng.holder_person_id = cp.holder_person_id
    AND ng.contract_register_date > cp.contract_due_date
    AND ng.contract_register_date <= DATE_ADD(cp.contract_due_date, INTERVAL 60 DAY)
    AND LOWER(ng.plan_name) LIKE '%gratis%'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ng.contract_id ORDER BY ng.date_month DESC) = 1
  AND ROW_NUMBER() OVER (PARTITION BY cp.contract_id ORDER BY ng.contract_register_date) = 1
),
voltaram_pago AS (
  SELECT pg.*,
    pp.contract_register_date AS retorno_inicio,
    DATE_DIFF(pp.contract_register_date, pg.gratis_inicio, DAY) AS dias_no_gratis_ate_retorno
  FROM proximo_gratis pg
  JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` pp
    ON pp.holder_person_id = pg.holder_person_id
    AND pp.contract_register_date > pg.gratis_inicio
    AND pp.contract_register_date <= DATE_ADD(pg.gratis_fim, INTERVAL 90 DAY)
    AND LOWER(pp.plan_name) NOT LIKE '%gratis%'
    AND pp.account_type = 'holder'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY pp.contract_id ORDER BY pp.date_month DESC) = 1
  AND ROW_NUMBER() OVER (PARTITION BY pg.contrato_churn_id ORDER BY pp.contract_register_date) = 1
)

SELECT
  CASE
    WHEN dias_no_gratis_ate_retorno <= 7 THEN '01_ate_7d'
    WHEN dias_no_gratis_ate_retorno <= 14 THEN '02_8-14d'
    WHEN dias_no_gratis_ate_retorno <= 21 THEN '03_15-21d'
    WHEN dias_no_gratis_ate_retorno <= 30 THEN '04_22-30d'
    WHEN dias_no_gratis_ate_retorno <= 45 THEN '05_31-45d'
    WHEN dias_no_gratis_ate_retorno <= 60 THEN '06_46-60d'
    WHEN dias_no_gratis_ate_retorno <= 90 THEN '07_61-90d'
    ELSE '08_90d+'
  END AS faixa_dias_no_gratis,
  COUNT(*) AS contratos,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) AS pct,
  ROUND(AVG(dias_no_gratis_ate_retorno), 1) AS media_dias
FROM voltaram_pago
GROUP BY faixa_dias_no_gratis
ORDER BY faixa_dias_no_gratis;


-- ============================================================================
-- BLOCO 5: Mudaram metodo de pagamento ao voltar?
-- ============================================================================
WITH contratos_pagos AS (
  SELECT ys.contract_id, ys.holder_person_id, ys.contract_due_date, ys.account_due_date,
    ys.payment_method AS metodo_original
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder' AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12) AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 18 MONTH)
    AND ys.contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) <= 7
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ys.contract_id ORDER BY ys.date_month DESC) = 1
),
proximo_gratis AS (
  SELECT cp.contract_id AS contrato_churn_id, cp.holder_person_id,
    cp.metodo_original,
    ng.contract_register_date AS gratis_inicio, ng.contract_due_date AS gratis_fim
  FROM contratos_pagos cp
  JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ng
    ON ng.holder_person_id = cp.holder_person_id
    AND ng.contract_register_date > cp.contract_due_date
    AND ng.contract_register_date <= DATE_ADD(cp.contract_due_date, INTERVAL 60 DAY)
    AND LOWER(ng.plan_name) LIKE '%gratis%'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ng.contract_id ORDER BY ng.date_month DESC) = 1
  AND ROW_NUMBER() OVER (PARTITION BY cp.contract_id ORDER BY ng.contract_register_date) = 1
),
voltaram_pago AS (
  SELECT pg.*,
    pp.payment_method AS metodo_retorno
  FROM proximo_gratis pg
  JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` pp
    ON pp.holder_person_id = pg.holder_person_id
    AND pp.contract_register_date > pg.gratis_inicio
    AND pp.contract_register_date <= DATE_ADD(pg.gratis_fim, INTERVAL 90 DAY)
    AND LOWER(pp.plan_name) NOT LIKE '%gratis%'
    AND pp.account_type = 'holder'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY pp.contract_id ORDER BY pp.date_month DESC) = 1
  AND ROW_NUMBER() OVER (PARTITION BY pg.contrato_churn_id ORDER BY pp.contract_register_date) = 1
)

SELECT
  metodo_original,
  metodo_retorno,
  CASE WHEN metodo_original = metodo_retorno THEN 'mesmo_metodo' ELSE 'mudou_metodo' END AS mudou,
  COUNT(*) AS contratos,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) AS pct
FROM voltaram_pago
GROUP BY 1, 2, 3
ORDER BY contratos DESC;
