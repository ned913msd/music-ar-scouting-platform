import base64

import streamlit as st
import pandas as pd
import duckdb
import joblib
import os
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
    """Design System Neumorphism (Fases 1 y 3): tema claro premium con
    sombras suaves dobles, hover states y animaciones de entrada.
    Selectores estables (data-testid) en vez de hashes .css-*, que cambian
    entre versiones de Streamlit."""
    custom_css = """
    <style>
    /* ==========================================
       NEUMORPHISM DESIGN SYSTEM
       ========================================== */

    /* Fondo principal con gradiente animado */
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #e8ecf1 100%);
        background-size: 200% 200%;
        animation: gradientShift 15s ease infinite;
    }

    @keyframes gradientShift {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }

    /* Cards con efecto Neumorphism */
    .neumorphic-card {
        background: #f0f2f6;
        border-radius: 20px;
        padding: 25px;
        box-shadow:
            8px 8px 16px #d1d5db,
            -8px -8px 16px #ffffff;
        margin-bottom: 20px;
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        animation: fadeInUp 0.6s ease-out;
    }

    .neumorphic-card:hover {
        box-shadow:
            12px 12px 24px #d1d5db,
            -12px -12px 24px #ffffff;
        transform: translateY(-4px) scale(1.01);
    }

    @keyframes fadeInUp {
        from {
            opacity: 0;
            transform: translateY(30px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    /* KPIs con estilo premium (grid en un solo bloque DOM: los div de
       Streamlit no permiten abrir un contenedor en varios st.markdown) */
    .kpi-container {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 20px;
        margin-bottom: 10px;
    }

    .kpi-card {
        background: linear-gradient(145deg, #ffffff, #f0f2f6);
        border-radius: 16px;
        padding: 20px;
        box-shadow:
            5px 5px 10px #d1d5db,
            -5px -5px 10px #ffffff;
        text-align: center;
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        animation: fadeInUp 0.6s ease-out both;
    }

    /* Entrada escalonada de los KPIs */
    .kpi-card:nth-child(1) { animation-delay: 0.1s; }
    .kpi-card:nth-child(2) { animation-delay: 0.2s; }
    .kpi-card:nth-child(3) { animation-delay: 0.3s; }
    .kpi-card:nth-child(4) { animation-delay: 0.4s; }

    .kpi-card:hover {
        transform: translateY(-5px) scale(1.05);
        box-shadow:
            10px 10px 20px #d1d5db,
            -10px -10px 20px #ffffff;
    }

    .kpi-value {
        font-size: 2.5rem;
        font-weight: 700;
        color: #0066FF;
        margin: 10px 0;
        text-shadow: 0 0 15px rgba(0, 102, 255, 0.3);
        animation: countUp 1s ease-out;
    }

    .kpi-label {
        font-size: 0.9rem;
        color: #6b7280;
        text-transform: uppercase;
        letter-spacing: 1px;
        transition: color 0.3s ease;
    }

    .kpi-card:hover .kpi-label {
        color: #0066FF;
    }

    @keyframes countUp {
        from { opacity: 0; transform: scale(0.5); }
        to { opacity: 1; transform: scale(1); }
    }

    /* Botones con efecto premium + brillo deslizante */
    .stButton > button {
        background: linear-gradient(145deg, #0066FF, #0052CC);
        color: white;
        border: none;
        border-radius: 12px;
        padding: 12px 24px;
        font-weight: 600;
        box-shadow:
            4px 4px 8px #d1d5db,
            -4px -4px 8px #ffffff;
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
    }

    .stButton > button::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent);
        transition: left 0.6s ease;
    }

    .stButton > button:hover::before {
        left: 100%;
    }

    .stButton > button:hover {
        transform: translateY(-3px);
        box-shadow:
            8px 8px 16px #d1d5db,
            -8px -8px 16px #ffffff,
            0 0 20px rgba(0, 102, 255, 0.4);
    }

    .stButton > button:active {
        transform: translateY(0);
        box-shadow:
            inset 2px 2px 4px #004099,
            inset -2px -2px 4px #0080FF;
    }

    /* Inputs con estilo neumórfico (inset) */
    .stTextInput > div > div > input,
    .stSelectbox > div > div > select {
        background: #f0f2f6;
        border-radius: 12px;
        padding: 12px;
        box-shadow:
            inset 2px 2px 4px #d1d5db,
            inset -2px -2px 4px #ffffff;
        border: 2px solid transparent;
        transition: all 0.3s ease;
    }

    .stTextInput > div > div > input:focus,
    .stSelectbox > div > div > select:focus {
        box-shadow:
            inset 3px 3px 6px #d1d5db,
            inset -3px -3px 6px #ffffff;
        border-color: #0066FF;
        animation: focusPulse 1.5s ease-in-out infinite;
    }

    @keyframes focusPulse {
        0%, 100% { box-shadow: inset 3px 3px 6px #d1d5db, inset -3px -3px 6px #ffffff, 0 0 0 0 rgba(0, 102, 255, 0.4); }
        50% { box-shadow: inset 3px 3px 6px #d1d5db, inset -3px -3px 6px #ffffff, 0 0 0 4px rgba(0, 102, 255, 0.2); }
    }

    /* Sidebar con gradiente y sombra (selector estable entre versiones) */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f5f7fa 0%, #e8ecf1 100%);
        box-shadow: 4px 0 15px rgba(0,0,0,0.08);
        transition: all 0.3s ease;
    }

    /* Títulos con brillo sutil que se intensifica al hover */
    h1, h2, h3 {
        color: #1f2937;
        font-weight: 700;
        text-shadow: 0 0 20px rgba(0, 102, 255, 0.15);
        transition: all 0.3s ease;
    }

    h1:hover, h2:hover, h3:hover {
        text-shadow: 0 0 30px rgba(0, 102, 255, 0.3);
    }

    /* Métricas nativas con card suave y hover */
    [data-testid="stMetric"] {
        background: linear-gradient(145deg, #ffffff, #f0f2f6);
        border-radius: 12px;
        padding: 15px;
        box-shadow:
            4px 4px 8px #d1d5db,
            -4px -4px 8px #ffffff;
        transition: all 0.3s ease;
    }

    [data-testid="stMetric"]:hover {
        transform: scale(1.05);
        box-shadow:
            6px 6px 12px #d1d5db,
            -6px -6px 12px #ffffff;
    }

    /* Animaciones (Fase 3) */
    @keyframes slideIn {
        from {
            opacity: 0;
            transform: translateY(20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.7; }
    }

    .loading {
        animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    }

    /* Imágenes de artista: esquinas suaves y sombra neumórfica */
    .artist-photo {
        width: 100%;
        height: auto;
        border-radius: 16px;
        box-shadow:
            4px 4px 8px #d1d5db,
            -4px -4px 8px #ffffff;
    }

    /* Internos de la card de artista como CLASES (no estilos inline):
       así el modo oscuro puede sobreescribirlos sin pelear con inline */
    .artist-name { margin: 0; color: #1f2937; }
    .artist-meta { margin: 5px 0; color: #6b7280; font-size: 0.9rem; }
    .score-value { color: #0066FF; }
    .artist-track { margin: 5px 0; color: #4b5563; font-size: 0.85rem; }
    .insight-pill {
        background: #e0f2fe;
        padding: 8px 12px;
        border-radius: 8px;
        margin-top: 10px;
    }
    .insight-pill span { color: #0369a1; font-size: 0.85rem; }
    .stat-block { margin-bottom: 10px; }
    .stat-label {
        font-size: 0.75rem;
        color: #6b7280;
        text-transform: uppercase;
    }
    .stat-value-blue { font-size: 1.5rem; font-weight: 700; color: #0066FF; }
    .stat-value-dark { font-size: 1.5rem; font-weight: 700; color: #1f2937; }
    .viral-track {
        background: #e5e7eb;
        border-radius: 6px;
        height: 8px;
        margin-top: 4px;
        overflow: hidden;
    }
    .viral-fill {
        background: linear-gradient(90deg, #0066FF, #4d94ff);
        height: 100%;
        animation: progressFill 1.5s ease-out;
    }
    .deezer-link {
        color: #0066FF;
        text-decoration: none;
        font-weight: 600;
    }

    /* ================= COMPONENTES PREMIUM ================= */

    /* Spinner de carga */
    .loading-spinner {
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 40px;
    }

    .spinner {
        width: 50px;
        height: 50px;
        border: 4px solid #f0f2f6;
        border-top: 4px solid #0066FF;
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

    /* Skeleton loader (efecto tipo Facebook/LinkedIn) */
    .skeleton {
        background: linear-gradient(90deg, #f0f2f6 25%, #e8ecf1 50%, #f0f2f6 75%);
        background-size: 200% 100%;
        animation: shimmer 1.5s infinite;
        border-radius: 8px;
        height: 20px;
        margin: 10px 0;
    }

    .skeleton-circle {
        width: 100px;
        height: 100px;
        border-radius: 50%;
        background: linear-gradient(90deg, #f0f2f6 25%, #e8ecf1 50%, #f0f2f6 75%);
        background-size: 200% 100%;
        animation: shimmer 1.5s infinite;
    }

    @keyframes shimmer {
        0% { background-position: 200% 0; }
        100% { background-position: -200% 0; }
    }

    /* Barra de progreso animada */
    .progress-bar-container {
        background: #f0f2f6;
        border-radius: 10px;
        padding: 4px;
        box-shadow:
            inset 2px 2px 4px #d1d5db,
            inset -2px -2px 4px #ffffff;
        margin: 10px 0;
    }

    .progress-bar {
        background: linear-gradient(90deg, #0066FF, #0080FF);
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
            rgba(255,255,255,0) 0%,
            rgba(255,255,255,0.1) 50%,
            rgba(255,255,255,0) 100%
        );
        transform: rotate(45deg);
        animation: shine 3s infinite;
        pointer-events: none;
    }

    @keyframes shine {
        0% { transform: translateX(-100%) translateY(-100%) rotate(45deg); }
        100% { transform: translateX(100%) translateY(100%) rotate(45deg); }
    }

    /* Scrollbar personalizada */
    ::-webkit-scrollbar {
        width: 10px;
    }

    ::-webkit-scrollbar-track {
        background: #f0f2f6;
        border-radius: 10px;
    }

    ::-webkit-scrollbar-thumb {
        background: linear-gradient(180deg, #0066FF, #0052CC);
        border-radius: 10px;
    }

    ::-webkit-scrollbar-thumb:hover {
        background: linear-gradient(180deg, #0080FF, #0066FF);
    }

    /* ==========================================
       MICRO-INTERACCIONES AVANZADAS
       ========================================== */

    /* 1. EFECTO RIPPLE EN BOTONES (onda al hacer clic) */
    .stButton > button {
        position: relative;
        overflow: hidden;
        transform: translateZ(0); /* acelera el render en GPU */
    }

    .stButton > button::after {
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

    .stButton > button:active::after {
        width: 400px;
        height: 400px;
        opacity: 1;
        transition: 0s; /* aparece instantáneo al presionar */
    }

    /* 2. TRANSICIÓN DE PÁGINA (fade & scale al cargar).
       Combinada con gradientShift en UNA declaración: dos reglas .stApp
       con animation distinta se pisan entre sí (la última gana) y matarían
       el gradiente animado. */
    .stApp {
        animation:
            pageTransition 0.8s cubic-bezier(0.4, 0, 0.2, 1),
            gradientShift 15s ease infinite;
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

    /* 3. STAGGER EFFECT: entrada con rebote (overshoot) para las cards de
       artista. El delay real se aplica INLINE por card (Streamlit no
       conserva contenedores entre st.markdown, así que nth-child no
       staggeriza: cada card es hija única de su wrapper) */
    .neumorphic-card.artist-card {
        opacity: 0;
        transform: translateY(40px);
        animation: staggerSlideIn 0.7s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
    }

    @keyframes staggerSlideIn {
        0% {
            opacity: 0;
            transform: translateY(40px) scale(0.95);
        }
        100% {
            opacity: 1;
            transform: translateY(0) scale(1);
        }
    }

    /* 4. Accesibilidad: sin movimiento para quien lo pide al sistema.
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

    /* 5. Compatibilidad Streamlit ≥1.64: los botones ya no usan .stButton
       (ahora [data-testid="stBaseButton-*"]); replicamos el estilo premium
       completo (gradiente + shimmer + ripple) en el selector actual */
    [data-testid="stBaseButton-secondary"] {
        position: relative;
        overflow: hidden;
        transform: translateZ(0);
        background: linear-gradient(145deg, #0066FF, #0052CC);
        color: white;
        border: none;
        border-radius: 12px;
        padding: 12px 24px;
        font-weight: 600;
        box-shadow:
            4px 4px 8px #d1d5db,
            -4px -4px 8px #ffffff;
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    }

    [data-testid="stBaseButton-secondary"]::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent);
        transition: left 0.6s ease;
    }

    [data-testid="stBaseButton-secondary"]:hover::before { left: 100%; }

    [data-testid="stBaseButton-secondary"]:hover {
        transform: translateY(-3px);
        box-shadow:
            8px 8px 16px #d1d5db,
            -8px -8px 16px #ffffff,
            0 0 20px rgba(0, 102, 255, 0.4);
    }

    [data-testid="stBaseButton-secondary"]:active {
        transform: translateY(0);
        box-shadow:
            inset 3px 3px 6px #004099,
            inset -3px -3px 6px #0080FF;
    }

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
        pointer-events: none;
    }

    [data-testid="stBaseButton-secondary"]:active::after {
        width: 400px;
        height: 400px;
        opacity: 1;
        transition: 0s;
    }
    </style>
    """
    st.markdown(custom_css, unsafe_allow_html=True)


