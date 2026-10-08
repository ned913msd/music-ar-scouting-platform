import time

# Instante de arranque del script: alimenta el indicador de carga del sidebar
# (cada re-render de Streamlit vuelve a ejecutar el archivo desde aquí).
_T0 = time.perf_counter()

import base64
import json
import math

import streamlit as st
import pandas as pd
import joblib
import os
import yaml

import streamlit_authenticator as stauth

# Lazy loading: pesadas SOLO cuando se usan (ver cargar_generador_pdf y las
# vistas): reporte_pdf (fpdf+PIL ≈0.35 s), prophet/lifelines/folium ya se
# importan dentro de sus vistas/motores. Nada de eso corre en la portada.
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(
    page_title="A&R Scouting Command Center - Deezer Data",
    page_icon="🎧",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def cargar_generador_pdf():
    """Importa el motor de informes BAJO DEMANDA.

    reporte_pdf trae fpdf + PIL + touring_engine (≈0.35 s de import) y solo
    se usa al pulsar "Generar Informe": cargarlo en el arranque retrasaba la
    portada sin aportar nada.
    """
    from reporte_pdf import generar_reporte_pdf

    return generar_reporte_pdf

# Tema visual (oscuro por defecto). Se guarda en data/preferencias.json para
# que sobreviva a un reload de página: session_state NO sobrevive a reload.
_RUTA_PREFERENCIAS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "preferencias.json"
)


def leer_tema():
    try:
        with open(_RUTA_PREFERENCIAS, encoding="utf-8") as f:
            tema = json.load(f).get("tema", "oscuro")
        return "claro" if tema == "claro" else "oscuro"
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return "oscuro"


def guardar_tema(tema):
    try:
        with open(_RUTA_PREFERENCIAS, "w", encoding="utf-8") as f:
            json.dump({"tema": tema}, f, ensure_ascii=False, indent=2)
    except OSError:
        pass

# Inyecta DESPUÉS del CSS base (misma especificidad → gana el cascada):
# sólo se emite cuando el usuario elige modo claro.
_CSS_CLARO = """
    /* ==========================================
       TEMA CLARO (A&R Scouting)
       ========================================== */
    :root {
        --background-color: #f5f7fb !important;
        --secondary-background-color: #ffffff !important;
        --text-color: #10142a !important;
        --primary-color: #0066FF !important;
        --arrow-data-text-color: #10142a;
        --arrow-header-text-color: #10142a;
        --arrow-header-bgcolor: #f0f2f6;
        --arrow-border-color: rgba(15, 23, 42, 0.12);
    }

    .stApp {
        background: linear-gradient(135deg, #f5f7fb 0%, #eef1f8 50%, #f7f9fc 100%) !important;
        background-size: 100% 100% !important;
        color: #10142a !important;
        animation: none !important;
    }

    [data-testid="stSidebar"] {
        background: #ffffff !important;
        color: #10142a !important;
    }
    [data-testid="stHeader"] { background: transparent !important; }

    /* Widgets que el CSS base tiñe a mano */
    [data-testid="stSidebar"] [data-testid="stMultiSelect"] input { color: #10142a !important; }
    [data-testid="stSidebar"] [data-testid="stSlider"] { color: #475569 !important; }

    /* Cards: cristal claro sobre página clara */
    .glass-card,
    .neumorphic-card {
        background: rgba(255, 255, 255, 0.88) !important;
        border: 1px solid rgba(15, 23, 42, 0.12) !important;
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.10) !important;
        color: #10142a !important;
    }
    .glass-card:hover,
    .neumorphic-card:hover {
        border-color: rgba(0, 102, 255, 0.55) !important;
        box-shadow: 0 10px 30px rgba(0, 102, 255, 0.16) !important;
    }

    .artist-name { color: #0f172a !important; }
    .artist-meta { color: #475569 !important; }
    .artist-track { color: #334155 !important; }
    .insight-pill { background: rgba(0, 102, 255, 0.10) !important; }
    .insight-pill span { color: #1d4ed8 !important; }
    .stat-label { color: #64748b !important; }
    .stat-value-dark { color: #0f172a !important; }
    .viral-track { background: #e2e8f0 !important; }
    .deezer-link { color: #0066FF !important; }
    .artist-photo { box-shadow: 0 6px 18px rgba(15, 23, 42, 0.25) !important; }

    /* KPIs: ficha clara, cifra con contraste */
    .kpi-card {
        background: linear-gradient(145deg, rgba(0, 102, 255, 0.08), rgba(0, 150, 136, 0.08)) !important;
        border: 1px solid rgba(0, 102, 255, 0.28) !important;
        backdrop-filter: none !important;
        -webkit-backdrop-filter: none !important;
    }
    .kpi-value {
        background: linear-gradient(135deg, #0052cc, #00838f) !important;
        -webkit-background-clip: text !important;
        background-clip: text !important;
        -webkit-text-fill-color: transparent !important;
    }
    .kpi-label { color: #475569 !important; }

    /* Cargadores y barras */
    .loading-spinner p { color: #475569 !important; }
    .spinner {
        border: 4px solid #dbe3ef !important;
        border-top-color: #0066FF !important;
        box-shadow: none !important;
    }
    .skeleton,
    .skeleton-circle {
        background: linear-gradient(90deg, #e9edf5 25%, #f4f6fb 50%, #e9edf5 75%) !important;
        background-size: 200% 100% !important;
    }
    .progress-bar-container {
        background: #e9edf5 !important;
        box-shadow: inset 2px 2px 4px rgba(15, 23, 42, 0.12) !important;
    }

    /* Avisos de Streamlit (info/warning/error) legibles */
    [data-testid="stAlert"] {
        background: rgba(255, 255, 255, 0.92) !important;
        border: 1px solid rgba(15, 23, 42, 0.12) !important;
        color: #10142a !important;
    }

    /* Texto heredado: el CSS base tiñe labels/markdown con slate claro,
       ilegible sobre página clara */
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] p,
    [data-testid="stWidgetLabel"] p,
    [data-testid="stRadio"] label,
    [data-testid="stRadio"] span,
    [data-testid="stCheckbox"] label,
    [data-testid="stToggle"] label,
    [data-testid="stExpander"] summary,
    [data-testid="stExpander"] summary * {
        color: #334155 !important;
    }

    /* Cabecera de expander: el base la deja azul noche */
    [data-testid="stExpander"] summary,
    [data-testid="stExpander"] summary * {
        background: #ffffff !important;
    }
    [data-testid="stExpander"] details > summary {
        border-bottom: 1px solid rgba(15, 23, 42, 0.10) !important;
    }

    /* Cajas de entrada: fondo blanco, tinta oscura */
    .stTextInput > div > div,
    [data-testid="stTextInput"] div,
    [data-testid="stMultiSelect"] div,
    .stSelectbox > div > div > select {
        background: #ffffff !important;
        border-color: rgba(15, 23, 42, 0.18) !important;
    }
    .stTextInput > div > div > input,
    [data-testid="stTextInput"] input,
    [data-testid="stMultiSelect"] input,
    .stSelectbox > div > div > select {
        background: #ffffff !important;
        color: #10142a !important;
    }

    /* Sin resplandor neón en títulos (sobre fondo claro ensucia) */
    h1, h2, h3 {
        text-shadow: none !important;
    }
    /* Streamlit envuelve el texto del título en un span con su propio
       color (slate-300): ilegible sobre página clara */
    h1 span[data-heading-text],
    h2 span[data-heading-text],
    h3 span[data-heading-text],
    h4 span[data-heading-text] {
        color: #10142a !important;
    }

    /* Scrollbar discreto */
    ::-webkit-scrollbar-track { background: #eef1f6 !important; }
"""


def load_custom_css(tema="oscuro"):
    """CYBERPUNK ENTERPRISE THEME: plataforma SaaS oscura tipo Bloomberg
    Terminal / Spotify for Artists. Glassmorphism (cristal esmerilado) en
    cards y KPIs, acentos neón azul→púrpura→cian, tipografía Inter +
    JetBrains Mono para cifras, scrollbar neón y micro-interacciones
    (ripple, page transition, stagger con overshoot).
    Selectores estables (data-testid) en vez de hashes .css-*, que cambian
    entre versiones de Streamlit."""
    custom_css = """
    <style>
    /* ==========================================
       CYBERPUNK ENTERPRISE THEME
       ========================================== */

    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=JetBrains+Mono:wght@400;700&display=swap');

    /* Fondo con gradiente animado (oscuro por defecto: look SaaS) */
    .stApp {
        background: linear-gradient(135deg, #0a0e27 0%, #161c42 50%, #0f1535 100%);
        background-size: 400% 400%;
        color: #e2e8f0;
        animation:
            pageTransition 0.8s cubic-bezier(0.4, 0, 0.2, 1),
            gradientShift 15s ease infinite;
    }

    @keyframes gradientShift {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }

    @keyframes pageTransition {
        0% {
            opacity: 0;
            transform: scale(0.98) translateY(10px);
            filter: blur(4px);
        }
        100% {
            opacity: 1;
            transform: scale(1) translateY(0);
            filter: blur(0);
        }
    }

    header[data-testid="stHeader"] { background: transparent; }

    /* ==========================================
       GLASSMORPHISM CARDS
       ========================================== */
    .glass-card,
    .neumorphic-card {
        background: rgba(255, 255, 255, 0.03);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 22px;
        margin-bottom: 18px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.37);
        transition: all 0.3s ease;
        animation: fadeInUp 0.6s ease-out;
    }

    .glass-card:hover,
    .neumorphic-card:hover {
        border-color: rgba(0, 102, 255, 0.5);
        box-shadow: 0 10px 34px rgba(0, 102, 255, 0.15);
        transform: translateY(-3px);
    }

    @keyframes fadeInUp {
        from { opacity: 0; transform: translateY(24px); }
        to { opacity: 1; transform: translateY(0); }
    }

    /* STAGGER: entrada con rebote (overshoot) para las cards de artista.
       El delay real se aplica INLINE por card (cada card es hija única de
       su wrapper en el DOM: nth-child no staggeriza entre st.markdown) */
    .neumorphic-card.artist-card {
        opacity: 0;
        transform: translateY(40px);
        animation: staggerSlideIn 0.7s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
    }

    @keyframes staggerSlideIn {
        0% { opacity: 0; transform: translateY(40px) scale(0.95); }
        100% { opacity: 1; transform: translateY(0) scale(1); }
    }

    /* ==========================================
       KPIs ESTILO BLOOMBERG TERMINAL
       ========================================== */
    .kpi-container {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 20px;
        margin-bottom: 10px;
    }

    .kpi-card {
        background: linear-gradient(145deg, rgba(0, 102, 255, 0.10), rgba(138, 43, 226, 0.10));
        border: 1px solid rgba(0, 102, 255, 0.25);
        border-radius: 14px;
        padding: 20px;
        text-align: center;
        position: relative;
        overflow: hidden;
        backdrop-filter: blur(8px);
        -webkit-backdrop-filter: blur(8px);
        transition: all 0.3s ease;
        animation: fadeInUp 0.6s ease-out both;
    }

    /* Barra superior degradada con barrido (shimmer) */
    .kpi-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 2px;
        background: linear-gradient(90deg, #0066FF, #8A2BE2, #00CED1);
        animation: shimmer 3s infinite;
    }

    @keyframes shimmer {
        0% { background-position: -1000px 0; }
        100% { background-position: 1000px 0; }
    }

    /* Entrada escalonada de los KPIs */
    .kpi-card:nth-child(1) { animation-delay: 0.1s; }
    .kpi-card:nth-child(2) { animation-delay: 0.2s; }
    .kpi-card:nth-child(3) { animation-delay: 0.3s; }
    .kpi-card:nth-child(4) { animation-delay: 0.4s; }

    .kpi-card:hover {
        transform: translateY(-4px);
        border-color: rgba(0, 102, 255, 0.6);
        box-shadow: 0 10px 30px rgba(0, 102, 255, 0.2);
    }

    .kpi-value {
        font-family: 'JetBrains Mono', monospace;
        font-size: 2.4rem;
        font-weight: 700;
        margin: 10px 0;
        background: linear-gradient(135deg, #4d94ff, #00CED1);
        -webkit-background-clip: text;
        background-clip: text;
        -webkit-text-fill-color: transparent;
        animation: countUp 1s ease-out;
    }

    /* Valores largos ($3,190,540 / nombres de ciudad): tamaño compacto */
    .kpi-value.kpi-value-sm {
        font-size: 1.7rem;
    }

    .kpi-label {
        font-size: 0.85rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 1px;
        font-weight: 600;
        transition: color 0.3s ease;
    }

    .kpi-card:hover .kpi-label {
        color: #4d94ff;
    }

    @keyframes countUp {
        from { opacity: 0; transform: scale(0.5); }
        to { opacity: 1; transform: scale(1); }
    }

    /* ==========================================
       SIDEBAR PROFESIONAL
       ========================================== */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(10, 14, 39, 0.97) 0%, rgba(13, 18, 40, 0.99) 100%);
        border-right: 1px solid rgba(0, 102, 255, 0.18);
        box-shadow: 4px 0 20px rgba(0, 0, 0, 0.45);
    }

    /* Titulares con glow neón */
    h1, h2, h3 {
        color: #e2e8f0;
        font-weight: 700;
        text-shadow: 0 0 24px rgba(0, 102, 255, 0.35);
        transition: all 0.3s ease;
    }
    h4 { color: #e2e8f0; }
    p, li, span { color: #cbd5e1; }
    hr { border-color: rgba(255, 255, 255, 0.08); }

    /* Métricas nativas: glass + hover */
    [data-testid="stMetric"] {
        background: linear-gradient(145deg, rgba(0, 102, 255, 0.08), rgba(138, 43, 226, 0.08));
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 12px;
        padding: 15px;
        transition: all 0.3s ease;
    }

    [data-testid="stMetric"]:hover {
        transform: scale(1.03);
        border-color: rgba(0, 102, 255, 0.4);
    }

    /* Inputs estilo cyberpunk */
    .stTextInput > div > div > input,
    .stSelectbox > div > div > select {
        background: rgba(255, 255, 255, 0.05);
        color: #e2e8f0;
        border: 1px solid rgba(0, 102, 255, 0.3);
        border-radius: 10px;
        padding: 12px;
        transition: all 0.3s ease;
    }

    .stTextInput > div > div > input:focus,
    .stSelectbox > div > div > select:focus {
        border-color: #0066FF;
        animation: focusPulse 1.5s ease-in-out infinite;
    }

    @keyframes focusPulse {
        0%, 100% { box-shadow: 0 0 10px rgba(0, 102, 255, 0.3); }
        50% { box-shadow: 0 0 18px rgba(0, 102, 255, 0.45); }
    }

    ::placeholder { color: #64748b; }

    /* ==========================================
       BOTONES CON GLOW + RIPPLE
       ========================================== */
    .stButton > button,
    [data-testid="stBaseButton-secondary"] {
        position: relative;
        overflow: hidden;
        transform: translateZ(0); /* acelera el render en GPU */
        background: linear-gradient(145deg, #0066FF, #8A2BE2);
        color: white;
        border: none;
        border-radius: 10px;
        padding: 12px 24px;
        font-weight: 600;
        box-shadow: 0 4px 15px rgba(0, 102, 255, 0.4);
        transition: all 0.3s ease;
    }

    /* Brillo deslizante (shimmer) */
    .stButton > button::before,
    [data-testid="stBaseButton-secondary"]::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.4), transparent);
        transition: left 0.6s ease;
    }

    .stButton > button:hover::before,
    [data-testid="stBaseButton-secondary"]:hover::before {
        left: 100%;
    }

    .stButton > button:hover,
    [data-testid="stBaseButton-secondary"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0, 102, 255, 0.6);
    }

    .stButton > button:active,
    [data-testid="stBaseButton-secondary"]:active {
        transform: translateY(0);
    }

    /* Ripple: onda al hacer clic */
    .stButton > button::after,
    [data-testid="stBaseButton-secondary"]::after {
        content: "";
        position: absolute;
        top: 50%;
        left: 50%;
        width: 0;
        height: 0;
        background: rgba(255, 255, 255, 0.4);
        border-radius: 50%;
        transform: translate(-50%, -50%);
        transition: width 0.6s ease-out, height 0.6s ease-out, opacity 0.6s ease-out;
        opacity: 0;
        pointer-events: none; /* no interfiere con el clic */
    }

    .stButton > button:active::after,
    [data-testid="stBaseButton-secondary"]:active::after {
        width: 400px;
        height: 400px;
        opacity: 1;
        transition: 0s;
    }

    /* ==========================================
       INTERNOS DE LA CARD DE ARTISTA (oscuros)
       ========================================== */
    .artist-name { margin: 0; color: #f1f5f9; }
    .artist-meta { margin: 5px 0; color: #94a3b8; font-size: 0.9rem; }
    .score-value { color: #4d94ff; }
    .artist-track { margin: 5px 0; color: #cbd5e1; font-size: 0.85rem; }
    .insight-pill {
        background: rgba(0, 102, 255, 0.12);
        padding: 8px 12px;
        border-radius: 8px;
        margin-top: 10px;
    }
    .insight-pill span { color: #93c5fd; font-size: 0.85rem; }
    .stat-block { margin-bottom: 10px; }
    .stat-label {
        font-size: 0.75rem;
        color: #94a3b8;
        text-transform: uppercase;
    }
    .stat-value-blue { font-size: 1.5rem; font-weight: 700; color: #4d94ff; }
    .stat-value-dark { font-size: 1.5rem; font-weight: 700; color: #f1f5f9; }
    .viral-track {
        background: #1f2a3d;
        border-radius: 6px;
        height: 8px;
        margin-top: 4px;
        overflow: hidden;
    }
    .viral-fill {
        background: linear-gradient(90deg, #0066FF, #00CED1);
        height: 100%;
        animation: progressFill 1.5s ease-out;
    }
    .deezer-link {
        color: #4d94ff;
        text-decoration: none;
        font-weight: 600;
    }
    .artist-photo {
        width: 100%;
        height: auto;
        border-radius: 16px;
        box-shadow: 0 6px 18px rgba(0, 0, 0, 0.5);
    }

    /* ==========================================
       COMPONENTES PREMIUM
       ========================================== */
    .loading-spinner {
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 40px;
    }

    .spinner {
        width: 50px;
        height: 50px;
        border: 4px solid #1f2a3d;
        border-top: 4px solid #4d94ff;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        box-shadow:
            0 0 10px rgba(0, 102, 255, 0.3),
            inset 0 0 10px rgba(0, 102, 255, 0.1);
    }

    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }

    .loading-spinner p { color: #94a3b8 !important; }

    /* Skeleton loader (efecto tipo Facebook/LinkedIn) */
    .skeleton,
    .skeleton-circle {
        background: linear-gradient(90deg, #161d33 25%, #1f2a3d 50%, #161d33 75%);
        background-size: 200% 100%;
        animation: shimmerSkel 1.5s infinite;
        border-radius: 8px;
    }

    .skeleton {
        height: 20px;
        margin: 10px 0;
    }

    .skeleton-circle {
        width: 100px;
        height: 100px;
        border-radius: 50%;
    }

    @keyframes shimmerSkel {
        0% { background-position: 200% 0; }
        100% { background-position: -200% 0; }
    }

    /* Barra de progreso animada */
    .progress-bar-container {
        background: #111827;
        border-radius: 10px;
        padding: 4px;
        box-shadow:
            inset 2px 2px 4px rgba(0, 0, 0, 0.5),
            inset -2px -2px 4px rgba(31, 42, 61, 0.8);
        margin: 10px 0;
    }

    .progress-bar {
        background: linear-gradient(90deg, #0066FF, #00CED1);
        height: 8px;
        border-radius: 8px;
        animation: progressFill 1.5s ease-out;
        box-shadow: 0 0 10px rgba(0, 102, 255, 0.5);
    }

    @keyframes progressFill {
        from { width: 0%; }
    }

    /* Badge con pulso */
    .badge-pulse {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        animation: badgePulse 2s infinite;
    }

    @keyframes badgePulse {
        0% { box-shadow: 0 0 0 0 rgba(0, 102, 255, 0.7); }
        70% { box-shadow: 0 0 0 10px rgba(0, 102, 255, 0); }
        100% { box-shadow: 0 0 0 0 rgba(0, 102, 255, 0); }
    }

    /* Efecto shine en fotos: sobre un CONTENEDOR (los <img> son elementos
       reemplazados y no soportan pseudo-elementos ::after) */
    .image-shine {
        position: relative;
        overflow: hidden;
        border-radius: 16px;
    }

    .image-shine img {
        display: block;
        width: 100%;
        height: auto;
        border-radius: 16px;
    }

    .image-shine::after {
        content: '';
        position: absolute;
        top: -50%;
        left: -50%;
        width: 200%;
        height: 200%;
        background: linear-gradient(
            to bottom right,
            rgba(255, 255, 255, 0) 0%,
            rgba(255, 255, 255, 0.1) 50%,
            rgba(255, 255, 255, 0) 100%
        );
        transform: rotate(45deg);
        animation: shine 3s infinite;
        pointer-events: none;
    }

    @keyframes shine {
        0% { transform: translateX(-100%) translateY(-100%) rotate(45deg); }
        100% { transform: translateX(100%) translateY(100%) rotate(45deg); }
    }

    /* ==========================================
       SCROLLBAR NEÓN
       ========================================== */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }

    ::-webkit-scrollbar-track {
        background: rgba(10, 14, 39, 0.6);
        border-radius: 4px;
    }

    ::-webkit-scrollbar-thumb {
        background: linear-gradient(180deg, #0066FF, #8A2BE2);
        border-radius: 4px;
    }

    ::-webkit-scrollbar-thumb:hover {
        background: linear-gradient(180deg, #00CED1, #0066FF);
    }

    /* Widgets nativos: el contenedor de chips del multiselect toma el
       secondaryBackgroundColor del tema global mediante clases emotion
       (hashes inestables entre versiones). Transparencia estructural. */
    [data-testid="stSidebar"] [data-testid="stMultiSelect"] div {
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }
    [data-testid="stSidebar"] [data-testid="stMultiSelect"] input {
        color: #e2e8f0 !important;
    }
    [data-testid="stSidebar"] [data-testid="stSlider"] {
        color: #94a3b8;
    }

    /* Accesibilidad: sin movimiento para quien lo pide al sistema.
       Sin esto, las cards quedarían en opacity:0 (estado base del stagger)
       con las animaciones desactivadas. */
    @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after {
            animation-duration: 0.01ms !important;
            animation-iteration-count: 1 !important;
            transition-duration: 0.01ms !important;
        }
        .neumorphic-card.artist-card {
            opacity: 1 !important;
            transform: none !important;
        }
    }
    </style>
    """
    if tema == "claro":
        custom_css = custom_css.replace("</style>", _CSS_CLARO + "\n    </style>")
    st.markdown(custom_css, unsafe_allow_html=True)


