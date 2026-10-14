"""
⏱️ Máquina del Tiempo: crecimiento semana a semana con SQL Avanzado.

Lee todos los CSV de data/snapshots/ con una query de DuckDB (CTEs +
funciones de ventana) y escribe data/crecimiento_semanal.csv, que el
dashboard usa para el panel "Máquina del Tiempo".

Conceptos aplicados:
  * LAG(deezer_fans) OVER (PARTITION BY artist_name ORDER BY snapshot_date)
    -> fans de la semana anterior para cada fila.
  * ROW_NUMBER() OVER (PARTITION BY ... ORDER BY snapshot_date DESC) = 1
    -> solo la fila más reciente de cada artista.
  * COUNT(*) OVER (PARTITION BY artist_name) -> tamaño del historial.
  * CTEs encadenadas (serie -> con_lag -> ultimo -> enriquecido) para que
    el pipeline se lea como una historia.
  * LEFT JOIN a la cohorte (registrada como vista) para país/género/ratio.
  * Generador iterar_snapshots(): los CSV se leen UNO A LA VEZ y solo las
    columnas que la query usa — el histórico completo nunca cabe entero en
    RAM (mañana, con 52 semanas × N artistas, la diferencia importa).

Con UN solo snapshot (línea base), fans_semana_anterior y crecimiento_pct
salen NULL: la comparación arranca el lunes siguiente, cuando exista un
snapshot anterior al actual.
"""

import glob
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
DIR_SNAPSHOTS = os.path.join(REPO_ROOT, "data", "snapshots")
RUTA_COHORTE = os.path.join(REPO_ROOT, "data", "cohort_table.csv")
RUTA_SALIDA = os.path.join(REPO_ROOT, "data", "crecimiento_semanal.csv")

COLUMNAS_SERIE = ["artist_name", "snapshot_date", "deezer_fans"]

COLUMNAS_SALIDA = [
    "artist_name",
    "genero",
    "pais_origen",
    "ratio_fans_rank",
    "snapshot_date",
    "deezer_fans",
    "fans_semana_anterior",
    "crecimiento_absoluto",
    "crecimiento_pct",
    "dias_desde_anterior",
    "snapshots_en_historial",
    "tendencia",
]

SQL_CRECIMIENTO = """
-- La vista `serie` la registra el caller: sale del generador
-- iterar_snapshots (un CSV por semana, solo las columnas necesarias).
WITH con_lag AS (
    -- Funciones de ventana sobre el histórico COMPLETO (antes de quedarnos
    -- con la fila más reciente): la semana anterior de CADA artista y el
    -- tamaño de su historial.
    SELECT
        artist_name,
        snapshot_date,
        deezer_fans,
        LAG(deezer_fans) OVER (
            PARTITION BY artist_name ORDER BY snapshot_date
        ) AS fans_semana_anterior,
        LAG(snapshot_date) OVER (
            PARTITION BY artist_name ORDER BY snapshot_date
        ) AS fecha_anterior,
        COUNT(*) OVER (PARTITION BY artist_name) AS snapshots_en_historial,
        ROW_NUMBER() OVER (
            PARTITION BY artist_name ORDER BY snapshot_date DESC
        ) AS rn_ultima
    FROM serie
),
ultimo AS (
    -- Solo el snapshot más reciente de cada artista (la fila "de hoy")
    SELECT *
    FROM con_lag
    WHERE rn_ultima = 1
)
SELECT
    u.artist_name,
    c.genero,
    c.pais_origen,
    c.ratio_fans_rank,
    u.snapshot_date,
    u.deezer_fans,
    u.fans_semana_anterior,
    u.deezer_fans - u.fans_semana_anterior AS crecimiento_absoluto,
    ROUND(
        100.0 * (u.deezer_fans - u.fans_semana_anterior)
        / NULLIF(u.fans_semana_anterior, 0), 2
    ) AS crecimiento_pct,
    DATE_DIFF('day', u.fecha_anterior, u.snapshot_date) AS dias_desde_anterior,
    u.snapshots_en_historial,
    CASE
        WHEN u.fans_semana_anterior IS NULL THEN '— línea base'
        WHEN u.deezer_fans > u.fans_semana_anterior THEN '▲ creciendo'
        WHEN u.deezer_fans < u.fans_semana_anterior THEN '▼ retroceso'
        ELSE '→ estable'
    END AS tendencia
FROM ultimo u
LEFT JOIN cohorte c ON u.artist_name = c.artist_name
ORDER BY crecimiento_pct DESC NULLS LAST, deezer_fans DESC
"""


