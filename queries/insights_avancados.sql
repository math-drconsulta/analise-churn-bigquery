-- ============================================================================
-- QUERIES AVANÇADAS — INSIGHTS DE ALTO IMPACTO PARA CHURN
-- Base: anl_churn_contratos + ref_yalo_subscriptions
-- Filtro padrão: planos 6+12m + credit_card + sem B2B
--
-- 3 blocos:
--   IA-1: Análise de Coorte & Retenção (curvas de sobrevivência)
--   IA-2: Impacto Financeiro & CLV (receita perdida, valor do cliente)
--   IA-3: Sazonalidade & Early Warning (padrões temporais, sinais precoces)
--
-- INSTRUÇÕES: Rode cada query separadamente no BigQuery e salve o CSV
-- na pasta results/ com o nome indicado em cada seção.
-- ============================================================================


-- ============================================================================
-- IA-1A: ANÁLISE DE COORTE — Retenção por safra de registro
-- Arquivo: results/coorte_retencao.csv
--
-- OBJETIVO: Construir a "retention table" clássica. Cada linha é uma safra
-- mensal de registro (cohort), e acompanhamos quantos contratos cada safra
-- gerou nos ciclos subsequentes (1o, 2o, 3o+ contrato).
-- Permite ver se safras recentes retêm melhor ou pior que as antigas.
-- ============================================================================

WITH contratos_validos AS (
  -- Só contratos com vencimento dentro do range confiável da base
  -- (anl_churn_contratos vai até ~mar/2026 em vencimentos)
  SELECT
    account_id,
    contract_id,
    contract_register_date,
    contract_due_date,
    contract_due_date_month,
    account_contract_number,
    churn_renovacao_automatica_sn,
    plan_months_duration,
    DATE_TRUNC(contract_register_date, MONTH) AS safra_registro
  FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
  WHERE plan_months_duration IN (6, 12)
    AND order_payment_method = 'credit_card'
    AND IFNULL(order_source_aj, '') != 'b2b'
    -- Filtrar só contratos que VENCERAM nos últimos 12 meses (dados confiáveis)
    AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
),

-- Para cada account, pegar a safra do PRIMEIRO contrato
-- (considerando toda a história, não só os 12 meses filtrados)
primeira_safra AS (
  SELECT
    account_id,
    DATE_TRUNC(MIN(contract_register_date), MONTH) AS coorte
  FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
  WHERE plan_months_duration IN (6, 12)
    AND order_payment_method = 'credit_card'
    AND IFNULL(order_source_aj, '') != 'b2b'
  GROUP BY account_id
)

SELECT
  ps.coorte,
  co.account_contract_number AS ciclo_contrato,
  CAST(co.plan_months_duration AS STRING) AS duracao,
  COUNT(DISTINCT co.account_id) AS clientes,
  COUNT(*) AS contratos,
  SUM(CASE WHEN co.churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  ROUND(100.0 * SUM(CASE WHEN co.churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_rate,
  ROUND(100.0 - 100.0 * SUM(CASE WHEN co.churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) AS retencao_rate
FROM contratos_validos co
JOIN primeira_safra ps ON co.account_id = ps.account_id
GROUP BY 1, 2, 3
HAVING COUNT(*) >= 30  -- evitar perfis com volume muito baixo
ORDER BY ps.coorte, co.account_contract_number, duracao;


-- ============================================================================
-- IA-1B: CURVA DE SOBREVIVÊNCIA POR PERFIL DE RISCO
-- Arquivo: results/sobrevivencia_perfil.csv
--
-- OBJETIVO: Para os perfis de risco (combinação ciclo × idade × crônico),
-- calcular quantos "sobrevivem" (renovam) em cada ciclo de contrato.
-- Isso mostra a velocidade de evasão por perfil — crucial para priorizar.
-- ============================================================================

WITH contratos_perfil AS (
  SELECT
    account_id,
    account_contract_number,
    plan_months_duration,
    churn_renovacao_automatica_sn,
    CASE
      WHEN titular_idade <= 30 THEN 'jovem_00-30'
      WHEN titular_idade <= 50 THEN 'adulto_31-50'
      ELSE 'senior_51+'
    END AS perfil_idade,
    IFNULL(titular_main_cronico_sn, 'N') AS cronico,
    CASE
      WHEN dependents_per_holder = 0 THEN 'solo'
      ELSE 'com_dep'
    END AS tem_dependente
  FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
  WHERE plan_months_duration IN (6, 12)
    AND order_payment_method = 'credit_card'
    AND IFNULL(order_source_aj, '') != 'b2b'
    AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 24 MONTH)
)

SELECT
  perfil_idade,
  cronico,
  tem_dependente,
  CAST(plan_months_duration AS STRING) AS duracao,
  account_contract_number AS ciclo,
  COUNT(*) AS contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'N' THEN 1 ELSE 0 END) AS renovaram,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'N' THEN 1 ELSE 0 END) / COUNT(*), 1) AS taxa_renovacao,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_rate
