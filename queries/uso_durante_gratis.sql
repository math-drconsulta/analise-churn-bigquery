-- ============================================================================
-- USO DA REDE DURANTE O PLANO GRATIS
--
-- Objetivo: entender se os 30% que migram pro gratis usam a rede
-- (consultas, exames, tele) durante o periodo gratis, e se o uso
-- diferencia quem volta pro pago (18%) de quem sai de vez (82%).
--
-- Rode cada BLOCO separadamente. Saidas sugeridas em results/:
--   BLOCO 1 → results/gratis_uso_resumo.csv
--   BLOCO 2 → results/gratis_uso_por_desfecho.csv
--   BLOCO 3 → results/gratis_uso_especialidades.csv
--   BLOCO 4 → results/gratis_uso_timeline.csv
-- ============================================================================


-- ============================================================================
-- CTE BASE: churners que migraram pro gratis + periodo no gratis + desfecho
-- (reutilizada em todos os blocos)
-- ============================================================================
-- BLOCO 1: Resumo geral — usaram ou nao durante o gratis?
-- ============================================================================
WITH contratos_pagos AS (
  SELECT
    contract_id,
    account_id,
    person_id,
    holder_person_id,
    id_paciente,
    payment_id,
    contract_due_date,
    account_due_date,
    plan_months_duration,
    plan_name,
    date_month
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions`
  WHERE account_type = 'holder'
    AND payment_method = 'credit_card'
    AND plan_months_duration IN (6, 12)
    AND plan_name NOT LIKE '%gratis%'
    AND IFNULL(order_source_aj, '') != 'b2b'
    AND contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 18 MONTH)
    AND contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 60 DAY)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY contract_id ORDER BY date_month DESC
  ) = 1
),

churners AS (
  SELECT *
  FROM contratos_pagos
  WHERE DATE_DIFF(account_due_date, contract_due_date, DAY) <= 7
),

-- Proximo contrato da mesma pessoa (pode ser gratis ou pago)
proximo_contrato AS (
  SELECT
    c.contract_id AS contrato_churn_id,
    c.holder_person_id,
    c.id_paciente,
    c.contract_due_date AS data_churn,
    n.contract_id AS contrato_next_id,
    n.account_id AS next_account_id,
    n.payment_id AS next_payment_id,
    n.plan_name AS next_plan_name,
    n.contract_register_date AS next_register_date,
    n.contract_due_date AS next_due_date,
    DATE_DIFF(n.contract_register_date, c.contract_due_date, DAY) AS dias_ate_gratis,
    ROW_NUMBER() OVER (
      PARTITION BY c.contract_id
      ORDER BY n.contract_register_date
    ) AS rn
  FROM churners c
  JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` n
    ON n.holder_person_id = c.holder_person_id
    AND n.contract_register_date > c.contract_due_date
    AND n.contract_register_date <= DATE_ADD(c.contract_due_date, INTERVAL 60 DAY)
    AND n.plan_name LIKE '%gratis%'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY n.contract_id ORDER BY n.date_month DESC
  ) = 1
),

migraram_gratis AS (
  SELECT * FROM proximo_contrato WHERE rn = 1
),