def display_kpi_grid(kpis):
    """KPIs estilo Bloomberg. Compone las cards en UN solo bloque HTML
    (varios st.markdown romperían el <div class="kpi-container">: Streamlit
    envuelve cada st.markdown en su propio div del DOM)."""
    cards = "".join(
        f'<div class="kpi-card"><div class="kpi-label">{icon} {label}</div>'
        f'<div class="kpi-value{" kpi-value-sm" if len(str(value)) > 8 else ""}">{value}</div></div>'
        for label, value, icon in kpis
    )
    st.markdown(
        f'<div class="kpi-container">{cards}</div>', unsafe_allow_html=True
    )

# Fase 4 — etiquetas de acción sobre la misma columna `riesgo` del perfil y
# la tabla (Alto >30%, Medio >10%, Bajo el resto en prob. de breakout a 6M).
ACCION_RIESGO = {
    "Alto": ("🔥 FIRMA INMEDIATA", "#FF4444"),
    "Medio": ("👀 OBSERVAR DE CERCA", "#FFA500"),
    "Bajo": ("⏳ ESPERAR MÁS DATOS", "#6B7280"),
}


def ventana_firma_cox_html(row):
    """Badge de acción + ventana de firma para las cards (Fase 4).

    Vacío si la columna `riesgo` no existe (Cox no desplegado): la card queda
    exactamente como antes, sin romper el render."""
    etiqueta, color = ACCION_RIESGO.get(row.get("riesgo", "—"), (None, None))
    if etiqueta is None:
        return ""
    mes = row.get("mes_optimo_firma")
    if pd.isna(mes):
        ventana = "Ventana: riesgo &lt;10% los 12 meses"
    else:
        ventana = (
            f'Ventana óptima: <strong style="color:#00CED1;">Mes {int(mes)}</strong>'
        )
    return (
        f'<span class="badge-pulse" style="background-color: {color}; color: #fff; '
        'padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; '
        'display: inline-block; margin: 6px 0 4px;">'
        f"{etiqueta}</span>"
        f'<p style="margin: 0 0 6px; font-size: 0.8rem; color: #94a3b8;">{ventana}</p>'
    )


def artist_card_html(row, photo_data_uri=None, index=0):
    """Card de artista glassmórfica (hero). Conserva las features del tablero
    anterior que el HTML plano del tutorial descartaba: Probabilidad de
    Viralidad (ML) con barra, y fallback de foto si la CDN falla."""
    fans = f"{int(row['deezer_fans']):,}"
    rank = f"{int(row['deezer_rank']):,}"
    viral = f"{row['probabilidad_viral']:.1f}"
    viral_pct = min(row["probabilidad_viral"] / 100.0, 1.0) * 100
    if photo_data_uri is None:
        # La foto va por URL directa (el navegador la baja en paralelo: cero
        # requests en el backend) con placeholder si la CDN falla.
        img_html = (
            f'<img class="artist-photo" src="{row["picture_url"]}" '
            f'onerror="this.src=\'data:image/svg+xml;base64,'
            f'{_SVG_PLACEHOLDER_B64}\'" alt="{row["artist_name"]}">'
        )
    else:
        img_html = f'<img class="artist-photo" src="{photo_data_uri}" alt="{row["artist_name"]}">'
    # Shine sobre un CONTENEDOR: los <img> (elementos reemplazados) no
    # soportan pseudo-elementos ::after
    photo = f'<div class="image-shine">{img_html}</div>'
    badge = display_badge_with_pulse(
        row["ar_recommendation"],
        badge_color_for(row["ar_recommendation"]),
        inline=True,
    )
    cox_html = ventana_firma_cox_html(row)
    estrella = (
        " ⭐" if row["artist_name"] in st.session_state.get("favoritos", []) else ""
    )
    # Stagger real por card: el delay va inline (nth-child no funciona entre
    # st.markdown separados: cada card es hija única de su wrapper en el DOM)
    return f"""
    <div class="neumorphic-card artist-card" style="animation-delay: {index * 0.1:.1f}s;">
        <div style="display: grid; grid-template-columns: 100px 1fr 220px; gap: 20px; align-items: center;">
            <div>{photo}</div>
            <div>
                <h3 class="artist-name">{row['artist_name']}{estrella}</h3>
                <p class="artist-meta">{badge} | Score: <strong class="score-value">{row['scouting_score']:.0f}/100</strong></p>
                {cox_html}
                <p class="artist-track">🎵 Top Track: {row['top_track_name']}</p>
                <div class="insight-pill"><span>💡 {row['strategic_insight']}</span></div>
            </div>
            <div style="text-align: right;">
                <div class="stat-block">
                    <div class="stat-label">Prob. Viralidad 6M</div>
                    <div class="stat-value-blue">{viral}%</div>
                    <div class="viral-track"><div class="viral-fill" style="width: {viral_pct:.0f}%;"></div></div>
                </div>
                <div class="stat-block">
                    <div class="stat-label">Fans Deezer</div>
                    <div class="stat-value-blue">{fans}</div>
                </div>
                <div class="stat-block">
                    <div class="stat-label">Deezer Rank</div>
                    <div class="stat-value-dark">{rank}</div>
                </div>
                <a class="deezer-link" href="{row['deezer_link']}" target="_blank">🔗 Ver en Deezer</a>
            </div>
        </div>
    </div>
    """


def artist_card_compacto_html(row, index=0):
    """Card compacta para la paginación (grid 2 columnas): foto, nombre,
    score, fans y badge de recomendación. La foto va por URL directa de la
    CDN de Deezer (el navegador la descarga: cero requests en el backend) con
    fallback inline si la CDN falla."""
    fans = f"{int(row['deezer_fans']):,}"
    badge = display_badge_with_pulse(
        row["ar_recommendation"],
        badge_color_for(row["ar_recommendation"]),
        inline=True,
    )
    cox_html = ventana_firma_cox_html(row)
    estrella = (
        " ⭐" if row["artist_name"] in st.session_state.get("favoritos", []) else ""
    )
    return f"""
    <div class="neumorphic-card artist-card" style="animation-delay: {index * 0.05:.2f}s; padding: 15px; margin-bottom: 15px;">
        <div style="display: flex; gap: 14px; align-items: center;">
            <img src="{row['picture_url']}"
                 onerror="this.src='data:image/svg+xml;base64,{_SVG_PLACEHOLDER_B64}'"
                 style="width: 56px; height: 56px; border-radius: 12px; object-fit: cover; flex-shrink: 0;"
                 alt="{row['artist_name']}">
            <div style="flex: 1; min-width: 0;">
                <h4 class="artist-name" style="font-size: 1rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{row['artist_name']}{estrella}</h4>
                <p class="artist-meta" style="margin: 4px 0 0;">
                    Score: <strong class="score-value">{row['scouting_score']:.0f}/100</strong> · 🎧 {fans} fans
                </p>
                <div style="margin-top: 6px;">{badge}</div>
                {cox_html}
            </div>
        </div>
    </div>
    """


