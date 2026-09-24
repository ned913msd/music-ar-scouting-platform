#!/usr/bin/env python3
# ============================================================================
# expand_database.py
# A&R Scouting Command Center | Expansión del universo de scouting (FASE 1)
#
# Qué hace:
#   1. Consulta la API pública de Deezer (/search/artist) con una lista de
#      géneros objetivo (reggaeton, trap latino, pop latino, ...) y limit=20
#      por género.
#   2. Para cada artista NUEVO trae su top-1 track (título, rank, duración):
#      el top_track_rank alimenta el 20% del Scouting Score del mart — sin
#      ese dato los nuevos artistas saldrían sistemáticamente infravalorados.
#   3. FUSIONA con el seed existente (ar_dbt_project/seeds/
#      deezer_artists_data.csv): los 10 artistas del watchlist NUNCA se
#      pierden ni son desplazados por homónimos (dedupe por artist_id y por
#      artist_name con prioridad al watchlist).
#   4. Añade la columna `genero` (término de búsqueda que trajo al artista)
#      y la preserva también para los artistas originales ("urbano").
#
# Diseño:
#   * Rate limiting: 1s entre géneros, 0.25s entre top-tracks + reintentos
#     con backoff ante 429/5xx (mismo espíritu que daily_update.py).
#   * Idempotente: correrlo dos veces no duplica filas.
#   * Escritura determinista: UTF-8 sin BOM, LF (compatible dbt seed y CI).
#
# Uso:  ./venv/Scripts/python scripts/expand_database.py
# ============================================================================

import sys

# Consolas Windows (cp1252) no imprimen emojis: forzar UTF-8 antes de todo
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import os
import time
from urllib.parse import quote

import pandas as pd
import requests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED_CSV = os.path.join(
    REPO_ROOT, "ar_dbt_project", "seeds", "deezer_artists_data.csv"
)

CORE_COLS = [
    "artist_name",
    "artist_id",
    "deezer_fans",
    "deezer_rank",
    "picture_url",
    "deezer_link",
    "top_track_name",
    "top_track_rank",
    "top_track_duration",
    "genero",
]
INT_COLS = [
    "artist_id",
    "deezer_fans",
    "deezer_rank",
    "top_track_rank",
    "top_track_duration",
]

# Géneros objetivo del pedido del Decano (9 búsquedas × 20 = hasta 180 candidatos)
GENEROS = [
    "reggaeton",
    "trap latino",
    "pop latino",
    "urbano",
    "rock latino",
    "electrónica",
    "indie",
    "folk",
    "salsa",
]
SEARCH_LIMIT = 20
API_BASE = "https://api.deezer.com"

SESION = requests.Session()
SESION.headers.update({"User-Agent": "AR-Scouting-Command-Center/1.0"})


