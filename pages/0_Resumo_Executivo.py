"""
Pagina 0 — Resumo Executivo
============================
Narrativa orientada a dados para o time de negocios.
Conduz o leitor pelos numeros sem prescrever acoes — a decisao e de quem le.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="Resumo Executivo · Churn", page_icon="🩺", layout="wide")


# ═══════════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════════
@st.cache_data
def load_univariada():
    return pd.read_csv("results/univariada.csv")

@st.cache_data
def load_interacao():
    return pd.read_csv("results/interacao_contrato_dep_cronico.csv")

@st.cache_data
def load_financeiro():
    df = pd.read_csv("results/impacto_financeiro.csv")
    df["duracao"] = df["duracao"].astype(str)
    return df

@st.cache_data
def load_clv():
    df = pd.read_csv("results/clv_por_perfil.csv")
    df["duracao"] = df["duracao"].astype(str)
    return df

@st.cache_data
def load_tempo_uso():
    return pd.read_csv("results/tempo_primeiro_uso.csv")

@st.cache_data
def load_silencioso():
    return pd.read_csv("results/churn_silencioso_vs_ativo.csv")

@st.cache_data
def load_velocidade():
    df = pd.read_csv("results/velocidade_churn.csv")
    df["duracao"] = df["duracao"].astype(str)
    return df

@st.cache_data
def load_winback():
    return pd.read_csv("results/winback_reativacoes.csv")


# ═══════════════════════════════════════════════════════════════════
# SIDEBAR — TICKET PARA CALCULO FINANCEIRO
# ═══════════════════════════════════════════════════════════════════
st.sidebar.markdown("### Parametros")
ticket_6m = st.sidebar.number_input(
    "Ticket plano 6m (R$):", value=600.0, step=50.0, key="exec_t6"
)
ticket_12m = st.sidebar.number_input(
    "Ticket plano 12m (R$):", value=1200.0, step=50.0, key="exec_t12"
)
TICKET = {"6": ticket_6m, "12": ticket_12m}


# ═══════════════════════════════════════════════════════════════════
# CARREGAMENTO
# ═══════════════════════════════════════════════════════════════════
try:
    df_uni = load_univariada()
    df_int = load_interacao()
    df_fin = load_financeiro()
    df_clv = load_clv()
except FileNotFoundError as e:
    st.error(f"CSV nao encontrado: {e}. Rode as queries antes.")
    st.stop()

# Metricas globais
total = int(df_uni[df_uni["dimensao"] == "plan_months_duration"]["total_contratos"].sum())
churners = int(df_uni[df_uni["dimensao"] == "plan_months_duration"]["churners"].sum())
retidos = total - churners
taxa = round(100 * churners / total, 1) if total else 0

# Financeiro
df_fin["ticket"] = df_fin["duracao"].map(TICKET)
receita_perdida = (df_fin["churners"] * df_fin["ticket"]).sum()
receita_total = (df_fin["total_contratos"] * df_fin["ticket"]).sum()

# CLV
df_clv["ticket"] = df_clv["duracao"].map(TICKET)
df_clv["ticket_mensal"] = df_clv["ticket"] / df_clv["duracao"].astype(float)
df_clv["clv"] = df_clv["ticket_mensal"] * df_clv["meses_vida_estimados"]


# ═══════════════════════════════════════════════════════════════════
# BLOCO 1 — O TAMANHO DO PROBLEMA
# ═══════════════════════════════════════════════════════════════════
st.title("Churn: o que os numeros mostram")
st.caption("Contratos cartao de credito · Planos 6 e 12 meses · Ultimos 12 meses")

st.markdown("---")
st.markdown("## 1. O tamanho do problema")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Contratos analisados", f"{total:,}")
k2.metric("Nao renovaram", f"{churners:,}", delta=f"{taxa}%", delta_color="inverse")
k3.metric("Receita nao renovada", f"R$ {receita_perdida:,.0f}",
          delta=f"{100 * receita_perdida / receita_total:.0f}% da receita total",
          delta_color="inverse")
k4.metric("Renovaram", f"{retidos:,}", delta=f"{100 - taxa:.1f}%")

st.markdown(f"""
De cada **100 contratos** que vencem, **{taxa:.0f} nao renovam**.

