-- ============================================================================
-- DEBUG: entender o volume real de vidas
--
-- Rode cada BLOCO separadamente. Saidas sugeridas:
--   BLOCO 1 → results/vidas_debug_total.csv
--   BLOCO 2 → results/vidas_debug_filtros.csv
--   BLOCO 3 → results/vidas_debug_public_accounts.csv
-- ============================================================================


-- ============================================================================
-- BLOCO 1: Contagem SEM nenhum filtro (ref_yalo_subscriptions)
-- Snapshot mais recente de cada contrato
-- ============================================================================
WITH snapshot AS (
  SELECT *
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions`
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY contract_id ORDER BY date_month DESC
  ) = 1
)
SELECT
  'total_sem_filtro' AS metrica,
  COUNT(DISTINCT contract_id) AS contratos,
  COUNT(DISTINCT person_id) AS pessoas,
  COUNT(DISTINCT account_id) AS accounts
FROM snapshot

UNION ALL

-- Com filtro de ativo (account_due_date >= hoje)
SELECT
  'account_due_date_futuro' AS metrica,
  COUNT(DISTINCT contract_id),
  COUNT(DISTINCT person_id),
  COUNT(DISTINCT account_id)
FROM snapshot
WHERE CAST(account_due_date AS DATE) >= CURRENT_DATE()

UNION ALL

-- Com filtro de ativo + registrado
SELECT
  'futuro_e_registrado' AS metrica,
  COUNT(DISTINCT contract_id),
  COUNT(DISTINCT person_id),
  COUNT(DISTINCT account_id)
FROM snapshot
WHERE CAST(account_due_date AS DATE) >= CURRENT_DATE()
  AND CAST(contract_register_date AS DATE) <= CURRENT_DATE()

UNION ALL

-- Somente account_due_date no ultimo mes (pode incluir vencendo agora)
SELECT
  'due_date_ultimo_mes' AS metrica,
  COUNT(DISTINCT contract_id),
  COUNT(DISTINCT person_id),
  COUNT(DISTINCT account_id)
FROM snapshot
WHERE CAST(account_due_date AS DATE) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY);


-- ============================================================================
-- BLOCO 2: Impacto de cada filtro isoladamente
-- ============================================================================
WITH snapshot AS (
  SELECT *
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions`
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY contract_id ORDER BY date_month DESC
  ) = 1
)
SELECT
  account_type,
  CASE WHEN LOWER(plan_name) LIKE '%gratis%' THEN 'gratis' ELSE 'pago' END AS tipo_plano,
  CASE
    WHEN CAST(account_due_date AS DATE) >= CURRENT_DATE() THEN 'ativo'
    WHEN CAST(account_due_date AS DATE) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY) THEN 'venceu_ultimo_mes'
    WHEN CAST(account_due_date AS DATE) >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY) THEN 'venceu_3m'
    ELSE 'inativo'
  END AS status_conta,
  COUNT(DISTINCT contract_id) AS contratos,
  COUNT(DISTINCT person_id) AS pessoas
FROM snapshot
GROUP BY 1, 2, 3
ORDER BY pessoas DESC;


-- ============================================================================
-- BLOCO 3: Tentar via public_accounts (pode ter universo maior)
-- ============================================================================
SELECT
  COUNT(DISTINCT id) AS total_accounts,
  COUNT(DISTINCT person_id) AS total_pessoas
FROM `airflow-datalake-prod.yalo.public_accounts`;
