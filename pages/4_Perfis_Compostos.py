import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from scipy import stats

st.set_page_config(page_title="Perfis Compostos · Churn", page_icon="🎯", layout="wide")

# ═══════════════════════════════════════════════════════════════════════
# FUNÇÕES ESTATÍSTICAS
# ═══════════════════════════════════════════════════════════════════════

def z_test_proportions(n1, x1, n2, x2):
    """Z-test para diferença de proporções. Retorna dict com resultados."""
    p1, p2 = x1/n1, x2/n2
    diff = p1 - p2
    p_pool = (x1 + x2) / (n1 + n2)
    se = np.sqrt(p_pool * (1 - p_pool) * (1/n1 + 1/n2))
    z = diff / se if se > 0 else 0
    pval = 2 * (1 - stats.norm.cdf(abs(z)))
    ci_lo = diff - 1.96 * se
    ci_hi = diff + 1.96 * se
    return {"diff": diff*100, "ci_lo": ci_lo*100, "ci_hi": ci_hi*100,
            "z": z, "p": pval, "n1": n1, "n2": n2, "p1": p1*100, "p2": p2*100}

def wilson_ci(n, x, alpha=0.05):
    """Intervalo de confiança de Wilson para proporção binomial."""
    if n == 0:
        return 0, 0, 0
    p = x / n
    z = stats.norm.ppf(1 - alpha/2)
    denom = 1 + z**2/n
    center = (p + z**2/(2*n)) / denom
    margin = z * np.sqrt(p*(1-p)/n + z**2/(4*n**2)) / denom
    return p*100, max(0, (center - margin)*100), min(100, (center + margin)*100)

def format_p(p):
    """Formata p-value para exibição."""
    if p < 0.001:
        return "< 0,001"
    elif p < 0.01:
        return f"= {p:.3f}"
    elif p < 0.05:
        return f"= {p:.3f}"
    else:
        return f"= {p:.3f} (n.s.)"

def sig_stars(p):
    """Retorna estrelas de significância."""
    if p < 0.001: return "***"
    if p < 0.01: return "**"
    if p < 0.05: return "*"
    return "n.s."


# ═══════════════════════════════════════════════════════════════════════
st.title("🎯 Capítulo 4 — Perfis compostos de risco")
st.markdown("""
Cruzamos **5 variáveis** para identificar micro-segmentos de risco. As variáveis foram
selecionadas com base em testes estatísticos de confounding — removemos as que
distorciam a leitura ou não agregavam poder preditivo.
""")

# ── BLOCO 1: HIPÓTESES ──────────────────────────────────────────────
with st.expander("📐 O que estamos testando? (Hipóteses)", expanded=False):
    st.markdown("""
    ### Pergunta central

    > *"As diferenças de churn que observamos entre grupos (ex: 1o contrato vs 2o+)
    > são reais ou podem ser explicadas pelo acaso ou por outra variável escondida?"*

    ### Hipóteses formais

    Para **cada variável** que usamos nos perfis, testamos:

    | | Definição | Em linguagem de negócio |
    |---|---|---|
    | **H0** (hipótese nula) | A taxa de churn é **igual** entre os dois grupos comparados. A diferença observada é fruto do acaso amostral. | *"Não faz diferença ser 1o contrato ou 2o+ — o churn seria o mesmo."* |
    | **Ha** (hipótese alternativa) | A taxa de churn é **diferente** entre os grupos. A diferença é real e estatisticamente significativa. | *"Ser 1o contrato realmente aumenta o risco de churn."* |

    ### O que é o p-valor?

    O p-valor responde: *"Se H0 fosse verdade (os grupos fossem iguais), qual a chance de
    eu observar uma diferença tão grande quanto a que vi nos dados?"*

    - **p < 0,001**: Menos de 0,1% de chance de ser acaso. Rejeitamos H0 com altíssima confiança.
    - **p < 0,05**: Menos de 5% de chance. Rejeitamos H0 (limiar convencional).
    - **p > 0,05**: Não temos evidência suficiente para rejeitar H0.

    Todas as 5 variáveis selecionadas têm **p < 0,001** — a probabilidade de as diferenças
    serem acaso é inferior a 1 em 1.000.

    ### O que é o Intervalo de Confiança (IC 95%)?

    É a faixa na qual a **diferença real** provavelmente está. Exemplo:

    > *Diferença 1o vs 2o+ contrato: **+10,5 p.p.** IC 95% [+9,8, +11,2]*

    Isso significa: temos 95% de confiança de que a diferença real está entre 9,8 e 11,2
    pontos percentuais. Se o intervalo não cruzar zero, o efeito é significativo.
    """)

