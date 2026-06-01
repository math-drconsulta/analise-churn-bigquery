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
A página trabalha em **dois níveis**, conforme a pergunta sendo respondida:

- **Núcleo de 5 variáveis** (Validação, Treemap, Silencioso) — duração, contrato,
  dependentes, idade, crônico. É o recorte usado para *defender estatisticamente* cada
  driver com z-test e análise estratificada de confounding. `consumo_sn` e `classe`
  ficaram **fora** desse núcleo (motivos no expander de Confounding).
- **Score completo de 8 variáveis** (Extremos, Acionáveis) — adiciona
  `composicao_drc` (no lugar de `dependentes`), `canal`, `classe` e `consumo_sn`. É o
  recorte do **score WLS da página 2** e o usado para gerar perfis acionáveis para CRM.
  As variáveis "removidas" do núcleo de 5 voltam aqui porque o score controla todas
  as outras simultaneamente — o confounding fica neutralizado por construção.

A diferença não é contradição: o núcleo de 5 prova *o quê* importa; as 8 vars produzem
o *ranking operacional* de quem agir primeiro.
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

    Todas as **5 variáveis do núcleo validado** têm p < 0,001 — a probabilidade de as
    diferenças serem acaso é inferior a 1 em 1.000. O score de 8 variáveis (Extremos,
    Acionáveis) herda essas mesmas 5 e adiciona 3 (`composicao_drc` no lugar de
    `dependentes`, `canal`, `consumo_sn`); a significância individual de cada coeficiente
    do score está na tabela de penalidades em **Capítulo 2 — Score**.

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

    **1. Consumo do plano vs Churn** (variável fora do núcleo de 5; presente no score 8v)

    | O que parece | O que realmente acontece |
    |---|---|
    | Quem **usa** o plano cancela **mais** (58,7% vs 52,1%) | Pacientes de **1o contrato + 12m** consomem muito nos primeiros meses — e cancelam de qualquer forma porque o churn do 1o contrato é naturalmente alto |
    | Conclusão errada: *"Usar o plano faz mal"* | Conclusão correta: *"O 1o contrato é o vilão — o consumo é inocente"* |

    Quando controlamos pelo ciclo do contrato, o efeito se **inverte**: no 2o+ contrato,
    quem usa retém mais. **Por isso `consumo_sn` está fora do núcleo de 5 variáveis** —
    cruzá-lo univariadamente confunde causa com efeito. **No score de 8 vars** ela está
    presente porque a WLS controla as outras 7 simultaneamente; o coeficiente isola o
    efeito de "consumiu" *dado* o ciclo, e fica com o sinal correto (consumo protege).

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

    **4. Classe social vs Churn** (variável fora do núcleo de 5; presente no score 8v)

    Todas as classes (A++ a E) oscilam entre 52% e 55% de churn — diferença de ~2 p.p.,
    sem relevância prática univariada. **No núcleo de 5** ela ficaria de fora para não
    fragmentar volume sem ganho. **No score de 8 vars** ela entra agrupada em apenas
    2 níveis (`AB` vs `CDE`) e tem coeficiente pequeno mas estatisticamente significativo
    — vale o custo porque já está disponível e não fragmenta tanto quanto a versão
    A++/A+/B1/B2/C/DE original.

    ### Como nos protegemos do confounding?

    **Análise estratificada**: testamos cada variável *dentro* de estratos da possível
    confundidora. Ex: em vez de comparar "12m vs 6m" no geral, comparamos "12m vs 6m
    *só entre 1o contratos*" e "12m vs 6m *só entre 2o+ contratos*". Se o efeito
    persiste nos dois estratos, é real. Se desaparece, era confounding.

    Nos perfis compostos, o cruzamento das variáveis faz isso automaticamente: cada
    célula compara pacientes com o **mesmo** contrato, mesma duração, mesma idade,
    mesmo status de dependentes e crônico. No núcleo de 5 vars o confounding fica
    controlado por construção; no score de 8 vars, é a regressão WLS que ajusta tudo
    simultaneamente.
    """)

# ── BLOCO 3: SELEÇÃO DE VARIÁVEIS ───────────────────────────────────
with st.expander("📖 As duas camadas: 5 vars validadas vs 8 vars do score", expanded=False):
    st.markdown("""
    ### Núcleo validado — 5 variáveis (Validação, Treemap, Silencioso)

    Cada uma sobreviveu a teste estatístico estratificado contra confoundings.
    Ordenadas por impacto:

    | # | Variável | Gap Univariado | Gap Controlado | Sig. | Justificativa |
    |---|---|---|---|---|---|
    | 1 | Ciclo do contrato (1o vs 2o+) | 10,5 p.p. | 7,6 – 11,8 p.p. | p < 0,001 | Driver mais forte — sobrevive a qualquer controle |
    | 2 | Dependentes (sem vs 3+) | 9,9 p.p. | 7,9 – 9,1 p.p. | p < 0,001 | Robusto controlando por contrato e idade |
    | 3 | Faixa etária (<=30 vs 51-70) | ~13 p.p. | 6,9 – 13,2 p.p. | p < 0,001 | Forte; absorve parte do efeito crônico |
    | 4 | Duração do plano (12m vs 6m) | 7,2 p.p. | 4,8 – 9,0 p.p. | p < 0,001 | Parcialmente inflado por mix de 1o contrato |
    | 5 | Doença crônica (N vs S) | 6,5 p.p. | 3,4 – 4,6 p.p. | p < 0,001 | ~50% é efeito da idade; real para 31+ |

    ### Score completo — 8 variáveis (Extremos, Acionáveis)

    A regressão WLS (Capítulo 2) controla todas simultaneamente, então
    `consumo_sn` e `classe` deixam de ser ruído univariado e viram peso real.
    `dependentes` vira `composicao_drc` (4 níveis: solo, só passivos, só ativos DRC,
    passivos+ativos) porque captura tanto presença quanto engajamento na rede.

    | # | Variável | Vinda de | O que muda em relação ao núcleo |
    |---|---|---|---|
    | 1 | Ciclo do contrato | Núcleo 5v | igual |
    | 2 | Faixa etária | Núcleo 5v | igual |
    | 3 | Duração do plano | Núcleo 5v | igual |
    | 4 | Doença crônica | Núcleo 5v | igual |
    | 5 | `composicao_drc` | Substitui `dependentes` | 4 níveis (DRC) em vez de 3 (apenas contagem) |
    | 6 | `canal` | Adicionada | digital vs presencial/CFP |
    | 7 | `classe` | Adicionada | AB vs CDE (agregada de 6 para 2 níveis) |
    | 8 | `consumo_sn` | Adicionada | "controlada" pelas outras 7 → sinal protetor real |

    ### Cobertura

    - **Núcleo 5v** — 96 combinações teóricas (2 durações × 2 ciclos × 3 dep × 4 idade × 2 crônico),
      ~95% dos contratos cobertos com volume >= 100
    - **Score 8v** — 499 perfis observados no CSV (após `HAVING COUNT >= 50`),
      usados tanto pelo score WLS quanto pelos rankings de Extremos e Acionáveis

    ### Testes estatísticos

    | Teste | Onde aparece | Como interpretar |
    |---|---|---|
    | **Z-test para proporções** | Validação (5v) | Se p < 0,05, a diferença entre dois grupos é real |
    | **IC de Wilson (95%)** | Validação, Extremos | Faixa provável do churn real; se ICs não se sobrepõem, grupos são diferentes |
    | **Análise estratificada** | Validação | Verifica se efeito persiste em estratos (controle de confounding) |
    | **WLS sobre logit** | Score 8v (Cap. 2) | Pesos e p-valores de cada variável controlando as demais |
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
@st.cache_data
def load_8vars(): return pd.read_csv("results/perfis_compostos_7vars.csv")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Validação Estatística",
    "🆚 Extremos (Alto vs Baixo Risco)",
    "🌳 Mapa de Perfis",
    "🔍 Churn Silencioso",
    "🎯 Grupos Acionáveis",
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
# TAB 2: EXTREMOS (ranqueado pelo score WLS, 8 variáveis)
# ═══════════════════════════════════════════════════════════════════════
def _logit(p):
    p = np.clip(p, 0.001, 0.999)
    return np.log(p / (1 - p))

