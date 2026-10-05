"""
Script para enriquecer la base de datos con características de "ADN Básico" del
artista. Estas features servirán como variables predictoras (X) para el futuro
modelo de supervivencia (Cox).

Versión 2: Con manejo de outliers y categorías de género completas.
  * rank = 0 se trata como "dato no reportado" (NaN) y se imputa con mediana.
  * log1p() comprime las ratios (2.9M -> ~15) para que no dominen el modelo.
  * Salsa queda como categoría explícita (6) en vez de "Desconocido" (5).

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

import numpy as np
import pandas as pd

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

# Mapeo de géneros a números (Label Encoding manual para control total).
# Claves en MINÚSCULAS: el seed guarda los géneros en minúscula ("urbano"),
# así que comparar con claves en mayúscula dejaba todo en "Desconocido".
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
    "salsa": 6,  # ✅ Categoría explícita para salsa (no va a "Desconocido")
    "desconocido": 5,
}


def extraer_adn_basico():
    print("🧬 Iniciando extracción de ADN Básico (v2 con manejo de outliers)...")

    csv_path = os.path.join(
        REPO_ROOT, "ar_dbt_project", "seeds", "deezer_artists_data.csv"
    )

    if not os.path.exists(csv_path):
        print(f"❌ Error: No se encontró {csv_path}")
        return

    df = pd.read_csv(csv_path)

    # ==========================================
    # 0. PRE-PROCESAMIENTO: Manejo de datos faltantes
    # ==========================================
    # deezer_rank = 0 significa "dato no reportado", no "rank cero".
    # Se imputa con mediana (robusto a outliers) SOLO para calcular las
    # features: el seed conserva los valores crudos tal cual (la capa staging
    # y el mart de dbt se alimentan del dato real, no de la imputación).
    rank = df["deezer_rank"].replace(0, np.nan)
    track = df["top_track_rank"].replace(0, np.nan)

    mediana_rank = rank.median()
    mediana_track = track.median()

    rank = rank.fillna(mediana_rank)
    track = track.fillna(mediana_track)

    print(
        f"📊 Ranks faltantes imputados con mediana: "
        f"Rank={mediana_rank:.0f}, Track={mediana_track:.0f}"
    )

    # ==========================================
    # 1. MÉTRICAS DE EFICIENCIA (con log1p para comprimir escala)
    # ==========================================
    # Ratio Fans/Rank: log1p() comprime valores extremos (2.9M -> ~15)
    df["ratio_fans_rank_raw"] = df["deezer_fans"] / rank
    df["ratio_fans_rank"] = np.log1p(df["ratio_fans_rank_raw"])

    # Dominancia del Top Track: también con log1p
    df["top_track_dominance_raw"] = track / rank
    df["top_track_dominance"] = np.log1p(df["top_track_dominance_raw"])

    print("📏 Rangos después de log1p:")
    print(
        f"   ratio_fans_rank: "
        f"[{df['ratio_fans_rank'].min():.2f}, {df['ratio_fans_rank'].max():.2f}]"
    )
    print(
        f"   top_track_dominance: "
        f"[{df['top_track_dominance'].min():.2f}, "
        f"{df['top_track_dominance'].max():.2f}]"
    )

    # ==========================================
    # 2. HEURÍSTICAS DE MARCA (El "Quién" es)
    # ==========================================
    # ¿Es solista o grupo/colaboración fija? (Heurística simple)
    df["es_solista"] = (
        df["artist_name"]
        .str.lower()
        .apply(
            lambda x: 0
            if any(
                w in x
                for w in ["feat", "featuring", " y ", " & ", " the ", "los ", "las "]
            )
            else 1
        )
    )

    # Longitud del nombre (nombres cortos suelen ser más memorables)
    df["nombre_corto"] = df["artist_name"].str.len().apply(lambda x: 1 if x < 12 else 0)

    # ==========================================
    # 3. MAPEO DE GÉNERO (Actualizado con Salsa = 6)
    # ==========================================
    if "genero" not in df.columns:
        df["genero"] = "Desconocido"

    df["genero_encoded"] = (
        df["genero"].astype(str).str.strip().str.lower().map(GENERO_MAP).fillna(5).astype(int)
    )

    # ==========================================
    # 4. GUARDAR RESULTADOS
    # ==========================================
    # Orden determinista del bloque de features al final del seed
    base_cols = [c for c in df.columns if c not in ADN_BLOCK]
    df = df[base_cols + ADN_BLOCK]

    df.to_csv(csv_path, index=False, encoding="utf-8", lineterminator="\n")
    print(f"✅ ADN Básico v2 agregado a {csv_path}")

    # Actualizar cohorte
    cohort_path = os.path.join(REPO_ROOT, "data", "cohort_table.csv")
    if os.path.exists(cohort_path):
        cohort_df = pd.read_csv(cohort_path)

        # Idempotencia: si ya existen (corrida anterior), se regeneran y no
        # aparecen sufijos _x/_y en el merge
        cohort_df = cohort_df.drop(columns=[c for c in ADN_COLS if c in cohort_df.columns])

        cohort_df = cohort_df.merge(
            df[["artist_name"] + ADN_COLS], on="artist_name", how="left"
        )

        cohort_df = cohort_df.fillna(
            {
                "ratio_fans_rank": 0,
                "top_track_dominance": 0,
                "es_solista": 1,
                "nombre_corto": 0,
                "genero_encoded": 5,
            }
        )
        cohort_df["genero_encoded"] = cohort_df["genero_encoded"].astype(int)
        for col in ("es_solista", "nombre_corto"):
            cohort_df[col] = cohort_df[col].astype(int)

        cohort_df.to_csv(cohort_path, index=False, encoding="utf-8", lineterminator="\n")
        print(f"✅ Tabla de cohorte actualizada en {cohort_path}")

    print("🎉 ¡Fase 2 (ADN Básico v2) completada exitosamente!")


if __name__ == "__main__":
    extraer_adn_basico()
