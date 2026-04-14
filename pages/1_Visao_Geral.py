import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Visão Geral · Churn", page_icon="📊", layout="wide")

# ═══════════════════════════════════════════════════════════════════════
# DICIONÁRIO DE DADOS
# ═══════════════════════════════════════════════════════════════════════
with st.expander("📖 Dicionário de Dados — Análise Univariada", expanded=False):
    st.markdown("""
    | Variável | Significado | Valores Possíveis |
    |---|---|---|
    | `plan_months_duration` | Duração do plano contratado | `6` ou `12` meses |
    | `account_contract_number` | Ciclo do contrato na conta do paciente | `1o contrato` (primeira vez) ou `2o+ contrato` (renovação/recompra) |
    | `dependentes_faixa` | Quantidade de dependentes vinculados ao titular | `0 (sem dep.)`, `1-2 dep.`, `3+ dep.` |
    | `titular_faixa_etaria` | Faixa etária do titular do plano | `00-10`, `11-20`, `21-30`, `31-40`, `41-50`, `51-60`, `61-70`, `71-80`, `81-90`, `91-99` |
    | `titular_sexo` | Sexo biológico informado | `F` (feminino), `M` (masculino), `I` (indeterminado) |
    | `classe_social` | Classificação socioeconômica estimada (Serasa/IBGE) | `A++`, `A+`, `B1`, `B2`, `C1`, `C2`, `D`, `E`, `(sem dados)` |
    | `titular_cronico` | Se o titular possui alguma doença crônica identificada | `S` (sim) ou `N` (não) |
    | `consumo_sn` | Se o paciente realizou **qualquer** utilização do plano durante a vigência | `S` (sim) ou `N` (não) |
    | `order_source` | Canal de origem da venda | `drc_digital` (site/app), `drc_cm` (clínica médica), `drc_cfp` (central), `b2b`, etc. |
    | `contract_sale_type` | Tipo de transação comercial | `first_contract`, `renewal`, `reactivation`, `other` |
    | `dep_idoso_6099` | Se possui dependente entre 60-99 anos | `S` ou `N` |
    | `dep_jovem_0020` | Se possui dependente entre 0-20 anos | `S` ou `N` |
    | `unsubscription_sn` | Se o paciente solicitou **ativamente** o cancelamento | `S` ou `N` |
    | `pacientes_cluster` | Cluster comportamental pré-definido pelo time de dados | Ex: `Titular_2160_sem_Dependente`, `Titular_6199`, etc. |

    **Métrica:**
    - `churn_rate` = (churners / total_contratos) × 100 — percentual que **não renovou** o contrato.
    """)

# ═══════════════════════════════════════════════════════════════════════
# CARREGAMENTO DOS DADOS
# ═══════════════════════════════════════════════════════════════════════
st.title("📊 Capítulo 1 — Análise Univariada")
st.markdown("""
Cada dimensão isolada e seu impacto no churn. Selecione abaixo para explorar.
Barras = volume, linha vermelha = taxa de churn.
""")

@st.cache_data
def load_data():
    return pd.read_csv("results/univariada.csv")

try:
    df = load_data()
except FileNotFoundError:
    st.error("Arquivo `results/univariada.csv` não encontrado.")
    st.stop()

# ═══════════════════════════════════════════════════════════════════════
# PAINEL DE SELEÇÃO
# ═══════════════════════════════════════════════════════════════════════

# Nomes amigáveis para as dimensões
dim_labels = {
    "plan_months_duration": "Duração do Plano",
    "account_contract_number": "Ciclo do Contrato (1º vs 2º+)",
    "dependentes_faixa": "Faixa de Dependentes",
    "titular_faixa_etaria": "Faixa Etária do Titular",
    "titular_sexo": "Sexo do Titular",
    "classe_social": "Classe Social",
    "titular_cronico": "Doença Crônica (S/N)",
    "consumo_sn": "Consumo do Plano (S/N)",
    "order_source": "Canal de Origem da Venda",
    "contract_sale_type": "Tipo de Venda",
    "dep_idoso_6099": "Tem Dependente Idoso? (60-99 anos)",
    "dep_jovem_0020": "Tem Dependente Jovem? (0-20 anos)",
    "unsubscription_sn": "Solicitou Cancelamento?",
    "pacientes_cluster": "Cluster Comportamental"
}

