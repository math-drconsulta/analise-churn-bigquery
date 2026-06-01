"""
Pagina 9 — Analise de Coorte & Retencao
========================================
Curvas de sobrevivencia por safra de registro e por perfil de risco.
Responde: "As safras recentes retêm melhor? Quanto tempo cada perfil sobrevive?"
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(page_title="Coorte & Retencao", page_icon="📈", layout="wide")
st.title("📈 Coorte & Retencao")
st.markdown(
    "Curvas de sobrevivencia por safra mensal e por perfil de risco. "
    "Mostra **quantos clientes cada safra reteve** ao longo dos ciclos de contrato."
)


# ═══════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════
@st.cache_data
def load_coorte():
    df = pd.read_csv("results/coorte_retencao.csv")
    df["duracao"] = df["duracao"].astype(str)
    return df


@st.cache_data
def load_sobrevivencia():
    df = pd.read_csv("results/sobrevivencia_perfil.csv")
    df["duracao"] = df["duracao"].astype(str)
    return df


tab1, tab2, tab3 = st.tabs([
    "📊 Heatmap de Coorte",
    "📉 Curvas de Sobrevivencia",
    "🎯 Perfis de Risco",
])


# ═══════════════════════════════════════════════════════════════════
# TAB 1: HEATMAP DE COORTE
# ═══════════════════════════════════════════════════════════════════
with tab1:
    try:
        df = load_coorte()
        df["coorte"] = pd.to_datetime(df["coorte"])

        st.markdown("### Heatmap de Retencao por Safra")
        st.markdown("""
        Cada linha e uma **safra mensal** (mes em que o cliente registrou o primeiro contrato).
        As colunas mostram o **ciclo do contrato** (1o, 2o, 3o...).
        A cor indica a **taxa de retencao** — mais verde = mais retencao.
        """)

        dur_sel = st.radio(
            "Duracao:", options=["6", "12"], index=1,
            format_func=lambda x: f"{x} meses", horizontal=True, key="coorte_dur"
        )

        df_dur = df[df["duracao"] == dur_sel].copy()

        if df_dur.empty:
            st.warning("Sem dados para a duracao selecionada.")
            st.stop()

        # Pivotar para heatmap: coorte × ciclo → retencao_rate
        pivot = df_dur.pivot_table(
            index="coorte", columns="ciclo_contrato",
            values="retencao_rate", aggfunc="mean"
        ).sort_index()

        # Limitar a ciclos com dados
        pivot = pivot.loc[:, pivot.notna().sum() >= 2]

        if pivot.empty:
            st.warning("Sem dados suficientes para o heatmap.")
        else:
            pivot.index = pivot.index.strftime("%Y-%m")

            # Tratar NaN para texto
            z_vals = pivot.values
            text_vals = []
            for row in z_vals:
                text_row = []
                for v in row:
                    text_row.append(f"{v:.1f}%" if not np.isnan(v) else "")
                text_vals.append(text_row)

            fig = go.Figure(data=go.Heatmap(
                z=z_vals,
                x=[f"Ciclo {c}" for c in pivot.columns],
                y=list(pivot.index),
                colorscale=[
                    [0, "#d73027"],
                    [0.3, "#fc8d59"],
                    [0.5, "#fee08b"],
                    [0.7, "#d9ef8b"],
                    [1.0, "#1a9850"],
                ],
                text=text_vals,
                texttemplate="%{text}",
                textfont=dict(size=12),
                hovertemplate="Safra: %{y}<br>%{x}<br>Retencao: %{z:.1f}%<extra></extra>",
                colorbar=dict(title="Retencao (%)"),
            ))
            fig.update_layout(
                title=f"Retencao por Coorte — Plano {dur_sel}m",
                xaxis_title="Ciclo do Contrato",
                yaxis_title="Safra de Registro",
                height=max(400, len(pivot) * 30 + 100),
                yaxis=dict(autorange="reversed"),
            )
            st.plotly_chart(fig, use_container_width=True)

            # KPIs
            st.markdown("---")
            st.markdown("### Evolucao das Safras")

            # Retencao media do 1o ciclo por safra
            if 1 in pivot.columns:
                col1, col2, col3 = st.columns(3)

                ret_1o = pivot[1].dropna()
                if len(ret_1o) >= 2:
                    ultima = ret_1o.iloc[-1]
                    primeira = ret_1o.iloc[0]
                    delta = ultima - primeira
                    col1.metric(
                        "Retencao 1o ciclo (safra mais recente)",
                        f"{ultima:.1f}%",
                        delta=f"{delta:+.1f} p.p. vs safra mais antiga",
                        delta_color="normal"
                    )

                media_geral = ret_1o.mean()
                col2.metric("Media geral 1o ciclo", f"{media_geral:.1f}%")

                melhor_safra = ret_1o.idxmax()
                col3.metric("Melhor safra", f"{melhor_safra}", delta=f"{ret_1o.max():.1f}%")

        # Volume por coorte
        st.markdown("---")
        st.markdown("### Volume de Clientes por Safra")

        vol = df_dur[df_dur["ciclo_contrato"] == 1].copy()
        if vol.empty:
            st.info("Sem dados de volume para o 1o ciclo.")
        else:
            vol["coorte_str"] = vol["coorte"].dt.strftime("%Y-%m")

            fig_vol = go.Figure()
            fig_vol.add_trace(go.Bar(
                x=vol["coorte_str"], y=vol["clientes"],
                marker_color="steelblue",
                text=vol["clientes"].apply(lambda v: f"{v:,}"),
                textposition="outside",
            ))
            fig_vol.update_layout(
                title="Clientes Novos por Safra (1o contrato)",
                xaxis_title="Safra", yaxis_title="Clientes",
                height=350,
            )
            st.plotly_chart(fig_vol, use_container_width=True)

    except FileNotFoundError:
        st.error("Arquivo `results/coorte_retencao.csv` nao encontrado. Rode a query IA-1A.")
    except Exception as e:
        st.error(f"Erro: {e}")


# ═══════════════════════════════════════════════════════════════════
# TAB 2: CURVAS DE SOBREVIVENCIA
# ═══════════════════════════════════════════════════════════════════
with tab2:
    try:
        df = load_coorte()
        df["coorte"] = pd.to_datetime(df["coorte"])

        st.markdown("### Curva de Sobrevivencia Agregada")
        st.markdown("""
        Mostra a **probabilidade de um cliente estar ativo** apos cada ciclo de contrato.
        A curva cai a cada ciclo — quanto mais rapido cai, pior a retencao.
        """)

        dur_sel = st.radio(
            "Duracao:", options=["6", "12"], index=1,
            format_func=lambda x: f"{x} meses", horizontal=True, key="surv_dur"
        )

        df_dur = df[df["duracao"] == dur_sel].copy()

        if df_dur.empty:
            st.warning("Sem dados para a duracao selecionada.")
        else:
            # Calcular sobrevivencia acumulada por ciclo
            surv = df_dur.groupby("ciclo_contrato").agg(
                contratos=("contratos", "sum"),
                churners=("churners", "sum"),
            ).reset_index()
            surv["churn_rate"] = surv["churners"] / surv["contratos"]
            surv["retencao"] = 1 - surv["churn_rate"]

            # Sobrevivencia acumulada (produto cumulativo)
            surv["sobrevivencia_acum"] = surv["retencao"].cumprod() * 100
            surv = pd.concat([
                pd.DataFrame({"ciclo_contrato": [0], "sobrevivencia_acum": [100.0]}),
                surv[["ciclo_contrato", "sobrevivencia_acum"]]
            ], ignore_index=True)

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=surv["ciclo_contrato"],
                y=surv["sobrevivencia_acum"],
                mode="lines+markers+text",
                line=dict(width=3, color="#2c3e50"),
                marker=dict(size=10),
                text=surv["sobrevivencia_acum"].apply(lambda v: f"{v:.1f}%"),
                textposition="top center",
                textfont=dict(size=12),
                fill="tozeroy",
                fillcolor="rgba(44, 62, 80, 0.1)",
            ))
            fig.update_layout(
                title=f"Curva de Sobrevivencia — Plano {dur_sel}m",
                xaxis_title="Ciclo do Contrato",
                yaxis_title="% Clientes Ativos",
                yaxis=dict(range=[0, 105]),
                height=400,
            )
            st.plotly_chart(fig, use_container_width=True)

            # Meia-vida
            meia_vida_row = surv[surv["sobrevivencia_acum"] <= 50]
            if len(meia_vida_row) > 0:
                ciclo_50 = meia_vida_row.iloc[0]["ciclo_contrato"]
                meses_50 = ciclo_50 * int(dur_sel)
                st.warning(
                    f"**Meia-vida do cliente:** no ciclo **{int(ciclo_50)}** "
                    f"(~{int(meses_50)} meses), menos de 50% dos clientes permanecem ativos."
                )
            else:
                st.info("A meia-vida nao foi atingida nos ciclos disponiveis — sinal positivo de retencao.")

            # Tabela
            st.dataframe(
                surv.rename(columns={
                    "ciclo_contrato": "Ciclo", "sobrevivencia_acum": "Sobrevivencia (%)"
                }),
                hide_index=True, use_container_width=True
            )

    except FileNotFoundError:
        st.error("Arquivo `results/coorte_retencao.csv` nao encontrado.")
    except Exception as e:
        st.error(f"Erro: {e}")


# ═══════════════════════════════════════════════════════════════════
# TAB 3: PERFIS DE RISCO — SOBREVIVENCIA POR SEGMENTO
# ═══════════════════════════════════════════════════════════════════
with tab3:
    try:
        df = load_sobrevivencia()

        st.markdown("### Curvas de Sobrevivencia por Perfil de Risco")
        st.markdown("""
        Comparamos a velocidade de evasao entre perfis. Perfis com curva mais
        ingreme perdem clientes mais rapido — sao prioridade para acoes de retencao.
        """)

        dur_sel = st.radio(
            "Duracao:", options=["6", "12"], index=1,
            format_func=lambda x: f"{x} meses", horizontal=True, key="perf_dur"
        )

        dim_sel = st.selectbox(
            "Segmentar por:",
            options=["perfil_idade", "cronico", "tem_dependente"],
            format_func=lambda x: {
                "perfil_idade": "Faixa Etaria",
                "cronico": "Cronico (S/N)",
                "tem_dependente": "Tem Dependente"
            }[x],
            key="perf_dim"
        )

        df_dur = df[df["duracao"] == dur_sel].copy()

        if df_dur.empty:
            st.warning("Sem dados para a duracao selecionada.")
        else:
            # Agrupar por dimensao selecionada e ciclo
            agg = df_dur.groupby([dim_sel, "ciclo"]).agg(
                contratos=("contratos", "sum"),
                renovaram=("renovaram", "sum"),
                churners=("churners", "sum"),
            ).reset_index()
            agg["retencao"] = agg["renovaram"] / agg["contratos"]

            fig = go.Figure()
            colors = px.colors.qualitative.Set2

            for i, (seg, grp) in enumerate(agg.groupby(dim_sel)):
                grp = grp.sort_values("ciclo")
                grp["sobrev_acum"] = grp["retencao"].cumprod() * 100

                # Adicionar ponto zero
                grp_full = pd.concat([
                    pd.DataFrame({"ciclo": [0], "sobrev_acum": [100.0]}),
                    grp[["ciclo", "sobrev_acum"]]
                ], ignore_index=True)

                fig.add_trace(go.Scatter(
                    x=grp_full["ciclo"],
                    y=grp_full["sobrev_acum"],
                    mode="lines+markers",
                    name=str(seg),
                    line=dict(width=3, color=colors[i % len(colors)]),
                    marker=dict(size=8),
                ))

            fig.update_layout(
                title=f"Sobrevivencia por {dim_sel.replace('_', ' ').title()} — Plano {dur_sel}m",
                xaxis_title="Ciclo do Contrato",
                yaxis_title="% Clientes Ativos",
                yaxis=dict(range=[0, 105]),
                height=450,
                legend=dict(orientation="h", y=-0.15),
            )
            st.plotly_chart(fig, use_container_width=True)

            # Tabela comparativa: churn no 1o ciclo por perfil
            st.markdown("---")
            st.markdown("### Churn no 1o Ciclo por Perfil")

            ciclo1 = df_dur[df_dur["ciclo"] == 1].groupby(dim_sel).agg(
                contratos=("contratos", "sum"),
                churners=("churners", "sum"),
            ).reset_index()
            ciclo1["churn_rate"] = round(100 * ciclo1["churners"] / ciclo1["contratos"], 1)
            ciclo1 = ciclo1.sort_values("churn_rate", ascending=False)

            if not ciclo1.empty:
                fig_bar = go.Figure()
                fig_bar.add_trace(go.Bar(
                    x=ciclo1[dim_sel],
                    y=ciclo1["churn_rate"],
                    marker_color=[
                        "#c0392b" if cr > 55 else "#f39c12" if cr > 50 else "#27ae60"
                        for cr in ciclo1["churn_rate"]
                    ],
                    text=ciclo1["churn_rate"].apply(lambda v: f"{v:.1f}%"),
                    textposition="outside",
                ))
                fig_bar.update_layout(
                    title=f"Churn no 1o Ciclo — Plano {dur_sel}m",
                    yaxis_title="Churn (%)",
                    height=350,
                    yaxis=dict(range=[0, max(ciclo1["churn_rate"]) * 1.15]),
                )
                st.plotly_chart(fig_bar, use_container_width=True)

                st.dataframe(
                    ciclo1.rename(columns={
                        dim_sel: "Perfil", "contratos": "Contratos",
                        "churners": "Churners", "churn_rate": "Churn (%)"
                    }),
                    hide_index=True, use_container_width=True
                )

    except FileNotFoundError:
        st.error("Arquivo `results/sobrevivencia_perfil.csv` nao encontrado. Rode a query IA-1B.")
    except Exception as e:
        st.error(f"Erro: {e}")
