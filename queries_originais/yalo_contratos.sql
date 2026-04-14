-- yalo_contratos

-- CREATE OR REPLACE TABLE `airflow-datalake-prod.YALO_DW.anl_churn_contratos` as 

WITH ate_cron AS (
  SELECT
    ated.id_paciente,
    STRING_AGG(
      DISTINCT CASE
        WHEN Classificacao_Cronico = 1 THEN cc.cid
      END
    ) AS historico_CIDs_Cronica,
    IFNULL(MAX(cc.Classificacao_Cronico), 0) AS cronico_sn,
    IFNULL(MAX(cc.main_cronico_sn), 'N') AS main_cronico_sn
  FROM
    `airflow-datalake-prod.DRC_DW.bi_atendimentos` ated
    LEFT JOIN `airflow-datalake-prod.DRC.atendimentos_diagnosticos` ad ON ated.id_atendimento = ad.id_atendimento
    LEFT JOIN (
      SELECT
        *,
        CASE
          WHEN CLASSIFICACAO = 'CRONICO' THEN 1
          ELSE 0
        END AS Classificacao_Cronico,
        (
          CASE
            WHEN (
              CASE
                WHEN CID_Hipertensao_SN = 'S'
                OR CID_Diabetico_SN = 'S'
                OR CID_Dislipidemia_SN = 'S' THEN 1
                ELSE 0
              END
            ) = 1 THEN 'S'
            ELSE 'N'
          END
        ) AS main_cronico_sn
      FROM
        `airflow-datalake-prod.DePara_BI.DePara_Classificacao_CIDs_aj`
    ) cc ON ad.cid = cc.CID
  GROUP BY
    ated.id_paciente    
),

pac_classe_social as (
  SELECT 
    id_paciente,
    precisao_mapeamento,
    valor_renda_provavel,
    classe_social as Classe_Social,
    date_ref as dt_atualizacao
  FROM `airflow-datalake-prod.geofusion_refined.vw_mapped_pacientes_classe_social`
  QUALIFY ROW_NUMBER() OVER(PARTITION BY id_paciente ORDER BY date_ref DESC) = 1
),