Isso representa **R$ {receita_perdida:,.0f}** em contratos que nao geraram um proximo ciclo
— {100 * receita_perdida / receita_total:.0f}% de toda a receita do periodo.
""")

st.caption("Valores estimados com ticket informado na sidebar. Ajuste conforme necessario.")


# ═══════════════════════════════════════════════════════════════════
# BLOCO 2 — ONDE ESTA CONCENTRADO
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 2. O churn nao e uniforme")

st.markdown("""
Se fosse, nao haveria muito o que fazer. Mas quando separamos por perfil,
o cenario muda completamente.
""")

# Pegar os extremos da interacao
df_int_sorted = df_int.sort_values("churn_rate", ascending=False)
pior = df_int_sorted.iloc[0]
melhor = df_int_sorted.iloc[-1]
gap = round(pior["churn_rate"] - melhor["churn_rate"], 1)

col_a, col_b = st.columns(2)

with col_a:
    st.markdown(f"""
    **Perfil com maior churn:**

    | | |
    |---|---|
    | Ciclo | {pior['ciclo']}o contrato |
    | Dependentes | {pior['dependentes']} |
    | Cronico | {'Sim' if pior['cronico'] == 'S' else 'Nao'} |
    | **Churn** | **{pior['churn_rate']}%** |
    | Volume | {int(pior['total_contratos']):,} contratos |
    """)

with col_b:
    st.markdown(f"""
    **Perfil com menor churn:**

    | | |
    |---|---|
    | Ciclo | {melhor['ciclo']}o contrato |
    | Dependentes | {melhor['dependentes']} |
    | Cronico | {'Sim' if melhor['cronico'] == 'S' else 'Nao'} |
    | **Churn** | **{melhor['churn_rate']}%** |
    | Volume | {int(melhor['total_contratos']):,} contratos |
    """)

st.markdown(f"""
A diferenca entre esses dois perfis e de **{gap} pontos percentuais** — usando apenas
3 variaveis: ciclo do contrato, dependentes e condicao cronica.

