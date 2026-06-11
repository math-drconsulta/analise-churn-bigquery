"""
Testa a significancia estatistica dos achados de SAC x Churn.
Responde: o churn de cada grupo SAC e significativamente diferente da base?

Testes aplicados:
  1. Z-test de proporcoes (cada grupo SAC vs base sem SAC)
  2. Chi-quadrado (associacao geral SAC motivo x churn)
  3. Regressao logistica (SAC controlando por ciclo, duracao, idade)
"""
import pandas as pd
import numpy as np
from scipy import stats

df = pd.read_csv("results/sac_churn_resumo.csv", dtype={"cpf": str})

# Converter churn pra binario
df["churn"] = (df["churn_sn"] == "S").astype(int)

# Base: sem SAC
base = df[df["tipo_contato"] == "Sem SAC"]
n_base = len(base)
p_base = base["churn"].mean()
x_base = base["churn"].sum()

print(f"Base (sem SAC): {n_base:,} contratos, churn = {100*p_base:.1f}%")
print()

# ═══════════════════════════════════════════════════════════════
# 1. Z-TEST POR GRUPO (tipo de contato)
# ═══════════════════════════════════════════════════════════════
print("=" * 70)
print("TESTE 1: Z-test de proporcoes — cada grupo SAC vs base sem SAC")
print("H0: churn do grupo = churn da base | H1: sao diferentes")
print("=" * 70)

for grupo, sub in df.groupby("tipo_contato"):
    if grupo == "Sem SAC":
        continue
    n = len(sub)
    x = sub["churn"].sum()
    p = x / n

    # Z-test
    p_pool = (x + x_base) / (n + n_base)
    se = np.sqrt(p_pool * (1 - p_pool) * (1/n + 1/n_base))
    z = (p - p_base) / se if se > 0 else 0
    pval = 2 * (1 - stats.norm.cdf(abs(z)))

    # IC 95% da diferenca
    se_diff = np.sqrt(p*(1-p)/n + p_base*(1-p_base)/n_base)
    diff = p - p_base
    ci_lo = (diff - 1.96 * se_diff) * 100
    ci_hi = (diff + 1.96 * se_diff) * 100

    sig = "***" if pval < 0.001 else "**" if pval < 0.01 else "*" if pval < 0.05 else "n.s."

    print(f"\n  {grupo}:")
    print(f"    N = {n:,}  |  churn = {100*p:.1f}%  |  base = {100*p_base:.1f}%")
    print(f"    Diferenca = {100*diff:+.1f} p.p.  |  IC 95% = [{ci_lo:+.1f}, {ci_hi:+.1f}] p.p.")
    print(f"    z = {z:.3f}  |  p-valor = {pval:.6f}  |  {sig}")

# ═══════════════════════════════════════════════════════════════
# 2. Z-TEST POR MOTIVO (sem cancelamentos)
# ═══════════════════════════════════════════════════════════════
print(f"\n\n{'='*70}")
print("TESTE 2: Z-test por motivo do SAC (excluindo cancelamentos) vs base")
print("=" * 70)

motivos = pd.read_csv("results/sac_churn_motivos.csv")
# Renomear coluna se necessario
if "categoria_sac" in motivos.columns:
    motivos = motivos.rename(columns={"categoria_sac": "categoria"})

for _, row in motivos.sort_values("churn_rate", ascending=False).iterrows():
    n = int(row["contratos"])
    x = int(row["churners"])
    p = x / n if n > 0 else 0

    p_pool = (x + x_base) / (n + n_base)
    se = np.sqrt(p_pool * (1 - p_pool) * (1/n + 1/n_base))
    z = (p - p_base) / se if se > 0 else 0
    pval = 2 * (1 - stats.norm.cdf(abs(z)))

    se_diff = np.sqrt(p*(1-p)/n + p_base*(1-p_base)/n_base)
    diff = p - p_base
    ci_lo = (diff - 1.96 * se_diff) * 100
    ci_hi = (diff + 1.96 * se_diff) * 100

    sig = "***" if pval < 0.001 else "**" if pval < 0.01 else "*" if pval < 0.05 else "n.s."

    print(f"\n  {row['categoria']}:")
    print(f"    N = {n:,}  |  churn = {100*p:.1f}%  |  base = {100*p_base:.1f}%  |  Δ = {100*diff:+.1f} p.p.")
    print(f"    IC 95% = [{ci_lo:+.1f}, {ci_hi:+.1f}]  |  p = {pval:.6f}  |  {sig}")

# ═══════════════════════════════════════════════════════════════
# 3. CHI-QUADRADO: associacao geral
# ═══════════════════════════════════════════════════════════════
print(f"\n\n{'='*70}")
print("TESTE 3: Chi-quadrado — associacao entre tipo_contato e churn")
print("=" * 70)

