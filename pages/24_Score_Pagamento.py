"""
Pagina 24 — Score com Features de Pagamento
=============================================
Comparacao completa: 4 targets × 2 feature sets × 2 layouts de faixa.
Mostra como features de pagamento (Adyen) transformam a capacidade
preditiva do modelo de churn.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="Score com Pagamento", page_icon="🔑", layout="wide")
st.title("🔑 Score com Features de Pagamento")
st.caption("O que acontece quando ensinamos o modelo a ver falhas de pagamento?")


# ═══════════════════════════════════════════════════════════════════
# DADOS
# ═══════════════════════════════════════════════════════════════════

@st.cache_data
def load_faixas():
    return pd.read_csv("results/score_pgto_v2_faixas.csv")

@st.cache_data
def load_auc():
    return pd.read_csv("results/score_pgto_v2_resumo_auc.csv")

@st.cache_data
def load_roc():
    return pd.read_csv("results/score_pgto_v2_roc.csv")

try:
    df_faixas = load_faixas()
    df_auc = load_auc()
    df_roc = load_roc()
except FileNotFoundError as e:
    st.error(f"CSV nao encontrado: {e}")
    st.stop()

CORES_FAIXA = {
    "CRITICO": "#8b0000", "MUITO ALTO": "#d62728", "ALTO": "#ff7f0e",
    "MEDIO": "#ffbb33", "BAIXO": "#2ca02c", "MUITO BAIXO": "#1f77b4", "SEGURO": "#0d3b8b",
}

TARGETS_LABEL = {
    "Original": "Original (nao renovou)",
    "v4 (exclui 30d)": "v4 (exclui todos 30d)",
    "v5 (so pago 30d)": "v5 (so exclui pago 30d)",
    "Estendido (pos-gratis)": "Estendido (pos-gratis)",
}

TARGET_ORDER = ["Original", "v4 (exclui 30d)", "v5 (so pago 30d)", "Estendido (pos-gratis)"]


# ═══════════════════════════════════════════════════════════════════
# INTRO
# ═══════════════════════════════════════════════════════════════════

st.markdown("""
---
### O contexto

Nas paginas anteriores, descobrimos que **71% do churn e involuntario** — causado
por falha de pagamento, nao por decisao do paciente. O score v4 (baseado em perfil)
nao conseguia prever esses casos porque usava features como idade, NPS e dependentes
— que nao tem relacao com o cartao passar ou nao.

Agora testamos: **o que acontece quando adicionamos features de pagamento ao modelo?**

