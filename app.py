import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="dr.consulta · Churn Intelligence",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Header ──────────────────────────────────────────────────────────────
st.title("Análise de Churn — dr.consulta")
st.caption("Contratos cartão de crédito · Planos de 6 e 12 meses · Últimos 12 meses")

st.markdown("---")

# ── KPIs de contexto ───────────────────────────────────────────────────
@st.cache_data
def load_univariada():
    return pd.read_csv("results/univariada.csv")

@st.cache_data
def load_interacao():
    try: return pd.read_csv("results/interacao_contrato_dep_cronico.csv")
    except: return None

try:
    df = load_univariada()

    total = df[df["dimensao"] == "plan_months_duration"]["total_contratos"].sum()
    churners = df[df["dimensao"] == "plan_months_duration"]["churners"].sum()
    taxa_global = round(100 * churners / total, 1) if total else 0

    df_ciclo = df[df["dimensao"] == "account_contract_number"]
    primeiro = df_ciclo[df_ciclo["segmento"] == "1o contrato"]["churn_rate"].values
    renovacao = df_ciclo[df_ciclo["segmento"] == "2o+ contrato"]["churn_rate"].values

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Contratos Analisados", f"{total:,.0f}")
    k2.metric("Churners", f"{churners:,.0f}")
    k3.metric("Taxa Global de Churn", f"{taxa_global}%")
    if len(primeiro) and len(renovacao):
        delta = round(primeiro[0] - renovacao[0], 1)
        k4.metric("Gap 1º vs 2º+ Contrato", f"{delta} p.p.", delta_color="inverse")
except Exception:
    pass

st.markdown("---")

# ── O QUE ENCONTRAMOS ──────────────────────────────────────────────────
st.markdown("""
### O que encontramos

Analisamos **{total:,.0f} contratos** com vencimento nos últimos 12 meses. Desses, **{churners:,.0f}
não renovaram** — uma taxa de churn de **{taxa_global}%**.

Esse número é alto, mas não é homogêneo. Quando quebramos por perfil, as diferenças são brutais:
o churn vai de **~42%** no melhor cenário até **~65%** no pior. Isso significa que temos
alavancas claras pra atuar.
""".format(total=total, churners=churners, taxa_global=taxa_global))

st.markdown("""
### Os 5 drivers que mais pesam
""")

col1, col2 = st.columns(2)

with col1:
    st.markdown("""
    **1. Ciclo do contrato é o fator dominante**
    > 1º contrato: **59%** de churn — 2º+ contrato: **49%**.
    > Sobreviver ao primeiro ciclo reduz o risco em 10 p.p.
    > O onboarding dos primeiros 30 dias é o momento mais crítico da jornada.

    **2. Dependentes funcionam como âncora de retenção**
    > Sem dependentes: **60%** — 3+ dependentes: **50%**.
    > Quando o plano cuida de mais gente, o custo de saída sobe.
    > Cada dependente adicionado reduz o churn em ~5 p.p.

    **3. Jovens (21-30) são o segmento mais volátil**
    > 21-30 anos: **63%** — 61-70 anos: **50%**.
    > Jovem saudável não sente urgência de manter plano.
    > A partir dos 50+, a dependência preventiva cria retenção natural.
    """)

with col2:
    st.markdown("""
    **4. Doença crônica é o melhor preditor de fidelidade**
    > Crônico: **50%** — Não crônico: **56%**.
    > Quem precisa de acompanhamento contínuo simplesmente não sai.
    > Identificar crônicos não diagnosticados é uma oportunidade de retenção.

    **5. Planos de 6 meses retêm melhor que 12**
    > 6 meses: **52%** — 12 meses: **59%**.
    > O ciclo curto gera menos arrependimento e dá 2 oportunidades/ano de reter.
    > Nos anuais, o onboarding precisa ser muito mais agressivo.
    """)

