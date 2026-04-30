import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Análises Avançadas · Churn", page_icon="🔬", layout="wide")

# ═══════════════════════════════════════════════════════════════════════
st.title("🔬 Capítulo 5 — Deep-dives")
st.markdown("""
Consumo controlado por ciclo, motivos de cancelamento, tempo até o primeiro uso,
win-back e perfil do churner silencioso vs ativo.
""")

with st.expander("📖 Dicionário de Dados desta Seção", expanded=False):
    st.markdown("""
    **Novas variáveis e conceitos:**

    | Variável | Significado |
    |---|---|
    | `ciclo` | `1o_contrato` (primeira assinatura) ou `2o+_contrato` (renovação/recompra) |
    | `consumo` | Se utilizou algum serviço durante a vigência (`S`/`N`) |
    | `motivo` | Texto livre informado pelo paciente/operador no momento do cancelamento ativo |
    | `faixa_primeiro_uso` | Quantos dias após a ativação o paciente fez a primeira utilização |
    | `tipo_desfecho` | Classificação em 3 grupos: `retido`, `churn_ativo` (pediu cancelamento), `churn_silencioso` (não renovou sem pedir cancelamento) |
    | `tipo_venda` | `first_contract`, `renewal`, `reactivation` — tipo da transação original |
    """)

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🧪 Paradoxo do Consumo",
    "📝 Motivos de Cancelamento",
    "⏱️ Tempo até 1º Uso",
    "🔄 Win-back",
    "👻 Silencioso vs Ativo"
])

# ═══════════════════════════════════════════════════════════════════════
# TAB 1: PARADOXO DO CONSUMO — CONTROLADO POR CICLO
# ═══════════════════════════════════════════════════════════════════════
with tab1:
    try:
        df = pd.read_csv("results/consumo_controlado_ciclo.csv")

        st.markdown("""
        #### Consumo controlado por ciclo do contrato

        Na Página 3, vimos que quem usa o plano cancela *mais* que quem não usa — um paradoxo.
        Aqui separamos por **ciclo** e **duração** para eliminar o viés.
        """)

        # KPIs
        col1, col2, col3 = st.columns(3)

        # 1o contrato
        pri_s = df[(df["ciclo"] == "1o_contrato") & (df["consumo"] == "S")]["churn_rate"].mean()
        pri_n = df[(df["ciclo"] == "1o_contrato") & (df["consumo"] == "N")]["churn_rate"].mean()
        # 2o+ contrato - note: só tem consumo N nos dados (2o+ não aparece com S)
        seg_n = df[(df["ciclo"] == "2o+_contrato") & (df["consumo"] == "N")]["churn_rate"].mean()

        col1.metric("1º Contrato + Usou", f"{pri_s:.1f}%")
        col2.metric("1º Contrato + NÃO Usou", f"{pri_n:.1f}%")
        col3.metric("2º+ Contrato + NÃO Usou", f"{seg_n:.1f}%")

        # Gráfico agrupado
        df["label"] = df["ciclo"] + " | " + df["duracao"].astype(str) + "m"

        fig = px.bar(
            df, x="label", y="churn_rate", color="consumo",
            barmode="group",
            text_auto=".1f",
            title="Taxa de Churn: Consumo controlado por Ciclo e Duração",
            labels={"label": "", "churn_rate": "Churn (%)", "consumo": "Consumiu?"},
            color_discrete_map={"S": "#d62728", "N": "#1f77b4"},
        )
        fig.update_layout(height=450, xaxis_tickangle=-15)
        st.plotly_chart(fig, use_container_width=True)

        # Tabela
        st.dataframe(
            df[["ciclo", "consumo", "duracao", "total_contratos", "churners", "churn_rate"]].rename(columns={
                "ciclo": "Ciclo", "consumo": "Consumo", "duracao": "Duração (m)",
                "total_contratos": "Contratos", "churners": "Churners", "churn_rate": "Churn (%)"
            }),
            hide_index=True, use_container_width=True
        )

        st.markdown("""
        #### Resultado: o consumo protege, mas não é o fator dominante

        **1. No 1º contrato, quem não usa cancela mais:**
        - 12m: Não usou **64,2%** vs Usou **60,8%** → proteção de **3,4 p.p.**
        - 6m: Não usou **57,5%** vs Usou **56,6%** → proteção de **0,9 p.p.**

        **2. O 1º contrato tem churn alto de qualquer forma** — o problema não é uso vs não uso,
        é que o paciente de 1º contrato é naturalmente volátil.

        **3. No 2º+ contrato sem consumo**, o churn é forte:
        - 12m: **54,0%** | 6m: **45,0%** — quem já renovou e parou de usar está saindo.

        > Os dados de `2o+_contrato + Consumo = S` não apareceram na amostra.
        > Possível que o volume tenha ficado fora do filtro ou que a categorização esteja diferente.
        > Merece investigação adicional.

        **Conclusão:** Incentivar o primeiro uso importa, mas o verdadeiro diferenciador é
        **garantir uso contínuo nas renovações**.
        """)
    except Exception as e:
        st.error(f"Erro: {e}")

