-- ============================================================================
-- CRUZAMENTO SAC × CHURN — Base de contratos com CPF
-- Arquivo: results/contratos_com_cpf.csv
--
-- OBJETIVO: Extrair todos os contratos do universo de churn com CPF limpo,
-- para cruzar com os dados de SAC (que estão em CSV) no Python.
--
-- Fonte principal: ref_yalo_subscriptions (dados frescos até ~out/2027)
--   + public_people (CPF)
--   + anl_churn_contratos (dados demográficos/comportamentais, até mar/2026)
--
-- O JOIN com SAC será feito no Python por CPF normalizado (só dígitos).
--
-- ATENÇÃO:
--   - CPF normalizado = só dígitos, sem pontos/traços (REGEXP_REPLACE)
--   - 1 linha = 1 contrato (holder, deduplicated)
--   - Inclui contratos com vencimento de out/2025 a mai/2026 (mesmo período do SAC)
-- ============================================================================

WITH contratos AS (
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

    -- Mesma definição de churn da anl_churn_contratos
    CASE
      WHEN DATE_DIFF(ys.account_due_date, ys.contract_due_date, DAY) > 7 THEN 'N'
      ELSE 'S'
    END AS churn_sn,

    -- Ciclo
    CASE WHEN ys.account_contract_number = 1 THEN '1o' ELSE '2o+' END AS ciclo

  FROM `airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions` ys
  WHERE ys.account_type = 'holder'
    AND ys.payment_method = 'credit_card'
    AND ys.plan_months_duration IN (6, 12)
    AND ys.plan_name NOT LIKE '%gratis%'
    AND IFNULL(ys.order_source_aj, '') != 'b2b'
    -- Período alinhado com SAC: out/2025 a mai/2026
    AND ys.contract_due_date BETWEEN '2025-10-01' AND '2026-05-31'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY ys.contract_id
    ORDER BY ys.date_month DESC
  ) = 1
),

-- CPF via public_people
cpf_map AS (
  SELECT
    id AS person_id,
    -- Normalizar CPF: remover tudo que não é dígito
    REGEXP_REPLACE(CAST(cpf AS STRING), r'[^0-9]', '') AS cpf_normalizado
  FROM `airflow-datalake-prod.yalo.public_people`
  WHERE cpf IS NOT NULL
    AND LENGTH(REGEXP_REPLACE(CAST(cpf AS STRING), r'[^0-9]', '')) = 11
),

-- Dados demográficos da anl_churn_contratos (quando disponível)
demo AS (
  SELECT
    contract_id,
    titular_idade,
    IFNULL(titular_main_cronico_sn, 'N') AS cronico,
    IFNULL(dependents_per_holder, 0) AS dependentes,
    IFNULL(consumo_sn, 'N') AS consumiu,
    IFNULL(qtd_TOTAL_CM, 0) + IFNULL(qtd_TOTAL_EXAMES, 0) AS total_itens,
    contract_unidade_principal AS unidade_principal,
    titular_sexo,
    titual_classe_social AS classe_social,
    titular_faixa_etaria
  FROM `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
)

SELECT
  c.contract_id,
  c.account_id,
  cm.cpf_normalizado AS cpf,
  c.contract_register_date,
  c.contract_due_date,
  c.plan_months_duration AS duracao,
  c.ciclo,
  c.canal,
  c.churn_sn,
  c.flag_unsubscription AS pediu_cancelamento,

  -- Demográficas (podem ser NULL pra contratos fora da anl_churn)
  d.titular_idade AS idade,
  d.titular_faixa_etaria AS faixa_etaria,
  d.cronico,
  d.dependentes,
  d.consumiu,
  d.total_itens,
  d.unidade_principal,
  d.titular_sexo AS sexo,
  d.classe_social,

  -- Classificação de desfecho
  CASE
    WHEN c.churn_sn = 'N' THEN 'retido'
    WHEN c.flag_unsubscription THEN 'churn_ativo'
    ELSE 'churn_silencioso'
  END AS tipo_desfecho

FROM contratos c
LEFT JOIN cpf_map cm ON cm.person_id = c.person_id
LEFT JOIN demo d ON d.contract_id = c.contract_id

ORDER BY c.contract_due_date, c.contract_id;
