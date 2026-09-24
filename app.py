import base64
import math

import streamlit as st
import pandas as pd
import duckdb
import joblib
import os
import plotly.express as px
from PIL import Image
import requests
from io import BytesIO

st.set_page_config(
    page_title="A&R Scouting Command Center - Deezer Data",
    page_icon="🎧",
    layout="wide",
    initial_sidebar_state="expanded",
)


def load_custom_css():
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


def artist_card_html(row, photo_data_uri=None, index=0):
    """Card de artista glassmórfica (hero). Conserva las features del tablero
    anterior que el HTML plano del tutorial descartaba: Probabilidad de
    Viralidad (ML) con barra, y fallback de foto si la CDN falla."""
    fans = f"{int(row['deezer_fans']):,}"
    rank = f"{int(row['deezer_rank']):,}"
    viral = f"{row['probabilidad_viral']:.1f}"
    viral_pct = min(row["probabilidad_viral"] / 100.0, 1.0) * 100
    if photo_data_uri is None:
        img_html = f'<img class="artist-photo" src="{row["picture_url"]}" alt="{row["artist_name"]}">'
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
    # Stagger real por card: el delay va inline (nth-child no funciona entre
    # st.markdown separados: cada card es hija única de su wrapper en el DOM)
    return f"""
    <div class="neumorphic-card artist-card" style="animation-delay: {index * 0.1:.1f}s;">
        <div style="display: grid; grid-template-columns: 100px 1fr 220px; gap: 20px; align-items: center;">
            <div>{photo}</div>
            <div>
                <h3 class="artist-name">{row['artist_name']}</h3>
                <p class="artist-meta">{badge} | Score: <strong class="score-value">{row['scouting_score']:.0f}/100</strong></p>
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
    return f"""
    <div class="neumorphic-card artist-card" style="animation-delay: {index * 0.05:.2f}s; padding: 15px; margin-bottom: 15px;">
        <div style="display: flex; gap: 14px; align-items: center;">
            <img src="{row['picture_url']}"
                 onerror="this.src='data:image/svg+xml;base64,{_SVG_PLACEHOLDER_B64}'"
                 style="width: 56px; height: 56px; border-radius: 12px; object-fit: cover; flex-shrink: 0;"
                 alt="{row['artist_name']}">
            <div style="flex: 1; min-width: 0;">
                <h4 class="artist-name" style="font-size: 1rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{row['artist_name']}</h4>
                <p class="artist-meta" style="margin: 4px 0 0;">
                    Score: <strong class="score-value">{row['scouting_score']:.0f}/100</strong> · 🎧 {fans} fans
                </p>
                <div style="margin-top: 6px;">{badge}</div>
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


