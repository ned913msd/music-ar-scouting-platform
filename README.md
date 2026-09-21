# 🎵 Music A&R Data Product

Data product que prioriza artistas emergentes para un sello discográfico: extrae métricas de
Spotify y TikTok (simulación estilo Chartmetric/Soundcharts), calcula un **Scouting Score (0–100)**
con lógica de negocio A&R y expone un mart consultable para el Director de A&R.

**Stack:** Python (pandas/duckdb) → DuckDB → dbt → Streamlit (dashboard del Director de A&R).

## Arquitectura (patrón ELT)

```
API simulada ──► pipeline/ar_scouting_pipeline.py ──► DuckDB (raw_artists_data, 50 artistas crudos)
                                                          │
                                                          ▼
                              ar_dbt_project (dbt-duckdb): staging → marts
                              • stg_artists          (tipado y limpieza de nombres)
                              • artist_scouting      (Data Quality + Scouting Score + clasificación)
```

La lógica de negocio (score y clasificación) vive en **dbt**, no en el script: así es auditable,
versionada y testeable. El script solo extrae y carga (E y L de ELT).

## Lógica de negocio

| Métrica | Peso | Por qué |
|---|---|---|
| Spotify Save Rate | 40% | Si un usuario guarda la canción, el algoritmo la empuja a Discover Weekly. La métrica reina. |
| Crecimiento 30d | 30% | Momento del artista (TikTok → Spotify). |
| Spotify Skip Rate (invertida) | 30% | Salto alto = la audiencia rechaza el track. |

Clasificación (`ar_recommendation`):
🔥 FIRMAR AHORA (score ≥ 75) · 👀 OBSERVAR (40–75) · ⚠️ DESCARTAR (< 40)

**Modelo oficial:** `artist_scouting_ranking` — corrige outliers (skip_rate > 1.0 se acota a 1.0
en vez de descartar la fila), añade KPIs de negocio (follower/listener ratio, vistas promedio
por video en TikTok) y un `strategic_insight` accionable por artista.

## Estructura

```
music-ar-data-product/
├── pipeline/
│   └── ar_scouting_pipeline.py     # Extract + Load a DuckDB (50 artistas crudos)
├── ar_dbt_project/
│   ├── dbt_project.yml
│   ├── profiles.yml                # Conexión duckdb (ruta por env_var con default)
│   ├── packages.yml                # dbt_utils (test accepted_range)
│   └── models/
│       ├── staging/
│       │   ├── sources.yml
│       │   └── stg_artists.sql
│       └── marts/
│           ├── artist_scouting.sql          # Fase 1: réplica del prototipo pandas
│           ├── artist_scouting_ranking.sql  # Ranking oficial + insights estratégicos
│           └── schema.yml                   # 16 tests de calidad de datos musicales
├── app.py                          # 🎛️ Dashboard Streamlit del Director de A&R
├── requirements.txt
├── setup.sh
└── README.md
```

## Quickstart

```bash
bash setup.sh                                # venv con dbt-duckdb + streamlit
source venv/Scripts/activate                 # (Windows / Git Bash)

python pipeline/ar_scouting_pipeline.py      # E+L: 50 artistas crudos → DuckDB
dbt deps --project-dir ar_dbt_project --profiles-dir ar_dbt_project  # dbt_utils
dbt run --project-dir ar_dbt_project --profiles-dir ar_dbt_project   # T: score en dbt
dbt test --project-dir ar_dbt_project --profiles-dir ar_dbt_project  # 16 tests de calidad

# Dashboard del Director de A&R (filtros, top 10, export CSV):
streamlit run app.py

# Consulta del Director de A&R:
duckdb "BASES DE DATOS DE PRUEBAS/music_ar_product.duckdb" -c \
  "SELECT artist_name, genre, scouting_score, ar_recommendation
   FROM artist_scouting WHERE ar_recommendation = '🔥 FIRMAR AHORA'
   ORDER BY scouting_score DESC"
```

## Convención de rutas (equipo)

- Los scripts viven en `Desktop\SCRIPTS PYTHON` (hay un symlink-free copy del pipeline ahí).
- Las bases de datos viven en `Desktop\BASES DE DATOS DE PRUEBAS` → `music_ar_product.duckdb`.
- Override en cualquier máquina: variable de entorno `MUSIC_AR_DB_PATH` o flag `--db`.