# ── BLOCO 2: CONFOUNDING ────────────────────────────────────────────
with st.expander("🔀 O que são variáveis de confusão? (Confounding)", expanded=False):
    st.markdown("""
    ### O problema em linguagem simples

    Imagine que alguém diga: *"Quem usa guarda-chuva tem mais chance de se molhar."*
    Parece absurdo — e é. O que está acontecendo é que **chuva** causa tanto o uso do
    guarda-chuva quanto o fato de se molhar. Se você não considerar a chuva, conclui
    erradamente que o guarda-chuva molha as pessoas.

    Isso é **confounding**: uma terceira variável que distorce a relação entre as duas
    que estamos analisando.

    ### Confoundings que encontramos nos nossos dados

    **1. Consumo do plano vs Churn** (variável REMOVIDA dos perfis)

    | O que parece | O que realmente acontece |
    |---|---|
    | Quem **usa** o plano cancela **mais** (58,7% vs 52,1%) | Pacientes de **1o contrato + 12m** consomem muito nos primeiros meses — e cancelam de qualquer forma porque o churn do 1o contrato é naturalmente alto |
    | Conclusão errada: *"Usar o plano faz mal"* | Conclusão correta: *"O 1o contrato é o vilão — o consumo é inocente"* |

    Quando controlamos pelo ciclo do contrato, o efeito se **inverte**: no 2o+ contrato,
    quem usa retém mais. Por isso **removemos `consumo_sn` dos perfis** — incluí-lo
    geraria clusters que confundem causa com efeito.

    ---

    **2. Doença crônica vs Churn** (variável MANTIDA, mas com ressalva)

    | O que parece | O que realmente acontece |
    |---|---|
    | Crônicos cancelam **6,5 p.p. menos** que não-crônicos | Crônicos são **muito mais velhos** (37,7% dos 71+ são crônicos vs 0,9% dos jovens). Parte do efeito é a **idade se disfarçando** de doença crônica |
    | Gap aparente: 6,5 p.p. | Gap real (controlado por idade): **3,5 a 4,6 p.p.** |

    Ainda é significativo (p < 0,001), mas é **metade** do que a análise simples sugere.
    Mantivemos nos perfis porque o efeito é real para 31+, mas sinalizamos a ressalva.

    ---

    **3. Duração do plano vs Churn** (variável MANTIDA, com ressalva)

    | O que parece | O que realmente acontece |
    |---|---|
    | Plano de 12m cancela **7,2 p.p. mais** que 6m | Planos de 12m têm **65% de 1o contrato** (vs 57% no 6m). O mix de clientes é diferente |
    | Gap aparente: 7,2 p.p. | Gap real (controlado por contrato): **4,8 a 9,0 p.p.** |

    O efeito persiste controlando pelo ciclo — é real. Mas o gap univariado é ligeiramente
    inflado pela maior proporção de primeiros contratos nos planos anuais.

    ---

    **4. Classe social vs Churn** (variável REMOVIDA dos perfis)

    Todas as classes (A++ a E) oscilam entre 52% e 55% de churn — diferença de ~2 p.p.,
    sem relevância prática. Incluí-la multiplicaria os perfis por 5 (A, B, C, DE, sem dado)
    sem ganho analítico, apenas fragmentando o volume de cada micro-segmento.

    ### Como nos protegemos do confounding?

    **Análise estratificada**: testamos cada variável *dentro* de estratos da possível
    confundidora. Ex: em vez de comparar "12m vs 6m" no geral, comparamos "12m vs 6m
    *só entre 1o contratos*" e "12m vs 6m *só entre 2o+ contratos*". Se o efeito
    persiste nos dois estratos, é real. Se desaparece, era confounding.

    Nos perfis compostos, o cruzamento das 5 variáveis faz isso automaticamente:
    cada célula compara pacientes com o **mesmo** contrato, mesma duração, mesma idade,
    mesmo status de dependentes e crônico. O confounding fica controlado por construção.
    """)

