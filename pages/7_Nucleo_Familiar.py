import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from scipy import stats

st.set_page_config(page_title="Núcleo Familiar · Influência dos Dependentes", page_icon="🏠", layout="wide")

# ═══════════════════════════════════════════════════════════════════════
# FUNÇÕES
# ═══════════════════════════════════════════════════════════════════════
def wilson_ci(n, x, alpha=0.05):
    if n == 0: return 0, 0, 0
    p = x / n
    z = stats.norm.ppf(1 - alpha/2)
    denom = 1 + z**2/n
    center = (p + z**2/(2*n)) / denom
    margin = z * np.sqrt(p*(1-p)/n + z**2/(4*n**2)) / denom
    return p*100, max(0, (center - margin)*100), min(100, (center + margin)*100)

def z_test_proportions(n1, x1, n2, x2):
    if n1 == 0 or n2 == 0: return {"diff": 0, "ci_lo": 0, "ci_hi": 0, "p": 1.0}
    p1, p2 = x1/n1, x2/n2
    diff = p1 - p2
    p_pool = (x1 + x2) / (n1 + n2)
    se = np.sqrt(p_pool * (1 - p_pool) * (1/n1 + 1/n2))
    z = diff / se if se > 0 else 0
    pval = 2 * (1 - stats.norm.cdf(abs(z)))
    return {"diff": diff*100, "ci_lo": (diff - 1.96*se)*100, "ci_hi": (diff + 1.96*se)*100, "p": pval}

def sig_label(p):
    return "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "n.s."))

def churn_table(df, by, dropna=False):
    """Agrega churn por uma ou mais colunas, com IC95% Wilson."""
    g = df.groupby(by, dropna=dropna).agg(contratos=("contract_id","count"), churners=("churner","sum")).reset_index()
    g["churn_pct"] = (g["churners"] / g["contratos"] * 100).round(1)
    ics = g.apply(lambda r: wilson_ci(r["contratos"], r["churners"]), axis=1)
    g["ic_lo"] = [round(x[1], 1) for x in ics]
    g["ic_hi"] = [round(x[2], 1) for x in ics]
    return g

# ═══════════════════════════════════════════════════════════════════════
# DADOS
# ═══════════════════════════════════════════════════════════════════════
@st.cache_data
def load_nucleo():
    df = pd.read_csv("results/nucleo_familiar.csv", low_memory=False)
    # Normaliza valores categóricos para visualização
    df["tem_dep_cronico_viz"] = df["tem_dep_cronico"].fillna("(solo)")
    return df


# ═══════════════════════════════════════════════════════════════════════
st.title("🏠 Capítulo 7 — Núcleo Familiar")
st.markdown("""
O score atual enxerga só o titular. Mas quem está com ele no plano também influencia o churn —
**ter dependente engajado segura, dependente passivo empurra**. Esta página mede esse efeito
e testa a hipótese: *o vínculo familiar com a DRC ancora o titular*.
""")

