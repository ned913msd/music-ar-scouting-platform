"""
Script para guardar snapshots semanales de la base de datos de artistas.
Este script se ejecuta automáticamente vía GitHub Actions cada semana.
"""

import os
import sys
from datetime import datetime

# Consolas Windows (cp1252) no imprimen emojis: forzar UTF-8 antes de todo
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def guardar_snapshot_semanal():
    """Guarda un snapshot de los datos actuales con timestamp"""

    # Rutas
    csv_path = os.path.join(
        REPO_ROOT, "ar_dbt_project", "seeds", "deezer_artists_data.csv"
    )
    snapshot_dir = os.path.join(REPO_ROOT, "data", "snapshots")

    # Verificar que el CSV principal exista
    if not os.path.exists(csv_path):
        print(f"❌ Error: No se encontró {csv_path}")
        return False

    # Crear directorio de snapshots si no existe
    os.makedirs(snapshot_dir, exist_ok=True)

    # Leer datos actuales
    df = pd.read_csv(csv_path)

    # Agregar columna de fecha de snapshot
    fecha_actual = datetime.now().strftime("%Y-%m-%d")
    df["snapshot_date"] = fecha_actual

    # Guardar snapshot con nombre timestamped
    snapshot_filename = f"snapshot_{datetime.now().strftime('%Y%m%d')}.csv"
    snapshot_path = os.path.join(snapshot_dir, snapshot_filename)

    df.to_csv(snapshot_path, index=False)

    print(f"✅ Snapshot guardado exitosamente: {snapshot_path}")
    print(f"📊 Total de artistas en el snapshot: {len(df)}")
    print(f"📅 Fecha del snapshot: {fecha_actual}")

    return True


if __name__ == "__main__":
    print("🚀 Iniciando proceso de snapshot semanal...")
    guardar_snapshot_semanal()
