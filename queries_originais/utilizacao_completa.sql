-- utilizacao_completa

SELECT
    y.account_id,
    y.contract_id,
    y.id_paciente,
    y.person_id,
    y.account_type,
    -- y.order_source,
    -- y.account_register_date,
    -- y.contract_register_date,
    -- y.contract_due_date,
    -- y.account_contract_number,
    -- y.contract_churn_limit_date,    
    -- y.plan_months_duration,
    CAST(
                  SUBSTR(CAST(format_date('%Y%m', r.data) AS STRING), 1, 4) || '-' || SUBSTR(CAST(format_date('%Y%m', r.data) AS STRING), 5, 2) || '-01' AS DATE
              ) AS date_month,
    format_date('%Y%m', r.data) as periodo,
    -- y.contract_churn_status,
    r.produto_grupo,
    r.produto_retorno_sn,
    r.executante_especialidade,
    r.unidade,
    date_diff(r.data ,y.account_register_date, month) as meses_ativo,
    COUNT(DISTINCT r.id_item) AS qtd_itens,
    SUM(r.valor) AS valor,

  FROM 
 (select  distinct 
    y.account_id,
    y.contract_id,
    y.id_paciente,
    y.person_id,
    y.account_type,
    y.order_source,
    y.account_register_date,
    y.contract_register_date,
    y.contract_due_date,
    y.account_contract_number,
    y.contract_churn_limit_date,
    y.plan_months_duration,    
    y.contract_churn_status,
    yi.id_item,
    r.data,
    -- r.id_paciente,
    r.valor,
    r.produto
  from `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` y 
  INNER JOIN `airflow-datalake-prod.YALO_DW.ref_yalo_itens` yi 
    on yi.payment_id = y.payment_id
    and yi.person_id = y.person_id 
  LEFT JOIN `airflow-datalake-prod.DRC_DW.bi_recepcao_itens` r on r.id_item = yi.id_item
    where y.contract_churn_limit_date_month BETWEEN '2024-01-01'
      AND date_trunc(current_date(), month)
      -- AND y.account_contract_number = 1 
      -- and y.flag_7days_cancellation_account = 0
  ) y
  LEFT JOIN `airflow-datalake-prod.DRC_DW.bi_recepcao_itens` r on r.id_item = y.id_item
  WHERE date_diff(r.data ,y.account_register_date, month) < y.plan_months_duration
  and r.data >= '2024-01-01'

  GROUP BY
    y.account_id,
    y.contract_id,
    y.id_paciente,
    y.person_id,  
    y.account_type,
    y.plan_months_duration,
    y.contract_due_date,
    y.contract_register_date,
    y.contract_churn_limit_date,
    meses_ativo,
    y.account_register_date,
    y.account_contract_number,
    y.contract_churn_status,
    periodo,
    r.data,
    r.unidade,
    r.produto_grupo,
    r.produto_retorno_sn,
    r.order_source,
    r.executante_especialidade