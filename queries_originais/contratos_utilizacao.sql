-- contratos_utilizacao

with tbl_ri_itens as (
  SELECT
    y.account_id,
    y.contract_id,
    -- y.id_paciente,
    y.person_id,
    y.account_type,
    -- y.order_source,
    -- y.account_register_date,
    -- y.contract_register_date,
    -- y.contract_due_date,
    -- y.account_contract_number,
    -- y.contract_churn_limit_date,    
    -- y.plan_months_duration,
    r.data,
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
  WHERE date_diff(r.data ,y.account_register_date, month) < r.plan_months_duration

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
 )

 select
  ys.contract_id,
  ys.account_id,

  
  -- FLAGS TRIMESTRAIS (0002)
  case when sum(case when riy.meses_ativo in (0,1,2) then 1 else 0 end) > 0 then 'S' else 'N' end as consumo_0002_sn,
  case when sum(case when riy.produto_grupo = 'CM' and riy.meses_ativo in (0,1,2) then 1 else 0 end) > 0 then 'S' else 'N' end as consumo_0002_CM_sn,
  case when sum(case when riy.produto_grupo in ('AC','PD','USG','MICRO') and riy.meses_ativo in (0,1,2) then 1 else 0 end) > 0 then 'S' else 'N' end as consumo_0002_exames_sn,

  -- FLAGS TRIMESTRAIS (0305)
  case when sum(case when riy.meses_ativo in (3,4,5) then 1 else 0 end) > 0 then 'S' else 'N' end as consumo_0305_sn,
  case when sum(case when riy.produto_grupo = 'CM' and riy.meses_ativo in (3,4,5) then 1 else 0 end) > 0 then 'S' else 'N' end as consumo_0305_CM_sn,
  case when sum(case when riy.produto_grupo in ('AC','PD','USG','MICRO') and riy.meses_ativo in (3,4,5) then 1 else 0 end) > 0 then 'S' else 'N' end as consumo_0305_exames_sn,

  -- FLAGS TRIMESTRAIS (0608)
  case when sum(case when riy.meses_ativo in (6,7,8) then 1 else 0 end) > 0 then 'S' else 'N' end as consumo_0608_sn,
  case when sum(case when riy.produto_grupo = 'CM' and riy.meses_ativo in (6,7,8) then 1 else 0 end) > 0 then 'S' else 'N' end as consumo_0608_CM_sn,
  case when sum(case when riy.produto_grupo in ('AC','PD','USG','MICRO') and riy.meses_ativo in (6,7,8) then 1 else 0 end) > 0 then 'S' else 'N' end as consumo_0608_exames_sn,

  -- FLAGS TRIMESTRAIS (0911)
  case when sum(case when riy.meses_ativo in (9,10,11) then 1 else 0 end) > 0 then 'S' else 'N' end as consumo_0911_sn,
  case when sum(case when riy.produto_grupo = 'CM' and riy.meses_ativo in (9,10,11) then 1 else 0 end) > 0 then 'S' else 'N' end as consumo_0911_CM_sn,
  case when sum(case when riy.produto_grupo in ('AC','PD','USG','MICRO') and riy.meses_ativo in (9,10,11) then 1 else 0 end) > 0 then 'S' else 'N' end as consumo_0911_exames_sn,
  
  -- FLAGS TRIMESTRAIS (0911)
  case when sum(case when riy.meses_ativo between 1 and 12 then 1 else 0 end) > 0 then 'S' else 'N' end as consumo_sn,
  case when sum(case when riy.produto_grupo = 'CM' and riy.meses_ativo between 1 and 12 then 1 else 0 end) > 0 then 'S' else 'N' end as consumo_CM_sn,
  case when sum(case when riy.produto_grupo in ('AC','PD','USG','MICRO') and riy.meses_ativo between 1 and 12 then 1 else 0 end) > 0 then 'S' else 'N' end as consumo_exames_sn,

  -- riy.plan_months_duration,
  -- riy.account_register_date,
  -- riy.contract_due_date,
  -- riy.contract_register_date,
  -- riy.contract_churn_limit_date,
  -- riy.contract_churn_status,
  -- riy.order_source,
  
  sum(case when riy.produto_grupo = 'CM' and unidade not in ('TELE') then  riy.qtd_itens else 0 end ) as qtd_TOTAL_CM,
  sum(case when riy.produto_grupo in ('AC','PD','USG','MICRO') then  riy.qtd_itens else 0 end ) as qtd_TOTAL_EXAMES,  
  sum(case when riy.produto_grupo = 'CM' and unidade in ('TELE') then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_TELE,  
  sum(case when riy.produto_grupo = 'CM' and unidade not in ('TELE') and executante_especialidade = 'CLINICA MEDICA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_CLINICA_MEDICA,
  sum(case when riy.produto_grupo = 'CM' and unidade not in ('TELE') and executante_especialidade = 'GINECOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_GINECOLOGIA,
  sum(case when riy.produto_grupo = 'CM' and unidade not in ('TELE') and executante_especialidade = 'CARDIOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_CARDIOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and unidade not in ('TELE') and executante_especialidade = 'DERMATOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_DERMATOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and unidade not in ('TELE') and executante_especialidade = 'ENDOCRINOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_ENDOCRINOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and unidade not in ('TELE') and executante_especialidade = 'GASTROENTEROLOGISTA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_GASTROENTEROLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and unidade not in ('TELE') and executante_especialidade = 'NEUROLOGIA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_NEUROLOGIA,
  sum(case when riy.produto_grupo = 'CM' and unidade not in ('TELE') and executante_especialidade = 'OFTALMOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_OFTALMOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and unidade not in ('TELE') and executante_especialidade = 'ORTOPEDISTA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_ORTOPEDISTA,
  sum(case when riy.produto_grupo = 'CM' and unidade not in ('TELE') and executante_especialidade = 'OTORRINOLARINGOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_OTORRINOLARINGOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and unidade not in ('TELE') and executante_especialidade = 'PEDIATRA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_PEDIATRA,
  sum(case when riy.produto_grupo = 'CM' and unidade not in ('TELE') and executante_especialidade = 'PSIQUIATRIA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_PSIQUIATRIA,
  sum(case when riy.produto_grupo = 'CM' and unidade not in ('TELE') and executante_especialidade = 'UROLOGISTA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_UROLOGISTA,

  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (0,1,2) and unidade not in ('TELE') then riy.qtd_itens else 0 end ) as qtd_0002_CM,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (0,1,2) and unidade in ('TELE') then riy.qtd_itens else 0 end ) as qtd_0002_CM_TELE,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (0,1,2) and unidade not in ('TELE')  and executante_especialidade = 'CLINICA MEDICA' then riy.qtd_itens else 0 end ) as qtd_0002_CM_CLINICA_MEDICA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (0,1,2) and unidade not in ('TELE')  and executante_especialidade = 'GINECOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0002_CM_GINECOLOGIA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (0,1,2) and unidade not in ('TELE')  and executante_especialidade = 'CARDIOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0002_CM_CARDIOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (0,1,2) and unidade not in ('TELE')  and executante_especialidade = 'DERMATOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0002_CM_DERMATOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (0,1,2) and unidade not in ('TELE')  and executante_especialidade = 'ENDOCRINOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0002_CM_ENDOCRINOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (0,1,2) and unidade not in ('TELE')  and executante_especialidade = 'GASTROENTEROLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0002_CM_GASTROENTEROLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (0,1,2) and unidade not in ('TELE')  and executante_especialidade = 'NEUROLOGIA' then riy.qtd_itens else 0 end ) as qtd_0002_CM_NEUROLOGIA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (0,1,2) and unidade not in ('TELE')  and executante_especialidade = 'OFTALMOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0002_CM_OFTALMOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (0,1,2) and unidade not in ('TELE')  and executante_especialidade = 'ORTOPEDISTA' then riy.qtd_itens else 0 end ) as qtd_0002_CM_ORTOPEDISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (0,1,2) and unidade not in ('TELE')  and executante_especialidade = 'OTORRINOLARINGOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0002_CM_OTORRINOLARINGOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (0,1,2) and unidade not in ('TELE')  and executante_especialidade = 'PEDIATRA' then riy.qtd_itens else 0 end ) as qtd_0002_CM_PEDIATRA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (0,1,2) and unidade not in ('TELE')  and executante_especialidade = 'PSIQUIATRIA' then riy.qtd_itens else 0 end ) as qtd_0002_CM_PSIQUIATRIA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (0,1,2) and unidade not in ('TELE')  and executante_especialidade = 'UROLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0002_CM_UROLOGISTA,

  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (3,4,5) and unidade not in ('TELE') then riy.qtd_itens else 0 end ) as qtd_0305_CM,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (3,4,5) and unidade in ('TELE') then riy.qtd_itens else 0 end ) as qtd_0305_CM_TELE,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (3,4,5) and unidade not in ('TELE')  and executante_especialidade = 'CLINICA MEDICA' then riy.qtd_itens else 0 end ) as qtd_0305_CM_CLINICA_MEDICA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (3,4,5) and unidade not in ('TELE')  and executante_especialidade = 'GINECOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0305_CM_GINECOLOGIA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (3,4,5) and unidade not in ('TELE')  and executante_especialidade = 'CARDIOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0305_CM_CARDIOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (3,4,5) and unidade not in ('TELE')  and executante_especialidade = 'DERMATOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0305_CM_DERMATOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (3,4,5) and unidade not in ('TELE')  and executante_especialidade = 'ENDOCRINOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0305_CM_ENDOCRINOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (3,4,5) and unidade not in ('TELE')  and executante_especialidade = 'GASTROENTEROLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0305_CM_GASTROENTEROLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (3,4,5) and unidade not in ('TELE')  and executante_especialidade = 'NEUROLOGIA' then riy.qtd_itens else 0 end ) as qtd_0305_CM_NEUROLOGIA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (3,4,5) and unidade not in ('TELE')  and executante_especialidade = 'OFTALMOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0305_CM_OFTALMOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (3,4,5) and unidade not in ('TELE')  and executante_especialidade = 'ORTOPEDISTA' then riy.qtd_itens else 0 end ) as qtd_0305_CM_ORTOPEDISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (3,4,5) and unidade not in ('TELE')  and executante_especialidade = 'OTORRINOLARINGOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0305_CM_OTORRINOLARINGOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (3,4,5) and unidade not in ('TELE')  and executante_especialidade = 'PEDIATRA' then riy.qtd_itens else 0 end ) as qtd_0305_CM_PEDIATRA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (3,4,5) and unidade not in ('TELE')  and executante_especialidade = 'PSIQUIATRIA' then riy.qtd_itens else 0 end ) as qtd_0305_CM_PSIQUIATRIA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (3,4,5) and unidade not in ('TELE')  and executante_especialidade = 'UROLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0305_CM_UROLOGISTA,

  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (6,7,8) and unidade not in ('TELE') then riy.qtd_itens else 0 end ) as qtd_0608_CM,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (6,7,8) and unidade in ('TELE') then riy.qtd_itens else 0 end ) as qtd_0608_CM_TELE,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (6,7,8) and unidade not in ('TELE') and executante_especialidade = 'CLINICA MEDICA' then riy.qtd_itens else 0 end ) as qtd_0608_CM_CLINICA_MEDICA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (6,7,8) and unidade not in ('TELE') and executante_especialidade = 'GINECOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0608_CM_GINECOLOGIA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (6,7,8) and unidade not in ('TELE') and executante_especialidade = 'CARDIOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0608_CM_CARDIOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (6,7,8) and unidade not in ('TELE') and executante_especialidade = 'DERMATOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0608_CM_DERMATOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (6,7,8) and unidade not in ('TELE') and executante_especialidade = 'ENDOCRINOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0608_CM_ENDOCRINOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (6,7,8) and unidade not in ('TELE') and executante_especialidade = 'GASTROENTEROLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0608_CM_GASTROENTEROLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (6,7,8) and unidade not in ('TELE') and executante_especialidade = 'NEUROLOGIA' then riy.qtd_itens else 0 end ) as qtd_0608_CM_NEUROLOGIA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (6,7,8) and unidade not in ('TELE') and executante_especialidade = 'OFTALMOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0608_CM_OFTALMOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (6,7,8) and unidade not in ('TELE') and executante_especialidade = 'ORTOPEDISTA' then riy.qtd_itens else 0 end ) as qtd_0608_CM_ORTOPEDISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (6,7,8) and unidade not in ('TELE') and executante_especialidade = 'OTORRINOLARINGOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0608_CM_OTORRINOLARINGOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (6,7,8) and unidade not in ('TELE') and executante_especialidade = 'PEDIATRA' then riy.qtd_itens else 0 end ) as qtd_0608_CM_PEDIATRA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (6,7,8) and unidade not in ('TELE') and executante_especialidade = 'PSIQUIATRIA' then riy.qtd_itens else 0 end ) as qtd_0608_CM_PSIQUIATRIA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (6,7,8) and unidade not in ('TELE') and executante_especialidade = 'UROLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0608_CM_UROLOGISTA,

  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (9,10,11) and unidade not in ('TELE') then riy.qtd_itens else 0 end ) as qtd_0911_CM,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (9,10,11) and unidade in ('TELE') then riy.qtd_itens else 0 end ) as qtd_0911_CM_TELE,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (9,10,11) and unidade not in ('TELE') and executante_especialidade = 'CLINICA MEDICA' then riy.qtd_itens else 0 end ) as qtd_0911_CM_CLINICA_MEDICA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (9,10,11) and unidade not in ('TELE') and executante_especialidade = 'GINECOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0911_CM_GINECOLOGIA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (9,10,11) and unidade not in ('TELE') and executante_especialidade = 'CARDIOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0911_CM_CARDIOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (9,10,11) and unidade not in ('TELE') and executante_especialidade = 'DERMATOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0911_CM_DERMATOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (9,10,11) and unidade not in ('TELE') and executante_especialidade = 'ENDOCRINOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0911_CM_ENDOCRINOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (9,10,11) and unidade not in ('TELE') and executante_especialidade = 'GASTROENTEROLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0911_CM_GASTROENTEROLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (9,10,11) and unidade not in ('TELE') and executante_especialidade = 'NEUROLOGIA' then riy.qtd_itens else 0 end ) as qtd_0911_CM_NEUROLOGIA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (9,10,11) and unidade not in ('TELE') and executante_especialidade = 'OFTALMOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0911_CM_OFTALMOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (9,10,11) and unidade not in ('TELE') and executante_especialidade = 'ORTOPEDISTA' then riy.qtd_itens else 0 end ) as qtd_0911_CM_ORTOPEDISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (9,10,11) and unidade not in ('TELE') and executante_especialidade = 'OTORRINOLARINGOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0911_CM_OTORRINOLARINGOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (9,10,11) and unidade not in ('TELE') and executante_especialidade = 'PEDIATRA' then riy.qtd_itens else 0 end ) as qtd_0911_CM_PEDIATRA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (9,10,11) and unidade not in ('TELE') and executante_especialidade = 'PSIQUIATRIA' then riy.qtd_itens else 0 end ) as qtd_0911_CM_PSIQUIATRIA,
  sum(case when riy.produto_grupo = 'CM' and meses_ativo in (9,10,11) and unidade not in ('TELE') and executante_especialidade = 'UROLOGISTA' then riy.qtd_itens else 0 end ) as qtd_0911_CM_UROLOGISTA,

  sum(case when riy.produto_grupo in ('AC','PD','USG','MICRO') then  riy.valor else 0 end ) as valor_TOTAL_EXAMES,
  sum(case when riy.produto_grupo in ('AC','PD','USG','MICRO') and meses_ativo in (0,1,2)   then riy.valor else 0 end ) as valor_0002_EXAMES, 
  sum(case when riy.produto_grupo in ('AC','PD','USG','MICRO') and meses_ativo in (3,4,5)   then riy.valor else 0 end ) as valor_0305_EXAMES, 
  sum(case when riy.produto_grupo in ('AC','PD','USG','MICRO') and meses_ativo in (6,7,8)   then riy.valor else 0 end ) as valor_0609_EXAMES, 
  sum(case when riy.produto_grupo in ('AC','PD','USG','MICRO') and meses_ativo in (9,10,11) then riy.valor else 0 end ) as valor_0911_EXAMES 


    FROM
      `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
    left join tbl_ri_itens riy on ys.contract_id = riy.contract_id
    
    where ys.account_type = 'holder'
      and ys.contract_payment_number = 1 
      and ys.contract_due_date_month >= '2024-01-01'
      and ys.contract_due_date_month <   date_trunc(current_date(), month)


group by 
  ys.contract_id,
  ys.account_id
  
  -- riy.plan_months_duration,
  -- riy.account_register_date,
  -- riy.contract_due_date,
  -- riy.contract_register_date,
  -- riy.contract_churn_limit_date,
  -- riy.contract_churn_status,
  -- riy.order_source