"""
Pagina 13 — Evolucao do Modelo de Churn
========================================
Explica de forma acessivel o que sao perfis compostos, como o modelo evoluiu,
quais variaveis foram testadas e quais universos analisamos.
Pagina pensada para compartilhar com o time de negocios e gestao.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(page_title="Evolucao do Modelo", page_icon="🧬", layout="wide")
st.title("🧬 Evolucao do Modelo de Churn")
st.caption("O que fizemos, o que aprendemos e pra onde vamos")


# ═══════════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════════
@st.cache_data
def load_interacao():
    return pd.read_csv("results/interacao_contrato_dep_cronico.csv")

@st.cache_data
def load_perfis_5v():
    return pd.read_csv("results/perfis_compostos_risco_a.csv")

@st.cache_data
def load_perfis_7v():
    return pd.read_csv("results/perfis_compostos_7vars.csv")

@st.cache_data
def load_silencioso():
    return pd.read_csv("results/churn_silencioso_vs_ativo.csv")

@st.cache_data
def load_perfis_silent():
    try:
        return pd.read_csv("results/perfis_compostos_risco_c.csv")
    except FileNotFoundError:
        return None

@st.cache_data
def load_univariada():
    return pd.read_csv("results/univariada.csv")


# ═══════════════════════════════════════════════════════════════════
# BLOCO 1 — O QUE SAO PERFIS COMPOSTOS
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 1. O que sao perfis compostos?")

st.markdown("""
Quando olhamos uma variavel isolada (ex: "1o contrato tem 59% de churn"),
ja aprendemos algo. Mas o paciente nao e uma variavel so — ele e uma
**combinacao** de caracteristicas.

Um **perfil composto** e exatamente isso: o cruzamento de varias
caracteristicas ao mesmo tempo. Em vez de perguntar "qual o churn do
1o contrato?", perguntamos:

> "Qual o churn de quem esta no **1o contrato**, tem **0 dependentes**,
> e **nao e cronico**?"