Isso significa que o churn tem **estrutura**. Nao e aleatorio. E onde tem estrutura, tem alavanca.
""")

# Grafico waterfall dos drivers
st.markdown("### Decomposicao: quanto cada fator pesa")

df_ciclo = df_uni[df_uni["dimensao"] == "account_contract_number"]
primeiro_cr = df_ciclo[df_ciclo["segmento"] == "1o contrato"]["churn_rate"].values
renov_cr = df_ciclo[df_ciclo["segmento"] == "2o+ contrato"]["churn_rate"].values

df_dep = df_uni[df_uni["dimensao"] == "dependentes_faixa"]
sem_dep = df_dep[df_dep["segmento"] == "0 (sem dep.)"]["churn_rate"].values
com_dep = df_dep[df_dep["segmento"] == "3+ dep."]["churn_rate"].values

df_cron = df_uni[df_uni["dimensao"] == "titular_main_cronico_sn"]
nao_cron = df_cron[df_cron["segmento"] == "N"]["churn_rate"].values
sim_cron = df_cron[df_cron["segmento"] == "S"]["churn_rate"].values

df_idade = df_uni[df_uni["dimensao"] == "titular_faixa_etaria"]
jovem = df_idade[df_idade["segmento"].str.contains("21-30", na=False)]["churn_rate"].values
senior = df_idade[df_idade["segmento"].str.contains("51-70|61-70", na=False)]["churn_rate"].values

drivers = []
if len(primeiro_cr) and len(renov_cr):
    drivers.append(("1o vs 2o+ contrato", round(float(primeiro_cr[0] - renov_cr[0]), 1)))
if len(sem_dep) and len(com_dep):
    drivers.append(("Sem dep. vs 3+ dep.", round(float(sem_dep[0] - com_dep[0]), 1)))
if len(jovem) and len(senior):
    drivers.append(("Jovem (21-30) vs Senior (51-70)", round(float(jovem[0] - senior[0]), 1)))
if len(nao_cron) and len(sim_cron):
    drivers.append(("Nao cronico vs Cronico", round(float(nao_cron[0] - sim_cron[0]), 1)))

if drivers:
    drivers.sort(key=lambda x: x[1], reverse=True)
    nomes = [d[0] for d in drivers]
    deltas = [d[1] for d in drivers]

    fig_drv = go.Figure()
    fig_drv.add_trace(go.Bar(
        x=deltas,
        y=nomes,
        orientation="h",
        marker_color=["#c0392b" if d > 8 else "#e67e22" if d > 5 else "#f39c12" for d in deltas],
        text=[f"+{d} p.p." for d in deltas],
        textposition="outside",
        textfont=dict(size=14),
    ))
    fig_drv.update_layout(
        title="Gap de churn entre extremos de cada variavel",
        xaxis_title="Diferenca em pontos percentuais",
        height=280,
        margin=dict(l=20, r=80, t=40, b=30),
        yaxis=dict(automargin=True),
    )
    st.plotly_chart(fig_drv, use_container_width=True)

    st.markdown(f"""
    O ciclo do contrato (1o vs renovacao) e a variavel com maior impacto isolado:
    **{drivers[0][1]} p.p.** de diferenca. Um cliente que sobrevive ao primeiro ciclo
    tem um perfil de risco fundamentalmente diferente.
    """)


# ═══════════════════════════════════════════════════════════════════
# BLOCO 3 — O QUE PROTEGE
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 3. O que os clientes que ficam tem em comum")

st.markdown("""
Tres padroes aparecem consistentemente nos clientes que renovam:
""")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("### Vinculo familiar")
    if len(sem_dep) and len(com_dep):
        st.metric("Churn sem dependentes", f"{sem_dep[0]}%")
        st.metric("Churn com 3+ dependentes", f"{com_dep[0]}%",
                  delta=f"{com_dep[0] - sem_dep[0]:+.1f} p.p.", delta_color="inverse")
    st.markdown(
        "Quando o plano cuida de mais pessoas, o custo percebido de sair aumenta. "
        "Cada dependente adicional reduz o churn em ~3-5 p.p."
    )

with col2:
    st.markdown("### Necessidade medica continua")
    if len(nao_cron) and len(sim_cron):
        st.metric("Churn nao cronico", f"{nao_cron[0]}%")
        st.metric("Churn cronico", f"{sim_cron[0]}%",
                  delta=f"{sim_cron[0] - nao_cron[0]:+.1f} p.p.", delta_color="inverse")
    st.markdown(
        "Pacientes com condicao cronica dependem do acompanhamento. "
        "Nao e fidelidade — e necessidade. Isso cria retencao organica."
    )

with col3:
    st.markdown("### Experiencia previa")
    if len(primeiro_cr) and len(renov_cr):
        st.metric("Churn 1o contrato", f"{primeiro_cr[0]}%")
        st.metric("Churn 2o+ contrato", f"{renov_cr[0]}%",
                  delta=f"{renov_cr[0] - primeiro_cr[0]:+.1f} p.p.", delta_color="inverse")
    st.markdown(
        "Quem ja renovou uma vez tem probabilidade muito maior de renovar de novo. "
        "O primeiro ciclo e o filtro mais duro."
    )


# ═══════════════════════════════════════════════════════════════════
# BLOCO 4 — A ANATOMIA DA SAIDA
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 4. Como e quando os clientes saem")

try:
    df_sil = load_silencioso()
    total_sil = df_sil.groupby("tipo_desfecho")["total_contratos"].sum()

    n_silencioso = int(total_sil.get("churn_silencioso", 0))
    n_ativo = int(total_sil.get("churn_ativo", 0))
    n_retido = int(total_sil.get("retido", 0))
    n_churn_total = n_silencioso + n_ativo

    pct_silencioso = round(100 * n_silencioso / n_churn_total, 0) if n_churn_total else 0

    col_s1, col_s2 = st.columns([1, 2])

    with col_s1:
        fig_pie = go.Figure(data=[go.Pie(
            labels=["Silencioso", "Ativo"],
            values=[n_silencioso, n_ativo],
            hole=0.5,
            marker_colors=["#e67e22", "#c0392b"],
            textinfo="label+percent",
            textfont=dict(size=14),
        )])
        fig_pie.update_layout(
            title="Composicao do churn",
            height=300, showlegend=False,
            margin=dict(l=10, r=10, t=40, b=10),
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_s2:
        st.markdown(f"""
        Dos que saem, **{pct_silencioso:.0f}% sao silenciosos** — nao pediram cancelamento.
        O contrato simplesmente venceu sem renovacao: cartao recusado, cobranca nao processada,
        ou nenhuma tentativa registrada.

        Apenas **{100 - pct_silencioso:.0f}% pediram cancelamento ativamente**.

        Isso muda a perspectiva: a maioria dos churners **nao decidiu sair**.
        O contrato morreu por inacao — do paciente, do sistema de cobranca, ou de ambos.
        """)

        st.markdown(f"""
        | Tipo | Volume | % do churn |
        |---|---|---|
        | Silencioso (nao agiu) | {n_silencioso:,} | {pct_silencioso:.0f}% |
        | Ativo (pediu cancelamento) | {n_ativo:,} | {100 - pct_silencioso:.0f}% |
        """)

except FileNotFoundError:
    st.info("Dados de churn silencioso vs ativo nao disponiveis.")

# Janela de decisao
try:
    df_vel = load_velocidade()
    df_vel_ativo = df_vel[df_vel["tipo_churn"] == "churn_ativo"].copy()

    if not df_vel_ativo.empty:
        st.markdown("### Quando o cancelamento ativo acontece")

        # Agrupar por janela
        janela_agg = df_vel_ativo.groupby("janela_saida")["total"].sum().reset_index()
        janela_agg["pct"] = round(100 * janela_agg["total"] / janela_agg["total"].sum(), 1)
        janela_agg = janela_agg.sort_values("janela_saida")

        # Separar antecipados (>30 dias antes)
        antecipado = janela_agg[janela_agg["janela_saida"].isin([
            "A_90+_dias_antes", "B_31-90_dias_antes"
        ])]
        pct_antecipado = antecipado["pct"].sum()

        tardio = janela_agg[janela_agg["janela_saida"].isin([
            "D_1-7_dias_antes", "E_no_dia_ou_apos"
        ])]
        pct_tardio = tardio["pct"].sum()

        col_j1, col_j2, col_j3 = st.columns(3)
        col_j1.metric("Cancelam com 30+ dias de antecedencia", f"{pct_antecipado:.0f}%")
        col_j2.metric("Cancelam na ultima semana ou apos", f"{pct_tardio:.0f}%")
        col_j3.metric("Total de cancelamentos ativos", f"{int(janela_agg['total'].sum()):,}")

        st.markdown(f"""
        **{pct_antecipado:.0f}%** dos cancelamentos ativos acontecem com mais de 30 dias
        de antecedencia. Esses pacientes ja decidiram — ha uma janela para entender o motivo.

        **{pct_tardio:.0f}%** cancelam na ultima semana ou depois do vencimento. Para esses,
        qualquer intervencao precisaria ter acontecido antes.
        """)

except FileNotFoundError:
    pass


# ═══════════════════════════════════════════════════════════════════
# BLOCO 5 — O VALOR EM JOGO
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 5. Quanto cada perfil vale")

st.markdown("""
Nem todo churn custa igual. Um cliente que ficaria 25 meses custa mais de perder
do que um que ficaria 12.
""")

# Top 5 maiores CLV vs Top 5 menores
df_clv_sorted = df_clv.sort_values("clv", ascending=False)
top5 = df_clv_sorted.head(5)
bottom5 = df_clv_sorted.tail(5)

col_t, col_b = st.columns(2)

with col_t:
    st.markdown("**Perfis com maior valor de vida (CLV):**")
    for _, r in top5.iterrows():
        st.markdown(
            f"- **{r['ciclo']}** · {r['perfil_idade']} · "
            f"{'Cronico' if r['cronico'] == 'S' else 'Nao cronico'} · "
            f"{r['tem_dependente']} · {r['duracao']}m → "
            f"**R$ {r['clv']:,.0f}** · vida media: {r['meses_vida_estimados']:.0f} meses · "
            f"churn: {r['churn_rate_pct']}%"
        )

with col_b:
    st.markdown("**Perfis com menor valor de vida (CLV):**")
    for _, r in bottom5.iterrows():
        st.markdown(
            f"- **{r['ciclo']}** · {r['perfil_idade']} · "
            f"{'Cronico' if r['cronico'] == 'S' else 'Nao cronico'} · "
            f"{r['tem_dependente']} · {r['duracao']}m → "
            f"**R$ {r['clv']:,.0f}** · vida media: {r['meses_vida_estimados']:.0f} meses · "
            f"churn: {r['churn_rate_pct']}%"
        )

# CLV medio por ciclo
clv_1o = df_clv[df_clv["ciclo"] == "1o"]["clv"].mean()
clv_2o = df_clv[df_clv["ciclo"] == "2o+"]["clv"].mean()

st.markdown(f"""
---

