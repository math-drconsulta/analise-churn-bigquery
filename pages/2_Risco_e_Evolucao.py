import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Risco e Evolução · Churn", page_icon="📉", layout="wide")

# ═══════════════════════════════════════════════════════════════════════
st.title("📉 Capítulo 2 — Score de Risco, Sazonalidade e Unidades")
st.markdown("""
Construímos um score paramétrico que atribui pontos de risco com base no que sabemos sobre
cada paciente no momento da contratação. O objetivo: ranquear contratos por probabilidade
de cancelamento antes que ele aconteça.
""")

# ═══════════════════════════════════════════════════════════════════════
# COMO O SCORE É CALCULADO — EXPLICAÇÃO VISUAL
# ═══════════════════════════════════════════════════════════════════════
st.subheader("Como o score é calculado")
st.markdown("""
Soma de pontos de risco atribuídos a cada característica conhecida no momento da assinatura.
Cada fator adiciona ou subtrai pontos:
""")

col_formula, col_example = st.columns([3, 2])

with col_formula:
    st.markdown("""
    | Fator | Condição | Pontos |
    |---|---|---:|
    | **Ciclo do contrato** | 1º contrato | **+15** |
    | | 2º+ contrato | +0 |
    | **Dependentes** | Sem dependentes | **+15** |
    | | 1-2 dependentes | +8 |
    | | 3+ dependentes | +0 |
    | **Idade do titular** | Até 30 anos | **+15** |
    | | 31-40 anos | +10 |
    | | 41-50 anos | +5 |
    | | 51+ anos | +0 |
    | **Consumo do plano** | Sim, usou | **+10** |
    | | Não usou | +0 |
    | **Doença crônica** | Não crônico | **+10** |
    | | Crônico | +0 |
    | **Canal de venda** | Clínica médica (drc_cm) | +5 |
    | | B2B (empresarial) | **-10** |
    | | Outros canais | +0 |
    | **Dependente idoso (60+)** | Tem | **-10** |
    | | Não tem | +0 |
    | **Pediu cancelamento** | Sim (unsubscription) | **+25** |
    | | Não | +0 |
    | **Classe social** | D ou E | +5 |
    | | Sem informação | +3 |
    | | Outras | +0 |
    """)

with col_example:
    st.markdown("##### 📝 Exemplo Prático")

    st.error("""
    **Paciente de Alto Risco (score = 65):**
    - 1º contrato → +15
    - Sem dependentes → +15
    - 25 anos → +15
    - Usou o plano → +10
    - Não crônico → +10
    - Canal digital → +0
    - Sem dep. idoso → +0
    - Não pediu cancelamento → +0
    - Classe C → +0

    **Total: 65 pontos** → Faixa CRÍTICA
    """)

    st.success("""
    **Paciente de Baixo Risco (score = 0):**
    - 2º+ contrato → +0
    - 3+ dependentes → +0
    - 55 anos → +0
    - Não usou → +0
    - Crônico → +0
    - Canal B2B → **-10**
    - Dep. idoso → **-10**
    - Não pediu cancel. → +0
    - Classe B → +0

    **Total: -20 pontos** → Faixa MÍNIMA
    """)

st.markdown("""
> **Sobre o fator Consumo (+10 pontos):** Parece contra-intuitivo que usar o plano aumente
> o risco. Isso reflete um viés da base: o 1º contrato (churn naturalmente alto) concentra
> o maior consumo inicial. Quando controlamos pelo ciclo (Página 5), o consumo protege
> no 2º+ contrato. Esse fator pode ser refinado em versões futuras do modelo.
""")

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════
# AS FAIXAS DE RISCO
# ═══════════════════════════════════════════════════════════════════════
st.subheader("Validação: as 5 faixas de risco")
st.markdown("""
Com o score calculado, classificamos cada contrato em 5 faixas. A validação crítica:
o modelo de fato separa quem cancela de quem fica?
""")

@st.cache_data
def load_c(): return pd.read_csv("results/unidade_evolucao_score_c.csv")
@st.cache_data
def load_b(): return pd.read_csv("results/unidade_evolucao_score_b.csv")
@st.cache_data
def load_a(): return pd.read_csv("results/unidade_evolucao_score_a.csv")