def display_kpi_grid(kpis):
    """Fase 2: KPIs neumórficos. Compone las cards en UN solo bloque HTML
    (varios st.markdown romperían el <div class="kpi-container">: Streamlit
    envuelve cada st.markdown en su propio div del DOM)."""
    cards = "".join(
        f'<div class="kpi-card"><div class="kpi-label">{icon} {label}</div>'
        f'<div class="kpi-value">{value}</div></div>'
        for label, value, icon in kpis
    )
    st.markdown(
        f'<div class="kpi-container">{cards}</div>', unsafe_allow_html=True
    )


def artist_card_html(row, photo_data_uri=None, index=0):
    """Fase 2: card de artista neumórfica. Conserva las features del tablero
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
                <p style="text-align: center; color: #6b7280; margin-top: 15px; font-weight: 500;">
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
    """Barra de progreso neumórfica animada (progressFill desde 0%)."""
    percentage = (value / max_value) * 100
    st.markdown(
        f"""
        <div style="margin: 15px 0;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                <span style="font-size: 0.85rem; color: #6b7280; font-weight: 500;">{label}</span>
                <span style="font-size: 0.85rem; color: #0066FF; font-weight: 600;">{percentage:.1f}%</span>
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


def dark_neumorphism_css():
    """Paleta Neumorphism oscura: misma estructura visual, sombras y brillos
    recalculados para superficie #111827. Se inyecta DESPUÉS del CSS claro,
    así sus reglas ganan por orden de cascada sin necesidad de !important."""
    return """
    <style>
    /* ================= DARK NEUMORPHISM ================= */
    .stApp {
        background: linear-gradient(135deg, #111827 0%, #0b101b 100%);
        color: #e5e7eb;
    }

    .neumorphic-card {
        background: #111827;
        box-shadow:
            8px 8px 16px #05070c,
            -8px -8px 16px #1f2a3d;
    }
    .neumorphic-card:hover {
        box-shadow:
            12px 12px 24px #05070c,
            -12px -12px 24px #24314a;
    }

    .kpi-card {
        background: linear-gradient(145deg, #182236, #111827);
        box-shadow:
            5px 5px 10px #05070c,
            -5px -5px 10px #1f2a3d;
    }
    .kpi-card:hover {
        box-shadow:
            8px 8px 16px #05070c,
            -8px -8px 16px #24314a;
    }
    .kpi-value {
        color: #6ba3ff;
        text-shadow: 0 0 12px rgba(107, 163, 255, 0.35);
    }
    .kpi-label { color: #9ca3af; }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #131a29 0%, #0e1420 100%);
        box-shadow: 4px 0 10px rgba(0,0,0,0.4);
    }

    [data-testid="stMetric"] {
        background: linear-gradient(145deg, #182236, #111827);
        box-shadow:
            4px 4px 8px #05070c,
            -4px -4px 8px #1f2a3d;
    }

    .stButton > button {
        background: linear-gradient(145deg, #0066FF, #0052CC);
        box-shadow:
            4px 4px 8px #05070c,
            -4px -4px 8px #1f2a3d;
    }
    .stButton > button:hover {
        box-shadow:
            6px 6px 12px #05070c,
            -6px -6px 12px #24314a;
    }

    /* Compatibilidad 1.64: botón real en el tema oscuro */
    [data-testid="stBaseButton-secondary"] {
        background: linear-gradient(145deg, #0066FF, #0052CC);
        box-shadow:
            4px 4px 8px #05070c,
            -4px -4px 8px #1f2a3d;
    }
    [data-testid="stBaseButton-secondary"]:hover {
        box-shadow:
            6px 6px 12px #05070c,
            -6px -6px 12px #24314a,
            0 0 20px rgba(0, 102, 255, 0.4);
    }

    .stTextInput > div > div > input,
    .stSelectbox > div > div > select {
        background: #111827;
        color: #e5e7eb;
        box-shadow:
            inset 2px 2px 4px #05070c,
            inset -2px -2px 4px #1f2a3d;
    }

    h1, h2, h3 { color: #f3f4f6; }
    p, li, span { color: #d1d5db; }

    /* Internos de la card de artista en oscuro */
    .artist-name { color: #f3f4f6; }
    .artist-meta { color: #9ca3af; }
    .score-value { color: #6ba3ff; }
    .artist-track { color: #cbd5e1; }
    .insight-pill {
        background: rgba(0, 102, 255, 0.12);
    }
    .insight-pill span { color: #93c5fd; }
    .stat-label { color: #9ca3af; }
    .stat-value-blue { color: #6ba3ff; }
    .stat-value-dark { color: #f3f4f6; }
    .viral-track { background: #1f2a3d; }
    .viral-fill { background: linear-gradient(90deg, #0066FF, #6ba3ff); }
    .deezer-link { color: #6ba3ff; }

    .artist-photo {
        box-shadow:
            4px 4px 8px #05070c,
            -4px -4px 8px #1f2a3d;
    }

    /* Componentes premium en oscuro */
    .spinner {
        border-color: #1f2a3d;
        border-top-color: #6ba3ff;
        box-shadow:
            0 0 10px rgba(107, 163, 255, 0.3),
            inset 0 0 10px rgba(107, 163, 255, 0.1);
    }
    .loading-spinner p { color: #9ca3af !important; }
    .skeleton,
    .skeleton-circle {
        background: linear-gradient(90deg, #182236 25%, #1f2a3d 50%, #182236 75%);
        background-size: 200% 100%;
    }
    .progress-bar-container {
        background: #111827;
        box-shadow:
            inset 2px 2px 4px #05070c,
            inset -2px -2px 4px #1f2a3d;
    }

    hr { border-color: #1f2a3d; }

    /* Widgets nativos: el contenedor de chips del multiselect toma el
       secondaryBackgroundColor del tema global mediante clases emotion
       (hashes inestables entre versiones, sin atributos baseweb en 1.64).
       Transparencia estructural: el gradiente oscuro del sidebar se ve a
       través, y los chips azules (spans) conservan su acento. */
    header[data-testid="stHeader"] { background: transparent; }
    [data-testid="stSidebar"] [data-testid="stMultiSelect"] div {
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }
    [data-testid="stSidebar"] [data-testid="stMultiSelect"] input {
        color: #e5e7eb !important;
    }
    [data-testid="stSidebar"] [data-testid="stSlider"] {
        color: #9ca3af;
    }
    </style>
    """


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


