import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Conversão Pós-Falha · Churn", page_icon="💳", layout="wide")

# ═══════════════════════════════════════════════════════════════════════
st.title("💳 Capítulo 6 — Conversão pós-disparo de email (falha de pagamento)")
st.markdown("""
Em março e abril de 2026, o time de negócios disparou emails para **1.300 pacientes** cujo
pagamento por cartão falhou. O objetivo: recuperar a assinatura. Aqui avaliamos a efetividade
dessa ação — tanto na janela de 7 dias quanto no acumulado.
""")

with st.expander("📖 Sobre esta base de dados", expanded=False):
    st.markdown("""
    | Campo | Significado |
    |---|---|
    | `id_paciente` | Identificador único do paciente |
    | `data_envio` | Data do disparo do email (31/mar ou 02/abr 2026) |
    | `assinatura_7dias_sn` | Se o paciente assinou um plano nos 7 dias após o disparo |
    | `assinatura_pos_disparo_sn` | Se o paciente assinou um plano em qualquer momento após o disparo |
    | `dias_ate_assinatura` | Dias entre o disparo e a data da nova assinatura |
    | `plano_assinado` | Nome do plano contratado |
    | `forma_pagamento` | Método de pagamento usado na nova assinatura |

    **Ondas de disparo:**
    - **31/mar/2026**: 300 pacientes
    - **02/abr/2026**: 1.000 pacientes

    **Fonte:** Query cruzando IDs da base de disparo com `ref_yalo_subscriptions`.
    """)

# ═══════════════════════════════════════════════════════════════════════
# CARREGAMENTO DOS DADOS
# ═══════════════════════════════════════════════════════════════════════
@st.cache_data
def load_data():
    return pd.read_csv("results/conversao_apos_falha_pgto.csv")

try:
    df = load_data()
except FileNotFoundError:
    st.error("Arquivo `results/conversao_apos_falha_pgto.csv` não encontrado.")
    st.stop()

total = len(df)
conv_bruta = df[df["assinatura_pos_disparo_sn"] == "Sim"]
conv_7d_bruta = df[df["assinatura_7dias_sn"] == "Sim"]

# Separar grátis vs pago
conv_pago = conv_bruta[conv_bruta["plano_assinado"] != "cartao dr.consulta - gratis"]
conv_gratis = conv_bruta[conv_bruta["plano_assinado"] == "cartao dr.consulta - gratis"]
conv_pago_7d = conv_pago[conv_pago["dias_ate_assinatura"] <= 7]

# ═══════════════════════════════════════════════════════════════════════
# KPIs
# ═══════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("### Visão geral do disparo")

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("📧 Total de Disparos", f"{total:,}")
k2.metric("🔄 Conversão Bruta", f"{len(conv_bruta):,}",
          delta=f"{100*len(conv_bruta)/total:.1f}%")
k3.metric("🆓 Plano Grátis", f"{len(conv_gratis):,}",
          delta=f"{100*len(conv_gratis)/total:.1f}%", delta_color="off")
k4.metric("💰 Plano Pago (total)", f"{len(conv_pago):,}",
          delta=f"{100*len(conv_pago)/total:.1f}%")
k5.metric("💰 Plano Pago (7 dias)", f"{len(conv_pago_7d):,}",
          delta=f"{100*len(conv_pago_7d)/total:.1f}%")

st.markdown("""
> **Atenção na leitura:** A taxa bruta de 61% inclui **685 assinaturas do plano grátis**.
> A métrica que importa para o negócio é a conversão para **plano pago**: **{pago_pct}%** no total
> e **{pago_7d_pct}%** em 7 dias.
""".format(
    pago_pct=round(100*len(conv_pago)/total, 1),
    pago_7d_pct=round(100*len(conv_pago_7d)/total, 1)
))