def _inv_logit(x):
    return 1 / (1 + np.exp(-x))

@st.cache_data
def fit_extremos_score():
    """Replica o WLS da página 2 sobre o CSV 8v e devolve perfis com score + Wilson."""
    a = load_8vars().copy()
    a["duracao"] = a["duracao"].astype(str)
    a["p_churn"] = a["churners"] / a["total_contratos"]
    a["logit_churn"] = _logit(a["p_churn"])

    refs = {"contrato": "2o+", "composicao_drc": "so_ativos_drc",
            "faixa_idade": "51-70", "duracao": "6", "cronico": "S",
            "canal": "presencial_cfp", "classe": "AB", "consumo_sn": "S"}

    features, _names = [], []
    for var, ref in refs.items():
        for level in sorted(a[var].unique()):
            if level == ref:
                continue
            features.append((a[var] == level).astype(float).values)
            _names.append(f"{var}={level}")

    X = np.column_stack([np.ones(len(a))] + features)
    y = a["logit_churn"].values
    w = a["total_contratos"].values
    beta = np.linalg.solve(X.T @ (w[:, None] * X), X.T @ (w * y))

    a["logit_pred"] = X @ beta
    a["churn_pred"] = np.round(100 * _inv_logit(a["logit_pred"]), 1)
    lmin, lmax = a["logit_pred"].min(), a["logit_pred"].max()
    a["score"] = np.round(1000 * (1 - (a["logit_pred"] - lmin) / (lmax - lmin))).astype(int)
    a["gap_obs_pred"] = a["churn_rate"] - a["churn_pred"]

    wlo, whi = [], []
    for _, r in a.iterrows():
        _, lo, hi = wilson_ci(r["total_contratos"], r["churners"])
        wlo.append(lo); whi.append(hi)
    a["wilson_lo"] = wlo
    a["wilson_hi"] = whi

    a["perfil"] = a.apply(lambda r: (
        f"{r['duracao']}m | {r['contrato']} | {r['composicao_drc']} | "
        f"{r['faixa_idade']} | cron={r['cronico']} | {r['canal']} | "
        f"cls={r['classe']} | cons={r['consumo_sn']}"
    ), axis=1)
    return a

