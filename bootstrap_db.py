#!/usr/bin/env python3
# ============================================================================
# bootstrap_db.py
# A&R Scouting Command Center | Auto-inicialización del warehouse DuckDB
#
# Ingeniería auto-reparable: si la app arranca en un servidor limpio
# (Render, contenedor nuevo, máquina nueva) y no encuentra el warehouse,
# lo reconstruye en segundos desde el seed versionado en el repo
# (ar_dbt_project/seeds/deezer_artists_data.csv), replicando EXACTAMENTE la
# misma lógica de scoring del mart dbt `artist_scouting_deezer` (50/30/20).
#
# Resolución de la ruta del warehouse (primera que aplique):
#   1. MUSIC_AR_DB_PATH (variable de entorno) — override explícito
#   2. Ruta canónica del equipo (Desktop/BASES DE DATOS DE PRUEBAS) si existe
#   3. Fallback portable: <raíz del repo>/music_ar_product.duckdb (la nube)
#
# Sin dependencia de Streamlit: módulo importable y testeable por CLI.
# ============================================================================

import os

import duckdb

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SEED = os.path.join(
    REPO_ROOT, "ar_dbt_project", "seeds", "deezer_artists_data.csv"
)

# Convención de rutas del equipo (solo existe en la máquina local)
_CANONICAL_DIR = r"C:\Users\LENOVO\Desktop\BASES DE DATOS DE PRUEBAS"
_CANONICAL_DB = os.path.join(_CANONICAL_DIR, "music_ar_product.duckdb")


def resolve_db_path():
    """Devuelve la ruta del warehouse según el entorno (local o nube)."""
    override = os.environ.get("MUSIC_AR_DB_PATH")
    if override:
        return override
    if os.path.isdir(_CANONICAL_DIR):
        return _CANONICAL_DB
    # Servidor limpio (Render): raíz del repo, siempre escribible
    return os.path.join(REPO_ROOT, "music_ar_product.duckdb")


def _scored_table_sql(csv_path):
    """CREATE TABLE artist_scouting_deezer: misma lógica que el mart dbt."""
    return f"""
        CREATE TABLE artist_scouting_deezer AS
        WITH src AS (
            SELECT * FROM read_csv_auto('{csv_path}')
        ),
        cleaned AS (
            SELECT
                *,
                CASE
                    WHEN deezer_rank < 0 THEN 0
                    WHEN deezer_rank > 1000000 THEN 1000000
                    ELSE deezer_rank
                END AS valid_rank,
                CASE WHEN deezer_fans < 0 THEN 0 ELSE deezer_fans END AS valid_fans
            FROM src
            WHERE artist_name IS NOT NULL AND deezer_fans > 0
        ),
        metrics AS (
            SELECT
                *,
                ROUND(valid_fans * 1.0 / NULLIF(valid_rank, 0), 4) AS fan_rank_ratio,
                ROUND(valid_rank * 1.0 / 1000000, 4) AS norm_rank,
                ROUND(valid_fans * 1.0 / (SELECT MAX(valid_fans) FROM cleaned), 4) AS norm_fans,
                ROUND(top_track_rank * 1.0 / (SELECT MAX(top_track_rank) FROM cleaned), 4) AS norm_track_rank
            FROM cleaned
        )
        SELECT
            artist_name, artist_id, picture_url, deezer_link,
            deezer_fans, deezer_rank, top_track_name, top_track_rank,
            top_track_duration, fan_rank_ratio,
            ROUND(
                (
                    (COALESCE(norm_rank, 0) * 0.50)
                    + (COALESCE(norm_fans, 0) * 0.30)
                    + (COALESCE(norm_track_rank, 0) * 0.20)
                ) * 100,
                2
            ) AS scouting_score,
            CASE
                WHEN (COALESCE(norm_rank, 0) * 0.50 + COALESCE(norm_fans, 0) * 0.30 + COALESCE(norm_track_rank, 0) * 0.20) * 100 >= 75 THEN '🔥 FIRMAR AHORA'
                WHEN (COALESCE(norm_rank, 0) * 0.50 + COALESCE(norm_fans, 0) * 0.30 + COALESCE(norm_track_rank, 0) * 0.20) * 100 >= 40 THEN '👀 OBSERVAR'
                ELSE '⚠️ DESCARTAR'
            END AS ar_recommendation,
            CASE
                WHEN deezer_rank > 500000 AND deezer_fans > 100000 THEN 'Alto Rank + Base de Fans sólida = Éxito consolidado'
                WHEN deezer_rank > 300000 AND top_track_rank > 400000 THEN 'Crecimiento orgánico detectado, monitorear de cerca'
                WHEN fan_rank_ratio > 0.5 THEN 'Excelente conversión de oyentes a fans'
                ELSE 'Datos insuficientes o nicho muy específico'
            END AS strategic_insight
        FROM metrics
        ORDER BY scouting_score DESC
    """


# Conexiones vivas por archivo (una por proceso). DuckDB rechaza abrir el
# mismo archivo con configuraciones distintas en un mismo proceso
# (read_only vs read-write): por eso app y reparaciones comparten UNA única
# conexión read-write cacheada — el conflicto de configuración no puede ocurrir.
_CONN_CACHE = {}


def get_connection(db_path=None):
    """Devuelve la conexión read-write cacheada del proceso para ese archivo."""
    db_path = db_path or resolve_db_path()
    con = _CONN_CACHE.get(db_path)
    if con is not None:
        try:
            con.execute("SELECT 1")
            return con
        except duckdb.Error:
            # Conexión muerta (p. ej. cerrada por código heredado): renovar.
            _CONN_CACHE.pop(db_path, None)
    con = duckdb.connect(db_path)
    _CONN_CACHE[db_path] = con
    return con


def ensure_table(db_path=None, seed_path=DEFAULT_SEED):
    """
    Segunda capa de auto-reparación: si el archivo existe pero la tabla
    scored no (warehouse parcial/anticuado), la crea desde el seed.
    Devuelve True si creó la tabla, False si ya estaba.
    """
    db_path = db_path or resolve_db_path()
    con = get_connection(db_path)
    exists = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_name = 'artist_scouting_deezer'"
    ).fetchone()[0]
    created = not exists
    if created:
        con.execute(_scored_table_sql(seed_path))
    return created


def ensure_database(db_path=None, seed_path=DEFAULT_SEED):
    """
    Crea el warehouse desde el seed si no existe. Idempotente:
    devuelve True si lo creó, False si ya existía.
    """
    db_path = db_path or resolve_db_path()
    if os.path.exists(db_path):
        return False
    if not os.path.exists(seed_path):
        raise FileNotFoundError(
            f"No se encontró el seed en {seed_path}. "
            "Ejecuta el extractor (python deezer_data_extractor.py) o "
            "verifica que el repo esté completo."
        )
    con = get_connection(db_path)
    con.execute(_scored_table_sql(seed_path))
    return True


if __name__ == "__main__":
    # CLI de verificación: python bootstrap_db.py
    target = resolve_db_path()
    created = ensure_database(target)
    print(f"warehouse: {target}")
    print("creado ahora" if created else "ya existía (nada por hacer)")
    con = get_connection(target)
    n = con.execute("SELECT COUNT(*) FROM artist_scouting_deezer").fetchone()[0]
    top = con.execute(
        "SELECT artist_name, scouting_score, ar_recommendation "
        "FROM artist_scouting_deezer ORDER BY scouting_score DESC LIMIT 1"
    ).fetchone()
    con.close()
    print(f"artist_scouting_deezer: {n} artistas | top: {top[0]} ({top[1]}) {top[2]}")