def _cohorte_vacia():
    return pd.DataFrame(
        columns=["artist_name", "genero", "pais_origen", "ratio_fans_rank"]
    )


def iterar_snapshots(dir_snapshots=DIR_SNAPSHOTS):
    """Generador: cede un snapshot a la vez, SOLO las columnas de la serie.

    Pereza real: cada `next()` lee un CSV del disco; el caller nunca ve más
    de un archivo completo en memoria. El orden es el orden de los
    archivos (snapshot_YYYYMMDD.csv → cronológico).
    """
    rutas = sorted(glob.glob(os.path.join(dir_snapshots, "*.csv")))
    for ruta in rutas:
        df = pd.read_csv(ruta)
        columnas = [c for c in COLUMNAS_SERIE if c in df.columns]
        if len(columnas) < len(COLUMNAS_SERIE):
            print(f"⚠️  Snapshot {os.path.basename(ruta)} sin columnas de serie; se omite.")
            continue
        chunk = df[columnas].copy()
        # pandas deja la fecha como texto; al registrar la vista, objects
        # datetime.date se mapean a DATE (igual que infería read_csv_auto)
        chunk["snapshot_date"] = pd.to_datetime(chunk["snapshot_date"]).dt.date
        yield chunk


@medir_rendimiento
def calcular_crecimiento(dir_snapshots=DIR_SNAPSHOTS, ruta_cohorte=RUTA_COHORTE):
    """Devuelve el DataFrame de crecimiento (vacío si no hay snapshots)."""
    marcos = list(iterar_snapshots(dir_snapshots))
    if not marcos:
        print(
            "⏳ Sin snapshots todavía: la máquina del tiempo empieza el próximo lunes."
        )
        return pd.DataFrame(columns=COLUMNAS_SALIDA)

    con = duckdb.connect()
    cohorte = (
        pd.read_csv(ruta_cohorte)
        if os.path.exists(ruta_cohorte)
        else _cohorte_vacia()
    )
    if cohorte.empty:
        print("⚠️  Cohorte vacía o ausente: se omite país/género/ratio.")

    # La serie (del generador) y la cohorte viajan como vistas temporales
    con.register("serie", pd.concat(marcos, ignore_index=True))
    con.register("cohorte", cohorte)
    df = con.execute(SQL_CRECIMIENTO).df()
    con.close()
    return df


def main():
    print("⏱️  Máquina del Tiempo: calculando crecimiento semana a semana...")
    df = calcular_crecimiento()

    if df.empty:
        return df

    df.to_csv(RUTA_SALIDA, index=False, encoding="utf-8", lineterminator="\n")

    con_historial = int(df["crecimiento_pct"].notna().sum())
    print(f"✅ {len(df)} artistas escritos en {RUTA_SALIDA}")
    print(f"📊 Con semana anterior (LAG no nulo): {con_historial}")
    if con_historial:
        top = df.dropna(subset=["crecimiento_pct"]).head(3)
        for _, fila in top.iterrows():
            print(
                f"   🚀 {fila['artist_name']}: {fila['crecimiento_pct']:+.2f}% "
                f"({int(fila['fans_semana_anterior']):,} -> {int(fila['deezer_fans']):,})"
            )
    else:
        print(
            "⏳ Línea base lista: el próximo snapshot (la próxima semana) "
            "activa LAG() y el Δ% semanal aparecerá solo."
        )
    return df


if __name__ == "__main__":
    main()
