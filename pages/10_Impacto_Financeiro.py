"""
Pagina 10 — Impacto Financeiro & CLV
=====================================
Quantifica o churn em R$: receita perdida, MRR lost, CLV por perfil e ROI de retencao.
O ticket medio e parametrizavel na sidebar (a tabela base nao tem coluna de valor).
Responde: "Quanto custa o churn? Onde investir para reter?"
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(page_title="Impacto Financeiro", page_icon="💰", layout="wide")
st.title("💰 Impacto Financeiro & CLV")
st.markdown(
    "Quantificacao do churn em **R$**: receita perdida, MRR lost e "
    "**Customer Lifetime Value** por perfil. Ticket medio parametrizavel na sidebar."
)


# ═══════════════════════════════════════════════════════════════════
# SIDEBAR — TICKET MEDIO PARAMETRIZAVEL
# ═══════════════════════════════════════════════════════════════════
st.sidebar.markdown("### 💲 Ticket Medio do Plano")
st.sidebar.caption(
    "A tabela de churn nao tem coluna de valor. Informe o ticket medio "
    "por duracao para calcular o impacto em R$."
)
ticket_6m = st.sidebar.number_input(
    "Ticket plano 6 meses (R$):", min_value=50.0, max_value=5000.0,
    value=600.0, step=50.0, key="ticket_6m",
)
ticket_12m = st.sidebar.number_input(
    "Ticket plano 12 meses (R$):", min_value=50.0, max_value=10000.0,
    value=1200.0, step=50.0, key="ticket_12m",
)
TICKET_MAP = {"6": ticket_6m, "12": ticket_12m}


# ═══════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════
@st.cache_data
def load_financeiro():
    df = pd.read_csv("results/impacto_financeiro.csv")
    df["duracao"] = df["duracao"].astype(str)
    return df


@st.cache_data
def load_clv():
    df = pd.read_csv("results/clv_por_perfil.csv")
    df["duracao"] = df["duracao"].astype(str)
    return df


tab1, tab2, tab3 = st.tabs([
    "📉 Receita Perdida",
    "💎 CLV por Perfil",
    "🎯 ROI de Retencao",
])


# ═══════════════════════════════════════════════════════════════════
# TAB 1: RECEITA PERDIDA
# ═══════════════════════════════════════════════════════════════════
with tab1:
    try:
        df = load_financeiro()
        df["mes_vencimento"] = pd.to_datetime(df["mes_vencimento"])

        # Calcular valores financeiros a partir do ticket parametrizado
        df["ticket"] = df["duracao"].map(TICKET_MAP)
        df["receita_total"] = df["total_contratos"] * df["ticket"]
        df["receita_perdida"] = df["churners"] * df["ticket"]
        df["receita_retida"] = df["retidos"] * df["ticket"]
        df["mrr_perdido"] = df["churners"] * df["ticket"] / df["duracao"].astype(float)

        st.markdown("### Panorama Financeiro do Churn")

        # KPIs globais
        receita_total = df["receita_total"].sum()
        receita_perdida = df["receita_perdida"].sum()
        mrr_perdido = df["mrr_perdido"].sum()
        total_churners = int(df["churners"].sum())
        total_contratos = int(df["total_contratos"].sum())

        k1, k2, k3, k4 = st.columns(4)
        k1.metric(
            "Receita Total (12m)", f"R$ {receita_total:,.0f}",
            help="Soma do ticket x contratos vencidos nos ultimos 12 meses"
        )
        k2.metric(
            "Receita Perdida por Churn", f"R$ {receita_perdida:,.0f}",
            delta=f"-{100 * receita_perdida / receita_total:.1f}%",
            delta_color="inverse",
        )
        k3.metric(
            "MRR Perdido (mensal)", f"R$ {mrr_perdido:,.0f}",
            delta=f"{total_churners:,} churners",
            delta_color="inverse",
        )
        k4.metric("Contratos Analisados", f"{total_contratos:,}")

        st.markdown("---")

        # Evolucao temporal
        st.markdown("### Evolucao do MRR Perdido por Mes")

        mensal = df.groupby("mes_vencimento").agg(
            mrr_perdido=("mrr_perdido", "sum"),
            churners=("churners", "sum"),
            total=("total_contratos", "sum"),
        ).reset_index()
        mensal["churn_rate"] = round(100 * mensal["churners"] / mensal["total"], 1)

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=mensal["mes_vencimento"],
            y=mensal["mrr_perdido"],
            name="MRR Perdido",
            marker_color="#c0392b",
            text=mensal["mrr_perdido"].apply(lambda v: f"R$ {v:,.0f}"),
            textposition="outside",
            textfont=dict(size=10),
        ))
        fig.add_trace(go.Scatter(
            x=mensal["mes_vencimento"],
            y=mensal["churn_rate"],
            name="Churn (%)",
            yaxis="y2",
            mode="lines+markers",
            line=dict(color="#f39c12", width=2),
            marker=dict(size=8),
        ))
        fig.update_layout(
            title="MRR Perdido x Churn Rate por Mes",
            yaxis=dict(title="MRR Perdido (R$)"),
            yaxis2=dict(title="Churn (%)", overlaying="y", side="right", range=[0, 100]),
            height=420,
            legend=dict(orientation="h", y=1.12),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        # Receita perdida por segmento
        st.markdown("### Receita Perdida por Segmento")

        col1, col2 = st.columns(2)

        with col1:
            by_ciclo = df.groupby("ciclo").agg(
                receita_perdida=("receita_perdida", "sum"),
                churners=("churners", "sum"),
            ).reset_index()

            fig_ciclo = go.Figure(data=[go.Pie(
                labels=by_ciclo["ciclo"].map({"1o": "1o Contrato", "2o+": "2o+ Contrato"}),
                values=by_ciclo["receita_perdida"],
                hole=0.45,
                marker_colors=["#e74c3c", "#3498db"],
                textinfo="label+percent+value",
                texttemplate="%{label}<br>R$ %{value:,.0f}<br>(%{percent})",
                textfont=dict(size=12),
            )])
            fig_ciclo.update_layout(
                title="Receita Perdida por Ciclo",
                height=350, showlegend=False,
            )
            st.plotly_chart(fig_ciclo, use_container_width=True)

        with col2:
            by_idade = df.groupby("perfil_idade").agg(
                receita_perdida=("receita_perdida", "sum"),
                churners=("churners", "sum"),
            ).reset_index().sort_values("receita_perdida", ascending=False)

            fig_idade = go.Figure()
            fig_idade.add_trace(go.Bar(
                x=by_idade["perfil_idade"],
                y=by_idade["receita_perdida"],
                marker_color=["#e74c3c", "#f39c12", "#27ae60"],
                text=by_idade["receita_perdida"].apply(lambda v: f"R$ {v:,.0f}"),
                textposition="outside",
            ))
            fig_idade.update_layout(
                title="Receita Perdida por Faixa Etaria",
                yaxis_title="Receita Perdida (R$)",
                height=350,
            )
            st.plotly_chart(fig_idade, use_container_width=True)

        st.caption(
            f"Valores calculados com ticket medio: 6m = R$ {ticket_6m:,.0f} | "
            f"12m = R$ {ticket_12m:,.0f}. Ajuste na sidebar."
        )

    except FileNotFoundError:
        st.error("Arquivo `results/impacto_financeiro.csv` nao encontrado. Rode a query IA-2A.")
    except Exception as e:
        st.error(f"Erro: {e}")


# ═══════════════════════════════════════════════════════════════════
# TAB 2: CLV POR PERFIL
# ═══════════════════════════════════════════════════════════════════
with tab2:
    try:
        df = load_clv()

        st.markdown("### Customer Lifetime Value por Perfil")
        st.markdown("""
        O CLV estima **quanto receita um cliente gera ao longo da vida**.

        `CLV = ticket_mensal x meses_vida_estimados`

        Onde `meses_vida_estimados = duracao / churn_rate` (modelo geometrico simples).
        """)

        # Calcular CLV com ticket parametrizado
        df["ticket"] = df["duracao"].map(TICKET_MAP)
        df["ticket_mensal"] = df["ticket"] / df["duracao"].astype(float)
        df["clv_estimado"] = df["ticket_mensal"] * df["meses_vida_estimados"]
        df["receita_perdida"] = df["churners"] * df["ticket"]

        df["perfil"] = (
            df["ciclo"] + " | " + df["perfil_idade"] + " | " +
            df["cronico"] + " | " + df["tem_dependente"]
        )

        # Top perfis por CLV
        df_sorted = df.sort_values("clv_estimado", ascending=False).head(20)

        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=df_sorted["perfil"].iloc[::-1],
            x=df_sorted["clv_estimado"].iloc[::-1],
            orientation="h",
            marker_color=[
                "#27ae60" if clv > df["clv_estimado"].quantile(0.75)
                else "#f39c12" if clv > df["clv_estimado"].quantile(0.5)
                else "#c0392b"
                for clv in df_sorted["clv_estimado"].iloc[::-1]
            ],
            text=df_sorted["clv_estimado"].iloc[::-1].apply(lambda v: f"R$ {v:,.0f}"),
            textposition="outside",
            textfont=dict(size=10),
        ))
        fig.update_layout(
            title="Top 20 Perfis por CLV Estimado",
            xaxis_title="CLV (R$)",
            height=max(500, len(df_sorted) * 28 + 80),
            margin=dict(l=20, r=100),
            yaxis=dict(automargin=True),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        # Scatter: CLV x Churn Rate x Volume
        st.markdown("### Mapa Estrategico: CLV vs Churn")
        st.markdown("""
        Cada bolha e um perfil. **Quadrante superior-direito** (alto CLV + alto churn)
        e a zona critica — muito valor sendo perdido.
        """)

        fig_scatter = go.Figure()
        fig_scatter.add_trace(go.Scatter(
            x=df["churn_rate_pct"],
            y=df["clv_estimado"],
            mode="markers+text",
            marker=dict(
                size=np.sqrt(df["total_contratos"]) / 3,
                color=df["receita_perdida"],
                colorscale="Reds",
                showscale=True,
                colorbar=dict(title="Receita Perdida (R$)"),
                line=dict(width=1, color="rgba(0,0,0,0.3)"),
                sizemin=8,
            ),
            text=df["ciclo"] + " " + df["perfil_idade"].str.split("_").str[-1],
            textposition="top center",
            textfont=dict(size=9),
            hovertext=df.apply(
                lambda r: f"Perfil: {r['perfil']}<br>"
                          f"CLV: R$ {r['clv_estimado']:,.0f}<br>"
                          f"Churn: {r['churn_rate_pct']:.1f}%<br>"
                          f"Contratos: {int(r['total_contratos']):,}<br>"
                          f"Vida media: {r['meses_vida_estimados']:.0f} meses<br>"
                          f"Receita perdida: R$ {r['receita_perdida']:,.0f}",
                axis=1
            ),
            hoverinfo="text",
        ))

        median_churn = df["churn_rate_pct"].median()
        median_clv = df["clv_estimado"].median()
        fig_scatter.add_hline(y=median_clv, line_dash="dash", line_color="gray", opacity=0.5)
        fig_scatter.add_vline(x=median_churn, line_dash="dash", line_color="gray", opacity=0.5)

        fig_scatter.add_annotation(
            x=df["churn_rate_pct"].max() * 0.85, y=df["clv_estimado"].max() * 0.9,
            text="CRITICO\nAlto valor + alto churn",
            showarrow=False, font=dict(size=11, color="red"),
        )
        fig_scatter.add_annotation(
            x=df["churn_rate_pct"].min() * 1.3, y=df["clv_estimado"].max() * 0.9,
            text="IDEAL\nAlto valor + baixo churn",
            showarrow=False, font=dict(size=11, color="green"),
        )

        fig_scatter.update_layout(
            title="Mapa Estrategico: CLV vs Churn Rate",
            xaxis_title="Churn Rate (%)",
            yaxis_title="CLV Estimado (R$)",
            height=550,
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

        st.markdown("---")

        # Tabela completa
        st.markdown("### Tabela Completa de CLV")
        table = df[[
            "ciclo", "perfil_idade", "cronico", "tem_dependente", "duracao",
            "total_contratos", "churn_rate_pct", "meses_vida_estimados",
            "ticket_mensal", "clv_estimado", "receita_perdida"
        ]].copy()
        table.columns = [
            "Ciclo", "Idade", "Cronico", "Dependente", "Duracao",
            "Contratos", "Churn (%)", "Vida (meses)",
            "Ticket Mensal", "CLV (R$)", "Receita Perdida (R$)"
        ]
        table = table.sort_values("CLV (R$)", ascending=False)

        for col in ["Ticket Mensal", "CLV (R$)", "Receita Perdida (R$)"]:
            table[col] = table[col].apply(lambda v: f"R$ {v:,.2f}")
        table["Contratos"] = table["Contratos"].apply(lambda v: f"{int(v):,}")
        table["Vida (meses)"] = table["Vida (meses)"].apply(lambda v: f"{v:.1f}")

        st.dataframe(table, hide_index=True, use_container_width=True)

        st.caption(
            f"Valores calculados com ticket medio: 6m = R$ {ticket_6m:,.0f} | "
            f"12m = R$ {ticket_12m:,.0f}. Ajuste na sidebar."
        )

    except FileNotFoundError:
        st.error("Arquivo `results/clv_por_perfil.csv` nao encontrado. Rode a query IA-2B.")
    except Exception as e:
        st.error(f"Erro: {e}")


# ═══════════════════════════════════════════════════════════════════
# TAB 3: ROI DE RETENCAO
# ═══════════════════════════════════════════════════════════════════
with tab3:
    try:
        df_fin = load_financeiro()

        st.markdown("### Simulador de ROI de Retencao")
        st.markdown("""
        Se conseguirmos **reduzir o churn em X p.p.** num segmento, quanto de receita preservamos?
        Use o simulador para projetar cenarios e priorizar investimentos.
        """)

        col_param, col_result = st.columns([1, 2])

        with col_param:
            st.markdown("#### Parametros")
            reducao_churn = st.slider(
                "Reducao de churn esperada (p.p.):",
                min_value=1, max_value=15, value=5, step=1,
            )
            custo_por_acao = st.number_input(
                "Custo por acao de retencao (R$):",
                min_value=0.0, max_value=500.0, value=15.0, step=5.0,
                help="SMS, WhatsApp, ligacao, desconto etc."
            )
            pct_alcance = st.slider(
                "% do publico alcancado:",
                min_value=10, max_value=100, value=60, step=10,
            )

        with col_result:
            st.markdown("#### Projecao por Segmento")

            seg = df_fin.groupby(["ciclo", "perfil_idade", "duracao"]).agg(
                total_contratos=("total_contratos", "sum"),
                churners=("churners", "sum"),
            ).reset_index()
            seg["churn_rate"] = round(100 * seg["churners"] / seg["total_contratos"], 1)
            seg["ticket"] = seg["duracao"].map(TICKET_MAP)

            seg["publico_alvo"] = (seg["total_contratos"] * pct_alcance / 100).astype(int)
            seg["churners_evitaveis"] = (seg["publico_alvo"] * reducao_churn / 100).astype(int)
            seg["receita_salva"] = seg["churners_evitaveis"] * seg["ticket"]
            seg["custo_total"] = seg["publico_alvo"] * custo_por_acao
            seg["roi"] = np.where(
                seg["custo_total"] > 0,
                ((seg["receita_salva"] - seg["custo_total"]) / seg["custo_total"] * 100).round(0),
                0
            )
            seg["lucro_liquido"] = seg["receita_salva"] - seg["custo_total"]
            seg = seg.sort_values("lucro_liquido", ascending=False)

            total_salvo = seg["receita_salva"].sum()
            total_custo = seg["custo_total"].sum()
            total_lucro = seg["lucro_liquido"].sum()
            roi_geral = ((total_salvo - total_custo) / total_custo * 100) if total_custo > 0 else 0

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Receita Salva", f"R$ {total_salvo:,.0f}")
            m2.metric("Custo Total", f"R$ {total_custo:,.0f}")
            m3.metric("Lucro Liquido", f"R$ {total_lucro:,.0f}",
                       delta=f"ROI: {roi_geral:.0f}%")
            m4.metric("Churners Evitados", f"{seg['churners_evitaveis'].sum():,}")

        st.markdown("---")

        top_seg = seg.head(10).iloc[::-1].copy()
        top_seg["label"] = top_seg["ciclo"] + " | " + top_seg["perfil_idade"] + " | " + top_seg["duracao"] + "m"

        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=top_seg["label"],
            x=top_seg["lucro_liquido"],
            orientation="h",
            marker_color=[
                "#27ae60" if roi > 200 else "#f39c12" if roi > 0 else "#c0392b"
                for roi in top_seg["roi"]
            ],
            text=top_seg.apply(
                lambda r: f"R$ {r['lucro_liquido']:,.0f} (ROI: {r['roi']:.0f}%)", axis=1
            ),
            textposition="outside",
            textfont=dict(size=11),
        ))
        fig.update_layout(
            title=f"Top 10 Segmentos — Lucro Liquido (reducao de {reducao_churn} p.p., custo R$ {custo_por_acao})",
            xaxis_title="Lucro Liquido (R$)",
            height=max(400, len(top_seg) * 35 + 80),
            margin=dict(l=20, r=120),
            yaxis=dict(automargin=True),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.info("""
        **Como interpretar:**
        - **ROI > 200%**: Acao altamente rentavel — priorizar
        - **ROI 50-200%**: Acao rentavel — implementar
        - **ROI < 50%**: Avaliar se o custo compensa
        - **ROI negativo**: Custo da acao supera a receita salva — nao recomendado
        """)

        st.caption(
            f"Valores calculados com ticket medio: 6m = R$ {ticket_6m:,.0f} | "
            f"12m = R$ {ticket_12m:,.0f}. Ajuste na sidebar."
        )

    except FileNotFoundError:
        st.error("Arquivos financeiros nao encontrados. Rode as queries IA-2A e IA-2B.")
    except Exception as e:
        st.error(f"Erro: {e}")
