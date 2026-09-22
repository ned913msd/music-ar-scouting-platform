#!/usr/bin/env python3
# ============================================================================
# spotify_data_extractor.py
# A&R Scouting Command Center | Extractor de datos REALES de Spotify Web API
#
# Adaptación del tutorial con 5 correcciones necesarias (equipo Windows):
#   1. Client Credentials en vez de SpotifyOAuth: los endpoints usados
#      (search / artist / top-tracks) no requieren login de usuario, así que
#      NO aparece ventana de navegador ni redirect a localhost.
#   2. Redirect URI con 127.0.0.1 (Spotify rechaza "localhost" literal desde
#      abril 2025 para apps nuevas).
#   3. audio-features degradado gracefulmente: Spotify la deprecó el
#      2025-11-27 (HTTP 403 para nuevas apps). Con fallback a 0.5 (neutro).
#   4. stdout UTF-8: la consola de Windows es cp1252 y los emojis rompen.
#   5. Dedupe de la lista de artistas (el tutorial pide "Feid" dos veces).
#
# Uso:
#   ./venv/Scripts/python spotify_data_extractor.py
#   ./venv/Scripts/python spotify_data_extractor.py "Bad Bunny" "Karol G" ...
# ============================================================================

import sys
import os

# Consolas Windows (cp1252) no imprimen emojis: forzar UTF-8 antes de todo
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import time
import duckdb
import pandas as pd
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv

# Cargar variables de entorno (.env junto a este script)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8501")

if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
    print("❌ Faltan SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET en el archivo .env")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Autenticación: Client Credentials (server-to-server, sin navegador)
# Scope de OAuth solo hace falta para datos de usuario (user-top-read, etc.);
# para catálogo público de artistas no se necesita login.
# ---------------------------------------------------------------------------
sp = spotipy.Spotify(
    auth_manager=SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
    ),
    requests_timeout=20,
    retries=3,
)

print("✅ Conectado exitosamente con Spotify API (Client Credentials)")

# Warehouse analítico (misma convención de rutas que el resto del producto)
AR_DB = os.environ.get(
    "MUSIC_AR_DB_PATH",
    r"C:\Users\LENOVO\Desktop\BASES DE DATOS DE PRUEBAS\music_ar_product.duckdb",
)

AUDIO_FEATURES_DEPRECATED = False  # se activa si la API devuelve 403


# ==========================================
# FUNCIÓN 1: Obtener datos de un artista por nombre
# ==========================================
def buscar_artista(nombre_artista):
    """
    Busca un artista en Spotify y retorna sus datos principales.
    audio-features está deprecado por Spotify (2025-11-27): si la API
    devuelve 403, se degrada a None y el score usa el neutro 0.5.
    """
    global AUDIO_FEATURES_DEPRECATED

    results = sp.search(q=f"artist:{nombre_artista}", type="artist", limit=1)

    if results["artists"]["items"]:
        artist = results["artists"]["items"][0]
        artist_id = artist["id"]

        # Obtener datos detallados
        artist_data = sp.artist(artist_id)

        # Obtener top tracks (mercado Colombia)
        top_tracks = sp.artist_top_tracks(artist_id, country="CO")

        # Audio features de la canción más popular (endpoint en deprecación)
        audio_features = None
        if top_tracks["tracks"] and not AUDIO_FEATURES_DEPRECATED:
            try:
                audio_features = sp.audio_features(top_tracks["tracks"][0]["id"])[0]
            except spotipy.exceptions.SpotifyException as e:
                if e.http_status == 403:
                    AUDIO_FEATURES_DEPRECATED = True
                    print(
                        "   ⚠️  audio-features deprecado por Spotify (403): "
                        "continúo sin features (energía/danza = neutro)."
                    )
                else:
                    raise

        return {
            "artist_name": artist_data["name"],
            "artist_id": artist_data["id"],
            "genres": ", ".join(artist_data["genres"]),
            "followers": artist_data["followers"]["total"],
            "popularity": artist_data["popularity"],
            "monthly_listeners": artist_data["followers"]["total"],  # Aproximación
            "top_track": (
                top_tracks["tracks"][0]["name"] if top_tracks["tracks"] else "N/A"
            ),
            "danceability": (
                audio_features["danceability"] if audio_features else None
            ),
            "energy": audio_features["energy"] if audio_features else None,
            "valence": (
                audio_features["valence"] if audio_features else None
            ),  # "Felicidad" de la canción
            "tempo": audio_features["tempo"] if audio_features else None,
            "external_url": artist_data["external_urls"]["spotify"],
        }
    else:
        return None


