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
# Scouting Score adaptado (misma estructura 40/30/30 del pipeline simulado):
#   * Fandom consolidado 40% → nb_fan normalizado (métrica reina: demanda real)
#   * Rank de reproducción 30% → max rank del top de tracks (0..1.000.000)
#   * Momentum 30% → recencia del último lanzamiento (decaimiento 0-1 sobre
#     24 meses)
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
from datetime import datetime, timezone

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
# FUNCIÓN 1: Obtener datos de un artista por nombre
# ==========================================
def buscar_artista(nombre_artista):
    """
    Busca un artista en Deezer y retorna sus datos principales con métricas
    100% reales: fandom (nb_fan), rank de reproducción del top de tracks y
    momentum por fecha de su álbum más reciente.
    """
    results = deezer_get("/search/artist", q=nombre_artista, limit=1)
    items = results.get("data", [])
    if not items:
        return None

    artist = items[0]
    artist_id = artist["id"]

    # Top de tracks → rank real de reproducción (0..1M)
    top = deezer_get(f"/artist/{artist_id}/top", limit=10)
    tracks = top.get("data", [])
    top_rank = max((t.get("rank") or 0) for t in tracks) if tracks else None
    top_track = tracks[0]["title"] if tracks else "N/A"

    # Álbumes ordenados por fecha (los más nuevos primero) → momentum
    albums = deezer_get(f"/artist/{artist_id}/albums", limit=50).get("data", [])
    dates = []
    for alb in albums:
        rd = alb.get("release_date")
        if rd:
            try:
                dates.append(datetime.strptime(rd, "%Y-%m-%d"))
            except ValueError:
                continue
    last_release = max(dates) if dates else None

    months_since = None
    if last_release is not None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        months_since = max(0.0, (now - last_release).days / 30.44)

    return {
        "artist_name": artist["name"],
        "artist_id": artist_id,
        "genres": "N/D",
        "followers": artist.get("nb_fan"),
        "popularity": top_rank,  # en este extractor: rank real de Deezer
        "monthly_listeners": artist.get("nb_fan"),  # aproximación documentada
        "top_track": top_track,
        "top_track_rank": top_rank,
        "albums_count": artist.get("nb_album"),
        "last_release_date": last_release.strftime("%Y-%m-%d") if last_release else None,
        "months_since_release": round(months_since, 1) if months_since is not None else None,
        "external_url": artist.get("link"),
    }


# ==========================================
# FUNCIÓN 2: Obtener datos de múltiples artistas
# ==========================================
def extraer_datos_artistas_lista(lista_artistas):
    """
    Extrae datos de una lista de artistas y retorna un DataFrame.
    """
    artistas_data = []

    for artista in lista_artistas:
        print(f"🎵 Buscando: {artista}...")
        data = buscar_artista(artista)
        if data:
            artistas_data.append(data)
            print(f"✅ {data['artist_name']} - {data['followers']:,} fans reales")
        else:
            print(f"❌ No encontrado: {artista}")

    return pd.DataFrame(artistas_data)


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
if __name__ == "__main__":
    # Lista por defecto (los mismos 10 artistas del plan original)
    artistas_a_buscar = [
        "Bad Bunny",
        "Karol G",
        "Feid",
        "Peso Pluma",
        "Bizarrap",
        "Shakira",
        "J Balvin",
        "Maluma",
        "Rauw Alejandro",
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

    print("🚀 Iniciando extracción de datos REALES vía Deezer API...\n")

    # Extraer datos reales
    df_deezer = extraer_datos_artistas_lista(artistas_a_buscar)

    if df_deezer.empty:
        print("❌ No se extrajo ningún artista. Revisa conectividad.")
        sys.exit(1)

    # Calcular Scouting Score
    df_deezer = calcular_scouting_score_real(df_deezer)

    # Persistir: CSV de export + tabla raw en DuckDB (ELT: dbt transforma)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_dir, "deezer_artists_data.csv")
    df_deezer.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n💾 CSV: {csv_path}")

    con = duckdb.connect(AR_DB)
    con.register("deezer_df", df_deezer)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS real_artists_raw AS
        SELECT * FROM deezer_df LIMIT 0
        """
    )
    con.execute("DELETE FROM real_artists_raw")
    con.execute("INSERT INTO real_artists_raw SELECT * FROM deezer_df")
    n = con.execute("SELECT COUNT(*) FROM real_artists_raw").fetchone()[0]
    con.close()
    print(f"🦆 DuckDB ({AR_DB}): real_artists_raw → {n} artistas reales")

    # Mostrar resumen
    print("\n" + "=" * 80)
    print("📊 RESUMEN DE ARTISTAS ANALIZADOS (DATOS REALES)")
    print("=" * 80)
    print(
        df_deezer[
            ["artist_name", "followers", "top_track_rank", "scouting_score", "ar_recommendation"]
        ].to_string(index=False)
    )

    # Top 3
    print("\n🏆 TOP 3 ARTISTAS POR SCOUTING SCORE:")
    top_3 = df_deezer.nlargest(3, "scouting_score")
    for idx, row in top_3.iterrows():
        print(
            f"  {row['artist_name']} - Score: {row['scouting_score']:.0f}/100"
            f" | {row['ar_recommendation']}"
        )