Isso e um perfil composto. Cada combinacao unica de caracteristicas
forma um grupo de pacientes com um comportamento de churn especifico.
""")

# Exemplo visual com 3 variaveis
try:
    df_int = load_interacao()

    st.markdown("### Exemplo: 3 variaveis cruzadas")
    st.markdown("""
    Abaixo cruzamos **ciclo × dependentes × cronico** — sao 3 variaveis
    que juntas geram 12 perfis compostos. O churn vai de 42% ate 65%
    dependendo da combinacao.
    """)

    df_int_sorted = df_int.sort_values("churn_rate", ascending=True)
    df_int_sorted["perfil"] = (
        df_int_sorted["ciclo"] + " · " +
        df_int_sorted["dependentes"].str.replace("_", " ") + " · " +
        "cronico=" + df_int_sorted["cronico"]
    )

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=df_int_sorted["perfil"],
        x=df_int_sorted["churn_rate"],
        orientation="h",
        marker_color=[
            "#1a9850" if cr < 50 else "#91cf60" if cr < 55 else "#fee08b" if cr < 60
            else "#fc8d59" if cr < 65 else "#d73027"
            for cr in df_int_sorted["churn_rate"]
        ],
        text=df_int_sorted.apply(
            lambda r: f'{r["churn_rate"]}% ({int(r["total_contratos"]):,} contratos)', axis=1
        ),
        textposition="outside",
        textfont=dict(size=12),
    ))
    fig.update_layout(
        title="Churn por perfil composto (3 variaveis)",
        xaxis_title="Churn (%)",
        height=max(400, len(df_int_sorted) * 35 + 80),
        margin=dict(l=20, r=120),
        yaxis=dict(automargin=True),
        xaxis=dict(range=[0, max(df_int_sorted["churn_rate"]) + 10]),
    )
    st.plotly_chart(fig, use_container_width=True)

    pior = df_int_sorted.iloc[-1]
    melhor = df_int_sorted.iloc[0]
    gap = round(pior["churn_rate"] - melhor["churn_rate"], 1)

    col1, col2, col3 = st.columns(3)
    col1.metric("Menor churn", f'{melhor["churn_rate"]}%',
                help=melhor["perfil"])
    col2.metric("Maior churn", f'{pior["churn_rate"]}%',
                help=pior["perfil"])
    col3.metric("Gap entre extremos", f"{gap} p.p.")

    st.markdown(f"""
    **O que isso mostra:** com apenas 3 variaveis, ja conseguimos separar
    grupos com **{gap} p.p. de diferenca** no churn. Isso nao e aleatorio —
    e estrutura que pode ser usada pra direcionar acoes.
    """)

except Exception as e:
    st.error(f"Erro ao carregar interacao: {e}")


# ═══════════════════════════════════════════════════════════════════
# BLOCO 2 — EVOLUCAO: DE 3 PRA 5 PRA 7 VARIAVEIS
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 2. Como o modelo evoluiu")

st.markdown("""
Fomos adicionando variaveis ao modelo ao longo do tempo. A cada rodada,
testamos se a nova variavel **realmente melhora** a separacao dos perfis
ou se so adiciona ruido.
""")

# Timeline visual
evolucao = [
    {
        "fase": "Fase 1 — Analise univariada",
        "variaveis": ["Cada variavel isolada (12 dimensoes)"],
        "o_que_aprendemos": "Ciclo do contrato, dependentes e idade sao os 3 maiores drivers. "
                           "Churn vai de ~50% a ~63% dependendo da variavel.",
        "perfis": "—",
        "status": "concluida",
    },
    {
        "fase": "Fase 2 — Perfis com 3 variaveis",
        "variaveis": ["Ciclo (1o vs 2o+)", "Dependentes (0, 1-2, 3+)", "Cronico (S/N)"],
        "o_que_aprendemos": f"Gap de {gap} p.p. entre extremos. Os efeitos sao aditivos — "
                           "cada variavel contribui de forma independente.",
        "perfis": "12 perfis",
        "status": "concluida",
    },
    {
        "fase": "Fase 3 — Perfis com 5 variaveis",
        "variaveis": ["Ciclo", "Dependentes", "Cronico", "Faixa etaria (5 faixas)", "Duracao (6m/12m)"],
        "o_que_aprendemos": "Idade refina a separacao: jovens (21-30) sao os mais volateis. "
                           "Duracao importa: 12m tem mais churn que 6m. Geramos ~85 perfis unicos.",
        "perfis": "~85 perfis",
        "status": "concluida",
    },
    {
        "fase": "Fase 4 — Perfis com 7 variaveis (modelo atual)",
        "variaveis": ["Ciclo", "Dependentes", "Cronico", "Faixa etaria", "Duracao",
                      "Canal (digital vs presencial)", "Classe social (AB vs CDE)"],
        "o_que_aprendemos": "Canal digital tem churn levemente maior. Classe social tem efeito pequeno (~2 p.p.). "
                           "O modelo gera ~310 perfis unicos e alimenta o score de 0 a 1000.",
        "perfis": "~310 perfis",
        "status": "modelo atual",
    },
    {
        "fase": "Fase 5 — Modelo individual (XGBoost)",
        "variaveis": ["Todas as 7 anteriores", "Sexo", "Plano odonto (S/N)",
                      "Uso por especialidade: CM, tele, exames, clinica, gineco, cardio, dermato, endocrino, psiq, orto, pediatra (11 flags)"],
        "o_que_aprendemos": "Adicionamos 12 variaveis comportamentais (se usou cada especialidade). "
                           "O AUC subiu pouco (0.58 → 0.60) porque as flags sao apenas sim/nao — "
                           "falta frequencia e recencia de uso.",
        "perfis": "188 mil contratos individuais",
        "status": "testado, ganho marginal",
    },
]

for fase in evolucao:
    if fase["status"] == "modelo atual":
        cor = "#d4efdf"
        icone = "▶"
    elif fase["status"] == "testado, ganho marginal":
        cor = "#fef9e7"
        icone = "⚠"
    else:
        cor = "#f2f3f4"
        icone = "✓"

    st.markdown(
        f'<div style="background:{cor}; padding:16px; border-radius:8px; '
        f'border-left:4px solid {"#27ae60" if icone == "▶" else "#f39c12" if icone == "⚠" else "#bdc3c7"}; '
        f'margin-bottom:10px;">',
        unsafe_allow_html=True,
    )

    col_fase, col_vars, col_aprend = st.columns([1.5, 2, 3])

    with col_fase:
        st.markdown(f"**{icone} {fase['fase']}**")
        st.caption(f"{fase['perfis']} perfis")

    with col_vars:
        for v in fase["variaveis"]:
            st.markdown(f"- {v}")

    with col_aprend:
        st.markdown(fase["o_que_aprendemos"])

    st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════
# BLOCO 3 — VARIAVEIS TESTADAS E DESCARTADAS
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 3. Variaveis que testamos e descartamos")

st.markdown("""
Nem toda variavel que parece importante sobrevive ao teste. Algumas
foram removidas do modelo por motivos especificos:
""")

descartadas = [
    {
        "variavel": "Consumo do plano (usou/nao usou)",
        "motivo": "Confounding com ciclo do contrato",
        "explicacao": "No 1o contrato, quem consome mais tambem cancela mais — "
                     "nao porque o consumo causa churn, mas porque o 1o contrato "
                     "ja tem churn alto naturalmente. Quando controlamos por ciclo, "
                     "o consumo ate protege. Mas no modelo agregado, ele engana.",
    },
    {
        "variavel": "Unsubscription (pediu cancelamento S/N)",
        "motivo": "Tautologia",
        "explicacao": "98.7% de quem pediu cancelamento tem churn = sim. "
                     "Incluir isso no modelo e usar o resultado pra prever o resultado. "
                     "Removido por definicao.",
    },
    {
        "variavel": "Dependente idoso (S/N)",
        "motivo": "Dupla contagem",
        "explicacao": "Ja esta capturado pela variavel de dependentes (0, 1-2, 3+). "
                     "Adicionar a flag separada nao melhora o modelo e cria redundancia.",
    },
    {
        "variavel": "Classe social (AB vs CDE)",
        "motivo": "Mantida, mas com efeito pequeno",
        "explicacao": "O gap entre AB e CDE e de ~2 p.p. Mantemos no modelo de 7 variaveis "
                     "porque nao atrapalha, mas e a variavel com menor poder discriminante.",
    },
]

for d in descartadas:
    with st.expander(f"**{d['variavel']}** — {d['motivo']}"):
        st.markdown(d["explicacao"])


# ═══════════════════════════════════════════════════════════════════
# BLOCO 4 — UNIVERSOS ANALISADOS
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 4. Quais universos analisamos?")

st.markdown("""
O modelo principal trabalha com um universo especifico. Mas tambem
fizemos analises separadas pra responder perguntas diferentes.
""")

# Universo principal
st.markdown("### Universo principal (base de todos os modelos)")

st.markdown("""
| Filtro | Valor | Por que |
|---|---|---|
| Meio de pagamento | Cartao de credito | Renovacao automatica so funciona com cartao |
| Duracao do plano | 6 e 12 meses | Sao os planos recorrentes — excluimos avulsos |
| Canal | Sem B2B/cooperativas | Dinamica corporativa e diferente da pessoa fisica |
| Periodo | Ultimos 12 meses | Dados recentes e comparaveis |
""")

try:
    df_uni = load_univariada()
    total = int(df_uni[df_uni["dimensao"] == "plan_months_duration"]["total_contratos"].sum())
    st.markdown(f"**Volume total nesse universo: {total:,} contratos**")
except Exception:
    pass

# Subuniversos
st.markdown("### Subuniversos analisados")

try:
    df_sil = load_silencioso()
    total_sil = df_sil.groupby("tipo_desfecho")["total_contratos"].sum()
    n_ativo = int(total_sil.get("churn_ativo", 0))
    n_silencioso = int(total_sil.get("churn_silencioso", 0))
    n_retido = int(total_sil.get("retido", 0))
    n_churn = n_ativo + n_silencioso
    pct_sil = round(100 * n_silencioso / n_churn, 0) if n_churn else 0
    pct_ati = round(100 * n_ativo / n_churn, 0) if n_churn else 0
    tem_dados_sil = True
except Exception:
    tem_dados_sil = False

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
    **Todos os churners (base principal)**

    Inclui tanto quem pediu cancelamento quanto quem
    simplesmente nao renovou. E o universo dos modelos
    e de todas as paginas do dashboard.
    """)

