"""
Script para enriquecer la base de datos con características de "ADN Básico" del
artista. Estas features servirán como variables predictoras (X) para el
modelo de supervivencia (Cox).

Versión 3 — SQL Avanzado en DuckDB (CTEs + funciones de ventana):
  * Toda la transformación vive en UNA query con CTEs legibles:
    src -> medias -> rank_imputado -> adn. Python solo recibe el DataFrame
    final y lo escribe con pandas (misma escritura de siempre).
  * rank = 0 se trata como "dato no reportado" (NULLIF) y se imputa con la
    MEDIAN() de los ranks válidos dentro de la propia query.
  * log1p() -> LN(1 + x): DuckDB 1.5.5 no expone LOG1P, y LN(1+x) es la
    misma función matemática (difiere en ~1 ULP, 1e-16, de numpy.log1p).
  * La cohorte se arma con LEFT JOIN + ROW_NUMBER() OVER () para conservar
    el orden de filas del CSV original (lo que garantiza diffs estables).

NOTA (importante): los robots del repo (`daily_update.py` y
`expand_database.py`) reescriben el seed con SOLO las columnas núcleo, así que
estas columnas desaparecen cada vez que corren. Por eso este script se ejecuta
en GitHub Actions justo después de `daily_update.py` y antes del snapshot.
Si corres los robots a mano, vuelve a correr este script después.
"""

import os
import sys

# Consolas Windows (cp1252) no imprimen emojis: forzar UTF-8 antes de todo
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import duckdb
import pandas as pd

from decoradores import medir_rendimiento

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Columnas que se fusionan también en la tabla de cohorte
ADN_COLS = [
    "ratio_fans_rank",
    "top_track_dominance",
    "es_solista",
    "nombre_corto",
    "genero_encoded",
]

# Orden final del bloque de features en el seed (determinista en cada corrida)
ADN_BLOCK = [
    "ratio_fans_rank_raw",
    "ratio_fans_rank",
    "top_track_dominance_raw",
    "top_track_dominance",
    "es_solista",
    "nombre_corto",
    "genero_encoded",
]

# Defaults de la cohorte cuando el artista no está en el seed
ADN_DEFAULTS = {
    "ratio_fans_rank": 0.0,
    "top_track_dominance": 0.0,
    "es_solista": 1,
    "nombre_corto": 0,
    "genero_encoded": 5,
}

# Mapeo de géneros a números (Label Encoding manual para control total).
# Claves en MINÚSCULAS: el seed guarda los géneros en minúscula ("urbano").
#   0 Urbano/Reggaetón/Trap · 1 Pop · 2 Guitarras/Indie/Folk ·
#   3 Electrónica · 4 Regional Mexicano · 5 Desconocido · 6 Salsa
GENERO_MAP = {
    "urbano": 0,
    "reggaeton": 0,
    "trap": 0,
    "trap latino": 0,
    "pop": 1,
    "pop latino": 1,
    "rock": 2,
    "rock latino": 2,
    "indie": 2,
    "folk": 2,
    "electrónica": 3,
    "electronica": 3,
    "house": 3,
    "techno": 3,
    "regional mexicano": 4,
    "banda": 4,
    "corridos": 4,
    "salsa": 6,  # Categoría explícita para salsa (no va a "Desconocido")
    "desconocido": 5,
}

# Heurística de "¿es solista?": mismo listado que la versión pandas.
SOLISTA_CLAVES = ["feat", "featuring", " y ", " & ", " the ", "los ", "las "]


def _sql_case_genero(col):
    """CASE WHEN equivalente al GENERO_MAP de pandas (ELSE 5 = Desconocido)."""
    whens = "\n".join(
        f"        WHEN '{clave}' THEN {valor}" for clave, valor in GENERO_MAP.items()
    )
    return f"""CASE LOWER(TRIM({col}))
{whens}
        ELSE 5
    END"""


def _sql_case_es_solista(col):
    """CONTAINS = substring-match exacto, lo mismo que `w in nombre` en pandas."""
    cond = " OR ".join(f"CONTAINS(LOWER({col}), '{w}')" for w in SOLISTA_CLAVES)
    return f"CASE WHEN {cond} THEN 0 ELSE 1 END"


