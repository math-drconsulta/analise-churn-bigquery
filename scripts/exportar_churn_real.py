"""
Exporta a pagina 'Churn Real vs Aparente' como HTML standalone.
Uso: .venv/bin/python3 scripts/exportar_churn_real.py
Saida: churn_real_vs_aparente.html
"""
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.io as pio

# Carregar dados
df_mensal = pd.read_csv("results/winback_30d_mensal.csv")
df_mensal["mes_vencimento"] = pd.to_datetime(df_mensal["mes_vencimento"])
df_vol = pd.read_csv("results/winback_voluntario.csv")
vol_30d = df_vol[df_vol["faixa_retorno"] == "01_ate_30_dias"]
dias = vol_30d["dias_ate_retorno"].dropna()

# Numeros
total_base = int(df_mensal["total_contratos"].sum())
total_churners = int(df_mensal["churners"].sum())
total_retidos = total_base - total_churners
total_voltaram = int(df_mensal["voltaram_30d"].sum())
total_churn_real = int(df_mensal["churn_real"].sum())
pct_retidos = round(100 * total_retidos / total_base, 1)
pct_churn_ap = round(100 * total_churners / total_base, 1)
pct_voltaram = round(100 * total_voltaram / total_churners, 1)
pct_churn_real = round(100 * total_churn_real / total_base, 1)
n_15_21 = int(((dias >= 15) & (dias <= 21)).sum())
pct_15_21 = round(100 * n_15_21 / len(dias), 1)

# Graficos
fig_pizza = go.Figure(data=[go.Pie(
    labels=["Renova normalmente", "Renovacao tardia (volta 30d)", "Churn real"],
    values=[total_retidos, total_voltaram, total_churn_real],
    hole=0.5,
    marker_colors=["#27ae60", "#3498db", "#c0392b"],
    textinfo="label+percent+value",
    texttemplate="%{label}<br>%{value:,}<br>(%{percent})",
    textfont=dict(size=13),
)])
fig_pizza.update_layout(
    title="Composicao da base: os 3 grupos",
    height=450, showlegend=False, width=700,
    annotations=[dict(text=f"{total_base:,}<br>contratos", x=0.5, y=0.5, font_size=16, showarrow=False)],
)

fig_hist = go.Figure()
fig_hist.add_trace(go.Histogram(x=dias, nbinsx=30, marker_color="#3498db", name="Contratos"))
fig_hist.add_vrect(x0=15, x1=21, fillcolor="red", opacity=0.1, line_width=0)
fig_hist.add_annotation(x=18, y=0.95, yref="paper", text=f"80.6% concentrados<br>entre 15-21 dias",
                        showarrow=False, font=dict(size=13, color="red"))
fig_hist.update_layout(title="Em quantos dias 'voltam'", xaxis_title="Dias ate retorno",
                       yaxis_title="Contratos", height=400, width=700)

fig_mensal = go.Figure()
fig_mensal.add_trace(go.Scatter(
    x=df_mensal["mes_vencimento"], y=df_mensal["churn_rate"],
    name="Churn aparente", mode="lines+markers",
    line=dict(color="#95a5a6", width=2, dash="dot"), marker=dict(size=6),
))
fig_mensal.add_trace(go.Scatter(
    x=df_mensal["mes_vencimento"], y=df_mensal["churn_real_rate"],
    name="Churn real", mode="lines+markers",
    line=dict(color="#c0392b", width=3), marker=dict(size=8),
))
fig_mensal.add_trace(go.Bar(
    x=df_mensal["mes_vencimento"], y=df_mensal["pct_retorno_30d"],
    name="% retorno 30d", marker_color="#3498db", opacity=0.3, yaxis="y2",
))
fig_mensal.update_layout(
    title="Churn aparente vs real — evolucao mensal",
    yaxis=dict(title="Churn (%)", range=[0, 70]),
    yaxis2=dict(title="% retorno 30d", overlaying="y", side="right", range=[0, 80]),
    height=400, width=900, legend=dict(orientation="h", y=1.12),
)