Features novas (extraidas da `public_adyen_events`):
- Numero de tentativas, sucessos e falhas
- Motivos de recusa (saldo insuficiente, cartao vencido, fraude...)
- Cycles e retries do gateway
- Merchant advice (retry after X days, new account info...)
- Taxa de falha e flag "so falha" (nunca aprovou)
""")


# ═══════════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════════

tab1, tab2, tab_roc, tab3, tab4, tab5, tab6 = st.tabs([
    "📐 Os 4 Targets",
    "📊 AUC Comparativo",
    "📉 Curva ROC",
    "📈 Faixas 5 e 7",
    "🔬 Subgrupo Adyen",
    "🏆 Feature Importance",
    "💡 Conclusoes",
])


# ═══════════════════════════════════════════════════════════════════
# TAB 1: OS 4 TARGETS
# ═══════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("### As 4 definicoes de churn testadas")

    st.markdown("""
    Cada target define churn de forma diferente, tratando os 4 destinos
    possiveis do paciente de maneira distinta:
    """)

    # Tabela conceitual
    st.markdown("""
    | Destino do paciente | Original | v4 | v5 | Estendido |
    |---|---|---|---|---|
    | **Saiu de vez** (nunca mais voltou) | 🔴 CHURN | 🔴 CHURN | 🔴 CHURN | 🔴 CHURN |
    | **Voltou pago direto** (<30 dias) | 🔴 CHURN | 🟢 nao churn | 🟢 nao churn | 🟢 nao churn |
    | **Migrou gratis → saiu** (82% dos casos) | 🔴 CHURN | 🟢 nao churn | 🔴 CHURN | 🔴 CHURN |
    | **Migrou gratis → voltou pago** (18%) | 🔴 CHURN | 🟢 nao churn | 🔴 CHURN | 🟢 nao churn |
    """)

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        #### Original
        *"Nao renovou = churn"*

        A definicao mais simples. Se o contrato venceu e a account_due_date
        nao se estendeu, e churn. Nao importa o que aconteceu depois.

        - Taxa: **54.7%**
        - Inclui tudo: quem saiu, quem voltou, quem migrou pro gratis
        - Com so perfil: AUC 0.59 (ruim — mistura causas diferentes)

        ---

        #### v4 (exclui todos 30d)
        *"Nao renovou E nao voltou em 30 dias"*

        Se a pessoa teve qualquer novo contrato em 30 dias (pago ou gratis),
        nao conta como churn. Foi o melhor modelo ate agora.

        - Taxa: **22.5%**
        - Exclui migracoes pro gratis (maioria acontece em ~17 dias)
        - Com so perfil: AUC 0.64 (melhor — removeu ruido de pagamento)
        - Problema: 82% dos que migram pro gratis saem depois (sao churn real)
        """)

    with col2:
        st.markdown("""
        #### v5 (so exclui pago 30d)
        *"Nao renovou E nao voltou pro PAGO em 30 dias"*

        Quem migrou pro gratis continua como churn (correto, ja que 82% saem).
        So exclui quem voltou pra um plano pago de verdade.

        - Taxa: **49.4%**
        - Conceito mais correto que o v4
        - Com so perfil: AUC 0.60 (fraco — falha de pagamento vira ruido)
        - Com pagamento: o modelo consegue separar

        ---

        #### Estendido (pos-gratis)
        *"Espera o desfecho real do gratis"*

        Proposta do Growth. Espera o gratis acabar pra saber se a pessoa
        voltou pro pago ou saiu de vez.

        - Taxa: **41.9%**
        - Conceitualmente o mais correto
        - Problema operacional: precisa esperar 2+ meses
        - Bom pra reporte, nao pra acao proativa
        """)