# ═══════════════════════════════════════════════════════════════════════
# TAB 2: MOTIVOS DE CANCELAMENTO
# ═══════════════════════════════════════════════════════════════════════
with tab2:
    try:
        df = pd.read_csv("results/motivos_cancelamento.csv")

        st.markdown("""
        #### Motivos de cancelamento ativo

        Dos registros que contêm motivo de cancelamento, a análise é reveladora —
        mais sobre os nossos processos do que sobre os pacientes.
        """)

        # Limpar e classificar motivos
        df_clean = df.copy()

        # Agrupar motivos similares
        def classificar_motivo(motivo):
            m = str(motivo).lower().strip()
            if 'ra' in m or 'procon' in m or 'prazo' in m:
                return '⚖️ Reclamação / Reclame Aqui / Procon'
            elif 'não deseja' in m or 'não renovar' in m or 'desativar' in m:
                return '🚪 Não deseja renovar'
            elif 'falecimento' in m:
                return '🕊️ Falecimento'
            elif 'duplici' in m or 'duplicado' in m:
                return '🔁 Duplicidade de contrato'
            elif 'erro' in m:
                return '⚙️ Erro operacional / sistema'
            elif 'nova assinatura' in m:
                return '🔄 Nova assinatura (migração)'
            elif 'teste' in m:
                return '🧪 Teste'
            elif set(m) <= set('a '):
                return '❓ Sem motivo real (preenchimento inválido)'
            else:
                return '📋 Outros'

        df_clean["categoria"] = df_clean["motivo"].apply(classificar_motivo)
        df_grouped = df_clean.groupby("categoria").agg(
            total=("total", "sum"),
        ).reset_index()
        df_grouped["pct"] = round(100 * df_grouped["total"] / df_grouped["total"].sum(), 1)
        df_grouped = df_grouped.sort_values("total", ascending=False)

        col1, col2 = st.columns([3, 2])

        with col1:
            fig = px.bar(
                df_grouped, x="total", y="categoria", orientation="h",
                text="total",
                title="Motivos de Cancelamento Ativo (Agrupados)",
                labels={"categoria": "", "total": "Nº de Cancelamentos"},
                color="total",
                color_continuous_scale="Reds",
            )
            fig.update_layout(height=400, showlegend=False, yaxis=dict(autorange="reversed"))
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.dataframe(
                df_grouped[["categoria", "total", "pct"]].rename(columns={
                    "categoria": "Motivo", "total": "Total", "pct": "% do Total"
                }),
                hide_index=True, use_container_width=True
            )

        st.markdown("""
        #### O problema real: não temos os motivos

        A maioria dos registros é **preenchimento inválido** ("aaaa...") ou
        genéricos ("Desativar", "Não renovar"). Isso mostra que:

        1. **O fluxo de cancelamento não coleta motivos de forma estruturada** — é texto livre
           que os operadores preenchem com qualquer coisa.
        2. **"pct no RA"** (paciente no Reclame Aqui/Procon) é o motivo operacional mais relevante.
        3. **Falecimentos** representam uma fatia real e precisam de tratamento específico no CRM.

        **Recomendação:** Implementar formulário de cancelamento com **opções fechadas**
        (múltipla escolha): *"Preço alto"*, *"Não usei o suficiente"*, *"Mudei de cidade"*,
        *"Encontrei alternativa melhor"*, *"Atendimento insatisfatório"*.
        Isso transforma o dado em inteligência acionável.
        """)

        with st.expander("📋 Ver motivos brutos (sem agrupamento)"):
            st.dataframe(df.rename(columns={"motivo": "Motivo", "total": "Total", "pct_do_total": "% Total"}),
                         hide_index=True, use_container_width=True)

    except Exception as e:
        st.error(f"Erro: {e}")