# ═══════════════════════════════════════════════════════════════════════
# PERFIL DO CONTRATO ORIGINAL (6m vs 12m)
# ═══════════════════════════════════════════════════════════════════════
if "duracao_plano_original" in df.columns:
    st.markdown("---")
    st.markdown("### Perfil do contrato original (antes da falha)")
    st.markdown("""
    Dos pacientes que receberam o email de recuperação, qual era a duração do contrato
    que teve a falha de pagamento?
    """)

    dur_dist = df["duracao_plano_original"].fillna("Não identificado").astype(str)
    dur_dist = dur_dist.apply(lambda x: f"{int(float(x))}m" if x not in ["Não identificado", "nan"] else x)
    dur_counts = dur_dist.value_counts().reset_index()
    dur_counts.columns = ["Duração", "Qtd"]
    dur_counts["% do Total"] = round(100 * dur_counts["Qtd"] / total, 1)

    # Métricas
    dur_cols = st.columns(len(dur_counts))
    for i, row in dur_counts.iterrows():
        dur_cols[i].metric(
            f"📋 {row['Duração']}",
            f"{row['Qtd']:,}",
            delta=f"{row['% do Total']}%",
            delta_color="off"
        )

    # Gráfico
    col_dur1, col_dur2 = st.columns([2, 3])

    with col_dur1:
        fig_dur = px.pie(
            dur_counts, values="Qtd", names="Duração",
            title="Distribuição por Duração do Contrato Original",
            color_discrete_sequence=["#1565c0", "#42a5f5", "#90caf9", "#bbdefb"],
            hole=0.4,
        )
        fig_dur.update_layout(height=350)
        fig_dur.update_traces(textinfo="label+value+percent")
        st.plotly_chart(fig_dur, use_container_width=True)

    with col_dur2:
        # Converter para análise: taxa de conversão paga por duração
        if "duracao_plano_original" in df.columns:
            df_dur_conv = df.copy()
            df_dur_conv["dur_label"] = df_dur_conv["duracao_plano_original"].fillna(-1).apply(
                lambda x: f"{int(x)}m" if x > 0 else "Não identificado"
            )
            dur_conv = []
            for dur, g in df_dur_conv.groupby("dur_label"):
                n = len(g)
                conv_g = g[g["assinatura_pos_disparo_sn"] == "Sim"]
                gratis_g = conv_g[conv_g["plano_assinado"] == "cartao dr.consulta - gratis"]
                pago_g = conv_g[conv_g["plano_assinado"] != "cartao dr.consulta - gratis"]
                dur_conv.append({
                    "Duração Original": dur,
                    "Total": n,
                    "Conv. Bruta": len(conv_g),
                    "Conv. Bruta (%)": round(100*len(conv_g)/n, 1),
                    "Plano Grátis": len(gratis_g),
                    "Plano Pago": len(pago_g),
                    "Pago (%)": round(100*len(pago_g)/n, 1),
                })
            df_dur_conv_tbl = pd.DataFrame(dur_conv).sort_values("Total", ascending=False)
            st.dataframe(df_dur_conv_tbl, use_container_width=True, hide_index=True)

            st.markdown("""
            **Leitura:** A tabela acima mostra, para cada duração do contrato original que falhou,
            quantos pacientes converteram para plano pago após o disparo do email.
            """)

# ═══════════════════════════════════════════════════════════════════════
# ANÁLISE POR ONDA DE DISPARO
# ═══════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("### Resultado por onda de disparo")

ondas = []
for d, g in df.groupby("data_envio"):
    n = len(g)
    conv_g = g[g["assinatura_pos_disparo_sn"] == "Sim"]
    gratis_g = conv_g[conv_g["plano_assinado"] == "cartao dr.consulta - gratis"]
    pago_g = conv_g[conv_g["plano_assinado"] != "cartao dr.consulta - gratis"]
    pago_7d_g = pago_g[pago_g["dias_ate_assinatura"] <= 7]

    ondas.append({
        "Data do Disparo": d,
        "Disparos": n,
        "Conversão Bruta": len(conv_g),
        "Taxa Bruta (%)": round(100*len(conv_g)/n, 1),
        "Plano Grátis": len(gratis_g),
        "Grátis (%)": round(100*len(gratis_g)/n, 1),
        "Plano Pago": len(pago_g),
        "Pago (%)": round(100*len(pago_g)/n, 1),
        "Pago em 7d": len(pago_7d_g),
        "Pago 7d (%)": round(100*len(pago_7d_g)/n, 1),
    })

df_ondas = pd.DataFrame(ondas)
st.dataframe(df_ondas, use_container_width=True, hide_index=True)

col1, col2 = st.columns(2)