def construir_query_adn(ruta_seed):
    """CTE chain que convierte el seed crudo en el seed con ADN Básico.

    medias      -> agregación con MEDIAN() para imputar ranks no reportados
    rank_imputado -> NULLIF + COALESCE (imputación) por fila
    adn         -> métricas (LN(1+x)) + heurísticas (CASE)
    """
    cols_seed = list(pd.read_csv(ruta_seed, nrows=0).columns)
    if "genero" not in cols_seed:
        cols_seed.append("genero")

    base_cols = [c for c in cols_seed if c not in ADN_BLOCK]
    proj_base = ",\n        ".join(base_cols)

    # Si el seed vino sin columna 'genero' (robots a medias), la inyectamos
    # en el primer CTE para que todos los CTEs siguientes la vean.
    if "genero" in pd.read_csv(ruta_seed, nrows=0).columns:
        inyectar_genero = ""
    else:
        inyectar_genero = " 'Desconocido' AS genero,"

    return f"""
    WITH src AS (
        -- ROW_NUMBER() OVER () fija el orden del CSV: sin esta ventana el
        -- orden de salida no está garantizado y git vería diffs de orden.
        SELECT *{inyectar_genero}, row_number() OVER () AS __orden
        FROM read_csv_auto(?)
    ),
    medias AS (
        -- Agregación: mediana de los ranks válidos (0 = no reportado -> NULL)
        SELECT
            MEDIAN(NULLIF(deezer_rank, 0))      AS mediana_rank,
            MEDIAN(NULLIF(top_track_rank, 0))   AS mediana_track
        FROM src
    ),
    rank_imputado AS (
        -- Imputación por fila: valor real si existe, si no la mediana
        SELECT
            s.*,
            COALESCE(NULLIF(s.deezer_rank, 0),    m.mediana_rank)   AS rank_imp,
            COALESCE(NULLIF(s.top_track_rank, 0), m.mediana_track)  AS track_imp
        FROM src s CROSS JOIN medias m
    ),
    adn AS (
        SELECT
            {proj_base},
            deezer_fans / NULLIF(rank_imp, 0) AS ratio_fans_rank_raw,
            LN(1 + deezer_fans / NULLIF(rank_imp, 0)) AS ratio_fans_rank,
            track_imp / NULLIF(rank_imp, 0) AS top_track_dominance_raw,
            LN(1 + track_imp / NULLIF(rank_imp, 0)) AS top_track_dominance,
            {_sql_case_es_solista('artist_name')} AS es_solista,
            CASE WHEN LENGTH(artist_name) < 12 THEN 1 ELSE 0 END AS nombre_corto,
            {_sql_case_genero('genero')} AS genero_encoded,
            __orden
        FROM rank_imputado
    )
    SELECT
        {", ".join(base_cols + ADN_BLOCK)}
    FROM adn
    ORDER BY __orden
    """


def construir_query_cohorte(ruta_seed, ruta_cohorte):
    """LEFT JOIN seed(ADN) x cohorte conservando el orden de filas del CSV.

    ROW_NUMBER() OVER () es la función de ventana que fija el orden original:
    sin ella DuckDB no garantiza el orden de un JOIN y el CSV de salida
    cambiaría de orden en cada corrida (diffs eternos en git).
    """
    cols_cohorte = list(pd.read_csv(ruta_cohorte, nrows=0).columns)
    # Proyección explícita de la cohorte: primero sus propias columnas (sin
    # las ADN, que se regeneran), luego las 5 ADN al final (mismo orden que
    # producía el merge de pandas). DuckDB no acepta `c.* EXCEPT(...)`.
    base_cohorte = [c for c in cols_cohorte if c not in ADN_COLS]
    proj_cohorte = ",\n            ".join(f"c.{c}" for c in base_cohorte)

    proj_adn = ",\n            ".join(
        f"COALESCE(a.{c}, {repr(ADN_DEFAULTS[c])}) AS {c}" for c in ADN_COLS
    )

    return f"""
    WITH adn AS (
        SELECT * FROM ({construir_query_adn(ruta_seed).strip()})
    ),
    cohorte AS (
        SELECT row_number() OVER () AS __orden, * FROM read_csv_auto(?)
    )
    SELECT
        {proj_cohorte},
            {proj_adn}
    FROM cohorte c
    LEFT JOIN adn a ON c.artist_name = a.artist_name
    ORDER BY c.__orden
    """


@medir_rendimiento
def extraer_adn_basico(ruta_seed=None, ruta_cohorte=None):
    """Regenera las features ADN en el seed y en la cohorte (v3: SQL)."""
    print("🧬 Iniciando extracción de ADN Básico (v3: SQL Avanzado en DuckDB)...")

    ruta_seed = ruta_seed or os.path.join(
        REPO_ROOT, "ar_dbt_project", "seeds", "deezer_artists_data.csv"
    )
    ruta_cohorte = ruta_cohorte or os.path.join(
        REPO_ROOT, "data", "cohort_table.csv"
    )

    if not os.path.exists(ruta_seed):
        print(f"❌ Error: No se encontró {ruta_seed}")
        return

    con = duckdb.connect()

    # ── 1. Seed con ADN: una sola query con CTEs ──
    df = con.execute(construir_query_adn(ruta_seed), [ruta_seed]).df()

    print("📏 Rangos después de LN(1+x):")
    print(
        f"   ratio_fans_rank: "
        f"[{df['ratio_fans_rank'].min():.2f}, {df['ratio_fans_rank'].max():.2f}]"
    )
    print(
        f"   top_track_dominance: "
        f"[{df['top_track_dominance'].min():.2f}, "
        f"{df['top_track_dominance'].max():.2f}]"
    )

    df.to_csv(ruta_seed, index=False, encoding="utf-8", lineterminator="\n")
    print(f"✅ ADN Básico v3 agregado a {ruta_seed}")

    # ── 2. Cohorte: LEFT JOIN con el ADN recién calculado ──
    if os.path.exists(ruta_cohorte):
        cohorte = con.execute(
            construir_query_cohorte(ruta_seed, ruta_cohorte), [ruta_seed, ruta_cohorte]
        ).df()
        cohorte = cohorte.astype(
            {
                "es_solista": "int64",
                "nombre_corto": "int64",
                "genero_encoded": "int64",
            }
        )
        cohorte.to_csv(
            ruta_cohorte, index=False, encoding="utf-8", lineterminator="\n"
        )
        print(f"✅ Tabla de cohorte actualizada en {ruta_cohorte}")

    con.close()
    print("🎉 ¡Fase 2 (ADN Básico v3 SQL) completada exitosamente!")


if __name__ == "__main__":
    extraer_adn_basico()