# Interação
df_int = load_interacao()
if df_int is not None:
    st.markdown("---")
    st.markdown("""
    ### O efeito combinado: de 65% para 42%

    Quando cruzamos ciclo × dependentes × condição crônica, os efeitos se multiplicam.
    Com essas 3 variáveis, já conseguimos separar perfis com precisão relevante:
    """)

    col_pior, col_melhor = st.columns(2)
    pior = df_int.iloc[0]
    melhor = df_int.iloc[-1]

    with col_pior:
        st.error(f"""
        **Perfil de maior risco:**
        - 1º contrato, sem dependentes, não crônico
        - Churn: **{pior['churn_rate']}%**
        - Volume: {int(pior['total_contratos']):,} contratos
        """)

    with col_melhor:
        st.success(f"""
        **Perfil de maior retenção:**
        - 2º+ contrato, 3+ dependentes, crônico
        - Churn: **{melhor['churn_rate']}%**
        - Volume: {int(melhor['total_contratos']):,} contratos
        """)

    st.markdown(f"""
    > A diferença entre os extremos é de **{round(pior['churn_rate'] - melhor['churn_rate'], 1)} p.p.**
    > — com apenas 3 variáveis. Isso confirma que os perfis são acionáveis e que
    > campanhas segmentadas podem ter impacto material no resultado.
    """)

st.markdown("---")

# ── PERGUNTAS QUE OS DADOS LEVANTAM ───────────────────────────────────
st.markdown("""
### Perguntas que os dados levantam

Os números acima apontam para questões que valem discutir:

| Observação | Pergunta |
|---|---|
| O 1º contrato concentra a maior parte do churn | O que acontece nos primeiros meses que leva tantos a não renovar? |
| Dependentes reduzem o churn em ~5 p.p. cada | O custo de saída sobe quando o plano cuida de mais gente — isso é alavancável? |
| ~75% do churn é silencioso (sem pedido de cancelamento) | Quantos desses clientes nem sabiam que estavam saindo? São recuperáveis? |
""")

st.markdown("---")

st.info("⬅️ **Navegue pelo menu lateral** para aprofundar em cada capítulo.")

st.markdown("""
| Capítulo | Conteúdo |
|---|---|
| **0. Resumo Executivo** | Narrativa completa: tamanho do problema, drivers, valor em jogo |
| **1. Visão Geral** | Cada variável isolada e o que ela mostra |
| **2. Risco e Evolução** | Score de risco, sazonalidade, unidades |
| **3. Saúde e Consumo** | Consumo por especialidade e o paradoxo do uso |
| **4. Perfis Compostos** | Cruzamento multivariável — o rosto do churner |
| **5. Análises Avançadas** | Motivos de cancelamento, win-back, churn silencioso vs ativo |
| **6. Conversão Falha Pgto** | Resultado do disparo de email pós-falha de pagamento |
| **8. Insights Negócio** | Anatomia da não-renovação em detalhe |
| **9. Coorte e Retenção** | Curvas de sobrevivência por safra e perfil |
| **10. Impacto Financeiro** | CLV, receita perdida e simulador de ROI |
| **11. Sazonalidade** | Meses críticos e sinais precoces de abandono |
""")

with st.expander("Sobre esta base de dados", expanded=False):
    st.markdown("""
    **Definição de churn:** Contrato cujo vencimento ocorreu e a renovação automática não aconteceu
    (diferença entre `account_due_date` e `contract_due_date` ≤ 7 dias = churn).

    Dois tipos de cancelamento:
    - **Ativo** (~26 mil): paciente solicitou cancelamento
    - **Silencioso** (~88 mil): contrato expirou sem renovação (falha na cobrança, cartão vencido, desinteresse)

    **Escopo:**
    - Pagamento via cartão de crédito
    - Duração de 6 ou 12 meses
    - Vencimentos nos últimos 12 meses
    - Fonte: `airflow-datalake-prod.YALO_DW.anl_churn_contratos`
    """)
