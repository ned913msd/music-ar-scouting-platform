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

    /* Fondo principal con gradiente sutil */
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #e8ecf1 100%);
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
        transition: all 0.3s ease;
        animation: slideIn 0.5s ease-out;
    }

    .neumorphic-card:hover {
        box-shadow:
            12px 12px 24px #d1d5db,
            -12px -12px 24px #ffffff;
        transform: translateY(-2px);
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
        transition: all 0.3s ease;
    }

    .kpi-card:hover {
        transform: translateY(-3px);
        box-shadow:
            8px 8px 16px #d1d5db,
            -8px -8px 16px #ffffff;
    }

    .kpi-value {
        font-size: 2.5rem;
        font-weight: 700;
        color: #0066FF;
        margin: 10px 0;
        text-shadow: 0 0 10px rgba(0, 102, 255, 0.3);
    }

    .kpi-label {
        font-size: 0.9rem;
        color: #6b7280;
        text-transform: uppercase;
        letter-spacing: 1px;
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
        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent);
        transition: left 0.5s;
    }

    .stButton > button:hover::before {
        left: 100%;
    }

    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow:
            6px 6px 12px #d1d5db,
            -6px -6px 12px #ffffff;
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
        border: none;
        transition: all 0.3s ease;
    }

    .stTextInput > div > div > input:focus,
    .stSelectbox > div > div > select:focus {
        box-shadow:
            inset 3px 3px 6px #d1d5db,
            inset -3px -3px 6px #ffffff,
            0 0 0 2px #0066FF;
    }

    /* Sidebar con gradiente y sombra (selector estable entre versiones) */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f5f7fa 0%, #e8ecf1 100%);
        box-shadow: 4px 0 10px rgba(0,0,0,0.05);
    }

    /* Títulos con brillo sutil */
    h1, h2, h3 {
        color: #1f2937;
        font-weight: 700;
        text-shadow: 0 0 20px rgba(0, 102, 255, 0.1);
    }

    /* Métricas nativas con card suave */
    [data-testid="stMetric"] {
        background: linear-gradient(145deg, #ffffff, #f0f2f6);
        border-radius: 12px;
        padding: 15px;
        box-shadow:
            4px 4px 8px #d1d5db,
            -4px -4px 8px #ffffff;
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


def artist_card_html(row, photo_data_uri=None):
    """Fase 2: card de artista neumórfica. Conserva las features del tablero
    anterior que el HTML plano del tutorial descartaba: Probabilidad de
    Viralidad (ML) con barra, y fallback de foto si la CDN falla."""
    fans = f"{int(row['deezer_fans']):,}"
    rank = f"{int(row['deezer_rank']):,}"
    viral = f"{row['probabilidad_viral']:.1f}"
    viral_pct = min(row["probabilidad_viral"] / 100.0, 1.0) * 100
    if photo_data_uri is None:
        photo = f'<img class="artist-photo" src="{row["picture_url"]}" alt="{row["artist_name"]}">'
    else:
        photo = f'<img class="artist-photo" src="{photo_data_uri}" alt="{row["artist_name"]}">'
    return f"""
    <div class="neumorphic-card">
        <div style="display: grid; grid-template-columns: 100px 1fr 220px; gap: 20px; align-items: center;">
            <div>{photo}</div>
            <div>
                <h3 style="margin: 0; color: #1f2937;">{row['artist_name']}</h3>
                <p style="margin: 5px 0; color: #6b7280; font-size: 0.9rem;">
                    {row['ar_recommendation']} | Score: <strong style="color: #0066FF;">{row['scouting_score']:.0f}/100</strong>
                </p>
                <p style="margin: 5px 0; color: #4b5563; font-size: 0.85rem;">
                    🎵 Top Track: {row['top_track_name']}
                </p>
                <div style="background: #e0f2fe; padding: 8px 12px; border-radius: 8px; margin-top: 10px;">
                    <span style="color: #0369a1; font-size: 0.85rem;">💡 {row['strategic_insight']}</span>
                </div>
            </div>
            <div style="text-align: right;">
                <div style="margin-bottom: 10px;">
                    <div style="font-size: 0.75rem; color: #6b7280; text-transform: uppercase;">Prob. Viralidad 6M</div>
                    <div style="font-size: 1.5rem; font-weight: 700; color: #0066FF;">{viral}%</div>
                    <div style="background: #e5e7eb; border-radius: 6px; height: 8px; margin-top: 4px; overflow: hidden;">
                        <div style="background: linear-gradient(90deg, #0066FF, #4d94ff); width: {viral_pct:.0f}%; height: 100%;"></div>
                    </div>
                </div>
                <div style="margin-bottom: 10px;">
                    <div style="font-size: 0.75rem; color: #6b7280; text-transform: uppercase;">Fans Deezer</div>
                    <div style="font-size: 1.5rem; font-weight: 700; color: #0066FF;">{fans}</div>
                </div>
                <div style="margin-bottom: 10px;">
                    <div style="font-size: 0.75rem; color: #6b7280; text-transform: uppercase;">Deezer Rank</div>
                    <div style="font-size: 1.5rem; font-weight: 700; color: #1f2937;">{rank}</div>
                </div>
                <a href="{row['deezer_link']}" target="_blank" style="color: #0066FF; text-decoration: none; font-weight: 600;">
                    🔗 Ver en Deezer
                </a>
            </div>
        </div>
    </div>
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


modelo_ml, feature_names = cargar_modelo_ml()

st.title("🎵 A&R Scouting Command Center")
st.markdown(
    "**Data Product con datos REALES de Deezer API para identificación de talento musical**"
)

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
    options=["🎯 Scouting", "🔮 Forecasting 6M"],
    label_visibility="collapsed",
)

# ==========================================
# VISTA 2: FORECASTING — despachada ANTES del contenido de Scouting para que
# cada vista sea una página independiente (antes el forecast se apilaba
# debajo de toda la página de Scouting)
# ==========================================
if vista_tab == "🔮 Forecasting 6M":
    try:
        fc = cargar_forecast()
    except Exception as e:
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

for idx, row in top_10.iterrows():
    # Foto cacheada convertida a data URI: un solo request por URL, y el HTML
    # no depende de que la CDN responda (fallback a imagen placeholder)
    try:
        foto_uri = cargar_foto_uri(row.loc["picture_url"])
    except Exception:
        foto_uri = None
    st.markdown(
        artist_card_html(row, photo_data_uri=foto_uri), unsafe_allow_html=True
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
