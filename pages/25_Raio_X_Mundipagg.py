"""
Pagina 25 — Raio-X Mundipagg
==============================
Visao operacional do gateway de pagamentos: clientes ativos,
tipos de cartao, frequencia de cobranca, taxa de sucesso,
chargebacks e receita mensal processada.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="Raio-X Mundipagg", page_icon="🏦", layout="wide")
st.title("🏦 Raio-X Mundipagg")
st.caption("Indicadores operacionais do gateway de pagamentos — solicitacao PM Growth")


# ═══════════════════════════════════════════════════════════════════
# DADOS
# ═══════════════════════════════════════════════════════════════════

@st.cache_data
def load_status():
    return pd.read_csv("results/mundi_clientes_status.csv")

@st.cache_data
def load_tipo_cartao():
    return pd.read_csv("results/mundi_tipo_cartao.csv")

@st.cache_data
def load_frequencia():
    return pd.read_csv("results/mundi_frequencia_cobranca.csv")

@st.cache_data
def load_sucesso():
    return pd.read_csv("results/mundi_taxa_sucesso_30d.csv")

@st.cache_data
def load_chargeback():
    return pd.read_csv("results/mundi_chargeback_90d.csv")

@st.cache_data
def load_receita():
    return pd.read_csv("results/mundi_receita_mensal.csv")


try:
    df_status = load_status()
    df_tipo = load_tipo_cartao()
    df_freq = load_frequencia()
    df_suc = load_sucesso()
    df_cb = load_chargeback()
    df_rec = load_receita()
except FileNotFoundError as e:
    st.error(f"CSV nao encontrado: {e}")
    st.stop()


# ═══════════════════════════════════════════════════════════════════
# KPIs PRINCIPAIS
# ═══════════════════════════════════════════════════════════════════

st.markdown("---")

# Totais de status
total_clientes = int(df_status["clientes_distintos"].sum())
ativos = df_status.loc[df_status["status_subscription"] == "active", "clientes_distintos"]
ativos = int(ativos.values[0]) if len(ativos) else 0
pct_ativos = round(100 * ativos / total_clientes, 1) if total_clientes else 0

cancelados = df_status.loc[df_status["status_subscription"] == "canceled", "clientes_distintos"]
cancelados = int(cancelados.values[0]) if len(cancelados) else 0

# Taxa de sucesso
taxa_sucesso = float(df_suc["taxa_sucesso_pct"].values[0])

# Receita ultimo mes completo (penultima linha, pois a ultima pode ser parcial)
df_rec_completo = df_rec[df_rec["transacoes_autorizadas"] > 1000]
ultimo_mes = df_rec_completo.iloc[-1]
receita_ultimo = float(ultimo_mes["receita_processada_brl"])
mes_label = str(ultimo_mes["mes"])

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total de Clientes", f"{total_clientes:,.0f}")
k2.metric("Recorrencia Ativa", f"{ativos:,.0f}", f"{pct_ativos}%")
k3.metric("Taxa de Sucesso (30d)", f"{taxa_sucesso}%")
k4.metric(f"Receita ({mes_label})", f"R$ {receita_ultimo:,.0f}")

st.markdown("---")


# ═══════════════════════════════════════════════════════════════════
# BLOCO 1: STATUS DOS CLIENTES
# ═══════════════════════════════════════════════════════════════════

st.subheader("1. Distribuicao de Clientes por Status")

col1, col2 = st.columns([1, 1])

with col1:
    df_status_show = df_status[df_status["clientes_distintos"] > 0].copy()
    df_status_show["status_subscription"] = df_status_show["status_subscription"].fillna("(vazio)")

    fig_status = go.Figure(go.Pie(
        labels=df_status_show["status_subscription"],
        values=df_status_show["clientes_distintos"],
        textinfo="label+percent",
        hole=0.4,
        marker=dict(colors=["#2ecc71", "#e74c3c", "#95a5a6", "#f39c12", "#3498db"])
    ))
    fig_status.update_layout(
        title="Clientes por Status de Subscription",
        height=400,
        margin=dict(t=40, b=20)
    )
    st.plotly_chart(fig_status, use_container_width=True)

with col2:
    st.dataframe(
        df_status_show[["status_subscription", "subscriptions", "clientes_distintos", "pct"]]
        .rename(columns={
            "status_subscription": "Status",
            "subscriptions": "Subscriptions",
            "clientes_distintos": "Clientes",
            "pct": "% do Total"
        }),
        use_container_width=True,
        hide_index=True
    )

    st.markdown(f"""
    **Resumo:**
    - **{ativos:,}** clientes com recorrencia ativa ({pct_ativos}%)
    - **{cancelados:,}** cancelados ({round(100 * cancelados / total_clientes, 1)}%)
    """)

st.markdown("---")


# ═══════════════════════════════════════════════════════════════════
# BLOCO 2: TIPO DE CARTAO / TRANSACAO
# ═══════════════════════════════════════════════════════════════════

st.subheader("2. Distribuicao por Tipo de Transacao")

col1, col2 = st.columns([1, 1])

with col1:
    fig_tipo = go.Figure(go.Bar(
        x=df_tipo["tipo_transacao"],
        y=df_tipo["transacoes"],
        text=df_tipo["pct_transacoes"].apply(lambda x: f"{x}%"),
        textposition="outside",
        marker_color=["#3498db", "#2ecc71", "#e67e22", "#e74c3c", "#9b59b6"][:len(df_tipo)]
    ))
    fig_tipo.update_layout(
        title="Volume por Tipo (ultimos 90 dias)",
        yaxis_title="Transacoes",
        height=400,
        margin=dict(t=40, b=20)
    )
    st.plotly_chart(fig_tipo, use_container_width=True)

with col2:
    st.dataframe(
        df_tipo.rename(columns={
            "tipo_transacao": "Tipo",
            "transacoes": "Transacoes",
            "clientes": "Clientes",
            "pct_transacoes": "% Transacoes",
            "valor_total": "Valor Total (R$)"
        }),
        use_container_width=True,
        hide_index=True
    )

st.markdown("---")


# ═══════════════════════════════════════════════════════════════════
# BLOCO 3: FREQUENCIA DE COBRANCA
# ═══════════════════════════════════════════════════════════════════

st.subheader("3. Frequencia de Cobranca")

col1, col2 = st.columns([1, 1])

with col1:
    fig_freq = go.Figure(go.Pie(
        labels=df_freq["frequencia"],
        values=df_freq["subscriptions"],
        textinfo="label+percent",
        hole=0.4,
        marker=dict(colors=["#9b59b6", "#3498db", "#2ecc71", "#e67e22"])
    ))
    fig_freq.update_layout(
        title="Subscriptions por Frequencia",
        height=400,
        margin=dict(t=40, b=20)
    )
    st.plotly_chart(fig_freq, use_container_width=True)

with col2:
    st.dataframe(
        df_freq.rename(columns={
            "frequencia": "Frequencia",
            "ciclos": "Ciclos",
            "subscriptions": "Subscriptions",
            "pct_subscriptions": "% do Total",
            "media_dias": "Media Dias entre Ciclos"
        }),
        use_container_width=True,
        hide_index=True
    )

    st.info("""
    **Nota:** 89% das subscriptions tem frequencia "customizada" (media ~242 dias),
    o que indica que a maioria sao planos semestrais/anuais com cobranca unica,
    nao recorrencia mensal.
    """)

st.markdown("---")


# ═══════════════════════════════════════════════════════════════════
# BLOCO 4: TAXA DE SUCESSO
# ═══════════════════════════════════════════════════════════════════

st.subheader("4. Taxa de Sucesso (ultimos 30 dias)")

total_tx = int(df_suc["total_transacoes"].values[0])
autorizadas = int(df_suc["autorizadas"].values[0])
negadas = int(df_suc["negadas"].values[0])
outros = int(df_suc["outros_status"].values[0])

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Transacoes", f"{total_tx:,}")
col2.metric("Autorizadas", f"{autorizadas:,}")
col3.metric("Negadas", f"{negadas:,}")
col4.metric("Outros Status", f"{outros:,}")

fig_suc = go.Figure()
fig_suc.add_trace(go.Bar(
    x=["Autorizadas", "Negadas", "Outros"],
    y=[autorizadas, negadas, outros],
    marker_color=["#2ecc71", "#e74c3c", "#95a5a6"],
    text=[f"{autorizadas:,}", f"{negadas:,}", f"{outros:,}"],
    textposition="outside"
))
fig_suc.update_layout(
    title=f"Taxa de Sucesso: {taxa_sucesso}%",
    yaxis_title="Transacoes",
    height=350,
    margin=dict(t=40, b=20)
)
st.plotly_chart(fig_suc, use_container_width=True)

if outros > autorizadas * 0.5:
    st.warning(f"""
    **Atencao:** {outros:,} transacoes ({round(100 * outros / total_tx, 1)}%) estao com status
    diferente de Autorizada/Negada (ex: Checkout Criado, Enviado, Pendente).
    A taxa de sucesso de {taxa_sucesso}% considera apenas A vs N.
    """)

st.markdown("---")


# ═══════════════════════════════════════════════════════════════════
# BLOCO 5: CHARGEBACKS
# ═══════════════════════════════════════════════════════════════════

st.subheader("5. Chargebacks / Estornos (ultimos 90 dias)")

if len(df_cb) > 0:
    total_cb = int(df_cb["eventos"].sum())
    clientes_cb = int(df_cb["clientes"].sum())

    # Calcular taxa sobre capturas dos ultimos 90 dias
    capturas_90d = int(df_tipo.loc[df_tipo["tipo_transacao"] == "Captura", "transacoes"].values[0]) \
        if "Captura" in df_tipo["tipo_transacao"].values else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Cancelamentos/Estornos", f"{total_cb:,}")
    col2.metric("Clientes Afetados", f"{clientes_cb:,}")
    if capturas_90d > 0:
        taxa_cb = round(100 * total_cb / capturas_90d, 2)
        col3.metric("Taxa sobre Capturas", f"{taxa_cb}%")

    st.dataframe(
        df_cb.rename(columns={
            "fonte": "Fonte",
            "event_code": "Tipo",
            "eventos": "Eventos",
            "clientes": "Clientes"
        }),
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("Nenhum evento de chargeback encontrado nos ultimos 90 dias.")

st.markdown("---")


# ═══════════════════════════════════════════════════════════════════
# BLOCO 6: RECEITA MENSAL
# ═══════════════════════════════════════════════════════════════════

st.subheader("6. Receita Mensal Processada")

df_rec_plot = df_rec[df_rec["transacoes_autorizadas"] > 1000].copy()

fig_rec = make_subplots(specs=[[{"secondary_y": True}]])

fig_rec.add_trace(
    go.Bar(
        x=df_rec_plot["mes"],
        y=df_rec_plot["receita_processada_brl"],
        name="Receita (R$)",
        marker_color="#3498db",
        text=df_rec_plot["receita_processada_brl"].apply(lambda x: f"R$ {x/1e6:.1f}M"),
        textposition="outside"
    ),
    secondary_y=False
)

fig_rec.add_trace(
    go.Scatter(
        x=df_rec_plot["mes"],
        y=df_rec_plot["ticket_medio"],
        name="Ticket Medio (R$)",
        mode="lines+markers",
        line=dict(color="#e74c3c", width=2),
        marker=dict(size=8)
    ),
    secondary_y=True
)

fig_rec.update_layout(
    title="Receita Processada e Ticket Medio — Ultimos 12 Meses",
    height=450,
    margin=dict(t=40, b=20),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)
fig_rec.update_yaxes(title_text="Receita (R$)", secondary_y=False)
fig_rec.update_yaxes(title_text="Ticket Medio (R$)", secondary_y=True)

st.plotly_chart(fig_rec, use_container_width=True)

# Tabela com detalhes
st.dataframe(
    df_rec_plot.rename(columns={
        "mes": "Mes",
        "transacoes_autorizadas": "Transacoes",
        "clientes_cobrando": "Clientes",
        "receita_processada_brl": "Receita (R$)",
        "ticket_medio": "Ticket Medio (R$)"
    }),
    use_container_width=True,
    hide_index=True
)

# Resumo de receita
receita_media = df_rec_plot["receita_processada_brl"].mean()
clientes_medio = df_rec_plot["clientes_cobrando"].mean()
ticket_medio = df_rec_plot["ticket_medio"].mean()

st.markdown(f"""
**Resumo (media mensal):**
- Receita processada: **R$ {receita_media:,.0f}** (~R$ {receita_media/1e6:.1f}M/mes)
- Clientes cobrando: **{clientes_medio:,.0f}**
- Ticket medio: **R$ {ticket_medio:.2f}**
""")
