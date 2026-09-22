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

# CSS personalizado para mejor visualización
st.markdown(
    """
<style>
    .metric-card {
        background-color: #1e1e1e;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #333;
    }
    .artist-card {
        background-color: #2a2a2a;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 15px;
        border-left: 4px solid #d4af37;
    }
</style>
""",
    unsafe_allow_html=True,
)

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

# KPIs Principales
col1, col2, col3, col4 = st.columns(4)
col1.metric("👥 Total Artistas Analizados", len(df_filtered))
col2.metric(
    "🔥 Firmar Ahora",
    len(df_filtered[df_filtered["ar_recommendation"] == "🔥 FIRMAR AHORA"]),
)
col3.metric("⭐ Scouting Score Promedio", f"{df_filtered['scouting_score'].mean():.1f}")
col4.metric("👥 Total Fans (Deezer)", f"{int(df_filtered['deezer_fans'].sum()):,}")

st.divider()

# Cache de fotos: un solo request por URL aunque Streamlit re-renderice
@st.cache_data(show_spinner=False, ttl=3600)
def cargar_foto(url):
    response = requests.get(url, timeout=5)
    response.raise_for_status()
    return Image.open(BytesIO(response.content)).convert("RGB")


# Top Artists con Fotos
st.subheader("🏆 Top 10 Artistas Prioritarios")

top_10 = df_filtered.head(10)

for idx, row in top_10.iterrows():
    col1, col2, col3 = st.columns([1, 3, 2])

    with col1:
        # Cargar la foto real del artista (fallback si la CDN falla)
        try:
            img = cargar_foto(row["picture_url"])
            st.image(img, width=100, caption=row["artist_name"][:15])
        except Exception:
            st.markdown("🖼️ *(foto no disponible)*")

    with col2:
        st.markdown(f"### {row['artist_name']}")
        st.caption(f"{row['ar_recommendation']} | Score: {row['scouting_score']:.0f}/100")
        st.markdown(f"**Top Track:** {row['top_track_name']}")
        st.info(f"💡 {row['strategic_insight']}")

    with col3:
        # Predicción ML: probabilidad de duplicar fans en 6 meses
        st.metric(
            "Probabilidad de Viralidad (6M)",
            f"{row['probabilidad_viral']:.1f}%",
        )
        st.progress(min(row["probabilidad_viral"] / 100, 1.0))
        st.metric("Fans Deezer", f"{int(row['deezer_fans']):,}")
        st.metric("Deezer Rank", f"{int(row['deezer_rank']):,}")
        st.metric("Track Rank", f"{int(row['top_track_rank']):,}")
        if row["deezer_link"]:
            st.markdown(f"[🔗 Ver en Deezer]({row['deezer_link']})")

    st.divider()

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

# ==========================================
# VISTA 2: FORECASTING (solo se renderiza al pedirla)
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

    c1, c2, c3 = st.columns(3)
    c1.metric("Fans hoy", f"{fc['fans_hoy']:,}")
    c2.metric("Crecimiento proyectado (6M)", f"+{fc['crecimiento_6m_pct']}%")
    c3.metric("CAGR anualizado", f"{fc['cagr_anualizado_pct']}%")

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

    # El resto de la página (tabla + export) no aplica en esta vista
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
    st.caption("Data Product desarrollado por David NED Bustamante | Music Data Analyst | CI/CD semanal + Forecasting")
    st.stop()

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
