-- ============================================================================
-- QUERY OPERACIONAL — Contratos ativos com sinais de risco
-- Arquivo: results/operacional_contratos.csv
--
-- OBJETIVO: Gerar a lista semanal de contratos que vencem nos próximos 60 dias,
-- enriquecidos com sinais comportamentais para o score dinâmico.
--
-- Rodar semanalmente (ou sob demanda). Alimenta o app_operacional.py.
-- ============================================================================

WITH contratos_ativos AS (
  -- Contratos que vencem nos próximos 60 dias (janela de ação)
  SELECT
    ys.contract_id,
    ys.account_id,
    ys.person_id,
    ys.contract_register_date,
    ys.contract_due_date,
    ys.account_due_date,
    ys.plan_months_duration,
    ys.account_contract_number,
    ys.payment_method,
    ys.plan_name,
    IFNULL(ys.order_source_aj, 'outros') AS canal,
    ys.flag_unsubscription,
    ys.unsubscription_date,

    -- Dias até o vencimento (negativo = já venceu)
    DATE_DIFF(ys.contract_due_date, CURRENT_DATE(), DAY) AS dias_ate_vencimento,

    -- Ciclo
    CASE WHEN ys.account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo

  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    -- Janela: vencendo nos próximos 60 dias OU venceu nos últimos 15 (win-back)
    AND ys.contract_due_date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 15 DAY)
                                 AND DATE_ADD(CURRENT_DATE(), INTERVAL 60 DAY)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id ORDER BY ys.date_month DESC
  ) = 1
),

-- Dados demográficos da anl_churn (pode não ter todos os contratos recentes)
demo AS (
  SELECT
    contract_id,
    titular_idade,
    titular_main_cronico_sn,
    dependents_per_holder,
    titular_sexo,
    titual_classe_social AS classe_social,
    consumo_sn,
    IFNULL(qtd_TOTAL_CM, 0) + IFNULL(qtd_TOTAL_EXAMES, 0) AS total_itens_usados,
    IFNULL(qtd_TOTAL_CM, 0) AS qtd_cm,
    IFNULL(qtd_TOTAL_EXAMES, 0) AS qtd_exames,
    IFNULL(qtd_TOTAL_CM_TELE, 0) AS qtd_tele
  FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
),

-- Último uso (consulta ou exame) via recepção
ultimo_uso AS (
  SELECT
    yi.payment_id,
    MAX(ri.data) AS data_ultimo_uso
  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_itens` yi
  JOIN `airflow-datalake-prod.DRC_DW.bi_recepcao_itens` ri
    ON ri.id_item = yi.id_item
  WHERE ri.data >= DATE_SUB(CURRENT_DATE(), INTERVAL 12 MONTH)
  GROUP BY yi.payment_id
),

-- Tentativas de pagamento recentes (Adyen)
falhas_pgto AS (
  SELECT
    ae.account_id,
    COUNT(*) AS total_tentativas,
    SUM(CASE WHEN ae.payment_status THEN 1 ELSE 0 END) AS tentativas_sucesso,
    SUM(CASE WHEN NOT ae.payment_status THEN 1 ELSE 0 END) AS tentativas_falha,
    MAX(CASE WHEN NOT ae.payment_status THEN ae.created_at END) AS ultima_falha,
    MAX(CASE WHEN ae.payment_status THEN ae.created_at END) AS ultimo_sucesso
  FROM `airflow-datalake-prod.yalo.public_adyen_events` ae
  WHERE ae.created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
  GROUP BY ae.account_id
)

SELECT
  ca.contract_id,
  ca.account_id,
  ca.contract_register_date,
  ca.contract_due_date,
  ca.dias_ate_vencimento,
  ca.plan_months_duration AS duracao,
  ca.ciclo,
  ca.canal,
  ca.flag_unsubscription AS pediu_cancelamento,

  -- Demograficas
  CASE
    WHEN d.titular_idade <= 30 THEN 'jovem_00-30'
    WHEN d.titular_idade <= 50 THEN 'adulto_31-50'
    ELSE 'senior_51+'
  END AS perfil_idade,
  d.titular_idade AS idade,
  IFNULL(d.titular_main_cronico_sn, 'N') AS cronico,
  IFNULL(d.dependents_per_holder, 0) AS dependentes,
  CASE
    WHEN IFNULL(d.dependents_per_holder, 0) = 0 THEN 'sem_dep'
    WHEN d.dependents_per_holder <= 2 THEN '1-2_dep'
    ELSE '3+_dep'
  END AS faixa_dependentes,
  IFNULL(d.classe_social, '(sem dados)') AS classe_social,

  -- Sinais de uso
  IFNULL(d.consumo_sn, 'N') AS consumiu,
  IFNULL(d.total_itens_usados, 0) AS total_itens,
  IFNULL(d.qtd_cm, 0) AS qtd_consultas,
  IFNULL(d.qtd_exames, 0) AS qtd_exames,
  IFNULL(d.qtd_tele, 0) AS qtd_tele,

  -- Recência do uso
  uu.data_ultimo_uso,
  DATE_DIFF(CURRENT_DATE(), uu.data_ultimo_uso, DAY) AS dias_sem_uso,

  -- Sinais de pagamento
  IFNULL(fp.total_tentativas, 0) AS pgto_tentativas_90d,
  IFNULL(fp.tentativas_falha, 0) AS pgto_falhas_90d,
  IFNULL(fp.tentativas_sucesso, 0) AS pgto_sucessos_90d,
  fp.ultima_falha AS pgto_ultima_falha,
  fp.ultimo_sucesso AS pgto_ultimo_sucesso,

  -- Flag de urgência
  CASE
    WHEN ca.flag_unsubscription THEN 'CANCELOU'
    WHEN ca.dias_ate_vencimento < 0 THEN 'VENCIDO'
    WHEN ca.dias_ate_vencimento <= 7 THEN 'URGENTE'
    WHEN ca.dias_ate_vencimento <= 30 THEN 'ATENCAO'
    ELSE 'ACOMPANHAR'
  END AS urgencia

FROM contratos_ativos ca
LEFT JOIN demo d ON d.contract_id = ca.contract_id
LEFT JOIN ultimo_uso uu ON uu.payment_id = ca.contract_id
LEFT JOIN falhas_pgto fp ON fp.account_id = ca.account_id

ORDER BY ca.dias_ate_vencimento ASC;