# ── Tema claro/oscuro (Neumorphism) ─────────────────────────────────────
# La preferencia vive en st.session_state: persiste durante la sesión y el
# toggle la cambia al instante (re-render con la hoja oscura inyectada).
if "tema_oscuro" not in st.session_state:
    st.session_state.tema_oscuro = False

st.sidebar.toggle("🌙 Modo oscuro", key="tema_oscuro")
if st.session_state.tema_oscuro:
    st.markdown(dark_neumorphism_css(), unsafe_allow_html=True)

st.sidebar.header("🗂️ Vistas")
vista_tab = st.sidebar.radio(
    "Selecciona la vista:",
    options=["🎯 Scouting", "🔮 Forecasting 6M"],
    label_visibility="collapsed",
)

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

# Sidebar - Filtros (literales con emoji: en el pegado del tutorial se perdieron)
st.sidebar.header("🎛️ Filtros de Búsqueda")
recommendation_filter = st.sidebar.multiselect(
    "Recomendación A&R",
    options=sorted(df["ar_recommendation"].unique()),
    default=["🔥 FIRMAR AHORA", "👀 OBSERVAR"],
)

min_score = st.sidebar.slider("Scouting Score Mínimo", 0, 100, 0)

# Filtrar datos
df_filtered = df[
    (df["ar_recommendation"].isin(recommendation_filter))
    & (df["scouting_score"] >= min_score)
].sort_values("scouting_score", ascending=False)

# KPIs con estilo Neumorphism (Fase 2)
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
# neumórficas (y fallback local si la CDN falla).
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
    '<rect width="100" height="100" fill="#e5e7eb"/>'
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

# Tabla completa exportable
st.subheader("📋 Base de Datos Completa")
st.dataframe(
    df_filtered[
        [
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
    ].rename(
        columns={
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
    ),
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