try:
    df_c = load_c()

    # KPIs
    total_critico = df_c[df_c["faixa_risco"].str.contains("CRITICO")]["total_contratos"].sum()
    churners_critico = df_c[df_c["faixa_risco"].str.contains("CRITICO")]["churners"].sum()
    total_minimo = df_c[df_c["faixa_risco"].str.contains("MINIMO")]["total_contratos"].sum()
    churners_minimo = df_c[df_c["faixa_risco"].str.contains("MINIMO")]["churners"].sum()

    k1, k2, k3 = st.columns(3)
    k1.metric("Churn na Faixa CRÍTICA", f"{round(100*churners_critico/total_critico,1)}%",
              help="Score 55+. Quase 4 em cada 5 pacientes saem.")
    k2.metric("Churn na Faixa MÍNIMA", f"{round(100*churners_minimo/total_minimo,1)}%",
              help="Score 0-9. Apenas 2 em cada 5 saem.")
    k3.metric("Spread entre Extremos", "40,1 p.p.",
              help="Diferença entre a faixa crítica e a mínima")

    colors = ["#d62728", "#ff7f0e", "#ffbb33", "#2ca02c", "#1f77b4"]
    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=df_c["faixa_risco"],
        y=df_c["total_contratos"],
        name="Nº de Contratos",
        marker_color=[f"rgba({int(c[1:3],16)},{int(c[3:5],16)},{int(c[5:7],16)},0.4)" for c in colors],
        yaxis="y",
        text=df_c["total_contratos"].apply(lambda x: f"{x:,.0f}"),
        textposition="outside",
    ))

    fig.add_trace(go.Scatter(
        x=df_c["faixa_risco"],
        y=df_c["churn_rate"],
        name="Taxa de Churn (%)",
        mode="lines+markers+text",
        marker=dict(size=14, color=colors, line=dict(width=2, color="white")),
        line=dict(width=3, color="gray", dash="dot"),
        yaxis="y2",
        text=df_c["churn_rate"].apply(lambda x: f"{x}%"),
        textposition="top center",
        textfont=dict(size=13, color="crimson"),
    ))

    fig.update_layout(
        title="Validação do Score: Volume & Taxa de Churn por Faixa",
        yaxis=dict(title="Contratos"),
        yaxis2=dict(title="Churn (%)", overlaying="y", side="right", range=[0, 100]),
        legend=dict(orientation="h", y=1.12),
        height=480,
    )
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        df_c[["faixa_risco", "total_contratos", "churners", "churn_rate", "score_medio", "score_min", "score_max"]].rename(
            columns={"faixa_risco": "Faixa", "total_contratos": "Contratos",
                     "churners": "Churners", "churn_rate": "Churn (%)", "score_medio": "Score Médio",
                     "score_min": "Score Mín.", "score_max": "Score Máx."}
        ),
        use_container_width=True, hide_index=True
    )

    st.markdown("""
    #### Validação

    **O modelo funciona.** A taxa de churn cai de forma monotônica conforme o score diminui:
    78% → 59% → 51% → 43% → 38%. As variáveis escolhidas são bons preditores.

    **Onde atuar com mais ROI?** A faixa **ALTO (40-54)** é a mais interessante para intervenção.
    Com 53.704 contratos, é o maior bloco onde ainda dá pra reter — na faixa CRÍTICA,
    78% já é praticamente inevitável.
    """)

except Exception as e:
    st.error(f"Erro: {e}")

# ═══════════════════════════════════════════════════════════════════════
st.markdown("---")
st.subheader("Sazonalidade: quando os pacientes saem?")
st.markdown("""
O score identifica *quem* tem mais risco. Agora, *quando* o churn acontece?
""")

try:
    df_b = load_b()
    df_b["mes_vencimento"] = pd.to_datetime(df_b["mes_vencimento"])
    df_b["duracao_label"] = df_b["duracao"].astype(str) + " meses"

    fig = px.line(
        df_b, x="mes_vencimento", y="churn_rate", color="duracao_label",
        markers=True, line_shape="spline",
        title="A montanha-russa: Taxa de Churn mês a mês",
        labels={"mes_vencimento": "", "churn_rate": "Churn (%)", "duracao_label": "Tipo de Plano"},
        color_discrete_map={"6 meses": "#2ca02c", "12 meses": "#d62728"},
    )
    fig.update_layout(height=420, yaxis_range=[40, 70], xaxis_dtick="M1", xaxis_tickformat="%b/%y")
    st.plotly_chart(fig, use_container_width=True)

    fig_vol = px.bar(
        df_b, x="mes_vencimento", y="total_contratos", color="duracao_label",
        barmode="group",
        title="Quantos contratos vencem em cada mês?",
        labels={"mes_vencimento": "", "total_contratos": "Contratos", "duracao_label": "Tipo de Plano"},
        color_discrete_map={"6 meses": "#2ca02c", "12 meses": "#d62728"},
    )
    fig_vol.update_layout(height=320, xaxis_dtick="M1", xaxis_tickformat="%b/%y")
    st.plotly_chart(fig_vol, use_container_width=True)

    st.markdown("""
    #### Leitura

    1. **Planos de 12 meses consistentemente acima dos de 6** — gap de ~7-10 p.p. mês a mês.

    2. **Dezembro/2025 foi o pior mês** (65,2% nos anuais). Provável efeito de revisão
       de gastos no fim de ano.

    3. **Volume de planos de 6 meses crescendo** — boa notícia, já que é o produto que retém melhor.

    **Ação:** Intensificar réguas de retenção em **outubro-dezembro**, quando o churn dos anuais dispara.
    """)