| | CLV medio | Interpretacao |
|---|---|---|
| 1o contrato | **R$ {clv_1o:,.0f}** | Alto churn reduz o valor — muitos saem antes de gerar retorno |
| 2o+ contrato | **R$ {clv_2o:,.0f}** | Quem renovou uma vez tende a ficar mais — gera mais valor |

A diferenca de **R$ {clv_2o - clv_1o:,.0f}** no CLV entre 1o e 2o+ contrato e o premio
de sobrevivencia ao primeiro ciclo.
""")


# ═══════════════════════════════════════════════════════════════════
# BLOCO 6 — O QUE OS DADOS SUGEREM (SEM PRESCREVER)
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 6. Perguntas que os dados levantam")

st.markdown(f"""
Os numeros acima apontam para algumas questoes que valem discutir:

**Sobre o primeiro ciclo:**
- {taxa:.0f}% de churn geral, mas o 1o contrato responde pela maior parte.
  O que acontece nos primeiros meses que leva tantos a nao renovar?
- O CLV do 1o contrato e R$ {clv_1o:,.0f} vs R$ {clv_2o:,.0f} do 2o+. Cada cliente
  que sobrevive ao primeiro ciclo vale {clv_2o/clv_1o:.1f}x mais.

**Sobre os silenciosos ({pct_silencioso:.0f}% do churn):**
- A maioria dos churners nao pediu para sair. O contrato expirou.
  Estamos perdendo clientes que talvez nem soubessem que estavam saindo?
