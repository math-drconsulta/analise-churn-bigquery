"""
Pagina 15 — Experiencia do Paciente × Churn
=============================================
Dados de fat_atendimento: NPS, tempos de espera, rotatividade de medicos.
Mostra como a experiencia real na clinica se relaciona com o churn.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(page_title="Experiencia × Churn", page_icon="🏥", layout="wide")
st.title("🏥 Experiencia do Paciente × Churn")
st.caption(
    "Dados reais de atendimento: NPS, notas, tempos de espera e rotatividade de medicos. "
    "Fonte: fat_atendimento (DATA_LAKE_GOLD)"
)


# ═══════════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════════
@st.cache_data
def load_experiencia():
    return pd.read_csv("results/features_experiencia.csv")

@st.cache_data
def load_tempos():
    return pd.read_csv("results/tempos_jornada.csv")


try:
    df_exp = load_experiencia()
    df_tmp = load_tempos()
except FileNotFoundError as e:
    st.error(f"CSV nao encontrado: {e}")
    st.stop()

df_exp["churn"] = (df_exp["churn_sn"] == "S").astype(int)
df_tmp["churn"] = (df_tmp["churn_sn"] == "S").astype(int)

total = len(df_exp)
churn_global = round(100 * df_exp["churn"].mean(), 1)
com_atend = (df_exp["qtd_atendimentos"] > 0).sum()
com_nps = (df_exp["qtd_com_nps"] > 0).sum()


# ═══════════════════════════════════════════════════════════════════
# HEADER KPIs
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Contratos analisados", f"{total:,}")
k2.metric("Churn global", f"{churn_global}%")
k3.metric("Com atendimento registrado", f"{com_atend:,}",
          delta=f"{100*com_atend/total:.0f}%", delta_color="off")
k4.metric("Com NPS preenchido", f"{com_nps:,}",
          delta=f"{100*com_nps/total:.0f}%", delta_color="off")


# ═══════════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════════
tab_nps, tab_notas, tab_tempos, tab_rotatividade, tab_jornada, tab_resumo = st.tabs([
    "⭐ NPS",
    "👨‍⚕️ Notas (Medico/Atendimento)",
    "⏱️ Tempos de Espera",
    "🔄 Rotatividade de Medicos",
    "🚶 Jornada na Clinica",
    "💡 Resumo",
])


# ═══════════════════════════════════════════════════════════════════
# TAB 1: NPS
# ═══════════════════════════════════════════════════════════════════
with tab_nps:
    st.markdown("### NPS e Churn")
    st.markdown(f"""
    {com_nps:,} contratos tem NPS preenchido ({100*com_nps/total:.1f}% da base).
    A cobertura e parcial, mas o sinal e forte: **detratores churneiam 8.9 p.p.
    a mais que promotores**.
    """)

    # NPS por faixa
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Por faixa NPS (promotor/neutro/detrator)")
        faixa_order = ["detrator", "neutro", "promotor", "sem_nps"]
        faixa_colors = {"detrator": "#c0392b", "neutro": "#f39c12", "promotor": "#27ae60", "sem_nps": "#95a5a6"}

        grp = df_exp.groupby("faixa_nps").agg(
            n=("churn", "count"), ch=("churn", "sum")
        ).reset_index()
        grp["cr"] = (100 * grp["ch"] / grp["n"]).round(1)
        grp["faixa_nps"] = pd.Categorical(grp["faixa_nps"], categories=faixa_order, ordered=True)
        grp = grp.sort_values("faixa_nps")

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=grp["faixa_nps"].astype(str),
            y=grp["cr"],
            marker_color=[faixa_colors.get(f, "#3498db") for f in grp["faixa_nps"]],
            text=grp.apply(lambda r: f'{r["cr"]}%<br>({int(r["n"]):,})', axis=1),
            textposition="outside", textfont=dict(size=12),
        ))
        fig.add_hline(y=churn_global, line_dash="dash", line_color="gray",
                      annotation_text=f"Base: {churn_global}%")
        fig.update_layout(
            yaxis_title="Churn (%)", height=400,
            yaxis=dict(range=[0, grp["cr"].max() + 8]),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("#### Por nota NPS (0-10)")
        nps_df = df_exp[df_exp["qtd_com_nps"] > 0].copy()
        if len(nps_df) > 0:
            nps_df["faixa_nota"] = pd.cut(
                nps_df["nps_medio"], bins=[-1, 5, 7, 8, 9, 10.1],
                labels=["0-5", "6-7", "8", "9", "10"]
            )
            grp_n = nps_df.groupby("faixa_nota", observed=True).agg(
                n=("churn", "count"), ch=("churn", "sum")
            ).reset_index()
            grp_n["cr"] = (100 * grp_n["ch"] / grp_n["n"]).round(1)

            fig_n = go.Figure()
            fig_n.add_trace(go.Bar(
                x=grp_n["faixa_nota"].astype(str),
                y=grp_n["cr"],
                marker_color=["#c0392b", "#e67e22", "#f39c12", "#2ecc71", "#27ae60"],
                text=grp_n.apply(lambda r: f'{r["cr"]}%<br>({int(r["n"]):,})', axis=1),
                textposition="outside", textfont=dict(size=12),
            ))
            fig_n.update_layout(
                yaxis_title="Churn (%)", height=400,
                yaxis=dict(range=[0, grp_n["cr"].max() + 8]),
            )
            st.plotly_chart(fig_n, use_container_width=True)

    st.markdown(f"""
    **Leitura:** NPS 0-5 (detratores) tem **59.0% de churn** vs NPS 9-10 (promotores)
    com **50-51%**. O spread de ~9 p.p. e significativo e confirma que a experiencia
    percebida impacta diretamente a retencao.

    **Limitacao:** apenas {100*com_nps/total:.0f}% dos contratos tem NPS. Para os outros
    {100 - 100*com_nps/total:.0f}%, nao temos essa informacao.
    """)


# ═══════════════════════════════════════════════════════════════════
# TAB 2: NOTAS MEDICO E ATENDIMENTO
# ═══════════════════════════════════════════════════════════════════
with tab_notas:
    st.markdown("### Notas do Medico e do Atendimento × Churn")

    nota_df = df_exp[df_exp["nota_medico_media"].notna()].copy()

    if len(nota_df) > 0:
        col1, col2 = st.columns(2)

        for col_area, col_nota, titulo, cor_map in [
            (col1, "nota_medico_media", "Nota do Medico (1-5)",
             ["#c0392b", "#e67e22", "#f39c12", "#27ae60"]),
            (col2, "nota_atendimento_media", "Nota do Atendimento (1-5)",
             ["#c0392b", "#e67e22", "#f39c12", "#27ae60"]),
        ]:
            with col_area:
                st.markdown(f"#### {titulo}")
                sub = df_exp[df_exp[col_nota].notna()].copy()
                sub["faixa"] = pd.cut(sub[col_nota], bins=[-0.1, 2, 3, 4, 5.1], labels=["1-2", "3", "4", "5"])

                grp = sub.groupby("faixa", observed=True).agg(
                    n=("churn", "count"), ch=("churn", "sum")
                ).reset_index()
                grp["cr"] = (100 * grp["ch"] / grp["n"]).round(1)

                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=grp["faixa"].astype(str), y=grp["cr"],
                    marker_color=cor_map[:len(grp)],
                    text=grp.apply(lambda r: f'{r["cr"]}%<br>({int(r["n"]):,})', axis=1),
                    textposition="outside", textfont=dict(size=12),
                ))
                fig.add_hline(y=churn_global, line_dash="dash", line_color="gray")
                fig.update_layout(
                    yaxis_title="Churn (%)", height=380,
                    yaxis=dict(range=[0, grp["cr"].max() + 8]),
                )
                st.plotly_chart(fig, use_container_width=True)

        st.markdown(f"""
        **Nota medico:** quem deu nota 1-2 tem **60.2% de churn** vs nota 5 com **51.8%**
        (spread de 8.4 p.p.).

        **Nota atendimento:** nota 1-2 = **60.8%** vs nota 5 = **51.8%** (spread de 9.0 p.p.).

        As notas baixas sao sinais claros de insatisfacao que precedem o churn.
        """)


# ═══════════════════════════════════════════════════════════════════
# TAB 3: TEMPOS DE ESPERA
# ═══════════════════════════════════════════════════════════════════
with tab_tempos:
    st.markdown("### Tempos de Espera × Churn")
    st.markdown("""
    A pesquisa qualitativa apontou **demora e espera** como driver #1 de churn.
    Mas os dados revelam algo contra-intuitivo: **quem espera menos churneia mais**.
    """)

    st.markdown("#### O paradoxo da espera")

    # Espera senha ate consulta — sem controle vs controlado
    sub = df_tmp[df_tmp["espera_senha_ate_consulta_medio"].notna() &
                 (df_tmp["espera_senha_ate_consulta_medio"] > 0)].copy()
    sub["espera_min"] = sub["espera_senha_ate_consulta_medio"] / 60
    sub["faixa"] = pd.cut(
        sub["espera_min"], bins=[-1, 10, 20, 30, 45, 60, 999],
        labels=["<10min", "10-20min", "20-30min", "30-45min", "45-60min", "60min+"]
    )

    ciclo_sel = st.radio(
        "Controlar por ciclo:", options=["Todos", "1o contrato", "2o+ contrato"],
        horizontal=True, key="tempo_ciclo"
    )

    if ciclo_sel == "1o contrato":
        sub_plot = sub[sub["ciclo"] == "1o"]
        titulo_ciclo = "1o contrato"
    elif ciclo_sel == "2o+ contrato":
        sub_plot = sub[sub["ciclo"] == "2o+"]
        titulo_ciclo = "2o+ contrato"
    else:
        sub_plot = sub
        titulo_ciclo = "Todos"

    grp = sub_plot.groupby("faixa", observed=True).agg(
        n=("churn", "count"), ch=("churn", "sum")
    ).reset_index()
    grp["cr"] = (100 * grp["ch"] / grp["n"]).round(1)
    churn_sub = round(100 * sub_plot["churn"].mean(), 1)

    fig_esp = go.Figure()
    fig_esp.add_trace(go.Bar(
        x=grp["faixa"].astype(str), y=grp["cr"],
        marker_color=[
            "#c0392b" if cr > churn_sub + 2 else "#f39c12" if cr > churn_sub
            else "#27ae60"
            for cr in grp["cr"]
        ],
        text=grp.apply(lambda r: f'{r["cr"]}%<br>({int(r["n"]):,})', axis=1),
        textposition="outside", textfont=dict(size=12),
    ))
    fig_esp.add_hline(y=churn_sub, line_dash="dash", line_color="gray",
                      annotation_text=f"Media {titulo_ciclo}: {churn_sub}%")
    fig_esp.update_layout(
        title=f"Espera real (senha → consulta) — {titulo_ciclo}",
        xaxis_title="Tempo de espera",
        yaxis_title="Churn (%)", height=420,
        yaxis=dict(range=[0, grp["cr"].max() + 8]),
    )
    st.plotly_chart(fig_esp, use_container_width=True)

    # Spread
    spread = round(grp["cr"].max() - grp["cr"].min(), 1)
    st.markdown(f"**Spread: {spread} p.p.** entre a faixa de menor e maior churn.")

    st.markdown("""
    ---
    #### Por que quem espera menos churneia mais?

    Esse paradoxo persiste **mesmo controlando por ciclo** — nao e confounding.
    A explicacao mais provavel:

    **Tempo na clinica e proxy de engajamento.** Quem passa mais tempo:
    - Precisa do servico (necessidade real)
    - Interage com a equipe (recepcao, triagem, medico)
    - Cria vinculo com o atendimento

    Quem entra e sai rapido pode ser:
    - Teleconsulta (espera zero, menos vinculo)
    - Visita sem engajamento real
    - Paciente que nao criou relacao com a clinica

    A pesquisa quali esta certa que espera longa **frustra** — mas quem
    aguenta a espera e fica e quem **valoriza** o servico o suficiente
    pra renovar.
    """)

    # Detalhamento por etapa
    st.markdown("---")
    st.markdown("#### Detalhamento por etapa da jornada")

    etapas = [
        ("tme_recepcao_medio", "TME Recepcao\n(espera pra balcao)"),
        ("tme_preconsulta_medio", "TME Pre-consulta\n(espera pra triagem)"),
        ("tme_consulta_medio", "TME Consulta\n(espera pro medico)"),
        ("tma_consulta_medio", "TMA Consulta\n(tempo com medico)"),
    ]

    medians = []
    for col, label in etapas:
        vals = df_tmp[col].dropna()
        vals = vals[vals > 0]
        if len(vals) > 0:
            medians.append({"Etapa": label, "Mediana (min)": round(vals.median() / 60, 1),
                           "Media (min)": round(vals.mean() / 60, 1),
                           "Registros": len(vals)})

    if medians:
        st.dataframe(pd.DataFrame(medians), hide_index=True, use_container_width=True)

        st.markdown("""
        A etapa com **maior espera** e a consulta (mediana ~21 min esperando
        pro medico). A recepcao e rapida (~5 min) e a triagem intermediaria (~6 min).
        """)


# ═══════════════════════════════════════════════════════════════════
# TAB 4: ROTATIVIDADE DE MEDICOS
# ═══════════════════════════════════════════════════════════════════
with tab_rotatividade:
    st.markdown("### Rotatividade de Medicos × Churn")
    st.markdown("""
    A pesquisa qualitativa apontou **trocas frequentes de profissionais** como
    driver #7 de churn. Os dados confirmam: e a feature de experiencia
    mais forte que encontramos.
    """)

    # Medicos por especialidade
    prof_df = df_exp[df_exp["qtd_atendimentos"] > 0].copy()
    prof_df["prof_por_esp"] = prof_df["qtd_profissionais"] / prof_df["qtd_especialidades"].clip(lower=1)
    prof_df["faixa_prof"] = pd.cut(
        prof_df["prof_por_esp"], bins=[-0.1, 1, 1.5, 2, 99],
        labels=["1 med/esp", "1-1.5 med/esp", "1.5-2 med/esp", "2+ med/esp"]
    )

    col1, col2 = st.columns([2, 1])

    with col1:
        grp = prof_df.groupby("faixa_prof", observed=True).agg(
            n=("churn", "count"), ch=("churn", "sum")
        ).reset_index()
        grp["cr"] = (100 * grp["ch"] / grp["n"]).round(1)

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=grp["faixa_prof"].astype(str), y=grp["cr"],
            marker_color=["#27ae60", "#f39c12", "#e67e22", "#c0392b"],
            text=grp.apply(lambda r: f'{r["cr"]}%<br>({int(r["n"]):,})', axis=1),
            textposition="outside", textfont=dict(size=13),
        ))
        fig.add_hline(y=churn_global, line_dash="dash", line_color="gray",
                      annotation_text=f"Base: {churn_global}%")
        fig.update_layout(
            title="Churn por rotatividade de medicos",
            xaxis_title="Medicos por especialidade visitada",
            yaxis_title="Churn (%)", height=420,
            yaxis=dict(range=[0, grp["cr"].max() + 8]),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        spread = round(grp["cr"].max() - grp["cr"].min(), 1)
        st.metric("Spread", f"{spread} p.p.")
        st.metric("1 medico/especialidade", f'{grp[grp["faixa_prof"]=="1 med/esp"]["cr"].values[0]}%')
        st.metric("2+ medicos/especialidade",
                  f'{grp[grp["faixa_prof"]=="2+ med/esp"]["cr"].values[0]}%',
                  delta=f'+{grp[grp["faixa_prof"]=="2+ med/esp"]["cr"].values[0] - grp[grp["faixa_prof"]=="1 med/esp"]["cr"].values[0]:.1f} p.p.',
                  delta_color="inverse")

    st.markdown(f"""
    **Pacientes que viram 2+ medicos diferentes na mesma especialidade tem
    {grp[grp['faixa_prof']=='2+ med/esp']['cr'].values[0]}% de churn** — {spread} p.p.
    acima de quem teve continuidade com 1 medico.

    Isso confirma o driver #7 da pesquisa quali: **trocas frequentes de profissionais
    dificultam a continuidade do tratamento** e o paciente precisa repetir historico.
    """)

    # Flag rotatividade vs continuidade
    st.markdown("---")
    st.markdown("#### Rotatividade vs Continuidade")

    grp_flag = df_exp.groupby("padrao_profissional").agg(
        n=("churn", "count"), ch=("churn", "sum")
    ).reset_index()
    grp_flag["cr"] = (100 * grp_flag["ch"] / grp_flag["n"]).round(1)

    for _, r in grp_flag.sort_values("cr", ascending=False).iterrows():
        cor = "#c0392b" if r["cr"] > churn_global else "#27ae60"
        st.markdown(
            f"- **{r['padrao_profissional'].title()}**: {r['cr']}% churn "
            f"({int(r['n']):,} contratos)"
        )


# ═══════════════════════════════════════════════════════════════════
# TAB 5: JORNADA NA CLINICA
# ═══════════════════════════════════════════════════════════════════
with tab_jornada:
    st.markdown("### A Jornada do Paciente na Clinica")
    st.markdown("""
    O atendimento tem 4 etapas. Cada uma tem tempo de **espera** (TME)
    e tempo de **atendimento** (TMA). Abaixo mostramos a jornada tipica
    e onde o paciente perde mais tempo.
    """)

    # Jornada visual
    etapas_data = []
    for col_tme, col_tma, nome in [
        ("tme_recepcao_medio", "tma_recepcao_medio", "Recepcao"),
        ("tme_preconsulta_medio", "tma_preconsulta_medio", "Pre-consulta (triagem)"),
        ("tme_consulta_medio", "tma_consulta_medio", "Consulta"),
        (None, "tma_posconsulta_medio", "Pos-consulta"),
    ]:
        tme = df_tmp[col_tme].dropna() if col_tme else pd.Series()
        tme = tme[tme > 0] if len(tme) > 0 else tme
        tma = df_tmp[col_tma].dropna()
        tma = tma[tma > 0]

        etapas_data.append({
            "Etapa": nome,
            "Espera mediana (min)": round(tme.median() / 60, 1) if len(tme) > 0 else 0,
            "Atendimento mediana (min)": round(tma.median() / 60, 1) if len(tma) > 0 else 0,
        })

    df_etapas = pd.DataFrame(etapas_data)

    fig_jornada = go.Figure()
    fig_jornada.add_trace(go.Bar(
        x=df_etapas["Etapa"], y=df_etapas["Espera mediana (min)"],
        name="Espera (TME)", marker_color="#e74c3c",
    ))
    fig_jornada.add_trace(go.Bar(
        x=df_etapas["Etapa"], y=df_etapas["Atendimento mediana (min)"],
        name="Atendimento (TMA)", marker_color="#3498db",
    ))
    fig_jornada.update_layout(
        barmode="stack", title="Jornada tipica do paciente (medianas em minutos)",
        yaxis_title="Minutos", height=400,
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_jornada, use_container_width=True)

    st.dataframe(df_etapas, hide_index=True, use_container_width=True)

    # Espera total
    espera_total = df_etapas["Espera mediana (min)"].sum()
    atend_total = df_etapas["Atendimento mediana (min)"].sum()
    total_jornada = espera_total + atend_total

    col1, col2, col3 = st.columns(3)
    col1.metric("Espera total (mediana)", f"{espera_total:.0f} min")
    col2.metric("Atendimento total", f"{atend_total:.0f} min")
    col3.metric("Jornada completa", f"{total_jornada:.0f} min")

    st.markdown(f"""
    O paciente passa em media **{espera_total:.0f} minutos esperando** e
    **{atend_total:.0f} minutos sendo atendido**. A maior espera e pra
    entrar no medico (~21 min de mediana). A jornada completa leva
    ~{total_jornada:.0f} minutos.
    """)


# ═══════════════════════════════════════════════════════════════════
# TAB 6: RESUMO
# ═══════════════════════════════════════════════════════════════════
with tab_resumo:
    st.markdown("### O que a experiencia do paciente revela sobre o churn")

    st.markdown("---")
    st.markdown("#### Ranking das features de experiencia")

    ranking = [
        ("Medicos por especialidade", "10.0", "70%", "Mais rotatividade = mais churn", "Forte"),
        ("Nota do atendimento", "9.0", "12%", "Nota baixa = mais churn", "Forte (pouca cobertura)"),
        ("NPS numerico", "8.9", "12%", "Detrator = mais churn", "Forte (pouca cobertura)"),
        ("Nota do medico", "8.4", "12%", "Nota baixa = mais churn", "Forte (pouca cobertura)"),
        ("TME Total (espera)", "8.5*", "69%", "Menos espera = mais churn (paradoxo)", "Forte mas invertido"),
        ("Espera senha→consulta", "8.4*", "98%", "Menos espera = mais churn", "Forte mas invertido"),
        ("Tempo total na clinica", "5.1", "69%", "Menos tempo = mais churn", "Moderado"),
        ("TMA Consulta (tempo com medico)", "2.5", "98%", "Sem efeito claro", "Fraco"),
    ]

    st.dataframe(
        pd.DataFrame(ranking, columns=[
            "Feature", "Spread (p.p.)", "Cobertura", "Direcao", "Veredicto"
        ]),
        hide_index=True, use_container_width=True,
    )

    st.caption("* Spread controlado por ciclo (1o contrato)")

    st.markdown("---")
    st.markdown("#### Conexao com a pesquisa qualitativa")

    st.markdown(f"""
    | Driver quali | Feature disponivel | Resultado |
    |---|---|---|
    | #1 Demora no agendamento | TME (tempos de espera) | Paradoxal: espera curta = mais churn (proxy de engajamento) |
    | #5 Horarios nao respeitados | Espera senha→consulta | Mediana de 31 min. Quem espera mais churneia menos |
    | #6 Problemas no atendimento | NPS + Notas | **Confirmado: detratores +8-9 p.p. de churn** |
    | #7 Rotatividade de medicos | Medicos por especialidade | **Confirmado: 2+ medicos = +10 p.p. de churn** |
    | #8 Custo-beneficio | — | Nao mensuravel por esta tabela |

    **O dado mais surpreendente:** a espera na clinica nao prediz churn na direcao
    esperada. O que prediz e a **qualidade** do atendimento (NPS, notas) e a
    **continuidade** do cuidado (rotatividade de medicos).
    """)

    st.markdown("---")
    st.markdown("#### Implicacoes pro score de churn")

    st.markdown("""
    Tres features podem ser adicionadas ao score dinamico:

    1. **Rotatividade de medicos** (spread 10 p.p., cobertura 70%)
       - Paciente viu 2+ medicos na mesma especialidade → penalidade no score
       - Sinal forte e na direcao certa

    2. **NPS** (spread 9 p.p., cobertura 12%)
       - Detrator (NPS 0-5) → penalidade forte
       - Neutro (6-7) → penalidade leve
       - Promotor (9-10) → bonus
       - So se aplica a quem respondeu

    3. **Tempo na clinica como proxy de engajamento** (spread 8.5 p.p., cobertura 69%)
       - Visitas muito curtas (<10 min) → penalidade (pouco engajamento)
       - Visitas longas (30+ min) → bonus (paciente engajado)
       - Direcao invertida do esperado mas confirmada por controle

    Essas features adicionam uma camada que o score atual nao tem:
    **a experiencia real do paciente dentro da clinica**.
    """)