except Exception as e:
    st.error(f"Erro: {e}")

# ═══════════════════════════════════════════════════════════════════════
st.markdown("---")
st.subheader("Unidades: onde o churn é pior?")
st.markdown("""
Churn por unidade principal de consumo — cada clínica atrai perfis diferentes
e pode ter dinâmicas de retenção distintas.
""")

try:
    df_a = load_a()
    df_unidades = df_a[df_a["unidade"] != "(sem consumo)"].copy()
    sem_consumo = df_a[df_a["unidade"] == "(sem consumo)"]

    if not sem_consumo.empty:
        row = sem_consumo.iloc[0]
        st.warning(f"⚠️ **Atenção:** {int(row['total_contratos']):,} contratos ({row['churn_rate']}% de churn) "
                   f"**nunca pisaram numa clínica**. Esses pacientes são invisíveis para as unidades — "
                   f"precisamos trazê-los para dentro.")

    df_unidades = df_unidades.sort_values("churn_rate", ascending=False)

    fig = px.scatter(
        df_unidades, x="media_itens", y="churn_rate", size="total_contratos",
        color="churn_rate", color_continuous_scale="RdYlGn_r",
        hover_name="unidade", size_max=45,
        title="Cada bolha é uma unidade: tamanho = volume, posição = consumo vs churn",
        labels={"media_itens": "Média de Itens por Paciente", "churn_rate": "Churn (%)"},
    )
    fig.update_layout(height=480, yaxis_range=[40, 68])
    st.plotly_chart(fig, use_container_width=True)

    col_worst, col_best = st.columns(2)
    with col_worst:
        st.markdown("##### 🔴 Maiores taxas de churn")
        top5 = df_unidades.nlargest(5, "churn_rate")[["unidade", "total_contratos", "churn_rate", "media_itens"]]
        top5.columns = ["Unidade", "Contratos", "Churn (%)", "Itens/Paciente"]
        st.dataframe(top5, hide_index=True, use_container_width=True)
    with col_best:
        st.markdown("##### 🟢 Menores taxas de churn")
        bot5 = df_unidades.nsmallest(5, "churn_rate")[["unidade", "total_contratos", "churn_rate", "media_itens"]]
        bot5.columns = ["Unidade", "Contratos", "Churn (%)", "Itens/Paciente"]
        st.dataframe(bot5, hide_index=True, use_container_width=True)

    st.markdown("""
    #### Leitura

    - **TELE** (Telemedicina): pior churn (**64%**) e menor consumo médio. O paciente resolve
      a demanda pontual e não forma vínculo com a rede.

    - **SPMK**: melhor churn entre unidades relevantes (**53%**) com o maior consumo médio
      (16,3 itens). Mais uso presencial = mais retenção.

    - Entre as unidades **físicas**, o spread é pequeno (~53-59%). A experiência presencial
      cria um piso de retenção que o digital não alcança.

    **Pergunta aberta:** Nas unidades com alto churn, o problema é o perfil de paciente
    que chega lá ou a experiência de atendimento? A resposta define se a ação é de mídia
    ou de operação.
    """)
except Exception as e:
    st.error(f"Erro: {e}")

with st.expander("📖 Dicionário de Dados desta Seção", expanded=False):
    st.markdown("""
    | Variável | Significado |
    |---|---|
    | `faixa_risco` | Classificação em 5 bandas baseada no score (CRÍTICO, ALTO, MÉDIO, BAIXO, MÍNIMO) |
    | `score_medio` | Nota média de risco dos contratos dentro da faixa |
    | `score_min` / `score_max` | Limites do score na faixa |
    | `mes_vencimento` | Mês em que o contrato expirou |
    | `duracao` | Duração do plano: 6 ou 12 meses |
    | `unidade` | Código da clínica onde o paciente mais consumiu |
    | `media_itens` | Média de consultas + exames realizados |
    | `(sem consumo)` | Pacientes que nunca realizaram nenhum procedimento |
    """)
