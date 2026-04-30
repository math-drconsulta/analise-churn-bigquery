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

@st.cache_data
def load_temporal():
    return pd.read_csv("results/univariada_temporal.csv")

@st.cache_data
def load_evolucao():
    return pd.read_csv("results/unidade_evolucao_score_b.csv")

# Tentar carregar versão temporal; se não existir, usar a original
has_temporal = False
try:
    df_temporal = load_temporal()
    df_temporal["mes_vencimento"] = pd.to_datetime(df_temporal["mes_vencimento"])
    has_temporal = True
except FileNotFoundError:
    pass

try:
    df_base = load_data()
except FileNotFoundError:
    st.error("Arquivo `results/univariada.csv` não encontrado.")
    st.stop()

# ═══════════════════════════════════════════════════════════════════════
# FILTRO DE PERÍODO
# ═══════════════════════════════════════════════════════════════════════
if has_temporal:
    meses_disponiveis = sorted(df_temporal["mes_vencimento"].unique())
    meses_labels = [m.strftime("%b/%Y") for m in meses_disponiveis]

    st.sidebar.markdown("### 📅 Filtro de Período")
    col_de, col_ate = st.sidebar.columns(2)
    with col_de:
        idx_de = st.selectbox("De:", range(len(meses_disponiveis)),
                               format_func=lambda i: meses_labels[i], index=0, key="periodo_de")
    with col_ate:
        idx_ate = st.selectbox("Até:", range(len(meses_disponiveis)),
                                format_func=lambda i: meses_labels[i], index=len(meses_disponiveis)-1, key="periodo_ate")

    if idx_de > idx_ate:
        st.sidebar.error("'De' deve ser anterior ou igual a 'Até'")
        idx_de, idx_ate = idx_ate, idx_de

    mes_ini = meses_disponiveis[idx_de]
    mes_fim = meses_disponiveis[idx_ate]

    st.sidebar.caption(f"Período: {mes_ini.strftime('%b/%Y')} → {mes_fim.strftime('%b/%Y')}")

    # Filtrar e reagregar
    df_filtrado = df_temporal[
        (df_temporal["mes_vencimento"] >= mes_ini) &
        (df_temporal["mes_vencimento"] <= mes_fim)
    ]
    df = df_filtrado.groupby(["dimensao", "segmento"], as_index=False).agg(
        total_contratos=("total_contratos", "sum"),
        churners=("churners", "sum"),
    )
    df["churn_rate"] = round(100.0 * df["churners"] / df["total_contratos"], 1)

    st.info(f"📅 Dados filtrados: **{mes_ini.strftime('%b/%Y')}** a **{mes_fim.strftime('%b/%Y')}** "
            f"({idx_ate - idx_de + 1} meses)")
else:
    df = df_base.copy()
    st.caption("💡 Para habilitar o filtro de período, rode a query `univariada_temporal.sql` e salve como `results/univariada_temporal.csv`.")

