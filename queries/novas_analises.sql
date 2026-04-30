-- ============================================================================
-- QUERIES COMPLEMENTARES PARA ANÁLISE DE CHURN — dr.consulta
-- Base: anl_churn_contratos | Filtro: planos 6+12m + credit_card + sem B2B/COOP
-- ============================================================================
-- 
-- INSTRUÇÕES: Rode cada query separadamente no BigQuery e salve o resultado
-- como CSV na pasta results/ com o nome indicado em cada seção.
--
-- Após rodar todas, me avise para eu integrar os resultados no dashboard.
-- ============================================================================


-- ============================================================================
-- QUERY N1: CONSUMO CONTROLADO POR CICLO DO CONTRATO
-- Arquivo: results/consumo_controlado_ciclo.csv
-- 
-- OBJETIVO: Resolver o paradoxo do consumo. Ao cruzar consumo × ciclo,
-- provaremos que o consumo PROTEGE nos 2o+ contratos (renovações).
-- ============================================================================

SELECT
  CASE WHEN account_contract_number = 1 THEN '1o_contrato' ELSE '2o+_contrato' END AS ciclo,
  IFNULL(consumo_sn, 'N') AS consumo,
  CAST(plan_months_duration AS STRING) AS duracao,
  COUNT(*) AS total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_rate
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12)
  AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3
ORDER BY ciclo, consumo, duracao;


-- ============================================================================
-- QUERY N2: MOTIVOS DE CANCELAMENTO (UNSUBSCRIPTION REASONS)
-- Arquivo: results/motivos_cancelamento.csv
--
-- OBJETIVO: Dos 26k que pediram cancelamento ativo, QUAIS SÃO OS MOTIVOS?
-- Isso dá munição direta para o time de produto/CX.
-- ============================================================================

SELECT
  IFNULL(unsubscription_reason, '(sem motivo informado)') AS motivo,
  COUNT(*) AS total,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) AS pct_do_total
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12)
  AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
  AND unsubscription_sn = 'S'
GROUP BY 1
ORDER BY total DESC
LIMIT 30;


-- ============================================================================
-- QUERY N3: TEMPO ATÉ O PRIMEIRO USO — Curva de Engajamento
-- Arquivo: results/tempo_primeiro_uso.csv
--
-- OBJETIVO: Quantos dias depois da ativação o paciente fez o 1o uso?
-- Pacientes que usam nos primeiros 30 dias retêm muito mais.
--
-- USA LEFT JOIN para incluir pacientes que NUNCA usaram o plano
-- (faixa "A_nunca_usou"). Filtro de datas de recepção fica na cláusula
-- ON do JOIN para não anular o LEFT JOIN.
-- ============================================================================

