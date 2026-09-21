#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================
# ar_scouting_pipeline.py
# Music A&R Data Product | Fase 1: Extract + Load (simulación de API musical)
#
# Simula la extracción de una API de monitoreo (Chartmetric / Soundcharts) y
# carga los datos CRUDOS en DuckDB. La transformación (limpieza + Scouting
# Score + clasificación) vive en dbt: ar_dbt_project/models/marts/artist_scouting.sql
# → patrón ELT auditable, igual que el producto SEO.
#
# Ejecutar:
#   python pipeline/ar_scouting_pipeline.py
#   python pipeline/ar_scouting_pipeline.py --db "ruta\a\music_ar_product.duckdb"
# Override por entorno:  MUSIC_AR_DB_PATH
# ============================================================================

import argparse
import os
import sys

import duckdb
import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# Consolas Windows (cp1252) no imprimen emojis: forzamos UTF-8 en stdout/stderr
# ----------------------------------------------------------------------------
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ----------------------------------------------------------------------------
# Rutas unificadas (mismo contrato que el producto SEO):
# prioridad --db > MUSIC_AR_DB_PATH > BASES DE DATOS DE PRUEBAS/...
# ----------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DESKTOP = os.path.dirname(os.path.dirname(SCRIPT_DIR))       # ...\Desktop
DEFAULT_DB = os.path.join(DESKTOP, "BASES DE DATOS DE PRUEBAS",
                          "music_ar_product.duckdb")


def resolve_db_path(cli_value=None):
    path = cli_value or os.environ.get("MUSIC_AR_DB_PATH") or DEFAULT_DB
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    return path


# ==========================================
# 1. EXTRACT (Simulación de API de Música)
# ==========================================
def extraer_datos_artistas(cantidad=50):
    np.random.seed(42)
    nombres_artistas = [f"Artista_{i}" for i in range(cantidad)]

    data = {
        'artist_name': nombres_artistas,
        'genre': np.random.choice(['Pop', 'Urbano', 'Indie', 'Electrónica', 'Folk'], cantidad),
        'spotify_monthly_listeners': np.random.randint(1000, 500000, cantidad),
        'spotify_followers': np.random.randint(500, 100000, cantidad),
        'spotify_save_rate': np.random.uniform(0.01, 0.15, cantidad),   # Tasa de guardado (CRUCIAL para A&R)
        'spotify_skip_rate': np.random.uniform(0.10, 0.60, cantidad),   # Tasa de salto (Mala si es alta)
        'tiktok_video_posts': np.random.randint(10, 5000, cantidad),    # Cuántos videos usan su sonido
        'tiktok_total_views': np.random.randint(10000, 10000000, cantidad),
        'growth_rate_30d': np.random.uniform(-0.05, 0.50, cantidad)     # Crecimiento mensual
    }

    df = pd.DataFrame(data)

    # Simular datos sucios (típico en la industria)
    df.loc[5:8, 'spotify_save_rate'] = np.nan
    df.loc[12, 'spotify_skip_rate'] = 1.5  # Error de API (no puede ser mayor a 1)

    return df


# ==========================================
# 3. LOAD (Cargar crudo en DuckDB — el T lo hace dbt)
# ==========================================
def cargar_datos(df, db_path):
    conn = duckdb.connect(db_path)
    try:
        conn.register("df_artists", df)
        conn.execute("DROP TABLE IF EXISTS raw_artists_data")
        conn.execute("CREATE TABLE raw_artists_data AS SELECT * FROM df_artists")
        n = conn.execute("SELECT COUNT(*) FROM raw_artists_data").fetchone()[0]
    finally:
        conn.close()
    print(f"✅ Pipeline completado. {n} artistas crudos cargados en DuckDB.")
    print(f"   Base de datos: {db_path}")
    print("   ℹ️  La limpieza y el Scouting Score viven en dbt (marts/artist_scouting.sql).")


def main():
    parser = argparse.ArgumentParser(description="A&R Scouting Pipeline (Extract + Load a DuckDB)")
    parser.add_argument("--db", default=None,
                        help="Ruta del .duckdb (default: BASES DE DATOS DE PRUEBAS/music_ar_product.duckdb)")
    parser.add_argument("--cantidad", type=int, default=50,
                        help="Cantidad de artistas a simular (default: 50)")
    args = parser.parse_args()

    db_path = resolve_db_path(args.db)

    print("🚀 Iniciando A&R Scouting Pipeline (ELT)...")
    df_raw = extraer_datos_artistas(args.cantidad)
    cargar_datos(df_raw, db_path)


if __name__ == "__main__":
    main()