-- O que aconteceu DEPOIS do gratis (voltou pago ou saiu)
pos_gratis AS (
  SELECT
    mg.contrato_churn_id,
    mg.contrato_next_id AS contrato_gratis_id,
    mg.holder_person_id,
    mg.id_paciente,
    mg.data_churn,
    mg.next_register_date AS gratis_inicio,
    mg.next_due_date AS gratis_fim,
    mg.dias_ate_gratis,
    p.contract_id AS contrato_pos_id,
    p.plan_name AS pos_plan_name,
    p.contract_register_date AS pos_register_date,
    CASE
      WHEN p.contract_id IS NOT NULL
        AND p.plan_name NOT LIKE '%gratis%' THEN 'voltou_pago'
      ELSE 'saiu_de_vez'
    END AS desfecho
  FROM migraram_gratis mg
  LEFT JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` p
    ON p.holder_person_id = mg.holder_person_id
    AND p.contract_register_date > mg.next_register_date
    AND p.contract_register_date <= DATE_ADD(mg.next_due_date, INTERVAL 90 DAY)
    AND p.plan_name NOT LIKE '%gratis%'
    AND p.account_type = 'holder'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY mg.contrato_churn_id
    ORDER BY p.contract_register_date
  ) = 1
),

-- Uso durante o periodo gratis (via bi_recepcao_itens)
uso_gratis AS (
  SELECT
    pg.contrato_churn_id,
    pg.desfecho,
    COUNT(DISTINCT ri.id_item) AS total_itens,
    COUNTIF(ri.produto_grupo = 'CM') AS consultas_presencial,
    COUNTIF(ri.produto_grupo = 'CM'
      AND LOWER(ri.executante_especialidade) LIKE '%tele%') AS consultas_tele,
    COUNTIF(ri.produto_grupo = 'EXAMES') AS exames,
    COUNT(DISTINCT ri.executante_especialidade) AS especialidades_distintas,
    COUNT(DISTINCT DATE(ri.data)) AS dias_com_uso,
    MIN(ri.data) AS primeiro_uso,
    MAX(ri.data) AS ultimo_uso
  FROM pos_gratis pg
  -- Join via itens do contrato gratis
  JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_itens` yi
    ON yi.person_id = pg.holder_person_id
  JOIN `airflow-datalake-prod.DRC_DW.bi_recepcao_itens` ri
    ON ri.id_item = yi.id_item
    AND ri.data >= pg.gratis_inicio
    AND ri.data <= COALESCE(pg.gratis_fim, DATE_ADD(pg.gratis_inicio, INTERVAL 120 DAY))
  GROUP BY pg.contrato_churn_id, pg.desfecho
)

-- RESULTADO BLOCO 1: resumo geral
SELECT
  COUNT(DISTINCT pg.contrato_churn_id) AS total_migraram_gratis,
  COUNT(DISTINCT ug.contrato_churn_id) AS usaram_rede,
  ROUND(100.0 * COUNT(DISTINCT ug.contrato_churn_id)
    / COUNT(DISTINCT pg.contrato_churn_id), 1) AS pct_usaram,
  COUNT(DISTINCT pg.contrato_churn_id)
    - COUNT(DISTINCT ug.contrato_churn_id) AS nao_usaram,
  ROUND(100.0 * (COUNT(DISTINCT pg.contrato_churn_id)
    - COUNT(DISTINCT ug.contrato_churn_id))
    / COUNT(DISTINCT pg.contrato_churn_id), 1) AS pct_nao_usaram,
  -- Medias de quem usou
  ROUND(AVG(ug.total_itens), 1) AS media_itens,
  ROUND(AVG(ug.consultas_presencial), 1) AS media_consultas,
  ROUND(AVG(ug.exames), 1) AS media_exames,
  ROUND(AVG(ug.dias_com_uso), 1) AS media_dias_com_uso
FROM pos_gratis pg
LEFT JOIN uso_gratis ug ON ug.contrato_churn_id = pg.contrato_churn_id;


-- ============================================================================
-- BLOCO 2: Uso por desfecho — quem usa mais volta pro pago?
-- ============================================================================
WITH contratos_pagos AS (
  SELECT
    contract_id, account_id, person_id, holder_person_id, id_paciente,
    payment_id, contract_due_date, account_due_date,
    plan_months_duration, plan_name, date_month
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions`
  WHERE account_type = 'holder'
    AND payment_method = 'credit_card'
    AND plan_months_duration IN (6, 12)
    AND plan_name NOT LIKE '%gratis%'
    AND IFNULL(order_source_aj, '') != 'b2b'
    AND contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 18 MONTH)
    AND contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 60 DAY)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY contract_id ORDER BY date_month DESC
  ) = 1
),

churners AS (
  SELECT * FROM contratos_pagos
  WHERE DATE_DIFF(account_due_date, contract_due_date, DAY) <= 7
),

proximo_contrato AS (
  SELECT
    c.contract_id AS contrato_churn_id,
    c.holder_person_id, c.id_paciente, c.contract_due_date AS data_churn,
    n.contract_id AS contrato_next_id, n.account_id AS next_account_id,
    n.payment_id AS next_payment_id, n.plan_name AS next_plan_name,
    n.contract_register_date AS next_register_date,
    n.contract_due_date AS next_due_date,
    ROW_NUMBER() OVER (
      PARTITION BY c.contract_id ORDER BY n.contract_register_date
    ) AS rn
  FROM churners c
  JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` n
    ON n.holder_person_id = c.holder_person_id
    AND n.contract_register_date > c.contract_due_date
    AND n.contract_register_date <= DATE_ADD(c.contract_due_date, INTERVAL 60 DAY)
    AND n.plan_name LIKE '%gratis%'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY n.contract_id ORDER BY n.date_month DESC
  ) = 1
),

