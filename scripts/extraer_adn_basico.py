"""
Script para enriquecer la base de datos con características de "ADN Básico" del
artista. Estas features servirán como variables predictoras (X) para el futuro
modelo de supervivencia (Cox).

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

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Columnas que genera este script (se regeneran, nunca se acumulan)
ADN_COLS = [
    "ratio_fans_rank",
    "top_track_dominance",
    "es_solista",
    "nombre_corto",
    "genero_encoded",
]

# Mapeo de géneros a números (Label Encoding manual para control total).
# Claves en minúsculas: el seed guarda los géneros en minúscula ("urbano").
#   0 Urbano/Reggaetón/Trap · 1 Pop · 2 Guitarras/Indie/Folk ·
#   3 Electrónica · 4 Regional Mexicano · 5 Desconocido · 6 Latino tradicional
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
    "salsa": 6,
    "desconocido": 5,
}


def extraer_adn_basico():
    print("🧬 Iniciando extracción de ADN Básico...")

    csv_path = os.path.join(
        REPO_ROOT, "ar_dbt_project", "seeds", "deezer_artists_data.csv"
    )

    if not os.path.exists(csv_path):
        print(f"❌ Error: No se encontró {csv_path}")
        return

    df = pd.read_csv(csv_path)

    # ==========================================
    # 1. MÉTRICAS DE EFICIENCIA (El "Cómo" crece)
    # ==========================================
    # Ratio Fans/Rank: Mide la eficiencia de conversión.
    # Un rank bajo (bueno) con muchos fans = artista consolidado.
    # Un rank alto (regular) con muchos fans = artista en crecimiento explosivo.
    df["ratio_fans_rank"] = df["deezer_fans"] / (df["deezer_rank"] + 1)

    # Dominancia del Top Track: ¿El artista es "one-hit wonder" o tiene catálogo?
    # Si el rank del top track es muy cercano al rank del artista, depende de
    # una sola canción.
    df["top_track_dominance"] = df["top_track_rank"] / (df["deezer_rank"] + 1)

    # ==========================================
    # 2. HEURÍSTICAS DE MARCA (El "Quién" es)
    # ==========================================
    # ¿Es solista o grupo/colaboración fija? (Heurística simple)
    # Si el nombre contiene "feat", "y", "&", "the", es probable que no sea
    # solista único.
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

    # Longitud del nombre (Heurística de branding: nombres cortos suelen ser
    # más memorables)
    df["nombre_corto"] = df["artist_name"].str.len().apply(lambda x: 1 if x < 12 else 0)

    # ==========================================
    # 3. MAPEO DE GÉNERO (Para el modelo numérico)
    # ==========================================
    # Si tu CSV ya tiene una columna 'genero', la usamos. Si no, la inferimos
    # o dejamos como 'Desconocido'
    if "genero" not in df.columns:
        df["genero"] = "Desconocido"

    # Label Encoding manual: sin categorías desconocidas perdidas en NaN
    df["genero_encoded"] = (
        df["genero"].astype(str).str.strip().str.lower().map(GENERO_MAP).fillna(5).astype(int)
    )

    # ==========================================
    # 4. GUARDAR RESULTADOS
    # ==========================================
    # Guardamos el CSV principal actualizado (LF, como los robots del repo)
    df.to_csv(csv_path, index=False, encoding="utf-8", lineterminator="\n")
    print(f"✅ ADN Básico agregado a {csv_path}")

    # También actualizamos la tabla de cohorte para que tenga las mismas
    # features predictoras
    cohort_path = os.path.join(REPO_ROOT, "data", "cohort_table.csv")
    if os.path.exists(cohort_path):
        cohort_df = pd.read_csv(cohort_path)

        # Idempotencia: si ya existen (corrida anterior), se regeneran y no
        # aparecen sufijos _x/_y en el merge
        cohort_df = cohort_df.drop(
            columns=[c for c in ADN_COLS if c in cohort_df.columns]
        )

        # Fusionar las nuevas features con la cohorte
        cohort_df = cohort_df.merge(
            df[["artist_name"] + ADN_COLS], on="artist_name", how="left"
        )

        # Rellenar NaNs por si algún artista de la cohorte no está en el CSV
        # principal
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
        print(f"✅ Tabla de cohorte actualizada con nuevas features en {cohort_path}")

    print("🎉 ¡Fase 2 (ADN Básico) completada exitosamente!")


if __name__ == "__main__":
    extraer_adn_basico()