# ── BLOCO 3: SELEÇÃO DE VARIÁVEIS ───────────────────────────────────
with st.expander("📖 Variáveis selecionadas e removidas", expanded=False):
    st.markdown("""
    ### 5 variáveis que compõem os perfis (ordenadas por impacto)

    | # | Variável | Gap Univariado | Gap Controlado | Sig. | Justificativa |
    |---|---|---|---|---|---|
    | 1 | Ciclo do contrato (1o vs 2o+) | 10,5 p.p. | 7,6 – 11,8 p.p. | p < 0,001 | Driver mais forte — sobrevive a qualquer controle |
    | 2 | Dependentes (sem vs 3+) | 9,9 p.p. | 7,9 – 9,1 p.p. | p < 0,001 | Robusto controlando por contrato e idade |
    | 3 | Faixa etária (<=30 vs 51-70) | ~13 p.p. | 6,9 – 13,2 p.p. | p < 0,001 | Forte; absorve parte do efeito crônico |
    | 4 | Duração do plano (12m vs 6m) | 7,2 p.p. | 4,8 – 9,0 p.p. | p < 0,001 | Parcialmente inflado por mix de 1o contrato |
    | 5 | Doença crônica (N vs S) | 6,5 p.p. | 3,4 – 4,6 p.p. | p < 0,001 | ~50% é efeito da idade; real para 31+ |

    ### 2 variáveis removidas

    | Variável | Gap Aparente | Motivo |
    |---|---|---|
    | Consumo do plano | 6,6 p.p. (invertido!) | Confounded com ciclo do contrato — efeito se inverte quando controlado |
    | Classe social | ~2 p.p. | Sem poder discriminante — fragmenta perfis sem ganho |

    ### Cobertura

    - **96 combinações** teóricas (2 durações × 2 ciclos × 3 faixas de dep. × 4 faixas de idade × 2 crônico)
    - Vs **960 combinações** na versão anterior (com 7 variáveis)
    - ~95% dos contratos da base são cobertos pelos perfis com volume >= 100

    ### Testes estatísticos

    | Teste | Para que serve | Como interpretar |
    |---|---|---|
    | **Z-test para proporções** | Compara churn entre dois grupos | Se p < 0,05, a diferença é real (não é acaso) |
    | **IC de Wilson (95%)** | Faixa provável da taxa de churn real | Se o IC de dois grupos não se sobrepõe, são diferentes |
    | **Análise estratificada** | Verifica se o efeito persiste controlando por outra variável | Se persiste nos estratos, é real; se desaparece, era confounding |
    """)


# ═══════════════════════════════════════════════════════════════════════
# DADOS
# ═══════════════════════════════════════════════════════════════════════
@st.cache_data
def load_a(): return pd.read_csv("results/perfis_compostos_risco_a.csv")
@st.cache_data
def load_b(): return pd.read_csv("results/perfis_compostos_risco_b.csv")
@st.cache_data
def load_c(): return pd.read_csv("results/perfis_compostos_risco_c.csv")

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Validação Estatística",
    "🆚 Extremos (Alto vs Baixo Risco)",
    "🌳 Mapa de Perfis",
    "🔍 Churn Silencioso",
])

