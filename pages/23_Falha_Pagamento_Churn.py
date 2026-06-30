"""
Pagina 23 — Falha de Pagamento e Churn
========================================
Analise completa: quanto do churn e causado por falha de pagamento,
proporcao Adyen vs Mundipagg, impacto da mudanca Adyen 15/05,
motivos de recusa, e evolucao semanal.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="Falha de Pagamento e Churn", page_icon="💳", layout="wide")
st.title("💳 Falha de Pagamento e Churn")
st.caption("De cada 100 contratos que vencem, quantos churn por falha no cartao?")


# ═══════════════════════════════════════════════════════════════════
# DADOS
# ═══════════════════════════════════════════════════════════════════

@st.cache_data
def load_diagnostico():
    return pd.read_csv("results/falha_pgto_diagnostico.csv")

@st.cache_data
def load_adyen_mundi():
    df = pd.read_csv("results/falha_pgto_adyen_vs_mundi.csv")
    df["taxa_aprov_adyen_pct"] = (df["taxa_aprov_adyen"] * 100).round(1)
    df["taxa_aprov_mundi_pct"] = (df["taxa_aprov_mundi"] * 100).round(1)
    return df

@st.cache_data
def load_semanal():
    return pd.read_csv("results/falha_pgto_semanal.csv")

@st.cache_data
def load_motivos():
    return pd.read_csv("results/falha_pgto_motivos.csv")


try:
    df_diag = load_diagnostico()
    df_am = load_adyen_mundi()
    df_sem = load_semanal()
    df_mot = load_motivos()
except FileNotFoundError as e:
    st.error(f"CSV nao encontrado: {e}")
    st.stop()

# Ordenar semanas
ORDEM_SEM = [
    "sem_-4", "sem_-3", "sem_-2", "sem_-1",
    "sem_+1", "sem_+2", "sem_+3", "sem_+4", "sem_+5", "sem_+6",
]
LABELS_SEM = {
    "sem_-4": "17-23/abr", "sem_-3": "24-30/abr",
    "sem_-2": "01-07/mai", "sem_-1": "08-14/mai",
    "sem_+1": "15-21/mai", "sem_+2": "22-28/mai",
    "sem_+3": "29mai-04jun", "sem_+4": "05-11/jun",
    "sem_+5": "12-18/jun", "sem_+6": "19-23/jun",
}

for df_temp in [df_am, df_sem]:
    df_temp["semana_key"] = df_temp["semana"].str.extract(r'(sem_[+-]?\d+)')[0]
    df_temp["semana_ord"] = df_temp["semana_key"].map({s: i for i, s in enumerate(ORDEM_SEM)})
    df_temp["semana_label"] = df_temp["semana_key"].map(LABELS_SEM)
    df_temp = df_temp.sort_values("semana_ord")

df_am = df_am.sort_values("semana_ord")
df_sem = df_sem.sort_values("semana_ord")


# ═══════════════════════════════════════════════════════════════════
# INTRO — NUMEROS-CHAVE
# ═══════════════════════════════════════════════════════════════════

total_contratos = int(df_diag["contratos"].sum())
renovados = int(df_diag[df_diag["diagnostico"] == "renovado"]["contratos"].sum())
total_churners = int(df_diag[df_diag["churn_sn"] == "S"]["contratos"].sum())
falha_pgto = int(df_diag[df_diag["diagnostico"] == "falha_pagamento"]["contratos"].sum())
cancelou = int(df_diag[df_diag["diagnostico"] == "cancelou_ativo"]["contratos"].sum())
pct_churn = round(100 * total_churners / total_contratos, 1)
pct_falha_do_churn = round(100 * falha_pgto / total_churners, 1)
pct_falha_do_total = round(100 * falha_pgto / total_contratos, 1)

st.markdown("---")

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Contratos analisados", f"{total_contratos:,}",
          help="Abr-Jun 2026, credit card, 6/12m, sem B2B")
k2.metric("Renovaram", f"{renovados:,}",
          delta=f"{round(100*renovados/total_contratos,1)}%", delta_color="normal")
k3.metric("Churners", f"{total_churners:,}",
          delta=f"{pct_churn}%", delta_color="inverse")
k4.metric("Falha de pagamento", f"{falha_pgto:,}",
          delta=f"{pct_falha_do_churn}% do churn", delta_color="inverse")
k5.metric("Cancelou ativamente", f"{cancelou:,}",
          delta=f"{round(100*cancelou/total_churners,1)}% do churn", delta_color="off")

st.markdown(f"""
**A descoberta central:** de cada 100 contratos que vencem, **{round(pct_falha_do_total)}
nao renovam por falha no cartao** — o paciente nao pediu pra sair, o pagamento simplesmente
nao passou. Isso representa **{pct_falha_do_churn}% de todo o churn**.
""")


# ═══════════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════════

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📐 Universo Analisado",
    "🔍 Diagnostico do Churn",
    "⚖️ Adyen vs Mundipagg",
    "📈 Impacto Mudanca 15/05",
    "🚫 Motivos de Recusa",
    "💡 Conclusoes",
])


# ═══════════════════════════════════════════════════════════════════
# TAB 1: UNIVERSO ANALISADO
# ═══════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("### De onde vem cada numero")

    st.markdown("""
    ---
    #### Fonte de dados
    """)

    st.markdown("""
    | Aspecto | Detalhe |
    |---|---|
    | **Tabela principal** | `YALO_DW.ref_yalo_subscriptions` (snapshot mais recente por contrato) |
    | **Pagamentos Adyen** | `yalo.public_adyen_events` (tentativas de cobranca via Adyen) |
    | **Pagamentos Mundipagg** | `yalo.public_payment_partner_charges` (via cadeia de joins) |
    | **Planos** | `yalo.public_account_plans` (flag is_recurrent) |
    """)

    st.markdown("""
    ---
    #### Filtros aplicados (universo base)

    ```sql
    WHERE account_type = 'holder'              -- apenas titulares
      AND payment_method = 'credit_card'       -- apenas cartao de credito
      AND plan_months_duration IN (6, 12)      -- planos semestrais e anuais
      AND plan_name NOT LIKE '%gratis%'        -- exclui planos gratuitos
      AND IFNULL(order_source_aj, '') != 'b2b' -- exclui vendas corporativas
      AND contract_due_date BETWEEN '2026-04-17' AND '2026-06-23'
    QUALIFY ROW_NUMBER() OVER (
      PARTITION BY contract_id ORDER BY date_month DESC
    ) = 1                                      -- snapshot mais recente
    ```
    """)

    st.markdown("""
    ---
    #### Janela temporal
    """)

    col_t1, col_t2 = st.columns(2)
    with col_t1:
        st.markdown("""
        **PRE mudanca Adyen** (4 semanas)
        - sem -4: 17-23/abr/2026
        - sem -3: 24-30/abr/2026
        - sem -2: 01-07/mai/2026
        - sem -1: 08-14/mai/2026
        """)
    with col_t2:
        st.markdown("""
        **POS mudanca Adyen** (6 semanas)
        - sem +1: 15-21/mai/2026
        - sem +2: 22-28/mai/2026
        - sem +3: 29/mai-04/jun/2026
        - sem +4: 05-11/jun/2026
        - sem +5: 12-18/jun/2026
        - sem +6: 19-23/jun/2026 *(parcial, 5 dias)*
        """)

    st.markdown("---")
    st.markdown("#### Como as tentativas de pagamento sao capturadas")

    st.markdown("""
    Para cada contrato, buscamos tentativas de cobranca em **ambos os adquirentes**
    numa janela de **7 dias antes ate 30 dias apos** o vencimento do contrato:

    ```
    Adyen:     public_adyen_events.created_at
               BETWEEN (contract_due_date - 7 dias) AND (contract_due_date + 30 dias)

    Mundipagg: public_payment_partner_charges.created_at
               BETWEEN (contract_due_date - 7 dias) AND (contract_due_date + 30 dias)
    ```

    Isso garante que capturamos tanto tentativas pre-vencimento (preventivas)
    quanto retentativas pos-vencimento (recuperacao).
    """)

    st.markdown("---")
    st.markdown("#### Volumes por semana")

    df_vol = df_am[["semana_label", "periodo", "contratos", "contratos_adyen",
                     "contratos_mundi", "sem_tentativa"]].copy()
    df_vol.columns = ["Semana", "Periodo", "Total", "Com Adyen", "Com Mundi", "Sem tentativa"]
    st.dataframe(df_vol, hide_index=True, use_container_width=True)

    total_sem = int(df_am["sem_tentativa"].sum())
    st.markdown(f"""
    **Nota:** {total_sem:,} contratos ({round(100*total_sem/total_contratos,1)}%)
    nao tiveram nenhuma tentativa de cobranca registrada nos dois adquirentes.
    Podem ser contratos processados por outro gateway ou falhas de integracao.
    """)


# ═══════════════════════════════════════════════════════════════════
# TAB 2: DIAGNOSTICO DO CHURN
# ═══════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("### Por que os contratos nao renovam?")
    st.markdown("Classificamos cada contrato em 5 diagnosticos baseados no cruzamento "
                "entre **status de churn** e **tentativas de pagamento**.")

    st.markdown("---")

    # Definicoes
    st.markdown("""
    #### Definicao dos diagnosticos

    | Diagnostico | Logica | Significa |
    |---|---|---|
    | **Renovado** | `account_due_date - contract_due_date > 7 dias` | Contrato renovado normalmente |
    | **Falha de pagamento** | Churnou + teve recusas + zero sucessos | Cartao recusado em todas as tentativas |
    | **Cancelou ativamente** | Churnou + `flag_unsubscription = TRUE` | Paciente pediu cancelamento |
    | **Sem tentativa** | Churnou + zero tentativas registradas | Nenhuma cobranca nos dois gateways |
    | **Cobrado mas churnou** | Churnou + teve pelo menos 1 sucesso | Pagamento passou mas contrato nao renovou (anomalia) |
    """)

    st.markdown("---")
    st.markdown("#### Distribuicao")

    # Preparar dados
    diag_order = ["renovado", "falha_pagamento", "cancelou_ativo", "sem_tentativa", "cobrado_mas_churnou"]
    diag_labels = {
        "renovado": "Renovado",
        "falha_pagamento": "Falha de pagamento",
        "cancelou_ativo": "Cancelou ativamente",
        "sem_tentativa": "Sem tentativa",
        "cobrado_mas_churnou": "Cobrado mas churnou",
    }
    diag_cores = {
        "renovado": "#27ae60",
        "falha_pagamento": "#e74c3c",
        "cancelou_ativo": "#f39c12",
        "sem_tentativa": "#95a5a6",
        "cobrado_mas_churnou": "#8e44ad",
    }

    df_diag_plot = df_diag.copy()
    df_diag_plot["label"] = df_diag_plot["diagnostico"].map(diag_labels)
    df_diag_plot["cor"] = df_diag_plot["diagnostico"].map(diag_cores)
    df_diag_plot = df_diag_plot.set_index("diagnostico").reindex(diag_order).reset_index()

    # Donut: todos os contratos
    fig_donut = go.Figure(data=[go.Pie(
        labels=df_diag_plot["label"],
        values=df_diag_plot["contratos"],
        hole=0.5,
        marker_colors=df_diag_plot["cor"],
        textinfo="label+percent",
        textfont=dict(size=12),
        hovertemplate="%{label}<br>%{value:,} contratos<br>%{percent}<extra></extra>",
    )])
    fig_donut.update_layout(
        title=f"Diagnostico de {total_contratos:,} contratos (abr-jun 2026)",
        height=450, showlegend=False,
        annotations=[dict(text=f"{total_contratos:,}<br>contratos", x=0.5, y=0.5,
                          font_size=14, showarrow=False)],
    )
    st.plotly_chart(fig_donut, use_container_width=True)

    # KPIs do churn
    st.markdown("---")
    st.markdown("#### Composicao do churn")

    fig_churn_comp = go.Figure()
    churner_diags = df_diag_plot[df_diag_plot["churn_sn"] == "S"]
    for _, row in churner_diags.iterrows():
        pct_of_churn = round(100 * row["contratos"] / total_churners, 1)
        fig_churn_comp.add_trace(go.Bar(
            x=[pct_of_churn],
            y=["Composicao do churn"],
            orientation="h",
            name=row["label"],
            marker_color=row["cor"],
            text=f"{row['label']}<br>{pct_of_churn}% ({int(row['contratos']):,})",
            textposition="inside",
            textfont=dict(size=11, color="white"),
            hovertemplate=f"{row['label']}: {int(row['contratos']):,} ({pct_of_churn}%)<extra></extra>",
        ))

    fig_churn_comp.update_layout(
        barmode="stack",
        title=f"De que e feito o churn? ({total_churners:,} churners)",
        xaxis=dict(title="% do churn total", range=[0, 105]),
        yaxis=dict(visible=False),
        height=180,
        legend=dict(orientation="h", y=-0.3),
        margin=dict(l=20, r=20, t=60, b=60),
    )
    st.plotly_chart(fig_churn_comp, use_container_width=True)

    st.markdown(f"""
    **Leitura:** de cada **100 pacientes que churn**:
    - **{round(100*falha_pgto/total_churners)}** saem porque o **cartao foi recusado** (nao pediram pra sair)
    - **{round(100*cancelou/total_churners)}** pediram cancelamento ativamente
    - **{round(100*835/total_churners)}** nao tiveram nenhuma tentativa de cobranca
    - **{round(100*169/total_churners)}** tiveram pagamento aprovado mas nao renovaram (anomalia)

    > A falha de pagamento e, de longe, a **maior causa de churn**.
    > Para cada paciente que pede cancelamento, quase **3 saem por falha no cartao**.
    """)

    # Tabela detalhada
    st.markdown("---")
    st.markdown("#### Tabela detalhada")

    df_tab_diag = df_diag_plot[["label", "churn_sn", "contratos", "pct_total",
                                 "media_tentativas", "media_recusas"]].copy()
    df_tab_diag.columns = ["Diagnostico", "Churn?", "Contratos", "% Total",
                           "Media tentativas", "Media recusas"]
    df_tab_diag["Churn?"] = df_tab_diag["Churn?"].map({"S": "Sim", "N": "Nao"})
    st.dataframe(df_tab_diag, hide_index=True, use_container_width=True)

    st.markdown("""
    **Nota sobre media de tentativas:** contratos com falha de pagamento tem em media
    apenas **1.5 tentativas** — o sistema faz poucas retentativas antes de desistir.
    Isso pode ser uma oportunidade: mais retentativas = mais chance de sucesso.
    """)


# ═══════════════════════════════════════════════════════════════════
# TAB 3: ADYEN VS MUNDIPAGG
# ═══════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("### Adyen vs Mundipagg: quem processa o que?")

    st.markdown("""
    A dr.consulta usa dois adquirentes para processar pagamentos de cartao de credito.
    Cada contrato pode ter tentativas em um ou ambos.
    """)

    st.markdown("---")
    st.markdown("#### Proporcao de contratos por adquirente")

    total_adyen = int(df_am["contratos_adyen"].sum())
    total_mundi = int(df_am["contratos_mundi"].sum())
    total_sem_tent = int(df_am["sem_tentativa"].sum())

    p1, p2, p3 = st.columns(3)
    p1.metric("Mundipagg", f"{total_mundi:,}",
              delta=f"{round(100*total_mundi/total_contratos,1)}% dos contratos", delta_color="off")
    p2.metric("Adyen", f"{total_adyen:,}",
              delta=f"{round(100*total_adyen/total_contratos,1)}% dos contratos", delta_color="off")
    p3.metric("Sem tentativa", f"{total_sem_tent:,}",
              delta=f"{round(100*total_sem_tent/total_contratos,1)}%", delta_color="inverse")

    st.markdown(f"""
    **Mundipagg processa {round(total_mundi/total_adyen, 1)}x mais contratos que Adyen.**
    Isso significa que melhorias na Adyen tem impacto limitado enquanto a maioria
    do volume passa pela Mundipagg.
    """)

    # Evolucao semanal de proporcao
    st.markdown("---")
    st.markdown("#### Proporcao semanal: quem processa mais?")

    fig_prop = go.Figure()
    fig_prop.add_trace(go.Bar(
        x=df_am["semana_label"], y=df_am["contratos_mundi"],
        name="Mundipagg", marker_color="#3498db", opacity=0.7,
    ))
    fig_prop.add_trace(go.Bar(
        x=df_am["semana_label"], y=df_am["contratos_adyen"],
        name="Adyen", marker_color="#e67e22", opacity=0.7,
    ))
    fig_prop.add_trace(go.Bar(
        x=df_am["semana_label"], y=df_am["sem_tentativa"],
        name="Sem tentativa", marker_color="#bdc3c7", opacity=0.5,
    ))
    fig_prop.add_shape(type="line", x0=3.5, x1=3.5, y0=0,
                       y1=df_am["contratos"].max() * 1.05,
                       line=dict(dash="dash", color="red", width=2))
    fig_prop.add_annotation(x=3.5, y=df_am["contratos"].max() * 1.05,
                            text="Mudanca Adyen<br>15/05", showarrow=False,
                            font=dict(color="red", size=11))
    fig_prop.update_layout(
        barmode="stack",
        title="Contratos por adquirente por semana",
        xaxis_title="Semana", yaxis_title="Contratos",
        height=450,
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_prop, use_container_width=True)

    # Taxas de aprovacao
    st.markdown("---")
    st.markdown("#### Taxas de aprovacao: Adyen vs Mundipagg")

    fig_aprov = go.Figure()
    fig_aprov.add_trace(go.Scatter(
        x=df_am["semana_label"], y=df_am["taxa_aprov_adyen_pct"],
        name="Adyen", mode="lines+markers+text",
        marker=dict(size=10, color="#e67e22"),
        line=dict(width=3, color="#e67e22"),
        text=df_am["taxa_aprov_adyen_pct"].apply(lambda x: f"{x:.1f}%"),
        textposition="top center", textfont=dict(size=11, color="#e67e22"),
    ))
    fig_aprov.add_trace(go.Scatter(
        x=df_am["semana_label"], y=df_am["taxa_aprov_mundi_pct"],
        name="Mundipagg", mode="lines+markers+text",
        marker=dict(size=10, color="#3498db"),
        line=dict(width=3, color="#3498db"),
        text=df_am["taxa_aprov_mundi_pct"].apply(lambda x: f"{x:.1f}%"),
        textposition="bottom center", textfont=dict(size=11, color="#3498db"),
    ))
    fig_aprov.add_shape(type="line", x0=3.5, x1=3.5, y0=0, y1=75,
                        line=dict(dash="dash", color="red", width=2))
    fig_aprov.add_annotation(x=3.5, y=72, text="Mudanca Adyen 15/05",
                             showarrow=False, font=dict(color="red", size=11))
    fig_aprov.update_layout(
        title="Taxa de aprovacao por adquirente (% das tentativas aprovadas)",
        xaxis_title="Semana", yaxis=dict(title="Aprovacao (%)", range=[0, 75]),
        height=450,
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_aprov, use_container_width=True)

    # Medias PRE vs POS
    pre = df_am[df_am["periodo"] == "PRE"]
    pos = df_am[df_am["periodo"] == "POS"]
    media_adyen_pre = round(pre["taxa_aprov_adyen_pct"].mean(), 1)
    media_adyen_pos = round(pos["taxa_aprov_adyen_pct"].mean(), 1)
    media_mundi_pre = round(pre["taxa_aprov_mundi_pct"].mean(), 1)
    media_mundi_pos = round(pos["taxa_aprov_mundi_pct"].mean(), 1)

    ma1, ma2, ma3, ma4 = st.columns(4)
    ma1.metric("Adyen PRE", f"{media_adyen_pre}%")
    ma2.metric("Adyen POS", f"{media_adyen_pos}%",
               delta=f"{media_adyen_pos - media_adyen_pre:+.1f} p.p.", delta_color="normal")
    ma3.metric("Mundi PRE", f"{media_mundi_pre}%")
    ma4.metric("Mundi POS", f"{media_mundi_pos}%",
               delta=f"{media_mundi_pos - media_mundi_pre:+.1f} p.p.",
               delta_color="normal" if media_mundi_pos > media_mundi_pre else "inverse")

    st.markdown(f"""
    **Adyen** mostra melhora clara: aprovacao media subiu de **{media_adyen_pre}%**
    para **{media_adyen_pos}%** (+{media_adyen_pos - media_adyen_pre:.1f} p.p.), com
    aceleracao nas ultimas semanas (51.2% na sem +6).

    **Mundipagg** esta **estavel ou caindo levemente**: de {media_mundi_pre}% para
    {media_mundi_pos}%. Como processa {round(total_mundi/total_adyen, 1)}x mais volume,
    e o **gargalo principal** para reduzir o churn por falha de pagamento.
    """)

    # Tabela completa
    st.markdown("---")
    st.markdown("#### Tabela: todos os numeros por semana")

    df_tab_am = df_am[["semana_label", "periodo", "contratos", "contratos_adyen",
                        "contratos_mundi", "sem_tentativa",
                        "taxa_aprov_adyen_pct", "taxa_aprov_mundi_pct",
                        "churners", "taxa_churn"]].copy()
    df_tab_am.columns = ["Semana", "Periodo", "Total", "Adyen", "Mundi",
                          "Sem tent.", "Aprov Adyen %", "Aprov Mundi %",
                          "Churners", "Churn %"]
    st.dataframe(df_tab_am, hide_index=True, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
# TAB 4: IMPACTO MUDANCA 15/05
# ═══════════════════════════════════════════════════════════════════
with tab4:
    st.markdown("### A mudanca da Adyen em 15/05 reduziu o churn?")

    st.markdown("""
    Em 15 de maio de 2026, a Adyen fez uma modificacao em sistema para reduzir
    ocorrencias de falha em pagamentos recorrentes. Acompanhamos semana a semana.
    """)

    st.markdown("---")
    st.markdown("#### Evolucao semanal: aprovacao Adyen vs churn")

    # Grafico dual: aprovacao adyen + taxa churn
    fig_impacto = make_subplots(specs=[[{"secondary_y": True}]])

    fig_impacto.add_trace(go.Bar(
        x=df_sem["semana_label"], y=df_sem["taxa_aprov_adyen_pct"],
        name="Aprovacao Adyen (%)",
        marker_color=["#f39c12" if p == "PRE" else "#e67e22" for p in df_sem["periodo"]],
        opacity=0.6,
        text=df_sem["taxa_aprov_adyen_pct"].apply(lambda x: f"{x:.1f}%"),
        textposition="outside", textfont=dict(size=11),
    ), secondary_y=False)

    fig_impacto.add_trace(go.Scatter(
        x=df_sem["semana_label"], y=df_sem["taxa_churn_pct"],
        name="Churn total (%)", mode="lines+markers",
        marker=dict(size=10, color="#e74c3c"),
        line=dict(width=3, color="#e74c3c"),
    ), secondary_y=True)

    fig_impacto.add_trace(go.Scatter(
        x=df_sem["semana_label"], y=df_sem["taxa_churn_involuntario_pct"],
        name="Churn involuntario (%)", mode="lines+markers",
        marker=dict(size=10, color="#c0392b", symbol="diamond"),
        line=dict(width=2, color="#c0392b", dash="dot"),
    ), secondary_y=True)

    fig_impacto.add_vline(x=3.5, line_dash="dash", line_color="red", line_width=2)
    fig_impacto.add_annotation(x=3.5, y=55, text="Mudanca<br>Adyen 15/05",
                               showarrow=False, font=dict(color="red", size=11))

    fig_impacto.update_layout(
        title="Aprovacao Adyen vs Taxa de Churn — semana a semana",
        height=500,
        legend=dict(orientation="h", y=1.12),
    )
    fig_impacto.update_yaxes(title_text="Aprovacao Adyen (%)", range=[0, 60], secondary_y=False)
    fig_impacto.update_yaxes(title_text="Churn (%)", range=[30, 65], secondary_y=True)

    st.plotly_chart(fig_impacto, use_container_width=True)

    # KPIs PRE vs POS
    st.markdown("---")
    st.markdown("#### PRE vs POS: numeros agregados")

    pre_sem = df_sem[df_sem["periodo"] == "PRE"]
    pos_sem = df_sem[df_sem["periodo"] == "POS"]

    aprov_pre = round(pre_sem["taxa_aprov_adyen_pct"].mean(), 1)
    aprov_pos = round(pos_sem["taxa_aprov_adyen_pct"].mean(), 1)
    churn_pre = round((pre_sem["churners"].sum() / pre_sem["contratos"].sum()) * 100, 1)
    churn_pos = round((pos_sem["churners"].sum() / pos_sem["contratos"].sum()) * 100, 1)
    invol_pre = round((pre_sem["churn_involuntario"].sum() / pre_sem["contratos"].sum()) * 100, 1)
    invol_pos = round((pos_sem["churn_involuntario"].sum() / pos_sem["contratos"].sum()) * 100, 1)
    falha_pct_pre = round(pre_sem["pct_so_falha_adyen"].mean(), 1)
    falha_pct_pos = round(pos_sem["pct_so_falha_adyen"].mean(), 1)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Aprovacao Adyen", f"{aprov_pre}% → {aprov_pos}%",
              delta=f"{aprov_pos - aprov_pre:+.1f} p.p.", delta_color="normal")
    c2.metric("% so falha Adyen", f"{falha_pct_pre}% → {falha_pct_pos}%",
              delta=f"{falha_pct_pos - falha_pct_pre:+.1f} p.p.",
              delta_color="inverse" if falha_pct_pos > falha_pct_pre else "normal")
    c3.metric("Churn total", f"{churn_pre}% → {churn_pos}%",
              delta=f"{churn_pos - churn_pre:+.1f} p.p.",
              delta_color="normal" if churn_pos < churn_pre else "inverse")
    c4.metric("Churn involuntario", f"{invol_pre}% → {invol_pos}%",
              delta=f"{invol_pos - invol_pre:+.1f} p.p.",
              delta_color="normal" if invol_pos < invol_pre else "inverse")

    st.markdown(f"""
    ---
    #### Interpretacao

    A aprovacao da Adyen **melhorou significativamente** ({aprov_pre}% → {aprov_pos}%),
    com aceleracao nas ultimas semanas. Porem:

    - O **churn total e involuntario nao cairam** — se mantiveram estaveis ou
      subiram levemente
    - Isso acontece porque a **Adyen processa apenas ~30% dos contratos**
    - A **Mundipagg**, que processa ~60%, esta estavel ou caindo em aprovacao
    - O efeito da melhora Adyen e **diluido** pelo volume Mundipagg

    **Calculo do impacto potencial:**
    """)

    # Simulacao de impacto
    adyen_share = round(100 * total_adyen / total_contratos, 1)
    mundi_share = round(100 * total_mundi / total_contratos, 1)
    adyen_melhora_pct = aprov_pos - aprov_pre
    contratos_salvos_adyen = round(total_adyen * adyen_melhora_pct / 100)

    st.markdown(f"""
    | Calculo | Valor |
    |---|---|
    | Contratos com Adyen | {total_adyen:,} ({adyen_share}% do total) |
    | Melhora na aprovacao | +{adyen_melhora_pct:.1f} p.p. |
    | Contratos potencialmente salvos | ~{contratos_salvos_adyen:,} |
    | Impacto no churn total | ~{round(100*contratos_salvos_adyen/total_contratos,1)}% do total |

    > A melhora da Adyen pode salvar ~{contratos_salvos_adyen:,} contratos,
    > mas isso representa apenas ~{round(100*contratos_salvos_adyen/total_contratos,1)}%
    > do universo total. **A alavanca maior esta na Mundipagg.**
    """)

    # Tabela semanal detalhada
    st.markdown("---")
    st.markdown("#### Tabela semanal detalhada")

    df_tab_sem = df_sem[["semana_label", "periodo", "contratos", "com_tentativa_adyen",
                          "taxa_aprov_adyen_pct", "so_falha_adyen", "pct_so_falha_adyen",
                          "churners", "taxa_churn_pct",
                          "cancelamentos_ativos", "churn_involuntario",
                          "taxa_churn_involuntario_pct"]].copy()
    df_tab_sem.columns = ["Semana", "Periodo", "Contratos", "Com Adyen",
                           "Aprov %", "So falha", "% so falha",
                           "Churners", "Churn %", "Cancelamentos",
                           "Churn invol.", "Churn invol. %"]
    st.dataframe(df_tab_sem, hide_index=True, use_container_width=True)

    st.markdown("""
    **Colunas-chave:**
    - **Churn involuntario** = churners que NAO pediram cancelamento (provavel falha de pagamento)
    - **% so falha** = contratos onde Adyen NUNCA aprovou (todas tentativas recusadas)
    """)


# ═══════════════════════════════════════════════════════════════════
# TAB 5: MOTIVOS DE RECUSA
# ═══════════════════════════════════════════════════════════════════
with tab5:
    st.markdown("### Por que o cartao e recusado?")
    st.markdown("Top motivos de recusa da Adyen, comparando PRE vs POS mudanca 15/05.")

    st.markdown("---")

    # Grafico horizontal PRE vs POS
    df_mot_top = df_mot.nlargest(10, "total").copy()
    # Truncar nomes longos
    df_mot_top["motivo_short"] = df_mot_top["motivo"].apply(
        lambda x: x[:40] + "..." if len(str(x)) > 40 else x)

    fig_mot = go.Figure()
    fig_mot.add_trace(go.Bar(
        y=df_mot_top["motivo_short"], x=df_mot_top["pct_pre"],
        name="PRE (abr-14/mai)", orientation="h",
        marker_color="#f39c12", opacity=0.7,
        text=df_mot_top["pct_pre"].apply(lambda x: f"{x}%"),
        textposition="outside",
    ))
    fig_mot.add_trace(go.Bar(
        y=df_mot_top["motivo_short"], x=df_mot_top["pct_pos"],
        name="POS (15/mai-jun)", orientation="h",
        marker_color="#e67e22", opacity=0.9,
        text=df_mot_top["pct_pos"].apply(lambda x: f"{x}%"),
        textposition="outside",
    ))
    fig_mot.update_layout(
        barmode="group",
        title="Top 10 motivos de recusa Adyen — PRE vs POS 15/05",
        xaxis=dict(title="% das recusas", range=[0, 45]),
        yaxis=dict(autorange="reversed"),
        height=550,
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig_mot, use_container_width=True)

    # Destaque das mudancas
    st.markdown("---")
    st.markdown("#### O que mudou?")

    df_mot["delta"] = df_mot["pct_pos"] - df_mot["pct_pre"]
    melhorou = df_mot[df_mot["delta"] < -0.5].sort_values("delta")
    piorou = df_mot[df_mot["delta"] > 0.5].sort_values("delta", ascending=False)

    col_m, col_p = st.columns(2)

    with col_m:
        st.markdown("##### Melhorou (caiu % POS)")
        for _, row in melhorou.iterrows():
            st.markdown(f"- **{row['motivo'][:50]}** (code {row['motivo_code']}): "
                        f"{row['pct_pre']}% → {row['pct_pos']}% "
                        f"({row['delta']:+.1f} p.p.)")

    with col_p:
        st.markdown("##### Piorou (subiu % POS)")
        for _, row in piorou.iterrows():
            st.markdown(f"- **{row['motivo'][:50]}** (code {row['motivo_code']}): "
                        f"{row['pct_pre']}% → {row['pct_pos']}% "
                        f"({row['delta']:+.1f} p.p.)")

    # Explicacao dos motivos
    st.markdown("---")
    st.markdown("#### O que cada motivo significa")

    st.markdown("""
    | Motivo | Code | O que e | Acao possivel |
    |---|---|---|---|
    | **Refused** | 2 | Recusa generica do emissor | Retentativa com outro BIN/timing |
    | **Blocked by Adyen (retry fees)** | 46 | Adyen bloqueia retentativa pra evitar multa | Config Adyen (foi o que mudou em 15/05) |
    | **Not enough balance** | 12 | Saldo insuficiente no cartao | Notificar paciente pra atualizar cartao |
    | **Transaction Not Permitted** | 23 | Tipo de transacao nao permitido | Verificar configuracao do MCC |
    | **Issuer Suspected Fraud** | 31 | Banco suspeitou de fraude | Paciente precisa liberar no banco |
    | **Restricted Card** | 25 | Cartao com restricao | Paciente precisa atualizar cartao |
    | **Invalid Card Number** | 8 | Numero do cartao invalido | Paciente atualizou cartao e nao informou |
    | **Blocked Card** | 5 | Cartao bloqueado | Paciente precisa atualizar |
    | **Expired Card** | 6 | Cartao vencido | Atualizar dados de pagamento |

    > **"Not enough balance" (19%)** e **"Refused" (33%)** somam mais da metade das recusas.
    > Sao problemas do lado do **paciente**, nao do gateway. Uma estrategia de
    > **notificacao proativa** ("seu cartao vai ser cobrado em X dias") poderia reduzir esses casos.
    """)

    # Tabela completa
    st.markdown("---")
    st.markdown("#### Tabela completa")

    df_tab_mot = df_mot[["motivo", "motivo_code", "recusas_pre", "recusas_pos",
                          "total", "pct_pre", "pct_pos", "delta"]].copy()
    df_tab_mot.columns = ["Motivo", "Code", "Recusas PRE", "Recusas POS",
                           "Total", "% PRE", "% POS", "Delta p.p."]
    st.dataframe(df_tab_mot, hide_index=True, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
# TAB 6: CONCLUSOES
# ═══════════════════════════════════════════════════════════════════
with tab6:
    st.markdown("### O que aprendemos e o que fazer")

    st.markdown(f"""
    ---
    #### 1. O churn e majoritariamente involuntario

    | Causa | % do churn | % do total | Natureza |
    |---|---|---|---|
    | **Falha de pagamento** | **{pct_falha_do_churn}%** | {pct_falha_do_total}% | Involuntario — paciente nao pediu pra sair |
    | Cancelamento ativo | {round(100*cancelou/total_churners,1)}% | {round(100*cancelou/total_contratos,1)}% | Voluntario — paciente decidiu sair |
    | Sem tentativa | {round(100*835/total_churners,1)}% | {round(100*835/total_contratos,1)}% | Anomalia — nenhuma cobranca registrada |

    Para cada paciente que **decide** sair, quase **3 saem porque o cartao falhou**.
    O problema de churn da dr.consulta e, em grande parte, um **problema de cobranca**.

    ---
    #### 2. Mundipagg e o gargalo, nao a Adyen

    | Adquirente | Volume | Aprovacao PRE | Aprovacao POS | Tendencia |
    |---|---|---|---|---|
    | **Mundipagg** | ~60% dos contratos | {media_mundi_pre}% | {media_mundi_pos}% | Estavel/caindo |
    | **Adyen** | ~30% dos contratos | {media_adyen_pre}% | {media_adyen_pos}% | Melhorando rapido |

    A Adyen melhorou de {media_adyen_pre}% para {media_adyen_pos}% (com pico de 51.2%
    na ultima semana), mas processa apenas 30% do volume. A Mundipagg, com 60%,
    esta estagnada. **O maior ROI esta em melhorar a Mundipagg.**

    ---
    #### 3. A mudanca Adyen 15/05 funciona, mas o impacto e limitado

    - Aprovacao Adyen subiu consistentemente semana a semana
    - O bloqueio "excessive retry fees" caiu de 20.8% para 17.3%
    - Mas o **churn total nao caiu** porque Adyen e so 30% do volume
    - Impacto estimado: ~{contratos_salvos_adyen:,} contratos salvos
      ({round(100*contratos_salvos_adyen/total_contratos,1)}% do total)

    ---
    #### 4. Acoes recomendadas
    """)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("""
        **Curto prazo (0-30 dias)**

        - Notificar pacientes com "Not enough
          balance" e "Expired Card" **antes**
          da retentativa — SMS/WhatsApp pedindo
          pra atualizar o cartao
        - Aumentar numero de retentativas
          (media atual: 1.5 — muito baixo)
        - Investigar os 835 contratos "sem
          tentativa" — bug de integracao?
        """)

    with col2:
        st.markdown("""
        **Medio prazo (30-90 dias)**

        - Negociar com Mundipagg melhora
          na taxa de aprovacao (prioridade #1)
        - Avaliar roteamento inteligente:
          se Mundi recusa, tentar Adyen
          (e vice-versa)
        - Criar score de risco de falha de
          pagamento com features do Adyen
          (cardFunction, BIN, retry history)
        """)

    with col3:
        st.markdown("""
        **Longo prazo (90+ dias)**

        - Modelo preditivo de falha de
          pagamento (features exploradas
          na query `explorar_pagamento_features`)
        - Estrategia de dunning automatizada:
          escalar canais (email → SMS → call)
          conforme tentativas falham
        - Avaliar se o plano gratis automatico
          deveria ser substituido por uma
          "pausa" com reativacao simplificada
        """)

    st.markdown(f"""
    ---
    > **O maior insight desta analise:** o churn da dr.consulta nao e
    > primariamente um problema de **retencao** (paciente insatisfeito),
    > e um problema de **cobranca** (cartao que nao passa).
    > Dos {total_churners:,} churners nesta janela, **{falha_pgto:,}
    > ({pct_falha_do_churn}%) nao pediram pra sair** — o pagamento simplesmente falhou.
    > Resolver isso e a maior alavanca para reduzir churn.
    """)