with col1:
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_ondas["Data do Disparo"], y=df_ondas["Grátis (%)"],
        name="Grátis (%)", marker_color="#ff9800",
    ))
    fig.add_trace(go.Bar(
        x=df_ondas["Data do Disparo"], y=df_ondas["Pago (%)"],
        name="Pago (%)", marker_color="#4caf50",
    ))
    fig.update_layout(
        title="Taxa de Conversão por Onda",
        barmode="stack", yaxis_title="% dos disparos",
        height=400, legend=dict(orientation="h", y=1.12),
    )
    st.plotly_chart(fig, use_container_width=True)

with col2:
    fig2 = go.Figure(data=[go.Pie(
        labels=["Não converteu", "Plano Grátis", "Plano Pago"],
        values=[total - len(conv_bruta), len(conv_gratis), len(conv_pago)],
        marker_colors=["#e0e0e0", "#ff9800", "#4caf50"],
        textinfo="label+value+percent",
        hole=0.4,
    )])
    fig2.update_layout(title="Distribuição dos 1.300 disparos", height=400)
    st.plotly_chart(fig2, use_container_width=True)

st.markdown("""
**Leitura:**
- A 1ª onda (31/mar, 300 disparos) teve **75% de conversão para grátis** e **6,7% para pago**.
- A 2ª onda (02/abr, 1.000 disparos) teve **46% grátis** e **8,9% para pago**.
- O plano grátis domina as conversões — possível que seja uma oferta automática ou
  extensão de carência. **Isso precisa ser validado com o time de produto.**
""")

# ═══════════════════════════════════════════════════════════════════════
# CURVA DE CONVERSÃO POR DIA
# ═══════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("### Curva de conversão: quando o paciente assina?")

conv_dias = conv_bruta.copy()
conv_dias["tipo_plano"] = conv_dias["plano_assinado"].apply(
    lambda x: "Grátis" if x == "cartao dr.consulta - gratis" else "Pago"
)

dias_dist = conv_dias.groupby(["dias_ate_assinatura", "tipo_plano"]).size().reset_index(name="conversoes")

fig3 = px.bar(
    dias_dist, x="dias_ate_assinatura", y="conversoes", color="tipo_plano",
    barmode="stack",
    title="Conversões por Dia Após o Disparo",
    labels={"dias_ate_assinatura": "Dias após disparo", "conversoes": "Conversões", "tipo_plano": "Tipo"},
    color_discrete_map={"Grátis": "#ff9800", "Pago": "#4caf50"},
)

# Adicionar linha vertical nos 7 dias
fig3.add_vline(x=7.5, line_dash="dash", line_color="red",
               annotation_text="Janela de 7 dias", annotation_position="top right")
fig3.update_layout(height=450, xaxis=dict(dtick=1))
st.plotly_chart(fig3, use_container_width=True)

st.markdown("""
**Dois padrões completamente diferentes:**

1. **Plano pago**: conversão forte nos **dias 0-7** (87% das conversões pagas acontecem na 1ª semana).
   Quem vai pagar, decide rápido. Média: **3-5 dias**.

2. **Plano grátis**: concentrado nos **dias 5-12**, com pico nos dias 9-11.
   Provável mecanismo automático (extensão de vigência ou carência) — não parece ser decisão ativa do paciente.
""")

# ── CURVA ACUMULADA ──────────────────────────────────────────────────
st.markdown("#### Curva acumulada: velocidade de conversão")

all_dias = list(range(0, 13))

# Acumular conversões por dia para cada tipo
acum_pago = []
acum_gratis = []
acum_total_conv = []
for d in all_dias:
    n_pago = len(conv_pago[conv_pago["dias_ate_assinatura"] <= d])
    n_gratis = len(conv_gratis[conv_gratis["dias_ate_assinatura"] <= d])
    acum_pago.append(n_pago)
    acum_gratis.append(n_gratis)
    acum_total_conv.append(n_pago + n_gratis)

fig_acum = go.Figure()

