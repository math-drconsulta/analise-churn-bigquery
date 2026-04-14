-- pacientes

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
)

SELECT distinct
    ys.account_id,
    ys.account_register_date,
    ys.account_due_date,
    ys.account_type,

    ys.contract_id,
    ys.person_id,

    pac.sexo as sexo,
    pac.idade as idade,
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
    end as faixa_etaria,

    ifnull(ate_cron.main_cronico_sn,'N') AS main_cronico_sn,
    

    FROM
      `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys

    LEFT JOIN pac ON pac.id_paciente = ys.id_paciente
    LEFT JOIN ate_cron ON ate_cron.id_paciente = ys.id_paciente

    where true 
      and ys.contract_payment_number = 1 
      and ys.contract_churn_limit_date_month >= '2024-01-01'
      and ys.contract_churn_limit_date_month <  date_trunc(current_date(), month)