"""
Pagina 14 — SAC × Churn v3 (dados corrigidos)
===============================================
Separa cancelamentos dos demais contatos. Analisa retencao, motivos,
timing, dependentes, reincidentes e unidades.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(page_title="SAC × Churn", page_icon="📞", layout="wide")
st.title("📞 SAC × Churn")
st.caption("O que o atendimento ao paciente revela sobre a retencao")


# ═══════════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════════
@st.cache_data
def load_metricas():
    return pd.read_csv("results/sac_churn_metricas.csv")

@st.cache_data
def load_motivos():
    df = pd.read_csv("results/sac_churn_motivos.csv")
    if "categoria_sac" in df.columns and "categoria" not in df.columns:
        df = df.rename(columns={"categoria_sac": "categoria"})
    return df

@st.cache_data
def load_cancelamentos():
    return pd.read_csv("results/sac_churn_cancelamentos.csv")

@st.cache_data
def load_timeline():
    return pd.read_csv("results/sac_churn_timeline.csv")

@st.cache_data
def load_unidades():
    return pd.read_csv("results/sac_churn_unidades.csv")

@st.cache_data
def load_dependentes():
    return pd.read_csv("results/sac_churn_dependentes.csv")

@st.cache_data
def load_reincidentes():
    return pd.read_csv("results/sac_churn_reincidentes.csv")


try:
    df_met = load_metricas()
    df_mot = load_motivos()
    df_can = load_cancelamentos()
    df_tim = load_timeline()
    df_uni = load_unidades()
    df_dep = load_dependentes()
    df_rei = load_reincidentes()
except FileNotFoundError as e:
    st.error(f"CSV nao encontrado: {e}. Rode `scripts/cruzar_sac_churn.py`.")
    st.stop()


# ═══════════════════════════════════════════════════════════════════
# METRICAS GLOBAIS
# ═══════════════════════════════════════════════════════════════════
df_met["grupo"] = df_met["grupo"].str.strip()
total_contratos = int(df_met["contratos"].sum())

mask_sem = df_met["grupo"].str.contains("Sem SAC", case=False)
mask_outros = df_met["grupo"].str.contains("sem cancelamento", case=False)
mask_cancel = df_met["grupo"].str.contains("cancelamento", case=False) & ~mask_outros

sem_sac = df_met[mask_sem].iloc[0] if mask_sem.any() else None
sac_outros = df_met[mask_outros].iloc[0] if mask_outros.any() else None

churn_sem = float(sem_sac["churn_rate"]) if sem_sac is not None else 0
churn_outros = float(sac_outros["churn_rate"]) if sac_outros is not None else 0

sac_cancel = df_met[mask_cancel]
n_cancel = int(sac_cancel["contratos"].sum())
ch_cancel = int(sac_cancel["churners"].sum())
churn_cancel = round(100 * ch_cancel / n_cancel, 1) if n_cancel > 0 else 0
retidos_cancel = n_cancel - ch_cancel
taxa_retencao = round(100 * retidos_cancel / n_cancel, 1) if n_cancel > 0 else 0


# ═══════════════════════════════════════════════════════════════════
# HEADER KPIs
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Contratos analisados", f"{total_contratos:,}")
k2.metric("Churn base (sem SAC)", f"{churn_sem}%")
k3.metric("Churn SAC (outros motivos)", f"{churn_outros}%",
          delta=f"{churn_outros - churn_sem:+.1f} p.p. vs base",
          delta_color="inverse" if churn_outros > churn_sem else "normal")
k4.metric("Pediram cancelamento", f"{n_cancel:,}")
k5.metric("Retidos pela retencao", f"{retidos_cancel:,}",
          delta=f"{taxa_retencao}% de retencao", delta_color="normal")


# ═══════════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════════
tab_visao, tab_retencao, tab_motivos, tab_timing, tab_unidades, tab_sinais = st.tabs([
    "📊 Visao Geral",
    "🛡️ Retencao",
    "🏷️ Motivos (sem cancelamento)",
    "⏱️ Timing",
    "🏥 Unidades",
    "💡 Insights",
])


# ═══════════════════════════════════════════════════════════════════
# TAB 1: VISAO GERAL
# ═══════════════════════════════════════════════════════════════════
with tab_visao:
    st.markdown("### O SAC protege contra o churn")
    st.markdown("""
    Quando separamos quem ligou por problema (sem cancelamento) de quem ligou
    pra cancelar, o papel do SAC fica claro.
    """)

    grupos = df_met.copy().sort_values("churn_rate", ascending=True)

    cores_grupo = {
        "Sem SAC": "#95a5a6",
        "SAC (sem cancelamento)": "#27ae60",
        "SAC (so cancelamento)": "#c0392b",
        "SAC (cancel + outros)": "#e74c3c",
    }

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=grupos["grupo"],
        x=grupos["churn_rate"],
        orientation="h",
        marker_color=[cores_grupo.get(g, "#3498db") for g in grupos["grupo"]],
        text=grupos.apply(
            lambda r: f'{r["churn_rate"]}% ({int(r["contratos"]):,} contratos)', axis=1
        ),
        textposition="outside",
        textfont=dict(size=13),
    ))
    fig.add_vline(x=churn_sem, line_dash="dash", line_color="gray",
                  annotation_text=f"Base: {churn_sem}%", annotation_position="top")
    fig.update_layout(
        title="Churn por tipo de contato com o SAC",
        xaxis_title="Churn (%)",
        height=300,
        margin=dict(l=20, r=120),
        yaxis=dict(automargin=True),
        xaxis=dict(range=[0, max(grupos["churn_rate"]) + 10]),
    )
    st.plotly_chart(fig, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.success(f"""
        **Quem liga com problema (sem cancelamento): {churn_outros}%**

        **{churn_sem - churn_outros:.1f} p.p. abaixo da base.** Pacientes que tiveram
        problema, ligaram pro SAC e foram atendidos, churneiam **menos** do que
        quem nao liga. O SAC resolve problemas e protege contra o churn.
        """)
    with col2:
        st.error(f"""
        **Quem liga pra cancelar: {churn_cancel}%**

        **{churn_cancel - churn_sem:.1f} p.p. acima da base.** A maioria de quem pede
        cancelamento realmente sai. De {n_cancel:,} que ligaram, **{retidos_cancel:,}
        ({taxa_retencao}%) foram retidos** — a retencao funciona mas e limitada.
        """)


# ═══════════════════════════════════════════════════════════════════
# TAB 2: RETENCAO
# ═══════════════════════════════════════════════════════════════════
with tab_retencao:
    st.markdown("### Analise de Retencao: quem pediu cancelamento")
    st.markdown(f"""
    De **{n_cancel:,}** contratos cujo titular ligou pedindo cancelamento,
    **{ch_cancel:,} ({churn_cancel}%)** cancelaram de fato e
    **{retidos_cancel:,} ({taxa_retencao}%)** foram retidos.
    """)

    k1, k2, k3 = st.columns(3)
    k1.metric("Pediram cancelamento", f"{n_cancel:,}")
    k2.metric("Cancelaram de fato", f"{ch_cancel:,}",
              delta=f"{churn_cancel}%", delta_color="inverse")
    k3.metric("Retidos", f"{retidos_cancel:,}",
              delta=f"{taxa_retencao}%", delta_color="normal")

    st.markdown("---")

    df_can_plot = df_can[df_can["contratos"] >= 10].sort_values("taxa_retencao", ascending=False)

    fig_ret = go.Figure()
    fig_ret.add_trace(go.Bar(
        y=df_can_plot["motivo_cancelamento"],
        x=df_can_plot["retido"],
        orientation="h",
        name="Retido",
        marker_color="#27ae60",
        text=df_can_plot["taxa_retencao"].apply(lambda v: f"{v}%"),
        textposition="inside",
        textfont=dict(size=11, color="white"),
    ))
    fig_ret.add_trace(go.Bar(
        y=df_can_plot["motivo_cancelamento"],
        x=df_can_plot["churnou"],
        orientation="h",
        name="Cancelou",
        marker_color="#c0392b",
        text=df_can_plot["churn_rate"].apply(lambda v: f"{v}%"),
        textposition="inside",
        textfont=dict(size=11, color="white"),
    ))
    fig_ret.update_layout(
        barmode="stack",
        title="Retencao por motivo do pedido de cancelamento",
        xaxis_title="Contratos",
        height=max(450, len(df_can_plot) * 30 + 100),
        legend=dict(orientation="h", y=1.08),
        margin=dict(l=20, r=20),
        yaxis=dict(automargin=True),
    )
    st.plotly_chart(fig_ret, use_container_width=True)

    st.markdown("### Destaques")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Maior taxa de retencao**")
        faceis = df_can.nlargest(5, "taxa_retencao")
        for _, r in faceis.iterrows():
            if r["contratos"] < 5:
                continue
            st.markdown(
                f"- **{r['motivo_cancelamento']}**: {r['taxa_retencao']}% retido "
                f"({int(r['contratos'])} contratos)"
            )

    with col2:
        st.markdown("**Menor taxa de retencao (maior churn)**")
        dificeis = df_can[df_can["contratos"] >= 10].nsmallest(5, "taxa_retencao")
        for _, r in dificeis.iterrows():
            st.markdown(
                f"- **{r['motivo_cancelamento']}**: {r['taxa_retencao']}% retido "
                f"({int(r['contratos'])} contratos)"
            )

    st.markdown("---")

    nao_sabia = df_can[df_can["motivo_cancelamento"] == "Não sabia da renovação"]
    if not nao_sabia.empty:
        r = nao_sabia.iloc[0]
        st.warning(f"""
        **Destaque: "Nao sabia da renovacao"** — {int(r['contratos'])} contratos

        Churn de **{r['churn_rate']}%** nesse grupo. A maioria cancela porque nao foi
        avisada da renovacao automatica. Um lembrete pre-vencimento evitaria boa parte
        desses cancelamentos.
        """)


# ═══════════════════════════════════════════════════════════════════
# TAB 3: MOTIVOS (sem cancelamento)
# ═══════════════════════════════════════════════════════════════════
with tab_motivos:
    st.markdown("### Churn por motivo do contato (excluindo cancelamentos)")
    st.markdown(f"""
    Pacientes que ligaram por outro motivo tem churn medio de **{churn_outros}%**
    — {churn_sem - churn_outros:.1f} p.p. abaixo da base ({churn_sem}%).
    O SAC esta resolvendo problemas e protegendo contra o churn.
    Mas o efeito varia por motivo.
    """)

    df_mot_sorted = df_mot.sort_values("churn_rate", ascending=True)

    fig_mot = go.Figure()
    fig_mot.add_trace(go.Bar(
        y=df_mot_sorted["categoria"],
        x=df_mot_sorted["churn_rate"],
        orientation="h",
        marker_color=[
            "#27ae60" if cr < churn_sem - 10 else "#2ecc71" if cr < churn_sem
            else "#f39c12" if cr < churn_sem + 5 else "#e74c3c"
            for cr in df_mot_sorted["churn_rate"]
        ],
        text=df_mot_sorted.apply(
            lambda r: f'{r["churn_rate"]}% ({int(r["contratos"]):,})', axis=1
        ),
        textposition="outside",
        textfont=dict(size=12),
    ))
    fig_mot.add_vline(x=churn_sem, line_dash="dash", line_color="gray")
    fig_mot.add_annotation(
        x=churn_sem, y=len(df_mot_sorted) - 0.5,
        text=f"Base sem SAC: {churn_sem}%",
        showarrow=False, font=dict(size=10, color="gray"),
        xanchor="left", xshift=5,
    )
    fig_mot.update_layout(
        title="Churn por categoria (sem cancelamentos)",
        xaxis_title="Churn (%)",
        height=max(400, len(df_mot_sorted) * 35 + 80),
        margin=dict(l=20, r=100),
        yaxis=dict(automargin=True),
        xaxis=dict(range=[0, max(df_mot_sorted["churn_rate"]) + 12]),
    )
    st.plotly_chart(fig_mot, use_container_width=True)

    # Dependentes
    st.markdown("---")
    st.markdown("### Dependentes: inclusao vs exclusao")

    if not df_dep.empty:
        col1, col2 = st.columns(2)
        dep_exc = df_dep[df_dep["tipo_dependente"].str.contains("exclusao")]
        dep_inc = df_dep[df_dep["tipo_dependente"].str.contains("inclusao")]

        with col1:
            if not dep_exc.empty:
                st.metric("Exclusao de dependente",
                          f'{dep_exc.iloc[0]["churn_rate"]}% churn',
                          delta=f"{int(dep_exc.iloc[0]['contratos'])} contratos",
                          delta_color="off")

        with col2:
            if not dep_inc.empty:
                st.metric("Inclusao de dependente",
                          f'{dep_inc.iloc[0]["churn_rate"]}% churn',
                          delta=f"{int(dep_inc.iloc[0]['contratos'])} contratos",
                          delta_color="off")

        exc_cr = dep_exc.iloc[0]["churn_rate"] if not dep_exc.empty else 0
        inc_cr = dep_inc.iloc[0]["churn_rate"] if not dep_inc.empty else 0

        st.markdown(f"""
        **Exclusao de dependente: {exc_cr}% de churn** — muito abaixo da base ({churn_sem}%).
        Quem exclui dependente esta **reorganizando o plano pra ficar**, nao pra sair.
        Pode estar removendo alguem que nao usa pra reduzir custo e manter a assinatura.

        **Inclusao: {inc_cr}% de churn** — proximo da base. Operacao normal.
        """)

    # Destaques por motivo
    st.markdown("---")
    st.markdown("### Destaques")

    integ = df_mot[df_mot["categoria"].str.contains("Integracao", case=False)]
    if not integ.empty:
        st.success(f"""
        **Integracao/Ativacao: {integ.iloc[0]['churn_rate']}% de churn**
        ({int(integ.iloc[0]['contratos'])} contratos)

        Muito abaixo da base ({churn_sem}%). Pacientes que tiveram falha de integracao,
        ligaram pro SAC e tiveram o problema resolvido, **ficam**. O atendimento funciona
        como rede de seguranca — sem o SAC, esses pacientes provavelmente teriam saido.
        """)

    # Tabela
    st.markdown("---")
    st.dataframe(
        df_mot.sort_values("churn_rate", ascending=False).rename(columns={
            "categoria": "Motivo", "contratos": "Contratos",
            "churners": "Churners", "churn_rate": "Churn (%)",
            "ticket_medio": "Tickets/paciente",
        }),
        hide_index=True, use_container_width=True,
    )


# ═══════════════════════════════════════════════════════════════════
# TAB 4: TIMING
# ═══════════════════════════════════════════════════════════════════
with tab_timing:
    st.markdown("### Quando o contato acontece em relacao ao vencimento")
    st.markdown("""
    Separamos: quem ligou pra **cancelar** vs quem ligou por **outro motivo**.
    O timing revela a dinamica da decisao.
    """)

    tim_cancel = df_tim[df_tim["tipo_contato"] == "So cancelamento"].copy()
    tim_outros = df_tim[df_tim["tipo_contato"] == "Outros (sem cancelamento)"].copy()

    janela_order = [
        "60+ dias antes", "30-60 dias antes", "7-30 dias antes", "0-7 dias antes",
        "0-7 dias depois", "7-30 dias depois", "30+ dias depois"
    ]

    fig_tim = go.Figure()

    if not tim_outros.empty:
        tim_outros["janela"] = pd.Categorical(tim_outros["janela"], categories=janela_order, ordered=True)
        tim_outros = tim_outros.sort_values("janela")
        fig_tim.add_trace(go.Scatter(
            x=tim_outros["janela"], y=tim_outros["churn_rate"],
            mode="lines+markers+text",
            name="Outros motivos",
            line=dict(width=3, color="#2ecc71"),
            marker=dict(size=10),
            text=tim_outros["churn_rate"].apply(lambda v: f"{v}%"),
            textposition="top center",
            textfont=dict(size=11),
        ))

    if not tim_cancel.empty:
        tim_cancel["janela"] = pd.Categorical(tim_cancel["janela"], categories=janela_order, ordered=True)
        tim_cancel = tim_cancel.sort_values("janela")
        fig_tim.add_trace(go.Scatter(
            x=tim_cancel["janela"], y=tim_cancel["churn_rate"],
            mode="lines+markers+text",
            name="Cancelamento",
            line=dict(width=3, color="#c0392b"),
            marker=dict(size=10),
            text=tim_cancel["churn_rate"].apply(lambda v: f"{v}%"),
            textposition="bottom center",
            textfont=dict(size=11),
        ))

    fig_tim.add_shape(
        type="line", x0=3.5, x1=3.5, y0=0, y1=1, yref="paper",
        line=dict(dash="dash", color="black", width=2),
    )
    fig_tim.add_annotation(
        x=3.5, y=1, yref="paper",
        text="Vencimento", showarrow=False, font=dict(size=12), yanchor="bottom",
    )
    fig_tim.add_hline(y=churn_sem, line_dash="dot", line_color="gray", opacity=0.5,
                      annotation_text=f"Base: {churn_sem}%", annotation_position="bottom left")
    fig_tim.update_layout(
        title="Churn por timing do contato: cancelamento vs outros",
        yaxis_title="Churn (%)",
        height=450,
        legend=dict(orientation="h", y=1.1),
        yaxis=dict(range=[0, 100]),
    )
    st.plotly_chart(fig_tim, use_container_width=True)

    st.markdown("""
    **Leitura:**

    - **Cancelamento ANTES do vencimento:** churn de 23-42%. Quem liga pra cancelar
      antes de vencer tem churn **abaixo da base** — sao pacientes tentando cancelar
      antecipadamente, e parte e retida no processo.

    - **Cancelamento DEPOIS do vencimento:** churn de 79-96%. A renovacao ja aconteceu,
      o paciente descobre a cobranca e liga reclamando. A maioria efetivamente cancela.

    - **Outros motivos ANTES:** churn de ~42-48%, abaixo da base. O SAC resolve e protege.

    - **Outros motivos DEPOIS:** churn de ~52-56%. Paciente ja renovou mas tem problema
      operacional — o churn e levemente acima da base.
    """)

    st.dataframe(
        df_tim.rename(columns={
            "janela": "Janela", "tipo_contato": "Tipo",
            "contratos": "Contratos", "churners": "Churners",
            "churn_rate": "Churn (%)",
        }),
        hide_index=True, use_container_width=True,
    )


# ═══════════════════════════════════════════════════════════════════
# TAB 5: UNIDADES
# ═══════════════════════════════════════════════════════════════════
with tab_unidades:
    st.markdown("### SAC e Churn por Unidade")

    df_uni_plot = df_uni[df_uni["contratos"] >= 100].copy()

    fig_uni = go.Figure()
    fig_uni.add_trace(go.Scatter(
        x=df_uni_plot["pct_com_sac"],
        y=df_uni_plot["churn_rate"],
        mode="markers+text",
        marker=dict(
            size=np.sqrt(df_uni_plot["contratos"]) / 2,
            color=df_uni_plot["churn_rate"],
            colorscale="RdYlGn_r",
            showscale=True,
            colorbar=dict(title="Churn (%)"),
            line=dict(width=1, color="rgba(0,0,0,0.3)"),
            sizemin=10,
        ),
        text=df_uni_plot["unidade"],
        textposition="top center",
        textfont=dict(size=10),
        hovertext=df_uni_plot.apply(
            lambda r: f'{r["unidade"]}<br>'
                      f'Contratos: {int(r["contratos"]):,}<br>'
                      f'Churn: {r["churn_rate"]}%<br>'
                      f'SAC: {int(r["com_sac"])} ({r["pct_com_sac"]}%)<br>'
                      f'Cancelamentos: {int(r["com_cancelamento"])}',
            axis=1
        ),
        hoverinfo="text",
    ))
    fig_uni.update_layout(
        title="Unidades: % com SAC vs Churn",
        xaxis_title="% dos contratos com ticket no SAC",
        yaxis_title="Churn (%)",
        height=500,
    )
    st.plotly_chart(fig_uni, use_container_width=True)

    st.dataframe(
        df_uni.sort_values("churn_rate", ascending=False).rename(columns={
            "unidade": "Unidade", "contratos": "Contratos",
            "churners": "Churners", "churn_rate": "Churn (%)",
            "com_sac": "Tickets SAC", "pct_com_sac": "% com SAC",
            "com_cancelamento": "Cancelamentos",
        }),
        hide_index=True, use_container_width=True,
    )


# ═══════════════════════════════════════════════════════════════════
# TAB 6: INSIGHTS
# ═══════════════════════════════════════════════════════════════════
with tab_sinais:
    st.markdown("### O que o cruzamento SAC × Churn revela")

    st.markdown("---")
    st.markdown("#### 1. O SAC protege — quem e atendido churneia menos")
    st.markdown(f"""
    Pacientes que ligaram pro SAC por problemas (sem pedir cancelamento) tem
    **{churn_outros}% de churn** — **{churn_sem - churn_outros:.1f} p.p. abaixo** da base
    ({churn_sem}%). Quem tem problema e e ouvido, fica.
    """)

    st.markdown("---")
    st.markdown("#### 2. A retencao funciona, mas e limitada")
    st.markdown(f"""
    De {n_cancel:,} que pediram cancelamento, **{retidos_cancel:,} ({taxa_retencao}%)
    foram retidos**. Nao e a maioria, mas sao {retidos_cancel:,} contratos salvos.
    A retencao e mais eficaz quando o paciente liga **antes** do vencimento.
    """)

    st.markdown("---")
    st.markdown("#### 3. Dois sinais que protegem contra o churn")

    col1, col2 = st.columns(2)
    with col1:
        dep_exc = df_dep[df_dep["tipo_dependente"].str.contains("exclusao")]
        if not dep_exc.empty:
            st.success(f"""
            **Exclusao de dependente: {dep_exc.iloc[0]['churn_rate']}% de churn**

            Muito abaixo da base. Quem exclui dependente esta **gerenciando o plano**,
            nao saindo. Provavelmente removendo alguem que nao usa pra manter
            a assinatura com custo menor.

            {int(dep_exc.iloc[0]['contratos'])} contratos
            """)

    with col2:
        integ = df_mot[df_mot["categoria"].str.contains("Integracao", case=False)]
        if not integ.empty:
            st.success(f"""
            **Integracao/Ativacao resolvida: {integ.iloc[0]['churn_rate']}% de churn**

            Paciente pagou, sistema falhou, SAC resolveu — e o paciente **ficou**.
            O atendimento funciona como rede de seguranca. Sem ele, esse churn
            seria muito maior.

            {int(integ.iloc[0]['contratos'])} contratos
            """)

    st.markdown("---")
    st.markdown("#### 4. O timing do cancelamento importa")

    antes_cancel = df_tim[
        (df_tim["tipo_contato"] == "So cancelamento") &
        (df_tim["janela"].str.contains("antes"))
    ]
    depois_cancel = df_tim[
        (df_tim["tipo_contato"] == "So cancelamento") &
        (df_tim["janela"].str.contains("depois"))
    ]

    if not antes_cancel.empty and not depois_cancel.empty:
        churn_antes = round(
            100 * antes_cancel["churners"].sum() / antes_cancel["contratos"].sum(), 1
        )
        churn_depois = round(
            100 * depois_cancel["churners"].sum() / depois_cancel["contratos"].sum(), 1
        )

        st.markdown(f"""
        | Quando pediu cancelamento | Churn | Leitura |
        |---|---|---|
        | **Antes** do vencimento | **{churn_antes}%** | Pediu antecipadamente — mais facil de reter |
        | **Depois** do vencimento | **{churn_depois}%** | Descobriu a cobranca — maioria cancela |

        A janela de retencao esta **antes do vencimento**. Depois que a cobranca passa,
        o paciente liga indignado e a chance de reter cai drasticamente.
        """)

    st.markdown("---")
    st.markdown("#### 5. Reincidentes")

    if not df_rei.empty:
        fig_rei = go.Figure()
        fig_rei.add_trace(go.Bar(
            x=df_rei["tickets"].astype(str),
            y=df_rei["churn_rate"],
            marker_color=["#f39c12", "#e67e22", "#c0392b"][:len(df_rei)],
            text=df_rei.apply(
                lambda r: f'{r["churn_rate"]}%\n({int(r["pacientes"])} pac.)', axis=1
            ),
            textposition="outside",
        ))
        fig_rei.add_hline(y=churn_sem, line_dash="dash", line_color="gray",
                          annotation_text=f"Base: {churn_sem}%")
        fig_rei.update_layout(
            title="Churn por numero de tickets do paciente",
            xaxis_title="Tickets no SAC",
            yaxis_title="Churn (%)",
            height=350,
            yaxis=dict(range=[0, max(df_rei["churn_rate"]) + 10]),
        )
        st.plotly_chart(fig_rei, use_container_width=True)

        st.caption(
            "Reincidentes tem churn levemente abaixo da base — quem liga mais vezes "
            "esta engajado com o plano, nao desistindo."
        )

    st.markdown("---")
    st.markdown("#### 6. Conexao com a pesquisa qualitativa")

    agend = df_mot[df_mot["categoria"].str.contains("Agendamento", case=False)]
    integ = df_mot[df_mot["categoria"].str.contains("Integracao", case=False)]
    nao_sabia = df_can[df_can["motivo_cancelamento"] == "Não sabia da renovação"]
    nao_usa = df_can[df_can["motivo_cancelamento"] == "Não faz uso dos beneficios"]

    st.markdown(f"""
    | Driver da pesquisa | O que o SAC mostra |
    |---|---|
    | Demora no agendamento (#1) | {int(agend.iloc[0]['contratos']) if not agend.empty else '?'} tickets, churn {agend.iloc[0]['churn_rate'] if not agend.empty else '?'}% — **abaixo da base**, SAC ajuda |
    | Promessa nao cumprida (#3) | {int(integ.iloc[0]['contratos']) if not integ.empty else '?'} tickets de integracao, churn {integ.iloc[0]['churn_rate'] if not integ.empty else '?'}% — **SAC resolve e retém** |
    | Falha de comunicacao (#12) | {int(nao_sabia.iloc[0]['contratos']) if not nao_sabia.empty else '?'} cancelamentos por "nao sabia", churn {nao_sabia.iloc[0]['churn_rate'] if not nao_sabia.empty else '?'}% |
    | Nao faz uso (#14) | {int(nao_usa.iloc[0]['contratos']) if not nao_usa.empty else '?'} cancelamentos, churn {nao_usa.iloc[0]['churn_rate'] if not nao_usa.empty else '?'}% |

    **O achado central:** o SAC nao e so custo operacional — e uma **ferramenta de retencao**.
    Pacientes atendidos por problemas tem 6 p.p. menos churn que a base.
    O desafio e levar esse efeito protetor pros 95% que nao ligam.
    """)
