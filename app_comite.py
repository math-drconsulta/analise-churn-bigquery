import streamlit as st

from comite_scoring import (
    BANDS_MODE_ASYMMETRIC,
    BANDS_MODE_FIXED,
    BANDS_MODE_LABELS,
    BANDS_MODE_SYMMETRIC,
)

st.set_page_config(
    page_title="dr.consulta · Churn Comitê",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)

pages = [
    st.Page("pages_comite/1_Panorama.py", title="Panorama", icon="🌐", default=True),
    st.Page("pages_comite/2_Narrativa.py", title="Narrativa", icon="📖"),
    st.Page("pages_comite/3_Drivers_Validados.py", title="Drivers Validados", icon="📐"),
    st.Page("pages_comite/4_Score_e_Faixas.py", title="Score e Faixas", icon="🎯"),
    st.Page("pages_comite/5_Transicao_Faixas.py", title="Transição entre Faixas", icon="🔄"),
    st.Page("pages_comite/6_Acoes.py", title="Ações", icon="✅"),
    st.Page("pages_comite/7_Score_Individual.py", title="Score Individual (Fase 1)", icon="🧮"),
]

nav = st.navigation(pages, position="sidebar")

# Configuração global de faixas — toggle propagado para Páginas 4, 5 e 6 via session_state.
if "bands_mode" not in st.session_state:
    st.session_state.bands_mode = BANDS_MODE_ASYMMETRIC

with st.sidebar:
    st.markdown("### 🩺 Churn — Comitê CEO")
    st.caption("Visão executiva enxuta · 6m vs 12m · 4 variáveis core")
    st.markdown("---")
    st.markdown("### ⚙️ Faixas do score")
    st.session_state.bands_mode = st.radio(
        "Estratégia de cortes:",
        options=[BANDS_MODE_ASYMMETRIC, BANDS_MODE_SYMMETRIC, BANDS_MODE_FIXED],
        format_func=lambda m: BANDS_MODE_LABELS[m],
        key="bands_mode_radio",
        help=(
            "Assimétrico (default): 10/15/25/25/25 — concentra extremos, "
            "maior spread em 12m. "
            "Simétrico: 20/20/20/20/20 (equilibrado). "
            "Fixo: cortes constantes por valor de score."
        ),
    )
    st.markdown("---")

nav.run()