def estilo_plotly(fig, alto=360, leyenda=False):
    """Fondo transparente + tipografía clara: el gráfico flota sobre el
    glassmorphism sin caja blanca (look Bloomberg/Spotify for Artists)."""
    fig.update_layout(
        height=alto,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, 'Segoe UI', sans-serif", size=12, color="#cbd5e1"),
        title=dict(font=dict(size=15, color="#e2e8f0"), x=0.01, xanchor="left"),
        margin=dict(l=10, r=10, t=46, b=10),
        showlegend=leyenda,
        legend=dict(font=dict(size=11), bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(
        gridcolor="rgba(255,255,255,0.06)",
        zerolinecolor="rgba(255,255,255,0.12)",
        linecolor="rgba(255,255,255,0.15)",
        tickfont=dict(color="#94a3b8"),
    )
    fig.update_yaxes(
        gridcolor="rgba(255,255,255,0.06)",
        zerolinecolor="rgba(255,255,255,0.12)",
        linecolor="rgba(255,255,255,0.15)",
        tickfont=dict(color="#94a3b8"),
    )
    return fig


load_custom_css()

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
modelo_ml, feature_names = cargar_modelo_ml()
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

# Cargar datos del modelo (creado por dbt o reconstruido por el bootstrap)
try:
    df = pd.read_sql_query("SELECT * FROM artist_scouting_deezer", conn)
except Exception:
    st.error("❌ No se encontraron datos. Ejecuta primero: `dbt seed && dbt run`")
    st.stop()

# ==========================================
# PREDICCIÓN DE MACHINE LEARNING EN TIEMPO REAL
# ==========================================
if modelo_ml is not None:
    # Proxy de crecimiento mensual calibrado al dominio del entrenamiento
    # U(-0.05, 0.30): ratio de conversión oyente→fan escalado y acotado
    # (el modelo aprendió con tasas reales, no con valores fuera de dominio)
    growth_proxy = (df["fan_rank_ratio"] / 15.0).clip(-0.05, 0.30)

    # Preparamos los datos para que coincidan con el entrenamiento
    df_ml_input = pd.DataFrame(
        {
            "current_fans": df["deezer_fans"],
            "current_rank": df["deezer_rank"],
            "track_rank": df["top_track_rank"],
            "monthly_growth_rate": growth_proxy,
            "genero_encoded": 0,  # valor por defecto para simplificar el demo
        }
    )

    # Aseguramos el orden exacto de columnas del entrenamiento
    df_ml_input = df_ml_input[feature_names]

    # Probabilidad de la clase "1" (Viral en 6 meses)
    df["probabilidad_viral"] = (
        modelo_ml.predict_proba(df_ml_input)[:, 1] * 100
    ).round(1)
else:
    df["probabilidad_viral"] = 0.0

# Datos y predicciones listas: fuera spinner y skeletons (solo si hubo)
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
# El gráfico se genera una vez por proceso (no en cada re-render): Prophet o
# su fallback sklearn solo se ejecutan cuando la app arranca o pasa la TTL.
@st.cache_resource(ttl=86400)
def cargar_forecast():
    import sys

    # El motor vive en scripts/; añadimos la carpeta al path para que el
    # import funcione igual en local y en el contenedor de Render.
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))
    import forecast_fans
    return forecast_fans.fit_and_forecast(save_png=False)


st.sidebar.header("🗂️ Vistas")
vista_tab = st.sidebar.radio(
    "Selecciona la vista:",
    options=["🎯 Scouting", "🔮 Forecasting 6M", "🌍 Touring"],
    label_visibility="collapsed",
)

# Motores de módulos: scripts/ al path ANTES de importar (el import directo
# 'from scripts.touring_engine import ...' rompe cuando el CWD de la app no
# es la raíz del repo — p.ej. el contenedor de Render)
import sys

_scripts_dir = os.path.join(os.path.dirname(__file__), "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)
from touring_engine import calcular_ruta_touring, resumen_gira

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
    # Spinner solo si el forecast no está en cache de proceso (cache hit =
    # flash innecesario; además Streamlit muestra su spinner nativo)
    fc_en_cache = "forecast_en_cache" in st.session_state
    fc_slot = None if fc_en_cache else st.empty()
    if not fc_en_cache:
        show_loading_spinner(
            "Entrenando Prophet y proyectando 6 meses...", slot=fc_slot
        )
    try:
        fc = cargar_forecast()
        st.session_state.forecast_en_cache = True
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
        f"Motor: **{fc['engine']}** · Histórico demo de 24 meses anclado al mes "
        "actual (forecast 'evergreen': siempre proyecta los 6 meses siguientes). "
        "El robot de "
        "GitHub Actions (lunes 8 AM) acumula snapshots reales de fans — con 6+ "
        "puntos este histórico se reemplaza por datos observados sin cambiar código."
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
        "| Forecasting: Prophet (fallback sklearn) · Datos: robot semanal"
    )
    st.stop()

# ==========================================
# VISTA 1: SCOUTING
# ==========================================

# ── BUSCADOR DE ARTISTAS (Fase 2) ────────────────────────────────────────
# Búsqueda en tiempo real por nombre: substring, case-insensitive y sin
# regex (el usuario escribe texto libre, p. ej. "C+" no debe explotar).
st.sidebar.header("🔍 Buscar Artista")
busqueda = st.sidebar.text_input(
    "Nombre del artista",
    placeholder="Ej: KAROL G, Feid, Marc Anthony…",
    label_visibility="collapsed",
)

patron = busqueda.strip()
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

    # Filtrar datos
    df_filtered = df[
        (df["ar_recommendation"].isin(recommendation_filter))
        & (df["scouting_score"] >= min_score)
    ].sort_values("scouting_score", ascending=False)

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

