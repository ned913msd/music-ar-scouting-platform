"""
Script para poblar la tabla de cohorte histórica con los artistas actuales.
"""

import os
import sys

# Consolas Windows (cp1252) no imprimen emojis: forzar UTF-8 antes de todo
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def poblar_cohorte_inicial():
    """Crea la cohorte inicial con los 151 artistas actuales"""

    # Leer datos actuales
    csv_path = os.path.join(
        REPO_ROOT, "ar_dbt_project", "seeds", "deezer_artists_data.csv"
    )
    df = pd.read_csv(csv_path)

    # Lista de artistas que ya "explotaron" (breakout conocido)
    # Ajusta estas fechas según tu conocimiento de la industria
    # (se compara en minúsculas: el seed guarda nombres como "KAROL G")
    artistas_breakout = {
        "karol g": "2023-06-15",
        "feid": "2023-09-20",
        "myke towers": "2023-03-10",
        "peso pluma": "2023-04-15",
        "bizarrap": "2023-01-20",
        "quevedo": "2023-07-10",
        "bad bunny": "2022-05-01",
        "shakira": "2022-01-01",
        "j balvin": "2021-06-01",
        "maluma": "2021-03-01",
    }

    # País de origen (solo para los artistas ya conocidos; el resto queda como
    # "Desconocido" y se puede enriquecer después con una tabla maestra).
    artistas_pais = {
        "karol g": "Colombia",
        "feid": "Colombia",
        "ryan castro": "Colombia",
        "bad bunny": "Puerto Rico",
        "shakira": "Colombia",
        "j balvin": "Colombia",
        "maluma": "Colombia",
        "myke towers": "Puerto Rico",
        "young miko": "Puerto Rico",
        "mora": "Puerto Rico",
        "peso pluma": "México",
        "bizarrap": "Argentina",
        "quevedo": "España",
        "saiko": "Perú",
    }

    # Crear tabla de cohorte (start_date se calcula después, ver abajo)
    cohort_data = []

    for idx, row in df.iterrows():
        artist_name = row["artist_name"]
        clave = str(artist_name).strip().lower()

        # Determinar si ya tuvo breakout
        if clave in artistas_breakout:
            event_date = artistas_breakout[clave]
            censored = 0
        else:
            event_date = ""
            censored = 1

        cohort_data.append(
            {
                "artist_id": idx + 1,
                "artist_name": artist_name,
                "event_date": event_date,
                "event_type": "breakout",
                "censored": censored,
                "genero": row.get("genero", "Desconocido"),
                "pais_origen": artistas_pais.get(clave, "Desconocido"),
            }
        )

    # Fecha de inicio de observación: PRIMER DÍA DEL AÑO del evento más
    # antiguo que cae dentro de esta cohorte. Un start_date posterior al
    # evento deja duraciones negativas, inválidas para el modelo de Cox
    # (antes era el placeholder "2024-01-01" y los 6 eventos son de 2023).
    # Solo se miran los artistas que existen en el seed: los del diccionario
    # que no están (Bad Bunny, Shakira…) no entran a la cohorte.
    eventos = [r["event_date"] for r in cohort_data if r["event_date"]]
    if eventos:
        fecha_min = min(pd.to_datetime(eventos))
        start_date = fecha_min.replace(month=1, day=1)
    else:
        start_date = pd.Timestamp.today().replace(month=1, day=1)

    cohort_df = pd.DataFrame(cohort_data)
    cohort_df.insert(2, "start_date", start_date.strftime("%Y-%m-%d"))
    cohort_path = os.path.join(REPO_ROOT, "data", "cohort_table.csv")
    os.makedirs(os.path.dirname(cohort_path), exist_ok=True)
    cohort_df.to_csv(cohort_path, index=False)

    print(f"✅ Cohorte inicial creada: {cohort_path}")
    print(f"🗓  Inicio de observación: {start_date.date()}")
    print(f"📊 Total de artistas: {len(cohort_df)}")
    print(
        f"Artistas con breakout: {len(cohort_df[cohort_df['censored'] == 0])}"
    )
    print(
        "⏳ Artistas censurados (aún no explotan): "
        f"{len(cohort_df[cohort_df['censored'] == 1])}"
    )


if __name__ == "__main__":
    print("🚀 Poblando cohorte histórica inicial...")
    poblar_cohorte_inicial()
