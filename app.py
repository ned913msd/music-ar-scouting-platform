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

conn = duckdb.connect(AR_DB, read_only=True)

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

# Exportar datos
st.sidebar.divider()
st.sidebar.subheader("💾 Exportar Datos")
csv = df_filtered.to_csv(index=False).encode("utf-8")
st.sidebar.download_button(
    label="📥 Descargar CSV",
    data=csv,
    file_name="ar_scouting_deezer_report.csv",
    mime="text/csv",
)

conn.close()

# Footer
st.divider()
st.caption("Data Product desarrollado por David NED Bustamante | Music Data Analyst")