# ═══════════════════════════════════════════════════════════════════════
# GRÁFICO TEMPORAL DE CHURN MÊS A MÊS
# ═══════════════════════════════════════════════════════════════════════
try:
    df_evol = load_evolucao()
    df_evol["mes_vencimento"] = pd.to_datetime(df_evol["mes_vencimento"])

    with st.expander("📈 Evolução temporal do churn (mês a mês)", expanded=True):
        # Agregar por mês (somando 6m e 12m)
        df_evol_total = df_evol.groupby("mes_vencimento", as_index=False).agg(
            total_contratos=("total_contratos", "sum"),
            churners=("churners", "sum"),
        )
        df_evol_total["churn_rate"] = round(100.0 * df_evol_total["churners"] / df_evol_total["total_contratos"], 1)

        fig_evol = go.Figure()

        # Linha global
        fig_evol.add_trace(go.Scatter(
            x=df_evol_total["mes_vencimento"],
            y=df_evol_total["churn_rate"],
            name="Geral",
            mode="lines+markers+text",
            line=dict(width=3, color="#1565c0"),
            marker=dict(size=9),
            text=df_evol_total["churn_rate"].apply(lambda x: f"{x}%"),
            textposition="top center",
            textfont=dict(size=10),
        ))

        # Linhas por duração
        for dur, cor in [(6, "#4caf50"), (12, "#ff5722")]:
            sub = df_evol[df_evol["duracao"] == dur].sort_values("mes_vencimento")
            fig_evol.add_trace(go.Scatter(
                x=sub["mes_vencimento"],
                y=sub["churn_rate"],
                name=f"{dur} meses",
                mode="lines+markers",
                line=dict(width=2, color=cor, dash="dot"),
                marker=dict(size=6),
                opacity=0.7,
            ))

        # Barras de volume
        fig_evol.add_trace(go.Bar(
            x=df_evol_total["mes_vencimento"],
            y=df_evol_total["total_contratos"],
            name="Contratos",
            marker_color="rgba(99, 110, 250, 0.15)",
            yaxis="y2",
            showlegend=True,
        ))

        fig_evol.update_layout(
            title="Taxa de Churn Mensal (contratos por mês de vencimento)",
            xaxis=dict(title="", tickformat="%b/%Y"),
            yaxis=dict(title="Churn (%)", range=[40, 70]),
            yaxis2=dict(title="Contratos", overlaying="y", side="right", showgrid=False),
            legend=dict(orientation="h", y=1.15),
            height=420,
            hovermode="x unified",
        )
        st.plotly_chart(fig_evol, use_container_width=True)

        # Métricas de tendência
        if len(df_evol_total) >= 3:
            ultimo = df_evol_total.iloc[-1]["churn_rate"]
            penultimo = df_evol_total.iloc[-2]["churn_rate"]
            media = round(df_evol_total["churn_rate"].mean(), 1)
            c1, c2, c3 = st.columns(3)
            c1.metric("Último mês", f"{ultimo}%", delta=f"{round(ultimo - penultimo, 1)} p.p.")
            c2.metric("Média 12 meses", f"{media}%")
            c3.metric("Amplitude", f"{round(df_evol_total['churn_rate'].max() - df_evol_total['churn_rate'].min(), 1)} p.p.",
                       help="Diferença entre o mês com maior e menor churn")

except FileNotFoundError:
    pass