fig_acum.add_trace(go.Scatter(
    x=all_dias, y=[round(100 * v / total, 1) for v in acum_gratis],
    name="Grátis (acumulado)",
    mode="lines+markers",
    fill="tozeroy",
    fillcolor="rgba(255, 152, 0, 0.15)",
    line=dict(color="#ff9800", width=2.5),
    marker=dict(size=7),
    hovertemplate="Dia %{x}: %{y}% (%{customdata} pacientes)<extra>Grátis</extra>",
    customdata=acum_gratis,
))

fig_acum.add_trace(go.Scatter(
    x=all_dias, y=[round(100 * v / total, 1) for v in acum_pago],
    name="Pago (acumulado)",
    mode="lines+markers",
    fill="tozeroy",
    fillcolor="rgba(76, 175, 80, 0.2)",
    line=dict(color="#4caf50", width=2.5),
    marker=dict(size=7),
    hovertemplate="Dia %{x}: %{y}% (%{customdata} pacientes)<extra>Pago</extra>",
    customdata=acum_pago,
))

fig_acum.add_vline(x=7, line_dash="dash", line_color="red", line_width=1.5,
                   annotation_text="Janela 7d", annotation_position="top left",
                   annotation_font_size=11, annotation_font_color="red")

fig_acum.update_layout(
    title="Conversão Acumulada (% da base de 1.300 disparos)",
    xaxis=dict(title="Dias após o disparo", dtick=1, range=[-0.3, 12.3]),
    yaxis=dict(title="% da base convertida", ticksuffix="%"),
    height=420,
    legend=dict(orientation="h", y=1.12),
    hovermode="x unified",
)
st.plotly_chart(fig_acum, use_container_width=True)

# Métricas de velocidade
pago_ate_3d = len(conv_pago[conv_pago["dias_ate_assinatura"] <= 3])
pago_ate_7d = len(conv_pago[conv_pago["dias_ate_assinatura"] <= 7])
gratis_ate_7d = len(conv_gratis[conv_gratis["dias_ate_assinatura"] <= 7])
pago_total_n = len(conv_pago)
gratis_total_n = len(conv_gratis)

mc1, mc2, mc3 = st.columns(3)
mc1.metric("Pago até dia 3",
           f"{pago_ate_3d} de {pago_total_n}",
           delta=f"{round(100*pago_ate_3d/max(pago_total_n,1))}% do total pago")
mc2.metric("Pago até dia 7",
           f"{pago_ate_7d} de {pago_total_n}",
           delta=f"{round(100*pago_ate_7d/max(pago_total_n,1))}% do total pago")
mc3.metric("Grátis até dia 7",
           f"{gratis_ate_7d} de {gratis_total_n}",
           delta=f"{round(100*gratis_ate_7d/max(gratis_total_n,1))}% do total grátis",
           delta_color="off")

st.markdown("""
**O gráfico acima deixa evidente:**
- A curva do **pago** sobe rápido e estabiliza no dia 7 — praticamente toda a conversão paga já aconteceu.
- A curva do **grátis** só começa a subir a partir do dia 5 e dispara entre os dias 8-12 —
  reforça a hipótese de processo automático ou batch.
- **Se o objetivo é maximizar conversão paga, a janela de ação é de 0-7 dias.**
  Após isso, follow-up tem retorno marginal pra plano pago.
""")

# ═══════════════════════════════════════════════════════════════════════
# DETALHE DOS PLANOS PAGOS
# ═══════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("### Detalhe dos planos pagos")