dims = df["dimensao"].unique().tolist()
dimension = st.selectbox(
    "Selecione a dimensão:",
    options=dims,
    format_func=lambda x: dim_labels.get(x, x)
)

filtered = df[df["dimensao"] == dimension].copy()
filtered = filtered.sort_values("churn_rate", ascending=False)

# ═══════════════════════════════════════════════════════════════════════
# GRÁFICOS
# ═══════════════════════════════════════════════════════════════════════
col_chart, col_detail = st.columns([3, 2])

with col_chart:
    # Gráfico combinado: barras de volume + linha de churn rate
    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=filtered["segmento"],
        y=filtered["total_contratos"],
        name="Total Contratos",
        marker_color="rgba(99, 110, 250, 0.6)",
        yaxis="y",
        text=filtered["total_contratos"].apply(lambda x: f"{x:,.0f}"),
        textposition="outside",
        textfont_size=10,
    ))

    fig.add_trace(go.Scatter(
        x=filtered["segmento"],
        y=filtered["churn_rate"],
        name="Taxa de Churn (%)",
        mode="lines+markers+text",
        marker=dict(size=10, color="crimson"),
        line=dict(width=3, color="crimson"),
        yaxis="y2",
        text=filtered["churn_rate"].apply(lambda x: f"{x}%"),
        textposition="top center",
        textfont=dict(size=11, color="crimson"),
    ))

    fig.update_layout(
        title=f"Volume & Taxa de Churn — {dim_labels.get(dimension, dimension)}",
        xaxis=dict(title="", tickangle=-30),
        yaxis=dict(title="Contratos", showgrid=False),
        yaxis2=dict(title="Churn (%)", overlaying="y", side="right", range=[0, 105]),
        legend=dict(orientation="h", y=1.12),
        height=500,
        margin=dict(t=80),
    )
    st.plotly_chart(fig, use_container_width=True)

with col_detail:
    st.markdown("##### Tabela de Dados")
    display_df = filtered[["segmento", "total_contratos", "churners", "churn_rate"]].copy()
    display_df.columns = ["Segmento", "Contratos", "Churners", "Churn (%)"]
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # Representatividade
    total_base = filtered["total_contratos"].sum()
    st.markdown(f"**Base nesta dimensão:** {total_base:,.0f} contratos")

    # Concentração
    if len(filtered) >= 2:
        top = filtered.iloc[0]
        bot = filtered.iloc[-1]
        spread = round(top["churn_rate"] - bot["churn_rate"], 1)
        st.metric("Spread Máx. de Churn", f"{spread} p.p.",
                  help="Diferença entre o segmento de maior e menor taxa de churn nesta dimensão")

# ═══════════════════════════════════════════════════════════════════════
# INSIGHTS CONTEXTUALIZADOS
# ═══════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("### O que isso significa para o negócio")

