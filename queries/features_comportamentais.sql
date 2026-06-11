-- ============================================================================
-- FEATURES COMPORTAMENTAIS PARA O SCORE DE CHURN
-- Arquivo: results/features_comportamentais.csv
--
-- OBJETIVO: Extrair 6 features de comportamento de uso para cada contrato,
-- baseadas em bi_recepcao_itens (registros de atendimento real).
--
-- Essas features capturam o que o paciente VIVE durante o contrato,
-- não apenas quem ele É (perfil) — complementando o score estático.
--
-- FEATURES:
--   1. dias_ate_primeiro_uso  — onboarding: quanto demorou pra usar
--   2. dias_desde_ultimo_uso  — recência: há quanto tempo parou de usar
--   3. total_itens            — volume total de atendimentos
--   4. itens_por_mes          — frequência: atendimentos/mês
--   5. qtd_unidades_distintas — dispersão: quantas clínicas diferentes
--   6. qtd_especialidades     — diversidade: quantas especialidades usou
--   7. itens_primeira_metade  — uso na 1a metade do contrato
--   8. itens_segunda_metade   — uso na 2a metade do contrato
--   9. trajetoria             — itens_2a_metade - itens_1a_metade
--                               negativo = uso caindo (sinal de desengajamento)
--
-- JOIN VALIDADO (mesmo padrão de novas_analises.sql e nucleo_familiar.sql):
--   ref_yalo_subscriptions → ref_yalo_itens (payment_id + person_id)
--                          → bi_recepcao_itens (id_item)
--
-- FILTRO DE DATAS:
--   Só conta itens dentro do período do contrato (register_date até due_date).
--   Contratos com due_date no futuro usam CURRENT_DATE como limite.
--
-- ESCOPO:
--   Todos os contratos credit_card, 6/12m, sem B2B, holder.
--   Inclui contratos sem nenhum uso (LEFT JOIN → features = 0/NULL).
-- ============================================================================


-- ============================================================================
-- STEP 0 (OPCIONAL): Diagnóstico — rode antes pra validar que os JOINs funcionam
-- ============================================================================

-- SELECT
--   COUNT(DISTINCT ys.contract_id) AS total_contratos,
--   COUNT(DISTINCT CASE WHEN ri.id_item IS NOT NULL THEN ys.contract_id END) AS contratos_com_uso,
--   COUNT(ri.id_item) AS total_itens,
--   MIN(ri.data) AS primeiro_item,
--   MAX(ri.data) AS ultimo_item
-- FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
-- LEFT JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_itens` yi
--   ON yi.payment_id = ys.payment_id AND yi.person_id = ys.person_id
-- LEFT JOIN `airflow-datalake-prod.DRC_DW.bi_recepcao_itens` ri
--   ON ri.id_item = yi.id_item
--   AND ri.data >= ys.contract_register_date
--   AND ri.data <= LEAST(ys.contract_due_date, CURRENT_DATE())
-- WHERE ys.account_type = 'holder'
--   AND ys.payment_method = 'credit_card'
--   AND ys.plan_months_duration IN (6, 12)
--   AND ys.plan_name NOT LIKE '%gratis%'
--   AND IFNULL(ys.order_source_aj, '') != 'b2b'
--   AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 18 MONTH);


-- ============================================================================
-- STEP 1: QUERY PRINCIPAL — Features comportamentais por contrato
-- ============================================================================

WITH contratos AS (
  -- Base: 1 linha por contrato (holder, deduplicated)
  -- Usa a snapshot mais recente pra pegar dados do contrato
  SELECT
    ys.contract_id,
    ys.account_id,
    ys.person_id,
    ys.contract_register_date,
    ys.contract_due_date,
    ys.plan_months_duration,
    ys.account_contract_number,
    IFNULL(ys.order_source_aj, 'outros') AS canal,

    -- Data limite de uso: vencimento ou hoje (o que for menor)
    LEAST(ys.contract_due_date, CURRENT_DATE()) AS data_limite,

    -- Ponto médio do contrato (pra calcular trajetória)
    DATE_ADD(
      ys.contract_register_date,
      INTERVAL CAST(DATE_DIFF(
        LEAST(ys.contract_due_date, CURRENT_DATE()),
        ys.contract_register_date, DAY
      ) / 2 AS INT64) DAY
    ) AS data_meio,

    -- Meses transcorridos (pra calcular frequência)
    GREATEST(
      DATE_DIFF(LEAST(ys.contract_due_date, CURRENT_DATE()), ys.contract_register_date, DAY) / 30.0,
      1
    ) AS meses_transcorridos,

    -- Churn (mesma definição do projeto)
    CASE
      WHEN DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) > 7 THEN 'N'
      ELSE 'S'
    END AS churn_sn

  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    -- Só contratos que JÁ VENCERAM (com margem de 30 dias pra garantir que o churn foi processado)
    -- e não muito antigos (últimos 12 meses de vencimento)
    AND ys.contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 12 MONTH)
    AND ys.contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id
    ORDER BY ys.date_month DESC
  ) = 1
),

-- Coletar TODOS os payment_ids de cada contrato (não só o último)
-- Isso garante que encontramos itens vinculados a qualquer pagamento do contrato
todos_payments AS (
  SELECT DISTINCT
    ys.contract_id,
    ys.payment_id,
    ys.person_id
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.contract_id IN (SELECT contract_id FROM contratos)
),

-- Itens de uso (atendimentos reais) dentro do período do contrato
-- JOIN via TODOS os payment_ids, não só o último
itens_uso AS (
  SELECT
    c.contract_id,
    ri.data AS data_uso,
    ri.unidade,
    ri.produto_grupo,
    ri.executante_especialidade,

    -- Em qual metade do contrato esse item caiu?
    CASE
      WHEN ri.data <= c.data_meio THEN 'primeira_metade'
      ELSE 'segunda_metade'
    END AS metade_contrato

  FROM contratos c
  INNER JOIN todos_payments tp
    ON tp.contract_id = c.contract_id
  INNER JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_itens` yi
    ON yi.payment_id = tp.payment_id
    AND yi.person_id = tp.person_id
  INNER JOIN `airflow-datalake-prod.DRC_DW.bi_recepcao_itens` ri
    ON ri.id_item = yi.id_item
  WHERE ri.data >= c.contract_register_date
    AND ri.data <= c.data_limite
    AND ri.data IS NOT NULL
),