# ═══════════════════════════════════════════════════════════════════
# TAB 2: AUC COMPARATIVO
# ═══════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("### AUC: antes e depois das features de pagamento")

    st.markdown("""
    Mesmo modelo (XGBoost), mesmos hiperparametros, mesma validacao (5-fold CV).
    A unica diferenca: adicionar 20 features extraidas das tentativas de pagamento Adyen.
    """)

    st.markdown("---")

    # Grafico de barras agrupadas
    fig_auc = go.Figure()

    targets_plot = df_auc["target"].tolist()
    auc_perfil = df_auc["auc_perfil"].tolist()
    auc_completo = df_auc["auc_completo"].tolist()
    deltas = df_auc["delta"].tolist()

    fig_auc.add_trace(go.Bar(
        x=targets_plot, y=auc_perfil,
        name="So perfil",
        marker_color="#95a5a6", opacity=0.7,
        text=[f"{v:.4f}" for v in auc_perfil],
        textposition="outside", textfont=dict(size=12),
    ))
    fig_auc.add_trace(go.Bar(
        x=targets_plot, y=auc_completo,
        name="Perfil + pagamento",
        marker_color="#e67e22", opacity=0.9,
        text=[f"{v:.4f}" for v in auc_completo],
        textposition="outside", textfont=dict(size=12, color="#c0392b"),
    ))

    fig_auc.update_layout(
        barmode="group",
        title="AUC por target: so perfil vs perfil + pagamento",
        yaxis=dict(title="AUC (5-fold CV)", range=[0.5, 0.8]),
        height=480,
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_auc, use_container_width=True)

    # KPIs de delta
    st.markdown("#### Ganho por target")

    cols = st.columns(4)
    for i, (_, row) in enumerate(df_auc.iterrows()):
        with cols[i]:
            st.metric(
                row["target"],
                f"AUC {row['auc_completo']:.4f}",
                delta=f"{row['delta']:+.4f} vs perfil",
                delta_color="normal" if row["delta"] > 0 else "inverse",
            )

    st.markdown("""
    ---
    #### O que isso significa

    **Antes** (so perfil), o v4 era o melhor target (AUC 0.638) porque excluia
    as falhas de pagamento que o modelo nao conseguia prever.

    **Agora** (perfil + pagamento), a hierarquia se inverte:
    - **Original** e **v5** ganham mais (+0.15 e +0.13) porque agora o modelo
      **consegue** prever falhas de pagamento
    - **v4** ganha menos (+0.05) porque ja tinha excluido esses casos do target

    > Excluir falhas de pagamento do target (v4) era uma muleta.
    > Agora que o modelo ve os dados de pagamento, a muleta nao e mais necessaria.
    """)

    # Tabela
    st.markdown("---")
    st.markdown("#### Tabela completa")

    df_auc_tab = df_auc.copy()
    df_auc_tab.columns = ["Target", "AUC Perfil", "AUC Perfil+Pgto", "Delta", "Churn Rate %"]
    df_auc_tab["AUC Perfil"] = df_auc_tab["AUC Perfil"].round(4)
    df_auc_tab["AUC Perfil+Pgto"] = df_auc_tab["AUC Perfil+Pgto"].round(4)
    df_auc_tab["Delta"] = df_auc_tab["Delta"].apply(lambda x: f"{x:+.4f}")
    df_auc_tab["Churn Rate %"] = df_auc_tab["Churn Rate %"].round(1)
    st.dataframe(df_auc_tab, hide_index=True, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
# TAB ROC: CURVAS ROC
# ═══════════════════════════════════════════════════════════════════
with tab_roc:
    st.markdown("### Curva ROC: como ler")

    st.markdown("""
    A curva ROC mostra a **capacidade do modelo de separar** quem churna
    de quem nao churna. Cada ponto da curva e um limiar de corte diferente.

    - **Eixo X (Taxa de Alarme Falso):** de todos os que NAO churnaram,
      quantos % o modelo classificou errado como churn
    - **Eixo Y (Taxa de Deteccao):** de todos os que churnaram,
      quantos % o modelo detectou corretamente
    - **Linha diagonal cinza:** chute aleatorio (AUC = 0.50)
    - **Quanto mais a curva encosta no canto superior esquerdo, melhor**

    > Em termos simples: se voce pegar 1 paciente que churnou e 1 que renovou,
    > o AUC e a probabilidade do modelo dar um **risco maior** pro que churnou.
    """)

    st.markdown("---")

    # Seletor de visualizacao
    roc_view = st.radio(
        "Visualizacao:",
        ["Por target (perfil vs perfil+pgto)", "Todos os modelos juntos"],
        horizontal=True, key="roc_view"
    )

    CORES_TARGET = {
        "Original": "#e74c3c",
        "v4 (exclui 30d)": "#27ae60",
        "v5 (so pago 30d)": "#f39c12",
        "Estendido (pos-gratis)": "#3498db",
    }

    if roc_view == "Por target (perfil vs perfil+pgto)":
        target_roc = st.selectbox("Target:", TARGET_ORDER, key="target_roc")

        fig_roc = go.Figure()

        # Diagonal
        fig_roc.add_trace(go.Scatter(
            x=[0, 1], y=[0, 1], mode="lines",
            line=dict(dash="dash", color="#bdc3c7", width=1),
            name="Aleatorio (0.50)", showlegend=True,
        ))

        for feat, cor, nome in [
            ("perfil", "#95a5a6", "So perfil"),
            ("perfil_pgto", "#e67e22", "Perfil + pagamento"),
        ]:
            mask = (df_roc["target"] == target_roc) & (df_roc["features"] == feat)
            df_r = df_roc[mask].sort_values("fpr")
            if len(df_r) == 0:
                continue
            auc_val = df_r["auc"].iloc[0]
            fig_roc.add_trace(go.Scatter(
                x=df_r["fpr"], y=df_r["tpr"],
                mode="lines", name=f"{nome} (AUC {auc_val:.4f})",
                line=dict(width=3, color=cor),
            ))

        fig_roc.update_layout(
            title=f"Curva ROC — {target_roc}",
            xaxis=dict(title="Taxa de Alarme Falso (FPR)", range=[0, 1]),
            yaxis=dict(title="Taxa de Deteccao (TPR)", range=[0, 1.05]),
            height=550,
            legend=dict(x=0.4, y=0.15, bgcolor="rgba(255,255,255,0.8)"),
        )
        st.plotly_chart(fig_roc, use_container_width=True)

    else:
        # Todos juntos — so perfil+pgto
        fig_roc_all = go.Figure()

        fig_roc_all.add_trace(go.Scatter(
            x=[0, 1], y=[0, 1], mode="lines",
            line=dict(dash="dash", color="#bdc3c7", width=1),
            name="Aleatorio (0.50)", showlegend=True,
        ))

        for target in TARGET_ORDER:
            for feat, dash, suffix in [("perfil", "dot", " (perfil)"), ("perfil_pgto", "solid", " (perf+pgto)")]:
                mask = (df_roc["target"] == target) & (df_roc["features"] == feat)
                df_r = df_roc[mask].sort_values("fpr")
                if len(df_r) == 0:
                    continue
                auc_val = df_r["auc"].iloc[0]
                fig_roc_all.add_trace(go.Scatter(
                    x=df_r["fpr"], y=df_r["tpr"],
                    mode="lines",
                    name=f"{target}{suffix} ({auc_val:.3f})",
                    line=dict(width=2 if dash == "dot" else 3,
                              color=CORES_TARGET.get(target, "gray"),
                              dash=dash),
                ))

        fig_roc_all.update_layout(
            title="Curvas ROC — Todos os modelos (pontilhado = so perfil, solido = perfil+pgto)",
            xaxis=dict(title="Taxa de Alarme Falso (FPR)", range=[0, 1]),
            yaxis=dict(title="Taxa de Deteccao (TPR)", range=[0, 1.05]),
            height=600,
            legend=dict(x=0.35, y=0.3, bgcolor="rgba(255,255,255,0.8)", font=dict(size=10)),
        )
        st.plotly_chart(fig_roc_all, use_container_width=True)

    st.markdown("""
    ---
    #### Como interpretar pra areas de negocio

    | AUC | Significado | Analogia |
    |---|---|---|
    | 0.50 | Chute aleatorio | Jogar moeda |
    | 0.59 | Fraco (Original, so perfil) | Acerta a ordem em 6 de 10 comparacoes |
    | 0.65 | Moderado (v4, so perfil) | Acerta 6.5 de 10 |
    | **0.74** | **Bom (Original + pgto)** | **Acerta quase 3 de cada 4** |
    | 0.81 | Muito bom (subgrupo Adyen) | Acerta 8 de 10 |
    | 1.00 | Perfeito | Nunca erra a ordem |

    > **Na pratica:** o que importa nao e o numero do AUC, e o **spread nas faixas**.
    > CRITICO com 94% de churn vs SEGURO com 12% = o modelo separa o suficiente
    > pra priorizar acoes do CRM.
    """)


# ═══════════════════════════════════════════════════════════════════
# TAB 3: FAIXAS 5 E 7
# ═══════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("### Faixas de risco: perfil vs perfil + pagamento")

    layout_sel = st.radio("Layout:", ["5 faixas", "7 faixas"],
                          horizontal=True, key="layout_tab3")
    layout_key = layout_sel.replace(" ", "_")

    target_sel = st.selectbox("Target:", TARGET_ORDER, key="target_tab3")

    df_f = df_faixas[df_faixas["layout"] == layout_key].copy()
    df_f_target = df_f[df_f["target"] == target_sel]

    df_perfil = df_f_target[df_f_target["features"] == "perfil"]
    df_pgto = df_f_target[df_f_target["features"] == "perfil_pgto"]

    if len(df_perfil) == 0 or len(df_pgto) == 0:
        st.warning("Dados nao disponiveis para esta combinacao")
        st.stop()

    labels_faixa = df_perfil["faixa"].tolist()

    # Funcao de grafico
    def plot_faixas(df_plot, col_contratos, col_churn, titulo, cores):
        fig = go.Figure()
        total = df_plot[col_contratos].sum()

        fig.add_trace(go.Bar(
            x=df_plot["faixa"], y=df_plot[col_contratos],
            name="Contratos",
            marker_color=[cores.get(f, "gray") for f in df_plot["faixa"]],
            opacity=0.4,
            text=df_plot.apply(
                lambda r: f'{int(r[col_contratos]):,}\n({round(100*r[col_contratos]/total,1)}%)',
                axis=1),
            textposition="outside", textfont=dict(size=10),
        ))

        fig.add_trace(go.Scatter(
            x=df_plot["faixa"], y=df_plot[col_churn],
            name="Churn (%)", mode="lines+markers+text",
            marker=dict(size=12,
                        color=[cores.get(f, "gray") for f in df_plot["faixa"]],
                        line=dict(width=2, color="white")),
            line=dict(width=3, color="gray", dash="dot"),
            yaxis="y2",
            text=df_plot[col_churn].apply(lambda x: f"{x}%"),
            textposition="top center",
            textfont=dict(size=13, color="crimson"),
        ))

        rates = df_plot.loc[df_plot[col_contratos] >= 10, col_churn]
        spread = round(rates.max() - rates.min(), 1) if len(rates) >= 2 else 0

        fig.update_layout(
            title=f"{titulo} — Spread: {spread} p.p.",
            yaxis=dict(title="Contratos"),
            yaxis2=dict(title="Churn (%)", overlaying="y", side="right", range=[0, 110]),
            legend=dict(orientation="h", y=1.12),
            height=470,
        )
        return fig, spread

    # Lado a lado
    col1, col2 = st.columns(2)

    with col1:
        fig_p, sp_p = plot_faixas(
            df_perfil, "contratos", "churn_rate",
            f"So perfil · {target_sel}", CORES_FAIXA)
        st.plotly_chart(fig_p, use_container_width=True)

    with col2:
        fig_c, sp_c = plot_faixas(
            df_pgto, "contratos", "churn_rate",
            f"Perfil + pagamento · {target_sel}", CORES_FAIXA)
        st.plotly_chart(fig_c, use_container_width=True)

    # Spreads
    s1, s2, s3 = st.columns(3)
    s1.metric("Spread perfil", f"{sp_p} p.p.")
    s2.metric("Spread perfil+pgto", f"{sp_c} p.p.",
              delta=f"{sp_c - sp_p:+.1f} p.p.", delta_color="normal" if sp_c > sp_p else "inverse")
    s3.metric("Ganho AUC",
              f"+{df_auc[df_auc['target']==target_sel]['delta'].values[0]:.4f}")

    # Tabela comparativa
    st.markdown("---")
    st.markdown("#### Tabela: churn rate por faixa")

    df_comp = df_perfil[["faixa", "contratos", "churn_rate"]].merge(
        df_pgto[["faixa", "contratos", "churn_rate"]],
        on="faixa", suffixes=("_perfil", "_pgto")
    )
    df_comp["delta"] = (df_comp["churn_rate_pgto"] - df_comp["churn_rate_perfil"]).round(1)
    df_comp.columns = ["Faixa", "n (perfil)", "Churn % (perfil)",
                        "n (perf+pgto)", "Churn % (perf+pgto)", "Delta p.p."]
    st.dataframe(df_comp, hide_index=True, use_container_width=True)

    # Todos os targets de uma vez
    st.markdown("---")
    st.markdown("#### Comparacao rapida: spread por target e features")

    rows_spread = []
    for t in TARGET_ORDER:
        for feat in ["perfil", "perfil_pgto"]:
            df_sub = df_f[(df_f["target"] == t) & (df_f["features"] == feat)]
            rates = df_sub.loc[df_sub["contratos"] >= 10, "churn_rate"]
            spread = round(rates.max() - rates.min(), 1) if len(rates) >= 2 else 0
            rows_spread.append({"Target": t, "Features": feat, "Spread (p.p.)": spread})

    df_spread = pd.DataFrame(rows_spread)
    df_spread_pivot = df_spread.pivot(index="Target", columns="Features", values="Spread (p.p.)")
    df_spread_pivot = df_spread_pivot[["perfil", "perfil_pgto"]]
    df_spread_pivot.columns = ["So perfil", "Perfil + pgto"]
    df_spread_pivot["Ganho"] = (df_spread_pivot["Perfil + pgto"] - df_spread_pivot["So perfil"]).round(1)
    st.dataframe(df_spread_pivot, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
# TAB 4: SUBGRUPO ADYEN
# ═══════════════════════════════════════════════════════════════════
with tab4:
    st.markdown("### Onde o ganho se concentra?")

    st.markdown("""
    As features de pagamento vem da `public_adyen_events`. Nem todos os contratos
    passam pela Adyen — ~23% tem dados de pagamento, ~77% nao.

    O modelo trata os dois grupos de forma diferente:
    - **Com Adyen:** usa perfil + pagamento → ganho massivo
    - **Sem Adyen:** features de pagamento ficam zeradas → sem mudanca
    """)

    st.markdown("---")

    # Metricas
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Com tentativa Adyen (23%)")
        st.metric("Contratos", "28,377")
        st.metric("Churn rate", "15.6%")
        st.metric("AUC so perfil", "0.7066")
        st.metric("AUC perfil + pgto", "0.8119",
                  delta="+0.1053", delta_color="normal")

    with col2:
        st.markdown("#### Sem tentativa Adyen (77%)")
        st.metric("Contratos", "95,475")
        st.metric("Churn rate", "24.5%")
        st.metric("AUC so perfil", "0.6356")
        st.metric("AUC perfil + pgto", "0.6355",
                  delta="-0.0001", delta_color="off")

    # Grafico
    fig_sub = go.Figure()
    subgrupos = ["Com Adyen\n(23%)", "Sem Adyen\n(77%)"]
    auc_p = [0.7066, 0.6356]
    auc_c = [0.8119, 0.6355]

    fig_sub.add_trace(go.Bar(x=subgrupos, y=auc_p, name="So perfil",
                             marker_color="#95a5a6", opacity=0.7,
                             text=[f"{v:.4f}" for v in auc_p], textposition="outside"))
    fig_sub.add_trace(go.Bar(x=subgrupos, y=auc_c, name="Perfil + pgto",
                             marker_color="#e67e22", opacity=0.9,
                             text=[f"{v:.4f}" for v in auc_c], textposition="outside"))
    fig_sub.update_layout(
        barmode="group",
        title="AUC por subgrupo (target v4)",
        yaxis=dict(title="AUC", range=[0.5, 0.9]),
        height=420,
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_sub, use_container_width=True)

    st.markdown("""
    ---
    #### Por que o subgrupo "com Adyen" tem churn menor (15.6% vs 24.5%)?

    Porque ter tentativa de pagamento registrada na Adyen significa que o sistema
    **tentou cobrar** — e muitas dessas tentativas foram bem-sucedidas. Contratos
    "sem tentativa Adyen" podem ter sido processados pela Mundipagg ou nao terem
    tido nenhuma tentativa de cobranca (27.5% do churn, conforme pagina 23).

    ---
    #### Implicacao

    Se conseguissemos dados equivalentes da **Mundipagg** (que processa ~60% dos
    contratos), o ganho se estenderia a quase toda a base. O AUC geral (hoje 0.69)
    poderia se aproximar do AUC do subgrupo Adyen (0.81).
    """)


# ═══════════════════════════════════════════════════════════════════
# TAB 5: FEATURE IMPORTANCE
# ═══════════════════════════════════════════════════════════════════
with tab5:
    st.markdown("### Quais features mais importam no modelo combinado?")

    st.markdown("Top 20 features por **gain** (modelo perfil + pagamento, target v4):")

    # Dados hardcoded do output
    feat_data = [
        ("sucessos", 230.1, True),
        ("faixa_dep_sem_dep", 142.3, False),
        ("tem_atendimento", 126.2, False),
        ("total_tentativas", 71.9, True),
        ("faixa_idade_cat_senior", 63.5, False),
        ("faixa_dep_3+_dep", 53.8, False),
        ("taxa_falha_pgto", 44.6, True),
        ("faixa_idade_cat_jovem", 27.2, False),
        ("falhas", 26.6, True),
        ("faixa_tempo_cat_sem_atend", 25.4, False),
        ("ciclo_2o+", 22.5, False),
        ("canal_simples_presencial", 21.7, False),
        ("tem_tentativa_pgto", 17.4, True),
        ("max_retry", 17.3, True),
        ("cronico_S", 13.1, False),
        ("qtd_atendimentos", 11.3, False),
        ("duracao_6", 10.9, False),
        ("janela_tentativas_dias", 10.6, True),
        ("faixa_nps_cat_promotor", 10.3, False),
        ("max_cycle", 6.9, True),
    ]

    # Grafico horizontal
    feat_names = [f[0] for f in feat_data][::-1]
    feat_gains = [f[1] for f in feat_data][::-1]
    feat_is_pgto = [f[2] for f in feat_data][::-1]
    feat_colors = ["#e67e22" if p else "#3498db" for p in feat_is_pgto]

    fig_feat = go.Figure()
    fig_feat.add_trace(go.Bar(
        y=feat_names, x=feat_gains, orientation="h",
        marker_color=feat_colors,
        text=[f"{g:.0f}" for g in feat_gains],
        textposition="outside",
    ))
    fig_feat.update_layout(
        title="Feature Importance (Gain) — 🟠 Pagamento  🔵 Perfil",
        xaxis_title="Gain",
        height=600,
        margin=dict(l=200),
    )
    st.plotly_chart(fig_feat, use_container_width=True)

    n_pgto_top20 = sum(1 for f in feat_data if f[2])
    st.markdown(f"""
    **{n_pgto_top20} das top 20 features sao de pagamento** (em laranja).

    A feature #1 e **sucessos** (gain 230): ter pelo menos 1 pagamento aprovado
    e o melhor preditor de renovacao. Faz sentido — se o cartao passou, o contrato renova.

    As features de perfil continuam relevantes (sem_dep, senior, atendimento),
    mas agora dividem espaco com as de pagamento.

    ---
    #### O que cada feature de pagamento captura

    | Feature | O que mede | Por que importa |
    |---|---|---|
    | **sucessos** | Pagamentos aprovados | Se passou ≥1 vez, renova |
    | **total_tentativas** | Volume de tentativas | Mais tentativas = mais chance |
    | **taxa_falha_pgto** | % de falhas | 100% falha ≈ churn certo |
    | **falhas** | Contagem de recusas | Correlaciona com tipo de problema |
    | **tem_tentativa_pgto** | Flag: teve cobranca? | Separa Adyen de nao-Adyen |
    | **max_retry** | Retries do gateway | Mostra persistencia do sistema |
    | **janela_tentativas_dias** | Dias entre 1a e ultima tentativa | Janela longa = sistema tentando |
    | **max_cycle** | Ciclo maximo de cobranca | Depth do processo de cobranca |
    """)


# ═══════════════════════════════════════════════════════════════════
# TAB 6: CONCLUSOES
# ═══════════════════════════════════════════════════════════════════
with tab6:
    st.markdown("### O que aprendemos")

    st.markdown("""
    ---
    #### 1. Features de pagamento melhoram TODOS os targets

    | Target | So perfil | + Pagamento | Ganho |
    |---|---|---|---|
    | Original | 0.5907 | **0.7427** | **+0.152** |
    | v5 (so pago 30d) | 0.6024 | **0.7340** | **+0.132** |
    | Estendido (pos-gratis) | 0.6302 | **0.7319** | **+0.102** |
    | v4 (exclui 30d) | 0.6384 | 0.6887 | +0.050 |

    O ganho e universal — nao depende da definicao de churn.

    ---
    #### 2. A hierarquia dos targets se inverteu

    **Antes** (so perfil): v4 > Estendido > v5 > Original

    **Agora** (perfil + pgto): **Original > v5 > Estendido > v4**

    O v4 era o melhor porque excluia o que o modelo nao conseguia prever.
    Agora que o modelo consegue, excluir **perde informacao**.

    ---
    #### 3. O ganho e concentrado nos 23% com dados Adyen

    | Subgrupo | n | AUC perfil | AUC completo |
    |---|---|---|---|
    | **Com Adyen** | 28,377 (23%) | 0.707 | **0.812** |
    | Sem Adyen | 95,475 (77%) | 0.636 | 0.636 |

    Para quem tem dados Adyen, o modelo melhora **+0.105 de AUC**.
    Para quem nao tem, permanece igual — nao piora.

    ---
    #### 4. Implicacao operacional
    """)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        **O que ja e acionavel:**

        - Contratos na faixa CRITICO do modelo
          combinado tem **94-99% de chance de churn**
        - Sao ~2-12k contratos (dependendo do target)
          onde sabemos que o cartao vai falhar
        - Acionar CRM proativo: SMS/WhatsApp
          pedindo atualizacao do cartao
        - Regra simples: `so_falha = 1` →
          alerta imediato (sem precisar do modelo)
        """)

    with col2:
        st.markdown("""
        **O que falta pra escalar:**

        - **Dados Mundipagg equivalentes:** cobriria
          os outros 60% dos contratos. AUC geral
          poderia ir de 0.69 pra ~0.80
        - **Dados em tempo real:** hoje analisamos
          retroativamente. Ideal: score rodando
          diariamente nos contratos proximos do
          vencimento
        - **Testar regras vs modelo:** a regra
          `so_falha = 1` pode ser tao boa quanto
          o XGBoost pra este caso especifico
        """)

    st.markdown("""
    ---
    #### 5. Recomendacao de modelo

    | Contexto | Modelo recomendado | Por que |
    |---|---|---|
    | **Score operacional (CRM)** | **v5 + pagamento** (AUC 0.734) | Conceito correto, bom AUC, nao precisa esperar |
    | **Maxima separacao** | Original + pagamento (AUC 0.743) | Melhor AUC e spread (92.6 p.p.) |
    | **Compatibilidade comite** | v4 + pagamento (AUC 0.689) | Mantem definicao conhecida, ganho de +0.05 |
    | **Reporte** | Estendido (taxa 41.9%) | Metrica mais justa de churn efetivo |

    ---
    > **A maior descoberta desta analise:** o "teto" do score de churn nao era
    > a qualidade das features de perfil — era a **ausencia de dados de pagamento**.
    > Adicionar 20 features de pagamento fez o AUC saltar de 0.59 pra 0.74
    > (target original), a maior melhoria em todo o historico do projeto.
    > O caminho pra reduzir churn na dr.consulta passa por **dados de cobranca**,
    > nao por mais features de perfil.
    """)