migraram_gratis AS (
  SELECT * FROM proximo_contrato WHERE rn = 1
),

pos_gratis AS (
  SELECT
    mg.contrato_churn_id, mg.contrato_next_id AS contrato_gratis_id,
    mg.holder_person_id, mg.id_paciente, mg.data_churn,
    mg.next_register_date AS gratis_inicio,
    mg.next_due_date AS gratis_fim,
    CASE
      WHEN p.contract_id IS NOT NULL
        AND p.plan_name NOT LIKE '%gratis%' THEN 'voltou_pago'
      ELSE 'saiu_de_vez'
    END AS desfecho
  FROM migraram_gratis mg
  LEFT JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` p
    ON p.holder_person_id = mg.holder_person_id
    AND p.contract_register_date > mg.next_register_date
    AND p.contract_register_date <= DATE_ADD(mg.next_due_date, INTERVAL 90 DAY)
    AND p.plan_name NOT LIKE '%gratis%'
    AND p.account_type = 'holder'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY mg.contrato_churn_id ORDER BY p.contract_register_date
  ) = 1
),

uso_gratis AS (
  SELECT
    pg.contrato_churn_id, pg.desfecho,
    COUNT(DISTINCT ri.id_item) AS total_itens,
    COUNTIF(ri.produto_grupo = 'CM') AS consultas_presencial,
    COUNTIF(ri.produto_grupo = 'CM'
      AND LOWER(ri.executante_especialidade) LIKE '%tele%') AS consultas_tele,
    COUNTIF(ri.produto_grupo = 'EXAMES') AS exames,
    COUNT(DISTINCT ri.executante_especialidade) AS especialidades_distintas,
    COUNT(DISTINCT DATE(ri.data)) AS dias_com_uso
  FROM pos_gratis pg
  JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_itens` yi
    ON yi.person_id = pg.holder_person_id
  JOIN `airflow-datalake-prod.DRC_DW.bi_recepcao_itens` ri
    ON ri.id_item = yi.id_item
    AND ri.data >= pg.gratis_inicio
    AND ri.data <= COALESCE(pg.gratis_fim, DATE_ADD(pg.gratis_inicio, INTERVAL 120 DAY))
  GROUP BY pg.contrato_churn_id, pg.desfecho
)

-- RESULTADO BLOCO 2: uso por desfecho
SELECT
  pg.desfecho,
  COUNT(DISTINCT pg.contrato_churn_id) AS contratos,
  COUNT(DISTINCT ug.contrato_churn_id) AS usaram_rede,
  ROUND(100.0 * COUNT(DISTINCT ug.contrato_churn_id)
    / COUNT(DISTINCT pg.contrato_churn_id), 1) AS pct_usaram,
  ROUND(AVG(IFNULL(ug.total_itens, 0)), 1) AS media_itens_todos,
  ROUND(AVG(ug.total_itens), 1) AS media_itens_quem_usou,
  ROUND(AVG(ug.consultas_presencial), 1) AS media_consultas,
  ROUND(AVG(ug.consultas_tele), 1) AS media_tele,
  ROUND(AVG(ug.exames), 1) AS media_exames,
  ROUND(AVG(ug.especialidades_distintas), 1) AS media_especialidades,
  ROUND(AVG(ug.dias_com_uso), 1) AS media_dias_com_uso