FROM contratos_perfil
GROUP BY 1, 2, 3, 4, 5
HAVING COUNT(*) >= 30
ORDER BY perfil_idade, cronico, tem_dependente, duracao, ciclo;


-- ============================================================================
-- IA-2A: IMPACTO FINANCEIRO — Volume de churn por segmento e mês
-- Arquivo: results/impacto_financeiro.csv
--
-- OBJETIVO: Fornecer os volumes de churn segmentados por mês, duração,
-- ciclo e perfil etário. O cálculo em R$ será feito no dashboard com
-- ticket médio parametrizável (a tabela anl_churn_contratos não tem
-- coluna de valor do plano).
-- ============================================================================

SELECT
  contract_due_date_month AS mes_vencimento,
  CAST(plan_months_duration AS STRING) AS duracao,
  CASE WHEN account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo,
  CASE
    WHEN titular_idade <= 30 THEN 'jovem_00-30'
    WHEN titular_idade <= 50 THEN 'adulto_31-50'
    ELSE 'senior_51+'
  END AS perfil_idade,
  COUNT(*) AS total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'N' THEN 1 ELSE 0 END) AS retidos,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_rate,

  -- Dependentes médios (proxy de complexidade do plano / ticket)
  ROUND(AVG(dependents_per_holder), 2) AS media_dependentes

FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12)
  AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3, 4
ORDER BY mes_vencimento, duracao, ciclo, perfil_idade;


-- ============================================================================
-- IA-2B: CLV ESTIMADO — Lifetime Value por perfil (baseado em contagens)
-- Arquivo: results/clv_por_perfil.csv
--
-- OBJETIVO: Estimar o CLV relativo para cada perfil usando a taxa de
-- retenção como proxy de vida útil.
-- CLV_relativo = duracao_meses / churn_rate (meses esperados de vida)
-- O dashboard multiplica pelo ticket informado pelo usuário para obter R$.
-- ============================================================================

SELECT
  CASE WHEN account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo,
  CASE
    WHEN titular_idade <= 30 THEN 'jovem_00-30'
    WHEN titular_idade <= 50 THEN 'adulto_31-50'
    ELSE 'senior_51+'
  END AS perfil_idade,
  IFNULL(titular_main_cronico_sn, 'N') AS cronico,
  CASE
    WHEN dependents_per_holder = 0 THEN 'solo'
    ELSE 'com_dep'
  END AS tem_dependente,
  CAST(plan_months_duration AS STRING) AS duracao,

  COUNT(*) AS total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'N' THEN 1 ELSE 0 END) AS retidos,

  -- Churn rate por ciclo do contrato (proxy para taxa periódica)
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 2) AS churn_rate_pct,

  -- Meses esperados de vida = duracao / churn_rate
  -- Ex: plano 12m com 55% churn → 12 / 0.55 = 21.8 meses de vida média
  ROUND(
    AVG(plan_months_duration) /
    NULLIF(SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1.0 ELSE 0 END) / COUNT(*), 0),
    1
  ) AS meses_vida_estimados,

  -- Dependentes médios (proxy de ticket — mais dependentes = plano mais caro)
  ROUND(AVG(dependents_per_holder), 2) AS media_dependentes

FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12)
  AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3, 4, 5
HAVING COUNT(*) >= 50
ORDER BY meses_vida_estimados DESC;


-- ============================================================================
-- IA-3A: SAZONALIDADE — Churn por mês × dia da semana de vencimento
-- Arquivo: results/sazonalidade_churn.csv
--
-- OBJETIVO: Identificar padrões sazonais (meses piores) e se o dia da semana
-- do vencimento afeta a renovação (cobranças em fim de semana podem falhar mais).
-- ============================================================================