- Que parte desses {n_silencioso:,} e recuperavel com uma acao simples
  (lembrete, atualizacao de cartao, retentativa)?

**Sobre o perfil que fica:**
- Dependentes, condicao cronica e experiencia previa — essas 3 variaveis
  explicam {gap} p.p. de diferenca no churn.
  Alguma dessas alavancas e influenciavel por uma acao de negocios?

**Sobre o valor financeiro:**
- R$ {receita_perdida:,.0f} em contratos nao renovados no periodo.
  Se reduzissemos o churn em 5 p.p., quanto disso seria preservado?
""")

# Simulacao simples inline
st.markdown("---")
st.markdown("### Simulacao: e se o churn caisse 5 p.p.?")

reducao = 5
churners_evitaveis = int(total * reducao / 100)
ticket_medio_ponderado = receita_total / total if total else 0
receita_salva = churners_evitaveis * ticket_medio_ponderado

col_sim1, col_sim2, col_sim3 = st.columns(3)
col_sim1.metric("Churners evitaveis", f"{churners_evitaveis:,}",
                help=f"{reducao} p.p. de {total:,} contratos")
col_sim2.metric("Receita preservada", f"R$ {receita_salva:,.0f}")
col_sim3.metric("Novo churn", f"{taxa - reducao:.1f}%",
                delta=f"-{reducao} p.p.", delta_color="inverse")

st.markdown(f"""
Uma reducao de **{reducao} p.p.** no churn preservaria aproximadamente
**R$ {receita_salva:,.0f}** em receita e **{churners_evitaveis:,} clientes**.

A questao nao e se vale investir em retencao — e *onde* e *como*.
Os dados das paginas seguintes detalham cada segmento, cada especialidade
e cada momento da jornada para subsidiar essa decisao.
""")

st.markdown("---")

# Navegacao
st.markdown("""
### Para aprofundar

| Pagina | O que mostra |
|---|---|
| **1. Visao Geral** | Cada variavel isolada — volume e taxa |
| **2. Risco e Evolucao** | Score por perfil e evolucao mensal |
| **3. Saude e Consumo** | Uso por especialidade e o paradoxo do consumo |
| **4. Perfis Compostos** | Cruzamento multivariavel — quem e o churner |
| **5. Analises Avancadas** | Motivos de cancelamento, win-back, silencioso vs ativo |
| **8. Insights Negocio** | Anatomia da nao-renovacao em detalhe |
| **9. Coorte e Retencao** | Curvas de sobrevivencia por safra |
| **10. Impacto Financeiro** | CLV, receita perdida e simulador de ROI |
| **11. Sazonalidade** | Meses criticos e sinais precoces de abandono |
""")