pac_ultimo_valor AS (
  SELECT
    id_paciente,
    LAST_VALUE(NULLIF(sexo, '') IGNORE NULLS) OVER (PARTITION BY id_paciente ORDER BY stamp ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS sexo,
    LAST_VALUE(dt_nasc IGNORE NULLS) OVER (PARTITION BY id_paciente ORDER BY stamp ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS dt_nasc,
    ROW_NUMBER() OVER (PARTITION BY id_paciente ORDER BY stamp DESC) AS row_num
  FROM
    `airflow-datalake-prod.DRC.pacientes_audit`
),


pac AS (
SELECT
  id_paciente,
  sexo,
  dt_nasc,
  DATE_DIFF(CURRENT_DATE(), dt_nasc, YEAR) AS idade,
FROM
  pac_ultimo_valor
WHERE
  row_num = 1
),

y_unsub as (
  SELECT
  ys.contract_id,
  yuns.account_id,
  ANY_VALUE(
      yuns.justification
    HAVING
      MAX(created_at)
  ) AS motivo_saida,
            date( MAX(created_at)) as data_cancelamento 
  FROM `airflow-datalake-prod.yalo.public_unsubscriptions` yuns 
  inner join `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys 
    on yuns.account_id = ys.account_id 
    and date(created_at) <= date_add(ys.due_date, interval 30 day)
    and date(created_at) >= contract_register_date
    and date(created_at) <= contract_due_date
  WHERE titular_account_id IS NULL 

  GROUP BY
    account_id , ys.contract_id
),

tb_pagamento as (
  select
    yalo_sales.account_id, 
    case 
      when yalo_payments.pspReference is not null then 'adyen'
      when yalo_payments.mundipaggOrderId is not null then 'mundpagg'
    end as adquirente,
    yalo_payments.pspReference, 
    yalo_payments.mundipaggOrderId, 
    yalo_payments.status, 
    yalo_payments.paymentMethod, 
    yalo_payments.created_at, 
    yalo_payments.data_adyen

  FROM
    `airflow-datalake-prod.yalo.public_sales` yalo_sales
    LEFT JOIN `airflow-datalake-prod.yalo.prod_ili_orders` yalo_orders ON CAST(yalo_sales.authorization_code AS INT64) = CAST(yalo_orders.orderId AS INT64)
    LEFT JOIN `airflow-datalake-prod.yalo.prod_ili_payment` yalo_payments ON yalo_orders.paymentId = yalo_payments.paymentId

  where true
    and SAFE_CAST(yalo_sales.authorization_code AS INT64) IS NOT NULL
    AND yalo_orders.orderId IS NOT NULL
    
  QUALIFY ROW_NUMBER() OVER(PARTITION BY yalo_sales.account_id ORDER BY yalo_payments.created_at DESC) = 1
),

 t_dependent AS (
      SELECT
        y.account_id,
        y.account_register_date,
        y.account_due_date,
        COUNT(
          DISTINCT CASE WHEN y.account_type = 'dependent' THEN y.person_id END
        ) AS dependents_per_holder,
        MAX(ate.cronico_sn) AS dependente_cronico_sn,
        MAX(ate.main_cronico_sn) AS dependente_main_cronico_sn,
        COUNT(DISTINCT 
          CASE 
            WHEN y.account_type = 'dependent' 
              AND pac.idade >= 60   
            THEN y.person_id END
        ) AS dependents_per_holder_6099,
        COUNT(DISTINCT 
          CASE 
            WHEN y.account_type = 'dependent' 
              AND pac.idade <= 20   
            THEN y.person_id END
        ) AS dependents_per_holder_0020,
      FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` AS y
      LEFT JOIN pac ON pac.id_paciente = y.id_paciente
      LEFT JOIN ate_cron ate ON ate.id_paciente = y.id_paciente
      WHERE
        account_type = 'dependent'
      GROUP BY
        account_id,
        y.account_register_date,
        y.account_due_date
),

tbl_ri_itens as (
  SELECT
    y.account_id,
    y.contract_id,
    y.person_id,
    y.account_type,
    r.data,
    format_date('%Y%m', r.data) as periodo,
    r.produto_grupo,
    r.produto_retorno_sn,
    r.executante_especialidade,
    r.unidade,
    date_diff(r.data ,y.account_register_date, month) as meses_ativo,
    COUNT(DISTINCT r.id_recepcao) as qtd_visitas,
    COUNT(DISTINCT r.id_item) AS qtd_itens,
    SUM(r.valor) AS valor,

  FROM 
  (select distinct 
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
    yi.id_recepcao,
    yi.id_item,
    r.data,
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
 ),

yalo_contrato_principal_CM as ( 
  SELECT 
      contract_id,
      unidade,
      SUM(qtd_visitas) AS total_visitas
  FROM 
      tbl_ri_itens 
  GROUP BY 
      contract_id, 
      unidade
  QUALIFY 
      ROW_NUMBER() OVER (PARTITION BY contract_id ORDER BY SUM(qtd_visitas) DESC) = 1
),

yalo_contrato_consumo as (
 select
  ys.contract_id,
  ys.account_id,
  case when riy.contract_id is not null then 'S' else 'N' end as consumo_sn,  
  sum(qtd_visitas ) as qtd_TOTAL_vistas,  
  sum(case when riy.produto_grupo = 'CM' then  riy.qtd_itens else 0 end ) as qtd_TOTAL_CM,
  sum(case when riy.produto_grupo in ('AC','PD','USG','MICRO') then  riy.qtd_itens else 0 end ) as qtd_TOTAL_EXAMES,  
  sum(case when riy.produto_grupo = 'CM' and unidade in ('TELE') then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_TELE,  
  sum(case when riy.produto_grupo = 'CM' and executante_especialidade = 'CLINICA MEDICA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_CLINICA_MEDICA,
  sum(case when riy.produto_grupo = 'CM' and executante_especialidade = 'GINECOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_GINECOLOGIA,
  sum(case when riy.produto_grupo = 'CM' and executante_especialidade = 'CARDIOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_CARDIOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and executante_especialidade = 'DERMATOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_DERMATOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and executante_especialidade = 'ENDOCRINOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_ENDOCRINOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and executante_especialidade = 'GASTROENTEROLOGISTA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_GASTROENTEROLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and executante_especialidade = 'NEUROLOGIA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_NEUROLOGIA,
  sum(case when riy.produto_grupo = 'CM' and executante_especialidade = 'OFTALMOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_OFTALMOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and executante_especialidade = 'ORTOPEDISTA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_ORTOPEDISTA,
  sum(case when riy.produto_grupo = 'CM' and executante_especialidade = 'OTORRINOLARINGOLOGISTA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_OTORRINOLARINGOLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and executante_especialidade = 'PEDIATRA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_PEDIATRA,
  sum(case when riy.produto_grupo = 'CM' and executante_especialidade = 'PSIQUIATRIA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_PSIQUIATRIA,
  sum(case when riy.produto_grupo = 'CM' and executante_especialidade = 'UROLOGISTA' then riy.qtd_itens else 0 end ) as qtd_TOTAL_CM_UROLOGISTA,
  sum(case when riy.produto_grupo = 'CM' and executante_especialidade = 'PSIQUIATRIA' and riy.account_type = 'holder' then riy.qtd_itens else 0 end ) as qtd_holder_CM_PSIQUIATRIA,


  FROM
    `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  left join tbl_ri_itens riy on ys.contract_id = riy.contract_id
  
  where ys.account_type = 'holder'
    and ys.contract_payment_number = 1 
    and ys.contract_churn_limit_date_month >= '2024-01-01'
    and ys.contract_churn_limit_date_month <  date_trunc(current_date(), month)


group by 
  ys.contract_id,
  ys.account_id,
  consumo_sn
) 


SELECT distinct
    ys.account_id,
    ys.account_register_date,
    ys.account_due_date,
    ys.order_source_aj,
    ys.contract_id,
    ys.contract_register_date,
    ys.contract_register_date_month,
    ys.contract_due_date,
    ys.contract_due_date_month,
    ys.contract_churn_limit_date,
    ys.contract_churn_limit_date_month,
    ys.contract_churn_status,
    ys.contract_sale_type,
    ys.account_contract_number,

    -- [NOVAS COLUNAS DE CHURN ADICIONADAS AQUI]
    CASE 
      WHEN DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) > 7 THEN 'N' 
      ELSE 'S' 
    END as churn_renovacao_automatica_sn,

    CASE 
      WHEN ys.days_diff_until_next_contract BETWEEN -30 AND 60 THEN 'N' 
      ELSE 'S' 
    END as churn_renovacao_60_dias_sn,
    -- [FIM DAS NOVAS COLUNAS]

    ys.person_id as holder_person_id,
    ys.id_paciente as holder_id_paciente,
    ys.plan_name,
    ys.plan_months_duration,
    ys.order_payment_method,
    ys.order_source,
    ys.order_term,
    ys.flag_7days_cancellation_account,
    -- ys.flag_is_in_legacy,
    -- ys.flag_is_in_legacy_active_eop,

    pac.sexo as titular_sexo,
    pac.idade as  titular_idade,
    case 
      when pac.idade <= 10 then '00-10' 
      when pac.idade <= 20 then '11-20' 
      when pac.idade <= 30 then '21-30' 
      when pac.idade <= 40 then '31-40' 
      when pac.idade <= 50 then '41-50' 
      when pac.idade <= 60 then '51-60' 
      when pac.idade <= 70 then '61-70' 
      when pac.idade <= 80 then '71-80' 
      when pac.idade <= 90 then '81-90'  
      when pac.idade < 100 then '91-99'
      else '99+'
    end as titular_faixa_etaria,

    pac_classe_social.Classe_social as titual_classe_social,

    case when unsubs.account_id is not null then 'S' else 'N' end as unsubscription_sn,
    unsubs.motivo_saida as unsubscription_reason,    
    unsubs.data_cancelamento as unsubscription_date,

    ifnull(ate_cron.main_cronico_sn,'N') AS titular_main_cronico_sn,

    coalesce(t_dependent.dependents_per_holder,0) as dependents_per_holder,
    t_dependent.dependente_cronico_sn,
    t_dependent.dependente_main_cronico_sn,
    t_dependent.dependents_per_holder_0020,
    t_dependent.dependents_per_holder_6099,
    case when t_dependent.dependents_per_holder_0020 > 0 then 'S' else 'N' END as dependents_per_holder_0020_SN,    
    case when t_dependent.dependents_per_holder_6099 > 0 then 'S' else 'N' END as dependents_per_holder_6099_SN,
    

    tb_pagamento.adquirente,
    tb_pagamento.pspReference, 
    tb_pagamento.mundipaggOrderId, 
    tb_pagamento.status as payment_status, 
    
    yalo_contrato_consumo.consumo_sn,  
    yalo_contrato_consumo.qtd_TOTAL_CM,
    yalo_contrato_consumo.qtd_TOTAL_EXAMES,  
    yalo_contrato_consumo.qtd_TOTAL_CM_TELE,  
    yalo_contrato_consumo.qtd_TOTAL_CM_CLINICA_MEDICA,
    yalo_contrato_consumo.qtd_TOTAL_CM_GINECOLOGIA,
    yalo_contrato_consumo.qtd_TOTAL_CM_CARDIOLOGISTA,
    yalo_contrato_consumo.qtd_TOTAL_CM_DERMATOLOGISTA,
    yalo_contrato_consumo.qtd_TOTAL_CM_ENDOCRINOLOGISTA,
    yalo_contrato_consumo.qtd_TOTAL_CM_GASTROENTEROLOGISTA,
    yalo_contrato_consumo.qtd_TOTAL_CM_NEUROLOGIA,
    yalo_contrato_consumo.qtd_TOTAL_CM_OFTALMOLOGISTA,
    yalo_contrato_consumo.qtd_TOTAL_CM_ORTOPEDISTA,
    yalo_contrato_consumo.qtd_TOTAL_CM_OTORRINOLARINGOLOGISTA,
    yalo_contrato_consumo.qtd_TOTAL_CM_PEDIATRA,
    yalo_contrato_consumo.qtd_TOTAL_CM_PSIQUIATRIA,
    yalo_contrato_consumo.qtd_TOTAL_CM_UROLOGISTA,

    yalo_contrato_principal_CM.unidade as contract_unidade_principal,

    -- Clusters 
    CASE 
      WHEN pac.idade >= 41 
        AND pac.idade <= 60
        AND t_dependent.dependents_per_holder_6099 > 0 
        THEN 'Titular_4160_Dependente_6099' 
      WHEN pac.idade >= 41 
        AND pac.idade <= 60
        AND t_dependent.dependents_per_holder_0020 > 0 
        THEN 'Titular_4160_Dependente_0020'
      WHEN yalo_contrato_consumo.qtd_holder_CM_PSIQUIATRIA > 2 
        then 'Titular_Consumo_PSIQUIATRIA'
      WHEN pac.idade >= 61 
        THEN 'Titular_6199' 
      WHEN pac.idade >= 21 
        AND pac.idade <= 60
        AND ifnull(t_dependent.dependents_per_holder,0) = 0 
        THEN 'Titular_2160_sem_Dependente'
      WHEN pac.idade >= 21 
        AND pac.idade <= 60
        AND ifnull(t_dependent.dependents_per_holder,0) > 0 
        THEN 'Titular_2160_com_Dependente'
      ELSE 'Outros'
    END as pacientes_cluster,

    CASE WHEN pac.idade >= 41 
      AND pac.idade <= 60
      AND t_dependent.dependents_per_holder_0020 > 0 
      THEN 'S' ELSE 'N'
    END as Titular_4160_Dependente_0020_SN,
    
    CASE WHEN pac.idade >= 41 
      AND pac.idade <= 60
      AND t_dependent.dependents_per_holder_6099 > 0 
      THEN 'S' ELSE 'N'
    END as Titular_4160_Dependente_6099_SN,

    CASE WHEN pac.idade >= 61 
      THEN 'S' ELSE 'N'
    END as Titular_6099_SN,

    case when yalo_contrato_consumo.qtd_holder_CM_PSIQUIATRIA > 2 then 'S' else 'N' end as consumo_Holder_PSIQUIATRIA_SN,
    case when yalo_contrato_consumo.qtd_TOTAL_CM_PSIQUIATRIA > 2 then 'S' else 'N' end as consumo_TOTAL_PSIQUIATRIA_SN,

    FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
    LEFT JOIN t_dependent ON t_dependent.account_id = ys.account_id
    LEFT JOIN y_unsub unsubs ON unsubs.account_id = ys.account_id and unsubs.contract_id = ys.contract_id
    LEFT JOIN pac ON pac.id_paciente = ys.id_paciente
    LEFT JOIN ate_cron ON ate_cron.id_paciente = ys.id_paciente
    LEFT JOIN tb_pagamento on tb_pagamento.account_id = ys.account_id
    LEFT JOIN pac_classe_social on pac_classe_social.id_paciente = ys.id_paciente
    LEFT JOIN yalo_contrato_consumo on yalo_contrato_consumo.contract_id = ys.contract_id
    LEFT JOIN yalo_contrato_principal_CM on yalo_contrato_principal_CM.contract_id = ys.contract_id

    where ys.account_type = 'holder'
      and ys.contract_payment_number = 1 
      and ys.contract_due_date >= '2024-01-01'
      and ys.contract_due_date <  date_trunc(current_date(), month)