# HTML
html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Churn Real vs Aparente — dr.consulta</title>
<style>
    body {{ font-family: 'Segoe UI', Arial, sans-serif; max-width: 960px; margin: 40px auto; padding: 0 20px; color: #2c3e50; line-height: 1.6; }}
    h1 {{ color: #1B2A4A; border-bottom: 3px solid #c0392b; padding-bottom: 10px; }}
    h2 {{ color: #c0392b; margin-top: 40px; }}
    h3 {{ color: #2c3e50; }}
    .kpi-row {{ display: flex; gap: 20px; margin: 20px 0; flex-wrap: wrap; }}
    .kpi {{ background: #f8f9fa; border-radius: 8px; padding: 15px 20px; flex: 1; min-width: 180px; border-left: 4px solid #3498db; }}
    .kpi-value {{ font-size: 28px; font-weight: bold; color: #2c3e50; }}
    .kpi-label {{ font-size: 13px; color: #7f8c8d; }}
    .kpi-delta {{ font-size: 12px; color: #95a5a6; }}
    .kpi-red {{ border-left-color: #c0392b; }}
    .kpi-green {{ border-left-color: #27ae60; }}
    .kpi-blue {{ border-left-color: #3498db; }}
    table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
    th, td {{ border: 1px solid #ddd; padding: 10px 14px; text-align: left; }}
    th {{ background: #1B2A4A; color: white; }}
    tr:nth-child(even) {{ background: #f8f9fa; }}
    .evidencia {{ background: #fafafa; border-left: 4px solid #3498db; padding: 20px; margin: 20px 0; border-radius: 4px; }}
    .conclusao {{ background: #fdedec; border-left: 4px solid #c0392b; padding: 20px; margin: 20px 0; border-radius: 4px; }}
    .fonte {{ background: #eaf2f8; padding: 15px; border-radius: 4px; font-size: 13px; margin: 15px 0; }}
    .grafico {{ margin: 25px 0; text-align: center; }}
</style>
</head>
<body>

<h1>🔎 Churn Real vs Churn Aparente</h1>
<p style="color: #7f8c8d;">Analise de Churn — dr.consulta | Dados: ultimos 30 meses | Contratos credit card 6/12m</p>

<hr>

<h2>O churn que medimos nao e o churn real</h2>

<p>Nos ultimos 30 meses, analisamos <strong>{total_base:,} contratos</strong> de cartao de credito
(planos de 6 e 12 meses, sem B2B).</p>

<p>Desses:</p>
<ul>
    <li><strong>{total_retidos:,}</strong> renovaram normalmente ({pct_retidos}%)</li>
    <li><strong>{total_churners:,}</strong> nao renovaram na data do vencimento ({pct_churn_ap}%) — o "churn aparente"</li>
</ul>

<p>Mas dos {total_churners:,} que nao renovaram:</p>
<ul>
    <li><strong>{total_voltaram:,}</strong> voltaram em ate 30 dias ({pct_voltaram}% dos churners) — sao <strong>retentativas de pagamento</strong></li>
    <li><strong>{total_churn_real:,}</strong> nao voltaram — sao o <strong>churn real</strong> ({pct_churn_real}% da base)</li>
</ul>

<div class="kpi-row">
    <div class="kpi">
        <div class="kpi-value">{total_base:,}</div>
        <div class="kpi-label">Contratos analisados</div>
        <div class="kpi-delta">Credit card, 6/12m, sem B2B, 30 meses</div>
    </div>
    <div class="kpi kpi-red">
        <div class="kpi-value">{total_churners:,}</div>
        <div class="kpi-label">Churners aparentes</div>
        <div class="kpi-delta">{pct_churn_ap}% da base</div>
    </div>
    <div class="kpi kpi-blue">
        <div class="kpi-value">{total_voltaram:,}</div>
        <div class="kpi-label">Voltaram em 30 dias</div>
        <div class="kpi-delta">{pct_voltaram}% dos churners — retentativa de pagamento</div>
    </div>
    <div class="kpi kpi-red">
        <div class="kpi-value">{total_churn_real:,}</div>
        <div class="kpi-label">Churn REAL</div>
        <div class="kpi-delta">{pct_churn_real}% da base — pacientes que realmente sairam</div>
    </div>
</div>

<div class="grafico">{pio.to_html(fig_pizza, full_html=False, include_plotlyjs='cdn')}</div>

<table>
<tr><th>Grupo</th><th>Volume</th><th>%</th><th>O que acontece</th></tr>
<tr><td>🟢 Renova normalmente</td><td>{total_retidos:,}</td><td>{pct_retidos}%</td><td>Pagamento passou na data, contrato continua</td></tr>
<tr><td>🔵 Renovacao tardia</td><td>{total_voltaram:,}</td><td>{round(100*total_voltaram/total_base,1)}%</td><td>Pagamento falhou, sistema retentou em 15-21 dias e passou</td></tr>
<tr><td>🔴 Churn real</td><td>{total_churn_real:,}</td><td>{pct_churn_real}%</td><td>Paciente saiu de verdade (cancelou ou pagamento nunca passou)</td></tr>
</table>

<div class="fonte">
<strong>De onde vem cada numero:</strong><br>
• <strong>{total_base:,} contratos</strong>: todos os contratos credit card, 6/12m, sem B2B, vencidos nos ultimos 30 meses.<br>
• <strong>{total_churners:,} churners aparentes</strong>: contratos sem renovacao automatica na data de vencimento.<br>
• <strong>{total_voltaram:,} voltaram em 30d</strong>: campo days_diff_until_next_contract indica extensao em ate 30 dias. Nao e contrato novo — e o mesmo contrato reativado apos pagamento passar.<br>
• <strong>{total_churn_real:,} churn real</strong>: churners que NAO tiveram extensao em 30 dias.
</div>

<hr>

<h2>Evidencia 1: voltam exatamente entre 15-21 dias</h2>

<div class="evidencia">
Dos <strong>{len(dias):,}</strong> contratos que "voltam" em ate 30 dias,
<strong>{n_15_21:,} ({pct_15_21}%)</strong> retornam especificamente entre 15 e 21 dias.
A mediana e de <strong>{int(dias.median())} dias</strong>.
<br><br>
Essa concentracao num intervalo tao especifico nao e decisao humana — e o
<strong>ciclo de retentativa automatica de pagamento</strong>.
</div>

<div class="grafico">{pio.to_html(fig_hist, full_html=False, include_plotlyjs=False)}</div>

<hr>

<h2>Evidencia 2: a maioria nem sabia que "churnou"</h2>

<div class="evidencia">
~75% do churn e silencioso — o paciente nao pediu cancelamento.
Para quem "volta em 30 dias", o cenario e ainda mais claro: o paciente
nem percebeu que estava "churado". O pagamento falhou e foi reprocessado
automaticamente 2-3 semanas depois.
</div>

<hr>

<h2>Evidencia 3: nao existe contrato de retorno</h2>

<div class="evidencia">
Quando tentamos encontrar o "contrato de retorno" na base, nao existe
um contract_id separado. O days_diff_until_next_contract aponta pra uma
extensao do <strong>mesmo contrato</strong>. O paciente nao "saiu e voltou" — o pagamento
falhou, o sistema retentou, e o contrato existente foi reativado.
</div>

<hr>

<h2>Evidencia 4: o padrao varia com o processamento</h2>

<div class="evidencia">
O % de retorno em 30 dias varia de 12% a 70% dependendo do mes, acompanhando
mudancas no sistema de pagamento — nao no comportamento do paciente.
A queda abrupta em abr-mai/2026 coincide com a mudanca no sistema Adyen.
</div>

<div class="grafico">{pio.to_html(fig_mensal, full_html=False, include_plotlyjs=False)}</div>

<hr>

<h2>Evidencia 5: o score confirma</h2>

<div class="kpi-row">
    <div class="kpi">
        <div class="kpi-value">0.590</div>
        <div class="kpi-label">AUC com churn aparente</div>
    </div>
    <div class="kpi kpi-green">
        <div class="kpi-value">0.654</div>
        <div class="kpi-label">AUC com churn real</div>
        <div class="kpi-delta">+0.064 de melhora</div>
    </div>
    <div class="kpi kpi-green">
        <div class="kpi-value">89 p.p.</div>
        <div class="kpi-label">Spread entre faixas</div>
        <div class="kpi-delta">vs 28 p.p. antes</div>
    </div>
</div>

<p>O modelo nao conseguia prever o churn aparente porque metade dos "churners"
nao tinha perfil de churner — eram pessoas normais cujo pagamento atrasou 15 dias.
Remover esse ruido fez o AUC saltar de 0.59 pra 0.65.</p>

<hr>

<div class="conclusao">
<h2>Conclusao</h2>

<table>
<tr><th>Evidencia</th><th>O que mostra</th></tr>
<tr><td>Timing</td><td>80.6% voltam entre 15-21 dias — ciclo de retentativa automatica</td></tr>
<tr><td>Perfil</td><td>Maioria nao pediu cancelamento — nem sabia que churnou</td></tr>
<tr><td>Contrato</td><td>Nao existe contrato de retorno — e o mesmo contrato reativado</td></tr>
<tr><td>Variacao mensal</td><td>% de retorno acompanha mudancas no sistema, nao no paciente</td></tr>
<tr><td>Score</td><td>AUC salta de 0.59 pra 0.65 ao excluir — o modelo confirma</td></tr>
</table>

<p><strong>O churn real e ~{pct_churn_real}%, nao ~{pct_churn_ap}%.</strong>
Os outros ~{round(pct_churn_ap - pct_churn_real)}% sao retentativas de pagamento que demoram
15-21 dias pra processar.</p>

<p>A implicacao: o problema de <strong>churn real</strong> ({pct_churn_real}%) e de <strong>retencao</strong>.
O problema dos <strong>{round(pct_churn_ap - pct_churn_real)}% aparentes</strong> e de <strong>pagamento/cobranca</strong>.
Sao areas diferentes com acoes diferentes.</p>
</div>

<p style="color: #95a5a6; font-size: 12px; margin-top: 40px;">
Dados & Analytics — dr.consulta | Gerado automaticamente
</p>

</body>
</html>"""

with open("churn_real_vs_aparente.html", "w", encoding="utf-8") as f:
    f.write(html)

print("Salvo: churn_real_vs_aparente.html")
print("Abra no navegador pra visualizar.")
