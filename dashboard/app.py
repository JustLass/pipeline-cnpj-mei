"""
app.py
------
Entrypoint do Dashboard MEI — Streamlit.

Executar com:
    cd dashboard
    streamlit run app.py
"""

import streamlit as st
from streamlit_option_menu import option_menu

from views import visao_geral, analise_temporal, analise_geografica, analise_cnae, consulta_cadastral

# ---------------------------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Dashboard MEI — Receita Federal",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# CSS CUSTOMIZADO — Tema escuro premium v3
# ---------------------------------------------------------------------------

st.markdown("""
<style>
    /* === Google Fonts === */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    /* Ocultar botão de Deploy do Streamlit e o menu padrão no canto superior direito */
    .stDeployButton,
    [data-testid="stAppDeployButton"],
    [data-testid="stMainMenu"],
    [data-testid="stHeaderActionButton"] {
        display: none !important;
        visibility: hidden !important;
        width: 0 !important;
        height: 0 !important;
    }

    /* Tornar o cabeçalho superior transparente para não interferir no tema escuro */
    header[data-testid="stHeader"] {
        background-color: transparent !important;
        background: transparent !important;
    }

    /* === Reset global === */
    html, body, [class*="css"], p, span, div, label, li, a {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    /* ====================================================================
       FUNDO PRINCIPAL — Gradiente sutil escuro
       ==================================================================== */
    .stApp {
        background: linear-gradient(160deg, #0a0e1a 0%, #0f1629 40%, #0a0e1a 100%) !important;
    }

    /* === Main content area === */
    .main .block-container {
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
        max-width: 1440px !important;
    }

    /* ====================================================================
       SIDEBAR
       ==================================================================== */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #111827 0%, #0a0e1a 100%) !important;
        border-right: 1px solid rgba(255,255,255,0.06) !important;
    }

    section[data-testid="stSidebar"] .stMarkdown h1,
    section[data-testid="stSidebar"] .stMarkdown h2,
    section[data-testid="stSidebar"] .stMarkdown h3 {
        color: #F1F5F9 !important;
        font-size: 1.3rem !important;
    }

    section[data-testid="stSidebar"] .stCaption,
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
        color: #94A3B8 !important;
        font-size: 0.9rem !important;
    }

    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] label {
        color: #CBD5E1 !important;
        font-size: 0.95rem !important;
    }

    /* ====================================================================
       CARDS DE MÉTRICAS — Bordas sutis e brilho
       ==================================================================== */
    div[data-testid="stMetric"] {
        background: linear-gradient(145deg, #1a1f35, #151a2e) !important;
        border: 1px solid rgba(99, 102, 241, 0.15) !important;
        border-radius: 16px !important;
        padding: 22px 26px !important;
        box-shadow:
            0 4px 20px rgba(0, 0, 0, 0.35),
            inset 0 1px 0 rgba(255, 255, 255, 0.04) !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        position: relative;
        overflow: hidden;
    }

    div[data-testid="stMetric"]::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: linear-gradient(90deg, #6366F1, #A78BFA, #818CF8);
        opacity: 0.7;
    }

    div[data-testid="stMetric"]:hover {
        transform: translateY(-3px) !important;
        border-color: rgba(99, 102, 241, 0.35) !important;
        box-shadow:
            0 8px 32px rgba(0, 0, 0, 0.5),
            0 0 40px rgba(99, 102, 241, 0.06),
            inset 0 1px 0 rgba(255, 255, 255, 0.06) !important;
    }

    /* LABEL do metric — tamanho GRANDE e CLARO */
    div[data-testid="stMetric"] label {
        color: #94A3B8 !important;
        font-weight: 500 !important;
        font-size: 0.95rem !important;
        letter-spacing: 0.01em !important;
    }

    /* VALOR do metric — GRANDE e BRANCO */
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #F1F5F9 !important;
        font-weight: 700 !important;
        font-size: 1.85rem !important;
        letter-spacing: -0.02em !important;
    }

    /* ====================================================================
       DIVIDER
       ==================================================================== */
    hr {
        border-color: rgba(255,255,255,0.06) !important;
        opacity: 1 !important;
        margin: 1.8rem 0 !important;
    }

    /* ====================================================================
       HEADERS — Grandes e claros
       ==================================================================== */
    h1 {
        color: #F1F5F9 !important;
        font-weight: 800 !important;
        font-size: 2.2rem !important;
        letter-spacing: -0.03em !important;
    }

    h2 {
        color: #E2E8F0 !important;
        font-weight: 700 !important;
        font-size: 1.5rem !important;
        letter-spacing: -0.02em !important;
    }

    h3 {
        color: #CBD5E1 !important;
        font-weight: 600 !important;
        font-size: 1.25rem !important;
        letter-spacing: -0.01em !important;
    }

    /* ====================================================================
       CAPTIONS / BODY TEXT
       ==================================================================== */
    .stCaption, [data-testid="stCaptionContainer"] {
        color: #94A3B8 !important;
        font-size: 0.95rem !important;
    }

    p, .stMarkdown p {
        color: #CBD5E1 !important;
        font-size: 1rem !important;
        line-height: 1.6 !important;
    }

    /* ====================================================================
       DATAFRAMES
       ==================================================================== */
    .stDataFrame {
        border: 1px solid rgba(255,255,255,0.08) !important;
        border-radius: 12px !important;
        overflow: hidden !important;
    }

    /* ====================================================================
       TABS — Pílulas escuras
       ==================================================================== */
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px !important;
        background: rgba(255,255,255,0.03) !important;
        border-radius: 12px !important;
        padding: 4px !important;
    }

    .stTabs [data-baseweb="tab"] {
        background: transparent !important;
        border-radius: 8px !important;
        color: #94A3B8 !important;
        border: none !important;
        padding: 12px 24px !important;
        font-weight: 500 !important;
        font-size: 0.95rem !important;
        transition: all 0.2s ease !important;
    }

    .stTabs [aria-selected="true"] {
        background: rgba(99, 102, 241, 0.12) !important;
        color: #A5B4FC !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3) !important;
        font-weight: 600 !important;
    }

    /* ====================================================================
       EXPANDER
       ==================================================================== */
    details {
        background: #151a2e !important;
        border: 1px solid rgba(255,255,255,0.06) !important;
        border-radius: 12px !important;
    }

    details summary {
        color: #E2E8F0 !important;
        font-weight: 500 !important;
        font-size: 1rem !important;
    }

    /* ====================================================================
       INPUTS — Selectbox, Multiselect, TextInput
       ==================================================================== */
    .stSelectbox > div > div,
    .stMultiSelect > div > div,
    .stTextInput > div > div > input {
        background-color: #151a2e !important;
        border-color: rgba(255,255,255,0.1) !important;
        color: #E2E8F0 !important;
        border-radius: 10px !important;
        font-size: 0.95rem !important;
    }

    .stSelectbox label,
    .stMultiSelect label,
    .stTextInput label {
        color: #CBD5E1 !important;
        font-size: 0.95rem !important;
        font-weight: 500 !important;
    }

    /* ====================================================================
       SLIDER
       ==================================================================== */
    .stSlider label {
        color: #CBD5E1 !important;
        font-size: 0.95rem !important;
        font-weight: 500 !important;
    }

    .stSlider [data-testid="stTickBarMin"],
    .stSlider [data-testid="stTickBarMax"] {
        color: #94A3B8 !important;
        font-size: 0.9rem !important;
    }

    /* ====================================================================
       ALERTS — st.info, st.success, st.warning, st.error
       ==================================================================== */
    .stAlert > div {
        border-radius: 12px !important;
        font-size: 0.95rem !important;
    }

    /* ====================================================================
       PLOTLY CHARTS CONTAINER — Card escuro
       ==================================================================== */
    [data-testid="stPlotlyChart"] {
        background: #111827 !important;
        border: 1px solid rgba(255,255,255,0.06) !important;
        border-radius: 16px !important;
        padding: 16px !important;
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3) !important;
    }

    /* ====================================================================
       SCROLLBAR
       ==================================================================== */
    ::-webkit-scrollbar {
        width: 6px;
        height: 6px;
    }
    ::-webkit-scrollbar-track {
        background: transparent;
    }
    ::-webkit-scrollbar-thumb {
        background: rgba(255,255,255,0.12);
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #6366F1;
    }

    /* ====================================================================
       SIDEBAR FOOTER
       ==================================================================== */
    .sidebar-footer {
        position: fixed;
        bottom: 16px;
        padding: 0 20px;
        color: #64748B;
        font-size: 0.78rem;
        line-height: 1.7;
    }

    /* ====================================================================
       SPINNER
       ==================================================================== */
    .stSpinner > div {
        border-top-color: #818CF8 !important;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# SIDEBAR — Navegação
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("## 📊 Dashboard MEI")
    st.caption("Dados Abertos CNPJ — Receita Federal")
    st.divider()

    pagina = option_menu(
        menu_title=None,
        options=[
            "Visão Geral",
            "Análise Temporal",
            "Análise Geográfica",
            "Análise por CNAE",
            "Consulta Cadastral",
        ],
        icons=[
            "bar-chart-fill",
            "graph-up",
            "geo-alt-fill",
            "building",
            "search",
        ],
        default_index=0,
        styles={
            "container": {
                "padding": "0 !important",
                "background-color": "transparent !important",
            },
            "menu-title": {
                "display": "none",
            },
            "icon": {
                "color": "#A5B4FC",
                "font-size": "18px",
            },
            "nav-link": {
                "font-size": "15px",
                "font-weight": "500",
                "text-align": "left",
                "margin": "4px 0",
                "padding": "14px 18px",
                "border-radius": "10px",
                "color": "#CBD5E1",
                "background-color": "transparent",
                "font-family": "Inter, sans-serif",
                "transition": "all 0.2s ease",
            },
            "nav-link-selected": {
                "background-color": "rgba(99, 102, 241, 0.15)",
                "color": "#A5B4FC",
                "font-weight": "600",
                "border-left": "3px solid #818CF8",
            },
        },
    )

    st.divider()
    st.markdown(
        '<div class="sidebar-footer">'
        "Fonte: Receita Federal do Brasil<br>"
        "Snapshot: Dezembro 2025<br>"
        "Polars · Plotly · MongoDB"
        "</div>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# ROTEAMENTO DE PÁGINAS
# ---------------------------------------------------------------------------

if pagina == "Visão Geral":
    visao_geral.render()
elif pagina == "Análise Temporal":
    analise_temporal.render()
elif pagina == "Análise Geográfica":
    analise_geografica.render()
elif pagina == "Análise por CNAE":
    analise_cnae.render()
elif pagina == "Consulta Cadastral":
    consulta_cadastral.render()