-- Agregar features por contrato
features_por_contrato AS (
  SELECT
    c.contract_id,

    -- 1. Onboarding: dias até o primeiro uso
    DATE_DIFF(MIN(iu.data_uso), c.contract_register_date, DAY) AS dias_ate_primeiro_uso,

    -- 2. Recência: dias desde o último uso até o limite (vencimento ou hoje)
    DATE_DIFF(c.data_limite, MAX(iu.data_uso), DAY) AS dias_desde_ultimo_uso,

    -- 3. Volume total
    COUNT(iu.data_uso) AS total_itens,

    -- 4. Frequência: itens por mês
    ROUND(COUNT(iu.data_uso) / c.meses_transcorridos, 2) AS itens_por_mes,

    -- 5. Dispersão geográfica: quantas clínicas diferentes
    COUNT(DISTINCT iu.unidade) AS qtd_unidades_distintas,

    -- 6. Diversidade de especialidades
    COUNT(DISTINCT iu.executante_especialidade) AS qtd_especialidades,

    -- 7-8. Uso por metade do contrato
    COUNTIF(iu.metade_contrato = 'primeira_metade') AS itens_primeira_metade,
    COUNTIF(iu.metade_contrato = 'segunda_metade') AS itens_segunda_metade,

    -- 9. Trajetória: negativo = uso caindo
    COUNTIF(iu.metade_contrato = 'segunda_metade')
      - COUNTIF(iu.metade_contrato = 'primeira_metade') AS trajetoria,

    -- Bonus: tipo de uso predominante
    COUNTIF(iu.produto_grupo = 'CM') AS qtd_consultas,
    COUNTIF(iu.produto_grupo = 'EXAMES') AS qtd_exames

  FROM contratos c
  LEFT JOIN itens_uso iu ON iu.contract_id = c.contract_id
  GROUP BY c.contract_id, c.contract_register_date, c.data_limite, c.meses_transcorridos
)

SELECT
  c.contract_id,
  c.account_id,
  c.contract_register_date,
  c.contract_due_date,
  CAST(c.plan_months_duration AS STRING) AS duracao,
  CASE WHEN c.account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo,
  c.churn_sn,

  -- Features comportamentais (NULL = nunca usou)
  f.dias_ate_primeiro_uso,
  f.dias_desde_ultimo_uso,
  f.total_itens,
  f.itens_por_mes,
  f.qtd_unidades_distintas,
  f.qtd_especialidades,
  f.itens_primeira_metade,
  f.itens_segunda_metade,
  f.trajetoria,
  f.qtd_consultas,
  f.qtd_exames,

  -- Flag derivadas (pra facilitar a análise)
  CASE WHEN f.total_itens IS NULL OR f.total_itens = 0 THEN 'nunca_usou'
       WHEN f.total_itens <= 2 THEN 'uso_baixo'
       WHEN f.total_itens <= 5 THEN 'uso_moderado'
       ELSE 'uso_alto'
  END AS faixa_uso,

  CASE WHEN f.dias_ate_primeiro_uso IS NULL THEN 'nunca_usou'
       WHEN f.dias_ate_primeiro_uso <= 7 THEN 'rapido_0-7d'
       WHEN f.dias_ate_primeiro_uso <= 30 THEN 'normal_8-30d'
       WHEN f.dias_ate_primeiro_uso <= 90 THEN 'lento_31-90d'
       ELSE 'muito_lento_90d+'
  END AS faixa_onboarding,

  CASE WHEN f.trajetoria IS NULL OR f.total_itens IS NULL OR f.total_itens = 0 THEN 'sem_uso'
       WHEN f.trajetoria > 0 THEN 'crescente'
       WHEN f.trajetoria = 0 THEN 'estavel'
       ELSE 'declinante'
  END AS tendencia_uso,

  CASE WHEN f.qtd_unidades_distintas IS NULL OR f.qtd_unidades_distintas <= 1 THEN 'uma_unidade'
       WHEN f.qtd_unidades_distintas = 2 THEN 'duas_unidades'
       ELSE 'tres_ou_mais'
  END AS faixa_dispersao

FROM contratos c
LEFT JOIN features_por_contrato f ON f.contract_id = c.contract_id

ORDER BY c.contract_due_date DESC;