with col2:
    st.markdown("**So quem pediu cancelamento (churn ativo)**")
    if tem_dados_sil:
        st.markdown(f"""
        {n_ativo:,} contratos ({pct_ati:.0f}% do churn)

        Analisamos separadamente pra entender:
        - Quais os motivos declarados?
        - Qual o perfil de quem decide ativamente sair?
        - Quando pedem (antecedencia do vencimento)?
        """)
    else:
        st.caption("Dados nao disponiveis.")

with col3:
    st.markdown("**So churn silencioso**")
    if tem_dados_sil:
        st.markdown(f"""
        {n_silencioso:,} contratos ({pct_sil:.0f}% do churn)

        O contrato venceu sem renovacao — cartao recusado,
        cobranca nao processada, ou nenhuma tentativa.
        Rodamos os perfis compostos separadamente pra esse
        grupo (arquivo `perfis_compostos_risco_c.csv`).
        """)
    else:
        st.caption("Dados nao disponiveis.")

# Comparacao ativo vs silencioso
if tem_dados_sil:
    st.markdown("### Churn ativo vs silencioso: perfis diferentes?")

    dim_map = {"ciclo": "Ciclo", "faixa_idade": "Idade", "dependentes": "Dependentes", "consumo": "Consumo"}

    for dim, label in dim_map.items():
        grp = df_sil.groupby(["tipo_desfecho", dim])["total_contratos"].sum().reset_index()
        totals = grp.groupby("tipo_desfecho")["total_contratos"].transform("sum")
        grp["pct"] = round(100 * grp["total_contratos"] / totals, 1)

        # Filtrar so churn
        grp = grp[grp["tipo_desfecho"].isin(["churn_ativo", "churn_silencioso"])]

        fig = px.bar(
            grp, x=dim, y="pct", color="tipo_desfecho",
            barmode="group", text_auto=".1f",
            title=f"Distribuicao por {label}: ativo vs silencioso",
            color_discrete_map={"churn_ativo": "#c0392b", "churn_silencioso": "#e67e22"},
            labels={dim: label, "pct": "% do grupo", "tipo_desfecho": ""},
        )
        fig.update_layout(height=300, legend=dict(orientation="h", y=1.12))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("""
    **O que os graficos mostram:**

    - **Ciclo:** o churn silencioso e mais concentrado no 1o contrato — o paciente
      nem teve tempo de criar vinculo antes de perder o plano por falha de pagamento.
      O ativo tem mais 2o+ contrato — sao pacientes que conhecem o produto e decidiram sair.

    - **Idade:** distribuicao parecida, com leve concentracao de silenciosos em 31-50.

    - **Dependentes:** perfis similares — dependentes protegem contra ambos os tipos de churn.

    - **Consumo:** o silencioso tem mais pacientes que consumiram (S) — ou seja, usaram o plano
      mas perderam a renovacao por falha operacional, nao por desinteresse.
    """)


