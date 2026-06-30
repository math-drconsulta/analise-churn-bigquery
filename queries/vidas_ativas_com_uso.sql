-- ============================================================================
-- VIDAS ATIVAS COM USO
--
-- Definicao da empresa: ativo = contrato vigente + usou a rede ao menos 1x
-- durante a vigencia do contrato.
--
-- Rode cada BLOCO separadamente. Saidas sugeridas:
--   BLOCO 1 → results/vidas_ativas_uso_resumo.csv
--   BLOCO 2 → results/vidas_ativas_uso_por_plano.csv
--   BLOCO 3 → results/vidas_ativas_uso_intensidade.csv
-- ============================================================================


-- ============================================================================
-- BLOCO 1: Contratos ativos — com uso vs sem uso
-- ============================================================================
WITH contratos_ativos AS (
  SELECT
    ys.contract_id,
    ys.account_id,
    ys.person_id,
    ys.holder_person_id,
    ys.account_type,
    ys.plan_name,
    ys.plan_months_duration,
    ys.payment_method,
    ys.contract_register_date,
    ys.account_due_date,
    CASE WHEN LOWER(ys.plan_name) LIKE '%gratis%' THEN 'gratis' ELSE 'pago' END AS tipo_plano
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE CAST(ys.account_due_date AS DATE) >= CURRENT_DATE()
    AND CAST(ys.contract_register_date AS DATE) <= CURRENT_DATE()
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),

uso AS (
  SELECT
    ca.contract_id,
    COUNT(DISTINCT ri.id_item) AS total_itens,
    COUNT(DISTINCT DATE(ri.data)) AS dias_com_uso,
    COUNTIF(ri.produto_grupo = 'CM') AS consultas,
    COUNTIF(ri.produto_grupo = 'EXAMES') AS exames
  FROM contratos_ativos ca
  JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_itens` yi
    ON yi.person_id = ca.person_id
  JOIN `airflow-datalake-prod.DRC_DW.bi_recepcao_itens` ri
    ON ri.id_item = yi.id_item
    AND ri.data >= CAST(ca.contract_register_date AS DATE)
    AND ri.data <= CAST(ca.account_due_date AS DATE)
  GROUP BY ca.contract_id
)

SELECT
  ca.account_type,
  ca.tipo_plano,
  COUNT(DISTINCT ca.contract_id) AS contratos_vigentes,
  COUNT(DISTINCT ca.person_id) AS pessoas_vigentes,
  COUNT(DISTINCT u.contract_id) AS contratos_com_uso,
  COUNT(DISTINCT CASE WHEN u.contract_id IS NOT NULL THEN ca.person_id END) AS pessoas_com_uso,
  ROUND(100.0 * COUNT(DISTINCT CASE WHEN u.contract_id IS NOT NULL THEN ca.person_id END)
    / NULLIF(COUNT(DISTINCT ca.person_id), 0), 1) AS pct_com_uso,
  COUNT(DISTINCT ca.person_id)
    - COUNT(DISTINCT CASE WHEN u.contract_id IS NOT NULL THEN ca.person_id END) AS pessoas_sem_uso,
  ROUND(100.0 * (COUNT(DISTINCT ca.person_id)
    - COUNT(DISTINCT CASE WHEN u.contract_id IS NOT NULL THEN ca.person_id END))
    / NULLIF(COUNT(DISTINCT ca.person_id), 0), 1) AS pct_sem_uso
FROM contratos_ativos ca
LEFT JOIN uso u ON u.contract_id = ca.contract_id
GROUP BY ca.account_type, ca.tipo_plano
ORDER BY pessoas_vigentes DESC;


-- ============================================================================
-- BLOCO 2: Por tipo de plano e metodo de pagamento
-- ============================================================================
WITH contratos_ativos AS (
  SELECT
    ys.contract_id,
    ys.account_id,
    ys.person_id,
    ys.account_type,
    ys.plan_name,
    ys.plan_months_duration,
    ys.payment_method,
    ys.contract_register_date,
    ys.account_due_date,
    CASE WHEN LOWER(ys.plan_name) LIKE '%gratis%' THEN 'gratis' ELSE 'pago' END AS tipo_plano
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE CAST(ys.account_due_date AS DATE) >= CURRENT_DATE()
    AND CAST(ys.contract_register_date AS DATE) <= CURRENT_DATE()
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),

uso AS (
  SELECT
    ca.contract_id,
    COUNT(DISTINCT ri.id_item) AS total_itens
  FROM contratos_ativos ca
  JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_itens` yi
    ON yi.person_id = ca.person_id
  JOIN `airflow-datalake-prod.DRC_DW.bi_recepcao_itens` ri
    ON ri.id_item = yi.id_item
    AND ri.data >= CAST(ca.contract_register_date AS DATE)
    AND ri.data <= CAST(ca.account_due_date AS DATE)
  GROUP BY ca.contract_id
)