FROM pos_gratis pg
LEFT JOIN uso_gratis ug ON ug.contrato_churn_id = pg.contrato_churn_id
GROUP BY pg.desfecho
ORDER BY pg.desfecho;


-- ============================================================================
-- BLOCO 3: Especialidades mais usadas durante o gratis (por desfecho)
-- ============================================================================
WITH contratos_pagos AS (
  SELECT
    contract_id, account_id, person_id, holder_person_id, id_paciente,
    payment_id, contract_due_date, account_due_date,
    plan_months_duration, plan_name, date_month
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions`
  WHERE account_type = 'holder'
    AND payment_method = 'credit_card'
    AND plan_months_duration IN (6, 12)
    AND plan_name NOT LIKE '%gratis%'
    AND IFNULL(order_source_aj, '') != 'b2b'
    AND contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 18 MONTH)
    AND contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 60 DAY)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY contract_id ORDER BY date_month DESC
  ) = 1
),

churners AS (
  SELECT * FROM contratos_pagos
  WHERE DATE_DIFF(account_due_date, contract_due_date, DAY) <= 7
),

proximo_contrato AS (
  SELECT
    c.contract_id AS contrato_churn_id, c.holder_person_id, c.id_paciente,
    c.contract_due_date AS data_churn,
    n.contract_id AS contrato_next_id,
    n.contract_register_date AS next_register_date,
    n.contract_due_date AS next_due_date,
    ROW_NUMBER() OVER (
      PARTITION BY c.contract_id ORDER BY n.contract_register_date
    ) AS rn
  FROM churners c
  JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` n
    ON n.holder_person_id = c.holder_person_id
    AND n.contract_register_date > c.contract_due_date
    AND n.contract_register_date <= DATE_ADD(c.contract_due_date, INTERVAL 60 DAY)
    AND n.plan_name LIKE '%gratis%'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY n.contract_id ORDER BY n.date_month DESC
  ) = 1
),

migraram_gratis AS (
  SELECT * FROM proximo_contrato WHERE rn = 1
),

pos_gratis AS (
  SELECT
    mg.contrato_churn_id, mg.holder_person_id, mg.id_paciente,
    mg.next_register_date AS gratis_inicio,
    mg.next_due_date AS gratis_fim,
    CASE
      WHEN p.contract_id IS NOT NULL
        AND p.plan_name NOT LIKE '%gratis%' THEN 'voltou_pago'
      ELSE 'saiu_de_vez'
    END AS desfecho
  FROM migraram_gratis mg
  LEFT JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` p
    ON p.holder_person_id = mg.holder_person_id
    AND p.contract_register_date > mg.next_register_date
    AND p.contract_register_date <= DATE_ADD(mg.next_due_date, INTERVAL 90 DAY)
    AND p.plan_name NOT LIKE '%gratis%'
    AND p.account_type = 'holder'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY mg.contrato_churn_id ORDER BY p.contract_register_date
  ) = 1
)

-- RESULTADO BLOCO 3: especialidades
SELECT
  pg.desfecho,
  ri.executante_especialidade AS especialidade,
  ri.produto_grupo,
  COUNT(*) AS atendimentos,
  COUNT(DISTINCT pg.contrato_churn_id) AS pacientes_distintos
FROM pos_gratis pg
JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_itens` yi
  ON yi.person_id = pg.holder_person_id
JOIN `airflow-datalake-prod.DRC_DW.bi_recepcao_itens` ri
  ON ri.id_item = yi.id_item
  AND ri.data >= pg.gratis_inicio
  AND ri.data <= COALESCE(pg.gratis_fim, DATE_ADD(pg.gratis_inicio, INTERVAL 120 DAY))
GROUP BY pg.desfecho, ri.executante_especialidade, ri.produto_grupo
HAVING atendimentos >= 5
ORDER BY pg.desfecho, atendimentos DESC;


-- ============================================================================
-- BLOCO 4: Timeline — quando usam durante o gratis (semana a semana)
-- ============================================================================
WITH contratos_pagos AS (
  SELECT
    contract_id, account_id, person_id, holder_person_id, id_paciente,
    payment_id, contract_due_date, account_due_date,
    plan_months_duration, plan_name, date_month
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions`
  WHERE account_type = 'holder'
    AND payment_method = 'credit_card'
    AND plan_months_duration IN (6, 12)
    AND plan_name NOT LIKE '%gratis%'
    AND IFNULL(order_source_aj, '') != 'b2b'
    AND contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 18 MONTH)
    AND contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 60 DAY)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY contract_id ORDER BY date_month DESC
  ) = 1
),

churners AS (
  SELECT * FROM contratos_pagos
  WHERE DATE_DIFF(account_due_date, contract_due_date, DAY) <= 7
),

proximo_contrato AS (
  SELECT
    c.contract_id AS contrato_churn_id, c.holder_person_id, c.id_paciente,
    c.contract_due_date AS data_churn,
    n.contract_register_date AS next_register_date,
    n.contract_due_date AS next_due_date,
    ROW_NUMBER() OVER (
      PARTITION BY c.contract_id ORDER BY n.contract_register_date
    ) AS rn
  FROM churners c
  JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` n
    ON n.holder_person_id = c.holder_person_id
    AND n.contract_register_date > c.contract_due_date
    AND n.contract_register_date <= DATE_ADD(c.contract_due_date, INTERVAL 60 DAY)
    AND n.plan_name LIKE '%gratis%'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY n.contract_id ORDER BY n.date_month DESC
  ) = 1
),

