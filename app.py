# -*- coding: utf-8 -*-
"""
A&R Scouting Command Center — Dashboard del Director de A&R
Ejecutar:  streamlit run app.py
"""
import os

import duckdb
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="A&R Scouting Dashboard",
    page_icon="🎵",
    layout="wide",
)

st.title("🎵 A&R Scouting Command Center")
st.markdown("**Data Product para identificación de talento musical con potencial de firma**")

# ----------------------------------------------------------------------------
# Conexión a DuckDB: ruta canónica del equipo (BASES DE DATOS DE PRUEBAS),
# portable vía MUSIC_AR_DB_PATH. read_only para no bloquear dbt mientras
# el dashboard está abierto.
# ----------------------------------------------------------------------------
DB_PATH = os.environ.get(
    "MUSIC_AR_DB_PATH",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "BASES DE DATOS DE PRUEBAS",
        "music_ar_product.duckdb",
    ),
)


@st.cache_data(ttl=60)
def load_data() -> pd.DataFrame:
    if not os.path.exists(DB_PATH):
        st.error(f"No se encontró la base de datos:\n`{DB_PATH}`\n\n"
                 "Ejecuta primero `pipeline/ar_scouting_pipeline.py` y `dbt run`.")
        st.stop()
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        return con.execute("SELECT * FROM artist_scouting_ranking").df()
    finally:
        con.close()


df = load_data()

# Sidebar - Filtros
st.sidebar.header("🎛️ Filtros de Búsqueda")
genre_filter = st.sidebar.multiselect(
    "Género Musical",
    options=df['genre'].unique(),
    default=df['genre'].unique()
)

recommendation_filter = st.sidebar.multiselect(
    "Recomendación A&R",
    options=df['ar_recommendation'].unique(),
    default=['🔥 FIRMAR AHORA', '👀 OBSERVAR']
)

# Filtrar datos
df_filtered = df[
    (df['genre'].isin(genre_filter)) &
    (df['ar_recommendation'].isin(recommendation_filter))
]

# KPIs Principales
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Artistas Analizados", len(df_filtered))
# Nota: el literal debe incluir el emoji 🔥 — coincide con los valores de ar_recommendation
col2.metric("🔥 Firmar Ahora", len(df_filtered[df_filtered['ar_recommendation'] == '🔥 FIRMAR AHORA']))
col3.metric("Scouting Score Promedio", f"{df_filtered['scouting_score'].mean():.1f}")
col4.metric("Save Rate Promedio", f"{df_filtered['save_rate_percentage'].mean():.1f}%")

st.divider()

# Top Artists
st.subheader("🏆 Top 10 Artistas Prioritarios")
top_10 = df_filtered.nlargest(10, 'scouting_score')

for idx, row in top_10.iterrows():
    with st.container():
        col1, col2, col3 = st.columns([3, 2, 2])
        col1.markdown(f"**{row['artist_name']}**")
        col1.caption(f"{row['genre']} | {row['ar_recommendation']}")
        col2.metric("Scouting Score", f"{row['scouting_score']:.0f}/100")
        col3.metric("Monthly Listeners", f"{row['spotify_monthly_listeners']:,}")
        st.caption(f"💡 {row['strategic_insight']}")
        st.divider()

# Tabla completa
st.subheader("📋 Base de Datos Completa")
st.dataframe(
    df_filtered[[
        'artist_name', 'genre', 'scouting_score', 'ar_recommendation',
        'save_rate_percentage', 'skip_rate_percentage', 'growth_rate_percentage',
        'spotify_monthly_listeners', 'tiktok_total_views', 'strategic_insight'
    ]].sort_values('scouting_score', ascending=False),
    use_container_width=True,
    hide_index=True
)

# Exportar datos
st.sidebar.divider()
st.sidebar.subheader("📤 Exportar Datos")
csv = df_filtered.to_csv(index=False).encode('utf-8')
st.sidebar.download_button(
    label="Descargar CSV",
    data=csv,
    file_name='ar_scouting_report.csv',
    mime='text/csv'
)