with tab2:
    try:
        df_8 = fit_extremos_score()
        # Threshold alinhado com a página 2 (score WLS): >=50 (já garantido pelo SQL)
        df_8 = df_8[df_8["total_contratos"] >= 50].copy()

        alto  = df_8.sort_values("score", ascending=True).head(30).copy()   # piores scores
        baixo = df_8.sort_values("score", ascending=False).head(30).copy()  # melhores scores

        st.markdown("### Os perfis que mais cancelam vs os que mais ficam")
        st.info(
            "Esta aba usa **8 variáveis** e ranqueia pelo **score WLS** da página 2 "
            "(menor score = maior risco). O churn observado e o IC 95% aparecem ao lado "
            "do predito para evidenciar onde o modelo acerta e onde subestima."
        )
        st.caption(
            "Top 30 menores scores vs. 30 maiores. Volume mínimo: 50 contratos "
            "(mesmo threshold do score)."
        )

        col_bad, col_good = st.columns(2)

        with col_bad:
            st.error("### Perfis de Maior Risco (menores scores)")
            for i in range(min(3, len(alto))):
                r = alto.iloc[i]
                st.markdown(f"""
                **{i+1}. {r['perfil']}**
                Score **{int(r['score'])}** · churn obs **{r['churn_rate']}%** IC 95% [{r['wilson_lo']:.1f}%, {r['wilson_hi']:.1f}%] · pred {r['churn_pred']}% · n={int(r['total_contratos']):,}
                """)

            st.markdown("""
            **Padrão dominante:**
            - 1o contrato + 12m + ≤30 + solo/só passivos
            - Canal digital + classe CDE + sem consumo

            > Modelo aponta esses perfis como pior risco; observado costuma confirmar.
            """)

        with col_good:
            st.success("### Perfis de Maior Retenção (maiores scores)")
            for i in range(min(3, len(baixo))):
                r = baixo.iloc[i]
                st.markdown(f"""
                **{i+1}. {r['perfil']}**
                Score **{int(r['score'])}** · churn obs **{r['churn_rate']}%** IC 95% [{r['wilson_lo']:.1f}%, {r['wilson_hi']:.1f}%] · pred {r['churn_pred']}% · n={int(r['total_contratos']):,}
                """)

            st.markdown("""
            **Padrão dominante:**
            - 2o+ contrato + 6m + 51-70/71+ + dependentes ativos na DRC
            - Presencial CFP + crônico + classe AB

            > Núcleo familiar engajado, vínculo presencial, necessidade contínua.
            """)

        st.markdown("---")

        # Teste estatístico: diferença entre os extremos (sobre churn observado)
        n_alto = alto["total_contratos"].sum()
        x_alto = alto["churners"].sum()
        n_baixo = baixo["total_contratos"].sum()
        x_baixo = baixo["churners"].sum()
        t = z_test_proportions(n_alto, x_alto, n_baixo, x_baixo)

        st.markdown(f"""
        **Teste de diferença entre os grupos extremos (churn observado):**
        Alto Risco ({100*x_alto/n_alto:.1f}%) vs Baixo Risco ({100*x_baixo/n_baixo:.1f}%)
        → Diferença: **{t['diff']:+.1f} p.p.** IC 95% [{t['ci_lo']:+.1f}, {t['ci_hi']:+.1f}] p {format_p(t['p'])}
        """)

        # Scatter: score x churn observado (a curva esperada vai do canto superior-esquerdo
        # ao inferior-direito; gap entre obs e pred fica visível).
        df_plot = pd.concat([
            alto.assign(cor="Alto Risco"),
            baixo.assign(cor="Baixo Risco"),
        ], ignore_index=True)

        fig = px.scatter(
            df_plot, x="score", y="churn_rate", color="cor",
            hover_name="perfil",
            hover_data={"churn_pred": True, "gap_obs_pred": ":.1f",
                        "total_contratos": True, "score": False, "cor": False},
            size="total_contratos", size_max=35,
            title="Mapa de Perfis: Score WLS × Churn Observado",
            labels={"score": "Score (0 = pior risco, 1000 = melhor)",
                    "churn_rate": "Churn observado (%)", "cor": "Categoria",
                    "churn_pred": "Pred (%)", "gap_obs_pred": "Gap obs-pred (p.p.)",
                    "total_contratos": "Contratos"},
            color_discrete_map={"Alto Risco": "#d62728", "Baixo Risco": "#2ca02c"},
        )
        fig.update_layout(height=500, yaxis_range=[25, 95], xaxis=dict(range=[-30, 1030]))
        st.plotly_chart(fig, use_container_width=True)

        # Tabelas com obs + pred + gap
        cols_table = ["perfil", "score", "total_contratos", "churners",
                      "churn_rate", "wilson_lo", "wilson_hi", "churn_pred", "gap_obs_pred"]
        rename_table = {
            "perfil": "Perfil", "score": "Score",
            "total_contratos": "Contratos", "churners": "Churners",
            "churn_rate": "Churn obs (%)", "churn_pred": "Churn pred (%)",
            "gap_obs_pred": "Gap (p.p.)",
        }

        with st.expander("📋 Tabela completa — Alto Risco (score ↑ pior)"):
            alto_display = alto[cols_table].copy()
            alto_display["IC 95%"] = alto.apply(
                lambda r: f"[{r['wilson_lo']:.1f}%, {r['wilson_hi']:.1f}%]", axis=1)
            alto_display["Gap (p.p.)"] = alto_display["gap_obs_pred"].round(1).apply(lambda v: f"{v:+.1f}")
            st.dataframe(
                alto_display.drop(columns=["wilson_lo", "wilson_hi", "gap_obs_pred"])
                            .rename(columns=rename_table),
                hide_index=True, use_container_width=True,
            )
            st.caption(
                "**Gap** > 0 → modelo **subestima** o risco desse perfil (observado é pior "
                "que o predito). É candidato a ganhar variável comportamental na próxima iteração."
            )

        with st.expander("📋 Tabela completa — Baixo Risco (score ↓ melhor)"):
            baixo_display = baixo[cols_table].copy()
            baixo_display["IC 95%"] = baixo.apply(
                lambda r: f"[{r['wilson_lo']:.1f}%, {r['wilson_hi']:.1f}%]", axis=1)
            baixo_display["Gap (p.p.)"] = baixo_display["gap_obs_pred"].round(1).apply(lambda v: f"{v:+.1f}")
            st.dataframe(
                baixo_display.drop(columns=["wilson_lo", "wilson_hi", "gap_obs_pred"])
                             .rename(columns=rename_table),
                hide_index=True, use_container_width=True,
            )

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
# TAB 5: GRUPOS ACIONÁVEIS
# ═══════════════════════════════════════════════════════════════════════
with tab5:
    try:
        df_8v = load_8vars()
        df_8v["duracao"] = df_8v["duracao"].astype(str)

        st.markdown("### 🎯 Segmentação em Grupos Acionáveis")
        st.markdown("""
        Agrupamos os **499 perfis compostos** (8 variáveis) em **5 grupos acionáveis**
        baseados nas variáveis de maior impacto no score de risco:
        `contrato`, `composição DRC`, `crônico`, `consumo_sn`, `faixa_idade`.
        """)

        # --- Definir grupos ---
        def assign_grupo(row):
            # Grupo 1: CRÍTICO - jovem + 1o contrato + solo + não consumiu
            if (row["contrato"] == "1o"
                and row["faixa_idade"] in ("00-20", "21-30")
                and row["composicao_drc"] == "solo"
                and row["consumo_sn"] == "N"):
                return "🔴 Inativo Solitário"

            # Grupo 2: 1o contrato + desengajado (solo/passivos, não crônico, não consumiu)
            if (row["contrato"] == "1o"
                and row["composicao_drc"] in ("solo", "so_passivos")
                and row["cronico"] == "N"
                and row["consumo_sn"] == "N"):
                return "🟠 Desengajado sem Vínculo"

            # Grupo 3: 1o contrato + consumiu (está usando mas instável)
            if row["contrato"] == "1o" and row["consumo_sn"] == "S":
                return "🟡 Engajado Instável"

            # Restante do 1o contrato que não consumiu (crônicos, etc)
            if row["contrato"] == "1o":
                return "🟠 Desengajado sem Vínculo"

            # 2o+ contrato + sem vínculo forte
            if (row["contrato"] == "2o+"
                and row["cronico"] == "N"
                and row["composicao_drc"] in ("solo", "so_passivos")):
                return "🔵 Renovador em Risco"

            # 2o+ contrato + vínculo (crônico ou deps ativos)
            return "🟢 Fidelizado"

        df_8v["grupo"] = df_8v.apply(assign_grupo, axis=1)

        # Ordem dos grupos
        grupo_order = [
            "🔴 Inativo Solitário",
            "🟠 Desengajado sem Vínculo",
            "🟡 Engajado Instável",
            "🔵 Renovador em Risco",
            "🟢 Fidelizado",
        ]

        # --- Agregar por grupo ---
        grupo_stats = []
        for g in grupo_order:
            sub = df_8v[df_8v["grupo"] == g]
            if len(sub) == 0:
                continue
            n = sub["total_contratos"].sum()
            ch = sub["churners"].sum()
            grupo_stats.append({
                "Grupo": g,
                "Contratos": n,
                "Churners": ch,
                "Churn": round(100 * ch / n, 1),
                "Perfis": len(sub),
                "Pct_base": round(100 * n / df_8v["total_contratos"].sum(), 1),
            })
        gs = pd.DataFrame(grupo_stats)

        # --- KPIs por grupo ---
        cols = st.columns(len(gs))
        colors = ["#e74c3c", "#e67e22", "#f1c40f", "#3498db", "#27ae60"]
        for i, (_, row) in enumerate(gs.iterrows()):
            with cols[i]:
                st.metric(
                    row["Grupo"].split(" ", 1)[1],
                    f"{row['Churn']}%",
                    delta=f"{row['Contratos']:,} contratos ({row['Pct_base']}%)",
                    delta_color="off",
                )

        # --- Gráfico de barras ---
        st.markdown("---")

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=gs["Grupo"],
            y=gs["Churn"],
            marker_color=colors[:len(gs)],
            text=gs.apply(lambda r: f'{r["Churn"]}%<br>({r["Contratos"]:,})', axis=1),
            textposition="outside",
            textfont=dict(size=12),
        ))
        fig.update_layout(
            title="Taxa de churn por grupo acionável",
            yaxis_title="Churn (%)",
            height=420,
            yaxis=dict(range=[0, 90]),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

        # --- Composição de cada grupo ---
        st.markdown("---")
        st.markdown("### Composição dos Grupos")
        st.markdown("Quais variáveis dominam cada grupo? Isso define a **ação específica**.")

        for i, g in enumerate(grupo_order):
            sub = df_8v[df_8v["grupo"] == g]
            if len(sub) == 0:
                continue

            total_g = sub["total_contratos"].sum()
            churn_g = round(100 * sub["churners"].sum() / total_g, 1)

            with st.expander(f"{g} — churn {churn_g}% | {total_g:,} contratos", expanded=(i == 0)):
                # Distribuição das variáveis
                var_cols = st.columns(4)
                for j, var in enumerate(["composicao_drc", "faixa_idade", "cronico", "duracao"]):
                    with var_cols[j]:
                        dist = sub.groupby(var)["total_contratos"].sum().sort_values(ascending=False)
                        st.markdown(f"**{var}**")
                        for level, count in dist.items():
                            pct = 100 * count / total_g
                            bar = "█" * int(pct / 5)
                            st.caption(f"{level}: {pct:.0f}% {bar}")

                var_cols2 = st.columns(4)
                for j, var in enumerate(["canal", "classe", "consumo_sn", "contrato"]):
                    with var_cols2[j]:
                        dist = sub.groupby(var)["total_contratos"].sum().sort_values(ascending=False)
                        st.markdown(f"**{var}**")
                        for level, count in dist.items():
                            pct = 100 * count / total_g
                            bar = "█" * int(pct / 5)
                            st.caption(f"{level}: {pct:.0f}% {bar}")

        # --- Anatomia do churn: motivos por tipo ---
        st.markdown("---")
        st.markdown("### Anatomia do Churn: Por que não renovam?")
        st.markdown("""
        Cruzamos o diagnóstico de não-renovação (da base de abril/2026, 13.5k contratos)
        com os grupos acionáveis para entender **qual tipo de intervenção** cada grupo precisa.
        """)

        try:
            motivos = pd.read_csv("results/motivos_churn.csv")

            # Categorizar diagnósticos
            diag_map = {
                "Renovado: Continuou": "Renovado",
                "Vencido Corretamente: Cancelado": "Cancelou voluntariamente",
                "Vencido Corretamente: Compra Avulsa Não-Recorrente": "Compra avulsa",
                "Vencido Corretamente: Meio de Pagamento Manual": "Pgto manual não efetuado",
                "Vencido Corretamente: Pagamento Recusado": "Pagamento recusado",
                "ALERTA: Nenhuma tentativa recente encontrada": "Sem tentativa",
                "ERRO TÉCNICO: Cobrado (Adyen) mas não renovado": "Erro técnico",
                "ERRO TÉCNICO: Cobrado (Mundipagg) mas não renovado": "Erro técnico",
            }
            motivos["tipo"] = motivos["diagnostico"].map(diag_map).fillna("Outros")

            # Distribuição geral (excluindo renovados)
            nao_renovou = motivos[motivos["tipo"] != "Renovado"]
            tipo_counts = nao_renovou["tipo"].value_counts()

            col_chart, col_text = st.columns([1, 1])
            with col_chart:
                fig_mot = go.Figure(data=[go.Pie(
                    labels=tipo_counts.index,
                    values=tipo_counts.values,
                    hole=0.4,
                    marker_colors=[
                        "#c0392b" if "Cancelou" in l
                        else "#f39c12" if "Pagamento" in l
                        else "#e67e22" if "manual" in l
                        else "#8e44ad" if "Sem" in l
                        else "#e74c3c" if "Erro" in l
                        else "#7f8c8d"
                        for l in tipo_counts.index
                    ],
                    textinfo="label+percent",
                    textfont=dict(size=11),
                )])
                fig_mot.update_layout(
                    title="Por que os contratos não renovam?",
                    height=380, showlegend=False,
                )
                st.plotly_chart(fig_mot, use_container_width=True)

            with col_text:
                pct_pgto = 100 * tipo_counts.get("Pagamento recusado", 0) / tipo_counts.sum()
                pct_cancel = 100 * tipo_counts.get("Cancelou voluntariamente", 0) / tipo_counts.sum()
                pct_manual = 100 * tipo_counts.get("Pgto manual não efetuado", 0) / tipo_counts.sum()

                st.info(f"""
                **O que isso significa para cada grupo:**

                🔴 **Inativo Solitário** e 🟠 **Desengajado**: provavelmente a maioria
                é churn **passivo** ({pct_pgto:.0f}% pagamento recusado + {pct_manual:.0f}% pgto manual).
                → **Ação: dunning, régua de cobrança, atualização de cartão.**

                🟡 **Engajado Instável**: parte é voluntário ({pct_cancel:.0f}%).
                → **Ação: save desk, oferta de renovação, demonstrar valor.**

                🔵 **Renovador em Risco** e 🟢 **Fidelizado**: quando churnam,
                é mais por falha de pagamento que por decisão.
                → **Ação: verificação preventiva de cartão antes do vencimento.**
                """)

                st.warning("""
                **Insight chave:** {:.0f}% do churn total é **involuntário** (pagamento recusado
                + pgto manual + sem tentativa). Esses pacientes **não decidiram sair**.
                Um score de **churn voluntário** (que modela apenas os {:.0f}% que cancelaram)
                terá drivers completamente diferentes e maior poder preditivo.
                """.format(pct_pgto + pct_manual + 100 * tipo_counts.get("Sem tentativa", 0) / tipo_counts.sum(),
                           pct_cancel))

        except FileNotFoundError:
            st.caption("⚠️ Arquivo `results/motivos_churn.csv` não encontrado. Rode a query `motivos_churn.sql` no BigQuery.")
        except Exception as e_motivos:
            st.caption(f"⚠️ Erro ao carregar motivos: {e_motivos}")

        # --- Ações recomendadas ---
        st.markdown("---")
        st.markdown("### Playbook de Ações")

        actions = {
            "🔴 Inativo Solitário": {
                "desc": "Jovem, 1o contrato, solo, nunca usou o plano",
                "churn": gs[gs["Grupo"].str.contains("Inativo")]["Churn"].values[0] if len(gs[gs["Grupo"].str.contains("Inativo")]) > 0 else "?",
                "acoes": [
                    "📞 Ligar nos primeiros 7 dias pós-assinatura",
                    "📅 Agendar 1ª consulta (Clínica Médica) automaticamente",
                    "📲 SMS/WhatsApp D+3, D+7, D+14 com CTA de agendamento",
                    "🏥 Direcionar para Cardiologista/Gastro (especialidades de vínculo)",
                ],
            },
            "🟠 Desengajado sem Vínculo": {
                "desc": "1o contrato, sem dependentes ativos na DRC, não crônico, não consumiu",
                "churn": gs[gs["Grupo"].str.contains("Desengajado")]["Churn"].values[0] if len(gs[gs["Grupo"].str.contains("Desengajado")]) > 0 else "?",
                "acoes": [
                    "📲 Régua de engajamento: push para 1ª consulta até D+30",
                    "👨‍👩‍👧 Campanha 'Adicione um dependente' com desconto",
                    "🏥 Encaminhar para check-up preventivo",
                    "💳 Verificar cartão e migrar para débito automático",
                ],
            },
            "🟡 Engajado Instável": {
                "desc": "1o contrato, já usou o plano — está engajado mas pode não renovar",
                "churn": gs[gs["Grupo"].str.contains("Engajado")]["Churn"].values[0] if len(gs[gs["Grupo"].str.contains("Engajado")]) > 0 else "?",
                "acoes": [
                    "📊 Enviar relatório de economia (valor que já usou vs. custo do plano)",
                    "🏥 Direcionar para 2ª especialidade (diversificar vínculo)",
                    "🔔 Lembrete de exames preventivos pendentes",
                    "🎯 Oferta de renovação antecipada com desconto",
                ],
            },
            "🔵 Renovador em Risco": {
                "desc": "2o+ contrato, mas sem crônico nem dependentes ativos — vínculo frágil",
                "churn": gs[gs["Grupo"].str.contains("Renovador")]["Churn"].values[0] if len(gs[gs["Grupo"].str.contains("Renovador")]) > 0 else "?",
                "acoes": [
                    "📈 Mostrar histórico de uso e economia acumulada",
                    "👨‍👩‍👧 Campanha de adição de dependente",
                    "🏥 Trilha de cuidado preventivo (check-up anual)",
                    "💡 Comunicar novos benefícios e especialidades",
                ],
            },
            "🟢 Fidelizado": {
                "desc": "2o+ contrato + crônico ou dependentes ativos na DRC",
                "churn": gs[gs["Grupo"].str.contains("Fidelizado")]["Churn"].values[0] if len(gs[gs["Grupo"].str.contains("Fidelizado")]) > 0 else "?",
                "acoes": [
                    "⭐ Programa de fidelidade e benefícios exclusivos",
                    "📣 Campanha de referral (indique um amigo)",
                    "🔝 Oferta de upgrade de plano",
                    "🎁 Ações de reconhecimento (aniversário de contrato)",
                ],
            },
        }

        for grupo, info in actions.items():
            st.markdown(f"#### {grupo}")
            st.caption(f'{info["desc"]} — Churn: **{info["churn"]}%**')
            for acao in info["acoes"]:
                st.write(f"  {acao}")
            st.write("")

    except Exception as e:
        st.error(f"Erro: {e}")
        import traceback
        st.code(traceback.format_exc())


# ═══════════════════════════════════════════════════════════════════════
# CONCLUSÃO
# ═══════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("""
### Síntese — duas leituras complementares

**Núcleo validado de 5 vars (defensável estatisticamente):**

| # | Variável | Efeito Controlado | Confiança | Ação |
|---|---|---|---|---|
| 1 | **1o contrato** vs 2o+ | +8 a +12 p.p. | p < 0,001 | Onboarding agressivo nos primeiros 30 dias |
| 2 | **Sem dependentes** vs 3+ | +8 a +9 p.p. | p < 0,001 | Campanha "Adicione um dependente" |
| 3 | **Jovem (≤30)** vs 51-70 | +7 a +13 p.p. | p < 0,001 | Proposta de valor diferenciada (tele, saúde mental) |
| 4 | **12 meses** vs 6 meses | +5 a +9 p.p. | p < 0,001 | Onboarding reforçado para anuais |
| 5 | **Não crônico** vs crônico | +3 a +5 p.p. | p < 0,001 | Trilhas de cuidado crônico (31+ anos) |

**Score 8v (operacional — Extremos e Acionáveis):** adiciona `composicao_drc`, `canal`,
`classe` e `consumo_sn`. As três adicionais entram com peso menor mas significativo no
WLS, e refinam o ranking de quem agir primeiro. O `consumo_sn` é particularmente
relevante: dentro do mesmo perfil demográfico, **quem consumiu retém mais** — sinal que
só fica visível quando as outras 7 estão controladas (no recorte univariado de 5 vars,
o efeito aparece invertido por confounding com ciclo do contrato).

O spread entre o pior perfil (score baixo: 1o + jovem + solo + 12m + não crônico +
digital + CDE + sem consumo) e o melhor (score alto: 2o+ + 51-70/71+ + ativos DRC +
6m + crônico + presencial + AB) confirma que **campanhas segmentadas podem reduzir
churn em dezenas de pontos percentuais** nos micro-segmentos mais vulneráveis.
""")