migraram_gratis AS (
  SELECT * FROM proximo_contrato WHERE rn = 1
),

pos_gratis AS (
  SELECT
    mg.contrato_churn_id, mg.holder_person_id, mg.id_paciente,
    mg.next_register_date AS gratis_inicio,
    mg.next_due_date AS gratis_fim,
    CASE
      WHEN p.contract_id IS NOT NULL
        AND p.plan_name NOT LIKE '%gratis%' THEN 'voltou_pago'
      ELSE 'saiu_de_vez'
    END AS desfecho
  FROM migraram_gratis mg
  LEFT JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` p
    ON p.holder_person_id = mg.holder_person_id
    AND p.contract_register_date > mg.next_register_date
    AND p.contract_register_date <= DATE_ADD(mg.next_due_date, INTERVAL 90 DAY)
    AND p.plan_name NOT LIKE '%gratis%'
    AND p.account_type = 'holder'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY mg.contrato_churn_id ORDER BY p.contract_register_date
  ) = 1
)

-- RESULTADO BLOCO 4: timeline semanal
SELECT
  pg.desfecho,
  CASE
    WHEN DATE_DIFF(ri.data, pg.gratis_inicio, DAY) BETWEEN 0 AND 7   THEN 'semana_1'
    WHEN DATE_DIFF(ri.data, pg.gratis_inicio, DAY) BETWEEN 8 AND 14  THEN 'semana_2'
    WHEN DATE_DIFF(ri.data, pg.gratis_inicio, DAY) BETWEEN 15 AND 21 THEN 'semana_3'
    WHEN DATE_DIFF(ri.data, pg.gratis_inicio, DAY) BETWEEN 22 AND 28 THEN 'semana_4'
    WHEN DATE_DIFF(ri.data, pg.gratis_inicio, DAY) BETWEEN 29 AND 42 THEN 'semana_5_6'
    WHEN DATE_DIFF(ri.data, pg.gratis_inicio, DAY) BETWEEN 43 AND 56 THEN 'semana_7_8'
    ELSE 'apos_8_semanas'
  END AS periodo,
  COUNT(*) AS atendimentos,
  COUNT(DISTINCT pg.contrato_churn_id) AS pacientes_distintos
FROM pos_gratis pg
JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_itens` yi
  ON yi.person_id = pg.holder_person_id
JOIN `airflow-datalake-prod.DRC_DW.bi_recepcao_itens` ri
  ON ri.id_item = yi.id_item
  AND ri.data >= pg.gratis_inicio
  AND ri.data <= COALESCE(pg.gratis_fim, DATE_ADD(pg.gratis_inicio, INTERVAL 120 DAY))
GROUP BY pg.desfecho, periodo
ORDER BY pg.desfecho, periodo;