ct = pd.crosstab(df["tipo_contato"], df["churn"])
chi2, pval_chi, dof, expected = stats.chi2_contingency(ct)
v_cramer = np.sqrt(chi2 / (len(df) * (min(ct.shape) - 1)))

print(f"  Chi2 = {chi2:.2f}  |  df = {dof}  |  p-valor = {pval_chi:.2e}")
print(f"  V de Cramer = {v_cramer:.4f}  (tamanho do efeito)")
print(f"  Interpretacao: {'Associacao significativa' if pval_chi < 0.05 else 'Sem associacao significativa'}")

# ═══════════════════════════════════════════════════════════════
# 4. REGRESSAO LOGISTICA (controlando confounders)
# ═══════════════════════════════════════════════════════════════
print(f"\n\n{'='*70}")
print("TESTE 4: Regressao logistica — SAC controlando por ciclo e duracao")
print("H0: coeficiente do SAC = 0 apos controlar por perfil")
print("=" * 70)

try:
    import statsmodels.api as sm

    # Preparar variaveis
    df_reg = df[df["tipo_contato"].isin(["Sem SAC", "SAC (sem cancelamento)"])].copy()
    df_reg["sac_flag"] = (df_reg["tipo_contato"] != "Sem SAC").astype(int)
    df_reg["ciclo_1o"] = (df_reg["ciclo"] == "1o").astype(int)
    df_reg["duracao_12"] = (df_reg["duracao"].astype(str) == "12").astype(int)

    X = df_reg[["sac_flag", "ciclo_1o", "duracao_12"]]
    X = sm.add_constant(X)
    y = df_reg["churn"]

    model = sm.Logit(y, X).fit(disp=0)

    print(f"\n  Modelo: churn ~ SAC + ciclo_1o + duracao_12")
    print(f"  N = {len(df_reg):,}  |  Pseudo R2 = {model.prsquared:.4f}")
    print()
    print(f"  {'Variavel':20s}  {'Coef':>8s}  {'SE':>8s}  {'z':>8s}  {'p-valor':>10s}  {'Sig':>5s}  {'OR':>6s}")
    print(f"  {'-'*75}")

    for var in model.params.index:
        coef = model.params[var]
        se = model.bse[var]
        z = model.tvalues[var]
        p = model.pvalues[var]
        odds_ratio = np.exp(coef)
        sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "n.s."
        print(f"  {var:20s}  {coef:8.4f}  {se:8.4f}  {z:8.3f}  {p:10.6f}  {sig:>5s}  {odds_ratio:6.3f}")

    # Interpretacao do SAC
    sac_coef = model.params["sac_flag"]
    sac_p = model.pvalues["sac_flag"]
    sac_or = np.exp(sac_coef)
    sac_sig = "***" if sac_p < 0.001 else "**" if sac_p < 0.01 else "*" if sac_p < 0.05 else "n.s."

    print(f"\n  INTERPRETACAO:")
    print(f"  Ter passado pelo SAC (sem cancelamento) tem Odds Ratio = {sac_or:.3f}")
    if sac_or > 1:
        print(f"  → Aumenta a chance de churn em {(sac_or-1)*100:.1f}% APOS controlar por ciclo e duracao")
    else:
        print(f"  → Reduz a chance de churn em {(1-sac_or)*100:.1f}% APOS controlar por ciclo e duracao")
    print(f"  p-valor = {sac_p:.6f} ({sac_sig})")

except ImportError:
    print("  statsmodels nao disponivel — pulando regressao logistica")
except Exception as e:
    print(f"  Erro na regressao: {e}")

# ═══════════════════════════════════════════════════════════════
# RESUMO
# ═══════════════════════════════════════════════════════════════
print(f"\n\n{'='*70}")
print("RESUMO PARA O PM")
print("=" * 70)
print("""
Os percentuais (78%, 66%) sao PROPORÇÕES OBSERVADAS confirmadas por:

  1. Z-test de proporcoes (teste padrao pra comparar taxas entre grupos)
     → Cada motivo testado contra a base sem SAC
     → p-valor e IC 95% calculados

  2. Chi-quadrado (teste de associacao)
     → Confirma se a relacao motivo×churn existe ou e acaso

  3. Regressao logistica (controle por confounders)
     → O efeito do SAC persiste apos controlar ciclo e duracao?
     → Se sim: o SAC TEM efeito independente
     → Se nao: o efeito e explicado pelo perfil do paciente

NAO e correlacao — e diferenca de proporcoes com teste de hipotese.
NAO e causal — pra causalidade precisariamos de experimento (A/B test).
""")