# ═══════════════════════════════════════════════════════════════════════
# TAB 3: TEMPO ATÉ PRIMEIRO USO
# ═══════════════════════════════════════════════════════════════════════
with tab3:
    try:
        df = pd.read_csv("results/tempo_primeiro_uso.csv")

        st.markdown("""
        #### Quando o paciente faz a primeira consulta após assinar?

        Uma hipótese forte: se o paciente não usar o plano na primeira semana,
        ele perde o ímpeto e a chance de virar hábito diminui drasticamente.
        """)

        col1, col2 = st.columns([3, 2])

        with col1:
            fig = go.Figure()

            fig.add_trace(go.Bar(
                x=df["faixa_primeiro_uso"],
                y=df["total_contratos"],
                name="Contratos",
                marker_color="rgba(99, 110, 250, 0.5)",
            ))

            fig.add_trace(go.Scatter(
                x=df["faixa_primeiro_uso"],
                y=df["churn_rate"],
                name="Churn (%)",
                mode="lines+markers+text",
                marker=dict(size=14, color="crimson"),
                line=dict(width=3, color="crimson"),
                yaxis="y2",
                text=df["churn_rate"].apply(lambda x: f"{x}%"),
                textposition="top center",
                textfont=dict(size=13, color="crimson"),
            ))

            fig.update_layout(
                title="Churn por Janela de Primeiro Uso",
                yaxis=dict(title="Contratos"),
                yaxis2=dict(title="Churn (%)", overlaying="y", side="right", range=[0, 100]),
                legend=dict(orientation="h", y=1.12),
                height=400,
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.dataframe(df.rename(columns={
                "faixa_primeiro_uso": "Faixa", "total_contratos": "Contratos",
                "churners": "Churners", "churn_rate": "Churn (%)", "media_dias": "Dias (Média)"
            }), hide_index=True, use_container_width=True)

        # Identificar faixas dinamicamente
        nunca_usou = df[df["faixa_primeiro_uso"].str.contains("nunca", case=False)]
        usou_7d = df[df["faixa_primeiro_uso"].str.contains("0-7", case=False)]
        usou_8_30 = df[df["faixa_primeiro_uso"].str.contains("8-30", case=False)]

        md_parts = ["#### Leitura\n"]

        if len(nunca_usou) > 0:
            row_nu = nunca_usou.iloc[0]
            md_parts.append(f"- **{row_nu['total_contratos']:,.0f} contratos nunca usaram** o plano → Churn **{row_nu['churn_rate']}%**")

        if len(usou_7d) > 0:
            row_7d = usou_7d.iloc[0]
            md_parts.append(f"- **{row_7d['total_contratos']:,.0f} contratos** usaram nos primeiros 7 dias (média: {row_7d['media_dias']:.0f} dias) → Churn **{row_7d['churn_rate']}%**")

        if len(usou_8_30) > 0:
            row_8_30 = usou_8_30.iloc[0]
            md_parts.append(f"- **{row_8_30['total_contratos']:,.0f} contratos** usaram entre 8-30 dias (média: {row_8_30['media_dias']:.0f} dias) → Churn **{row_8_30['churn_rate']}%**")

        md_parts.append("")
        md_parts.append("Todos os grupos têm churn alto (~73-76%). ")
        md_parts.append("O tempo de engajamento não é o fator dominante — ciclo do contrato e perfil demográfico pesam mais.")

        st.markdown("\n".join(md_parts))
    except Exception as e:
        st.error(f"Erro: {e}")

# ═══════════════════════════════════════════════════════════════════════
# TAB 4: WIN-BACK / REATIVAÇÃO
# ═══════════════════════════════════════════════════════════════════════
with tab4:
    try:
        df = pd.read_csv("results/winback_reativacoes.csv")

        st.markdown("""
        #### Win-back e reativações

        Reativar um paciente tem o mesmo efeito que adquirir um novo?
        Ou a experiência anterior gera fidelidade residual?
        """)

        fig = px.bar(
            df, x="tipo_venda", y="churn_rate", color="consumo",
            barmode="group", text_auto=".1f",
            title="Taxa de Re-Churn por Tipo de Transação e Consumo",
            labels={"tipo_venda": "Tipo de Venda", "churn_rate": "Churn (%)", "consumo": "Consumiu?"},
            color_discrete_map={"S": "#d62728", "N": "#1f77b4"},
            facet_col="ciclo",
        )
        fig.update_layout(height=450)
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(df.rename(columns={
            "tipo_venda": "Tipo Venda", "ciclo": "Ciclo", "consumo": "Consumo",
            "total_contratos": "Contratos", "churners": "Churners", "churn_rate": "Churn (%)"
        }), hide_index=True, use_container_width=True)

        st.markdown("""
        #### Resultado sobre win-back

        | Tipo de Venda | Ciclo | Consumo | Churn |
        |---|---|---|---|
        | Primeiro contrato | 1o | N | 60,6% |
        | Primeiro contrato | 1o | S | 59,2% |
        | Reativação | 1o | N | **59,0%** |
        | Reativação | 1o | S | **58,1%** |
        | Renovação | 1o | N | 59,1% |
        | Renovação | 1o | S | **56,2%** |
        | Renovação | 2o+ | N | **48,7%** |

        **Leitura:**
        - Reativações têm churn **praticamente igual** ao primeiro contrato (~58-60%).
          Trazer alguém de volta não gera fidelidade residual — é como vender pra um novo cliente.
        - Renovações no 1º ciclo que consomem já mostram alguma proteção (56,2% vs 59,1%).
        - A única classe que retém de verdade é a renovação do 2o+ contrato (48,7%).

        **Recomendação:** Campanhas de win-back só valem a pena se o custo de aquisição for
        menor que o CAC de um novo cliente. Se o custo for similar, melhor investir em reter
        quem já está ativo.
        """)
    except Exception as e:
        st.error(f"Erro: {e}")

# ═══════════════════════════════════════════════════════════════════════
# TAB 5: CHURN SILENCIOSO VS ATIVO
# ═══════════════════════════════════════════════════════════════════════
with tab5:
    try:
        df = pd.read_csv("results/churn_silencioso_vs_ativo.csv")

        st.markdown("""
        #### Churn silencioso vs ativo: perfis diferentes, ações diferentes

        Dois tipos de ex-paciente: o que ligou e pediu cancelamento, e o que simplesmente
        sumiu (cartão venceu, cobrança falhou, contrato morreu). Quem é quem?
        """)

        # Agrupar para comparação
        grouped = df.groupby("tipo_desfecho")["total_contratos"].sum().reset_index()

        col1, col2, col3 = st.columns(3)
        for _, row in grouped.iterrows():
            if row["tipo_desfecho"] == "retido":
                col1.metric("🟢 Retidos", f"{int(row['total_contratos']):,}")
            elif row["tipo_desfecho"] == "churn_silencioso":
                col2.metric("👻 Churn Silencioso", f"{int(row['total_contratos']):,}")
            else:
                col3.metric("📢 Churn Ativo", f"{int(row['total_contratos']):,}")

        # Sunburst por tipo
        fig_sun = px.sunburst(
            df, path=["tipo_desfecho", "ciclo", "faixa_idade", "dependentes"],
            values="total_contratos",
            title="Composição Demográfica por Tipo de Desfecho",
            color="tipo_desfecho",
            color_discrete_map={
                "retido": "#2ca02c", "churn_silencioso": "#ff7f0e", "churn_ativo": "#d62728"
            },
        )
        fig_sun.update_layout(height=550)
        st.plotly_chart(fig_sun, use_container_width=True)

        # Comparação de perfis
        st.subheader("Perfil Comparado: Quem é o Churner Silencioso?")

        # Para cada tipo de desfecho, calcular distribuição por dimensão
        for dim, dim_label in [("ciclo", "Ciclo do Contrato"), ("faixa_idade", "Faixa Etária"),
                                ("dependentes", "Dependentes"), ("consumo", "Consumo")]:
            dim_grouped = df.groupby(["tipo_desfecho", dim])["total_contratos"].sum().reset_index()
            totals = dim_grouped.groupby("tipo_desfecho")["total_contratos"].transform("sum")
            dim_grouped["pct"] = round(100 * dim_grouped["total_contratos"] / totals, 1)

            fig = px.bar(
                dim_grouped, x=dim, y="pct", color="tipo_desfecho",
                barmode="group", text_auto=".1f",
                title=f"Distribuição por {dim_label}",
                labels={dim: dim_label, "pct": "% do Grupo", "tipo_desfecho": "Desfecho"},
                color_discrete_map={
                    "retido": "#2ca02c", "churn_silencioso": "#ff7f0e", "churn_ativo": "#d62728"
                },
            )
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("""
        #### Perfil do churner silencioso

        **Silencioso:**
        - Maior proporção de **1º contrato** — churn passivo, sem rejeição ativa
        - Leve concentração em **31-50 e 51-70 anos**
        - **Maior proporção de quem consome (S)** — usaram o plano mas provavelmente
          tiveram falha na cobrança automática do cartão

        **Ativo:**
        - Perfil mais diversificado em faixa etária
        - Proporção relevante de **2o+ contrato** — conhecem o produto e
          deliberadamente decidiram que não vale mais a pena

        **Retido:**
        - Concentração em **2o+ contrato + 3+ dependentes + 51-70 anos**
        - Família madura com necessidade contínua de saúde

        **Ações:**
        - Para silenciosos: régua de SMS/WhatsApp pré-vencimento + oferta de desconto
        - Para ativos: entrevista de saída estruturada + oferta de reativação em 30 dias
        """)
    except Exception as e:
        st.error(f"Erro: {e}")

# ═══════════════════════════════════════════════════════════════════════
# INTERAÇÃO CICLO × DEPENDENTES × CRÔNICO (bonus inline)
# ═══════════════════════════════════════════════════════════════════════
st.markdown("---")
st.subheader("Interação: ciclo × dependentes × crônico")
st.markdown("""
As 3 variáveis se somam ou se anulam? Se um paciente é crônico mas está no 1º contrato,
o que pesa mais? Cruzamos as 3 de maior impacto.
""")

try:
    df_int = pd.read_csv("results/interacao_contrato_dep_cronico.csv")

    fig = px.bar(
        df_int, x="dependentes", y="churn_rate", color="cronico",
        barmode="group", facet_col="ciclo", text_auto=".1f",
        title="Churn por Ciclo × Dependentes × Crônico",
        labels={"dependentes": "Dependentes", "churn_rate": "Churn (%)", "cronico": "Crônico?"},
        color_discrete_map={"S": "#2ca02c", "N": "#d62728"},
    )
    fig.update_layout(height=450)
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(df_int.rename(columns={
        "ciclo": "Ciclo", "dependentes": "Dependentes", "cronico": "Crônico",
        "total_contratos": "Contratos", "churners": "Churners", "churn_rate": "Churn (%)"
    }), hide_index=True, use_container_width=True)

    st.markdown("""
    #### Aditividade confirmada

    Os efeitos são aditivos — cada variável contribui independentemente:

    | Perfil | Churn | Observação |
    |---|---|---|
    | 1o + sem dep. + não crônico | **65,0%** | Pior cenário |
    | 1o + 3+ dep. + crônico | **50,8%** | Família + crônico já protege no 1º contrato |
    | 2o+ + sem dep. + não crônico | **54,2%** | Renovação sozinha já reduz ~10 p.p. |
    | 2o+ + 3+ dep. + crônico | **42,1%** | Melhor cenário — queda de 22,9 p.p. vs o pior |

    **Decomposição do efeito:**
    - Ciclo (1o → 2o+): ~**10 p.p.**
    - Dependentes (sem → 3+): ~**8-10 p.p.**
    - Crônico (N → S): ~**4-6 p.p.**

    **Implicação:** Reter o 1º contrato (mover pra 2o+) é a alavanca de maior ROI.
    """)
except Exception as e:
    st.error(f"Erro: {e}")
