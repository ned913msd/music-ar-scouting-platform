#!/usr/bin/env python3
# ============================================================================
# daily_update.py
# A&R Scouting Command Center | Robot de actualización automática (GitHub Actions)
#
# Qué hace:
#   1. Consulta la API pública de Deezer para la lista de artistas vigilados.
#   2. Reutiliza la lógica YA PROBADA del extractor (deezer_data_extractor.py):
#      resolución de homónimos por coincidencia exacta + proxy de rank con el
#      top-10 de tracks — no duplica lógica, la importa.
#   3. Reescribe las COLUMNAS NÚCLEO del seed (ar_dbt_project/seeds/
#      deezer_artists_data.csv) preservando las columnas derivadas que dbt y
#      el mart calculan (norm_*, scouting_score, ar_recommendation, ...).
#   4. Fusiona con el historial: los artistas de corridas anteriores que ya no
#      están en la lista NO se pierden del seed.
#
# Diseño para CI:
#   * Sin dependencia del warehouse local ni de rutas de Windows: escribe el
#     seed del repo y termina (Render redeploya al detectar el push).
#   * Throttling + reintentos de la API heredados del extractor.
#   * Falla con exit 1 si NINGÚN artista se pudo extraer (CI visible en rojo).
#
# Uso local:   ./venv/Scripts/python scripts/daily_update.py
# Uso en CI:   python scripts/daily_update.py   (desde la raíz del repo)
# ============================================================================

import sys

# Consolas Windows (cp1252) no imprimen emojis: forzar UTF-8 antes de todo
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import os

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED_CSV = os.path.join(
    REPO_ROOT, "ar_dbt_project", "seeds", "deezer_artists_data.csv"
)

# Columnas NÚCLEO que este robot actualiza desde la API (las derivadas —
# norm_*, scouting_score, ar_recommendation, strategic_insight — las calcula
# dbt/the mart; el robot no las toca para no pisar la lógica del pipeline).
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
    "genero",  # añadida por expand_database.py (Fase 1): el robot la PRESERVA
]

INT_COLS = ["artist_id", "deezer_fans", "deezer_rank", "top_track_rank", "top_track_duration"]

# Artistas vigilados por el robot (dedupe: la lista del tutorial repetía "Saiko")
ARTISTAS = [
    "Karol G",
    "Feid",
    "Myke Towers",
    "Peso Pluma",
    "Young Miko",
    "Saiko",
    "Mora",
    "Ryan Castro",
    "Quevedo",
    "Bizarrap",
]


def _cargar_seed_previo() -> pd.DataFrame:
    """Lee el seed actual (solo columnas núcleo). Tolerante a BOM y ausencia."""
    if not os.path.exists(SEED_CSV):
        print("ℹ️ Seed previo no existe; se creará desde cero.")
        return pd.DataFrame(columns=CORE_COLS)
    df = pd.read_csv(SEED_CSV, encoding="utf-8-sig", usecols=lambda c: c in CORE_COLS)
    for col in CORE_COLS:
        if col not in df.columns:
            df[col] = None
    return df[CORE_COLS]


def _leer_delta_fans(df_previo: pd.DataFrame, df_nuevo: pd.DataFrame) -> pd.DataFrame:
    """Tabla legible de cambio de fans por artista (para el log de CI)."""
    prev = df_previo.set_index("artist_name")["deezer_fans"]
    rows = []
    for _, r in df_nuevo.iterrows():
        antes = prev.get(r["artist_name"])
        rows.append(
            {
                "artist_name": r["artist_name"],
                "fans_antes": None if pd.isna(antes) else int(antes),
                "fans_ahora": int(r["deezer_fans"]),
            }
        )
    d = pd.DataFrame(rows)
    d["delta_fans"] = d["fans_ahora"] - d["fans_antes"]
    return d


def actualizar_datos() -> int:
    print("🤖 Iniciando actualización automática desde Deezer API...\n")

    # Importar la lógica probada del extractor (búsqueda robusta + proxy rank)
    sys.path.insert(0, REPO_ROOT)
    from deezer_data_extractor import buscar_artista_deezer

    filas = []
    for nombre in ARTISTAS:
        try:
            data = buscar_artista_deezer(nombre)
        except Exception as e:  # API caída / rate limit agotado: no tumbar la corrida por un artista
            print(f"❌ Error consultando {nombre}: {e}")
            continue
        if data:
            fila = {k: data.get(k) for k in CORE_COLS}
            fila["genero"] = "urbano"  # el watchlist es urbano latino
            filas.append(fila)
            print(f"✅ {data['artist_name']} | Fans: {int(data['deezer_fans']):,} | Rank: {data['deezer_rank']}")
        else:
            print(f"⚠️ No encontrado: {nombre}")

    if not filas:
        print("\n❌ Ningún artista se pudo extraer: no se toca el seed.")
        return 1

    df_nuevo = pd.DataFrame(filas, columns=CORE_COLS)
    for col in INT_COLS:
        df_nuevo[col] = pd.to_numeric(df_nuevo[col], errors="coerce").fillna(0).astype(int)

    # Merge con historial: conservar artistas de corridas previas no vigilados hoy
    df_previo = _cargar_seed_previo()
    df_final = pd.concat([df_previo, df_nuevo], ignore_index=True)
    df_final = df_final.drop_duplicates(subset="artist_name", keep="last")
    df_final = df_final.sort_values("deezer_fans", ascending=False).reset_index(drop=True)
    for col in INT_COLS:
        df_final[col] = pd.to_numeric(df_final[col], errors="coerce").fillna(0).astype(int)

    # Delta de fans vs. corrida anterior (la línea que el Director quiere ver)
    if not df_previo.empty:
        print("\n📈 Cambios de fans vs. snapshot anterior:")
        delta = _leer_delta_fans(df_previo, df_nuevo)
        delta["delta_fans"] = delta["delta_fans"].fillna(0).astype(int)
        print(delta.to_string(index=False))

    # Escritura determinista: sin BOM, LF (compatible con dbt seed y CI)
    df_final.to_csv(SEED_CSV, index=False, encoding="utf-8", lineterminator="\n")
    print(f"\n💾 Seed actualizado: {SEED_CSV} ({len(df_final)} artistas, columnas núcleo)")
    return 0


if __name__ == "__main__":
    sys.exit(actualizar_datos())