if len(conv_pago) > 0:
    col_plano, col_pgto = st.columns(2)

    with col_plano:
        plano_dist = conv_pago["plano_assinado"].value_counts().reset_index()
        plano_dist.columns = ["Plano", "Conversões"]
        plano_dist["% do Total Pago"] = round(100 * plano_dist["Conversões"] / len(conv_pago), 1)

        fig4 = px.bar(
            plano_dist, x="Conversões", y="Plano", orientation="h",
            text="Conversões", title="Planos Pagos Contratados",
            color_discrete_sequence=["#4caf50"],
        )
        fig4.update_layout(height=300, yaxis=dict(autorange="reversed"))
        fig4.update_traces(textposition="outside")
        st.plotly_chart(fig4, use_container_width=True)

    with col_pgto:
        pgto_dist = conv_pago["forma_pagamento"].fillna("(não informado)").value_counts().reset_index()
        pgto_dist.columns = ["Forma Pagamento", "Conversões"]

        fig5 = px.pie(
            pgto_dist, values="Conversões", names="Forma Pagamento",
            title="Forma de Pagamento dos Planos Pagos",
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig5.update_layout(height=300)
        st.plotly_chart(fig5, use_container_width=True)

    st.markdown(f"""
    | Plano | Conversões | % do Pago |
    |---|---|---|
    | Anual (com/sem odonto) | {len(conv_pago[conv_pago['plano_assinado'].str.contains('anual')])} | {round(100*len(conv_pago[conv_pago['plano_assinado'].str.contains('anual')])/len(conv_pago),1)}% |
    | Semestral | {len(conv_pago[conv_pago['plano_assinado'].str.contains('semestral')])} | {round(100*len(conv_pago[conv_pago['plano_assinado'].str.contains('semestral')])/len(conv_pago),1)}% |

    **Observações:**
    - **{round(100*len(conv_pago[conv_pago['plano_assinado'].str.contains('anual')])/len(conv_pago),1)}% escolheram plano anual** (com ou sem odonto) — boa notícia para LTV.
    - **{round(100*len(conv_pago[conv_pago['forma_pagamento']=='credit_card'])/len(conv_pago),1)}% pagaram com cartão de crédito** — coerente, já que o motivo da falha era cartão.
    - Pix, boleto e débito são residuais.
    """)

# ═══════════════════════════════════════════════════════════════════════
# CONCLUSÕES E RECOMENDAÇÕES
# ═══════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("### Conclusões e recomendações")

st.markdown(f"""
**Resultado da ação:**
- De 1.300 disparos, **{len(conv_pago)} pacientes ({round(100*len(conv_pago)/total,1)}%) assinaram um plano pago**.
- **{len(conv_pago_7d)} ({round(100*len(conv_pago_7d)/total,1)}%)** converteram nos primeiros 7 dias.
- A maioria das conversões "brutas" ({len(conv_gratis)}, {round(100*len(conv_gratis)/total,1)}%) são adesões ao **plano grátis**,
  que precisam ser investigadas: é extensão automática de carência ou decisão do paciente?

**O que podemos concluir:**

1. **A conversão para plano pago é baixa, mas real ({round(100*len(conv_pago)/total,1)}%).**
   Em escala — se 10.000 pacientes receberem esse disparo — estamos falando de ~{round(10000*len(conv_pago)/total)} assinaturas recuperadas.
   Se o ticket médio mensal for R$100-150, o ROI do email é significativo.

2. **A janela de 7 dias captura {round(100*len(conv_pago_7d)/max(len(conv_pago),1))}% das conversões pagas.**
   A decisão de pagar é rápida. Réguas de follow-up além de 7 dias provavelmente não valem o esforço
   para conversão paga — mas podem valer para o plano grátis.

3. **O plano grátis é um sinal ambíguo.**
   Se for uma extensão automática: não é conversão real, é mecanismo de sistema.
   Se for oferta ativa: dá pra medir se esses pacientes eventualmente migram pra plano pago.

**Próximos passos sugeridos:**
- Validar com produto o que é o "cartão dr.consulta - gratis" (automático vs escolha do paciente?)
- Medir se os {len(conv_gratis)} que entraram no grátis eventualmente migram pra pago
- Testar variações de copy/oferta no email pra aumentar a taxa de {round(100*len(conv_pago)/total,1)}%
- Considerar SMS/WhatsApp como canal complementar (o email pode não ser aberto)
""")

# ═══════════════════════════════════════════════════════════════════════
# DADOS BRUTOS
# ═══════════════════════════════════════════════════════════════════════
with st.expander("📋 Ver dados individuais", expanded=False):
    filtro = st.selectbox("Filtrar por:", ["Todos", "Converteu (pago)", "Converteu (grátis)", "Não converteu"])

    if filtro == "Converteu (pago)":
        df_show = conv_pago
    elif filtro == "Converteu (grátis)":
        df_show = conv_gratis
    elif filtro == "Não converteu":
        df_show = df[df["assinatura_pos_disparo_sn"] == "Nao"]
    else:
        df_show = df

    st.dataframe(df_show, use_container_width=True, hide_index=True)
    st.caption(f"Mostrando {len(df_show)} de {total} registros")