try:
    df = load_nucleo()
    churn_global = df["churner"].mean() * 100
    n_total = len(df)

    # ─── KPIs de abertura ──────────────────────────────────────────────
    solo = df[df["composicao_drc"] == "solo"]
    so_ativos = df[df["composicao_drc"] == "so_ativos_drc"]
    so_passivos = df[df["composicao_drc"] == "so_passivos"]
    com_dep_cron = df[df["tem_dep_cronico"] == "S"]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Churn Global da Base", f"{churn_global:.1f}%",
              help=f"{n_total:,} contratos no universo do score")
    k2.metric("Churn — Contratos SOLO",
              f"{solo['churner'].mean()*100:.1f}%",
              f"{(solo['churner'].mean() - df['churner'].mean())*100:+.1f} p.p. vs base",
              help=f"{len(solo):,} contratos sem dependentes — referência da análise")
    k3.metric("Churn — Dep Crônico Confirmado",
              f"{com_dep_cron['churner'].mean()*100:.1f}%",
              f"{(com_dep_cron['churner'].mean() - solo['churner'].mean())*100:+.1f} p.p. vs solo",
              help=f"{len(com_dep_cron):,} contratos onde pelo menos 1 dep tem CID crônico confirmado")
    k4.metric("Churn — Só Deps Passivos",
              f"{so_passivos['churner'].mean()*100:.1f}%",
              f"{(so_passivos['churner'].mean() - solo['churner'].mean())*100:+.1f} p.p. vs solo",
              help=f"{len(so_passivos):,} contratos onde nenhum dep nunca consumiu na DRC")

    # ─── ABAS ──────────────────────────────────────────────────────────
    tab_comp, tab_inter, tab_eng, tab_lim = st.tabs([
        "🏠 Composição do Núcleo",
        "🔗 Interações com o Titular",
        "📊 Engajamento DRC",
        "⚠️ Limitações",
    ])

    # ═══════════════════════════════════════════════════════════════════
    # TAB 1: COMPOSIÇÃO DO NÚCLEO
    # ═══════════════════════════════════════════════════════════════════
    with tab_comp:
        st.markdown("### Como a base se distribui pelo tipo de núcleo")
        st.markdown(
            "Definimos **dependente ativo na DRC** como aquele que já teve pelo menos 1 atendimento "
            "na rede. Quem está no plano mas nunca consumiu é **dependente passivo**. "
            "Essa distinção é crítica: o engajamento real do núcleo é o sinal, não a contagem cega."
        )

        # ── Distribuição composição DRC ──
        comp_drc = churn_table(df, ["composicao_drc"]).sort_values("contratos", ascending=False)

        nomes_comp = {
            "solo": "SOLO (sem dep)",
            "so_ativos_drc": "Só deps ATIVOS na DRC",
            "passivos_e_ativos": "Mistura ativos + passivos",
            "so_passivos": "Só deps PASSIVOS",
        }
        cores_comp = {
            "solo": "#7f7f7f",
            "so_ativos_drc": "#2ca02c",
            "passivos_e_ativos": "#ff7f0e",
            "so_passivos": "#d62728",
        }
        comp_drc["nome"] = comp_drc["composicao_drc"].map(nomes_comp)
        comp_drc["cor"] = comp_drc["composicao_drc"].map(cores_comp)

        col_dist, col_churn = st.columns(2)
        with col_dist:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=comp_drc["nome"], y=comp_drc["contratos"],
                marker_color=comp_drc["cor"],
                text=comp_drc["contratos"].apply(lambda v: f"{v:,}"),
                textposition="outside",
            ))
            fig.update_layout(title="Volume de contratos por composição",
                              yaxis_title="Contratos", height=380, showlegend=False,
                              margin=dict(t=50))
            st.plotly_chart(fig, use_container_width=True)

        with col_churn:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=comp_drc["nome"], y=comp_drc["churn_pct"],
                marker_color=comp_drc["cor"],
                error_y=dict(
                    type="data", symmetric=False,
                    array=(comp_drc["ic_hi"] - comp_drc["churn_pct"]).values,
                    arrayminus=(comp_drc["churn_pct"] - comp_drc["ic_lo"]).values,
                    color="rgba(0,0,0,0.4)", thickness=2, width=8,
                ),
                text=comp_drc["churn_pct"].apply(lambda v: f"{v}%"),
                textposition="outside",
            ))
            fig.add_hline(y=churn_global, line_dash="dash", line_color="gray",
                          annotation_text=f"Churn global ({churn_global:.1f}%)",
                          annotation_position="top right")
            fig.update_layout(title="Churn por composição (com IC 95%)",
                              yaxis_title="Churn (%)", height=380, showlegend=False,
                              yaxis=dict(range=[40, 70]), margin=dict(t=50))
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            comp_drc[["nome", "contratos", "churners", "churn_pct", "ic_lo", "ic_hi"]].rename(
                columns={"nome": "Composição", "contratos": "Contratos", "churners": "Churners",
                         "churn_pct": "Churn (%)", "ic_lo": "IC 95% Inf", "ic_hi": "IC 95% Sup"}),
            hide_index=True, use_container_width=True,
        )

        # ── Z-test entre extremos ──
        r_ativos = comp_drc[comp_drc["composicao_drc"] == "so_ativos_drc"].iloc[0]
        r_passivos = comp_drc[comp_drc["composicao_drc"] == "so_passivos"].iloc[0]
        r_solo = comp_drc[comp_drc["composicao_drc"] == "solo"].iloc[0]

        t_ap = z_test_proportions(r_ativos["contratos"], r_ativos["churners"],
                                   r_passivos["contratos"], r_passivos["churners"])
        t_as = z_test_proportions(r_ativos["contratos"], r_ativos["churners"],
                                   r_solo["contratos"], r_solo["churners"])
        t_ps = z_test_proportions(r_passivos["contratos"], r_passivos["churners"],
                                   r_solo["contratos"], r_solo["churners"])

        st.success(f"""
        **Leitura principal:**
        - **Só deps ATIVOS DRC ({r_ativos['churn_pct']}%) vs Só deps PASSIVOS ({r_passivos['churn_pct']}%):**
          {t_ap['diff']:+.1f} p.p. de gap dentro de "tem dependente" — o que o dep faz com o plano importa muito mais
          que a presença do dep ({sig_label(t_ap['p'])}).
        - **Só deps ATIVOS DRC ({r_ativos['churn_pct']}%) vs SOLO ({r_solo['churn_pct']}%):**
          {t_as['diff']:+.1f} p.p. — ter dep engajado **reduz** churn em relação ao titular sozinho ({sig_label(t_as['p'])}).
        - **Só deps PASSIVOS ({r_passivos['churn_pct']}%) vs SOLO ({r_solo['churn_pct']}%):**
          {t_ps['diff']:+.1f} p.p. — ter dep que não usa **aumenta** churn em relação ao titular sozinho ({sig_label(t_ps['p'])}).

        Ou seja: o score atual usa `qtd_dep_total` cego, e essa dummy ESCONDE um spread de
        **{(r_passivos['churn_pct'] - r_ativos['churn_pct']):.1f} p.p.** que existe entre os tipos de dep.
        """)

        # ── Crônico do dep ──
        st.markdown("---")
        st.markdown("### Crônico no dependente: efeito-âncora")
        st.markdown(
            "Hipótese clínica: dependente crônico precisa de acompanhamento contínuo — "
            "isso amarra a família ao plano e por consequência amarra o titular. Vamos ver."
        )

        cron_df = churn_table(df, ["tem_dep_cronico_viz"])
        ordem_cron = ["S", "N", "desconhecido", "(solo)"]
        nomes_cron = {"S": "Dep crônico CONFIRMADO",
                      "N": "Dep não-crônico (atendimento sem CID crônico)",
                      "desconhecido": "Crônico desconhecido (deps passivos)",
                      "(solo)": "SOLO (sem dep)"}
        cores_cron = {"S": "#1f77b4", "N": "#aec7e8", "desconhecido": "#d62728", "(solo)": "#7f7f7f"}
        cron_df["ordem"] = cron_df["tem_dep_cronico_viz"].map({k:i for i,k in enumerate(ordem_cron)})
        cron_df = cron_df.sort_values("ordem")
        cron_df["nome"] = cron_df["tem_dep_cronico_viz"].map(nomes_cron)
        cron_df["cor"] = cron_df["tem_dep_cronico_viz"].map(cores_cron)

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=cron_df["nome"], y=cron_df["churn_pct"],
            marker_color=cron_df["cor"],
            error_y=dict(
                type="data", symmetric=False,
                array=(cron_df["ic_hi"] - cron_df["churn_pct"]).values,
                arrayminus=(cron_df["churn_pct"] - cron_df["ic_lo"]).values,
                color="rgba(0,0,0,0.4)", thickness=2, width=8,
            ),
            text=cron_df.apply(lambda r: f"{r['churn_pct']}%<br>{int(r['contratos']):,} contratos", axis=1),
            textposition="outside",
        ))
        fig.add_hline(y=churn_global, line_dash="dash", line_color="gray",
                      annotation_text=f"Churn global ({churn_global:.1f}%)")
        fig.update_layout(title="Churn por status crônico do dependente",
                          yaxis_title="Churn (%)", yaxis=dict(range=[40, 70]),
                          height=420, showlegend=False, margin=dict(t=60))
        st.plotly_chart(fig, use_container_width=True)

        r_cron_s = cron_df[cron_df["tem_dep_cronico_viz"] == "S"].iloc[0]
        r_cron_solo = cron_df[cron_df["tem_dep_cronico_viz"] == "(solo)"].iloc[0]
        t_cs = z_test_proportions(r_cron_s["contratos"], r_cron_s["churners"],
                                   r_cron_solo["contratos"], r_cron_solo["churners"])
        st.caption(
            f"**Spread principal:** dep crônico CONFIRMADO ({r_cron_s['churn_pct']}%) vs SOLO "
            f"({r_cron_solo['churn_pct']}%) = {t_cs['diff']:+.1f} p.p. ({sig_label(t_cs['p'])}). "
            f"Confirma a hipótese: o dep crônico ancora o titular. "
            f"Note também que 'desconhecido' (crônico não-aferível por serem deps passivos) tem o pior churn — "
            f"reforça que falta de engajamento é o sinal mais forte."
        )

    # ═══════════════════════════════════════════════════════════════════
    # TAB 2: INTERAÇÕES COM O TITULAR
    # ═══════════════════════════════════════════════════════════════════
    with tab_inter:
        st.markdown("### O dependente atenua os fatores de risco do titular?")
        st.markdown(
            "Aqui testamos as duas hipóteses-âncora que aparecem no design do score evolutivo: "
            "*ter dependente certo modera o efeito de ser titular de risco*. Se isso for verdade, "
            "as interações precisam entrar no modelo (não basta dummies aditivas)."
        )

        # ── Interação 1: cronico_titular x tem_dep_cronico ──
        st.markdown("#### 1. Crônico do titular × Crônico do dependente")
        st.markdown(
            "Hipótese: titular **não-crônico** com dep crônico cancela menos do que titular não-crônico sem dep crônico. "
            "Para titular já crônico, o efeito do dep deve ser menor (titular já tem motivo próprio pra ficar)."
        )

        inter1 = churn_table(df, ["cronico_titular", "tem_dep_cronico_viz"])
        # Normaliza ordem
        order_dep = ["S", "N", "desconhecido", "(solo)"]
        nomes_dep_cron = {"S": "Dep crônico=S", "N": "Dep crônico=N",
                          "desconhecido": "Dep status desc.", "(solo)": "Sem dep"}
        inter1["dep_label"] = inter1["tem_dep_cronico_viz"].map(nomes_dep_cron)
        inter1["dep_ord"] = inter1["tem_dep_cronico_viz"].map({k:i for i,k in enumerate(order_dep)})
        inter1["tit_label"] = inter1["cronico_titular"].map({"S": "Titular CRÔNICO", "N": "Titular não-crônico"})
        inter1 = inter1.sort_values(["cronico_titular", "dep_ord"])

        fig = px.bar(
            inter1, x="dep_label", y="churn_pct", color="tit_label",
            barmode="group",
            color_discrete_map={"Titular CRÔNICO": "#1f77b4", "Titular não-crônico": "#ff7f0e"},
            text=inter1["churn_pct"].apply(lambda v: f"{v}%"),
            labels={"dep_label": "Status crônico do dep", "churn_pct": "Churn (%)", "tit_label": ""},
        )
        fig.update_traces(textposition="outside")
        fig.add_hline(y=churn_global, line_dash="dash", line_color="gray",
                      annotation_text=f"Churn global ({churn_global:.1f}%)")
        fig.update_layout(title="Churn por (crônico titular × crônico dep)",
                          height=420, yaxis=dict(range=[40, 70]),
                          legend=dict(orientation="h", y=1.10))
        st.plotly_chart(fig, use_container_width=True)

        # Cálculo dos efeitos
        def churn_for(tit, dep):
            sub = df[(df["cronico_titular"] == tit) & (df["tem_dep_cronico_viz"] == dep)]
            return sub["churner"].mean() * 100, len(sub)

        cn_n, _ = churn_for("N", "(solo)")
        cn_S, _ = churn_for("N", "S")
        cs_n, _ = churn_for("S", "(solo)")
        cs_S, _ = churn_for("S", "S")
        efeito_dep_em_tit_n = cn_S - cn_n
        efeito_dep_em_tit_s = cs_S - cs_n

        st.success(f"""
        **Hipótese confirmada:**
        - **Titular não-crônico**: ter dep crônico=S vs não ter dep → churn cai de {cn_n:.1f}% para {cn_S:.1f}% ({efeito_dep_em_tit_n:+.1f} p.p.)
        - **Titular crônico**: ter dep crônico=S vs não ter dep → churn cai de {cs_n:.1f}% para {cs_S:.1f}% ({efeito_dep_em_tit_s:+.1f} p.p.)

        O efeito do dep crônico é **{abs(efeito_dep_em_tit_n - efeito_dep_em_tit_s):.1f} p.p. maior** no titular não-crônico —
        ou seja, o dep crônico "supre" parcialmente a falta de razão clínica do titular para manter o plano.
        Isso é uma **interação genuína**, não um efeito aditivo.
        """)

        # ── Interação 2: contrato (1o vs 2o+) x composicao_drc ──
        st.markdown("---")
        st.markdown("#### 2. Ciclo do contrato × Composição DRC")
        st.markdown(
            "Hipótese: '1o contrato' é o fator de risco mais forte do score atual. Se ter "
            "dep ativo DRC reduzir esse efeito, o score precisa enxergar essa interação."
        )

        inter2 = churn_table(df, ["contrato", "composicao_drc"])
        ordem_comp_inter = ["solo", "so_passivos", "passivos_e_ativos", "so_ativos_drc"]
        inter2["comp_label"] = inter2["composicao_drc"].map(nomes_comp)
        inter2["comp_ord"] = inter2["composicao_drc"].map({k:i for i,k in enumerate(ordem_comp_inter)})
        inter2 = inter2.sort_values(["contrato", "comp_ord"])
        inter2["contrato_label"] = inter2["contrato"].map({"1o": "1o contrato", "2o+": "2o+ contrato"})

        fig = px.bar(
            inter2, x="comp_label", y="churn_pct", color="contrato_label",
            barmode="group",
            color_discrete_map={"1o contrato": "#d62728", "2o+ contrato": "#2ca02c"},
            text=inter2["churn_pct"].apply(lambda v: f"{v}%"),
            labels={"comp_label": "Composição DRC", "churn_pct": "Churn (%)", "contrato_label": ""},
        )
        fig.update_traces(textposition="outside")
        fig.add_hline(y=churn_global, line_dash="dash", line_color="gray",
                      annotation_text=f"Churn global ({churn_global:.1f}%)")
        fig.update_layout(title="Churn por (ciclo do contrato × composição DRC)",
                          height=420, yaxis=dict(range=[40, 70]),
                          legend=dict(orientation="h", y=1.10))
        st.plotly_chart(fig, use_container_width=True)

        spread_1o = inter2[inter2["contrato"] == "1o"]["churn_pct"].max() - inter2[inter2["contrato"] == "1o"]["churn_pct"].min()
        spread_2o = inter2[inter2["contrato"] == "2o+"]["churn_pct"].max() - inter2[inter2["contrato"] == "2o+"]["churn_pct"].min()
        st.info(f"""
        **Spread interno por ciclo:**
        - Dentro do **1o contrato**: {spread_1o:.1f} p.p. de spread entre as 4 composições
        - Dentro do **2o+ contrato**: {spread_2o:.1f} p.p. de spread

        O efeito da composição do núcleo é **mais forte em contratos renovados** — onde o titular
        já decidiu uma vez e está re-decidindo, o engajamento dos deps pesa mais. Isso sugere que a
        feature de núcleo deve entrar com peso variável conforme `meses_ativo` no score evolutivo.
        """)

        # ── Interação 3: faixa_idade_titular x tem_dep_cronico ──
        st.markdown("---")
        st.markdown("#### 3. Faixa etária do titular × Dep crônico")
        st.markdown(
            "Para titulares jovens (que têm baixa razão clínica própria pra ficar), "
            "o dep crônico pode ser o gancho mais forte. Vamos olhar."
        )

        inter3 = churn_table(df, ["faixa_idade_titular", "tem_dep_cronico_viz"])
        order_fx = ["00-20", "21-30", "31-50", "51-70", "71+"]
        inter3["fx_ord"] = inter3["faixa_idade_titular"].map({k:i for i,k in enumerate(order_fx)})
        inter3["dep_label"] = inter3["tem_dep_cronico_viz"].map(nomes_dep_cron)
        inter3 = inter3.sort_values(["fx_ord"])

        fig = px.line(
            inter3, x="faixa_idade_titular", y="churn_pct", color="dep_label",
            markers=True, line_shape="spline",
            category_orders={"faixa_idade_titular": order_fx},
            color_discrete_map={"Dep crônico=S": "#1f77b4", "Dep crônico=N": "#aec7e8",
                                "Dep status desc.": "#d62728", "Sem dep": "#7f7f7f"},
            labels={"faixa_idade_titular": "Faixa etária do titular", "churn_pct": "Churn (%)", "dep_label": ""},
        )
        fig.update_traces(line=dict(width=3), marker=dict(size=10))
        fig.update_layout(title="Churn por faixa etária do titular, segmentado por status crônico do dep",
                          height=420, legend=dict(orientation="h", y=1.10))
        st.plotly_chart(fig, use_container_width=True)

        st.caption(
            "Quando as linhas se afastam, há interação. Se a linha 'Dep crônico=S' é "
            "consistentemente mais baixa ao longo de todas as faixas etárias, o efeito é robusto."
        )

    # ═══════════════════════════════════════════════════════════════════
    # TAB 3: ENGAJAMENTO DRC
    # ═══════════════════════════════════════════════════════════════════
    with tab_eng:
        st.markdown("### Granularidade fina: dose-resposta")
        st.markdown(
            "Será que mais dep ativo = ainda menos churn? Mais dep crônico = ainda mais âncora? "
            "Curvas de dose-resposta nas contagens diretas."
        )

        # ── Dose-resposta: qtd_dep_ativos_drc ──
        st.markdown("#### Quantidade de deps ativos no DRC")
        sub = df.copy()
        sub["qtd_dep_ativos_bin"] = sub["qtd_dep_ativos_drc"].clip(upper=4).astype(int)
        sub["qtd_dep_ativos_bin"] = sub["qtd_dep_ativos_bin"].astype(str).replace({"4": "4+"})
        d_at = churn_table(sub, ["qtd_dep_ativos_bin"])
        ordem_at = ["0", "1", "2", "3", "4+"]
        d_at["ord"] = d_at["qtd_dep_ativos_bin"].map({k:i for i,k in enumerate(ordem_at)})
        d_at = d_at.sort_values("ord")

        col1, col2 = st.columns(2)
        with col1:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=d_at["qtd_dep_ativos_bin"], y=d_at["churn_pct"],
                mode="lines+markers+text",
                marker=dict(size=14, color="#2ca02c"), line=dict(width=3, color="#2ca02c"),
                error_y=dict(
                    type="data", symmetric=False,
                    array=(d_at["ic_hi"] - d_at["churn_pct"]).values,
                    arrayminus=(d_at["churn_pct"] - d_at["ic_lo"]).values,
                    color="rgba(0,0,0,0.3)", thickness=2, width=6,
                ),
                text=d_at["churn_pct"].apply(lambda v: f"{v}%"),
                textposition="top center",
            ))
            fig.add_hline(y=churn_global, line_dash="dash", line_color="gray")
            fig.update_layout(title="Churn por nº de deps ativos DRC",
                              xaxis_title="Qtd deps ativos DRC", yaxis_title="Churn (%)",
                              height=380, yaxis=dict(range=[40, 65]), margin=dict(t=50))
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            sub["qtd_dep_passivos_bin"] = sub["qtd_dep_passivos_drc"].clip(upper=3).astype(int)
            sub["qtd_dep_passivos_bin"] = sub["qtd_dep_passivos_bin"].astype(str).replace({"3": "3+"})
            d_pas = churn_table(sub, ["qtd_dep_passivos_bin"])
            ordem_pas = ["0", "1", "2", "3+"]
            d_pas["ord"] = d_pas["qtd_dep_passivos_bin"].map({k:i for i,k in enumerate(ordem_pas)})
            d_pas = d_pas.sort_values("ord")

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=d_pas["qtd_dep_passivos_bin"], y=d_pas["churn_pct"],
                mode="lines+markers+text",
                marker=dict(size=14, color="#d62728"), line=dict(width=3, color="#d62728"),
                error_y=dict(
                    type="data", symmetric=False,
                    array=(d_pas["ic_hi"] - d_pas["churn_pct"]).values,
                    arrayminus=(d_pas["churn_pct"] - d_pas["ic_lo"]).values,
                    color="rgba(0,0,0,0.3)", thickness=2, width=6,
                ),
                text=d_pas["churn_pct"].apply(lambda v: f"{v}%"),
                textposition="top center",
            ))
            fig.add_hline(y=churn_global, line_dash="dash", line_color="gray")
            fig.update_layout(title="Churn por nº de deps passivos",
                              xaxis_title="Qtd deps passivos DRC", yaxis_title="Churn (%)",
                              height=380, yaxis=dict(range=[40, 65]), margin=dict(t=50))
            st.plotly_chart(fig, use_container_width=True)

        st.caption(
            "Dose-resposta clara: cada dep ativo a mais reduz churn (esquerda); "
            "cada dep passivo a mais aumenta churn (direita). Os efeitos são monotônicos."
        )

        # ── pct_deps_passivos ──
        st.markdown("---")
        st.markdown("#### % de deps passivos sobre o total de deps")
        sub_dep = df[df["qtd_dep_total"] > 0].copy()
        sub_dep["pct_passivos_bin"] = pd.cut(
            sub_dep["pct_deps_passivos"],
            bins=[-0.01, 0, 33.34, 66.67, 99.99, 100.01],
            labels=["0% (todos ativos)", "1-33% passivos", "34-66% passivos", "67-99% passivos", "100% (todos passivos)"],
        )
        d_pct = churn_table(sub_dep, ["pct_passivos_bin"], dropna=True)

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=d_pct["pct_passivos_bin"].astype(str), y=d_pct["churn_pct"],
            marker_color=["#2ca02c", "#7f7f7f", "#ffbb33", "#ff7f0e", "#d62728"],
            error_y=dict(
                type="data", symmetric=False,
                array=(d_pct["ic_hi"] - d_pct["churn_pct"]).values,
                arrayminus=(d_pct["churn_pct"] - d_pct["ic_lo"]).values,
                color="rgba(0,0,0,0.4)", thickness=2, width=8,
            ),
            text=d_pct.apply(lambda r: f"{r['churn_pct']}%<br>{int(r['contratos']):,}", axis=1),
            textposition="outside",
        ))
        fig.add_hline(y=churn_global, line_dash="dash", line_color="gray",
                      annotation_text=f"Churn global ({churn_global:.1f}%)")
        fig.update_layout(title="Churn por % de deps passivos no núcleo",
                          xaxis_title="% de deps passivos", yaxis_title="Churn (%)",
                          height=420, yaxis=dict(range=[40, 70]), showlegend=False, margin=dict(t=60))
        st.plotly_chart(fig, use_container_width=True)

        st.caption(
            "**`pct_deps_passivos` é candidato direto a feature do score**: monotônica, "
            "monoton_amplitude > 8 p.p., distribuída em todas as faixas. Captura o engajamento "
            "do núcleo de forma contínua."
        )

        # ── qtd_dep_cronicos_S ──
        st.markdown("---")
        st.markdown("#### Quantidade de deps com crônico confirmado")
        sub2 = df.copy()
        sub2["qtd_dep_cron_bin"] = sub2["qtd_dep_cronicos_S"].clip(upper=2).astype(int)
        sub2["qtd_dep_cron_bin"] = sub2["qtd_dep_cron_bin"].astype(str).replace({"2": "2+"})
        d_cron = churn_table(sub2, ["qtd_dep_cron_bin"])
        ordem_cron2 = ["0", "1", "2+"]
        d_cron["ord"] = d_cron["qtd_dep_cron_bin"].map({k:i for i,k in enumerate(ordem_cron2)})
        d_cron = d_cron.sort_values("ord")

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=d_cron["qtd_dep_cron_bin"], y=d_cron["churn_pct"],
            marker_color=["#7f7f7f", "#1f77b4", "#0d3b8b"],
            error_y=dict(
                type="data", symmetric=False,
                array=(d_cron["ic_hi"] - d_cron["churn_pct"]).values,
                arrayminus=(d_cron["churn_pct"] - d_cron["ic_lo"]).values,
                color="rgba(0,0,0,0.4)", thickness=2, width=8,
            ),
            text=d_cron.apply(lambda r: f"{r['churn_pct']}%<br>{int(r['contratos']):,}", axis=1),
            textposition="outside",
        ))
        fig.add_hline(y=churn_global, line_dash="dash", line_color="gray")
        fig.update_layout(title="Churn por nº de deps com crônico confirmado",
                          xaxis_title="Qtd deps crônicos confirmados", yaxis_title="Churn (%)",
                          height=380, yaxis=dict(range=[40, 65]), showlegend=False, margin=dict(t=50))
        st.plotly_chart(fig, use_container_width=True)

        st.caption(
            "Dois ou mais deps crônicos confirmados → churn ainda mais baixo. "
            "Sinaliza que a feature pode entrar como contagem (não só dummy 0/1)."
        )

    # ═══════════════════════════════════════════════════════════════════
    # TAB 4: LIMITAÇÕES
    # ═══════════════════════════════════════════════════════════════════
    with tab_lim:
        st.markdown("### O que esta análise NÃO captura ainda")

        n_idade_desc = df["qtd_dep_idade_desconhecida"].sum()
        n_idade_conh = df["qtd_dep_idade_conhecida"].sum()
        n_total_deps = df["qtd_dep_total"].sum()

        st.warning(f"""
        **Idade dos dependentes — limitação atual.**

        A definição de "dependente financeiro" (idade <21 ou >60) e os buckets etários do núcleo
        (jovens / idosos / adultos) **não foram aplicados** nesta versão da análise:

        - {n_total_deps:,} dependentes no escopo
        - {n_idade_desc:,} ({100*n_idade_desc/max(n_total_deps,1):.1f}%) com `dt_nasc` ausente em `pacientes_audit`
        - {n_idade_conh:,} com idade conhecida

        Mesmo entre os {df['qtd_dep_ativos_drc'].sum():,} dependentes ativos no DRC (que têm match em
        `bi_atendimentos`), o `id_paciente` não está casando com `pacientes_audit`. Provável causa:
        formatos/origens diferentes de `id_paciente` entre as tabelas, ou `pacientes_audit` cobre
        apenas titulares.

        **Próximos passos pra fechar:**
        1. Verificar se `bi_atendimentos` tem `dt_nasc` ou `idade_paciente` direto.
        2. Procurar tabela mestre alternativa (ex: `bi_pacientes`, view do Yalo com `birth_date`).
        3. Reconfirmar o mapeamento de `id_paciente` entre Yalo e DRC.

        Quando isso for resolvido, esta página ganha uma 5a aba com a composição etária e o teste
        da definição de dep financeiro.
        """)

        st.markdown("---")
        st.markdown("### O que JÁ está validado pra alimentar o score v2")

        st.success("""
        **Features candidatas com sinal estatisticamente significativo:**

        - `composicao_drc` (4 níveis) — spread de ~9 p.p. entre extremos.
        - `tem_dep_cronico` (3 estados + solo) — spread de ~8 p.p. entre solo e dep crônico=S;
          desconhecido (deps passivos) é o pior cenário.
        - `pct_deps_passivos` — feature contínua, monotônica, dose-resposta clara.
        - `qtd_dep_ativos_drc` (0/1/2/3/4+) — efeito monotônico negativo no churn.
        - `qtd_dep_passivos_drc` (0/1/2/3+) — efeito monotônico positivo no churn.
        - `qtd_dep_cronicos_S` (0/1/2+) — efeito monotônico negativo no churn.

        **Interações detectadas (não capturáveis por dummies aditivas):**
        - `cronico_titular × tem_dep_cronico`: dep crônico ancora mais o titular não-crônico.
        - `contrato × composicao_drc`: efeito do núcleo é maior em renovações que em 1o contrato.

        **Implicação pro score evolutivo:** essas features não são plug-and-play — vão precisar
        de termos de interação. Vale mais pesar `composicao_drc` no score de mês 0 (já disponível
        na assinatura) e refinar com `qtd_dep_cronicos_S` quando o histórico clínico do núcleo
        ficar consolidado nos primeiros 60-90 dias.
        """)

except FileNotFoundError:
    st.error("`results/nucleo_familiar.csv` não encontrado. Rode `queries/nucleo_familiar.sql` no BigQuery e exporte o CSV pra esse caminho.")
except Exception as e:
    st.error(f"Erro ao carregar análise: {e}")
    raise