# ═══════════════════════════════════════════════════════════════════════
# TAB 1: VALIDAÇÃO ESTATÍSTICA
# ═══════════════════════════════════════════════════════════════════════
with tab1:
    try:
        df_a = load_a()
        df_a["duracao"] = df_a["duracao"].astype(str)

        st.markdown("""
        ### Validação: cada variável resiste ao controle pelas demais?

        Abaixo, cada driver é testado **dentro de estratos** da principal variável
        confundidora. Se o efeito desaparece, é confounding. Se persiste, é real.
        """)

        # --- Helper: agregar perfis por combinação de variáveis ---
        def agg(mask):
            sub = df_a[mask]
            n = sub["total_contratos"].sum()
            x = sub["churners"].sum()
            return n, x

        # ═══════ DRIVER 1: CONTRATO ═══════
        st.markdown("---")
        st.markdown("#### #1 Ciclo do contrato (1o vs 2o+)")
        st.caption("Controlado por: duração do plano")

        rows = []
        for dur in ["6", "12"]:
            n1, x1 = agg((df_a["contrato"]=="1o") & (df_a["duracao"]==dur))
            n2, x2 = agg((df_a["contrato"]=="2o+") & (df_a["duracao"]==dur))
            t = z_test_proportions(n1, x1, n2, x2)
            rows.append({
                "Estrato": f"Plano {dur}m",
                "1o contrato": f'{t["p1"]:.1f}% (n={n1:,})',
                "2o+ contrato": f'{t["p2"]:.1f}% (n={n2:,})',
                "Diferença": f'{t["diff"]:+.1f} p.p.',
                "IC 95%": f'[{t["ci_lo"]:+.1f}, {t["ci_hi"]:+.1f}]',
                "p-valor": format_p(t["p"]),
                "Sig.": sig_stars(t["p"]),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.success("Efeito **robusto**: +7,6 a +11,8 p.p. em ambos os estratos. O ciclo do contrato é o driver mais forte.")

        # ═══════ DRIVER 2: DEPENDENTES ═══════
        st.markdown("---")
        st.markdown("#### #2 Dependentes (sem vs 3+)")
        st.caption("Controlado por: ciclo do contrato")

        rows = []
        for cont in ["1o", "2o+"]:
            n1, x1 = agg((df_a["dependentes"]=="sem_dep") & (df_a["contrato"]==cont))
            n2, x2 = agg((df_a["dependentes"]=="3+_dep") & (df_a["contrato"]==cont))
            t = z_test_proportions(n1, x1, n2, x2)
            rows.append({
                "Estrato": f"{cont} contrato",
                "Sem dep.": f'{t["p1"]:.1f}% (n={n1:,})',
                "3+ dep.": f'{t["p2"]:.1f}% (n={n2:,})',
                "Diferença": f'{t["diff"]:+.1f} p.p.',
                "IC 95%": f'[{t["ci_lo"]:+.1f}, {t["ci_hi"]:+.1f}]',
                "p-valor": format_p(t["p"]),
                "Sig.": sig_stars(t["p"]),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.success("Efeito **robusto**: +7,9 a +9,1 p.p. Dependentes protegem independente do ciclo.")

        # ═══════ DRIVER 3: IDADE ═══════
        st.markdown("---")
        st.markdown("#### #3 Faixa etária (≤30 vs 51-70)")
        st.caption("Controlado por: ciclo do contrato. ≤30 = união de 00-20 (infantil/adolescente) + 21-30 (jovem adulto).")

        rows = []
        for cont in ["1o", "2o+"]:
            n1, x1 = agg((df_a["faixa_idade"].isin(["00-20", "21-30"])) & (df_a["contrato"]==cont))
            n2, x2 = agg((df_a["faixa_idade"]=="51-70") & (df_a["contrato"]==cont))
            t = z_test_proportions(n1, x1, n2, x2)
            rows.append({
                "Estrato": f"{cont} contrato",
                "≤30 anos": f'{t["p1"]:.1f}% (n={n1:,})',
                "51-70 anos": f'{t["p2"]:.1f}% (n={n2:,})',
                "Diferença": f'{t["diff"]:+.1f} p.p.',
                "IC 95%": f'[{t["ci_lo"]:+.1f}, {t["ci_hi"]:+.1f}]',
                "p-valor": format_p(t["p"]),
                "Sig.": sig_stars(t["p"]),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.success("Efeito **robusto**: +6,9 a +13,2 p.p. Jovens cancelam mais em qualquer cenário.")

        # ═══════ DRIVER 4: DURAÇÃO ═══════
        st.markdown("---")
        st.markdown("#### #4 Duração do plano (12m vs 6m)")
        st.caption("Controlado por: ciclo do contrato — importante porque 12m tem 65% de 1o contrato vs 57% no 6m")

        rows = []
        for cont in ["1o", "2o+"]:
            n1, x1 = agg((df_a["duracao"]=="12") & (df_a["contrato"]==cont))
            n2, x2 = agg((df_a["duracao"]=="6") & (df_a["contrato"]==cont))
            t = z_test_proportions(n1, x1, n2, x2)
            rows.append({
                "Estrato": f"{cont} contrato",
                "12 meses": f'{t["p1"]:.1f}% (n={n1:,})',
                "6 meses": f'{t["p2"]:.1f}% (n={n2:,})',
                "Diferença": f'{t["diff"]:+.1f} p.p.',
                "IC 95%": f'[{t["ci_lo"]:+.1f}, {t["ci_hi"]:+.1f}]',
                "p-valor": format_p(t["p"]),
                "Sig.": sig_stars(t["p"]),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        # Confounding disclosure
        n_12 = df_a[df_a["duracao"]=="12"]["total_contratos"].sum()
        n1_12 = df_a[(df_a["duracao"]=="12") & (df_a["contrato"]=="1o")]["total_contratos"].sum()
        n_6 = df_a[df_a["duracao"]=="6"]["total_contratos"].sum()
        n1_6 = df_a[(df_a["duracao"]=="6") & (df_a["contrato"]=="1o")]["total_contratos"].sum()
        st.warning(f"""
        **Confounding parcial identificado:** Planos de 12m têm **{100*n1_12/n_12:.0f}%** de 1o contrato
        vs **{100*n1_6/n_6:.0f}%** nos de 6m. Parte do gap univariado (7,2 p.p.) vem dessa composição.
        Controlando por ciclo, o efeito persiste (+4,8 a +9,0 p.p.) — é real, mas menor do que parece no agregado.
        """)

        # ═══════ DRIVER 5: CRÔNICO ═══════
        st.markdown("---")
        st.markdown("#### #5 Doença crônica (N vs S)")
        st.caption("Controlado por: faixa etária — crítico porque 37,7% dos 71+ são crônicos vs 0,9% dos ≤30")

        rows = []
        for idade in ["00-20", "21-30", "31-50", "51-70", "71+"]:
            subN = df_a[(df_a["cronico"]=="N") & (df_a["faixa_idade"]==idade)]
            subS = df_a[(df_a["cronico"]=="S") & (df_a["faixa_idade"]==idade)]
            n1, x1 = subN["total_contratos"].sum(), subN["churners"].sum()
            n2, x2 = subS["total_contratos"].sum(), subS["churners"].sum()
            if n1 > 0 and n2 > 0:
                t = z_test_proportions(n1, x1, n2, x2)
                pct_cron = 100 * n2 / (n1 + n2)
                rows.append({
                    "Estrato": f"{idade} ({pct_cron:.0f}% crônicos)",
                    "Não crônico": f'{t["p1"]:.1f}% (n={n1:,})',
                    "Crônico": f'{t["p2"]:.1f}% (n={n2:,})',
                    "Diferença": f'{t["diff"]:+.1f} p.p.',
                    "IC 95%": f'[{t["ci_lo"]:+.1f}, {t["ci_hi"]:+.1f}]',
                    "p-valor": format_p(t["p"]),
                    "Sig.": sig_stars(t["p"]),
                })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.warning("""
        **Confounding substancial:** O gap univariado de 6,5 p.p. cai para **3,4-4,6 p.p.**
        quando controlado por idade. Em jovens (≤30), o efeito é estatisticamente nulo (volume
        de crônicos muito baixo). O efeito real é concentrado em pacientes 31+.
        A idade é o driver dominante; crônico é um amplificador secundário.
        """)

        # ═══════ RESUMO ═══════
        st.markdown("---")
        st.markdown("### Resumo: Hierarquia dos Drivers de Churn")

        resumo = pd.DataFrame([
            {"#": 1, "Variável": "Ciclo do contrato", "Gap Univariado": "10,5 p.p.",
             "Gap Controlado": "7,6 – 11,8 p.p.", "Confounding": "Nenhum relevante", "Sig.": "***"},
            {"#": 2, "Variável": "Dependentes", "Gap Univariado": "9,9 p.p.",
             "Gap Controlado": "7,9 – 9,1 p.p.", "Confounding": "Nenhum relevante", "Sig.": "***"},
            {"#": 3, "Variável": "Faixa etária", "Gap Univariado": "~13 p.p.",
             "Gap Controlado": "6,9 – 13,2 p.p.", "Confounding": "Absorve parte do crônico", "Sig.": "***"},
            {"#": 4, "Variável": "Duração do plano", "Gap Univariado": "7,2 p.p.",
             "Gap Controlado": "4,8 – 9,0 p.p.", "Confounding": "12m tem mais 1o contrato", "Sig.": "***"},
            {"#": 5, "Variável": "Doença crônica", "Gap Univariado": "6,5 p.p.",
             "Gap Controlado": "3,4 – 4,6 p.p.", "Confounding": "~50% é efeito da idade", "Sig.": "***"},
        ])
        st.dataframe(resumo, hide_index=True, use_container_width=True)

        st.info("""
        **Nota metodológica:** Todos os testes utilizam z-test bicaudal para diferença de proporções
        com IC de 95%. A significância (***) indica p < 0,001. Os gaps controlados representam o range
        observado nos diferentes estratos — a variação reflete interação entre as variáveis, não
        instabilidade do efeito. Base: ~204 mil contratos (cartão de crédito, 6/12m, sem B2B, últimos 12 meses).
        """)

    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")


# ═══════════════════════════════════════════════════════════════════════
# TAB 2: EXTREMOS
# ═══════════════════════════════════════════════════════════════════════
with tab2:
    try:
        df_b = load_b()

        alto = df_b[df_b["categoria"] == "ALTO_RISCO"].copy()
        baixo = df_b[df_b["categoria"] == "BAIXO_RISCO"].copy()

        st.markdown("### Os perfis que mais cancelam vs os que mais ficam")
        st.markdown("Top 30 piores vs. 30 melhores perfis compostos (volume mínimo: 200 contratos).")

        col_bad, col_good = st.columns(2)

        with col_bad:
            st.error("### Perfis de Maior Risco")
            for i in range(min(3, len(alto))):
                r = alto.iloc[i]
                p, ci_lo, ci_hi = wilson_ci(r["total_contratos"], r["churners"])
                st.markdown(f"""
                **{i+1}. {r['perfil']}**
                Churn: **{r['churn_rate']}%** IC 95% [{ci_lo:.1f}%, {ci_hi:.1f}%] — {int(r['total_contratos']):,} contratos
                """)

            st.markdown("""
            **Padrão dominante:**
            - 1o contrato + Jovem (≤30) + Sem dependentes + 12 meses + Não crônico

            > Assinou por impulso, não formou hábito, não renovou.
            """)

        with col_good:
            st.success("### Perfis de Maior Retenção")
            for i in range(min(3, len(baixo))):
                r = baixo.iloc[i]
                p, ci_lo, ci_hi = wilson_ci(r["total_contratos"], r["churners"])
                st.markdown(f"""
                **{i+1}. {r['perfil']}**
                Churn: **{r['churn_rate']}%** IC 95% [{ci_lo:.1f}%, {ci_hi:.1f}%] — {int(r['total_contratos']):,} contratos
                """)

            st.markdown("""
            **Padrão dominante:**
            - 2o+ contrato + 3+ dependentes + 51-70 anos + 6 meses + Crônico

            > Família grande, necessidade contínua de saúde, confia na rede.
            """)

        st.markdown("---")

        # Teste estatístico: diferença entre os extremos
        n_alto = alto["total_contratos"].sum()
        x_alto = alto["churners"].sum()
        n_baixo = baixo["total_contratos"].sum()
        x_baixo = baixo["churners"].sum()
        t = z_test_proportions(n_alto, x_alto, n_baixo, x_baixo)

        st.markdown(f"""
        **Teste de diferença entre os grupos extremos:**
        Alto Risco ({100*x_alto/n_alto:.1f}%) vs Baixo Risco ({100*x_baixo/n_baixo:.1f}%)
        → Diferença: **{t['diff']:+.1f} p.p.** IC 95% [{t['ci_lo']:+.1f}, {t['ci_hi']:+.1f}] p {format_p(t['p'])}
        """)

        # Scatter plot
        df_b["cor"] = df_b["categoria"].map({"ALTO_RISCO": "Alto Risco", "BAIXO_RISCO": "Baixo Risco"})

        fig = px.scatter(
            df_b, x="total_contratos", y="churn_rate", color="cor",
            hover_name="perfil",
            size="total_contratos", size_max=35,
            title="Mapa de Perfis: Alto Risco vs Baixo Risco",
            labels={"total_contratos": "Volume de Contratos", "churn_rate": "Churn (%)", "cor": "Categoria"},
            color_discrete_map={"Alto Risco": "#d62728", "Baixo Risco": "#2ca02c"},
        )
        fig.update_layout(height=500, yaxis_range=[25, 85])
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("📋 Tabela completa — Alto Risco (com IC 95%)"):
            alto_display = alto[["perfil", "total_contratos", "churners", "churn_rate",
                                 "media_consultas", "media_exames"]].copy()
            alto_display["IC 95%"] = alto.apply(
                lambda r: f"[{wilson_ci(r['total_contratos'], r['churners'])[1]:.1f}%, {wilson_ci(r['total_contratos'], r['churners'])[2]:.1f}%]", axis=1)
            st.dataframe(alto_display.rename(columns={
                "perfil": "Perfil", "total_contratos": "Contratos", "churners": "Churners",
                "churn_rate": "Churn (%)", "media_consultas": "Consultas/Pac.", "media_exames": "Exames/Pac."
            }), hide_index=True, use_container_width=True)

        with st.expander("📋 Tabela completa — Baixo Risco (com IC 95%)"):
            baixo_display = baixo[["perfil", "total_contratos", "churners", "churn_rate",
                                   "media_consultas", "media_exames"]].copy()
            baixo_display["IC 95%"] = baixo.apply(
                lambda r: f"[{wilson_ci(r['total_contratos'], r['churners'])[1]:.1f}%, {wilson_ci(r['total_contratos'], r['churners'])[2]:.1f}%]", axis=1)
            st.dataframe(baixo_display.rename(columns={
                "perfil": "Perfil", "total_contratos": "Contratos", "churners": "Churners",
                "churn_rate": "Churn (%)", "media_consultas": "Consultas/Pac.", "media_exames": "Exames/Pac."
            }), hide_index=True, use_container_width=True)

    except Exception as e:
        st.error(f"Erro: {e}")


# ═══════════════════════════════════════════════════════════════════════
# TAB 3: TREEMAP
# ═══════════════════════════════════════════════════════════════════════
with tab3:
    try:
        df_a = load_a()

        st.subheader("Navegação Hierárquica dos Perfis de Risco")
        st.caption("Clique nos blocos para fazer drill-down. Quanto mais vermelho, maior o churn.")

        hierarchy = st.radio(
            "Nível de detalhe:",
            ["Duração → Contrato → Idade → Dependentes",
             "Contrato → Idade → Crônico → Dependentes"],
            horizontal=True
        )

        if hierarchy.startswith("Duração"):
            path_cols = ["duracao", "contrato", "faixa_idade", "dependentes"]
        else:
            path_cols = ["contrato", "faixa_idade", "cronico", "dependentes"]

        fig = px.treemap(
            df_a,
            path=path_cols,
            values="total_contratos",
            color="churn_rate",
            color_continuous_scale="RdYlGn_r",
            range_color=[35, 85],
            title="Mapa de Árvore — Perfis por Taxa de Churn",
            labels={"churn_rate": "Churn (%)"},
        )
        fig.update_traces(root_color="lightgrey")
        fig.update_layout(height=600)
        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Erro: {e}")


# ═══════════════════════════════════════════════════════════════════════
# TAB 4: CHURN SILENCIOSO
# ═══════════════════════════════════════════════════════════════════════
with tab4:
    try:
        df_c = load_c()

        st.subheader("Churn Silencioso — Sem Pedido de Cancelamento")
        st.caption("Exclui pacientes com `unsubscription = S`. Foca no churn passivo — os recuperáveis.")

        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            dur_filter = st.multiselect("Duração:", df_c["duracao"].unique().tolist(),
                                        default=df_c["duracao"].unique().tolist())
        with col_f2:
            cont_filter = st.multiselect("Contrato:", df_c["contrato"].unique().tolist(),
                                         default=df_c["contrato"].unique().tolist())
        with col_f3:
            idade_filter = st.multiselect("Faixa de Idade:", df_c["faixa_idade"].unique().tolist(),
                                          default=df_c["faixa_idade"].unique().tolist())

        mask = (
            df_c["duracao"].isin(dur_filter) &
            df_c["contrato"].isin(cont_filter) &
            df_c["faixa_idade"].isin(idade_filter)
        )
        df_filtered = df_c[mask].copy()

        if df_filtered.empty:
            st.warning("Nenhum dado com os filtros selecionados.")
        else:
            sort_col = st.selectbox("Ordenar por:", ["churn_rate", "total_contratos", "churners"],
                                    format_func=lambda x: {"churn_rate": "Churn (%)", "total_contratos": "Volume", "churners": "Churners"}.get(x, x))
            df_filtered = df_filtered.sort_values(sort_col, ascending=(sort_col == "total_contratos"))

            # Adicionar IC 95%
            df_filtered["IC 95%"] = df_filtered.apply(
                lambda r: f"[{wilson_ci(r['total_contratos'], r['churners'])[1]:.1f}%, {wilson_ci(r['total_contratos'], r['churners'])[2]:.1f}%]", axis=1)

            fig = px.bar(
                df_filtered.head(30), x="churn_rate",
                y=df_filtered.head(30).apply(
                    lambda r: f"{r['duracao']}m|{r['contrato']}|{r['dependentes']}|{r['faixa_idade']}|{r['cronico']}",
                    axis=1
                ),
                orientation="h",
                color="churn_rate",
                color_continuous_scale="RdYlGn_r",
                title=f"Top 30 Perfis (Churn Silencioso) — ordenados por {sort_col}",
                labels={"x": "Churn (%)", "y": "Perfil"},
                text="churn_rate",
            )
            fig.update_layout(height=max(500, len(df_filtered.head(30)) * 22), yaxis_title="")
            fig.update_traces(texttemplate="%{text}%", textposition="outside")
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")
            st.markdown("""
            #### Por que analisar o churn silencioso separadamente?

            O churn com `unsubscription = S` é de 98,7% — inevitável. Mas o churn
            **sem unsubscription** (48,7% da base restante) representa contratos que
            simplesmente expiram: cartão falha, fatura não paga, paciente ignora lembretes.

            Esses são os churners **recuperáveis** com intervenções assertivas.
            Os filtros acima permitem que CRM e Growth priorizem os micro-segmentos
            silenciosos em réguas de WhatsApp/SMS pré-vencimento.
            """)

            with st.expander("📋 Tabela Completa (com IC 95%)"):
                st.dataframe(df_filtered[["duracao", "contrato", "dependentes", "faixa_idade",
                                          "cronico", "total_contratos", "churners", "churn_rate", "IC 95%"]].rename(columns={
                    "duracao": "Duração", "contrato": "Contrato", "dependentes": "Dependentes",
                    "faixa_idade": "Idade", "cronico": "Crônico",
                    "total_contratos": "Contratos", "churners": "Churners", "churn_rate": "Churn (%)"
                }), hide_index=True, use_container_width=True)

    except Exception as e:
        st.error(f"Erro: {e}")


# ═══════════════════════════════════════════════════════════════════════
# CONCLUSÃO
# ═══════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("""
### Síntese: Hierarquia das Alavancas de Retenção

| # | Variável | Efeito Controlado | Confiança | Ação |
|---|---|---|---|---|
| 1 | **1o contrato** vs 2o+ | +8 a +12 p.p. | p < 0,001 | Onboarding agressivo nos primeiros 30 dias |
| 2 | **Sem dependentes** vs 3+ | +8 a +9 p.p. | p < 0,001 | Campanha "Adicione um dependente" |
| 3 | **Jovem (≤30)** vs 51-70 | +7 a +13 p.p. | p < 0,001 | Proposta de valor diferenciada (tele, saúde mental) |
| 4 | **12 meses** vs 6 meses | +5 a +9 p.p. | p < 0,001 | Onboarding reforçado para anuais |
| 5 | **Não crônico** vs crônico | +3 a +5 p.p. | p < 0,001 | Trilhas de cuidado crônico (31+ anos) |

O spread entre o pior perfil (1o + jovem + sem dep. + 12m + não crônico) e o melhor
(2o+ + 3+ dep. + 51-70 + 6m + crônico) confirma que **campanhas segmentadas podem
reduzir churn em dezenas de pontos percentuais** nos micro-segmentos mais vulneráveis.
""")