def get_json(url, intentos=3, timeout=15):
    """GET con reintentos y backoff; devuelve {} si la API falla o responde error."""
    for intento in range(1, intentos + 1):
        try:
            r = SESION.get(url, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                raise ValueError(data["error"].get("message", "error desconocido"))
            return data
        except Exception as e:
            if intento == intentos:
                print(f"   ⚠️ Falla tras {intentos} intentos: {url} → {e}")
                return {}
            time.sleep(2 * intento)
    return {}


def buscar_artistas_genero(genero):
    """Búsqueda /search/artist por término de género (limit=SEARCH_LIMIT)."""
    url = f"{API_BASE}/search/artist?q={quote(genero)}&limit={SEARCH_LIMIT}"
    data = get_json(url)
    return data.get("data") or []


def top_track_de(artist_id):
    """Top-1 track del artista: (título, rank, duración). Vacío → ('N/A', 0, 0)."""
    data = get_json(f"{API_BASE}/artist/{artist_id}/top?limit=1")
    tracks = data.get("data") or []
    if not tracks:
        return "N/A", 0, 0
    t = tracks[0]
    return (
        (t.get("title") or "N/A"),
        int(t.get("rank") or 0),
        int(t.get("duration") or 0),
    )


def cargar_seed_previo():
    """Lee el seed actual preservando TODAS sus columnas. Tolerante a BOM."""
    if not os.path.exists(SEED_CSV):
        print("ℹ️ Seed previo no existe; se creará desde cero.")
        return pd.DataFrame(columns=CORE_COLS)
    df = pd.read_csv(SEED_CSV, encoding="utf-8-sig")
    for col in CORE_COLS:
        if col not in df.columns:
            df[col] = None
    return df[CORE_COLS]


def extraer_mas_artistas() -> int:
    print("🌍 Expandiendo universo de scouting desde Deezer API...\n")

    previo = cargar_seed_previo()
    ids_previos = set()
    if not previo.empty:
        ids_previos = set(previo["artist_id"].dropna().astype(int))
    print(f"📋 Watchlist previa: {len(previo)} artistas (se preservan intactos)\n")

    filas_nuevas = []
    por_genero = {}
    for genero in GENEROS:
        print(f"🎵 Buscando artistas de: {genero}")
        nuevos_del_genero = 0
        for a in buscar_artistas_genero(genero):
            aid = int(a.get("id") or 0)
            if not aid or aid in ids_previos:
                continue
            ids_previos.add(aid)  # evita re-consultar el mismo id entre géneros
            track, trank, tdur = top_track_de(aid)
            filas_nuevas.append(
                {
                    "artist_name": (a.get("name") or "").strip(),
                    "artist_id": aid,
                    "deezer_fans": int(a.get("nb_fan") or 0),
                    "deezer_rank": int(a.get("rank") or 0),
                    "picture_url": a.get("picture_xl") or a.get("picture_big") or "",
                    "deezer_link": a.get("link") or "",
                    "top_track_name": track,
                    "top_track_rank": trank,
                    "top_track_duration": tdur,
                    "genero": genero,
                }
            )
            nuevos_del_genero += 1
            print(
                f"   ✅ {a.get('name')} | fans: {int(a.get('nb_fan') or 0):,} | top: {track}"
            )
            time.sleep(0.25)  # rate limiting fino entre top-tracks
        por_genero[genero] = nuevos_del_genero
        time.sleep(1.0)  # rate limiting entre búsquedas de género

    df_nuevos = pd.DataFrame(filas_nuevas, columns=CORE_COLS)
    if df_nuevos.empty:
        print("\n❌ Ningún artista nuevo se pudo extraer: no se toca el seed.")
        return 1

    # Dedupe interno: ids repetidos entre géneros (ya evitados arriba) y
    # HOMÓNIMOS con distinto id → gana el de más fans (probablemente el real).
    df_nuevos = df_nuevos[df_nuevos["artist_name"] != ""]
    df_nuevos = df_nuevos.sort_values("deezer_fans", ascending=False)
    df_nuevos = df_nuevos.drop_duplicates(subset="artist_id", keep="first")
    df_nuevos = df_nuevos.drop_duplicates(subset="artist_name", keep="first")

    # Watchlist primero: jamás desplazada por homónimos nuevos (keep="first").
    previo["genero"] = previo["genero"].fillna("urbano")
    df_final = pd.concat([previo, df_nuevos], ignore_index=True)
    df_final = df_final.drop_duplicates(subset="artist_name", keep="first")
    df_final = df_final.sort_values("deezer_fans", ascending=False).reset_index(drop=True)
    for col in INT_COLS:
        df_final[col] = pd.to_numeric(df_final[col], errors="coerce").fillna(0).astype(int)
    df_final = df_final[CORE_COLS]

    df_final.to_csv(SEED_CSV, index=False, encoding="utf-8", lineterminator="\n")

    print("\n📊 Resumen por género (nuevos únicos):")
    for genero, n in por_genero.items():
        print(f"   • {genero:<12} +{n}")
    con_fans = int((df_final["deezer_fans"] > 0).sum())
    print(
        f"\n💾 Seed actualizado: {SEED_CSV}\n"
        f"   {len(previo)} originales + {len(df_nuevos)} nuevos = {len(df_final)} artistas\n"
        f"   ({con_fans} con fans > 0 pasarán el DQ del mart)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(extraer_mas_artistas())
