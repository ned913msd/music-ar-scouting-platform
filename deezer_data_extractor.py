#!/usr/bin/env python3
# ============================================================================
# deezer_data_extractor.py
# A&R Scouting Command Center | Extractor de datos REALES vía Deezer API
#
# ¿Por qué Deezer? La Web API de Spotify exige (desde 2025) que el dueño de
# la app tenga suscripción Premium activa; Deezer es pública: sin API key,
# sin login y sin Premium, con datos reales de streaming:
#   * nb_fan            → base de fans del artista (equivalente aproximado a
#                         followers; para headliners ronda ~10% de los
#                         followers de Spotify)
#   * album['fans']     → fans del álbum
#   * album['release_date'] → fecha real de lanzamiento
#   * track['rank']     → popularidad real de reproducción (0..1M)
#   * track['duration'] → duración en segundos
#
# Scouting Score (fórmula del curso, ajustada para Deezer):
#   * Rank del artista 50% → PROMEDIO del rank del top-10 de tracks
#     (0..1.000.000). Nota honesta: la API ya NO expone 'rank' a nivel
#     artista (ni en /search ni en /artist/{id}); el promedio del top-10 es
#     el proxy real de fuerza de catálogo en la misma escala 0-1M.
#   * Fandom consolidado 30% → nb_fan normalizado (base de fans reales)
#   * Pico del mayor hit 20% → rank del track más escuchado (0..1M absoluto)
#
# Notas técnicas:
#   * stdout UTF-8 (consola Windows cp1252 + emojis)
#   * Throttling ~3 req/s y reintentos ante 429/5xx de la API pública
#   * Dedupe de la lista de artistas
#   * Persistencia: CSV de export + tabla real_artists_raw en DuckDB
#     (patrón ELT: dbt transforma después)
#
# Uso:
#   ./venv/Scripts/python deezer_data_extractor.py
#   ./venv/Scripts/python deezer_data_extractor.py "Bad Bunny" "Karol G" ...
# ============================================================================

import sys

# Consolas Windows (cp1252) no imprimen emojis: forzar UTF-8 antes de todo
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import os
import time

import duckdb
import pandas as pd
import requests

DEEZER_BASE = "https://api.deezer.com"

# Warehouse analítico (misma convención de rutas que el resto del producto)
AR_DB = os.environ.get(
    "MUSIC_AR_DB_PATH",
    r"C:\Users\LENOVO\Desktop\BASES DE DATOS DE PRUEBAS\music_ar_product.duckdb",
)

MOMENTUM_DECAY_MONTHS = 24.0  # un lanzamiento "pesa" hasta 2 años
MAX_TRACK_RANK = 1_000_000.0  # escala oficial del campo rank de Deezer

session = requests.Session()