def show_loading_spinner(message, slot=None):
    """Spinner premium. Pásale un st.empty() como slot: al escribir encima
    el spinner desaparece (el flujo normal de Streamlit NO borra los
    st.markdown de la corrida anterior)."""
    target = slot if slot is not None else st
    target.markdown(
        f"""
        <div class="loading-spinner">
            <div>
                <div class="spinner"></div>
                <p style="text-align: center; margin-top: 15px; font-weight: 500;">
                    {message}
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_skeleton_loaders(rows=3, slot=None):
    """Skeletons estilo Facebook/LinkedIn: foto-círculo + líneas de texto.
    Compone todas las filas en UN solo bloque (y opcionalmente en un slot
    para poder limpiarlas cuando llegan los datos reales)."""
    row_html = """
        <div style="display: grid; grid-template-columns: 100px 1fr 200px; gap: 20px; margin-bottom: 20px;">
            <div class="skeleton-circle"></div>
            <div>
                <div class="skeleton" style="width: 60%;"></div>
                <div class="skeleton" style="width: 40%;"></div>
                <div class="skeleton" style="width: 80%;"></div>
            </div>
            <div>
                <div class="skeleton" style="width: 80%;"></div>
                <div class="skeleton" style="width: 60%;"></div>
            </div>
        </div>
    """
    target = slot if slot is not None else st
    target.markdown(row_html * rows, unsafe_allow_html=True)


def display_animated_progress(value, max_value=100, label="Progreso"):
    """Barra de progreso animada (progressFill desde 0%)."""
    percentage = (value / max_value) * 100
    st.markdown(
        f"""
        <div style="margin: 15px 0;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                <span style="font-size: 0.85rem; color: #94a3b8; font-weight: 500;">{label}</span>
                <span style="font-size: 0.85rem; color: #4d94ff; font-weight: 600;">{percentage:.1f}%</span>
            </div>
            <div class="progress-bar-container">
                <div class="progress-bar" style="width: {percentage}%;"></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def badge_color_for(recommendation):
    """Color semántico del badge según la recomendación A&R."""
    if recommendation == "🔥 FIRMAR AHORA":
        return "#FF4444"
    if recommendation == "👀 OBSERVAR":
        return "#FFA500"
    return "#6B7280"


def display_badge_with_pulse(text, color="#0066FF", inline=False):
    """Badge con pulso. Con inline=True devuelve el HTML (para componer dentro
    de una card) en vez de escribir un bloque propio."""
    html = (
        f'<span class="badge-pulse" '
        f'style="background-color: {color}; color: white;">{text}</span>'
    )
    if inline:
        return html
    st.markdown(html, unsafe_allow_html=True)

# ==========================================
# PLOTLY: TEMA SaaS PARA TODOS LOS GRÁFICOS
# ==========================================
NEON_AZUL = "#0066FF"
NEON_CIAN = "#00CED1"
PALETA_RECOMENDACION = {
    "🔥 FIRMAR AHORA": "#FF4757",
    "👀 OBSERVAR": "#FFA502",
    "⚠️ DESCARTAR": "#64748B",
}

# Placeholder en línea (via.placeholder.com murió en 2024): fallback inline
# de las fotos (hero, cards del Comparador y card compacta) cuando la CDN de
# Deezer falla. Vive aquí (no en la sección de Scouting) para que cualquier
# vista pueda usarlo: cada corrida termina en st.stop() antes o después.
_SVG_PLACEHOLDER = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
    '<rect width="100" height="100" fill="#1f2a3d"/>'
    '<text x="50" y="55" font-size="30" text-anchor="middle">🎼</text></svg>'
)
_SVG_PLACEHOLDER_B64 = base64.b64encode(_SVG_PLACEHOLDER.encode()).decode()