SELECT
  contract_due_date_month AS mes_vencimento,
  EXTRACT(MONTH FROM contract_due_date_month) AS mes_num,
  FORMAT_DATE('%B', contract_due_date_month) AS mes_nome,
  EXTRACT(DAYOFWEEK FROM contract_due_date) AS dia_semana_vencimento,
  CASE EXTRACT(DAYOFWEEK FROM contract_due_date)
    WHEN 1 THEN 'Dom'
    WHEN 2 THEN 'Seg'
    WHEN 3 THEN 'Ter'
    WHEN 4 THEN 'Qua'
    WHEN 5 THEN 'Qui'
    WHEN 6 THEN 'Sex'
    WHEN 7 THEN 'Sab'
  END AS dia_semana_nome,
  CAST(plan_months_duration AS STRING) AS duracao,
  COUNT(*) AS total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_rate
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12)
  AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3, 4, 5, 6
ORDER BY mes_vencimento, dia_semana_vencimento, duracao;


-- ============================================================================
-- IA-3B: EARLY WARNING — Sinais precoces nos primeiros 30/60/90 dias
-- Arquivo: results/early_warning.csv
--
-- OBJETIVO: Quais comportamentos nos primeiros N dias predizem churn?
-- Cruza: tempo até 1º uso × nº de itens consumidos × tipo de uso
-- para criar "sinais de alerta" que o CRM pode monitorar em tempo real.
-- ============================================================================

SELECT
  CAST(plan_months_duration AS STRING) AS duracao,
  CASE WHEN account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo,

  -- Sinal 1: Usou nos primeiros 30 dias?
  CASE WHEN IFNULL(consumo_sn, 'N') = 'S' THEN 'usou' ELSE 'nao_usou' END AS consumiu,

  -- Sinal 2: Quantidade de itens consumidos (engajamento)
  CASE
    WHEN IFNULL(qtd_TOTAL_CM, 0) + IFNULL(qtd_TOTAL_EXAMES, 0) = 0 THEN '0_itens'
    WHEN IFNULL(qtd_TOTAL_CM, 0) + IFNULL(qtd_TOTAL_EXAMES, 0) <= 2 THEN '1-2_itens'
    WHEN IFNULL(qtd_TOTAL_CM, 0) + IFNULL(qtd_TOTAL_EXAMES, 0) <= 5 THEN '3-5_itens'
    ELSE '6+_itens'
  END AS faixa_itens,

  -- Sinal 3: Diversidade de uso (quantas especialidades diferentes)
  (CASE WHEN IFNULL(qtd_TOTAL_CM_CLINICA_MEDICA, 0) > 0 THEN 1 ELSE 0 END
   + CASE WHEN IFNULL(qtd_TOTAL_CM_GINECOLOGIA, 0) > 0 THEN 1 ELSE 0 END
   + CASE WHEN IFNULL(qtd_TOTAL_CM_CARDIOLOGISTA, 0) > 0 THEN 1 ELSE 0 END
   + CASE WHEN IFNULL(qtd_TOTAL_CM_DERMATOLOGISTA, 0) > 0 THEN 1 ELSE 0 END
   + CASE WHEN IFNULL(qtd_TOTAL_CM_ENDOCRINOLOGISTA, 0) > 0 THEN 1 ELSE 0 END
   + CASE WHEN IFNULL(qtd_TOTAL_CM_PSIQUIATRIA, 0) > 0 THEN 1 ELSE 0 END
   + CASE WHEN IFNULL(qtd_TOTAL_CM_ORTOPEDISTA, 0) > 0 THEN 1 ELSE 0 END
   + CASE WHEN IFNULL(qtd_TOTAL_CM_PEDIATRA, 0) > 0 THEN 1 ELSE 0 END
   + CASE WHEN IFNULL(qtd_TOTAL_CM_TELE, 0) > 0 THEN 1 ELSE 0 END
   + CASE WHEN IFNULL(qtd_TOTAL_EXAMES, 0) > 0 THEN 1 ELSE 0 END
  ) AS diversidade_uso,

  -- Sinal 4: Crônico (ancoragem médica)
  IFNULL(titular_main_cronico_sn, 'N') AS cronico,

  COUNT(*) AS total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_rate

FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12)
  AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3, 4, 5, 6
HAVING COUNT(*) >= 20
ORDER BY churn_rate DESC;


-- ============================================================================
-- IA-3C: ANTECEDÊNCIA DO CANCELAMENTO ATIVO
-- Arquivo: results/velocidade_churn.csv
--
-- OBJETIVO: Para quem pediu cancelamento ativo (unsubscription), quantos dias
-- ANTES do vencimento do contrato o pedido foi feito?
-- Isso mostra a "janela de decisão" do paciente e quando o CRM deve agir.
--
-- Usa ref_yalo_subscriptions para pegar unsubscription_date (não disponível
-- na anl_churn_contratos). Inclui também o days_diff_until_next_contract
-- para churners silenciosos como proxy do gap pós-vencimento.
-- ============================================================================

WITH cancelamentos AS (
  SELECT
    CAST(c.plan_months_duration AS STRING) AS duracao,
    CASE WHEN c.account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo,
    'churn_ativo' AS tipo_churn,
    DATE_DIFF(c.contract_due_date, DATE(ys.unsubscription_date), DAY) AS dias_antecedencia
  FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` c
  JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
    ON ys.contract_id = c.contract_id
    AND ys.account_type = 'holder'
  WHERE c.plan_months_duration IN (6, 12)
    AND c.order_payment_method = 'credit_card'
    AND IFNULL(c.order_source_aj, '') != 'b2b'
    AND c.contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
    AND c.churn_renovacao_automatica_sn = 'S'
    AND c.unsubscription_sn = 'S'
    AND ys.unsubscription_date IS NOT NULL
),

silenciosos AS (
  SELECT
    CAST(c.plan_months_duration AS STRING) AS duracao,
    CASE WHEN c.account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo,
    'churn_silencioso' AS tipo_churn,
    -- Para silenciosos: days_diff_until_next_contract como proxy
    -- Negativo = nunca mais voltou (sem proximo contrato)
    CASE
      WHEN ys.days_diff_until_next_contract IS NULL THEN -999
      ELSE CAST(ys.days_diff_until_next_contract AS INT64)
    END AS dias_antecedencia
  FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos` c
  JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
    ON ys.contract_id = c.contract_id
    AND ys.account_type = 'holder'
  WHERE c.plan_months_duration IN (6, 12)
    AND c.order_payment_method = 'credit_card'
    AND IFNULL(c.order_source_aj, '') != 'b2b'
    AND c.contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
    AND c.churn_renovacao_automatica_sn = 'S'
    AND IFNULL(c.unsubscription_sn, 'N') = 'N'
),

todos AS (
  SELECT * FROM cancelamentos
  UNION ALL
  SELECT * FROM silenciosos
),

faixas AS (
  SELECT
    duracao, ciclo, tipo_churn,
    CASE
      WHEN tipo_churn = 'churn_ativo' THEN
        CASE
          WHEN dias_antecedencia > 90 THEN 'A_90+_dias_antes'
          WHEN dias_antecedencia > 30 THEN 'B_31-90_dias_antes'
          WHEN dias_antecedencia > 7  THEN 'C_8-30_dias_antes'
          WHEN dias_antecedencia > 0  THEN 'D_1-7_dias_antes'
          ELSE 'E_no_dia_ou_apos'
        END
      ELSE  -- silencioso
        CASE
          WHEN dias_antecedencia = -999 THEN 'F_nunca_voltou'
          WHEN dias_antecedencia > 60 THEN 'G_voltou_60+_dias'
          WHEN dias_antecedencia > 0  THEN 'H_voltou_1-60_dias'
          ELSE 'I_sem_proximo'
        END
    END AS janela_saida
  FROM todos
),

agg AS (
  SELECT duracao, ciclo, tipo_churn, janela_saida, COUNT(*) AS total
  FROM faixas
  GROUP BY 1, 2, 3, 4
)

SELECT
  duracao, ciclo, tipo_churn, janela_saida, total,
  ROUND(100.0 * total / SUM(total) OVER(PARTITION BY duracao, ciclo, tipo_churn), 1) AS pct_do_tipo
FROM agg
ORDER BY duracao, ciclo, tipo_churn, janela_saida;