def deezer_get(path, **params):
    """GET contra Deezer con reintentos ante 429/5xx y throttling amable."""
    for attempt in range(4):
        resp = session.get(f"{DEEZER_BASE}{path}", params=params, timeout=20)
        if resp.status_code == 200:
            time.sleep(0.35)  # ~3 req/s, respetuoso con la API pública
            return resp.json()
        if resp.status_code in (429, 500, 502, 503):
            wait = 2 ** attempt
            print(f"   ⏳ Deezer {resp.status_code}; reintento en {wait}s...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
    raise RuntimeError(f"Deezer no respondió tras 4 intentos: {path}")


# ==========================================
# FUNCIÓN 1: Obtener datos de un artista en Deezer
# ==========================================
def buscar_artista_deezer(nombre_artista):
    """
    Busca un artista en Deezer y retorna sus datos principales + top track.
    Métricas 100% reales: nb_fan (fans), rank del artista (0..1M) y rank del
    track más escuchado.
    """
    # Traer 5 candidatos: /search/artist puede devolver homónimos (ej. para
    # "Quevedo" aparecen otro Quevedo, Creed, Bad Gyal...). Prioridad:
    # coincidencia exacta de nombre (sin tildes/mayúsculas) y, entre ellos,
    # el más prominente por fans.
    results = deezer_get("/search/artist", q=nombre_artista, limit=5)
    items = results.get("data", [])
    if not items:
        return None

    import unicodedata

    def _norm(s):
        return "".join(
            c for c in unicodedata.normalize("NFKD", (s or "").casefold())
            if not unicodedata.combining(c)
        ).strip()

    exact = [a for a in items if _norm(a["name"]) == _norm(nombre_artista)]
    pool = exact or items
    artist = max(pool, key=lambda a: a.get("nb_fan") or 0)
    artist_id = artist["id"]

    # Top-10 de tracks → proxy de rank de artista (promedio) + mayor hit
    top = deezer_get(f"/artist/{artist_id}/top", limit=10)
    tracks = top.get("data", [])
    ranks = [t.get("rank") or 0 for t in tracks]
    artist_rank = round(sum(ranks) / len(ranks)) if ranks else 0
    top_track = tracks[0] if tracks else {}

    return {
        "artist_name": artist["name"],
        "artist_id": artist_id,
        "deezer_fans": artist.get("nb_fan"),
        "deezer_rank": artist_rank,  # proxy real (0..1M), ver header
        "picture_url": (
            artist.get("picture_xl")
            or artist.get("picture_big")
            or artist.get("picture_medium")
        ),
        "deezer_link": artist.get("link"),
        "top_track_name": top_track.get("title", "N/A"),
        "top_track_rank": top_track.get("rank", 0),
        "top_track_duration": top_track.get("duration", 0),
    }


# ==========================================
# FUNCIÓN 2: Extraer y Calcular Scouting Score
# ==========================================
def extraer_y_calcular_score(lista_artistas):
    """
    Extrae datos de una lista de artistas, calcula el Scouting Score
    (fórmula ajustada para Deezer) y retorna un DataFrame.
    """
    artistas_data = []

    print("🎵 Iniciando extracción de datos de Deezer...\n")
    for artista in lista_artistas:
        print(f"Buscando: {artista}...")
        data = buscar_artista_deezer(artista)
        if data:
            artistas_data.append(data)
            print(
                f"✅ {data['artist_name']} | Fans: {data['deezer_fans']:,}"
                f" | Rank: {data['deezer_rank']}"
            )
        else:
            print(f"⚠️ No encontrado: {artista}")

    df = pd.DataFrame(artistas_data)
    if df.empty:
        return df

    # ==============================================
    # LÓGICA DE NEGOCIO: Scouting Score con Deezer
    # ==============================================
    # Blindaje numérico: asegurar dtypes numéricos antes de normalizar
    for col in ("deezer_fans", "deezer_rank", "top_track_rank"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Normalizamos las métricas a escala 0-1
    df["norm_fans"] = df["deezer_fans"] / df["deezer_fans"].max()
    df["norm_rank"] = df["deezer_rank"] / 1_000_000  # rank máximo: 1.000.000

    # Fórmula de Scouting Score (Ajustada para Deezer)
    # Rank (50%) + Fans (30%) + Popularidad del Top Track (20%)
    df["norm_track_rank"] = df["top_track_rank"] / df["top_track_rank"].max()

    df["scouting_score"] = (
        (df["norm_rank"] * 0.50)
        + (df["norm_fans"] * 0.30)
        + (df["norm_track_rank"] * 0.20)
    ) * 100
    df["scouting_score"] = df["scouting_score"].round(2)

    # Clasificación A&R (bins idénticos al pipeline: 0-40 / 40-75 / 75-100)
    df["ar_recommendation"] = pd.cut(
        df["scouting_score"],
        bins=[0, 40, 75, 100],
        labels=["⚠️ DESCARTAR", "👀 OBSERVAR", "🔥 FIRMAR AHORA"],
    )

    # Insight estratégico
    df["strategic_insight"] = df.apply(
        lambda row: (
            "Alto Rank + Base de Fans sólida = Éxito consolidado"
            if row["scouting_score"] > 75
            else "Crecimiento orgánico detectado, monitorear de cerca"
            if row["scouting_score"] > 40
            else "Datos insuficientes o nicho muy específico"
        ),
        axis=1,
    )

    return df


# ==========================================
# FUNCIÓN 3: Calcular Scouting Score con datos reales
# ==========================================
def calcular_scouting_score_real(df):
    """
    Scouting Score con datos reales de Deezer (misma estructura 40/30/30):
      * Fandom consolidado 40%  → nb_fan normalizado (métrica reina)
      * Rank de reproducción 30% → top_track_rank / 1.000.000
      * Momentum 30% → decaimiento exponencial del último lanzamiento
    """
    # Normalizar métricas (0 a 1)
    df["norm_fans"] = df["followers"] / df["followers"].max()
    df["norm_rank"] = df["top_track_rank"].fillna(0) / MAX_TRACK_RANK
    df["norm_momentum"] = (
        -(df["months_since_release"].fillna(MOMENTUM_DECAY_MONTHS)
          / MOMENTUM_DECAY_MONTHS)
    ).apply(lambda x: pow(2.0, x))  # 1.0 = lanzado hoy; ~0.5 a los 24 meses

    # Scouting Score (fandom 40% + reproducción real 30% + momentum 30%)
    df["scouting_score"] = (
        (df["norm_fans"] * 0.40)
        + (df["norm_rank"] * 0.30)
        + (df["norm_momentum"] * 0.30)
    ) * 100
    df["scouting_score"] = df["scouting_score"].round(2)

    # Clasificación (bins idénticos al pipeline: 0-40 / 40-75 / 75-100)
    df["ar_recommendation"] = pd.cut(
        df["scouting_score"],
        bins=[0, 40, 75, 100],
        labels=["⚠️ DESCARTAR", "👀 OBSERVAR", "🔥 FIRMAR AHORA"],
    )

    return df


# ==========================================
# EJECUCIÓN PRINCIPAL
# ==========================================
# ==========================================
# EJECUCIÓN PRINCIPAL
# ==========================================
if __name__ == "__main__":
    # Lista de artistas emergentes (el verdadero caso de uso A&R)
    artistas_a_buscar = [
        "Feid",
        "Karol G",
        "Peso Pluma",
        "Mora",
        "Ryan Castro",
        "Saiko",
        "Young Miko",
        "Quevedo",
        "Bizarrap",
        "Myke Towers",
    ]

    # Override opcional por CLI: python deezer_data_extractor.py "X" "Y" ...
    if len(sys.argv) > 1:
        artistas_a_buscar = []
        seen = set()
        for a in sys.argv[1:]:
            k = a.strip().casefold()
            if k not in seen:
                seen.add(k)
                artistas_a_buscar.append(a.strip())

    df_deezer = extraer_y_calcular_score(artistas_a_buscar)

    if df_deezer.empty:
        print("❌ No se pudieron extraer datos.")
        sys.exit(1)

    # Guardar CSV (para ingestión/exports) y DuckDB (ELT: dbt transforma)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_dir, "deezer_artists_data.csv")
    df_deezer.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n✅ Datos guardados exitosamente en: {csv_path}")

    con = duckdb.connect(AR_DB)
    con.register("deezer_df", df_deezer)
    # CREATE OR REPLACE: cada extracción es un snapshot completo y evoluciona
    # limpiamente si el esquema cambia entre corridas.
    con.execute("CREATE OR REPLACE TABLE real_artists_raw AS SELECT * FROM deezer_df LIMIT 0")
    con.execute("INSERT INTO real_artists_raw SELECT * FROM deezer_df")
    n = con.execute("SELECT COUNT(*) FROM real_artists_raw").fetchone()[0]
    con.close()
    print(f"🦆 DuckDB ({AR_DB}): real_artists_raw → {n} artistas reales")

    # Resumen
    print("\n" + "=" * 80)
    print("📊 RESUMEN DE ARTISTAS ANALIZADOS (DEEZER API)")
    print("=" * 80)
    cols_to_show = [
        "artist_name",
        "deezer_fans",
        "deezer_rank",
        "scouting_score",
        "ar_recommendation",
    ]
    print(df_deezer[cols_to_show].to_string(index=False))

    print("\n🏆 TOP 3 ARTISTAS POR SCOUTING SCORE:")
    top_3 = df_deezer.nlargest(3, "scouting_score")
    for idx, row in top_3.iterrows():
        print(
            f"  🔥 {row['artist_name']} | Score: {row['scouting_score']:.0f}/100"
            f" | {row['ar_recommendation']}"
        )
