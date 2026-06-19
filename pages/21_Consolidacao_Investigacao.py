"""
Pagina 21 — Consolidacao: Toda a Investigacao
===============================================
Storytelling completo: o que achamos antes, o que descobrimos,
como funciona o campo days_diff, a migracao gratis de 17 dias,
e por que o score v4 continua valido.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="Consolidacao da Investigacao", page_icon="📋", layout="wide")
st.title("📋 Consolidacao: Toda a Investigacao de Churn")
st.caption("De 'churn = 55%' ate '3 destinos' — o caminho completo, com as evidencias")


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

@st.cache_data
def load_auditoria():
    return pd.read_csv("results/auditoria_days_diff_check.csv")

@st.cache_data
def load_dist():
    return pd.read_csv("results/auditoria_days_diff_dist.csv")

@st.cache_data
def load_v5_faixas():
    return pd.read_csv("results/score_v5_faixas.csv")

@st.cache_data
def load_v4_faixas():
    return pd.read_csv("results/score_v4_faixas.csv")


try:
    df_perfil = load_perfil()
    df_depois = load_depois()
    df_timing = load_timing()
    df_mensal = load_mensal()
    df_audit = load_auditoria()
    df_dist = load_dist()
    df_v5 = load_v5_faixas()
    df_v4 = load_v4_faixas()
except FileNotFoundError as e:
    st.error(f"CSV nao encontrado: {e}")
    st.stop()

df_mensal["mes_vencimento"] = pd.to_datetime(df_mensal["mes_vencimento"])


# ═══════════════════════════════════════════════════════════════════
# INTRO
# ═══════════════════════════════════════════════════════════════════

st.markdown("""
---
### O resumo em 30 segundos

Comecamos com a pergunta simples: *"qual e a taxa de churn?"*.
A resposta parecia ser **~55%** — mais da metade dos contratos nao renovava.

Investigando, descobrimos que **30% dos 'churners' voltavam em ate 30 dias**.
Achamos que eram **retentativas automaticas de pagamento**. O churn real
cairia pra **~24%**. O score de risco (XGBoost) melhorou de AUC 0.59 pra 0.65.

Mas ao auditar o campo `days_diff_until_next_contract`, descobrimos que
**nao sao retentativas de pagamento**. Sao **migracoes automaticas pro plano gratis**
que acontecem exatamente entre **15-21 dias** apos o vencimento.

E dos que migram pro gratis, **82% saem de vez**. Apenas 18% voltam pro pago.

