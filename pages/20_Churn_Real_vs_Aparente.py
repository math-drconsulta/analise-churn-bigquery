"""
Pagina 20 — Anatomia do Churn: 3 Destinos
==========================================
Mostra que o churn nao e binario (saiu/ficou).
Quem churna tem 3 destinos: saiu de vez, migrou pro gratis, voltou pro pago.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="Anatomia do Churn", page_icon="🔎", layout="wide")
st.title("🔎 Anatomia do Churn: os 3 Destinos")
st.caption("O que realmente acontece com quem nao renova — e por que 30% migra pro gratis")


# ═══════════════════════════════════════════════════════════════════
# DADOS
# ═══════════════════════════════════════════════════════════════════

@st.cache_data
def load_perfil():
    return pd.read_csv("results/migracao_gratis_perfil.csv")

@st.cache_data
def load_depois():
    return pd.read_csv("results/migracao_gratis_depois.csv")

@st.cache_data
def load_timing():
    return pd.read_csv("results/migracao_gratis_timing.csv")

@st.cache_data
def load_mensal():
    return pd.read_csv("results/winback_30d_mensal.csv")


try:
    df_perfil = load_perfil()
    df_depois = load_depois()
    df_timing = load_timing()
    df_mensal = load_mensal()
except FileNotFoundError as e:
    st.error(f"CSV nao encontrado: {e}")
    st.stop()


# ═══════════════════════════════════════════════════════════════════
# NARRATIVA PRINCIPAL
# ═══════════════════════════════════════════════════════════════════

st.markdown("---")
st.markdown("## O churn nao e binario")

total = int(df_perfil["contratos"].sum())

row_saiu = df_perfil[df_perfil["desfecho"] == "saiu_de_vez"].iloc[0]
row_gratis = df_perfil[df_perfil["desfecho"] == "migrou_gratis"].iloc[0]
row_pago = df_perfil[df_perfil["desfecho"] == "voltou_pago"].iloc[0]

st.markdown(f"""
Analisamos **{total:,} contratos** que nao renovaram (churners).
Em vez de tratar todos como "churn", rastreamos o que aconteceu
com cada um nos 12 meses seguintes. Descobrimos **3 destinos distintos**:
""")

# KPIs dos 3 grupos
k1, k2, k3 = st.columns(3)
k1.metric(
    "🔴 Saiu de vez",
    f"{int(row_saiu['contratos']):,}",
    delta=f"{row_saiu['pct']}%",
    delta_color="inverse",
    help="Nao fez nenhum contrato nos 12 meses seguintes"
)
k2.metric(
    "🟡 Migrou pro gratis",
    f"{int(row_gratis['contratos']):,}",
    delta=f"{row_gratis['pct']}%",
    delta_color="off",
    help="Foi automaticamente migrado para plano gratuito apos falha de pagamento"
)
k3.metric(
    "🟢 Voltou pro pago",
    f"{int(row_pago['contratos']):,}",
    delta=f"{row_pago['pct']}%",
    delta_color="normal",
    help="Fez um novo contrato pago em ate 12 meses"
)

# Donut dos 3 grupos
fig_donut = go.Figure(data=[go.Pie(
    labels=["Saiu de vez", "Migrou pro gratis", "Voltou pro pago"],
    values=[int(row_saiu["contratos"]), int(row_gratis["contratos"]), int(row_pago["contratos"])],
    hole=0.5,
    marker_colors=["#c0392b", "#f39c12", "#27ae60"],
    textinfo="label+percent+value",
    texttemplate="%{label}<br>%{value:,}<br>(%{percent})",
    textfont=dict(size=12),
)])
fig_donut.update_layout(
    title="Os 3 destinos de quem nao renova",
    height=420, showlegend=False,
    annotations=[dict(text=f"{total:,}<br>churners", x=0.5, y=0.5, font_size=14, showarrow=False)],
)
st.plotly_chart(fig_donut, use_container_width=True)

st.markdown(f"""
> **Descoberta critica:** os 30% que migram pro gratis **nao sao retentativas
> de pagamento** como pensavamos. Sao migracoes automaticas para o plano
> gratuito (`cartao dr.consulta - gratis`) apos a falha de cobranca.
> O paciente nao decide voltar — o sistema migra ele automaticamente.
""")


# ═══════════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════════

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Perfil de cada grupo",
    "🔄 O que acontece no gratis",
    "⏱️ Timing",
    "💡 Implicacoes"
])


# ───────────────────────────────────────────────────────────────────
# TAB 1: PERFIL
# ───────────────────────────────────────────────────────────────────
with tab1:
    st.markdown("### Quem e quem: perfil dos 3 grupos")

    st.markdown("""
    Os 3 grupos tem perfis surpreendentemente parecidos em composicao
    (% 1o contrato, % 12 meses), mas diferem muito no **comportamento de saida**:
    """)

    # Tabela comparativa
    df_tab = df_perfil[["desfecho", "contratos", "pct", "pct_1o_contrato",
                         "pct_12m", "pct_pediu_cancelamento", "pct_digital"]].copy()
    df_tab.columns = ["Destino", "Contratos", "%", "% 1o contrato",
                       "% plano 12m", "% pediu cancelamento", "% digital"]
    df_tab["Destino"] = df_tab["Destino"].map({
        "saiu_de_vez": "🔴 Saiu de vez",
        "migrou_gratis": "🟡 Migrou pro gratis",
        "voltou_pago": "🟢 Voltou pro pago",
    })
    st.dataframe(df_tab, use_container_width=True, hide_index=True)

    # Graficos de barras comparativos
    col1, col2 = st.columns(2)

    with col1:
        fig_cancel = go.Figure()
        labels = ["Saiu de vez", "Migrou gratis", "Voltou pago"]
        colors = ["#c0392b", "#f39c12", "#27ae60"]
        vals = [row_saiu["pct_pediu_cancelamento"],
                row_gratis["pct_pediu_cancelamento"],
                row_pago["pct_pediu_cancelamento"]]
        fig_cancel.add_trace(go.Bar(
            x=labels, y=vals,
            marker_color=colors,
            text=[f"{v}%" for v in vals],
            textposition="auto",
        ))
        fig_cancel.update_layout(
            title="% que pediu cancelamento",
            yaxis_title="%", height=350,
        )
        st.plotly_chart(fig_cancel, use_container_width=True)

    with col2:
        fig_12m = go.Figure()
        vals_12 = [row_saiu["pct_12m"], row_gratis["pct_12m"], row_pago["pct_12m"]]
        fig_12m.add_trace(go.Bar(
            x=labels, y=vals_12,
            marker_color=colors,
            text=[f"{v}%" for v in vals_12],
            textposition="auto",
        ))
        fig_12m.update_layout(
            title="% plano 12 meses",
            yaxis_title="%", height=350,
        )
        st.plotly_chart(fig_12m, use_container_width=True)

    st.markdown(f"""
    **Insights do perfil:**

    - **Pediu cancelamento:** {row_saiu['pct_pediu_cancelamento']}% de quem saiu de vez pediu cancelamento,
      vs apenas {row_gratis['pct_pediu_cancelamento']}% de quem migrou pro gratis.
      Quem migra pro gratis **nao pediu pra sair** — o pagamento falhou e o sistema migrou automaticamente.

    - **Plano 12m:** quem volta pro pago tem a maior taxa de plano anual ({row_pago['pct_12m']}%),
      sugerindo que contratos mais longos tem maior chance de reconversao.

    - **1o contrato:** os 3 grupos sao similares (~65-67%), indicando que ser primeiro contrato
      nao diferencia quem sai de quem migra pro gratis.
    """)


# ───────────────────────────────────────────────────────────────────
# TAB 2: O QUE ACONTECE NO GRATIS
# ───────────────────────────────────────────────────────────────────
with tab2:
    st.markdown("### Jornada pos-gratis: a grande maioria nao volta")

    # Dados do step 2
    row_sem = df_depois[df_depois["jornada_status"] == "sem_gratis"].iloc[0]
    row_g_saiu = df_depois[df_depois["jornada_status"] == "gratis_depois_saiu"].iloc[0]
    row_g_pago = df_depois[df_depois["jornada_status"] == "gratis_depois_pago"].iloc[0]

    total_com_gratis = int(row_g_saiu["contratos"]) + int(row_g_pago["contratos"])
    pct_saiu_gratis = round(100 * int(row_g_saiu["contratos"]) / total_com_gratis, 1)
    pct_voltou_gratis = round(100 * int(row_g_pago["contratos"]) / total_com_gratis, 1)

    st.markdown(f"""
    Dos churners que migram pro gratis, rastreamos o que acontece depois:
    """)

    k1, k2, k3 = st.columns(3)
    k1.metric("Total que foi pro gratis", f"{total_com_gratis:,}")
    k2.metric("Saiu do gratis sem voltar", f"{int(row_g_saiu['contratos']):,}",
              delta=f"{pct_saiu_gratis}%", delta_color="inverse")
    k3.metric("Voltou pro pago", f"{int(row_g_pago['contratos']):,}",
              delta=f"{pct_voltou_gratis}%", delta_color="normal")

    # Funnel
    fig_funnel = go.Figure(go.Funnel(
        y=["Churners totais", "Migrou pro gratis", "Ficou no gratis e saiu", "Voltou pro pago"],
        x=[total, int(row_gratis["contratos"]), int(row_g_saiu["contratos"]), int(row_g_pago["contratos"])],
        textinfo="value+percent initial",
        marker_color=["#95a5a6", "#f39c12", "#c0392b", "#27ae60"],
    ))
    fig_funnel.update_layout(
        title="Funil: do churn ao retorno pelo gratis",
        height=400,
    )
    st.plotly_chart(fig_funnel, use_container_width=True)

    st.markdown(f"""
    **O gratis nao recupera clientes.** De cada 100 churners:
    - **30** migram pro gratis
    - Desses 30, **{round(30 * pct_saiu_gratis / 100)}** saem de vez depois (~{pct_saiu_gratis}%)
    - Apenas **{round(30 * pct_voltou_gratis / 100)}** voltam pro pago (~{pct_voltou_gratis}%)

    O tempo medio no gratis e de **{int(row_g_saiu['media_dias_no_gratis'])} dias** — cerca de 2 meses.
    Depois disso, a grande maioria simplesmente sai.

    > **Implicacao:** o plano gratis funciona mais como uma **sala de espera pro churn**
    > do que como ferramenta de retencao. Apenas ~18% dos que entram voltam pro pago.
    """)


# ───────────────────────────────────────────────────────────────────
# TAB 3: TIMING
# ───────────────────────────────────────────────────────────────────
with tab3:
    st.markdown("### Quando a migracao pro gratis acontece")

    # Dados de timing
    df_gratis_timing = df_timing[df_timing["status"] == "migrou_gratis"].copy()

    st.markdown("""
    A migracao pro gratis nao e decisao do paciente — e um processo automatico
    que acontece num timing muito especifico:
    """)

    # Barras por faixa
    fig_timing = go.Figure()
    fig_timing.add_trace(go.Bar(
        x=df_gratis_timing["faixa_dias"],
        y=df_gratis_timing["contratos"],
        marker_color=["#bdc3c7", "#f39c12", "#bdc3c7", "#bdc3c7"],
        text=[f"{int(c):,}" for c in df_gratis_timing["contratos"]],
        textposition="auto",
    ))
    fig_timing.update_layout(
        title="Distribuicao: em quantos dias migram pro gratis",
        xaxis_title="Dias apos vencimento",
        yaxis_title="Contratos",
        height=380,
    )
    st.plotly_chart(fig_timing, use_container_width=True)

    # Highlight do 15-21
    row_15_21 = df_gratis_timing[df_gratis_timing["faixa_dias"] == "15-21 dias"]
    if len(row_15_21) > 0:
        n_15_21 = int(row_15_21.iloc[0]["contratos"])
        pct_15_21 = row_15_21.iloc[0]["pct"]
        total_gratis = int(df_gratis_timing["contratos"].sum())

        k1, k2, k3 = st.columns(3)
        k1.metric("Total migracoes pro gratis", f"{total_gratis:,}")
        k2.metric("Entre 15-21 dias", f"{n_15_21:,}",
                  delta=f"{pct_15_21}%", delta_color="off")
        k3.metric("Media days_diff", f"{row_15_21.iloc[0]['media_days_diff']:.0f} dias")

    st.markdown(f"""
    **{pct_15_21}% das migracoes acontecem entre 15-21 dias** apos o vencimento.
    Esse timing e identico ao ciclo de retentativa de pagamento do gateway.

    O processo real:
    1. Contrato vence, pagamento falha
    2. Sistema retenta cobranca automaticamente por ~15-21 dias
    3. Se nao consegue cobrar, migra automaticamente pro plano gratis
    4. Paciente fica no gratis por ~61 dias em media
    5. 82% saem de vez, 18% eventualmente voltam pro pago
    """)

    # Evolucao mensal do retorno 30d (contextual)
    st.markdown("---")
    st.markdown("### Contexto: evolucao mensal")

    df_mensal["mes_vencimento"] = pd.to_datetime(df_mensal["mes_vencimento"])

    fig_mensal = go.Figure()
    fig_mensal.add_trace(go.Scatter(
        x=df_mensal["mes_vencimento"], y=df_mensal["churn_rate"],
        name="Churn aparente", mode="lines+markers",
        line=dict(color="#95a5a6", width=2, dash="dot"),
    ))
    fig_mensal.add_trace(go.Scatter(
        x=df_mensal["mes_vencimento"], y=df_mensal["churn_real_rate"],
        name="Churn real (sem retorno 30d)", mode="lines+markers",
        line=dict(color="#c0392b", width=3),
    ))
    fig_mensal.add_trace(go.Bar(
        x=df_mensal["mes_vencimento"], y=df_mensal["pct_retorno_30d"],
        name="% retorno 30d", marker_color="#3498db", opacity=0.3,
        yaxis="y2",
    ))
    fig_mensal.update_layout(
        title="Churn aparente vs real — evolucao mensal",
        yaxis=dict(title="Churn (%)", range=[0, 70]),
        yaxis2=dict(title="% retorno 30d", overlaying="y", side="right", range=[0, 80]),
        height=420,
        legend=dict(orientation="h", y=1.12),
    )
    st.plotly_chart(fig_mensal, use_container_width=True)


# ───────────────────────────────────────────────────────────────────
# TAB 4: IMPLICACOES
# ───────────────────────────────────────────────────────────────────
with tab4:
    st.markdown("### O que isso muda na estrategia")

    st.markdown(f"""
    A descoberta de que o churn tem 3 destinos — e nao 2 — muda
    fundamentalmente como devemos abordar o problema:
    """)

    st.markdown("""
    ---
    #### 1. O churn "real" nao e 24% — e maior

    Na versao anterior desta analise, diziamos que o churn real era ~24%
    porque 30% "voltavam em 30 dias" (retentativas de pagamento).

    **Isso estava errado.** Esses 30% nao sao retentativas — sao migracoes
    automaticas pro plano gratis. E 82% deles eventualmente saem de vez.

    O churn efetivo (quem sai e nao volta pro pago) e:
    """)

    # Calculo do churn efetivo
    n_saiu = int(row_saiu["contratos"])
    n_gratis_saiu = int(row_g_saiu["contratos"])
    n_churn_efetivo = n_saiu + n_gratis_saiu
    pct_churn_efetivo = round(100 * n_churn_efetivo / total, 1)

    k1, k2, k3 = st.columns(3)
    k1.metric("Saiu de vez", f"{n_saiu:,}", delta=f"{row_saiu['pct']}%", delta_color="inverse")
    k2.metric("Gratis → saiu", f"{n_gratis_saiu:,}",
              delta=f"{round(100*n_gratis_saiu/total,1)}%", delta_color="inverse")
    k3.metric("Churn efetivo total", f"{n_churn_efetivo:,}",
              delta=f"{pct_churn_efetivo}% dos churners", delta_color="inverse")

    st.markdown(f"""
    ---
    #### 2. Tres problemas distintos exigem tres acoes distintas

    | Grupo | Volume | Problema | Acao sugerida |
    |---|---|---|---|
    | 🔴 **Saiu de vez** | {row_saiu['pct']}% | Decisao ativa — 64.6% pediu cancelamento | Retencao proativa antes do vencimento |
    | 🟡 **Migrou pro gratis** | {row_gratis['pct']}% | Falha de pagamento → gratis → saida | Resolver cobranca ANTES da migracao |
    | 🟢 **Voltou pro pago** | {row_pago['pct']}% | Temporariamente sem contrato, mas voltou | Acelerar reconversao (media 56 dias) |

    ---
    #### 3. O plano gratis e uma armadilha, nao uma rede de seguranca

    O gratis deveria ser uma ponte de retorno. Na pratica:
    - **82%** de quem entra no gratis sai de vez depois
    - Apenas **18%** volta pro pago
    - Tempo medio no gratis: **61 dias** (2 meses "gratis" sem converter)

    > **Recomendacao:** revisar a politica de migracao automatica pro gratis.
    > Se a cobranca falha, talvez seja melhor uma abordagem ativa
    > (notificacao, contato SAC, oferta de desconto) do que migrar
    > silenciosamente pro gratis — onde 82% se perdem.

    ---
    #### 4. Impacto no score de churn

    A correcao do target (excluindo retornos em 30 dias) continua valida
    e melhorou o AUC de **0.59 → 0.65**. Mas agora entendemos POR QUE:
    - Os 30% que migravam pro gratis tinham perfil similar aos outros churners
    - O modelo nao conseguia distingui-los porque **nao e perfil que os separa — e o gateway**
    - Ao excluir, removemos ruido do processamento de pagamento do sinal de comportamento
    """)

    st.markdown("""
    ---
    #### 5. Proximos passos sugeridos

    1. **Curto prazo:** compartilhar com Financeiro/Pagamentos o dado de que
       30% dos churners sao migrados pro gratis por falha de cobranca
    2. **Medio prazo:** testar intervencao ativa nos 15-21 dias pos-vencimento
       (antes da migracao automatica pro gratis)
    3. **Longo prazo:** revisar se o plano gratis deve existir como destino
       automatico ou se uma abordagem de retencao ativa seria mais eficaz
    """)