# ==========================================
# FUNCIÓN 2: Obtener datos de múltiples artistas
# ==========================================
def extraer_datos_artistas_lista(lista_artistas):
    """
    Extrae datos de una lista de artistas y retorna un DataFrame.
    Incluye throttling (~3.5 req/s) para respetar el rate limit de Spotify.
    """
    artistas_data = []

    for i, artista in enumerate(lista_artistas):
        if i > 0:
            time.sleep(0.3)  # rate limit amable
        print(f"🎵 Buscando: {artista}...")
        data = buscar_artista(artista)
        if data:
            artistas_data.append(data)
            print(f"✅ {data['artist_name']} - {data['followers']:,} followers")
        else:
            print(f"❌ No encontrado: {artista}")

    return pd.DataFrame(artistas_data)


# ==========================================
# FUNCIÓN 3: Calcular Scouting Score con datos reales
# ==========================================
def calcular_scouting_score_real(df):
    """
    Calcula el Scouting Score con datos reales de Spotify.
    Pesos: popularidad 40% + followers 30% + energía 15% + danzabilidad 15%.
    """
    # Normalizar métricas
    df["norm_followers"] = df["followers"] / df["followers"].max()
    df["norm_popularity"] = df["popularity"] / 100

    # Calcular Scouting Score (adaptado para datos reales)
    df["scouting_score"] = (
        (df["norm_popularity"] * 0.40)
        + (df["norm_followers"] * 0.30)
        + (df["energy"].fillna(0.5) * 0.15)
        + (df["danceability"].fillna(0.5) * 0.15)
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
    # Lista por defecto (dedupe: el tutorial incluía "Feid" dos veces)
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

    # Override opcional por CLI: python spotify_data_extractor.py "X" "Y" ...
    if len(sys.argv) > 1:
        artistas_a_buscar = []
        seen = set()
        for a in sys.argv[1:]:
            k = a.strip().casefold()
            if k not in seen:
                seen.add(k)
                artistas_a_buscar.append(a.strip())

    print("🚀 Iniciando extracción de datos de Spotify...\n")

    # Extraer datos reales
    df_spotify = extraer_datos_artistas_lista(artistas_a_buscar)

    if df_spotify.empty:
        print("❌ No se extrajo ningún artista. Revisa credenciales/conectividad.")
        sys.exit(1)

    # Calcular Scouting Score
    df_spotify = calcular_scouting_score_real(df_spotify)

    # Persistir: CSV de export + tabla raw en DuckDB (ELT: dbt transforma)
    csv_path = os.path.join(BASE_DIR, "spotify_artists_data.csv")
    df_spotify.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n💾 CSV: {csv_path}")

    con = duckdb.connect(AR_DB)
    con.register("spotify_df", df_spotify)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS spotify_artists_raw AS
        SELECT * FROM spotify_df LIMIT 0
        """
    )
    con.execute("DELETE FROM spotify_artists_raw")
    con.execute("INSERT INTO spotify_artists_raw SELECT * FROM spotify_df")
    n = con.execute("SELECT COUNT(*) FROM spotify_artists_raw").fetchone()[0]
    con.close()
    print(f"🦆 DuckDB ({AR_DB}): spotify_artists_raw → {n} artistas reales")

    # Mostrar resumen
    print("\n" + "=" * 80)
    print("📊 RESUMEN DE ARTISTAS ANALIZADOS")
    print("=" * 80)
    print(
        df_spotify[
            ["artist_name", "followers", "popularity", "scouting_score", "ar_recommendation"]
        ].to_string(index=False)
    )

    # Top 3
    print("\n🏆 TOP 3 ARTISTAS POR SCOUTING SCORE:")
    top_3 = df_spotify.nlargest(3, "scouting_score")
    for idx, row in top_3.iterrows():
        print(
            f"  {row['artist_name']} - Score: {row['scouting_score']:.0f}/100"
            f" | {row['ar_recommendation']}"
        )

    if AUDIO_FEATURES_DEPRECATED:
        print(
            "\nℹ️  Nota: Spotify deprecó audio-features (2025-11-27); energía y "
            "danzabilidad usaron el neutro 0.5. El 70% del score "
            "(popularity + followers) son datos 100% reales."
        )
