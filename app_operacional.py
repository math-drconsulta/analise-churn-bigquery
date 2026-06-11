"""
App Operacional — Dashboard semanal do Growth
==============================================
Uso: streamlit run app_operacional.py

Alimentado por: results/operacional_contratos.csv
Score: score_dinamico.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from score_dinamico import calcular_score_dinamico

st.set_page_config(
    page_title="Churn · Operacional",
    page_icon="⚡",
    layout="wide",
)


# ═══════════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════════
@st.cache_data
def load_sac_por_cpf():
    """Carrega resumo SAC por CPF (se disponivel)."""
    import re
    try:
        df = pd.read_csv("results/sac_churn_resumo.csv", usecols=[
            "cpf", "teve_sac", "qtd_tickets", "tipo_contato", "categoria_principal"
        ])
        df = df.drop_duplicates("cpf")
        df = df.rename(columns={
            "teve_sac": "sac_teve_sac",
            "qtd_tickets": "sac_qtd_tickets",
            "tipo_contato": "sac_tipo_contato",
            "categoria_principal": "sac_categoria_principal",
        })
        return df
    except (FileNotFoundError, ValueError):
        return None


@st.cache_data
def load_data():
    df = pd.read_csv("results/operacional_contratos.csv")
    df["contract_due_date"] = pd.to_datetime(df["contract_due_date"])
    df["contract_register_date"] = pd.to_datetime(df["contract_register_date"])
    df["duracao"] = df["duracao"].astype(str)

    # Enriquecer com dados de SAC (se disponivel)
    sac = load_sac_por_cpf()
    if sac is not None:
        import re
        def normalizar_cpf(cpf):
            if pd.isna(cpf):
                return None
            cpf_limpo = re.sub(r"[^0-9]", "", str(cpf))
            return cpf_limpo if len(cpf_limpo) == 11 else None

        # A query operacional traz account_id mas nao CPF.
        # Tentar match via contratos_com_cpf.csv
        try:
            cpf_map = pd.read_csv("results/contratos_com_cpf.csv", usecols=["contract_id", "cpf"], dtype={"cpf": str})
            cpf_map["cpf"] = cpf_map["cpf"].apply(normalizar_cpf)
            cpf_map = cpf_map.dropna(subset=["cpf"]).drop_duplicates("contract_id")
            sac["cpf"] = sac["cpf"].astype(str)
            df = df.merge(cpf_map, on="contract_id", how="left")
            df["cpf"] = df["cpf"].fillna("").astype(str)
            df = df.merge(sac, on="cpf", how="left")
            n_match = df["sac_teve_sac"].fillna(0).astype(int).sum()
            print(f"SAC enriquecido: {n_match} contratos com dados de SAC")
        except FileNotFoundError:
            pass

    # Enriquecer com dados de experiencia (fat_atendimento, se disponivel)
    try:
        df_exp = pd.read_csv("results/features_experiencia.csv", usecols=[
            "contract_id", "qtd_profissionais", "qtd_especialidades",
            "nps_medio", "tempo_total_medio", "faixa_nps",
        ])
        df_exp = df_exp.drop_duplicates("contract_id")
        df_exp = df_exp.rename(columns={
            "qtd_profissionais": "exp_qtd_profissionais",
            "qtd_especialidades": "exp_qtd_especialidades",
            "nps_medio": "exp_nps_medio",
            "tempo_total_medio": "exp_tempo_total_medio",
            "faixa_nps": "exp_faixa_nps",
        })
        df = df.merge(df_exp, on="contract_id", how="left")
        n_exp = df["exp_qtd_profissionais"].notna().sum()
        print(f"Experiencia enriquecida: {n_exp} contratos com dados de fat_atendimento")
    except (FileNotFoundError, ValueError):
        pass

    # Aplicar score dinamico
    df = calcular_score_dinamico(df)
    return df


try:
    df = load_data()
except FileNotFoundError:
    st.error(
        "Arquivo `results/operacional_contratos.csv` nao encontrado.\n\n"
        "Rode a query `queries/operacional.sql` no BigQuery e salve o resultado."
    )
    st.stop()
except Exception as e:
    import traceback
    st.error(f"Erro ao carregar dados: {e}")
    st.code(traceback.format_exc())
    st.stop()


# ═══════════════════════════════════════════════════════════════════
# CORES E CONSTANTES
# ═══════════════════════════════════════════════════════════════════
CORES_RISCO = {
    "CRITICO": "#c0392b",
    "ALTO": "#e67e22",
    "MEDIO": "#f1c40f",
    "BAIXO": "#27ae60",
    "SEGURO": "#2980b9",
}
CORES_URGENCIA = {
    "CANCELOU": "#8b0000",
    "VENCIDO": "#c0392b",
    "URGENTE": "#e74c3c",
    "ATENCAO": "#f39c12",
    "ACOMPANHAR": "#3498db",
}


# ═══════════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════════
st.title("⚡ Painel Operacional — Churn")
st.caption("Contratos em risco · Atualizado semanalmente")

# Data dos dados
data_min = df["contract_due_date"].min().strftime("%d/%b")
data_max = df["contract_due_date"].max().strftime("%d/%b")
st.markdown(f"**Janela:** contratos vencendo de {data_min} a {data_max} · {len(df):,} contratos")

st.markdown("---")


# ═══════════════════════════════════════════════════════════════════
# KPIs TOPO
# ═══════════════════════════════════════════════════════════════════
total = len(df)
criticos = len(df[df["risco"] == "CRITICO"])
altos = len(df[df["risco"] == "ALTO"])
vencidos = len(df[df["urgencia"] == "VENCIDO"])
cancelaram = len(df[df["urgencia"] == "CANCELOU"])
sem_uso = len(df[df["consumiu"] == "N"])
com_falha = len(df[df["pgto_falhas_90d"] > 0])
score_medio = round(df["score_total"].mean())

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Total contratos", f"{total:,}")
k2.metric("Risco CRITICO + ALTO", f"{criticos + altos:,}",
          delta=f"{round(100*(criticos+altos)/total)}% do total",
          delta_color="inverse")
k3.metric("Ja vencidos (win-back)", f"{vencidos:,}")
k4.metric("Pediram cancelamento", f"{cancelaram:,}")
k5.metric("Nunca usaram o plano", f"{sem_uso:,}",
          delta=f"{round(100*sem_uso/total)}%", delta_color="inverse")
k6.metric("Com falha de pagamento", f"{com_falha:,}",
          delta=f"{round(100*com_falha/total)}%", delta_color="inverse")


# ═══════════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════════
tab_painel, tab_lista, tab_score, tab_export = st.tabs([
    "📊 Painel do Mes",
    "📋 Lista de Acao",
    "🎯 Score Dinamico",
    "📥 Exportar",
])


# ═══════════════════════════════════════════════════════════════════
# TAB 1: PAINEL DO MES
# ═══════════════════════════════════════════════════════════════════
with tab_painel:

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Distribuicao de Risco")
        risco_counts = df["risco"].value_counts().reindex(
            ["CRITICO", "ALTO", "MEDIO", "BAIXO", "SEGURO"], fill_value=0
        )
        fig_risco = go.Figure(data=[go.Pie(
            labels=risco_counts.index,
            values=risco_counts.values,
            hole=0.5,
            marker_colors=[CORES_RISCO[r] for r in risco_counts.index],
            textinfo="label+value+percent",
            textfont=dict(size=13),
        )])
        fig_risco.update_layout(
            height=380, showlegend=False,
            annotations=[dict(text=f"Score<br>medio<br>{score_medio}",
                              x=0.5, y=0.5, font_size=16, showarrow=False)],
        )
        st.plotly_chart(fig_risco, use_container_width=True)

    with col2:
        st.markdown("### Urgencia (timing)")
        urg_counts = df["urgencia"].value_counts().reindex(
            ["CANCELOU", "VENCIDO", "URGENTE", "ATENCAO", "ACOMPANHAR"], fill_value=0
        )
        fig_urg = go.Figure()
        fig_urg.add_trace(go.Bar(
            x=urg_counts.index,
            y=urg_counts.values,
            marker_color=[CORES_URGENCIA[u] for u in urg_counts.index],
            text=urg_counts.values,
            textposition="outside",
            textfont=dict(size=14),
        ))
        fig_urg.update_layout(
            height=380, yaxis_title="Contratos",
            yaxis=dict(range=[0, urg_counts.max() * 1.2]),
        )
        st.plotly_chart(fig_urg, use_container_width=True)

    # Timeline de vencimentos
    st.markdown("### Vencimentos por dia")

    venc_dia = df.groupby([df["contract_due_date"].dt.date, "risco"], observed=True).size().reset_index(name="n")
    venc_dia.columns = ["dia", "risco", "n"]
    venc_dia["dia"] = pd.to_datetime(venc_dia["dia"])

    fig_timeline = px.bar(
        venc_dia, x="dia", y="n", color="risco",
        color_discrete_map=CORES_RISCO,
        labels={"dia": "", "n": "Contratos", "risco": "Risco"},
    )
    hoje = pd.Timestamp.now()
    fig_timeline.add_shape(
        type="line", x0=hoje, x1=hoje, y0=0, y1=1, yref="paper",
        line=dict(dash="dash", color="black", width=2),
    )
    fig_timeline.add_annotation(
        x=hoje, y=1, yref="paper", text="Hoje",
        showarrow=False, font=dict(size=12), yanchor="bottom",
    )
    fig_timeline.update_layout(height=350, legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig_timeline, use_container_width=True)

    # Motivos de risco
    st.markdown("### Por que esses contratos estao em risco?")

    com_sac_sinal = int(df["score_sac"].lt(0).sum()) if "score_sac" in df.columns else 0

    motivos = {
        "Nunca usaram o plano": sem_uso,
        "Falha de pagamento (90d)": com_falha,
        "1o contrato": len(df[df["ciclo"] == "1o"]),
        "Sem dependentes": len(df[df["faixa_dependentes"] == "sem_dep"]),
        "Nao cronico": len(df[df["cronico"] == "N"]),
        "Pediram cancelamento": cancelaram,
        "Sinal SAC negativo": com_sac_sinal,
    }
    motivos_df = pd.DataFrame([
        {"Sinal": k, "Contratos": v, "% do total": round(100*v/total, 1)}
        for k, v in sorted(motivos.items(), key=lambda x: -x[1])
    ])

    fig_mot = go.Figure()
    fig_mot.add_trace(go.Bar(
        y=motivos_df["Sinal"].iloc[::-1],
        x=motivos_df["Contratos"].iloc[::-1],
        orientation="h",
        marker_color="#e74c3c",
        text=motivos_df.apply(
            lambda r: f'{int(r["Contratos"]):,} ({r["% do total"]}%)', axis=1
        ).iloc[::-1],
        textposition="outside",
    ))
    fig_mot.update_layout(height=300, margin=dict(l=20, r=100), yaxis=dict(automargin=True))
    st.plotly_chart(fig_mot, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
# TAB 2: LISTA DE ACAO
# ═══════════════════════════════════════════════════════════════════
with tab_lista:
    st.markdown("### Lista de Acao Priorizada")
    st.markdown("Filtrada por risco e urgencia. Cada linha = 1 contrato com acao sugerida.")

    # Filtros
    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    with col_f1:
        risco_filter = st.multiselect(
            "Risco:", options=["CRITICO", "ALTO", "MEDIO", "BAIXO", "SEGURO"],
            default=["CRITICO", "ALTO"], key="lista_risco"
        )
    with col_f2:
        urgencia_filter = st.multiselect(
            "Urgencia:", options=["CANCELOU", "VENCIDO", "URGENTE", "ATENCAO", "ACOMPANHAR"],
            default=["CANCELOU", "VENCIDO", "URGENTE", "ATENCAO"], key="lista_urg"
        )
    with col_f3:
        ciclo_filter = st.multiselect(
            "Ciclo:", options=df["ciclo"].unique().tolist(),
            default=df["ciclo"].unique().tolist(), key="lista_ciclo"
        )
    with col_f4:
        max_rows = st.number_input("Max linhas:", value=200, step=50, key="lista_max")

    # Aplicar filtros
    mask = (
        df["risco"].isin(risco_filter) &
        df["urgencia"].isin(urgencia_filter) &
        df["ciclo"].isin(ciclo_filter)
    )
    df_filtrado = df[mask].sort_values("score_total").head(max_rows)

    st.markdown(f"**{len(df_filtrado):,} contratos** na selecao atual")

    # Colunas pra exibir
    cols_exibir = [
        "contract_id", "risco", "score_total", "urgencia", "acao_sugerida",
        "dias_ate_vencimento", "ciclo", "duracao",
        "consumiu", "total_itens", "dias_sem_uso",
        "pgto_falhas_90d", "faixa_dependentes", "cronico", "perfil_idade",
    ]
    cols_presentes = [c for c in cols_exibir if c in df_filtrado.columns]

    rename_map = {
        "contract_id": "Contrato", "risco": "Risco", "score_total": "Score",
        "urgencia": "Urgencia", "acao_sugerida": "Acao Sugerida",
        "dias_ate_vencimento": "Dias p/ venc.", "ciclo": "Ciclo", "duracao": "Dur.",
        "consumiu": "Usou?", "total_itens": "Itens", "dias_sem_uso": "Dias s/ uso",
        "pgto_falhas_90d": "Falhas pgto", "faixa_dependentes": "Deps", "cronico": "Cron.",
        "perfil_idade": "Idade",
    }

    st.dataframe(
        df_filtrado[cols_presentes].rename(columns=rename_map),
        hide_index=True,
        use_container_width=True,
        height=500,
    )

    # Resumo das acoes
    st.markdown("---")
    st.markdown("### Resumo das Acoes")

    # Quebrar acoes compostas
    todas_acoes = []
    for acoes_str in df_filtrado["acao_sugerida"]:
        for acao in str(acoes_str).split(" + "):
            todas_acoes.append(acao.strip())

    acoes_count = pd.Series(todas_acoes).value_counts().reset_index()
    acoes_count.columns = ["Acao", "Contratos"]

    st.dataframe(acoes_count, hide_index=True, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
# TAB 3: SCORE DINAMICO
# ═══════════════════════════════════════════════════════════════════
with tab_score:
    st.markdown("### Como o Score Dinamico Funciona")

    st.markdown("""
    O score combina **quem o paciente e** (perfil) com **o que esta acontecendo** (comportamento):
    """)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        **Camada 1 — Perfil (estatico)**
        - Base: 700 pontos
        - 1o contrato: -120
        - Sem dependentes: -100
        - Jovem (ate 30): -80
        - Nao cronico: -60
        - Plano 12m: -50
        - Canal digital: -30

        **Camada 2 — Comportamento**
        - Nunca usou o plano: -100
        - Parou de usar (4+ meses): -60
        - Falha de pagamento grave: -80
        - Vence essa semana: -30
        - Pediu cancelamento: -200
        - Usou recentemente: +30
        - Muitos itens usados (5+): +50
        """)

    with col2:
        st.markdown("""
        **Camada 3 — SAC (corrigido v3)**
        - Excluiu dependente: +80 (ficam)
        - Integracao resolvida: +50 (SAC protege)
        - Reclamacao/agendamento: +10
        - Financeiro/estorno: -20
        - Pediu cancelamento: -80
        - Reincidente: +5 a +10 (engajamento)

        **Camada 4 — Experiencia (novo)**
        - NPS detrator (0-5): -60
        - NPS promotor (9-10): +40
        - Rotatividade alta (2+ med/esp): -80
        - Continuidade (1 med/esp): +20
        - Visita curta (<10min): -40
        - Visita longa (30min+): +30
        """)

    st.markdown("""
    **Score final** = Perfil + Comportamento + SAC + Experiencia (0 a 1000)

    O score agora tem **4 camadas**: quem a pessoa **e** (perfil), o que ela **faz**
    (uso/pagamento), o que ela **disse** (SAC) e o que ela **viveu** (NPS, rotatividade,
    engajamento na clinica). Dois pacientes identicos em perfil e uso podem ter scores
    diferentes se um deu NPS 10 e o outro deu NPS 3.
    """)

    # Distribuicao do score
    st.markdown("---")
    st.markdown("### Distribuicao do Score na Base Atual")

    fig_hist = go.Figure()
    for risco in ["CRITICO", "ALTO", "MEDIO", "BAIXO", "SEGURO"]:
        sub = df[df["risco"] == risco]
        if not sub.empty:
            fig_hist.add_trace(go.Histogram(
                x=sub["score_total"], name=risco,
                marker_color=CORES_RISCO[risco],
                opacity=0.7, nbinsx=30,
            ))
    fig_hist.update_layout(
        barmode="stack", height=400,
        xaxis_title="Score Dinamico", yaxis_title="Contratos",
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_hist, use_container_width=True)

    # Decomposicao media por faixa
    st.markdown("### Decomposicao Media do Score por Faixa")

    agg_dict = {
        "n": ("score_total", "count"),
        "score_medio": ("score_total", "mean"),
        "perfil": ("score_perfil", "mean"),
        "uso": ("score_uso", "mean"),
        "pgto": ("score_pgto", "mean"),
        "timing": ("score_timing", "mean"),
        "cancel": ("score_cancel", "mean"),
    }
    if "score_sac" in df.columns:
        agg_dict["sac"] = ("score_sac", "mean")
    if "score_exp" in df.columns:
        agg_dict["exp"] = ("score_exp", "mean")

    decomp = df.groupby("risco").agg(**agg_dict).reindex(
        ["CRITICO", "ALTO", "MEDIO", "BAIXO", "SEGURO"]
    ).reset_index()

    fig_decomp = go.Figure()
    componentes = [
        ("perfil", "Perfil (estatico)", "#3498db"),
        ("uso", "Uso do plano", "#e74c3c"),
        ("pgto", "Pagamento", "#f39c12"),
        ("timing", "Timing", "#9b59b6"),
        ("cancel", "Cancelamento", "#8b0000"),
    ]
    if "sac" in decomp.columns:
        componentes.append(("sac", "SAC", "#1abc9c"))
    if "exp" in decomp.columns:
        componentes.append(("exp", "Experiencia", "#e67e22"))
    for col, nome, cor in componentes:
        fig_decomp.add_trace(go.Bar(
            x=decomp["risco"], y=decomp[col].round(0),
            name=nome, marker_color=cor,
            text=decomp[col].apply(lambda v: f"{v:+.0f}"),
            textposition="inside",
        ))
    fig_decomp.update_layout(
        barmode="relative", height=420,
        yaxis_title="Pontos (media)",
        legend=dict(orientation="h", y=1.12),
        title="O que compoe o score de cada faixa",
    )
    st.plotly_chart(fig_decomp, use_container_width=True)

    st.markdown("""
    **Como ler:** nas faixas CRITICO e ALTO, a maior parte da penalidade vem
    do **perfil** (1o contrato, sem dependentes, jovem) e do **uso** (nunca usou
    ou parou de usar). Na faixa SEGURO, os sinais positivos (uso recente,
    pagamentos ok) somam pontos ao perfil ja favoravel.
    """)


