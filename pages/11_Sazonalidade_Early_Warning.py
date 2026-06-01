"""
Pagina 11 — Sazonalidade & Early Warning
==========================================
Padroes temporais de churn e sinais precoces de abandono.
Responde: "Quando o churn e pior? Quais sinais antecipam a saida?"
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(page_title="Sazonalidade & Early Warning", page_icon="⚡", layout="wide")
st.title("⚡ Sazonalidade & Early Warning")
st.markdown(
    "Padroes temporais do churn e **sinais precoces** que o CRM pode monitorar "
    "para intervir antes da perda do cliente."
)


# ═══════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════
@st.cache_data
def load_sazonalidade():
    df = pd.read_csv("results/sazonalidade_churn.csv")
    df["duracao"] = df["duracao"].astype(str)
    return df


@st.cache_data
def load_early_warning():
    df = pd.read_csv("results/early_warning.csv")
    df["duracao"] = df["duracao"].astype(str)
    return df


@st.cache_data
def load_velocidade():
    df = pd.read_csv("results/velocidade_churn.csv")
    df["duracao"] = df["duracao"].astype(str)
    return df


tab1, tab2, tab3, tab4 = st.tabs([
    "📅 Sazonalidade Mensal",
    "📆 Dia da Semana",
    "🔔 Early Warning",
    "⏱️ Janela de Resgate",
])


# ═══════════════════════════════════════════════════════════════════
# TAB 1: SAZONALIDADE MENSAL
# ═══════════════════════════════════════════════════════════════════
with tab1:
    try:
        df = load_sazonalidade()
        df["mes_vencimento"] = pd.to_datetime(df["mes_vencimento"])

        st.markdown("### Churn por Mes de Vencimento")
        st.markdown("""
        Identifica **meses criticos** onde o churn e sistematicamente maior.
        Util para planejar campanhas de retencao com antecedencia.
        """)

        # Agregar por mes (sem dia da semana)
        mensal = df.groupby(["mes_vencimento", "duracao"]).agg(
            total=("total_contratos", "sum"),
            churners=("churners", "sum"),
        ).reset_index()
        mensal["churn_rate"] = round(100 * mensal["churners"] / mensal["total"], 1)

        dur_sel = st.radio(
            "Duracao:", options=["6", "12"], index=1,
            format_func=lambda x: f"{x} meses", horizontal=True, key="saz_dur"
        )

        mensal_d = mensal[mensal["duracao"] == dur_sel].sort_values("mes_vencimento")

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=mensal_d["mes_vencimento"],
            y=mensal_d["total"],
            name="Contratos",
            marker_color="rgba(52, 152, 219, 0.4)",
        ))
        fig.add_trace(go.Scatter(
            x=mensal_d["mes_vencimento"],
            y=mensal_d["churn_rate"],
            name="Churn (%)",
            yaxis="y2",
            mode="lines+markers+text",
            line=dict(width=3, color="#c0392b"),
            marker=dict(size=10),
            text=mensal_d["churn_rate"].apply(lambda v: f"{v:.1f}%"),
            textposition="top center",
            textfont=dict(size=11, color="#c0392b"),
        ))

        # Media
        media = mensal_d["churn_rate"].mean()
        fig.add_hline(
            y=media, yref="y2", line_dash="dash", line_color="gray",
            annotation_text=f"Media: {media:.1f}%",
        )

        fig.update_layout(
            title=f"Churn Mensal — Plano {dur_sel}m",
            yaxis=dict(title="Contratos"),
            yaxis2=dict(title="Churn (%)", overlaying="y", side="right", range=[0, 100]),
            height=420,
            legend=dict(orientation="h", y=1.12),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Destaque dos meses piores
        piores = mensal_d[mensal_d["churn_rate"] > media + 2].sort_values("churn_rate", ascending=False)
        if len(piores) > 0:
            meses_piores = piores["mes_vencimento"].dt.strftime("%b/%Y").tolist()
            st.warning(
                f"**Meses criticos** (churn > {media + 2:.1f}%): "
                + ", ".join(meses_piores)
                + ". Planejar campanhas de retencao com 30-60 dias de antecedencia."
            )

        # Sazonalidade por mes do ano
        st.markdown("---")
        st.markdown("### Padrao Sazonal (media por mes do ano)")

        mensal_d["mes_num"] = mensal_d["mes_vencimento"].dt.month
        sazonal = mensal_d.groupby("mes_num").agg(
            churn_medio=("churn_rate", "mean"),
            volume_medio=("total", "mean"),
        ).reset_index()

        meses_pt = {
            1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
            7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
        }
        sazonal["mes_nome"] = sazonal["mes_num"].map(meses_pt)

        fig_saz = go.Figure()
        fig_saz.add_trace(go.Bar(
            x=sazonal["mes_nome"],
            y=sazonal["churn_medio"],
            marker_color=[
                "#c0392b" if cr > sazonal["churn_medio"].mean() + 1
                else "#f39c12" if cr > sazonal["churn_medio"].mean()
                else "#27ae60"
                for cr in sazonal["churn_medio"]
            ],
            text=sazonal["churn_medio"].apply(lambda v: f"{v:.1f}%"),
            textposition="outside",
        ))
        fig_saz.update_layout(
            title="Churn Medio por Mes do Ano",
            yaxis_title="Churn (%)",
            height=350,
            yaxis=dict(range=[0, max(sazonal["churn_medio"]) * 1.2]),
        )
        st.plotly_chart(fig_saz, use_container_width=True)

    except FileNotFoundError:
        st.error("Arquivo `results/sazonalidade_churn.csv` nao encontrado. Rode a query IA-3A.")
    except Exception as e:
        st.error(f"Erro: {e}")


# ═══════════════════════════════════════════════════════════════════
# TAB 2: DIA DA SEMANA
# ═══════════════════════════════════════════════════════════════════
with tab2:
    try:
        df = load_sazonalidade()

        st.markdown("### Churn por Dia da Semana de Vencimento")
        st.markdown("""
        Cobranças automaticas em **fins de semana** ou feriados podem ter taxa de
        recusa maior. Se confirmado, ajustar datas de cobrança pode reduzir churn passivo.
        """)

        dia_agg = df.groupby(["dia_semana_vencimento", "dia_semana_nome"]).agg(
            total=("total_contratos", "sum"),
            churners=("churners", "sum"),
        ).reset_index()
        dia_agg["churn_rate"] = round(100 * dia_agg["churners"] / dia_agg["total"], 1)
        dia_agg = dia_agg.sort_values("dia_semana_vencimento")

        # Identificar fim de semana
        dia_agg["tipo"] = dia_agg["dia_semana_vencimento"].apply(
            lambda d: "Fim de semana" if d in (1, 7) else "Dia util"
        )

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=dia_agg["dia_semana_nome"],
            y=dia_agg["churn_rate"],
            marker_color=[
                "#e74c3c" if t == "Fim de semana" else "#3498db"
                for t in dia_agg["tipo"]
            ],
            text=dia_agg.apply(
                lambda r: f"{r['churn_rate']:.1f}%<br>({int(r['total']):,})", axis=1
            ),
            textposition="outside",
            textfont=dict(size=11),
        ))
        media = dia_agg["churn_rate"].mean()
        fig.add_hline(y=media, line_dash="dash", line_color="gray",
                      annotation_text=f"Media: {media:.1f}%")
        fig.update_layout(
            title="Churn por Dia da Semana de Vencimento",
            yaxis_title="Churn (%)",
            height=400,
            yaxis=dict(range=[0, max(dia_agg["churn_rate"]) * 1.15]),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Comparacao fds vs util
        fds = dia_agg[dia_agg["tipo"] == "Fim de semana"]
        util = dia_agg[dia_agg["tipo"] == "Dia util"]
        if len(fds) > 0 and len(util) > 0:
            churn_fds = (fds["churners"].sum() / fds["total"].sum()) * 100
            churn_util = (util["churners"].sum() / util["total"].sum()) * 100
            delta = churn_fds - churn_util

            st.markdown(f"""
            | Periodo | Churn | Volume |
            |---|---|---|
            | Dia util | {churn_util:.1f}% | {int(util['total'].sum()):,} contratos |
            | Fim de semana | {churn_fds:.1f}% | {int(fds['total'].sum()):,} contratos |
            | **Delta** | **{delta:+.1f} p.p.** | |
            """)

            if abs(delta) > 1:
                st.info(
                    f"**Insight:** Contratos vencendo em {'fim de semana' if delta > 0 else 'dia util'} "
                    f"tem churn {abs(delta):.1f} p.p. {'maior' if delta > 0 else 'menor'}. "
                    f"Considerar ajustar data de cobranca para dias uteis."
                )

    except FileNotFoundError:
        st.error("Arquivo `results/sazonalidade_churn.csv` nao encontrado.")
    except Exception as e:
        st.error(f"Erro: {e}")


# ═══════════════════════════════════════════════════════════════════
# TAB 3: EARLY WARNING — SINAIS PRECOCES
# ═══════════════════════════════════════════════════════════════════
with tab3:
    try:
        df = load_early_warning()

        st.markdown("### Sinais Precoces de Churn")
        st.markdown("""
        Cruzamos **4 sinais observaveis durante a vigencia do contrato** para
        identificar padroes que antecipam o churn. O CRM pode monitorar esses
        sinais e disparar acoes preventivas.
        """)

        dur_sel = st.radio(
            "Duracao:", options=["6", "12"], index=1,
            format_func=lambda x: f"{x} meses", horizontal=True, key="ew_dur"
        )
        df_d = df[df["duracao"] == dur_sel].copy()

        # Sinal 1: Consumo × Ciclo
        st.markdown("#### Sinal 1: Consumo no 1o contrato")

        s1 = df_d.groupby(["ciclo", "consumiu"]).agg(
            total=("total_contratos", "sum"),
            churners=("churners", "sum"),
        ).reset_index()
        s1["churn_rate"] = round(100 * s1["churners"] / s1["total"], 1)

        fig1 = px.bar(
            s1, x="ciclo", y="churn_rate", color="consumiu",
            barmode="group", text_auto=".1f",
            title="Churn: Consumiu vs Nao Consumiu",
            color_discrete_map={"usou": "#27ae60", "nao_usou": "#c0392b"},
            labels={"ciclo": "Ciclo", "churn_rate": "Churn (%)", "consumiu": ""},
        )
        fig1.update_layout(height=350)
        st.plotly_chart(fig1, use_container_width=True)

        # Sinal 2: Intensidade de uso (faixa de itens)
        st.markdown("#### Sinal 2: Intensidade de Uso")

        s2 = df_d.groupby("faixa_itens").agg(
            total=("total_contratos", "sum"),
            churners=("churners", "sum"),
        ).reset_index()
        s2["churn_rate"] = round(100 * s2["churners"] / s2["total"], 1)
        s2 = s2.sort_values("faixa_itens")

        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            x=s2["faixa_itens"],
            y=s2["churn_rate"],
            marker_color=["#c0392b", "#e74c3c", "#f39c12", "#27ae60"],
            text=s2.apply(
                lambda r: f"{r['churn_rate']:.1f}%\n({int(r['total']):,})", axis=1
            ),
            textposition="outside",
        ))
        fig2.update_layout(
            title="Churn por Quantidade de Itens Consumidos",
            yaxis_title="Churn (%)",
            height=350,
            yaxis=dict(range=[0, max(s2["churn_rate"]) * 1.15]),
        )
        st.plotly_chart(fig2, use_container_width=True)

        # Sinal 3: Diversidade de uso
        st.markdown("#### Sinal 3: Diversidade de Especialidades Usadas")

        s3 = df_d.groupby("diversidade_uso").agg(
            total=("total_contratos", "sum"),
            churners=("churners", "sum"),
        ).reset_index()
        s3["churn_rate"] = round(100 * s3["churners"] / s3["total"], 1)
        s3 = s3.sort_values("diversidade_uso")

        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(
            x=s3["diversidade_uso"],
            y=s3["churn_rate"],
            mode="lines+markers+text",
            line=dict(width=3, color="#2c3e50"),
            marker=dict(
                size=np.sqrt(s3["total"]) / 8 + 5,
                color=s3["churn_rate"],
                colorscale="RdYlGn_r",
                showscale=True,
                colorbar=dict(title="Churn (%)"),
            ),
            text=s3["churn_rate"].apply(lambda v: f"{v:.1f}%"),
            textposition="top center",
        ))
        fig3.update_layout(
            title="Churn por Numero de Especialidades Diferentes Usadas",
            xaxis_title="Especialidades usadas",
            yaxis_title="Churn (%)",
            height=350,
        )
        st.plotly_chart(fig3, use_container_width=True)

        # Score de risco combinado
        st.markdown("---")
        st.markdown("### Matriz de Risco: Consumo × Diversidade × Ciclo")

        matrix = df_d.groupby(["ciclo", "consumiu", "faixa_itens"]).agg(
            total=("total_contratos", "sum"),
            churners=("churners", "sum"),
        ).reset_index()
        matrix["churn_rate"] = round(100 * matrix["churners"] / matrix["total"], 1)
        matrix = matrix[matrix["total"] >= 50]

        if len(matrix) > 0:
            fig_m = px.bar(
                matrix, x="faixa_itens", y="churn_rate", color="consumiu",
                facet_col="ciclo", barmode="group", text_auto=".1f",
                title="Churn por Ciclo × Consumo × Intensidade",
                color_discrete_map={"usou": "#27ae60", "nao_usou": "#c0392b"},
                labels={"faixa_itens": "Itens", "churn_rate": "Churn (%)"},
            )
            fig_m.update_layout(height=400)
            st.plotly_chart(fig_m, use_container_width=True)

        # Alertas acionaveis
        st.markdown("---")
        st.markdown("### 🔔 Regras de Alerta para o CRM")

        # Calcular os perfis de maior risco
        risco_alto = df_d[
            (df_d["consumiu"] == "nao_usou") &
            (df_d["ciclo"] == "1o")
        ]
        if len(risco_alto) > 0:
            churn_nao_usou_1o = round(
                100 * risco_alto["churners"].sum() / risco_alto["total_contratos"].sum(), 1
            )
        else:
            churn_nao_usou_1o = 0

        st.error(f"""
        **ALERTA VERMELHO** — Churn {churn_nao_usou_1o}%
        - **Quem:** 1o contrato + nao consumiu nenhum servico
        - **Quando disparar:** 30 dias apos ativacao sem uso
        - **Acao:** SMS/WhatsApp com agendamento facilitado + voucher 1a consulta
        """)

        risco_medio = df_d[
            (df_d["diversidade_uso"] <= 1) &
            (df_d["ciclo"] == "1o") &
            (df_d["consumiu"] == "usou")
        ]
        if len(risco_medio) > 0:
            churn_baixo_div = round(
                100 * risco_medio["churners"].sum() / risco_medio["total_contratos"].sum(), 1
            )
        else:
            churn_baixo_div = 0

        st.warning(f"""
        **ALERTA AMARELO** — Churn {churn_baixo_div}%
        - **Quem:** 1o contrato + usou apenas 1 especialidade
        - **Quando disparar:** 60 dias apos ativacao
        - **Acao:** Sugerir especialidades complementares (check-up, preventivo)
        """)

        st.success("""
        **SINAL POSITIVO** — Baixo risco
        - **Quem:** 2o+ contrato + 3+ especialidades usadas + cronico
        - **Acao:** Programa de fidelidade / beneficio exclusivo para reforcar vinculo
        """)

    except FileNotFoundError:
        st.error("Arquivo `results/early_warning.csv` nao encontrado. Rode a query IA-3B.")
    except Exception as e:
        st.error(f"Erro: {e}")


# ═══════════════════════════════════════════════════════════════════
# TAB 4: JANELA DE RESGATE
# ═══════════════════════════════════════════════════════════════════
with tab4:
    try:
        df = load_velocidade()

        st.markdown("### Janela de Decisao — Quando o cliente decide sair?")
        st.markdown("""
        **Churn ativo:** quantos dias *antes* do vencimento o paciente pediu cancelamento?
        Mostra quando a decisao acontece e quando o CRM precisa agir.

        **Churn silencioso:** o paciente voltou depois? Em quanto tempo?
        """)

        dur_sel = st.radio(
            "Duracao:", options=["6", "12"], index=1,
            format_func=lambda x: f"{x} meses", horizontal=True, key="vel_dur"
        )
        df_d = df[df["duracao"].astype(str) == dur_sel].copy()

        for tipo in ["churn_ativo", "churn_silencioso"]:
            sub = df_d[df_d["tipo_churn"] == tipo].copy()
            if len(sub) == 0:
                continue

            if tipo == "churn_ativo":
                titulo = "Churn Ativo — Antecedencia do pedido de cancelamento"
                desc = "Dias entre o pedido de cancelamento e o vencimento do contrato."
            else:
                titulo = "Churn Silencioso — Retorno pos-vencimento"
                desc = "O paciente voltou? Se sim, em quanto tempo?"

            st.markdown(f"#### {titulo}")
            st.caption(desc)

            # Agrupar por janela (ja vem agregado por ciclo, pegar total)
            janela = sub.groupby("janela_saida").agg(
                total=("total", "sum"),
            ).reset_index()

            janela["pct"] = round(100 * janela["total"] / janela["total"].sum(), 1)
            janela["pct_acum"] = janela["pct"].cumsum()
            janela = janela.sort_values("janela_saida")

            col1, col2 = st.columns([2, 1])

            with col1:
                n_bars = len(janela)
                colors_ativo = ["#1a9850", "#91cf60", "#fee08b", "#fc8d59", "#d73027"]
                colors_silen = ["#d73027", "#fc8d59", "#fee08b"]

                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=janela["janela_saida"].astype(str).str.replace("_", " "),
                    y=janela["pct"],
                    marker_color=(colors_ativo if tipo == "churn_ativo" else colors_silen)[:n_bars],
                    text=janela.apply(
                        lambda r: f"{r['pct']:.1f}%\n({int(r['total']):,})", axis=1
                    ),
                    textposition="outside",
                    textfont=dict(size=11),
                ))
                fig.add_trace(go.Scatter(
                    x=janela["janela_saida"].astype(str).str.replace("_", " "),
                    y=janela["pct_acum"],
                    mode="lines+markers",
                    name="% Acumulado",
                    line=dict(width=2, color="#2c3e50", dash="dot"),
                    marker=dict(size=8),
                    yaxis="y2",
                ))
                fig.update_layout(
                    title=titulo,
                    yaxis=dict(title="% dos Churners"),
                    yaxis2=dict(title="% Acumulado", overlaying="y", side="right", range=[0, 105]),
                    height=400,
                    legend=dict(orientation="h", y=1.12),
                    xaxis=dict(automargin=True),
                )
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                disp = janela[["janela_saida", "total", "pct", "pct_acum"]].copy()
                disp["janela_saida"] = disp["janela_saida"].str.replace("_", " ")
                st.dataframe(
                    disp.rename(columns={
                        "janela_saida": "Janela", "total": "Churners",
                        "pct": "%", "pct_acum": "% Acum."
                    }),
                    hide_index=True, use_container_width=True,
                )

            # Insights especificos por tipo
            if tipo == "churn_ativo":
                antes_30d = janela[janela["janela_saida"].isin([
                    "A_90+_dias_antes", "B_31-90_dias_antes"
                ])]
                pct_antes_30d = antes_30d["pct"].sum() if len(antes_30d) > 0 else 0

                if pct_antes_30d > 30:
                    st.info(
                        f"**{pct_antes_30d:.0f}%** dos cancelamentos ativos acontecem com "
                        f"mais de 30 dias de antecedencia. Ha tempo para uma **contra-oferta** "
                        f"ou entrevista de retencao."
                    )
                else:
                    st.warning(
                        f"Apenas **{pct_antes_30d:.0f}%** cancelam com mais de 30 dias de "
                        f"antecedencia. A maioria decide perto do vencimento — acoes preventivas "
                        f"precisam comecar **cedo no ciclo do contrato**."
                    )
            else:
                nunca = janela[janela["janela_saida"] == "F_nunca_voltou"]
                pct_nunca = nunca["pct"].values[0] if len(nunca) > 0 else 0
                st.error(
                    f"**{pct_nunca:.0f}%** dos churners silenciosos **nunca voltaram**. "
                    f"Sao a maior oportunidade de win-back — nao houve rejeicao ativa."
                )

            st.markdown("")

        st.markdown("---")
        st.success("""
        **Recomendacoes de Timing:**
        1. **D-90:** Campanha preventiva para perfis de alto risco (score < 400)
        2. **D-30:** Regua de engajamento — lembrar beneficios, sugerir consulta
        3. **D-7:** Lembrete de renovacao + destaque de especialidades nao usadas
        4. **D+1:** Regua de recuperacao para falha de pagamento (SMS + email + WhatsApp)
        5. **D+7:** Oferta de retencao com desconto para quem nao renovou
        6. **D+30:** Win-back para silenciosos — pesquisa + oferta de retorno
        """)

    except FileNotFoundError:
        st.error("Arquivo `results/velocidade_churn.csv` nao encontrado. Rode a query IA-3C (v2).")
    except Exception as e:
        st.error(f"Erro: {e}")