insights = {
    "account_contract_number": """
**O 1º contrato concentra o maior risco.**

- 1º contrato: **59,0%** de churn
- 2º+ contrato: **48,7%**
- Gap: **10,3 p.p.**

O padrão é claro: boa parte dos pacientes assina num momento de necessidade aguda ou
por impulso promocional e, sem formar o hábito de uso nos primeiros meses, não renova.
Quem sobrevive ao 1º ciclo já demonstra aderência — a taxa cai quase 10 pontos.

**Ação:** Onboarding clínico nos primeiros 30 dias — agendar 1ª consulta,
lembretes de agendamento, oferta de telemedicina. O objetivo é acionar o primeiro uso
antes que o paciente se distancie.
""",
    "consumo_sn": """
**O paradoxo do consumo: confounding, não causalidade.**

- Consumiu: **58,4%** de churn
- Não consumiu: **52,2%**

Aparentemente quem usa mais cancela mais. Mas esse dado engana: pacientes de 1º contrato
com 12m (churn base altíssimo) são os que mais consomem nos primeiros meses. E quem
"não usa" inclui renovações automáticas silenciosas com churn naturalmente baixo.

Quando controlamos por `account_contract_number` (ver Página 5), o efeito se inverte:
no 2º+ contrato, quem não usa chega a **54%** de churn vs resultados melhores pra quem usa.

**Conclusão:** O consumo protege, mas o efeito só aparece quando isolamos o viés do 1º contrato.
""",
    "dependentes_faixa": """
**Dependentes funcionam como âncora de retenção.**

- Sem dependentes: **60,3%**
- 1-2 dependentes: **55,8%**
- 3+ dependentes: **50,2%**

A lógica é simples: quando o plano cobre filho, cônjuge e pais, cancelar impacta
várias pessoas ao mesmo tempo. O custo percebido de sair sobe com cada dependente.

**Ação:** Campanhas de "Adicione um dependente" com desconto marginal. O custo por
dependente extra é baixo e o ganho de retenção é de ~5 p.p. por faixa.
""",
    "titular_faixa_etaria": """
**Jovens de 21-30 são o segmento mais volátil.**

- 21-30 anos: **63,2%** — pior taxa entre faixas com volume relevante
- 51-60 anos: **51,4%**
- 61-70 anos: **50,1%**

Jovens são saudáveis, usam o plano de forma pontual (emergência, dermatologia) e são
sensíveis a preço. A partir dos 50+, a dependência preventiva — check-ups regulares,
acompanhamento de crônicos — cria retenção natural.

**Ação:** Para jovens, a proposta de valor precisa mudar: telemedicina, saúde mental,
dermatologia, bem-estar — não check-up clássico.
""",
    "titular_cronico": """
**Crônicos são o público mais fiel.**

- Não crônico: **56,2%**
- Crônico: **49,8%**
- Diferença: **6,4 p.p.**

Diabéticos, hipertensos e portadores de condições contínuas dependem de acompanhamento
regular. O plano oferece isso a custo acessível — sair significa perder acesso.

**Ação:** Trilhas de cuidado crônico personalizadas (check-points trimestrais) e,
mais importante, identificar potenciais crônicos entre os não-diagnosticados para
gerar o mesmo efeito de ancoragem.
""",
    "plan_months_duration": """
**Planos de 6 meses retêm melhor.**

- 12 meses: **58,7%**
- 6 meses: **51,8%**
- Diferença: **6,9 p.p.**

Ciclo mais curto = decisão de renovar mais leve + 2 oportunidades/ano de reter.
Nos planos anuais, o paciente tem mais tempo pra acumular insatisfação ou simplesmente
esquecer que assinou.

**Ponto de atenção:** Não é pra abandonar o anual, mas o onboarding nos planos de 12m
precisa ser significativamente mais agressivo nos primeiros 90 dias.
""",
    "unsubscription_sn": """
**A maioria do churn é silencioso.**

- Com pedido de cancelamento: **98,7%** de churn (esperado)
- Sem pedido: **48,7%**

O ponto central: **~88 mil contratos churnam sem o paciente nunca pedir cancelamento**.
O cartão vence, a cobrança falha, o contrato morre. Esses são os recuperáveis — não
tiveram uma experiência negativa explícita.

**Ação:** Régua de retenção pré-vencimento (SMS/WhatsApp, 15-30 dias antes) focada
nesse público. O ROI tende a ser alto justamente porque não há rejeição ativa.
""",
    "order_source": """
**O canal de aquisição impacta diretamente a retenção.**

| Canal | Churn | Contexto |
|---|---|---|
| `b2b` (empresas) | **45,3%** | Paciente não é o pagador direto |
| `drc_cfp` (central) | **52,2%** | Venda consultiva |
| `drc_cm` (clínica) | **55,0%** | Venda presencial pós-consulta |
| `drc_digital` (site/app) | **58,1%** | Venda fria, sem vínculo |
| `psycoai` | **70,4%** | Volume baixo, mas churn preocupante |

B2B retém melhor porque há um terceiro (a empresa) sustentando a relação.
O digital é onde mais se perde — e provavelmente onde mais se investe em aquisição.

**Ação:** Conteúdo educacional pós-venda digital + explorar expansão B2B como canal
de retenção natural.
""",
    "contract_sale_type": """
**Renovações confirmam fidelização; reativações não.**

- `first_contract`: **59,4%**
- `renewal`: **50,2%**
- `reactivation`: **57,8%**
- `other`: **63,1%**

Quem reativa já cancelou uma vez e tende a repetir — o churn é praticamente igual ao
de primeiro contrato. A renovação é o único indicador real de fidelização consolidada.
""",
    "pacientes_cluster": """
**Os clusters confirmam o padrão: responsabilidade por outro reduz churn.**

| Cluster | Churn | Perfil |
|---|---|---|
| Titular 21-60 sem Dependente | **62,4%** | Sozinho, sem ancoragem |
| Titular Consumo PSIQUIATRIA | **61,2%** | Demanda pontual de saúde mental |
| Titular 21-60 com Dependente | **56,5%** | Família começa a proteger |
| Titular 41-60 + Dep. Jovem | **53,8%** | Pais com filhos, engajados |
| Titular 61-99 | **50,4%** | Dependência clínica natural |
| Titular 41-60 + Dep. Idoso | **50,2%** | Cuidador de idoso, muito engajado |

O melhor preditor de retenção é a responsabilidade de cuidar de outro — seja filho,
seja pai idoso. Quem cuida de alguém não sai.
""",
    "dep_idoso_6099": """
**Dependente idoso reduz o churn em 7,5 p.p.**

- Sem idoso: **57,6%**
- Com idoso: **50,1%**

Ter um dependente entre 60-99 anos cria ancoragem por necessidade médica contínua.
O titular não pode cancelar sem comprometer o acesso de saúde de alguém vulnerável.
""",
    "dep_jovem_0020": """
**Dependente jovem tem efeito marginal, mas positivo.**

- Sem jovem: **55,3%**
- Com jovem: **54,1%**
- Diferença: **1,2 p.p.**

O efeito é menor que o do idoso porque jovens usam menos serviços regulares.
A combinação dependente jovem + idoso, porém, é bastante protetora (ver Página 4).
""",
    "titular_sexo": """
**Sexo do titular não diferencia significativamente.**

- Feminino: **55,2%**
- Masculino: **54,1%**
- Indeterminado: **64,7%** — possível problema de qualidade de cadastro

A classificação `I` e `(vazio)` merece atenção do time de dados — provavelmente
são cadastros incompletos, e a taxa alta pode refletir desengajamento geral.
""",
    "classe_social": """
**Classe social não é driver relevante de churn.**

As taxas oscilam entre **52-55%** para todas as classes (A++ a E). A exceção é
**(sem dados)** com **60,7%** — e esse é o insight real: a falta de preenchimento
do cadastro socioeconômico é um proxy de baixo engajamento com a marca.

Paciente que nem preencheu o cadastro provavelmente tem vínculo fraco desde o início.
""",
}

if dimension in insights:
    st.markdown(insights[dimension])
else:
    st.info("Observe a relação entre o *Volume* (barras azuis) e a *Taxa de Churn* (linha vermelha). "
            "Segmentos com alto volume e alta taxa de churn devem ser priorizados em campanhas de retenção.")