SELECT
  ca.account_type,
  ca.tipo_plano,
  ca.payment_method,
  ca.plan_months_duration,
  COUNT(DISTINCT ca.person_id) AS pessoas_vigentes,
  COUNT(DISTINCT CASE WHEN u.contract_id IS NOT NULL THEN ca.person_id END) AS pessoas_com_uso,
  ROUND(100.0 * COUNT(DISTINCT CASE WHEN u.contract_id IS NOT NULL THEN ca.person_id END)
    / NULLIF(COUNT(DISTINCT ca.person_id), 0), 1) AS pct_com_uso
FROM contratos_ativos ca
LEFT JOIN uso u ON u.contract_id = ca.contract_id
GROUP BY 1, 2, 3, 4
HAVING pessoas_vigentes >= 50
ORDER BY pessoas_vigentes DESC;


-- ============================================================================
-- BLOCO 3: Intensidade de uso (quem usou — quantas vezes)
-- ============================================================================
WITH contratos_ativos AS (
  SELECT
    ys.contract_id,
    ys.person_id,
    ys.account_type,
    ys.contract_register_date,
    ys.account_due_date
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE CAST(ys.account_due_date AS DATE) >= CURRENT_DATE()
    AND CAST(ys.contract_register_date AS DATE) <= CURRENT_DATE()
    AND LOWER(ys.plan_name) NOT LIKE '%gratis%'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),

uso AS (
  SELECT
    ca.contract_id,
    ca.account_type,
    COUNT(DISTINCT ri.id_item) AS total_itens,
    COUNT(DISTINCT DATE(ri.data)) AS dias_com_uso
  FROM contratos_ativos ca
  JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_itens` yi
    ON yi.person_id = ca.person_id
  JOIN `airflow-datalake-prod.DRC_DW.bi_recepcao_itens` ri
    ON ri.id_item = yi.id_item
    AND ri.data >= CAST(ca.contract_register_date AS DATE)
    AND ri.data <= CAST(ca.account_due_date AS DATE)
  GROUP BY ca.contract_id, ca.account_type
)

SELECT
  account_type,
  CASE
    WHEN total_itens = 0 THEN '0_sem_uso'
    WHEN total_itens = 1 THEN '1_uso'
    WHEN total_itens BETWEEN 2 AND 3 THEN '2-3_usos'
    WHEN total_itens BETWEEN 4 AND 6 THEN '4-6_usos'
    WHEN total_itens BETWEEN 7 AND 12 THEN '7-12_usos'
    ELSE '13+_usos'
  END AS faixa_uso,
  COUNT(*) AS contratos,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(PARTITION BY account_type), 1) AS pct,
  ROUND(AVG(dias_com_uso), 1) AS media_dias_com_uso
FROM uso
GROUP BY account_type, faixa_uso
ORDER BY account_type, faixa_uso;