st.markdown("---")

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
    # ─── TIER 1: DRIVERS FORTES (~10 p.p. controlado) ───────────────────
    "account_contract_number": """
**#1 DRIVER — O 1º contrato concentra o maior risco.**

- 1º contrato: **59,2%** de churn
- 2º+ contrato: **48,7%**
- Gap: **10,5 p.p.** (robusto — se mantém controlando por todas as outras variáveis)

É o fator mais forte e mais "causal": quem sobrevive ao 1º ciclo já demonstrou
aderência real. A queda de ~10 p.p. não é confounding — é seleção genuína.

**Ação:** Onboarding clínico nos primeiros 30 dias — agendar 1ª consulta,
lembretes de agendamento, oferta de telemedicina. O objetivo é acionar o primeiro uso
antes que o paciente se distancie.
""",
    "dependentes_faixa": """
**#2 DRIVER — Dependentes funcionam como âncora de retenção.**

- Sem dependentes: **60,3%**
- 1-2 dependentes: **55,9%**
- 3+ dependentes: **50,4%**
- Gap controlado: **~8-9 p.p.** (testado dentro de 1o e 2o+ contrato — se mantém)

Quando o plano cobre filho, cônjuge e pais, cancelar impacta várias pessoas.
O custo percebido de sair sobe com cada dependente. O efeito é real e não se
confunde com idade ou ciclo do contrato.

**Ação:** Campanhas de "Adicione um dependente" com desconto marginal. O custo por
dependente extra é baixo e o ganho de retenção é de ~5 p.p. por faixa.
""",
    "titular_faixa_etaria": """
**#3 DRIVER — Jovens de 21-30 são o segmento mais volátil.**

- 21-30 anos: **63,6%** — pior taxa entre faixas com volume relevante
- 51-60 anos: **51,8%**
- 61-70 anos: **50,1%**
- Gap controlado: **~10-12 p.p.** entre jovens e 50+

A idade é o terceiro maior driver. Parte do efeito vem de jovens serem menos
crônicos — mas mesmo controlando por doença crônica, a idade continua relevante:
jovens são saudáveis, usam o plano de forma pontual e são sensíveis a preço.

**Ação:** Para jovens, a proposta de valor precisa mudar: telemedicina, saúde mental,
dermatologia, bem-estar — não check-up clássico.
""",
    # ─── TIER 2: DRIVERS MODERADOS (~5-7 p.p. controlado) ──────────────
    "plan_months_duration": """
**#4 DRIVER — Planos de 12 meses retêm pior.**

- 12 meses: **59,0%**
- 6 meses: **51,8%**
- Gap aparente: **7,2 p.p.** | Gap controlado: **4,8-9,0 p.p.**

Parte do gap se explica porque 12m tem mais 1o contratos (65% vs 57% no 6m).
Mas controlando por ciclo, o efeito **persiste**: no 2o+ contrato, 12m tem 54,0%
vs 45,0% no 6m — uma diferença de **9 p.p.** Ciclo mais longo dá mais tempo
para o paciente acumular insatisfação ou esquecer que assinou.

**Ponto de atenção:** Não é pra abandonar o anual, mas o onboarding nos planos de 12m
precisa ser significativamente mais agressivo nos primeiros 90 dias.
""",
    "titular_cronico": """
**#5 DRIVER — Crônicos são mais fiéis, mas menos do que parece.**

- Não crônico: **56,4%**
- Crônico: **49,9%**
- Gap aparente: **6,5 p.p.** | Gap controlado por idade: **~3,5-4,6 p.p.**

Atenção: a idade se disfarça de crônico. Como 37,7% dos 71+ são crônicos (vs 0,9%
dos ≤30), o gap aparente de 6,5 p.p. inclui o efeito da idade. Controlando por
faixa etária, o efeito real cai para **~3,5-4,6 p.p.** — ainda relevante, mas metade
do que a univariada sugere. Nos jovens (≤30), crônico praticamente não faz diferença.

**Ação:** Trilhas de cuidado crônico personalizadas (check-points trimestrais),
mas focar em pacientes 31+ onde o efeito é real. Em jovens, a retenção depende
mais de outros fatores (dependentes, onboarding).
""",
    # ─── TIER 3: VARIÁVEIS CONTEXTUAIS (sem efeito controlado forte) ───
    "consumo_sn": """
**VARIÁVEL CONFOUNDED — O paradoxo do consumo.**

- Consumiu: **58,7%** de churn
- Não consumiu: **52,1%**

Aparentemente quem usa mais cancela mais. Mas esse dado engana: pacientes de 1º contrato
com 12m (churn base altíssimo) são os que mais consomem nos primeiros meses. E quem
"não usa" inclui renovações automáticas silenciosas com churn naturalmente baixo.

Quando controlamos por `account_contract_number` (ver Página 5), o efeito se inverte:
no 2º+ contrato, quem não usa chega a **54%** de churn vs resultados melhores pra quem usa.

**Por isso, `consumo_sn` foi removido dos perfis compostos (Página 4).**
Usá-lo como variável de segmentação sem controlar pelo ciclo gera clusters enviesados.
""",
    "unsubscription_sn": """
**VARIÁVEL OPERACIONAL — A maioria do churn é silencioso.**

- Com pedido de cancelamento: **98,7%** de churn (esperado)
- Sem pedido: **48,7%**

O ponto central: **~87 mil contratos churnam sem o paciente nunca pedir cancelamento**.
O cartão vence, a cobrança falha, o contrato morre. Esses são os recuperáveis — não
tiveram uma experiência negativa explícita.

**Ação:** Régua de retenção pré-vencimento (SMS/WhatsApp, 15-30 dias antes) focada
nesse público. O ROI tende a ser alto justamente porque não há rejeição ativa.
""",
    "order_source": """
**VARIÁVEL CONTEXTUAL — O canal de aquisição impacta a retenção.**

*B2B excluído na query (dinâmica comercial diferente):*

| Canal | Churn | Volume | Contexto |
|---|---|---|---|
| `drc_cfp` (central) | **52,2%** | 55.466 | Venda consultiva, melhor retenção B2C |
| `others` | **52,1%** | 15.494 | Categoria agrupada |
| `drc_cm` (clínica) | **55,0%** | 60.978 | Venda presencial pós-consulta |
| `drc_digital` (site/app) | **58,1%** | 71.950 | Maior volume, mas maior churn |
| `psycoai` | **70,4%** | 291 | Volume residual, churn crítico |

O digital concentra **35% da base** e tem o segundo pior churn entre os canais B2C.
A central telefônica (`drc_cfp`) retém melhor — provável efeito da venda consultiva.

**Nota:** O canal pode estar confundido com perfil de paciente — quem compra pelo
digital pode ser mais jovem e com menos dependentes.

**Ação:** Investir em conteúdo educacional pós-venda digital e considerar um fluxo
de ligação de boas-vindas para assinantes vindos do site/app.
""",
    "contract_sale_type": """
**VARIÁVEL CORRELATA — Renovações confirmam fidelização; reativações não.**

- `first_contract`: **59,6%**
- `renewal`: **50,2%**
- `reactivation`: **58,3%**
- `other`: **66,2%**

Quem reativa já cancelou uma vez e tende a repetir — o churn é praticamente igual ao
de primeiro contrato. A renovação é o único indicador real de fidelização consolidada.

**Nota:** Esta variável está fortemente correlacionada com `account_contract_number`.
Ambas capturam o mesmo fenômeno (fidelização progressiva).
""",
    "pacientes_cluster": """
**CLUSTERS — Confirmam o padrão: responsabilidade por outro reduz churn.**

| Cluster | Churn | Perfil |
|---|---|---|
| Titular 21-60 sem Dependente | **62,4%** | Sozinho, sem ancoragem |
| Titular Consumo PSIQUIATRIA | **61,4%** | Demanda pontual de saúde mental |
| Titular 21-60 com Dependente | **56,9%** | Família começa a proteger |
| Titular 41-60 + Dep. Jovem | **53,9%** | Pais com filhos, engajados |
| Titular 61-99 | **50,4%** | Dependência clínica natural |
| Titular 41-60 + Dep. Idoso | **50,4%** | Cuidador de idoso, muito engajado |

Os clusters são combinações pré-definidas de idade + dependentes. Confirmam que
as duas variáveis mais acionáveis (após o ciclo do contrato) são **dependentes** e **idade**.
""",
    "dep_idoso_6099": """
**Dependente idoso reduz o churn em 7,4 p.p.**

- Sem idoso: **57,7%**
- Com idoso: **50,3%**

Ter um dependente entre 60-99 anos cria ancoragem por necessidade médica contínua.
O titular não pode cancelar sem comprometer o acesso de saúde de alguém vulnerável.

**Nota:** Este é um subconjunto da variável `dependentes_faixa` — o efeito
de dependente idoso é o maior contribuidor do gap de ~10 p.p. observado em dependentes.
""",
    "dep_jovem_0020": """
**Dependente jovem tem efeito marginal.**

- Sem jovem: **55,4%**
- Com jovem: **54,4%**
- Diferença: **1,0 p.p.**

O efeito é menor que o do idoso porque jovens usam menos serviços regulares.
A combinação dependente jovem + idoso, porém, é bastante protetora (ver Página 4).
""",
    "titular_sexo": """
**Sexo do titular não é driver de churn.**

- Feminino: **55,4%**
- Masculino: **54,2%**
- Indeterminado: **65,0%** — possível problema de qualidade de cadastro

A diferença de **1,2 p.p.** entre F e M não é acionável. O destaque vai para `I` e
`(vazio)`: a taxa alta provavelmente reflete desengajamento geral (cadastro incompleto),
não o sexo em si.
""",
    "classe_social": """
**Classe social não é driver de churn.**

As taxas oscilam entre **52-55%** para todas as classes (A++ a E) — gap de ~2 p.p.,
sem poder discriminante. A exceção é **(sem dados)** com **60,4%** — e esse é o
insight real: a falta de preenchimento do cadastro socioeconômico é um proxy de
baixo engajamento com a marca.

**Por isso, `classe_social` foi removida dos perfis compostos (Página 4).**
Incluí-la como variável de perfil fragmentava os dados sem agregar poder preditivo.
""",
}

if dimension in insights:
    st.markdown(insights[dimension])
else:
    st.info("Observe a relação entre o *Volume* (barras azuis) e a *Taxa de Churn* (linha vermelha). "
            "Segmentos com alto volume e alta taxa de churn devem ser priorizados em campanhas de retenção.")