# Cache de fotos: un solo request por URL aunque Streamlit re-renderice.
# Devuelve data URI para embeber la imagen en el HTML de las cards
# glassmórficas (y fallback local si la CDN falla).
@st.cache_data(show_spinner=False, ttl=3600)
def cargar_foto_uri(url):
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content)).convert("RGB")
        img.thumbnail((160, 160))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        # Placeholder en línea (via.placeholder.com murió en 2024)
        return (
            "data:image/svg+xml;base64," + _SVG_PLACEHOLDER_B64
        )


_SVG_PLACEHOLDER = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
    '<rect width="100" height="100" fill="#1f2a3d"/>'
    '<text x="50" y="55" font-size="30" text-anchor="middle">🎼</text></svg>'
)
_SVG_PLACEHOLDER_B64 = base64.b64encode(_SVG_PLACEHOLDER.encode()).decode()


# Top Artists con Fotos
st.subheader("🏆 Top 10 Artistas Prioritarios")

top_10 = df_filtered.head(10)

for pos, (_, row) in enumerate(top_10.iterrows()):
    # Foto cacheada convertida a data URI: un solo request por URL, y el HTML
    # no depende de que la CDN responda (fallback a imagen placeholder)
    try:
        foto_uri = cargar_foto_uri(row["picture_url"])
    except Exception:
        foto_uri = None
    st.markdown(
        artist_card_html(row, photo_data_uri=foto_uri, index=pos),
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
        marker=dict(line=dict(color="#0a0e27", width=2)),
    )
    st.plotly_chart(
        estilo_plotly(fig_donut, leyenda=True),
        use_container_width=True,
        config={"displayModeBar": False},
        key="chart_donut_reco",
    )

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
    height=420,
)
fig_top.update_traces(textposition="outside", cliponaxis=False)
fig_top.update_yaxes(title=None)
st.plotly_chart(
    estilo_plotly(fig_top, alto=420),
    use_container_width=True,
    config={"displayModeBar": False},
    key="chart_top10",
)

col_scatter, col_genero = st.columns(2)
with col_scatter:
    fig_scatter = px.scatter(
        df_filtered,
        x="deezer_fans",
        y="scouting_score",
        color="ar_recommendation",
        color_discrete_map=PALETA_RECOMENDACION,
        hover_name="artist_name",
        log_x=True,
        title="Score vs Fans (escala log)",
        labels={"deezer_fans": "Fans Deezer (log)", "scouting_score": "Scouting Score"},
    )
    st.plotly_chart(
        estilo_plotly(fig_scatter, leyenda=True),
        use_container_width=True,
        config={"displayModeBar": False},
        key="chart_scatter_fans",
    )

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
    "ar_recommendation": "Recomendación",
    "deezer_fans": "Fans",
    "deezer_rank": "Rank",
    "top_track_name": "Top Track",
    "fan_rank_ratio": "Fan/Rank Ratio",
    "strategic_insight": "Insight",
}
if "genero" in df_filtered.columns:
    columnas_tabla.insert(1, "genero")
    rename_tabla["genero"] = "Género"
st.dataframe(
    df_filtered[columnas_tabla].rename(columns=rename_tabla),
    use_container_width=True,
    hide_index=True,
)

# Exportar datos (Vista 1: Scouting)
st.sidebar.divider()
st.sidebar.subheader("💾 Exportar Datos")
csv = df_filtered.to_csv(index=False).encode("utf-8")
st.sidebar.download_button(
    label="📥 Descargar CSV",
    data=csv,
    file_name="ar_scouting_deezer_report.csv",
    mime="text/csv",
)

# La conexión compartida se cachea por proceso: NO se cierra aquí.
# Cerrarla en cada render mataba la re-ejecución de Streamlit
# ("Connection already closed!") al cambiar de vista.

# Footer
st.divider()
st.caption(
    "Data Product desarrollado por David NED Bustamante | Music Data Analyst "
    "| Datos: robot semanal (GitHub Actions) · Predicción: RandomForest · Forecasting: Prophet/sklearn"
)