# ═══════════════════════════════════════════════════════════════════
# TAB 4: EXPORTAR
# ═══════════════════════════════════════════════════════════════════
with tab_export:
    st.markdown("### Exportar Lista para CRM")
    st.markdown("Selecione o filtro e exporte como CSV para importar no CRM/ferramenta de acoes.")

    col1, col2 = st.columns(2)
    with col1:
        export_risco = st.multiselect(
            "Risco:", options=["CRITICO", "ALTO", "MEDIO", "BAIXO", "SEGURO"],
            default=["CRITICO", "ALTO"], key="export_risco"
        )
    with col2:
        export_urg = st.multiselect(
            "Urgencia:", options=["CANCELOU", "VENCIDO", "URGENTE", "ATENCAO", "ACOMPANHAR"],
            default=["CANCELOU", "VENCIDO", "URGENTE", "ATENCAO"], key="export_urg"
        )

    df_export = df[
        df["risco"].isin(export_risco) & df["urgencia"].isin(export_urg)
    ].sort_values("score_total")

    st.markdown(f"**{len(df_export):,} contratos** para exportar")

    # Preview
    st.dataframe(
        df_export[[
            "contract_id", "account_id", "risco", "score_total",
            "urgencia", "acao_sugerida", "dias_ate_vencimento",
            "ciclo", "duracao", "consumiu", "pgto_falhas_90d",
        ]].head(10).rename(columns={
            "contract_id": "Contrato", "account_id": "Conta",
            "risco": "Risco", "score_total": "Score",
            "urgencia": "Urgencia", "acao_sugerida": "Acao",
            "dias_ate_vencimento": "Dias p/ venc.",
            "ciclo": "Ciclo", "duracao": "Dur.",
            "consumiu": "Usou?", "pgto_falhas_90d": "Falhas pgto",
        }),
        hide_index=True, use_container_width=True,
    )

    # Botao de download
    csv_data = df_export.to_csv(index=False).encode("utf-8")
    st.download_button(
        label=f"Baixar CSV ({len(df_export):,} contratos)",
        data=csv_data,
        file_name="lista_acao_churn.csv",
        mime="text/csv",
    )

    st.caption(
        "O CSV inclui: contract_id, account_id, score, risco, urgencia, acao sugerida, "
        "dados demograficos e sinais comportamentais. Pronto pra importar no CRM."
    )