# ═══════════════════════════════════════════════════════════════════
# BLOCO 5 — COMPARACAO 5 VARS vs 7 VARS
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 5. O que ganhou ao adicionar variaveis?")

try:
    df_5v = load_perfis_5v()
    df_7v = load_perfis_7v()

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Modelo com 5 variaveis")
        st.markdown(f"""
        - **Variaveis:** ciclo, dependentes, cronico, idade, duracao
        - **Perfis gerados:** {len(df_5v)}
        - **Range de churn:** {df_5v['churn_rate'].min()}% a {df_5v['churn_rate'].max()}%
        - **Spread:** {round(df_5v['churn_rate'].max() - df_5v['churn_rate'].min(), 1)} p.p.
        """)

    with col2:
        st.markdown("### Modelo com 7 variaveis")
        st.markdown(f"""
        - **Variaveis:** + canal, classe social
        - **Perfis gerados:** {len(df_7v)}
        - **Range de churn:** {df_7v['churn_rate'].min()}% a {df_7v['churn_rate'].max()}%
        - **Spread:** {round(df_7v['churn_rate'].max() - df_7v['churn_rate'].min(), 1)} p.p.
        """)

    spread_5 = round(df_5v['churn_rate'].max() - df_5v['churn_rate'].min(), 1)
    spread_7 = round(df_7v['churn_rate'].max() - df_7v['churn_rate'].min(), 1)
    ganho = round(spread_7 - spread_5, 1)

    st.markdown(f"""
    **Ganho de separacao:** o modelo com 7 variaveis ampliou o spread em
    **{ganho} p.p.** ({spread_5} → {spread_7} p.p.). As 2 variaveis adicionais
    (canal e classe) refinam a segmentacao nos extremos.

    Na pratica, passamos de ~85 grupos de pacientes pra ~310. Isso permite
    acoes mais direcionadas — em vez de "1o contrato jovem", podemos dizer
    "1o contrato, jovem, digital, CDE" que e um grupo ainda mais especifico.
    """)

    # Distribuicao de churn nos dois modelos
    fig_comp = go.Figure()
    fig_comp.add_trace(go.Histogram(
        x=df_5v["churn_rate"], nbinsx=20,
        name="5 variaveis", marker_color="#3498db", opacity=0.6,
    ))
    fig_comp.add_trace(go.Histogram(
        x=df_7v["churn_rate"], nbinsx=30,
        name="7 variaveis", marker_color="#e74c3c", opacity=0.6,
    ))
    fig_comp.update_layout(
        title="Distribuicao das taxas de churn dos perfis: 5 vars vs 7 vars",
        xaxis_title="Churn (%)", yaxis_title="Numero de perfis",
        barmode="overlay", height=380,
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_comp, use_container_width=True)

    st.caption(
        "Com mais variaveis, a distribuicao se espalha mais — os perfis ficam mais especificos "
        "e o modelo consegue diferenciar melhor quem tem alto e baixo risco."
    )