WITH primeiro_uso AS (
  SELECT
    ys.contract_id,
    ys.contract_register_date,
    ys.contract_due_date,
    ys.account_due_date,
    ys.plan_months_duration,
    ys.account_contract_number,
    CASE
      WHEN DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) > 7 THEN 'N'
      ELSE 'S'
    END AS churn_renovacao_automatica_sn,
    MIN(ri.data) AS data_primeiro_uso,
    DATE_DIFF(MIN(ri.data), ys.contract_register_date, DAY) AS dias_ate_primeiro_uso
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  LEFT JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_itens` yi
    ON yi.payment_id = ys.payment_id AND yi.person_id = ys.person_id
  LEFT JOIN `airflow-datalake-prod.DRC_DW.bi_recepcao_itens` ri
    ON ri.id_item = yi.id_item
    AND ri.data >= ys.contract_register_date
    AND ri.data <= ys.contract_due_date
  WHERE ys.account_type = 'holder'
    AND ys.contract_payment_number = 1
    AND ys.plan_months_duration IN (6, 12)
    AND ys.order_payment_method = 'credit_card'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    AND ys.contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
  GROUP BY 1, 2, 3, 4, 5, 6, 7
)

SELECT
  CASE
    WHEN dias_ate_primeiro_uso IS NULL THEN 'A_nunca_usou'
    WHEN dias_ate_primeiro_uso <= 7 THEN 'B_0-7_dias'
    WHEN dias_ate_primeiro_uso <= 30 THEN 'C_8-30_dias'
    WHEN dias_ate_primeiro_uso <= 90 THEN 'D_31-90_dias'
    ELSE 'E_90+_dias'
  END AS faixa_primeiro_uso,
  COUNT(*) AS total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_rate,
  ROUND(AVG(dias_ate_primeiro_uso), 0) AS media_dias
FROM primeiro_uso
GROUP BY 1
ORDER BY 1;


-- ============================================================================
-- QUERY N4: CHURN POR CONTRATO + DEPENDENTES + CRÔNICO (interação controlada)
-- Arquivo: results/interacao_contrato_dep_cronico.csv
--
-- OBJETIVO: Isolar o efeito combinado das 3 variáveis mais poderosas
-- para mostrar ao time de negócios as "alavancas" incrementais.
-- ============================================================================

SELECT
  CASE WHEN account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo,
  CASE
    WHEN dependents_per_holder = 0 THEN '0_sem_dep'
    WHEN dependents_per_holder IN (1, 2) THEN '1_1-2_dep'
    ELSE '2_3+_dep'
  END AS dependentes,
  titular_main_cronico_sn AS cronico,
  COUNT(*) AS total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_rate
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12)
  AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3
ORDER BY churn_rate DESC;


-- ============================================================================
-- QUERY N5: WIN-BACK — Reativações e sua taxa de re-churn
-- Arquivo: results/winback_reativacoes.csv
--
-- OBJETIVO: Dos que foram reativados (contract_sale_type = 'reactivation'),
-- qual o perfil e a taxa de re-abandono? Serve para avaliar o ROI de
-- campanhas de recuperação.
-- ============================================================================

SELECT
  contract_sale_type AS tipo_venda,
  CASE WHEN account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo,
  IFNULL(consumo_sn, 'N') AS consumo,
  COUNT(*) AS total_contratos,
  SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) AS churners,
  ROUND(100.0 * SUM(CASE WHEN churn_renovacao_automatica_sn = 'S' THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_rate
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12)
  AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
  AND contract_sale_type IN ('reactivation', 'renewal', 'first_contract')
GROUP BY 1, 2, 3
ORDER BY tipo_venda, ciclo, consumo;


-- ============================================================================
-- QUERY N6: CHURN SILENCIOSO VS ATIVO — Perfil demográfico comparado
-- Arquivo: results/churn_silencioso_vs_ativo.csv
--
-- OBJETIVO: Dos que churnam, quem é o "silent churner" (não pediu unsub)
-- vs quem pediu ativamente? Os perfis são diferentes? O silent churner
-- é mais recuperável.
-- ============================================================================

SELECT
  CASE
    WHEN churn_renovacao_automatica_sn = 'N' THEN 'retido'
    WHEN unsubscription_sn = 'S' THEN 'churn_ativo'
    ELSE 'churn_silencioso'
  END AS tipo_desfecho,
  CASE WHEN account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo,
  CASE
    WHEN titular_idade <= 30 THEN '00-30'
    WHEN titular_idade <= 50 THEN '31-50'
    WHEN titular_idade <= 70 THEN '51-70'
    ELSE '71+'
  END AS faixa_idade,
  CASE
    WHEN dependents_per_holder = 0 THEN 'sem_dep'
    WHEN dependents_per_holder IN (1, 2) THEN '1-2_dep'
    ELSE '3+_dep'
  END AS dependentes,
  IFNULL(consumo_sn, 'N') AS consumo,
  COUNT(*) AS total_contratos
FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
WHERE plan_months_duration IN (6, 12)
  AND order_payment_method = 'credit_card'
  AND IFNULL(order_source_aj, '') != 'b2b'
  AND contract_due_date_month >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 12 MONTH)
GROUP BY 1, 2, 3, 4, 5
ORDER BY tipo_desfecho, total_contratos DESC;