O churn tem **3 destinos**, nao 2. E o score v4 continua sendo a melhor
ferramenta operacional — porque o que ele preve (perfil de risco) e acionavel,
enquanto a migracao pro gratis e um problema de cobranca, nao de retencao.
""")


# ═══════════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════════

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📖 Antes vs Agora",
    "🔢 Universo dos Dados",
    "🔍 O Campo days_diff",
    "🔄 Migracao Gratis (17 dias)",
    "📊 Score v4 vs v5",
    "💡 Conclusoes",
])


# ═══════════════════════════════════════════════════════════════════
# TAB 1: ANTES VS AGORA
# ═══════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("### A evolucao do entendimento")

    st.markdown("""
    A investigacao de churn passou por **3 fases**. Cada uma corrigiu
    premissas da anterior e revelou uma camada mais profunda do problema.
    """)

    # Timeline visual
    st.markdown("---")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("#### Fase 1: Churn Aparente")
        st.markdown("*'55% dos contratos nao renovam'*")
        st.markdown("""
        **O que sabiamos:**
        - Contratos credit card, 6/12 meses, sem B2B
        - Churn definido como: contrato venceu e account_due_date
          nao se estendeu (gap <= 7 dias)
        - Taxa: ~54-55%

        **Score WLS:** AUC 0.579, spread ~25 p.p.

        **Problema:** o churn parecia alto demais
        e o modelo nao conseguia separar bem os grupos.
        """)

    with col2:
        st.markdown("#### Fase 2: Churn Real 30d")
        st.markdown("*'30% voltam em 30 dias — sao retentativas'*")
        st.markdown("""
        **O que descobrimos:**
        - `days_diff_until_next_contract` mostrava que ~30% dos churners
          tinham um novo contrato em ate 30 dias
        - Concentracao massiva entre 15-21 dias
        - Hipotese: retentativa automatica de pagamento

        **Score v4 (XGBoost):** AUC 0.654, spread ~89 p.p.

        **Problema:** ao auditar o campo, descobrimos
        que a hipotese estava errada.
        """)

    with col3:
        st.markdown("#### Fase 3: Os 3 Destinos")
        st.markdown("*'Nao sao retentativas — sao migracoes pro gratis'*")
        st.markdown("""
        **O que descobrimos:**
        - Os 30% nao voltam pro mesmo contrato — migram pro plano
          `cartao dr.consulta - gratis`
        - 82% dos que migram pro gratis saem de vez depois
        - Apenas 18% voltam pro pago

        **Score v5:** AUC 0.600 (pior que v4)

        **Conclusao:** v4 continua melhor operacionalmente.
        A migracao gratis e problema de cobranca, nao de perfil.
        """)

    # Comparacao direta
    st.markdown("---")
    st.markdown("### O que mudou: antes vs agora")

    st.markdown("""
    | Aspecto | O que achavamos (Fase 2) | O que sabemos agora (Fase 3) |
    |---|---|---|
    | **O que sao os 30%** | Retentativas automaticas de pagamento | Migracoes automaticas pro plano gratis |
    | **O contrato** | Mesmo contrato reativado | Contrato novo (plano gratis, person_id diferente de account) |
    | **O campo days_diff** | Aponta pro mesmo contrato | Aponta pro proximo contrato da mesma **pessoa** (holder_person_id) |
    | **Quem decide** | Sistema de pagamento (automatico) | Pipeline de migracao (automatico, apos falha de cobranca) |
    | **O que acontece depois** | Contrato continua normalmente | 82% saem de vez, 18% voltam pro pago |
    | **Churn real** | ~24% (excluindo todos os 30d) | 44% saiu de vez + 24% gratis→saiu = **~69% dos churners nao voltam** |
    | **Score recomendado** | v4 (AUC 0.654) | v4 continua valido (preve churn por perfil) |
    """)

    # Grafico: evolucao do AUC
    fig_auc = go.Figure()
    versoes = ["WLS\n(7 vars)", "Score v3\n(+experiencia)", "Score v4\n(target 30d)", "Score v5\n(target gratis)"]
    aucs = [0.579, 0.590, 0.654, 0.600]
    cores = ["#95a5a6", "#95a5a6", "#27ae60", "#f39c12"]

    fig_auc.add_trace(go.Bar(
        x=versoes, y=aucs,
        marker_color=cores,
        text=[f"{a:.3f}" for a in aucs],
        textposition="outside",
        textfont=dict(size=14),
    ))
    fig_auc.add_shape(type="line", x0=-0.5, x1=3.5, y0=0.654, y1=0.654,
                      line=dict(dash="dot", color="green", width=1))
    fig_auc.update_layout(
        title="Evolucao do AUC por versao do score",
        yaxis=dict(title="AUC", range=[0.5, 0.72]),
        height=400,
    )
    st.plotly_chart(fig_auc, use_container_width=True)

    st.markdown("""
    > **Por que o v5 piora?** Porque a migracao pro gratis e determinada pelo
    > **gateway de pagamento** (o cartao passou ou nao), nao pelo perfil do paciente.
    > As features do modelo (idade, dependentes, NPS, etc.) nao conseguem prever
    > falha de pagamento. Ao incluir esses casos como churn, adicionamos ruido.
    """)


# ═══════════════════════════════════════════════════════════════════
# TAB 2: UNIVERSO DOS DADOS
# ═══════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("### De onde vem cada numero")

    st.markdown("""
    Todos os numeros desta analise vem de uma unica fonte:
    **`airflow-datalake-prod.YALO_DW.ref_yalo_subscriptions`** —
    a tabela de assinaturas do sistema Yalo (dr.consulta).
    """)

    st.markdown("---")
    st.markdown("#### Filtros aplicados (universo base)")

    st.markdown("""
    ```sql
    WHERE account_type = 'holder'              -- apenas titulares
      AND payment_method = 'credit_card'       -- apenas cartao de credito
      AND plan_months_duration IN (6, 12)      -- planos semestrais e anuais
      AND plan_name NOT LIKE '%gratis%'        -- exclui planos gratuitos
      AND IFNULL(order_source_aj, '') != 'b2b' -- exclui vendas corporativas
      AND contract_due_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 18 MONTH)
      AND contract_due_date < DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
    ```

    E para cada contract_id, pegamos apenas o snapshot mais recente:
    ```sql
    QUALIFY ROW_NUMBER() OVER (
      PARTITION BY contract_id
      ORDER BY date_month DESC
    ) = 1
    ```
    """)

    st.markdown("---")
    st.markdown("#### Definicao de churn")

    st.markdown("""
    ```sql
    CASE
      WHEN DATE_DIFF(account_due_date, contract_due_date, DAY) > 7 THEN 'N'  -- renovou
      ELSE 'S'  -- churnou
    END AS churn_sn
    ```

    Se a `account_due_date` (data de validade da conta) se estendeu mais de 7 dias
    alem do `contract_due_date` (vencimento do contrato), o paciente renovou.
    Caso contrario, churnou.
    """)

    st.markdown("---")
    st.markdown("#### Volumes por analise")

    # Tabela de volumes
    total_base_mensal = int(df_mensal["total_contratos"].sum())
    total_churners_mensal = int(df_mensal["churners"].sum())
    total_perfil = int(df_perfil["contratos"].sum())
    total_depois = int(df_depois["contratos"].sum())

    st.markdown(f"""
    | Analise | Contratos | Janela | Fonte |
    |---|---|---|---|
    | **Base mensal** (winback_30d_mensal) | {total_base_mensal:,} | 30 meses | ref_yalo_subscriptions |
    | **Churners mensais** | {total_churners_mensal:,} | 30 meses | Filtro: churn_sn = 'S' |
    | **Score v4/v5** | 133,944 | 18 meses | + features_experiencia + winback |
    | **Perfil 3 destinos** (migracao_gratis_perfil) | {total_perfil:,} | 18 meses | Churners + proximo contrato |
    | **Jornada pos-gratis** (migracao_gratis_depois) | {total_depois:,} | 18 meses | Churners + gratis + pos-gratis |
    | **Auditoria days_diff** | 195,160 | 12 meses | Recriacao manual do campo |

    **Por que os volumes sao diferentes?**
    - A **base mensal** usa 30 meses de historia (desde dez/2023)
    - O **score** usa 18 meses e faz inner join com features de experiencia (fat_atendimento)
    - A **auditoria** usa 12 meses pra focar em dados mais recentes
    - O **perfil 3 destinos** rastreia o proximo contrato em 12 meses apos o churn
    """)

    st.markdown("---")
    st.markdown("#### Evolucao mensal: a base e estavel")

    fig_base = go.Figure()
    fig_base.add_trace(go.Bar(
        x=df_mensal["mes_vencimento"],
        y=df_mensal["total_contratos"],
        name="Total contratos",
        marker_color="#3498db", opacity=0.4,
    ))
    fig_base.add_trace(go.Bar(
        x=df_mensal["mes_vencimento"],
        y=df_mensal["churners"],
        name="Churners",
        marker_color="#c0392b", opacity=0.6,
    ))
    fig_base.update_layout(
        title="Volume mensal de contratos e churners",
        barmode="overlay",
        yaxis_title="Contratos",
        height=380,
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_base, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
# TAB 3: O CAMPO DAYS_DIFF
# ═══════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("### A auditoria do campo `days_diff_until_next_contract`")

    st.markdown("""
    Este campo e central pra toda a analise de retorno/winback.
    Ao audita-lo, descobrimos que ele **nao funciona como esperavamos**.
    """)

    st.markdown("---")
    st.markdown("#### O que achavamos")

    st.markdown("""
    Achavamos que `days_diff_until_next_contract` era calculado como:

    ```
    proximo contrato do mesmo ACCOUNT → register_date - este contrato → due_date
    ```

    Ou seja, o gap entre o vencimento de um contrato e o inicio do proximo
    **da mesma conta (account_id)**.
    """)

    st.markdown("#### O que descobrimos")

    st.markdown("""
    O campo e calculado pelo pipeline de dados com esta logica:

    ```sql
    LEAD(contract_register_date) OVER (
      PARTITION BY holder_person_id
      ORDER BY contract_register_date
    ) - contract_due_date
    ```

    A diferenca crucial: o particionamento e por **`holder_person_id`**, nao por
    `account_id`. Isso significa que o campo aponta pro proximo contrato
    **da mesma pessoa**, que pode ser:
    - Outro contrato pago (na mesma ou outra conta)
    - Um contrato **gratis** (plano `cartao dr.consulta - gratis`)
    - Qualquer contrato onde a pessoa seja titular
    """)

    # Resultado da auditoria
    st.markdown("---")
    st.markdown("#### Resultado da auditoria: campo original vs recalculado")

    st.markdown("""
    Recriamos o campo do zero usando `LEAD() OVER (PARTITION BY account_id)`
    e comparamos com o valor original:
    """)

    st.dataframe(
        df_audit.rename(columns={
            "comparacao": "Comparacao",
            "contratos": "Contratos",
            "pct": "% do Total",
            "media_original": "Media Original",
            "media_calculado": "Media Calculado",
        }),
        hide_index=True, use_container_width=True,
    )

    # Destaque
    pct_batem = df_audit[df_audit["comparacao"].str.contains("batem", na=False)]["pct"].sum()
    pct_diferente = df_audit[df_audit["comparacao"].str.contains("muito_diferente", na=False)]["pct"].sum()

    k1, k2, k3 = st.columns(3)
    k1.metric("Batem (diff <= 3d)", f"{pct_batem:.1f}%",
              help="Campo original e recalculado concordam")
    k2.metric("Muito diferentes (>30d)", f"{pct_diferente:.1f}%",
              delta="maioria", delta_color="inverse")
    k3.metric("Motivo", "Particionamento diferente",
              help="Original usa holder_person_id, auditoria usou account_id")

    st.markdown(f"""
    **Apenas {pct_batem:.1f}% dos valores batem.** Os {pct_diferente:.1f}% de divergencia
    acontecem porque:
    - O campo original agrupa por **pessoa** (holder_person_id)
    - Nossa auditoria agrupou por **conta** (account_id)
    - Uma pessoa pode ter multiplas contas ao longo do tempo

    Isso explica por que o campo aponta pra contratos gratis: quando o pagamento falha,
    a pessoa ganha um contrato gratis em uma **nova conta**, e o campo captura esse
    vinculo pela person_id.
    """)

    st.markdown("---")
    st.markdown("#### Distribuicao do campo (churners)")

    df_dist_churn = df_dist[df_dist["churn_sn"] == "S"].copy()

    fig_dist = go.Figure()
    # Ordenar as faixas logicamente
    ordem = ["negativo_ou_zero", "1-7 dias", "8-14 dias", "15-21 dias",
             "22-30 dias", "31-60 dias", "61-90 dias", "91-180 dias", "181-365 dias", "NULL"]
    df_dist_ord = df_dist_churn.set_index("faixa_days_diff").reindex(ordem).reset_index().dropna(subset=["contratos"])

    cores_dist = ["#95a5a6"] * len(df_dist_ord)
    for i, row in df_dist_ord.iterrows():
        if row["faixa_days_diff"] == "15-21 dias":
            cores_dist[i] = "#f39c12"
        elif row["faixa_days_diff"] == "NULL":
            cores_dist[i] = "#c0392b"

    fig_dist.add_trace(go.Bar(
        x=df_dist_ord["faixa_days_diff"],
        y=df_dist_ord["contratos"],
        marker_color=cores_dist,
        text=[f"{int(c):,}" for c in df_dist_ord["contratos"]],
        textposition="outside",
    ))
    fig_dist.update_layout(
        title="Distribuicao de days_diff_until_next_contract (churners)",
        xaxis_title="Faixa", yaxis_title="Contratos",
        height=420,
    )
    st.plotly_chart(fig_dist, use_container_width=True)

    row_15_21 = df_dist_churn[df_dist_churn["faixa_days_diff"] == "15-21 dias"]
    row_null = df_dist_churn[df_dist_churn["faixa_days_diff"] == "NULL"]

    if len(row_15_21) > 0 and len(row_null) > 0:
        total_churn_dist = int(df_dist_churn["contratos"].sum())
        n_15_21 = int(row_15_21.iloc[0]["contratos"])
        n_null = int(row_null.iloc[0]["contratos"])
        st.markdown(f"""
        Dois picos dominam:
        - **15-21 dias:** {n_15_21:,} contratos ({round(100*n_15_21/total_churn_dist,1)}%) — sao as **migracoes pro gratis**
        - **NULL:** {n_null:,} contratos ({round(100*n_null/total_churn_dist,1)}%) — nao tiveram proximo contrato (saiu de vez)
        """)


# ═══════════════════════════════════════════════════════════════════
# TAB 4: MIGRACAO GRATIS
# ═══════════════════════════════════════════════════════════════════
with tab4:
    st.markdown("### A migracao automatica pro plano gratis")

    st.markdown("""
    A descoberta central desta investigacao: quando o pagamento do cartao falha
    no vencimento, o sistema **migra automaticamente o paciente pro plano gratis**
    apos ~17 dias de tentativas de cobranca.
    """)

    # Os 3 destinos
    st.markdown("---")
    st.markdown("#### Os 3 destinos de quem nao renova")

    total = int(df_perfil["contratos"].sum())
    row_saiu = df_perfil[df_perfil["desfecho"] == "saiu_de_vez"].iloc[0]
    row_gratis = df_perfil[df_perfil["desfecho"] == "migrou_gratis"].iloc[0]
    row_pago = df_perfil[df_perfil["desfecho"] == "voltou_pago"].iloc[0]

    k1, k2, k3, k4 = st.columns(4)
    k4.metric("Total churners", f"{total:,}")
    k1.metric("Saiu de vez", f"{int(row_saiu['contratos']):,}",
              delta=f"{row_saiu['pct']}%", delta_color="inverse")
    k2.metric("Migrou pro gratis", f"{int(row_gratis['contratos']):,}",
              delta=f"{row_gratis['pct']}%", delta_color="off")
    k3.metric("Voltou pro pago", f"{int(row_pago['contratos']):,}",
              delta=f"{row_pago['pct']}%", delta_color="normal")

    # Donut
    fig_dest = go.Figure(data=[go.Pie(
        labels=["Saiu de vez", "Migrou pro gratis", "Voltou pro pago"],
        values=[int(row_saiu["contratos"]), int(row_gratis["contratos"]), int(row_pago["contratos"])],
        hole=0.5,
        marker_colors=["#c0392b", "#f39c12", "#27ae60"],
        textinfo="label+percent",
        textfont=dict(size=13),
    )])
    fig_dest.update_layout(
        title=f"Destino dos {total:,} churners",
        height=400, showlegend=False,
        annotations=[dict(text=f"{total:,}<br>churners", x=0.5, y=0.5, font_size=14, showarrow=False)],
    )
    st.plotly_chart(fig_dest, use_container_width=True)

    # Timing: a flag de 17 dias
    st.markdown("---")
    st.markdown("#### O timing: por que exatamente 15-21 dias?")

    df_gratis_t = df_timing[df_timing["status"] == "migrou_gratis"].copy()

    fig_timing = go.Figure()
    cores_t = []
    for _, r in df_gratis_t.iterrows():
        if r["faixa_dias"] == "15-21 dias":
            cores_t.append("#f39c12")
        else:
            cores_t.append("#bdc3c7")

    fig_timing.add_trace(go.Bar(
        x=df_gratis_t["faixa_dias"],
        y=df_gratis_t["contratos"],
        marker_color=cores_t,
        text=[f"{int(c):,}" for c in df_gratis_t["contratos"]],
        textposition="outside",
    ))
    fig_timing.update_layout(
        title="Quando a migracao pro gratis acontece",
        xaxis_title="Dias apos vencimento",
        yaxis_title="Contratos",
        height=380,
    )
    st.plotly_chart(fig_timing, use_container_width=True)

    row_15 = df_gratis_t[df_gratis_t["faixa_dias"] == "15-21 dias"]
    if len(row_15) > 0:
        st.markdown(f"""
        **{row_15.iloc[0]['pct']}% das migracoes** acontecem entre 15-21 dias, com
        media de **{row_15.iloc[0]['media_days_diff']:.0f} dias**. As outras faixas
        sao residuais (menos de 30 contratos somadas).

        Esse timing nao e coincidencia — reflete o **ciclo de retentativa do gateway
        de pagamento**:

        1. **Dia 0:** contrato vence, cobranca falha no cartao
        2. **Dias 1-14:** sistema retenta cobranca periodicamente
        3. **Dia ~17:** apos esgotar retentativas, pipeline migra automaticamente
           pro plano `cartao dr.consulta - gratis`
        4. **Dias 17-61:** paciente fica no gratis (media 61 dias)
        5. **Depois:** 82% saem, 18% voltam pro pago
        """)

    # O que acontece depois do gratis
    st.markdown("---")
    st.markdown("#### Depois do gratis: funil de retorno")

    row_g_saiu = df_depois[df_depois["jornada_status"] == "gratis_depois_saiu"].iloc[0]
    row_g_pago = df_depois[df_depois["jornada_status"] == "gratis_depois_pago"].iloc[0]
    total_gratis = int(row_g_saiu["contratos"]) + int(row_g_pago["contratos"])
    pct_saiu_g = round(100 * int(row_g_saiu["contratos"]) / total_gratis, 1)
    pct_voltou_g = round(100 * int(row_g_pago["contratos"]) / total_gratis, 1)

    fig_funnel = go.Figure(go.Funnel(
        y=["Todos os churners", "Migraram pro gratis", "Gratis → saiu de vez", "Gratis → voltou pago"],
        x=[total, int(row_gratis["contratos"]), int(row_g_saiu["contratos"]), int(row_g_pago["contratos"])],
        textinfo="value+percent initial",
        marker_color=["#95a5a6", "#f39c12", "#c0392b", "#27ae60"],
    ))
    fig_funnel.update_layout(title="Funil: do churn ao retorno via gratis", height=400)
    st.plotly_chart(fig_funnel, use_container_width=True)

    st.markdown(f"""
    De cada **100 churners**:
    - **30** migram pro gratis (automaticamente)
    - Desses 30, **{round(30 * pct_saiu_g / 100)}** saem de vez depois ({pct_saiu_g}%)
    - Apenas **{round(30 * pct_voltou_g / 100)}** voltam pro pago ({pct_voltou_g}%)
    - Tempo medio no gratis: **{int(row_g_saiu['media_dias_no_gratis'])} dias**

    > O plano gratis funciona como **sala de espera pro churn**, nao como
    > ferramenta de retencao.
    """)

    # Perfil comparativo
    st.markdown("---")
    st.markdown("#### Perfil dos 3 grupos")

    df_tab = df_perfil[["desfecho", "contratos", "pct", "pct_1o_contrato",
                         "pct_12m", "pct_pediu_cancelamento", "pct_digital"]].copy()
    df_tab.columns = ["Destino", "Contratos", "%", "% 1o contrato",
                       "% plano 12m", "% pediu cancelamento", "% digital"]
    df_tab["Destino"] = df_tab["Destino"].map({
        "saiu_de_vez": "Saiu de vez",
        "migrou_gratis": "Migrou pro gratis",
        "voltou_pago": "Voltou pro pago",
    })
    st.dataframe(df_tab, use_container_width=True, hide_index=True)

    st.markdown(f"""
    **Insight-chave:** quem migra pro gratis tem a **menor taxa de cancelamento ativo**
    ({row_gratis['pct_pediu_cancelamento']}% vs {row_saiu['pct_pediu_cancelamento']}%
    de quem saiu). Ou seja, nao pediram pra sair — o pagamento simplesmente falhou.
    """)


# ═══════════════════════════════════════════════════════════════════
# TAB 5: SCORE V4 VS V5
# ═══════════════════════════════════════════════════════════════════
with tab5:
    st.markdown("### Score v4 vs v5: qual target e melhor?")

    st.markdown("""
    Testamos 4 definicoes de target pra avaliar qual produz o melhor score:
    """)

    # Tabela de targets
    st.markdown("""
    | Target | Definicao | Taxa de churn | AUC (5-fold CV) |
    |---|---|---|---|
    | A: Original | nao renovou = churn | 54.3% | 0.5895 |
    | B: Real 30d **(v4)** | exclui todos que voltam em 30d | 24.1% | **0.6544** |
    | D: V5 | exclui so quem voltou **pago** em 30d | 48.9% | 0.6001 |
    | C: Real 90d | exclui todos que voltam em 90d | 22.5% | 0.6623 |
    """)

    st.markdown("""
    **Por que o v5 e pior que o v4?**

    O v5 mantem quem migrou pro gratis como churn (conceitualmente correto,
    ja que 82% saem). Mas o modelo usa features de **perfil** (idade, dependentes,
    NPS, canal...) e a migracao pro gratis depende de **se o cartao passou ou nao** —
    algo que o perfil nao consegue prever.

    Adicionar esses ~33K casos de volta como churn injeta ruido que as features
    nao explicam, e o AUC cai.
    """)

    # Comparacao de faixas
    st.markdown("---")
    layout_sel = st.radio(
        "Layout de faixas:", ["5 faixas", "7 faixas"],
        horizontal=True, key="v4v5_layout"
    )
    layout_key = layout_sel.replace(" ", "_")

    df_v4_f = df_v4[df_v4["layout"] == layout_key].copy()
    df_v5_f = df_v5[df_v5["layout"] == layout_key].copy()

    CORES = {"CRITICO": "#8b0000", "MUITO ALTO": "#d62728", "ALTO": "#ff7f0e",
             "MEDIO": "#ffbb33", "BAIXO": "#2ca02c", "MUITO BAIXO": "#1f77b4", "SEGURO": "#0d3b8b"}

    # Preparar churn rates do v4
    if "churn_rate" in df_v4_f.columns:
        df_v4_f = df_v4_f.rename(columns={"churn_rate": "churn_rate_v4", "contratos": "contratos_v4"})
    elif "churners" in df_v4_f.columns:
        df_v4_f["churn_rate_v4"] = round(100 * df_v4_f["churners"] / df_v4_f["contratos"], 1)
        df_v4_f = df_v4_f.rename(columns={"contratos": "contratos_v4"})

    # Funcao: grafico barras + linha (mesmo estilo da pag 18)
    def grafico_faixas_dual(df_faixa, col_contratos, col_churn, cores, titulo):
        fig = go.Figure()

        fig.add_trace(go.Bar(
            x=df_faixa["faixa"],
            y=df_faixa[col_contratos],
            name="Contratos",
            marker_color=[cores.get(f, "gray") for f in df_faixa["faixa"]],
            opacity=0.4,
            text=df_faixa.apply(
                lambda r: f'{int(r[col_contratos]):,}\n({round(100*r[col_contratos]/df_faixa[col_contratos].sum(),1)}%)',
                axis=1),
            textposition="outside", textfont=dict(size=11),
        ))

        fig.add_trace(go.Scatter(
            x=df_faixa["faixa"],
            y=df_faixa[col_churn],
            name="Churn (%)",
            mode="lines+markers+text",
            marker=dict(size=14,
                        color=[cores.get(f, "gray") for f in df_faixa["faixa"]],
                        line=dict(width=2, color="white")),
            line=dict(width=3, color="gray", dash="dot"),
            yaxis="y2",
            text=df_faixa[col_churn].apply(lambda x: f"{x}%"),
            textposition="top center",
            textfont=dict(size=14, color="crimson"),
        ))

        churn_vals = df_faixa.loc[df_faixa[col_contratos] >= 10, col_churn]
        spread = round(churn_vals.max() - churn_vals.min(), 1) if len(churn_vals) >= 2 else 0

        fig.update_layout(
            title=f"{titulo} — Spread: {spread} p.p.",
            yaxis=dict(title="Contratos"),
            yaxis2=dict(title="Churn (%)", overlaying="y", side="right", range=[0, 110]),
            legend=dict(orientation="h", y=1.12),
            height=500,
        )
        return fig, spread

    # Grafico V4
    st.markdown(f"#### Score v4 — {layout_sel}")
    fig_v4, spread_v4 = grafico_faixas_dual(
        df_v4_f, "contratos_v4", "churn_rate_v4", CORES,
        f"Score v4 · {layout_sel} (target: exclui todos 30d)"
    )
    st.plotly_chart(fig_v4, use_container_width=True)

    # Grafico V5
    st.markdown(f"#### Score v5 — {layout_sel}")
    fig_v5, spread_v5 = grafico_faixas_dual(
        df_v5_f, "contratos", "churn_rate_v5", CORES,
        f"Score v5 · {layout_sel} (target: so exclui pago)"
    )
    st.plotly_chart(fig_v5, use_container_width=True)

    # KPIs de spread
    col1, col2, col3 = st.columns(3)
    col1.metric("Spread v4", f"{spread_v4} p.p.")
    col2.metric("Spread v5", f"{spread_v5} p.p.")
    col3.metric("AUC v4 vs v5", "0.654 vs 0.600",
                delta="-0.054 (v5 piora)", delta_color="inverse")

    # Tabela detalhada
    st.markdown("---")
    st.markdown("#### Tabela detalhada: churn rate por faixa e versao")

    df_detail = df_v5_f[["faixa", "contratos", "churn_rate_v5", "churn_rate_v4", "churn_rate_original"]].copy()
    df_detail.columns = ["Faixa", "Contratos (v5)", "Churn v5 (%)", "Churn v4 (%)", "Churn Original (%)"]
    st.dataframe(df_detail, hide_index=True, use_container_width=True)

    st.markdown("""
    **Observacoes:**
    - O v5 tem churn rates **muito mais altos** em todas as faixas (porque o target inclui
      os gratis como churn)
    - A distribuicao do v5 e **mais concentrada** no MEDIO (66% da base em 5 faixas)
    - O v4 distribui melhor e separa mais (spread maior em 5 faixas)
    - Em 7 faixas, o v5 tem spread maior mas com faixas extremas vazias (SEGURO = 115 contratos)
    """)

    st.markdown("""
    ---
    #### Veredicto

    | Criterio | v4 | v5 |
    |---|---|---|
    | AUC | **0.654** | 0.600 |
    | Spread (5 faixas) | **75.3 p.p.** | 68.4 p.p. |
    | Distribuicao equilibrada | **Sim** | Nao (concentra no MEDIO) |
    | Target conceitualmente correto | Parcial | **Sim** |
    | Acionavel pelo Growth | **Sim** | Parcial |

    **Recomendacao: manter o score v4** para priorizacao operacional.
    A migracao gratis deve ser tratada como workstream separada
    (problema de cobranca/pagamento, nao de retencao).
    """)


# ═══════════════════════════════════════════════════════════════════
# TAB 6: CONCLUSOES
# ═══════════════════════════════════════════════════════════════════
with tab6:
    st.markdown("### O que aprendemos e o que fazer")

    st.markdown("""
    ---
    #### 1. O churn nao e um numero — sao 3 problemas

    | Destino | % dos churners | Natureza | Responsavel |
    |---|---|---|---|
    | **Saiu de vez** | 44.3% | Decisao ativa (64.6% pediu cancelamento) | Growth / Retencao |
    | **Migrou pro gratis** | 30.0% | Falha de pagamento → migracao automatica | Financeiro / Pagamentos |
    | **Voltou pro pago** | 25.7% | Churn temporario, retorno em ~56 dias | Growth (acelerar) |

    ---
    #### 2. O campo `days_diff_until_next_contract`

    - **Como funciona:** LEAD() particionado por `holder_person_id` (pessoa), nao por account_id
    - **Implicacao:** quando diz "voltou em 17 dias", pode ser pra um plano gratis em outra conta
    - **Validacao:** apenas 2.6% dos valores batem com calculo por account_id
    - **Uso correto:** entender como "proximo contrato da mesma pessoa", sem assumir que e o mesmo plano

    ---
    #### 3. A flag de 17 dias

    - 65.4% das migracoes pro gratis acontecem entre 15-21 dias (media: 17 dias)
    - Reflete o ciclo de retentativa do gateway de pagamento
    - Apos esgotar retentativas, o pipeline migra automaticamente pro `cartao dr.consulta - gratis`
    - Esse timing e deterministico (do sistema), nao comportamental (do paciente)

    ---
    #### 4. O score v4 continua valido

    - AUC 0.654 (melhor que todas as alternativas testadas, exceto target 90d)
    - Preve **churn por perfil** — o que o time de Growth pode atuar
    - A migracao gratis nao e previsivel por perfil (depende do gateway)
    - Recomendacao: usar v4 para priorizacao + tratar gratis como workstream separada

    ---
    #### 5. Proximos passos sugeridos
    """)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        **Para Growth/Retencao:**
        - Usar score v4 para priorizar contato proativo
          antes do vencimento (foco nos 44.3% que saem de vez)
        - Acelerar reconversao dos 25.7% que voltam pro pago
          (reduzir os 56 dias de media)
        - Acompanhar drivers por faixa de risco (pag 19)
        """)

    with col2:
        st.markdown("""
        **Para Financeiro/Pagamentos:**
        - Investigar por que 30% dos pagamentos falham no vencimento
        - Considerar intervencao ativa nos 15-21 dias
          (antes da migracao automatica pro gratis)
        - Avaliar se o plano gratis deveria existir como
          destino automatico (82% nao voltam)
        """)

    st.markdown("""
    ---
    > **A maior descoberta desta investigacao nao e um numero — e que churn
    > nao e um problema unico. Sao 3 problemas distintos que exigem
    > 3 equipes, 3 metricas e 3 planos de acao diferentes.**
    """)
