"""
Página 8 — Insights para o Negócio
===================================
Análises acionáveis pedidas pelos times de Growth, Produto e CRM.
Responde a 4 perguntas:
  1. Por que os pacientes não renovam? (motivos + ativo vs silencioso)
  2. O grupo de pior score consome o quê?
  3. Quando retido, o que o paciente fez aqui?
  4. Qual especialidade gera vínculo (retenção)?
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

# ═══════════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════════
st.set_page_config(page_title="Insights para o Negócio", page_icon="💡", layout="wide")
st.title("💡 Insights para o Negócio")
st.markdown("Análises acionáveis para os times de **Growth**, **Produto** e **CRM**.")


# ═══════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════
@st.cache_data
def load_motivos():
    df = pd.read_csv("results/motivos_churn.csv")
    # Criar categoria simplificada
    mapping = {
        "Renovado: Continuou": "✅ Renovado",
        "Vencido Corretamente: Cancelado": "🔴 Cancelou voluntariamente",
        "Vencido Corretamente: Compra Avulsa Não-Recorrente": "⚫ Compra avulsa (não recorrente)",
        "Vencido Corretamente: Meio de Pagamento Manual": "🟠 Pgto manual não efetuado",
        "Vencido Corretamente: Pagamento Recusado": "🟡 Pagamento recusado pelo banco",
        "ALERTA: Nenhuma tentativa recente encontrada": "⚠️ Sem tentativa de cobrança",
        "ERRO TÉCNICO: Cobrado (Adyen) mas não renovado": "🔧 Erro técnico (cobrou mas não renovou)",
        "ERRO TÉCNICO: Cobrado (Mundipagg) mas não renovado": "🔧 Erro técnico (cobrou mas não renovou)",
        "Investigar Manualmente": "❓ Investigar",
    }
    df["categoria"] = df["diagnostico"].map(mapping).fillna("❓ Investigar")

    # Tipo macro
    tipo_map = {
        "✅ Renovado": "Renovado",
        "🔴 Cancelou voluntariamente": "Churn Ativo",
        "⚫ Compra avulsa (não recorrente)": "Churn Passivo",
        "🟠 Pgto manual não efetuado": "Churn Passivo",
        "🟡 Pagamento recusado pelo banco": "Churn Passivo",
        "⚠️ Sem tentativa de cobrança": "Churn Passivo",
        "🔧 Erro técnico (cobrou mas não renovou)": "Erro Técnico",
        "❓ Investigar": "Investigar",
    }
    df["tipo_churn"] = df["categoria"].map(tipo_map).fillna("Investigar")
    return df


@st.cache_data
def load_consumo_esp():
    return pd.read_csv("results/consumo_por_especialidade_a.csv")


@st.cache_data
def load_consumo_controlado():
    return pd.read_csv("results/consumo_controlado_ciclo.csv")


# ═══════════════════════════════════════════════════════════════════
# TAB LAYOUT
# ═══════════════════════════════════════════════════════════════════
tab1, tab2, tab3 = st.tabs([
    "🔍 Por que não renovam?",
    "📊 Consumo e Retenção",
    "🏥 Especialidades",
])


# ═══════════════════════════════════════════════════════════════════
# TAB 1: POR QUE NÃO RENOVAM?
# ═══════════════════════════════════════════════════════════════════
with tab1:
    motivos = load_motivos()
    total = len(motivos)
    nao_renovaram = motivos[motivos["categoria"] != "✅ Renovado"]
    renovaram = motivos[motivos["categoria"] == "✅ Renovado"]

    st.markdown("### Anatomia da não-renovação")
    st.markdown(f"""
    Análise de **{total:,} contratos** com vencimento em abril/2026.
    Identificamos exatamente *por que* cada contrato não renovou.
    """)

    # --- KPIs ---
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total de contratos", f"{total:,}")
    k2.metric("Renovaram", f"{len(renovaram):,}",
              delta=f"{100*len(renovaram)/total:.1f}%")
    k3.metric("Não renovaram", f"{len(nao_renovaram):,}",
              delta=f"{100*len(nao_renovaram)/total:.1f}%", delta_color="inverse")

    # Erro técnico
    erros = motivos[motivos["categoria"].str.contains("Erro técnico")]
    k4.metric("⚠️ Erro técnico", f"{len(erros):,}",
              delta="Cobrou mas não renovou!", delta_color="inverse",
              help="Contratos em que o gateway processou o pagamento com sucesso, mas o sistema não gerou a renovação. Requer investigação técnica urgente.")

    st.markdown("---")

    # --- Gráfico principal: Waterfall de motivos ---
    st.markdown("### Distribuição dos motivos")

    cat_counts = motivos["categoria"].value_counts().reset_index()
    cat_counts.columns = ["Categoria", "Contratos"]
    cat_counts["Pct"] = (100 * cat_counts["Contratos"] / total).round(1)
    cat_counts = cat_counts.sort_values("Contratos", ascending=True)

    # Cores por categoria
    color_map = {
        "✅ Renovado": "#27ae60",
        "🔴 Cancelou voluntariamente": "#c0392b",
        "🟡 Pagamento recusado pelo banco": "#f39c12",
        "🟠 Pgto manual não efetuado": "#e67e22",
        "⚫ Compra avulsa (não recorrente)": "#7f8c8d",
        "⚠️ Sem tentativa de cobrança": "#8e44ad",
        "🔧 Erro técnico (cobrou mas não renovou)": "#e74c3c",
        "❓ Investigar": "#95a5a6",
    }
    colors = [color_map.get(c, "#95a5a6") for c in cat_counts["Categoria"]]

    fig_motivos = go.Figure()
    fig_motivos.add_trace(go.Bar(
        y=cat_counts["Categoria"],
        x=cat_counts["Contratos"],
        orientation="h",
        marker_color=colors,
        text=cat_counts.apply(lambda r: f'{r["Contratos"]:,} ({r["Pct"]}%)', axis=1),
        textposition="outside",
        textfont=dict(size=13),
    ))
    fig_motivos.update_layout(
        title="Por que os contratos não renovaram?",
        xaxis_title="Número de contratos",
        height=400,
        margin=dict(l=10, r=120),
        yaxis=dict(automargin=True),
        showlegend=False,
    )
    st.plotly_chart(fig_motivos, use_container_width=True)

    # --- Split: Churn Ativo vs Passivo ---
    st.markdown("---")
    st.markdown("### Churn Ativo vs Passivo")
    st.markdown("""
    - **Churn Ativo**: o paciente *escolheu* cancelar (unsubscription)
    - **Churn Passivo**: o paciente *não agiu* — o pagamento falhou, não pagou boleto/pix, ou ninguém cobrou
    - **Erro Técnico**: o pagamento foi processado com sucesso, mas o sistema não renovou o contrato
    """)

    tipo_counts = motivos[motivos["categoria"] != "✅ Renovado"]["tipo_churn"].value_counts()

    col_pie, col_insight = st.columns([1, 1])
    with col_pie:
        fig_tipo = go.Figure(data=[go.Pie(
            labels=tipo_counts.index,
            values=tipo_counts.values,
            hole=0.45,
            marker_colors=["#c0392b" if "Ativo" in l else "#f39c12" if "Passivo" in l
                           else "#e74c3c" if "Erro" in l else "#95a5a6"
                           for l in tipo_counts.index],
            textinfo="label+percent",
            textfont=dict(size=13),
        )])
        fig_tipo.update_layout(
            title="Composição do churn (excluindo renovados)",
            height=380, showlegend=False,
        )
        st.plotly_chart(fig_tipo, use_container_width=True)

    with col_insight:
        pct_passivo = 100 * tipo_counts.get("Churn Passivo", 0) / tipo_counts.sum()
        pct_ativo = 100 * tipo_counts.get("Churn Ativo", 0) / tipo_counts.sum()

        st.info(f"""
        **Insight principal:**

        **{pct_passivo:.0f}%** do churn é **passivo** — o paciente não agiu,
        o pagamento simplesmente falhou ou não foi efetuado.

        Isso significa que a maioria dos churners **não decidiu sair**.
        São oportunidades de **dunning** (retentativa), **régua de cobrança**
        e **atualização de cartão**.

        Apenas **{pct_ativo:.0f}%** cancelou ativamente.
        """)

    # --- Detalhamento do pagamento recusado ---
    st.markdown("---")
    st.markdown("### Detalhamento: Pagamento Recusado")

    pgto_recusado = motivos[motivos["diagnostico"] == "Vencido Corretamente: Pagamento Recusado"]

    if len(pgto_recusado) > 0 and "ultima_tentativa_motivo_recusa" in pgto_recusado.columns:
        motivos_recusa = pgto_recusado["ultima_tentativa_motivo_recusa"].fillna("(sem detalhe)").value_counts().head(15)

        fig_recusa = go.Figure()
        fig_recusa.add_trace(go.Bar(
            y=motivos_recusa.index[::-1],
            x=motivos_recusa.values[::-1],
            orientation="h",
            marker_color="#f39c12",
            text=[f"{v:,}" for v in motivos_recusa.values[::-1]],
            textposition="outside",
        ))
        fig_recusa.update_layout(
            title=f"Top 15 motivos de recusa ({len(pgto_recusado):,} contratos)",
            xaxis_title="Contratos",
            height=450,
            margin=dict(l=10, r=80),
            yaxis=dict(automargin=True),
            showlegend=False,
        )
        st.plotly_chart(fig_recusa, use_container_width=True)

        st.caption("""
        **Como interpretar:** Motivos como "Insufficient Funds" ou "Refused" indicam
        problemas do lado do paciente (cartão vencido, limite). Já "Acquirer Error" ou
        "Issuer Unavailable" são problemas técnicos do lado do banco/adquirente.
        """)

    # --- Erros técnicos ---
    if len(erros) > 0:
        st.markdown("---")
        st.markdown("### ⚠️ Alerta: Erros Técnicos")
        st.error(f"""
        **{len(erros)} contratos** foram cobrados com sucesso pelo gateway
        (Adyen ou Mundipagg), mas o contrato **não foi renovado** no sistema.

        Isso representa **receita perdida** e requer investigação técnica urgente.
        """)

        # Breakdown por acquirer
        if "diagnostico" in erros.columns:
            for diag, count in erros["diagnostico"].value_counts().items():
                st.write(f"- {diag}: **{count}** contratos")

    # --- Breakdown por meio de pagamento ---
    st.markdown("---")
    st.markdown("### Breakdown por meio de pagamento")

    if "payment_method" in motivos.columns:
        pgto_tipo = motivos.groupby(["payment_method", "tipo_churn"]).size().reset_index(name="contratos")
        pgto_total = motivos.groupby("payment_method").size().reset_index(name="total")
        pgto_tipo = pgto_tipo.merge(pgto_total, on="payment_method")
        pgto_tipo["pct"] = (100 * pgto_tipo["contratos"] / pgto_tipo["total"]).round(1)

        fig_pgto = px.bar(
            pgto_tipo[pgto_tipo["tipo_churn"] != "Renovado"],
            x="payment_method", y="contratos", color="tipo_churn",
            barmode="stack",
            color_discrete_map={
                "Churn Ativo": "#c0392b", "Churn Passivo": "#f39c12",
                "Erro Técnico": "#e74c3c", "Investigar": "#95a5a6"
            },
            labels={"payment_method": "Meio de Pagamento", "contratos": "Contratos",
                    "tipo_churn": "Tipo de Churn"},
        )
        fig_pgto.update_layout(
            title="Distribuição do churn por meio de pagamento",
            height=400,
        )
        st.plotly_chart(fig_pgto, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
# TAB 2: CONSUMO E RETENÇÃO
# ═══════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("### O consumo protege contra o churn?")
    st.markdown("""
    Analisamos se **usar o plano** (ter pelo menos uma consulta ou exame)
    reduz a probabilidade de cancelamento, **controlando pelo ciclo do contrato**
    e pela duração do plano.
    """)

    consumo_ctrl = load_consumo_controlado()

    if len(consumo_ctrl) > 0:
        # Pivotar para mostrar consumo vs não-consumo
        consumo_ctrl["label"] = consumo_ctrl["ciclo"] + " | " + consumo_ctrl["duracao"].astype(str) + "m"

        fig_consumo = go.Figure()

        for consumo_val, color, name in [("N", "#e74c3c", "Não consumiu"), ("S", "#27ae60", "Consumiu")]:
            sub = consumo_ctrl[consumo_ctrl["consumo"] == consumo_val].sort_values("label")
            fig_consumo.add_trace(go.Bar(
                x=sub["label"],
                y=sub["churn_rate"],
                name=name,
                marker_color=color,
                text=sub["churn_rate"].apply(lambda v: f"{v:.1f}%"),
                textposition="outside",
                textfont=dict(size=12),
            ))

        fig_consumo.update_layout(
            title="Churn por consumo, controlado por ciclo e duração",
            xaxis_title="Perfil (ciclo | duração)",
            yaxis_title="Taxa de churn (%)",
            barmode="group",
            height=420,
            yaxis=dict(range=[0, 75]),
            legend=dict(orientation="h", y=1.12),
        )
        st.plotly_chart(fig_consumo, use_container_width=True)

        # Calcular deltas
        st.markdown("#### Efeito protetor do consumo")
        deltas = []
        for label in consumo_ctrl["label"].unique():
            sub = consumo_ctrl[consumo_ctrl["label"] == label]
            row_s = sub[sub["consumo"] == "S"]
            row_n = sub[sub["consumo"] == "N"]
            if len(row_s) > 0 and len(row_n) > 0:
                delta = row_s.iloc[0]["churn_rate"] - row_n.iloc[0]["churn_rate"]
                deltas.append({
                    "Perfil": label,
                    "Churn (consumiu)": f'{row_s.iloc[0]["churn_rate"]:.1f}%',
                    "Churn (não consumiu)": f'{row_n.iloc[0]["churn_rate"]:.1f}%',
                    "Δ (p.p.)": f'{delta:+.1f}',
                    "Efeito": "🟢 Protege" if delta < 0 else "🔴 Confundido" if delta > 2 else "➡️ Neutro",
                })

        if deltas:
            st.dataframe(pd.DataFrame(deltas), hide_index=True, use_container_width=True)

            st.caption("""
            **Nota:** Quando controlamos por ciclo e duração, o consumo tem efeito **protetor**
            (reduz o churn) ou neutro. No 1o contrato com 12 meses, quem consumiu tem churn
            ~3 p.p. menor que quem não consumiu. Isso confirma que o score dinâmico (que inclui
            `consumo_sn`) captura um sinal real.
            """)

    st.markdown("---")
    st.markdown("### Perfil de consumo: 1o contrato vs renovação")
    st.markdown("""
    Pacientes no **1o contrato** consomem mais (estão explorando o plano),
    mas também cancelam mais. A partir do **2o+ contrato**, o consumo tende
    a ser mais recorrente e focado nas necessidades reais.
    """)

    # Consumo por especialidade
    consumo_esp = load_consumo_esp()

    if len(consumo_esp) > 0:
        pivot = consumo_esp.pivot(index="especialidade", columns="uso", values="churn_rate").reset_index()
        pivot["spread"] = pivot["usou"] - pivot["nao_usou"]
        pivot = pivot.sort_values("spread")

        total_usou = consumo_esp[consumo_esp["uso"] == "usou"].set_index("especialidade")["total"]
        pivot["volume"] = pivot["especialidade"].map(total_usou)

        fig_esp = go.Figure()
        fig_esp.add_trace(go.Bar(
            y=pivot["especialidade"],
            x=pivot["spread"],
            orientation="h",
            marker_color=[
                "#27ae60" if s <= 1 else "#f39c12" if s <= 4 else "#c0392b"
                for s in pivot["spread"]
            ],
            text=pivot.apply(
                lambda r: f'{r["spread"]:+.1f} p.p. ({int(r["volume"]):,} pacientes)', axis=1),
            textposition="outside",
            textfont=dict(size=11),
        ))
        fig_esp.add_vline(x=0, line_dash="dash", line_color="gray")
        fig_esp.update_layout(
            title="Spread de churn: quem usou vs. quem não usou cada especialidade",
            xaxis_title="Δ churn (p.p.) — positivo = usou e cancelou MAIS",
            height=550,
            margin=dict(l=10, r=140),
            yaxis=dict(automargin=True),
            showlegend=False,
        )
        st.plotly_chart(fig_esp, use_container_width=True)

        st.warning("""
        **⚠️ Atenção: Confounding!**
        O spread positivo **NÃO significa** que usar a especialidade causa churn.
        Significa que quem usa tende a ser do 1o contrato (que já tem churn alto).
        Quando controlamos por ciclo (ver gráfico acima), o consumo **protege**.

        **Especialidades com menor spread** (Cardiologista, Gastro, Urologista) são
        as que possivelmente **mais geram vínculo** — o efeito protetor supera o confounding.
        """)

        # Highlight specialties that likely protect
        st.markdown("#### 🏥 Especialidades com maior potencial de retenção")
        protege = pivot[pivot["spread"] <= 2.0].sort_values("spread")
        for _, row in protege.iterrows():
            st.write(f"- **{row['especialidade']}**: spread de apenas {row['spread']:+.1f} p.p. "
                     f"({int(row['volume']):,} pacientes usaram)")

        st.info("""
        **Recomendação:** Cardiologista, Gastroenterologista, Urologista e Oftalmologista
        são as especialidades com menor spread confundido — indicando que o vínculo criado
        pela consulta **compensa** o efeito do 1o contrato. São candidatas a ações de
        engajamento precoce.
        """)


# ═══════════════════════════════════════════════════════════════════
# TAB 3: ESPECIALIDADES — VISÃO DETALHADA
# ═══════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("### Mapa de especialidades × retenção")
    st.markdown("""
    Para cada especialidade, mostramos o **volume de pacientes que usaram**
    e o **impacto no churn**. Especialidades no quadrante inferior-direito
    (alto volume + baixo spread) são as mais estratégicas para ações de retenção.
    """)

    consumo_esp = load_consumo_esp()

    if len(consumo_esp) > 0:
        pivot = consumo_esp.pivot(index="especialidade", columns="uso", values=["churn_rate", "total"]).reset_index()
        pivot.columns = ["especialidade", "churn_nao", "churn_usou", "n_nao", "n_usou"]
        pivot["spread"] = pivot["churn_usou"] - pivot["churn_nao"]
        pivot["pct_usou"] = (100 * pivot["n_usou"] / (pivot["n_usou"] + pivot["n_nao"])).round(1)

        # Scatter: volume × spread
        fig_scatter = go.Figure()
        fig_scatter.add_trace(go.Scatter(
            x=pivot["pct_usou"],
            y=pivot["spread"],
            mode="markers+text",
            marker=dict(
                size=np.sqrt(pivot["n_usou"]) / 4,
                color=pivot["spread"],
                colorscale="RdYlGn_r",
                showscale=True,
                colorbar=dict(title="Δ churn (p.p.)"),
                line=dict(width=1, color="rgba(0,0,0,0.3)"),
                sizemin=8,
            ),
            text=pivot["especialidade"].str.replace("_", " ").str.title(),
            textposition="top center",
            textfont=dict(size=10),
            hovertext=pivot.apply(
                lambda r: f'{r["especialidade"]}<br>'
                          f'Usou: {int(r["n_usou"]):,} ({r["pct_usou"]}%)<br>'
                          f'Churn usou: {r["churn_usou"]:.1f}%<br>'
                          f'Churn não usou: {r["churn_nao"]:.1f}%<br>'
                          f'Spread: {r["spread"]:+.1f} p.p.', axis=1),
            hoverinfo="text",
        ))
        fig_scatter.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
        fig_scatter.add_annotation(
            x=pivot["pct_usou"].max() * 0.8, y=-0.5,
            text="🎯 Zona de retenção",
            showarrow=False, font=dict(size=12, color="green"),
        )
        fig_scatter.update_layout(
            title="Especialidades: % de adesão vs impacto no churn",
            xaxis_title="% dos contratos que usaram",
            yaxis_title="Δ churn (usou - não usou, p.p.)",
            height=500,
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

        st.markdown("---")
        st.markdown("### Tabela resumo")

        table_data = pivot[["especialidade", "n_usou", "pct_usou", "churn_nao", "churn_usou", "spread"]].copy()
        table_data.columns = ["Especialidade", "Pacientes que usaram", "% Adesão", "Churn (não usou)", "Churn (usou)", "Δ Spread"]
        table_data["Especialidade"] = table_data["Especialidade"].str.replace("_", " ").str.title()
        table_data = table_data.sort_values("Δ Spread")

        # Formatar antes de exibir (evita dependência de matplotlib)
        table_display = table_data.copy()
        table_display["Pacientes que usaram"] = table_display["Pacientes que usaram"].apply(lambda v: f"{v:,.0f}")
        table_display["% Adesão"] = table_display["% Adesão"].apply(lambda v: f"{v:.1f}%")
        table_display["Churn (não usou)"] = table_display["Churn (não usou)"].apply(lambda v: f"{v:.1f}%")
        table_display["Churn (usou)"] = table_display["Churn (usou)"].apply(lambda v: f"{v:.1f}%")
        table_display["Δ Spread"] = table_display["Δ Spread"].apply(lambda v: f"{v:+.1f} p.p.")

        st.dataframe(table_display, hide_index=True, use_container_width=True)

        st.markdown("---")
        st.markdown("### 🎯 Conclusões para o negócio")

        st.success("""
        **1. Especialidades que geram vínculo (menor spread confundido):**
        - Cardiologista (+0.2 p.p.) → consulta regular cria dependência
        - Gastroenterologista (+0.8 p.p.) → acompanhamento contínuo
        - Urologista (+1.1 p.p.) → tratamentos de longo prazo
        - Oftalmologista (+1.2 p.p.) → necessidade recorrente (óculos, acompanhamento)

        **2. Especialidades com menor potencial de retenção (maior spread):**
        - CM Tele (+7.6 p.p.) → consulta rápida, pouco vínculo
        - Pediatra (+6.7 p.p.) → paciente pode ser 1o contrato explorando
        - Psiquiatria (+6.0 p.p.) → pode indicar churn por insatisfação

        **3. Recomendação:** Priorizar ações de engajamento precoce
        direcionando pacientes para especialidades de alto vínculo
        (Cardiologista, Gastro, Oftalmo) nos primeiros 90 dias do contrato.
        """)