def estilo_plotly(fig, alto=360, leyenda=False):
    """Fondo transparente + tipografía legible: el gráfico flota sobre el
    glassmorphism sin caja blanca. Los colores siguen el tema activo
    (oscuro por defecto, claro si el usuario lo eligió)."""
    claro = TEMA_APP == "claro"
    color_texto = "#334155" if claro else "#cbd5e1"
    color_titulo = "#0f172a" if claro else "#e2e8f0"
    color_tick = "#64748b" if claro else "#94a3b8"
    grid = "rgba(15,23,42,0.08)" if claro else "rgba(255,255,255,0.06)"
    cero = "rgba(15,23,42,0.18)" if claro else "rgba(255,255,255,0.12)"
    eje = "rgba(15,23,42,0.25)" if claro else "rgba(255,255,255,0.15)"
    fig.update_layout(
        height=alto,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, 'Segoe UI', sans-serif", size=12, color=color_texto),
        title=dict(font=dict(size=15, color=color_titulo), x=0.01, xanchor="left"),
        margin=dict(l=10, r=10, t=46, b=10),
        showlegend=leyenda,
        legend=dict(font=dict(size=11), bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(
        gridcolor=grid,
        zerolinecolor=cero,
        linecolor=eje,
        tickfont=dict(color=color_tick),
    )
    fig.update_yaxes(
        gridcolor=grid,
        zerolinecolor=cero,
        linecolor=eje,
        tickfont=dict(color=color_tick),
    )
    return fig

TEMA_APP = leer_tema()
load_custom_css(TEMA_APP)

# ==========================================
# FAVORITOS — lista personal del usuario (A&R). Se persiste en
# data/favoritos.json porque session_state se pierde al recargar la página;
# en Streamlit Cloud el archivo vive en la instancia (efímero entre deploys).
# ==========================================
_RUTA_FAVORITOS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "favoritos.json"
)


def _leer_favoritos():
    try:
        with open(_RUTA_FAVORITOS, encoding="utf-8") as f:
            datos = json.load(f)
        return sorted({a for a in datos.get("artistas", []) if isinstance(a, str)})
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return []


def guardar_favoritos(lista):
    try:
        os.makedirs(os.path.dirname(_RUTA_FAVORITOS), exist_ok=True)
        with open(_RUTA_FAVORITOS, "w", encoding="utf-8") as f:
            json.dump({"artistas": sorted(set(lista))}, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def alternar_favorito(nombre):
    """Añade/quita del set de favoritos y escribe a disco. Devuelve True si
    el artista queda como favorito tras el cambio."""
    favoritos = list(st.session_state.get("favoritos", []))
    if nombre in favoritos:
        favoritos.remove(nombre)
        es_fav = False
    else:
        favoritos.append(nombre)
        es_fav = True
    st.session_state["favoritos"] = favoritos
    guardar_favoritos(favoritos)
    return es_fav

if "favoritos" not in st.session_state:
    st.session_state["favoritos"] = _leer_favoritos()

# ==========================================
# AUTENTICACIÓN SaaS: cada sello tiene su propio acceso. config.yaml trae las
# credenciales con hash bcrypt (nunca en claro) y la cookie firmada (30 días).
# Sin sesión activa la app NO renderiza NI UN dato: solo la pantalla de acceso.
# ==========================================
@st.cache_data
def cargar_config_auth():
    """Config de autenticación (yaml parseado 1 vez por proceso)."""
    ruta_config = os.path.join(os.path.dirname(__file__), "config.yaml")
    with open(ruta_config, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

config_auth = cargar_config_auth()
# Instancia por corrida (patrón documentado del paquete): el objeto maneja
# cookies y estado de sesión de Streamlit, no se cachea.
authenticator = stauth.Authenticate(
    credentials=config_auth["credentials"],
    cookie_name=config_auth["cookie"]["name"],
    cookie_key=config_auth["cookie"]["key"],
    cookie_expiry_days=float(config_auth["cookie"]["expiry_days"]),
)

if not st.session_state.get("authentication_status"):
    # ---- PANTALLA DE LOGIN: única cosa visible sin sesión ----
    st.markdown(
        """
        <div class="glass-card" style="max-width: 660px; margin: 28px auto 14px; text-align: center;">
            <h1 style="margin-bottom: 6px;">🎵 A&R Scouting Command Center</h1>
            <p style="color: #94a3b8; margin: 0;">
                Plataforma SaaS de scouting musical: datos REALES de Deezer API,
                predicción ML de viralidad a 6 meses y simulación de gira.
                Acceso exclusivo para sellos y managers.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _, col_login, _ = st.columns([1, 1.5, 1])
    with col_login:
        try:
            authenticator.login(
                fields={
                    "Form name": "🔐 Acceso para Sellos & Managers",
                    "Username": "Usuario",
                    "Password": "Contraseña",
                    "Login": "Ingresar",
                }
            )
        except Exception as e:
            st.error(f"⚠️ Error del módulo de autenticación: {e}")
    if st.session_state.get("authentication_status") is False:
        st.error("⛔ Usuario o contraseña incorrectos. Intenta de nuevo.")
    st.caption("Sesión protegida con cookie firmada (30 días) · Contraseñas hasheadas con bcrypt")
    st.stop()

# ---- AUTENTICADO: identidad + logout arriba de la sidebar ----
st.sidebar.markdown(f"👤 **{st.session_state.get('name', 'Usuario')}**")
authenticator.logout(button_name="🚪 Cerrar sesión", location="sidebar", key="btn_logout")
st.sidebar.divider()

# Carga del modelo ML (serializado desde el notebook con joblib) — cacheado
# para que se deserialice una sola vez por sesión, no en cada re-render
@st.cache_resource
def cargar_modelo_ml():
    try:
        modelo = joblib.load("modelo_viralidad_rf.pkl")
        features = joblib.load("feature_names.pkl")
        return modelo, features
    except FileNotFoundError:
        st.warning("⚠️ Modelo no encontrado. Ejecuta el Notebook primero.")
        return None, None

# Caché de predicciones en disco: cargar scikit-learn + el RandomForest cuesta
# ≈1.4 s por proceso, así que la probabilidad viral de cada artista se guarda
# y solo se recalcula si cambian sus datos (fingerprint fans|rank|track|ratio).
_RUTA_PROBS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "probabilidades.json"
)
# Igual para el Cox: la primera predicción importa lifelines (≈1.3 s).
_RUTA_COX = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "predicciones_cox.json"
)


def _leer_cache_json(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
        return datos if isinstance(datos, dict) else {}
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}


def _guardar_cache_json(ruta, cache):
    try:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        tmp = ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f)
        os.replace(tmp, ruta)
    except OSError:
        pass


def _fmt_key(valor):
    """Clave estable de una feature para los cachés de disco."""
    if isinstance(valor, str):
        return valor.strip()
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    if math.isnan(v):
        return "nan"
    return f"{v:.6g}"


def _cache_val(valor):
    """Serializa un valor de predicción para JSON (pd.NA/nan → "")."""
    if valor is None or valor is pd.NA:
        return ""
    if isinstance(valor, float) and math.isnan(valor):
        return ""
    if hasattr(valor, "item"):
        try:
            valor = valor.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(valor, (str, int, float, bool)):
        return valor
    return str(valor)


def _clave_probs(fans, rank, track, ratio):
    return (
        f"{float(fans):.0f}|{float(rank):.0f}|{float(track):.0f}|"
        f"{float(ratio):.4f}"
    )


def _probabilidades_virales(data):
    """Prob. viral 6M por artista, con caché en disco por fila.

    Solo carga scikit-learn (≈1.4 s) si el caché no cubre todas las filas:
    en un arranque normal el JSON está completo y el proceso ni toca sklearn.
    """
    claves = [
        _clave_probs(f, r, t, ra)
        for f, r, t, ra in zip(
            data["deezer_fans"],
            data["deezer_rank"],
            data["top_track_rank"],
            data["fan_rank_ratio"],
        )
    ]
    cache = _leer_cache_json(_RUTA_PROBS)
    nuevo = {k: cache[k] for k in claves if k in cache}
    if all(k in cache for k in claves):
        return pd.Series(
            [nuevo[k] for k in claves], index=data.index, name="probabilidad_viral"
        )

    modelo_ml, feature_names = cargar_modelo_ml()
    if modelo_ml is None:
        return pd.Series(0.0, index=data.index, name="probabilidad_viral")

    growth_proxy = (data["fan_rank_ratio"] / 15.0).clip(-0.05, 0.30)
    X = pd.DataFrame(
        {
            "current_fans": data["deezer_fans"],
            "current_rank": data["deezer_rank"],
            "track_rank": data["top_track_rank"],
            "monthly_growth_rate": growth_proxy,
            "genero_encoded": 0,
        }
    )[feature_names]
    probs = (modelo_ml.predict_proba(X)[:, 1] * 100).round(1)
    for k, p in zip(claves, probs):
        nuevo[k] = float(p)
    _guardar_cache_json(_RUTA_PROBS, nuevo)
    return pd.Series(probs, index=data.index, name="probabilidad_viral")

st.title("🎵 A&R Scouting Command Center")
st.markdown(
    "**Data Product con datos REALES de Deezer API para identificación de talento musical**"
)

# Estado de carga premium SOLO en la primera carga de la sesión: en los
# re-renders (cambios de filtro, toggle) el spinner parpadearía sin
# necesidad — Streamlit re-ejecuta todo el script en cada interacción.
primera_carga = "carga_completada" not in st.session_state
load_slot = st.empty() if primera_carga else None
if primera_carga:
    show_loading_spinner(
        "Conectando con Deezer API y calculando predicciones de ML...",
        slot=load_slot,
    )
# La predicción de viralidad ya viene cacheada en disco (ver
# _probabilidades_virales): si el caché está completo el proceso ni importa
# scikit-learn, que es lo que más cuesta del arranque (≈1.4 s).
if primera_carga:
    show_skeleton_loaders(rows=3, slot=load_slot)

# Conectar a DuckDB con AUTO-REPARACIÓN: si el warehouse no existe (servidor
# limpio, p. ej. Render), se reconstruye en segundos desde el seed versionado
# en el repo con la misma lógica de scoring del mart dbt (bootstrap_db.py).
import bootstrap_db

AR_DB = bootstrap_db.resolve_db_path()
if bootstrap_db.ensure_database(AR_DB):
    st.info("⚙️ Inicializando base de datos en la nube... (solo la primera vez)")
    st.success("✅ ¡Base de datos inicializada con éxito!")
bootstrap_db.ensure_table(AR_DB)

conn = bootstrap_db.get_connection(AR_DB)  # única conexión read-write del proceso

# Firma del warehouse (mtime): clave de caché del dataset. Si el robot
# semanal reescribe el .duckdb, la caché de 5 min se invalida sola.
try:
    _firma_db = os.path.getmtime(AR_DB)
except OSError:
    _firma_db = 0.0

# Lectura + ML + Cox viven en cargar_dataset() (más abajo), cacheada: los
# re-renders (filtros, toggles, drill) y las sesiones nuevas reutilizan el
# DataFrame en vez de repetir predict_proba + predecir_lote + merges.

# ==========================================
# FASE 3 — SUPERVIVENCIA DE COX: VENTANA DE FIRMA ÓPTIMA
# Añade prob_breakout_6m, mes_optimo_firma y riesgo a todo el universo.
# Las features ADN viven en el seed (la tabla de scoring no las incluye),
# así que se fusionan por nombre. Si el modelo o lifelines no están, la app
# sigue funcionando con las columnas vacías en vez de romper.
# ==========================================
import sys

_scripts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from prediccion_ventana_firma import (
    FEATURES as COX_FEATURES,
    predecir_lote,
    curva_supervivencia,
    TIMES as COX_TIMES,
)

_REPO_DIR = os.path.dirname(os.path.abspath(__file__))


@st.cache_resource
def cargar_modelo_cox():
    """Modelo Cox de Fase 3 (None si falta el archivo o lifelines)."""
    try:
        return joblib.load(os.path.join(_REPO_DIR, "models", "cox_model.pkl"))
    except Exception:
        return None


def cargar_y_predecir_cox(data):
    """Devuelve `data` con prob_breakout_6m (%), mes_optimo_firma y riesgo.

    Las predicciones por fila se cachean en disco (data/predicciones_cox.json):
    la primera vez se paga el modelo Cox + lifelines (≈1.3 s) y después cada
    arranque solo lee el JSON, igual que hace _probabilidades_virales.
    """
    faltantes = [c for c in COX_FEATURES if c not in data.columns]
    if faltantes:
        seed_path = os.path.join(
            _REPO_DIR, "ar_dbt_project", "seeds", "deezer_artists_data.csv"
        )
        try:
            seed = pd.read_csv(seed_path)
            columnas = ["artist_name"] + [
                c for c in COX_FEATURES if c not in data.columns and c in seed.columns
            ]
            data = data.merge(seed[columnas], on="artist_name", how="left")
        except FileNotFoundError:
            pass

    if any(c not in data.columns for c in COX_FEATURES):
        data["prob_breakout_6m"] = float("nan")
        data["mes_optimo_firma"] = pd.NA
        data["riesgo"] = "—"
        return data

    claves = [
        "|".join(_fmt_key(v) for v in valores)
        for valores in zip(*[data[c] for c in COX_FEATURES])
    ]
    cache = _leer_cache_json(_RUTA_COX)
    if all(k in cache for k in claves):
        filas = [cache[k] for k in claves]
        data["prob_breakout_6m"] = [float(f[0]) for f in filas]
        data["mes_optimo_firma"] = [f[1] if f[1] != "" else pd.NA for f in filas]
        data["riesgo"] = [f[2] for f in filas]
        return data

    cph = cargar_modelo_cox()
    if cph is None:
        data["prob_breakout_6m"] = float("nan")
        data["mes_optimo_firma"] = pd.NA
        data["riesgo"] = "—"
        return data

    pred = predecir_lote(cph, data[COX_FEATURES])
    data["prob_breakout_6m"] = (pred["prob_breakout_6m"] * 100).round(1)
    data["mes_optimo_firma"] = pred["mes_optimo_firma"]
    data["riesgo"] = pred["riesgo"]

    nuevo = {}
    for k, p, m, r in zip(
        claves,
        data["prob_breakout_6m"],
        data["mes_optimo_firma"],
        data["riesgo"],
    ):
        nuevo[k] = [_cache_val(p), _cache_val(m), _cache_val(r)]
    _guardar_cache_json(_RUTA_COX, nuevo)
    return data

# El dataset completo lo construye cargar_dataset() (cacheada), definida
# después de _conectar_pais_origen para tener todos los motores a mano.


def _conectar_pais_origen(data):
    """Trae `pais_origen` desde la cohorte del Cox (por nombre de artista).

    El seed de Deezer no expone el país (la API pública tampoco): la única
    fuente versionada es la cohorte `data/cohort_table.csv`, que es la misma
    con la que se entrenó el modelo. Si falta el archivo la app sigue
    funcionando con 'Desconocido'.
    """
    try:
        cohorte = pd.read_csv(
            os.path.join(_REPO_DIR, "data", "cohort_table.csv"),
            usecols=["artist_name", "pais_origen"],
        ).drop_duplicates("artist_name")
        data = data.merge(cohorte, on="artist_name", how="left")
        data["pais_origen"] = data["pais_origen"].fillna("Desconocido")
    except (FileNotFoundError, ValueError, pd.errors.EmptyDataError):
        data["pais_origen"] = "Desconocido"
    return data


@st.cache_data(ttl=300, show_spinner=False)
def cargar_dataset(ruta_db, firma_db):
    """Warehouse + ML + Cox + cohorte, cacheado 5 min (firma_db = mtime).

    Es el único camino pesado del arranque: la primera sesión paga la
    conexión DuckDB, el modelo Cox y las predicciones ML que falten en el
    caché de disco; después cada re-render y cada sesión nueva reutiliza
    el DataFrame ya calculado. Si el robot semanal reescribe el archivo,
    firma_db cambia y se recalcula.
    """
    conn = bootstrap_db.get_connection(ruta_db)
    try:
        data = pd.read_sql_query("SELECT * FROM artist_scouting_deezer", conn)
    except Exception as exc:
        raise RuntimeError(
            "❌ No se encontraron datos. Ejecuta primero: `dbt seed && dbt run`"
        ) from exc

    # ---- PREDICCIÓN DE MACHINE LEARNING (caché en disco por artista) ----
    # Solo carga scikit-learn si data/probabilidades.json no cubre las filas.
    data["probabilidad_viral"] = _probabilidades_virales(data)

    data = cargar_y_predecir_cox(data)
    return _conectar_pais_origen(data)

try:
    df = cargar_dataset(AR_DB, _firma_db)
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()

# Alcance multi-plataforma estimado (factores documentados en el perfil).
# Debe existir ANTES de derivar df_filtered: las copias de pandas no
# heredan columnas añadidas después (causó KeyError en las cards hero).
df["est_alcance_max"] = (
    df["deezer_rank"].astype(float) * 2.5 + df["deezer_fans"] * 1.5
).astype(int)

# Datos y predicciones listos: fuera spinner y skeletons (solo si hubo)
if primera_carga:
    load_slot.empty()
    st.session_state.carga_completada = True

# Barra de estado SaaS: indicador de salud + tamaño del universo vigilado
st.markdown(
    f"🟢 **En línea** · **{len(df)}** artistas monitorizados · Fuente: "
    "**Deezer API** · Robot semanal (GitHub Actions)"
)

# ==========================================
# FORECASTING DE CRECIMIENTO (Módulo 5)
# ==========================================
# El gráfico se genera una vez por artista y se cachea 24 h (el motor —
# sklearn por defecto, Prophet con FORECAST_ENGINE=prophet — solo corre la
# primera vez que se pide cada artista): cambiar de pestaña ni de artista
# repiten el entrenamiento.
@st.cache_resource(ttl=86400)
def cargar_forecast(
    artista: str,
    fans_actuales: int | None = None,
    momentum: float | None = None,
    motor: str = "sklearn",
):
    import sys

    # El motor vive en scripts/; añadimos la carpeta al path para que el
    # import funcione igual en local y en el contenedor de Render.
    ruta_scripts = os.path.join(os.path.dirname(__file__), "scripts")
    if ruta_scripts not in sys.path:
        sys.path.insert(0, ruta_scripts)
    import forecast_fans

    return forecast_fans.fit_and_forecast(
        artista=artista,
        fans_actuales=fans_actuales,
        momentum=momentum,
        save_png=False,
    )

# ==========================================
# SIDEBAR — ORDEN OPTIMIZADO (flujo UX: buscar → navegar → refinar)
# 1. BUSCADOR arriba: la acción #1 del usuario
# ==========================================
st.sidebar.header("🔍 Buscar Artista")
busqueda = st.sidebar.text_input(
    "Nombre del artista",
    placeholder="Ej: KAROL G, Feid, Marc Anthony…",
    label_visibility="collapsed",
)
patron = busqueda.strip()

st.sidebar.divider()

# ── 2. VISTAS (navegación principal) ───────────────────────────────────
st.sidebar.header("🗂️ Vistas")
vista_tab = st.sidebar.radio(
    "Selecciona la vista:",
    options=["🎯 Scouting", "🔮 Forecasting 6M", "🌍 Touring", "🆚 Comparador"],
    label_visibility="collapsed",
    key="vista_tab",
)
st.sidebar.divider()

# ── 2b. TEMA (Prioridad 3): claro/oscuro. La preferencia vive en
# data/preferencias.json porque session_state se pierde al recargar la
# página; el callback escribe antes de que la app vuelva a leer el tema.
def _cb_tema():
    guardar_tema("claro" if st.session_state.get("toggle_tema") else "oscuro")

st.sidebar.toggle(
    "☀️ Modo claro",
    value=(TEMA_APP == "claro"),
    key="toggle_tema",
    on_change=_cb_tema,
    help="Alterna el tema visual de la app (Cyberpunk oscuro ↔ claro). "
    "La elección queda guardada en data/preferencias.json.",
)

# Métrica de rendimiento visible: tiempo desde el arranque del script hasta
# esta línea (imports + auth + dataset). Es lo que el usuario percibe como
# "la app tardó X segundos en cargar"; en re-renders suele ser <0.1 s.
st.sidebar.caption(f"⚡ Carga: {(time.perf_counter() - _T0):.2f}s")

# ── Router de vistas (st.session_state: Streamlit no tiene routing nativo).
# El radio MANDA: si el usuario cambia de vista mientras está en un perfil,
# el perfil se cierra limpio. Interactuar DENTRO del perfil no lo cierra
# (el radio no cambió entre re-renders).
if "vista_actual" not in st.session_state:
    st.session_state.vista_actual = "scouting"
if "artista_seleccionado" not in st.session_state:
    st.session_state.artista_seleccionado = None
if "radio_previo" in st.session_state and st.session_state.radio_previo != vista_tab:
    st.session_state.vista_actual = "scouting"
    st.session_state.artista_seleccionado = None
st.session_state.radio_previo = vista_tab

# Motores de módulos: scripts/ al path ANTES de importar (el import directo
# 'from scripts.touring_engine import ...' rompe cuando el CWD de la app no
# es la raíz del repo — p.ej. el contenedor de Render)
import sys

_scripts_dir = os.path.join(os.path.dirname(__file__), "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)
from touring_engine import calcular_ruta_touring, resumen_gira

# ==========================================
# PERFIL DE ARTISTA — Multi-Platform Analytics Hub
# Routing con st.session_state: las cards del Scouting navegan aquí.
# ==========================================
COLORES_PLATAFORMA = {
    "Spotify": "#1DB954",
    "YouTube": "#FF0000",
    "Apple Music": "#FA243C",
    "TikTok": "#FFFFFF",  # #000000 (marca) desaparecería sobre el tema oscuro
    "Deezer": "#00CED1",
}


def kpi_plataforma_html(icono, nombre, valor, color, sublabel):
    """Card glass del hub multi-plataforma. Las 5 cards se componen en UN
    bloque dentro de .kpi-container (un st.markdown por card rompería la
    grilla en el DOM de Streamlit)."""
    return (
        f'<div class="kpi-card" style="text-align: center;">'
        f'<div style="font-size: 1.9rem;">{icono}</div>'
        f'<div class="kpi-label">{nombre}</div>'
        f'<div style="font-size: 1.45rem; font-weight: 700; color: {color}; '
        f"font-family: 'JetBrains Mono', monospace; margin: 6px 0;\">{valor}</div>"
        f'<div style="font-size: 0.72rem; color: #64748b;">{sublabel}</div></div>'
    )


def mostrar_perfil_artista(artist_name):
    """Perfil exclusivo del artista con hub multi-plataforma.

    La API pública de Deezer solo expone su propio ecosistema (fans, rank,
    top track). Los números de Spotify/YouTube/Apple/TikTok son ESTIMACIONES
    con factores de industria 2026 aplicados a las métricas REALES de Deezer;
    así se declara en la UI para no vender datos sintéticos como reales.
    """
    artista_rows = df[df["artist_name"] == artist_name]
    if artista_rows.empty:
        # El artista salió del universo (robot semanal, seed nuevo): salir limpio
        st.session_state.vista_actual = "scouting"
        st.session_state.artista_seleccionado = None
        st.warning(f"⚠️ {artist_name} ya no está en el universo monitorizado.")
        return
    artista = artista_rows.iloc[0]

    if st.button("← Volver al Scouting", key="btn_volver_perfil"):
        st.session_state.vista_actual = "scouting"
        st.session_state.artista_seleccionado = None
        st.rerun()

    # Header del perfil
    col_foto, col_datos = st.columns([1, 3])
    with col_foto:
        st.image(artista["picture_url"], use_container_width=True)
    with col_datos:
        st.title(artista["artist_name"])
        badge = display_badge_with_pulse(
            artista["ar_recommendation"],
            badge_color_for(artista["ar_recommendation"]),
            inline=True,
        )
        st.markdown(
            f"{badge} · Score: **{artista['scouting_score']:.0f}/100** · "
            f"Género: **{artista.get('genero', 'N/A')}** · "
            f"País: **{artista.get('pais_origen', '—')}** · "
            f"Prob. Viralidad 6M: **{artista['probabilidad_viral']:.1f}%**",
            unsafe_allow_html=True,  # el badge inline llega como HTML
        )
        if pd.notna(artista.get("prob_breakout_6m")):
            if pd.isna(artista.get("mes_optimo_firma")):
                ventana_cox = "riesgo <10% los 12 meses"
            else:
                ventana_cox = f"firmar antes del mes {int(artista['mes_optimo_firma'])}"
            st.markdown(
                f"🪧 **Cox:** Prob. breakout 6M **"
                f"{artista['prob_breakout_6m']:.1f}%** · Ventana: "
                f"**{ventana_cox}** · Riesgo: **{artista.get('riesgo', '—')}**"
            )
        st.markdown(
            f"🎧 **{int(artista['deezer_fans']):,}** fans · Rank: "
            f"**{int(artista['deezer_rank']):,}** · "
            f"🎵 Top Track: **{artista['top_track_name']}**"
        )
        st.markdown(f"[🔗 Ver en Deezer]({artista['deezer_link']})")
        st.markdown(f"💡 {artista['strategic_insight']}")

        # Favoritos (Prioridad 2): lista personal del A&R persistida en
        # data/favoritos.json; la estrella también se pinta en las cards
        # y sirve de filtro en el sidebar.
        _es_fav = artista["artist_name"] in st.session_state.get("favoritos", [])
        if st.button(
            ("★ Quitar de favoritos" if _es_fav else "⭐ Añadir a favoritos"),
            key="btn_favorito_"
            + str(artista["artist_name"]).lower().replace(" ", "_"),
            use_container_width=True,
        ):
            alternar_favorito(artista["artist_name"])
            st.rerun()

    st.divider()

    # ==========================================
    # SIMULADOR DE ESCENARIOS "¿Qué pasa si...?"
    # Palancas: crecimiento de fans + presupuesto + valor por fan. El
    # crecimiento se traduce en la ÚNICA feature del Cox que depende de fans
    # (ratio_fans_rank = log1p(fans/rank), con rank fijo) → prob. de
    # breakout y ventana se recalculan con el MISMO modelo entrenado, nunca
    # con una regla inventada. El ROI declara su supuesto en la propia UI.
    # ==========================================
    st.subheader("🎮 Simulador de Escenarios")
    st.markdown(
        "**¿Qué pasa si...?** Mueve las palancas y mira cómo cambian la "
        "probabilidad de breakout (Cox), la ventana de firma y el ROI de la "
        "campaña."
    )

    _clave_sim = str(artista["artist_name"]).lower().replace(" ", "_")
    col_crec, col_inv, col_val = st.columns(3)
    with col_crec:
        crecimiento = st.slider(
            "Crecimiento de fans simulado (%)",
            min_value=0,
            max_value=500,
            value=50,
            step=10,
            key=f"sim_crec_{_clave_sim}",
            help=(
                "El rank se mantiene fijo: solo cambia la ratio fans/rank "
                "que el modelo Cox recibe como feature."
            ),
        )
    with col_inv:
        inversion = st.slider(
            "Inversión en marketing (USD)",
            min_value=0,
            max_value=100000,
            value=10000,
            step=5000,
            key=f"sim_inv_{_clave_sim}",
        )
    with col_val:
        valor_fan = st.selectbox(
            "Valor por fan nuevo (supuesto)",
            options=[0.02, 0.05, 0.10],
            index=1,
            format_func=lambda v: f"${v:.2f} por fan",
            key=f"sim_valor_{_clave_sim}",
            help="Supuesto de negocio editable: no es una tasación del artista.",
        )

    fans_actuales = int(artista["deezer_fans"])
    fans_simulados = int(fans_actuales * (1 + crecimiento / 100))
    fans_nuevos = fans_simulados - fans_actuales
    valor_generado = fans_nuevos * valor_fan
    roi_neto = valor_generado - inversion
    costo_por_fan = (inversion / fans_nuevos) if fans_nuevos > 0 else None
    multiplo = (valor_generado / inversion) if inversion > 0 else None

    # ── Recálculo del Cox con la ratio simulada ──
    prob_actual = artista.get("prob_breakout_6m", float("nan"))
    prob_sim = pd.NA
    ventana_sim = pd.NA
    riesgo_sim = "—"
    cph_sim = cargar_modelo_cox()
    rank_artista = (
        int(artista["deezer_rank"]) if pd.notna(artista.get("deezer_rank")) else 0
    )
    X_base = X_sim = None
    if cph_sim is not None and all(c in artista.index for c in COX_FEATURES):
        X_base = pd.DataFrame([{c: artista[c] for c in COX_FEATURES}]).astype(float)
        X_sim = X_base.copy()
        if rank_artista > 0:
            X_sim.loc[0, "ratio_fans_rank"] = math.log1p(fans_simulados / rank_artista)
            _pred_sim = predecir_lote(cph_sim, X_sim)
            prob_sim = float(_pred_sim["prob_breakout_6m"].iloc[0]) * 100
            ventana_sim = _pred_sim["mes_optimo_firma"].iloc[0]
            riesgo_sim = str(_pred_sim["riesgo"].iloc[0])

    _sim_ok = cph_sim is not None and X_sim is not None and pd.notna(prob_sim)

    display_kpi_grid(
        [
            ("Fans Actuales", f"{fans_actuales:,}", "🎧"),
            ("Fans Simulados", f"{fans_simulados:,}", "📈"),
            (
                "Prob. Breakout (actual)",
                f"{prob_actual:.1f}%" if pd.notna(prob_actual) else "—",
                "🪧",
            ),
            (
                "Prob. Breakout (simulada)",
                f"{prob_sim:.1f}%" if _sim_ok else "—",
                "🎯",
            ),
        ]
    )

    if _sim_ok:
        ventana_sim_txt = (
            "riesgo <10% los 12 meses"
            if pd.isna(ventana_sim)
            else f"firmar antes del mes {int(ventana_sim)}"
        )
        delta_txt = (
            f" ({prob_sim - float(prob_actual):+.1f} pp vs. actual)"
            if pd.notna(prob_actual)
            else ""
        )
        st.markdown(
            f"🪧 **Cox simulado:** Prob. breakout 6M **{prob_sim:.1f}%**"
            f"{delta_txt} · Ventana: **{ventana_sim_txt}** · "
            f"Riesgo: **{riesgo_sim}** · Palanca: **+{crecimiento}% fans**"
        )

        # Curva acumulada de breakout (1 - S(t)): actual vs simulada
        S_actual = curva_supervivencia(cph_sim, X_base)
        S_simulada = curva_supervivencia(cph_sim, X_sim)
        meses = [t / 30 for t in COX_TIMES]
        fig_sim = go.Figure()
        fig_sim.add_trace(
            go.Scatter(
                x=meses,
                y=(1 - S_actual[0]) * 100,
                name="Actual",
                mode="lines+markers",
                line=dict(color=NEON_AZUL, width=3),
                marker=dict(size=6),
                hovertemplate="Mes %{x:.0f}<br>%{y:.1f}%<extra>Actual</extra>",
            )
        )
        fig_sim.add_trace(
            go.Scatter(
                x=meses,
                y=(1 - S_simulada[0]) * 100,
                name=f"Simulado (+{crecimiento}%)",
                mode="lines+markers",
                line=dict(color=NEON_CIAN, width=3),
                marker=dict(size=6),
                hovertemplate="Mes %{x:.0f}<br>%{y:.1f}%<extra>Simulado</extra>",
            )
        )
        fig_sim.add_vline(x=6, line_dash="dash", line_color="#94a3b8")
        fig_sim.update_layout(title="Probabilidad acumulada de breakout (Cox)")
        fig_sim.update_xaxes(title_text="Meses")
        fig_sim.update_yaxes(title_text="Prob. acumulada (%)", range=[0, 100])
        st.plotly_chart(
            estilo_plotly(fig_sim, alto=400, leyenda=True),
            use_container_width=True,
            key="chart_simulador_escenarios",
        )
    else:
        st.info(
            "🎮 La predicción simulada necesita el modelo Cox desplegado y un "
            "rank reportado (>0). Fans y ROI siguen siendo calculables con "
            "los supuestos elegidos."
        )

    _roi_color = "#10B981" if roi_neto > 0 else "#EF4444"
    st.markdown(
        f"""
        <div class="glass-card">
            <h4>💶 Resultados de la Simulación</h4>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px;">
                <div>
                    <p style="color: #94a3b8; font-size: 0.85rem; margin: 0;">Fans nuevos</p>
                    <p style="font-size: 1.6rem; font-weight: 700; color: #E2E8F0; margin: 0;">+{fans_nuevos:,}</p>
                </div>
                <div>
                    <p style="color: #94a3b8; font-size: 0.85rem; margin: 0;">Costo por fan (CAC)</p>
                    <p style="font-size: 1.6rem; font-weight: 700; color: #E2E8F0; margin: 0;">{f"${costo_por_fan:.3f}" if costo_por_fan is not None else "—"}</p>
                </div>
                <div>
                    <p style="color: #94a3b8; font-size: 0.85rem; margin: 0;">Valor generado</p>
                    <p style="font-size: 1.6rem; font-weight: 700; color: #00CED1; margin: 0;">${valor_generado:,.0f}</p>
                </div>
                <div>
                    <p style="color: #94a3b8; font-size: 0.85rem; margin: 0;">Inversión</p>
                    <p style="font-size: 1.6rem; font-weight: 700; color: #E2E8F0; margin: 0;">${inversion:,}</p>
                </div>
                <div>
                    <p style="color: #94a3b8; font-size: 0.85rem; margin: 0;">ROI Neto</p>
                    <p style="font-size: 1.6rem; font-weight: 700; color: {_roi_color}; margin: 0;">{"" if roi_neto >= 0 else "-"}${abs(roi_neto):,.0f}</p>
                </div>
                <div>
                    <p style="color: #94a3b8; font-size: 0.85rem; margin: 0;">Múltiplo (valor / inversión)</p>
                    <p style="font-size: 1.6rem; font-weight: 700; color: {_roi_color}; margin: 0;">{f"{multiplo:.1f}x" if multiplo is not None else "—"}</p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        f"Supuestos declarados: rank fijo (solo se recalcula "
        f"ratio_fans_rank = log1p(fans/rank)) · valor por fan = "
        f"${valor_fan:.2f} (supuesto editable, no es una tasación) · la "
        f"inversión no modifica el modelo Cox · la línea punteada marca el "
        f"horizonte de 6 meses."
    )

    st.divider()

    # ==========================================
    # MULTI-PLATFORM ANALYTICS HUB (estimaciones declaradas)
    # ==========================================
    st.subheader("📊 Analytics Multi-Plataforma")
    st.caption(
        "Estimaciones con factores de industria 2026 sobre las métricas REALES "
        "de Deezer (su API pública no expone a la competencia). En producción: "
        "conectores de YouTube Data API, TikTok Research API y Apple Music."
    )

    # Factores declarados (nada de fórmulas ocultas):
    factor_youtube = float(artista["deezer_rank"]) * 2.5  # alcance audio+video
    factor_spotify = float(artista["deezer_fans"]) * 1.5  # líder de mercado
    factor_apple = float(artista["deezer_fans"]) * 0.8    # base menor, engagement alto
    factor_tiktok = float(artista["deezer_rank"]) * 5     # viralidad exponencial

    kpis_html = "".join(
        [
            kpi_plataforma_html("🎵", "SPOTIFY", f"{int(factor_spotify):,}", COLORES_PLATAFORMA["Spotify"], "Monthly Listeners (est.)"),
            kpi_plataforma_html("📺", "YOUTUBE", f"{int(factor_youtube):,}", COLORES_PLATAFORMA["YouTube"], "Subscribers (est.)"),
            kpi_plataforma_html("🍎", "APPLE MUSIC", f"{int(factor_apple):,}", COLORES_PLATAFORMA["Apple Music"], "Followers (est.)"),
            kpi_plataforma_html("🎭", "TIKTOK", f"{int(factor_tiktok):,}", COLORES_PLATAFORMA["TikTok"], "Followers (est.)"),
            kpi_plataforma_html("🎧", "DEEZER", f"{int(artista['deezer_fans']):,}", COLORES_PLATAFORMA["Deezer"], "Fans (Dato real)"),
        ]
    )
    st.markdown(f'<div class="kpi-container">{kpis_html}</div>', unsafe_allow_html=True)

    st.divider()

    # Gráfico comparativo (log-y: el dato real de Deezer y las estimaciones
    # viven en órdenes de magnitud distintos)
    plataformas = list(COLORES_PLATAFORMA.keys())
    valores = [factor_spotify, factor_youtube, factor_apple, factor_tiktok, float(artista["deezer_fans"])]
    fig = go.Figure(
        data=[
            go.Bar(
                x=plataformas,
                y=valores,
                marker_color=[COLORES_PLATAFORMA[p] for p in plataformas],
                text=[f"{int(v):,}" for v in valores],
                textposition="auto",
            )
        ]
    )
    fig.update_layout(title="Distribución de Audiencia por Plataforma (escala log)")
    fig.update_yaxes(type="log")
    st.plotly_chart(
        estilo_plotly(fig, alto=420),
        use_container_width=True,
        config={"displayModeBar": False},
        key="chart_perfil_plataformas",
    )

    # Insights estratégicos
    st.subheader("💡 Insights Estratégicos")
    plataforma_dominante = plataformas[valores.index(max(valores))]
    ratio_youtube_deezer = factor_youtube / max(float(artista["deezer_fans"]), 1)
    st.markdown(
        f"""
        <div class="glass-card">
            <h4>🎯 Análisis de Presencia Digital</h4>
            <ul>
                <li><strong>Plataforma dominante:</strong> {plataforma_dominante} concentra el mayor alcance estimado del artista.</li>
                <li><strong>Ratio YouTube/Deezer:</strong> {ratio_youtube_deezer:.1f}x — por encima de 3x indica fuerte presencia visual/video.</li>
                <li><strong>Recomendación:</strong> {'Enfocar estrategia en video content (YouTube/TikTok)' if ratio_youtube_deezer > 3 else 'Fortalecer presencia en streaming de audio (Spotify/Apple Music)'}.</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ==========================================
    # INFORME EJECUTIVO PDF — el entregable para la junta del sello. Se genera
    # 100% en memoria (io.BytesIO): Render es efímero, el PDF nunca toca disco.
    # Dos fases (Generar -> Descargar): el PDF se compone 1 vez y queda en
    # session_state, no en cada re-render del perfil.
    # ==========================================
    st.divider()
    st.subheader("📄 Informe Ejecutivo (PDF)")
    st.caption(
        "Entregable para comités e inversores: foto, veredicto A&R, analytics "
        "multi-plataforma, insights estratégicos y plan de gira con ROI."
    )
    nombre_pdf = artista["artist_name"]
    if st.session_state.get("pdf_generado_para") != nombre_pdf:
        st.session_state.pop("pdf_bytes_actual", None)
    if st.button(
        "⚙️ Generar Informe Ejecutivo",
        key="btn_pdf_generar_perfil",
        use_container_width=True,
        type="primary",
    ):
        with st.spinner("Componiendo informe (analytics + gira)..."):
            try:
                st.session_state["pdf_bytes_actual"] = cargar_generador_pdf()(artista)
                st.session_state["pdf_generado_para"] = nombre_pdf
            except Exception as e:
                st.session_state.pop("pdf_bytes_actual", None)
                st.error(f"⚠️ No se pudo generar el PDF: {e}")
    if (
        st.session_state.get("pdf_bytes_actual") is not None
        and st.session_state.get("pdf_generado_para") == nombre_pdf
    ):
        st.download_button(
            label="⬇️ Descargar Informe Ejecutivo (PDF)",
            data=st.session_state["pdf_bytes_actual"],
            file_name=(
                f"informe_ejecutivo_{nombre_pdf.replace(' ', '_').lower()}.pdf"
            ),
            mime="application/pdf",
            key="btn_pdf_descargar_perfil",
            use_container_width=True,
        )

    # ==========================================
    # SALTO AL FORECASTING — el router de Vistas resetea `artista_seleccionado`
    # al cambiar de pestaña, así que el artista viaja en `artista_forecast`
    # (la key del selectbox de la vista Forecasting). El salto va en un
    # callback: los callbacks corren ANTES de instanciar los widgets, y
    # Streamlit prohíbe escribir la key de un radio ya instanciado en el run.
    # ==========================================
    def _ir_a_forecasting():
        st.session_state["artista_forecast"] = nombre_pdf
        st.session_state["vista_tab"] = "🔮 Forecasting 6M"
        st.session_state["vista_actual"] = "scouting"
        st.session_state["artista_seleccionado"] = None

    st.button(
        "🔮 Ver proyección a 6 meses de fans",
        key="btn_forecast_perfil",
        use_container_width=True,
        on_click=_ir_a_forecasting,
    )

# ── DRILL-DOWN (Prioridad 2): la selección de un punto en los gráficos de
# Scouting abre el perfil de ese artista. El salto se DIFIERE un run: los
# keys de los gráficos no se pueden limpiar mientras el widget está
# instanciado en el mismo run (Streamlit lo prohibiría), así que aquí, al
# arrancar el run siguiente, se borran ANTES de que los gráficos se rendericen.
_drill = st.session_state.pop("drill_pendiente", None)
if _drill:
    for _key_grafico in ("chart_scatter_fans", "chart_top10"):
        st.session_state.pop(_key_grafico, None)
    st.session_state.artista_seleccionado = _drill
    st.session_state.vista_actual = "perfil"

# ROUTER: el perfil se despacha ANTES que las vistas (es un estado
# transitorio encima de la navegación; cambiar el radio lo cierra)
if st.session_state.vista_actual == "perfil" and st.session_state.artista_seleccionado:
    mostrar_perfil_artista(st.session_state.artista_seleccionado)
    st.stop()

# ==========================================
# VISTA 4: COMPARADOR DE ARTISTAS — laboratorio interactivo
# Comparativa lado a lado (2-3 artistas): audiencia, scoring ML, prob. de
# breakout y ventana de firma del Cox. Trabaja sobre el universo COMPLETO
# (`df`): los filtros de Scouting no aplican a esta vista.
# ==========================================
if vista_tab == "🆚 Comparador":
    from plotly.subplots import make_subplots

    st.subheader("🆚 Comparador de Artistas")
    st.markdown(
        "Selecciona **2 o 3 artistas** y compara sus métricas lado a lado: "
        "audiencia, Scouting Score, probabilidad de viralidad, probabilidad "
        "de breakout (Cox) y ventana de firma óptima."
    )

    _orden = df.sort_values("scouting_score", ascending=False)["artist_name"].tolist()
    seleccion = st.multiselect(
        "Elige artistas para comparar:",
        options=_orden,
        default=_orden[:2],
        max_selections=3,
        key="comparador_artistas",
        help="Máximo 3 · el orden de selección define el color en los gráficos.",
    )

    if len(seleccion) < 2:
        st.info(
            "Comparador listo: elige **al menos 2 artistas** para ver la "
            "comparativa."
        )
    else:
        sub = (
            df[df["artist_name"].isin(seleccion)]
            .set_index("artist_name")
            .loc[seleccion]
        )
        colores = ["#0066FF", "#00CED1", "#FF4757"]

        # Colores de texto del bloque (tarjetas + gráficos) según tema activo:
        # los neón de identidad (#00CED1 y la paleta) solo cambian en claro.
        _claro = TEMA_APP == "claro"
        _TXT = "#0f172a" if _claro else "#e2e8f0"
        _SEC = "#475569" if _claro else "#94a3b8"
        _VAL = "#0066FF" if _claro else "#00CED1"
        _HR = "rgba(15,23,42,0.12)" if _claro else "rgba(255,255,255,0.1)"

        # Formateador compartido por las tarjetas KPI y la ficha técnica.
        def _fmt_ficha(tipo, valor):
            try:
                if valor is None or pd.isna(valor):
                    return "—"
            except (TypeError, ValueError):
                pass
            if tipo == "entero":
                return f"{int(valor):,}"
            if tipo == "score":
                return f"{valor:.1f}"
            if tipo == "pct":
                return f"{valor:.1f}%"
            if tipo == "dec":
                return f"{float(valor):.3f}"
            if tipo == "mes":
                return f"Mes {int(valor)}"
            if tipo == "si_no":
                return "Sí" if float(valor) == 1 else "No"
            return str(valor)

        # ── Tarjetas KPI lado a lado (glassmorphism + foto con fallback) ──
        # Borde superior con el MISMO color neón que las barras del gráfico:
        # la identidad visual del artista es consistente en toda la vista.
        st.markdown("#### 📊 Resumen Ejecutivo Comparativo")
        cols_kpi = st.columns(len(sub.index))
        for i, (col_kpi, artista) in enumerate(zip(cols_kpi, sub.index)):
            color = colores[i % len(colores)]
            f = sub.loc[artista]
            score = float(f.get("scouting_score", 0) or 0)
            fans = f.get("deezer_fans", None)
            genero = f.get("genero", None) or "—"
            pais = f.get("pais_origen", None)
            try:
                foto = str(f.get("picture_url", "") or "")
            except (TypeError, ValueError):
                foto = ""
            pares = [
                ("Score", f"{score:.0f}/100"),
                ("Breakout 6M", _fmt_ficha("pct", f.get("prob_breakout_6m"))),
                ("Prob. Viralidad", _fmt_ficha("pct", f.get("probabilidad_viral"))),
                ("Ventana firma", _fmt_ficha("mes", f.get("mes_optimo_firma"))),
                ("Fans Deezer", _fmt_ficha("entero", fans)),
            ]
            filas_html = "".join(
                f'<div style="display:flex;justify-content:space-between;'
                f'font-size:0.8rem;color:{_SEC};margin-top:5px;">'
                f"<span>{et}</span>"
                f'<strong style="color:{_VAL};">{val}</strong></div>'
                for et, val in pares
            )
            with col_kpi:
                st.markdown(
                    f"""
                    <div class="glass-card" style="border-top: 4px solid {color};
                            text-align: center; padding: 16px;">
                        <img src="{foto}"
                             onerror="this.onerror=null;
                                      this.src='{_SVG_PLACEHOLDER_B64}'"
                             style="width: 80px; height: 80px; border-radius: 50%;
                                    object-fit: cover; margin-bottom: 10px;
                                    border: 2px solid {color};">
                        <h4 style="margin: 0; color: {_TXT};">{artista}</h4>
                        <p style="color: {_SEC}; font-size: 0.85rem;
                                  margin-top: 5px;">{genero}{' · ' + str(pais) if pais and str(pais) != 'nan' else ''}</p>
                        <hr style="border-color: {_HR};
                                   margin: 10px 0;">
                        {filas_html}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        st.markdown("---")

        # ── Gráfico ejecutivo agrupado (2 paneles): la vista de un vistazo ──
        fig_resumen = make_subplots(
            rows=1,
            cols=2,
            subplot_titles=(
                "Scouting Score vs Prob. Breakout 6M (%)",
                "Fans en Deezer (millones)",
            ),
            horizontal_spacing=0.12,
        )
        for i, artista in enumerate(sub.index):
            color = colores[i % len(colores)]
            score = float(sub.at[artista, "scouting_score"])
            bo = sub.at[artista, "prob_breakout_6m"]
            fans_m = float(sub.at[artista, "deezer_fans"]) / 1_000_000
            fig_resumen.add_trace(
                go.Bar(
                    name=artista,
                    x=["Scouting Score", "Prob. Breakout 6M"],
                    y=[score, bo if pd.notna(bo) else 0],
                    text=[
                        f"{score:.0f}",
                        f"{bo:.0f}%" if pd.notna(bo) else "—",
                    ],
                    textposition="auto",
                    textfont=dict(color=_TXT),
                    marker=dict(color=color, line=dict(width=0)),
                    legendgroup=artista,
                    showlegend=True,
                    hovertemplate="%{x}: %{text}<extra></extra>",
                ),
                row=1,
                col=1,
            )
            fig_resumen.add_trace(
                go.Bar(
                    name=artista,
                    x=["Fans (M)"],
                    y=[fans_m],
                    text=[f"{fans_m:.1f}M"],
                    textposition="auto",
                    textfont=dict(color=_TXT),
                    marker=dict(color=color, line=dict(width=0)),
                    legendgroup=artista,
                    showlegend=False,
                    hovertemplate="%{x}: %{text}<extra></extra>",
                ),
                row=1,
                col=2,
            )
        fig_resumen.update_layout(barmode="group", height=380)
        fig_resumen.update_yaxes(range=[0, 105], row=1, col=1)
        fig_resumen.update_annotations(font=dict(color=_TXT, size=13))
        st.plotly_chart(
            estilo_plotly(fig_resumen, alto=380, leyenda=True),
            use_container_width=True,
            key="comparador_resumen",
        )

        # ── 6 paneles (2x3) con la MISMA paleta por artista ──
        fig = make_subplots(
            rows=2,
            cols=3,
            subplot_titles=(
                "Fans Deezer (escala log)",
                "Deezer Rank (escala log)",
                "Scouting Score (/100)",
                "Prob. Viralidad 6M (%)",
                "Prob. Breakout 6M · Cox (%)",
                "Mes óptimo de firma (0 = sin riesgo >10%)",
            ),
            vertical_spacing=0.18,
            horizontal_spacing=0.09,
        )

        for i, artista in enumerate(sub.index):
            color = colores[i % len(colores)]
            fans = sub.at[artista, "deezer_fans"]
            rank = sub.at[artista, "deezer_rank"]
            score = sub.at[artista, "scouting_score"]
            viral = sub.at[artista, "probabilidad_viral"]
            breakout = sub.at[artista, "prob_breakout_6m"]
            mes = sub.at[artista, "mes_optimo_firma"]
            tiene_ventana = pd.notna(mes)

            trazas = [
                # row1: audiencia
                dict(x=[artista], y=[fans], text=f"{int(fans):,}", t="fans"),
                dict(x=[artista], y=[rank], text=f"{int(rank):,}", t="rank"),
                dict(x=[artista], y=[score], text=f"{score:.1f}", t="score"),
                # row2
                dict(x=[artista], y=[viral], text=f"{viral:.1f}%", t="viral"),
                dict(
                    x=[artista],
                    y=[breakout if pd.notna(breakout) else 0],
                    text=f"{breakout:.1f}%" if pd.notna(breakout) else "—",
                    t="breakout",
                ),
                dict(
                    x=[artista],
                    y=[mes if tiene_ventana else 0],
                    text=f"Mes {int(mes)}" if tiene_ventana else "—",
                    t="mes",
                ),
            ]
            for pos, tr in enumerate(trazas):
                fila, columna = divmod(pos, 3)
                fig.add_trace(
                    go.Bar(
                        x=tr["x"],
                        y=tr["y"],
                        text=tr["text"],
                        textposition="outside",
                        textfont=dict(size=11, color=_TXT),
                        marker=dict(
                            color=color,
                            line=dict(width=0),
                            opacity=0.9,
                        ),
                        name=artista,
                        legendgroup=artista,
                        showlegend=pos == 0,  # un ítem por artista en la leyenda
                        hovertemplate="%{x}<br>%{text}<extra></extra>",
                    ),
                    row=fila + 1,
                    col=columna + 1,
                )

        fig.update_yaxes(type="log", row=1, col=1)
        fig.update_yaxes(type="log", row=1, col=2)
        fig.update_yaxes(range=[0, 105], row=1, col=3)
        fig.update_yaxes(range=[0, 105], row=2, col=1)
        fig.update_yaxes(range=[0, 105], row=2, col=2)
        fig.update_yaxes(range=[0, 13], row=2, col=3, dtick=1)
        fig.update_layout(barmode="group")
        fig.update_annotations(font=dict(color=_TXT, size=13))
        st.plotly_chart(
            estilo_plotly(fig, alto=640, leyenda=True),
            use_container_width=True,
            key="comparador_charts",
        )
        st.caption(
            "Los ejes de audiencia usan escala logarítmica (los artistas "
            "difieren en dos órdenes de magnitud). En *Mes óptimo*, la barra "
            "en 0 significa que el riesgo no cruza el 10% en 12 meses."
        )

        # ── Ficha técnica lado a lado (lo que un A&R lee en la reunión) ──
        st.markdown("#### 📋 Ficha comparativa")

        COLUMNAS_FICHA = [
            ("scouting_score", "Scouting Score", "score"),
            ("ar_recommendation", "Recomendación A&R", "texto"),
            ("deezer_fans", "Fans Deezer", "entero"),
            ("deezer_rank", "Deezer Rank", "entero"),
            ("est_alcance_max", "Alcance est. máx.", "entero"),
            ("probabilidad_viral", "Prob. Viralidad 6M", "pct"),
            ("prob_breakout_6m", "Prob. Breakout 6M (Cox)", "pct"),
            ("mes_optimo_firma", "Ventana de firma", "mes"),
            ("riesgo", "Riesgo Cox", "texto"),
            ("top_track_name", "Top Track", "texto"),
            ("top_track_rank", "Rank Top Track", "entero"),
            ("genero", "Género", "texto"),
            ("pais_origen", "País", "texto"),
            ("ratio_fans_rank", "ratio_fans_rank (ADN)", "dec"),
            ("top_track_dominance", "top_track_dominance (ADN)", "dec"),
            ("es_solista", "Es solista", "si_no"),
            ("nombre_corto", "Nombre corto", "si_no"),
        ]

        ficha = {}
        for col, etiqueta, tipo in COLUMNAS_FICHA:
            if col not in sub.columns:
                continue
            ficha[etiqueta] = {
                artista: _fmt_ficha(tipo, sub.at[artista, col])
                for artista in sub.index
            }
        st.dataframe(
            pd.DataFrame(ficha).T, use_container_width=True, hide_index=False
        )

        # ── Veredicto del comparador + salto al perfil ──
        resumen = []
        mejor_score = sub["scouting_score"].idxmax()
        resumen.append(
            f"mejor Scouting Score: **{mejor_score}** "
            f"({sub['scouting_score'].max():.1f}/100)"
        )
        if "prob_breakout_6m" in sub.columns and sub["prob_breakout_6m"].notna().any():
            mejor_bo = sub["prob_breakout_6m"].idxmax()
            resumen.append(
                f"mayor prob. de breakout a 6M: **{mejor_bo}** "
                f"({sub['prob_breakout_6m'].max():.1f}%)"
            )
        if "deezer_fans" in sub.columns:
            resumen.append(f"mayor base de fans: **{sub['deezer_fans'].idxmax()}**")
        st.caption(" · ".join(resumen))

        # Exportar la comparación (Prioridad 2c): mismas métricas que la
        # ficha, una fila por artista, con fecha para no pisar exportaciones.
        _cols_export = ["artist_name"] + [
            c for c, _et, _tp in COLUMNAS_FICHA if c in sub.columns
        ]
        csv_comparacion = (
            sub.reset_index()[_cols_export].to_csv(index=False).encode("utf-8")
        )
        st.download_button(
            label=f"📥 Exportar comparación ({len(sub)} artistas, CSV)",
            data=csv_comparacion,
            file_name=(
                "comparacion_artistas_"
                + pd.Timestamp.today().strftime("%Y-%m-%d")
                + ".csv"
            ),
            mime="text/csv",
            key="export_comparacion",
        )

        botones = st.columns(len(sub.index))
        for i, artista in enumerate(sub.index):
            with botones[i]:
                if st.button(
                    f"👤 Ver perfil de {artista}",
                    key=f"perfil_comparador_{artista}",
                    use_container_width=True,
                ):
                    st.session_state.artista_seleccionado = artista
                    st.session_state.vista_actual = "perfil"
                    st.rerun()

    st.stop()

# ==========================================
# VISTA 3: TOURING — página independiente (mismo despacho que Forecasting)
# ==========================================
if vista_tab == "🌍 Touring":
    st.subheader("🌍 Touring Recommendation Engine")
    st.markdown(
        "**Simulación de mercado geoespacial**: la API pública de Deezer no "
        "expone fans por ciudad (dato premium), así que la demanda se modela "
        "con el tamaño de mercado de cada ciudad y la conversión fan→ticket "
        "de la industria. Σ fans por ciudad = fans reales del artista "
        "(reparto proporcional conservativo)."
    )

    opciones_tour = (
        df.sort_values("scouting_score", ascending=False)["artist_name"]
        .tolist()
    )
    artista_seleccionado = st.selectbox(
        "Elige un artista para planificar su gira:", opciones_tour
    )

    datos_artista = df[df["artist_name"] == artista_seleccionado].iloc[0]
    df_touring = calcular_ruta_touring(
        artista_seleccionado,
        int(datos_artista["deezer_fans"]),
        int(datos_artista["deezer_rank"]),
    )
    resumen = resumen_gira(df_touring)

    display_kpi_grid(
        [
            ("ROI bruto de la gira", f"${resumen['roi_total_usd']:,}", "💰"),
            ("Asistentes proyectados", f"{resumen['total_asistentes']:,}", "🎟️"),
            ("Mercado #1", resumen["mercado_top"], "🥇"),
            ("Venues viables", f"{resumen['venues_viables']}/8", "🏛️"),
        ]
    )

    st.divider()

    # Mapa con tema oscuro premium (Esri Dark Gray Canvas) — coherente con el
    # design system. st_folium vacío de returned_objects: el mapa es de
    # solo-lectura y así Streamlit NO re-ejecuta el script en cada drag/zoom.
    import folium
    from streamlit_folium import st_folium

    mapa_gira = folium.Map(
        location=[10.0, -70.0],  # centro visual entre LatAm y España
        zoom_start=3,
        tiles=None,
    )
    # CartoDB dark_matter (el basemap del tutorial) ya NO acepta acceso
    # anónimo: los tiles llegan con el sello "API key REQUIRED" estampado.
    # Esri Dark Gray Canvas: tema oscuro real, gratuito, solo atribución.
    folium.TileLayer(
        tiles=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
        ),
        attr=(
            "Tiles &copy; Esri — Source: Esri, HERE, Garmin, FAO, NOAA, "
            "USGS | Esri Dark Gray Canvas"
        ),
        name="Esri Dark Gray",
        max_zoom=16,
    ).add_to(mapa_gira)
    for _, mrow in df_touring.iterrows():
        popup_html = f"""
        <div style="font-family: sans-serif; color: #333;">
            <h4 style="margin:0; color:#0066FF;">{mrow['ciudad']}</h4>
            <hr style="margin: 5px 0;">
            <b>Venue:</b> {mrow['venue_recomendado']}<br>
            <b>Asistentes Est.:</b> {int(mrow['asistentes_estimados']):,}<br>
            <b>Ticket:</b> ${int(mrow['ticket_price_usd'])} USD<br>
            <b>ROI Estimado:</b> ${int(mrow['roi_estimado_usd']):,} USD
        </div>
        """
        folium.CircleMarker(
            location=[mrow["lat"], mrow["lon"]],
            radius=int(mrow["radio"]),
            popup=folium.Popup(popup_html, max_width=250),
            color=mrow["color"],
            fill=True,
            fill_color=mrow["color"],
            fill_opacity=0.6,
            weight=2,
        ).add_to(mapa_gira)

    st_folium(mapa_gira, use_container_width=True, height=500, returned_objects=[])

    # Resumen de la gira
    st.markdown("#### 📊 Resumen de la Gira")
    st.dataframe(
        df_touring[
            [
                "ciudad",
                "venue_recomendado",
                "asistentes_estimados",
                "ticket_price_usd",
                "roi_estimado_usd",
            ]
        ].rename(
            columns={
                "ciudad": "Ciudad",
                "venue_recomendado": "Venue Recomendado",
                "asistentes_estimados": "Asistentes Est.",
                "ticket_price_usd": "Ticket (USD)",
                "roi_estimado_usd": "ROI Bruto (USD)",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        f"Simulación para **{artista_seleccionado}**: {resumen['asistentes_top']:,} "
        "asistentes en el mercado #1. Conversión fan→ticket 2% "
        "(−20% fuera del top 400k de rank), reparto proporcional por tamaño de "
        "mercado, ticket por tier de venue. Modelo determinista: mismo artista "
        "→ misma gira."
    )
    st.divider()
    st.caption(
        "Data Product desarrollado por David NED Bustamante | Music Data Analyst "
        "| Touring: Folium + simulación de mercado"
    )
    st.stop()

# ==========================================
# VISTA 2: FORECASTING — despachada ANTES del contenido de Scouting para que
# cada vista sea una página independiente (antes el forecast se apilaba
# debajo de toda la página de Scouting)
# ==========================================
if vista_tab == "🔮 Forecasting 6M":
    # Selector de artista PROPIO de esta vista. El radio de Vistas resetea
    # `artista_seleccionado` al cambiar de pestaña (línea del router arriba),
    # así que el forecast vive en SU estado: `artista_forecast` (widget key).
    # Antes de esto la vista leía un artista fijo → todo el módulo decía
    # "KAROL G" sin importar qué artistas filtrara el usuario.
    st.sidebar.subheader("🔮 Forecasting 6M")
    _artistas = sorted(df["artist_name"].dropna().unique().tolist())
    _preferido = st.session_state.get("artista_forecast")
    if _preferido not in _artistas:
        _preferido = (
            "KAROL G"
            if "KAROL G" in _artistas
            else (_artistas[0] if _artistas else None)
        )
        st.session_state["artista_forecast"] = _preferido
    artista_nombre = st.sidebar.selectbox(
        "Artista a proyectar a 6 meses",
        _artistas,
        key="artista_forecast",
        help=(
            "El modelo se (re)entrena con los fans actuales de este artista: "
            "título, curva, KPIs y CSV cambian con la selección."
        ),
    )
    st.sidebar.divider()

    _fila_artista = df.loc[df["artist_name"] == artista_nombre]
    fans_actuales = None
    momentum_viral = None
    if not _fila_artista.empty:
        _fans = pd.to_numeric(_fila_artista.iloc[0].get("deezer_fans"), errors="coerce")
        if pd.notna(_fans) and float(_fans) > 0:
            fans_actuales = int(_fans)
        _viral = pd.to_numeric(
            _fila_artista.iloc[0].get("probabilidad_viral"), errors="coerce"
        )
        if pd.notna(_viral):
            momentum_viral = float(_viral)

    if fans_actuales is None:
        st.warning(
            f"⚠️ Sin métrica de fans actual para **{artista_nombre}**: el "
            "forecast necesita el contador de Deezer de HOY para anclar la "
            "proyección."
        )
        st.stop()

    # Spinner solo si ESTE artista aún no está en cache de proceso (cache hit
    # = flash innecesario; además Streamlit muestra su spinner nativo)
    fc_en_cache = st.session_state.get("forecast_en_cache") == artista_nombre
    fc_slot = None if fc_en_cache else st.empty()
    if not fc_en_cache:
        show_loading_spinner(
            f"Entrenando el modelo y proyectando 6 meses para {artista_nombre}...",
            slot=fc_slot,
        )
    try:
        fc = cargar_forecast(
    artista_nombre,
    fans_actuales,
    momentum_viral,
    # Solo forma parte de la clave de caché: si cambia el motor de
    # forecasting (FORECAST_ENGINE) la figura de 24 h se regenera sola.
    motor=os.environ.get("FORECAST_ENGINE", "sklearn"),
)
        st.session_state.forecast_en_cache = artista_nombre
        if fc_slot is not None:
            fc_slot.empty()
    except Exception as e:
        if fc_slot is not None:
            fc_slot.empty()
        st.error(f"⚠️ No se pudo generar el forecast: {e}")
        st.stop()

    st.subheader(f"🔮 Proyección de Crecimiento de Fans: {fc['artista']}")
    st.markdown(
        "**Series de tiempo** para anticipar el fandom a 6 meses — la métrica "
        "que planea giras, lanzamientos y pricing de firma antes de que el "
        "artista explote."
    )

    display_kpi_grid(
        [
            ("Fans hoy", f"{fc['fans_hoy']:,}", "🎧"),
            ("Crecimiento proyectado 6M", f"+{fc['crecimiento_6m_pct']}%", "📈"),
            ("CAGR anualizado", f"{fc['cagr_anualizado_pct']}%", "🚀"),
        ]
    )

    st.pyplot(fc["fig"], use_container_width=True)

    with st.expander("📋 Detalle mes a mes de la proyección"):
        st.dataframe(fc["forecast"], use_container_width=True, hide_index=True)

    st.caption(
        f"Motor: **{fc['engine']}** · Histórico: {fc['origen_historico']}, "
        "anclado al mes actual (forecast 'evergreen': siempre proyecta los 6 "
        "meses siguientes). El robot de "
        "GitHub Actions (lunes 8 AM) acumula snapshots reales de fans — con 6+ "
        "puntos este histórico sintético se reemplaza por datos observados sin "
        "cambiar código."
    )

    st.sidebar.divider()
    st.sidebar.subheader("💾 Exportar Datos")
    csv_fc = fc["forecast"].to_csv(index=False).encode("utf-8")
    st.sidebar.download_button(
        label="📥 Descargar proyección (CSV)",
        data=csv_fc,
        file_name=f"forecast_fans_{fc['artista'].replace(' ', '_').lower()}.csv",
        mime="text/csv",
    )
    st.divider()
    st.caption(
        "Data Product desarrollado por David NED Bustamante | Music Data Analyst "
        "| Forecasting: scikit-learn (Prophet opt-in) · Datos: robot semanal"
    )
    st.stop()

# ==========================================
# VISTA 1: SCOUTING
# ==========================================

# ── ALERTAS CONFIGURABLES (Prioridad 3): el usuario mueve sus umbrales y la
# app le avisa al entrar. Se evalúan SIEMPRE sobre el universo completo (`df`)
# para que la alerta no dependa de los filtros del momento.
with st.sidebar.expander("🔔 Alertas A&R", expanded=False):
    alertas_on = st.toggle(
        "Activar alertas",
        value=True,
        key="alertas_activas",
        help="Escanea el universo completo con tus umbrales y muestra el "
        "aviso en la cabecera de Scouting.",
    )
    alerta_score = st.slider(
        "Score mínimo", 0, 100, 75, key="alerta_score", help="Scouting Score."
    )
    alerta_prob = st.slider(
        "Prob. Breakout 6M mínima",
        0,
        100,
        40,
        key="alerta_prob",
        help="Modelo Cox (probabilidad de cruzar el umbral de breakout a 6 meses).",
    )
    alerta_mes = st.slider(
        "Ventana de firma máxima (meses)",
        1,
        12,
        6,
        key="alerta_mes",
        help="Sólo aplica a artistas con ventana de firma (riesgo >10%). "
        "Un artista sin ventana nunca dispara alerta.",
    )
    alerta_favoritos = st.toggle(
        "Sólo favoritos ⭐",
        value=False,
        key="alerta_solo_favoritos",
        help="Limita las alertas a tu lista de favoritos.",
    )

# ── 3. FILTROS (el widget del buscador se define arriba del sidebar;
# aquí solo vive su lógica: búsqueda = comodín, filtros = refinamiento) ──
if patron:
    df_busqueda = df[
        df["artist_name"].str.contains(patron, case=False, na=False, regex=False)
    ].sort_values("scouting_score", ascending=False)
    if df_busqueda.empty:
        st.sidebar.warning("Sin coincidencias en el universo monitorizado")
    else:
        st.sidebar.success(f"✅ {len(df_busqueda)} artista(s) encontrado(s)")
        st.sidebar.caption(
            "🔎 Modo búsqueda: el nombre manda — los filtros de recomendación "
            "y score quedan en pausa para que encuentres a CUALQUIER artista "
            "del universo."
        )
    df_filtered = df_busqueda
    _desc_filtros = f'búsqueda "{patron}"'
else:
    st.sidebar.header("🎛️ Filtros de Búsqueda")
    # Default = TODO el universo: con 151 artistas la paginación y el
    # histograma pierden sentido si DESCARTAR (la cola larga) está oculta.
    recommendation_filter = st.sidebar.multiselect(
        "Recomendación A&R",
        options=sorted(df["ar_recommendation"].unique()),
        default=sorted(df["ar_recommendation"].unique()),
    )

    min_score = st.sidebar.slider("Scouting Score Mínimo", 0, 100, 0)

    # ── Filtros avanzados (Prioridad 1.3): género, país, fans y Cox ──
    # Todos con default "sin filtrar" para no alterar el universo completo.
    with st.sidebar.expander("🧭 Filtros Avanzados", expanded=False):
        opciones_genero = sorted(df["genero"].dropna().astype(str).unique())
        generos_sel = st.multiselect(
            "Género",
            options=opciones_genero,
            default=[],
            key="filtro_genero",
            help="Vacío = todos los géneros.",
        )
        opciones_pais = sorted(df["pais_origen"].dropna().astype(str).unique())
        paises_sel = st.multiselect(
            "País de origen",
            options=opciones_pais,
            default=[],
            key="filtro_pais",
            help="Mercado de origen según la cohorte con la que se entrenó "
            "el modelo Cox (la API de Deezer no expone país).",
        )

        fans_min = int(df["deezer_fans"].min())
        fans_max = int(df["deezer_fans"].max())
        paso_fans = max(1, (fans_max - fans_min) // 200)
        # El extremo superior se alinea al paso: si no, el tirador derecho
        # queda fuera de la retícula y el artista con más fans se excluye.
        tope_fans = fans_min + paso_fans * (
            (fans_max - fans_min + paso_fans - 1) // paso_fans
        )
        rango_fans = st.slider(
            "Rango de fans (Deezer)",
            min_value=fans_min,
            max_value=tope_fans,
            value=(fans_min, tope_fans),
            step=paso_fans,
            key="filtro_fans",
            format="%d",
            help="Escala lineal sobre los fans de Deezer.",
        )

        prob_min = st.slider(
            "Prob. Breakout 6M mínima (Cox)",
            0,
            100,
            0,
            key="filtro_prob_breakout",
            help="0 = sin filtrar. Modela la probabilidad de que el artista "
            "cruce el umbral de breakout dentro de 6 meses.",
        )
        solo_ventana = st.checkbox(
            "Solo con ventana de firma (riesgo >10%)",
            value=False,
            key="filtro_ventana",
            help="Excluye a los artistas cuyo riesgo nunca supera el 10% "
            "durante los 12 meses (sin ventana de firma).",
        )
        solo_favoritos = st.checkbox(
            "Solo favoritos ⭐",
            value=False,
            key="filtro_favoritos",
            help="Se añade favoritos desde el perfil del artista. "
            f"Tienes {len(st.session_state.get('favoritos', []))} favorito(s).",
        )
        _favs = st.session_state.get("favoritos", [])
        if _favs:
            st.caption(
                "⭐ " + " · ".join(_favs[:10]) + (" …" if len(_favs) > 10 else "")
            )

    # Filtrar datos
    df_filtered = df[
        (df["ar_recommendation"].isin(recommendation_filter))
        & (df["scouting_score"] >= min_score)
        & (df["deezer_fans"] >= rango_fans[0])
        & (df["deezer_fans"] <= rango_fans[1])
        & (df["prob_breakout_6m"].fillna(0) >= prob_min)
    ].sort_values("scouting_score", ascending=False)

    if generos_sel:
        df_filtered = df_filtered[
            df_filtered["genero"].astype(str).isin(generos_sel)
        ]
    if paises_sel:
        df_filtered = df_filtered[
            df_filtered["pais_origen"].astype(str).isin(paises_sel)
        ]
    if solo_ventana:
        df_filtered = df_filtered[df_filtered["mes_optimo_firma"].notna()]
    if solo_favoritos:
        df_filtered = df_filtered[
            df_filtered["artist_name"].isin(st.session_state.get("favoritos", []))
        ]

    # Descripción legible del filtro activo (Prioridad 2): la lleva el
    # export del CSV y la muestra el sidebar.
    _partes = []
    if len(recommendation_filter) < len(df["ar_recommendation"].unique()):
        _partes.append("recomendación=" + "/".join(recommendation_filter))
    if min_score:
        _partes.append(f"score ≥ {min_score}")
    if generos_sel:
        _partes.append("género=" + ", ".join(generos_sel))
    if paises_sel:
        _partes.append("país=" + ", ".join(paises_sel))
    if rango_fans[0] > fans_min or rango_fans[1] < tope_fans:
        _partes.append(f"fans {rango_fans[0]:,}–{rango_fans[1]:,}")
    if prob_min:
        _partes.append(f"prob. breakout ≥ {prob_min}%")
    if solo_ventana:
        _partes.append("con ventana")
    if solo_favoritos:
        _partes.append("favoritos")
    _desc_filtros = " · ".join(_partes) if _partes else "ninguno (universo completo)"

    st.sidebar.caption(
        f"🎛️ **{len(df_filtered)}** de {len(df)} artistas tras los filtros"
        f" · ⭐ {len(st.session_state.get('favoritos', []))} favoritos"
    )

# ── AVISO DE ALERTAS (Prioridad 3): umbrales configurados en el sidebar,
# evaluados SIEMPRE sobre el universo completo (los filtros no las apagan).
# Va ANTES del corte por vacío: si tus filtros dejan 0 filas, las alertas
# siguen siendo la salida accionable.
if alertas_on:
    _mascara_alerta = (
        (df["scouting_score"] >= alerta_score)
        & (df["prob_breakout_6m"].fillna(0) >= alerta_prob)
        & (df["mes_optimo_firma"].fillna(99) <= alerta_mes)
    )
    if alerta_favoritos:
        _mascara_alerta &= df["artist_name"].isin(
            st.session_state.get("favoritos", [])
        )
    alertas = df[_mascara_alerta].sort_values("scouting_score", ascending=False)
    _resumen_alerta = (
        f"score ≥ {alerta_score} · prob. breakout ≥ {alerta_prob}% · "
        f"ventana ≤ mes {alerta_mes}"
        + (" · sólo favoritos" if alerta_favoritos else "")
    )
    if alertas.empty:
        st.success(f"✅ **Sin alertas**: ningún artista cumple {_resumen_alerta}.")
    else:
        _nombres_alerta = ", ".join(alertas.head(6)["artist_name"].tolist())
        _extra = f" (+{len(alertas) - 6})" if len(alertas) > 6 else ""
        st.warning(
            f"🔔 **{len(alertas)} artista(s)** disparan tus alertas "
            f"({_resumen_alerta}): **{_nombres_alerta}**{_extra}"
        )
        _cols_alerta = st.columns(min(3, len(alertas)))
        for _i, _nombre in enumerate(alertas.head(3)["artist_name"]):
            with _cols_alerta[_i]:
                if st.button(f"👤 Ver {_nombre}", key=f"alerta_btn_{_nombre}"):
                    st.session_state.artista_seleccionado = _nombre
                    st.session_state.vista_actual = "perfil"
                    st.rerun()

if df_filtered.empty:
    if patron:
        st.warning(
            f"🔎 Sin resultados para **“{patron}”** en el universo de "
            f"{len(df)} artistas monitorizados."
        )
    else:
        st.warning("🎛️ Ningún artista cumple los filtros seleccionados.")
    st.info(
        "💡 Prueba con: **"
        + "**, **".join(df.nlargest(3, "deezer_fans")["artist_name"].tolist())
        + "**"
    )
    st.stop()

# KPIs estilo Bloomberg (Fase 2)
display_kpi_grid(
    [
        ("Total Artistas Analizados", len(df_filtered), "👥"),
        (
            "Firmar Ahora",
            len(df_filtered[df_filtered["ar_recommendation"] == "🔥 FIRMAR AHORA"]),
            "🔥",
        ),
        ("Scouting Score Promedio", f"{df_filtered['scouting_score'].mean():.1f}", "⭐"),
        ("Total Fans (Deezer)", f"{int(df_filtered['deezer_fans'].sum()):,}", "🎵"),
    ]
)

st.divider()

# Top Artists con Fotos — cada card es CLICKEABLE: navega al perfil
# multi-plataforma del artista (router st.session_state). El botón va
# ENCIMA de la card: dentro del HTML no se puede incrustar un st.button.
st.subheader("🏆 Top 10 Artistas Prioritarios")

top_10 = df_filtered.head(10)

for pos, (_, row) in enumerate(top_10.iterrows()):
    if st.button(
        f"👤 Ver perfil de {row['artist_name']} · alcance est. {int(row['est_alcance_max']):,}",
        key=f"perfil_hero_{row['artist_name']}",
        use_container_width=True,
    ):
        st.session_state.artista_seleccionado = row["artist_name"]
        st.session_state.vista_actual = "perfil"
        st.rerun()
    # La foto la descarga el navegador (paralelo, con fallback inline): la
    # versión anterior la bajaba el servidor en serie y costaba ≈1.7 s de
    # backend en la primera carga.
    st.markdown(
        artist_card_html(row, photo_data_uri=None, index=pos),
        unsafe_allow_html=True,
    )

# ==========================================
# ANALYTICS DEL UNIVERSO (Fase 5: Plotly)
# ==========================================
st.markdown("---")
st.subheader("📊 Analytics del Universo Scouting")

col_hist, col_donut = st.columns(2)
with col_hist:
    fig_hist = px.histogram(
        df_filtered,
        x="scouting_score",
        nbins=20,
        title="Distribución de Scouting Scores",
        color_discrete_sequence=[NEON_AZUL],
    )
    fig_hist.update_layout(bargap=0.08)
    st.plotly_chart(
        estilo_plotly(fig_hist),
        use_container_width=True,
        config={"displayModeBar": False},
        key="chart_hist_scores",
    )

with col_donut:
    reco_counts = (
        df_filtered["ar_recommendation"]
        .value_counts()
        .reset_index()
    )
    reco_counts.columns = ["recomendacion", "artistas"]
    fig_donut = px.pie(
        reco_counts,
        names="recomendacion",
        values="artistas",
        hole=0.55,
        title="Recomendaciones A&R",
        color="recomendacion",
        color_discrete_map=PALETA_RECOMENDACION,
    )
    fig_donut.update_traces(
        textinfo="percent",
        marker=dict(
            line=dict(
                color="#ffffff" if TEMA_APP == "claro" else "#0a0e27", width=2
            )
        ),
    )
    st.plotly_chart(
        estilo_plotly(fig_donut, leyenda=True),
        use_container_width=True,
        config={"displayModeBar": False},
        key="chart_donut_reco",
    )

# ── Drill-down (Prioridad 2): seleccionar puntos en un gráfico abre el
# perfil del artista. 1 punto = salto directo; varios = botones de elección.
def _nombres_desde_seleccion(evento):
    """Nombres de artista de los puntos seleccionados en un gráfico
    (customdata primero; fallback al eje Y para las barras del Top 10)."""
    try:
        puntos = list(evento.selection.points or [])
    except Exception:
        return []
    universo = set(df["artist_name"])
    nombres = []
    for punto in puntos:
        cd = punto.get("customdata")
        nombre = None
        if isinstance(cd, (list, tuple)) and cd:
            nombre = cd[0]
        elif isinstance(cd, str):
            nombre = cd
        if not isinstance(nombre, str):
            nombre = punto.get("y") if isinstance(punto.get("y"), str) else punto.get("x")
        if isinstance(nombre, str) and nombre in universo and nombre not in nombres:
            nombres.append(nombre)
    return nombres


def _drill_o_botones(nombres):
    if not nombres:
        return
    if len(nombres) == 1:
        st.session_state["drill_pendiente"] = nombres[0]
        st.rerun()
    st.caption("🔎 Varios puntos seleccionados — elige un artista para abrir su perfil:")
    for nombre in nombres[:8]:
        if st.button(f"👤 {nombre}", key=f"drill_btn_{nombre}"):
            st.session_state["drill_pendiente"] = nombre
            st.rerun()

# Top N en barras horizontales (respeta búsqueda y filtros activos)
top_chart = df_filtered.head(10).iloc[::-1]  # mejor score arriba
fig_top = px.bar(
    top_chart,
    x="scouting_score",
    y="artist_name",
    orientation="h",
    title="Top 10 por Scouting Score",
    color="ar_recommendation",
    color_discrete_map=PALETA_RECOMENDACION,
    text_auto=".0f",
    custom_data=["artist_name"],
    height=420,
)
fig_top.update_traces(textposition="outside", cliponaxis=False)
fig_top.update_yaxes(title=None)
evento_top = st.plotly_chart(
    estilo_plotly(fig_top, alto=420),
    use_container_width=True,
    # modebar solo al pasar el ratón: sin él no hay lasso/box (selección
    # múltiple); con él oculto el click simple en un punto sigue funcionando.
    config={"displayModeBar": "hover"},
    key="chart_top10",
    on_select="rerun",
)
_drill_o_botones(_nombres_desde_seleccion(evento_top))

col_scatter, col_genero = st.columns(2)
with col_scatter:
    fig_scatter = px.scatter(
        df_filtered,
        x="deezer_fans",
        y="scouting_score",
        color="ar_recommendation",
        color_discrete_map=PALETA_RECOMENDACION,
        hover_name="artist_name",
        custom_data=["artist_name"],
        log_x=True,
        title="Score vs Fans (escala log)",
        labels={"deezer_fans": "Fans Deezer (log)", "scouting_score": "Scouting Score"},
    )
    evento_scatter = st.plotly_chart(
        estilo_plotly(fig_scatter, leyenda=True),
        use_container_width=True,
        config={"displayModeBar": "hover"},
        key="chart_scatter_fans",
        on_select="rerun",
    )
    _drill_o_botones(_nombres_desde_seleccion(evento_scatter))

with col_genero:
    # El género llega del seed expandido (Fase 1); en un warehouse reconstruido
    # por bootstrap (sin la columna) la gráfica se omite con elegancia.
    if "genero" in df_filtered.columns:
        fans_genero = (
            df_filtered.groupby("genero", as_index=False)["deezer_fans"]
            .median()
            .sort_values("deezer_fans", ascending=False)
        )
        fig_genero = px.bar(
            fans_genero,
            x="deezer_fans",
            y="genero",
            orientation="h",
            title="Fans (mediana) por Género",
            color_discrete_sequence=[NEON_CIAN],
        )
        fig_genero.update_yaxes(title=None)
        st.plotly_chart(
            estilo_plotly(fig_genero),
            use_container_width=True,
            config={"displayModeBar": False},
            key="chart_genero_fans",
        )

# ==========================================
# PAGINACIÓN: TODOS LOS ARTISTAS (Fase 3)
# ==========================================
st.markdown("---")
st.subheader("🗂️ Todos los Artistas")

ARTISTAS_POR_PAGINA = 20
total_paginas = max(1, math.ceil(len(df_filtered) / ARTISTAS_POR_PAGINA))
pagina_actual = st.select_slider(
    "Página",
    options=list(range(1, total_paginas + 1)),
    value=1,
    label_visibility="collapsed",
)

inicio = (pagina_actual - 1) * ARTISTAS_POR_PAGINA
pagina_df = df_filtered.iloc[inicio : inicio + ARTISTAS_POR_PAGINA]
st.caption(
    f"Mostrando {len(pagina_df)} de {len(df_filtered)} artistas "
    f"(página {pagina_actual} de {total_paginas})"
)

cols_grid = st.columns(2)
for idx, (_, artista) in enumerate(pagina_df.iterrows()):
    with cols_grid[idx % 2]:
        # También las cards compactas de la paginación abren el perfil
        if st.button(
            f"👤 {artista['artist_name']} · score {artista['scouting_score']:.0f}",
            key=f"perfil_grid_{artista['artist_name']}",
            use_container_width=True,
        ):
            st.session_state.artista_seleccionado = artista["artist_name"]
            st.session_state.vista_actual = "perfil"
            st.rerun()
        st.markdown(
            artist_card_compacto_html(artista, index=idx),
            unsafe_allow_html=True,
        )

# Tabla completa exportable
st.subheader("📋 Base de Datos Completa")
columnas_tabla = [
    "artist_name",
    "scouting_score",
    "probabilidad_viral",
    "prob_breakout_6m",
    "mes_optimo_firma",
    "riesgo",
    "ar_recommendation",
    "deezer_fans",
    "deezer_rank",
    "top_track_name",
    "fan_rank_ratio",
    "strategic_insight",
]
rename_tabla = {
    "artist_name": "Artista",
    "scouting_score": "Score",
    "probabilidad_viral": "Prob. Viral 6M",
    "prob_breakout_6m": "Prob. Breakout 6M",
    "mes_optimo_firma": "Mes firma",
    "riesgo": "Riesgo Cox",
    "ar_recommendation": "Recomendación",
    "deezer_fans": "Fans",
    "deezer_rank": "Rank",
    "top_track_name": "Top Track",
    "fan_rank_ratio": "Fan/Rank Ratio",
    "strategic_insight": "Insight",
}
_idx_col = 1
if "genero" in df_filtered.columns:
    columnas_tabla.insert(_idx_col, "genero")
    rename_tabla["genero"] = "Género"
    _idx_col += 1
if "pais_origen" in df_filtered.columns:
    columnas_tabla.insert(_idx_col, "pais_origen")
    rename_tabla["pais_origen"] = "País"
tabla_cox = df_filtered[columnas_tabla].copy()
# Sin ventana de firma (riesgo <10% todo el año): en blanco no se distingue
# de un fallo de cálculo, así que se muestra el guion explícito
if "mes_optimo_firma" in tabla_cox.columns:
    tabla_cox["mes_optimo_firma"] = (
        tabla_cox["mes_optimo_firma"].astype("string").fillna("—")
    )
st.dataframe(
    tabla_cox.rename(columns=rename_tabla),
    use_container_width=True,
    hide_index=True,
)

# Exportar datos (Vista 1: Scouting) — exporta el FILTRO ACTIVO: respeta
# búsqueda, filtros y favoritos; el nombre lleva fecha y nº de filas para
# que dos exportaciones nunca se pisen.
st.sidebar.divider()
st.sidebar.subheader("💾 Exportar Datos")
csv = df_filtered.to_csv(index=False).encode("utf-8")
st.sidebar.caption(
    f"Exporta **{len(df_filtered)}** filas · filtro: **{_desc_filtros}**"
)
st.sidebar.download_button(
    label=f"📥 Descargar CSV ({len(df_filtered)} filas)",
    data=csv,
    file_name=(
        "ar_scouting_filtrado_"
        + pd.Timestamp.today().strftime("%Y-%m-%d")
        + f"_{len(df_filtered)}.csv"
    ),
    mime="text/csv",
)

# Informe Ejecutivo PDF del #1 del ranking activo (respeta búsqueda y filtros):
# el atajo "qué artista le mando a la junta hoy" sin entrar al perfil.
top_uno = df_filtered.iloc[0]
if st.sidebar.button(
    f"📄 Informe PDF: {top_uno['artist_name']} (Top 1)",
    key="btn_pdf_sidebar_top1",
    use_container_width=True,
):
    with st.spinner("Componiendo informe ejecutivo..."):
        try:
            st.session_state["pdf_bytes_sidebar"] = cargar_generador_pdf()(top_uno)
            st.session_state["pdf_generado_para_sidebar"] = top_uno["artist_name"]
        except Exception as e:
            st.session_state.pop("pdf_bytes_sidebar", None)
            st.sidebar.error(f"⚠️ No se pudo generar: {e}")
if (
    st.session_state.get("pdf_bytes_sidebar") is not None
    and st.session_state.get("pdf_generado_para_sidebar") == top_uno["artist_name"]
):
    st.sidebar.download_button(
        label="⬇️ Descargar Informe Ejecutivo (PDF)",
        data=st.session_state["pdf_bytes_sidebar"],
        file_name=(
            "informe_ejecutivo_"
            + top_uno["artist_name"].replace(" ", "_").lower()
            + ".pdf"
        ),
        mime="application/pdf",
        key="btn_pdf_descargar_sidebar",
        use_container_width=True,
    )

# La conexión compartida se cachea por proceso: NO se cierra aquí.
# Cerrarla en cada render mataba la re-ejecución de Streamlit
# ("Connection already closed!") al cambiar de vista.

# Footer
st.divider()
st.caption(
    "Data Product desarrollado por David NED Bustamante | Music Data Analyst "
    "| Datos: robot semanal (GitHub Actions) · Predicción: RandomForest · Forecasting: sklearn (Prophet opt-in)"
)