except Exception as e:
    st.error(f"Erro ao comparar modelos: {e}")


# ═══════════════════════════════════════════════════════════════════
# BLOCO 6 — LIMITACOES E PROXIMOS PASSOS
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 6. Onde estamos e o que falta")

st.markdown("""
### O que o modelo faz bem hoje

- **Separa grupos** com 23+ p.p. de diferenca no churn — suficiente pra segmentar acoes
- **Identifica os drivers** que mais pesam (ciclo, dependentes, cronico, idade)
- **Score de 0 a 1000** pra cada perfil, com faixas de risco validadas
- **Distingue churn ativo de silencioso** — perfis diferentes, acoes diferentes

### O que limita a precisao

O modelo acerta no **grupo**, mas nao no **individuo**. Dentro de um
mesmo perfil (ex: "1o contrato, jovem, solo, nao cronico"), uns 65%
cancelam e 35% ficam. O modelo nao sabe quem e quem porque faltam
dados de comportamento:

| O que falta | Por que importa |
|---|---|
| Frequencia de uso (quantas consultas/mes) | Quem usa mais tem mais vinculo |
| Recencia (dias desde a ultima consulta) | Quem parou de usar provavelmente esta saindo |
| Historico de falhas de pagamento | Preve churn silencioso diretamente |
| Interacoes com suporte/SAC | Sinal de insatisfacao antes do cancelamento |

Com essas variaveis, o modelo individual (XGBoost) poderia subir de
AUC 0.60 pra 0.75-0.85 — e ai sim diferenciar dentro do grupo quem
vai sair de quem vai ficar.
""")

st.markdown("""
### Universos que ainda nao analisamos

| Universo | Por que ainda nao | Vale explorar? |
|---|---|---|
| Boleto / PIX | Dinamica de renovacao diferente (nao e automatica) | Sim, mas precisa de modelo separado |
| Planos mensais | Volume grande mas churn tem outra logica | Sim, e complementar |
| B2B / corporativo | Decisao de cancelamento nao e do paciente | Talvez — depende do interesse comercial |
| Planos gratis / trial | Conversao, nao retencao | Outro problema |
""")
