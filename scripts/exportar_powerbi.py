"""
📦 Export corporativo: el "motor" Python alimenta el "tablero" Power BI.

Enfoque híbrido del producto:
  * Python (este pipeline) = cerebro: DuckDB + ML (Random Forest de
    viralidad + Cox de ventana de firma) + dataclasses + generadores.
  * Power BI Desktop = cara corporativa: consume data/output/
    dashboard_data.parquet (y .csv de respaldo) y arma la página
    ejecutiva (KPIs · mapa de Touring · tabla de ventana de firma ·
    barras de fans por género).

Parquet es el formato nativo de intercambio: columnar, comprimido y
tipado — Power BI lo lee mucho más rápido que CSV y preserva bool/Int64
nullable. El CSV queda como fallback universal.

El dataset exportado replica la misma enrichement del dashboard
(app.py::cargar_dataset): mart scored + features ADN + probabilidad
viral (RF) + predicciones Cox + país de la cohorte + crecimiento
semanal, más la bandera `es_firma_inmediata` calculada con el
dataclass PerfilArtista (el mismo contrato que usan las alertas).

Uso:
    python scripts/exportar_powerbi.py
"""

import os
import sys

# Consolas Windows (cp1252) no imprimen emojis: forzar UTF-8 antes de todo
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import joblib
import numpy as np
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import bootstrap_db  # noqa: E402
from decoradores import medir_rendimiento  # noqa: E402
from perfiles import iterar_perfiles  # noqa: E402
from prediccion_ventana_firma import FEATURES as COX_FEATURES  # noqa: E402
from prediccion_ventana_firma import cargar_modelo as cargar_modelo_cox  # noqa: E402
from prediccion_ventana_firma import predecir_lote  # noqa: E402

DIR_SALIDA = os.path.join(REPO_ROOT, "data", "output")
RUTA_PARQUET = os.path.join(DIR_SALIDA, "dashboard_data.parquet")
RUTA_CSV = os.path.join(DIR_SALIDA, "dashboard_data.csv")
RUTA_COHORTE = os.path.join(REPO_ROOT, "data", "cohort_table.csv")
RUTA_CRECIMIENTO = os.path.join(REPO_ROOT, "data", "crecimiento_semanal.csv")
RUTA_SEED = os.path.join(
    REPO_ROOT, "ar_dbt_project", "seeds", "deezer_artists_data.csv"
)

# Columnas del crecimiento semanal que se fusionan (sin colisionar con
# deezer_fans del mart: ese nombre ya existe en el universo).
COLS_CRECIMIENTO = [
    "artist_name",
    "fans_semana_anterior",
    "crecimiento_absoluto",
    "crecimiento_pct",
    "dias_desde_anterior",
    "snapshots_en_historial",
    "tendencia",
]


def _cargar_universo() -> pd.DataFrame:
    """Mart scored desde el warehouse (auto-repara desde el seed si hace falta)."""
    db = bootstrap_db.resolve_db_path()
    bootstrap_db.ensure_database(db)
    bootstrap_db.ensure_table(db)
    conn = bootstrap_db.get_connection(db)
    return pd.read_sql_query("SELECT * FROM artist_scouting_deezer", conn)


def _merge_adn(data: pd.DataFrame) -> pd.DataFrame:
    """Features ADN del seed (el mart scored no las incluye; el Cox las exige)."""
    faltantes = [c for c in COX_FEATURES if c not in data.columns]
    if not faltantes:
        return data
    seed = pd.read_csv(RUTA_SEED)
    columnas = ["artist_name"] + [c for c in faltantes if c in seed.columns]
    return data.merge(seed[columnas], on="artist_name", how="left")


def _probabilidad_viral(data: pd.DataFrame) -> pd.Series:
    """Random Forest de viralidad 6M (%). Sin el modelo la columna sale NaN."""
    try:
        modelo = joblib.load(os.path.join(REPO_ROOT, "modelo_viralidad_rf.pkl"))
        feature_names = joblib.load(os.path.join(REPO_ROOT, "feature_names.pkl"))
    except FileNotFoundError:
        print("⚠️  Modelo RF ausente: probabilidad_viral = NaN.")
        return pd.Series(np.nan, index=data.index, name="probabilidad_viral")

    # Mismo proxy de crecimiento calibrado al dominio de entrenamiento
    # que usa el dashboard (app.py::_probabilidades_virales).
    growth_proxy = (data["fan_rank_ratio"] / 15.0).clip(-0.05, 0.30)
    X = pd.DataFrame(
        {
            "current_fans": data["deezer_fans"],
            "current_rank": data["deezer_rank"],
            "track_rank": data["top_track_rank"],
            "monthly_growth_rate": growth_proxy,
            "genero_encoded": 0,
        }
    )[feature_names]
    probs = (modelo.predict_proba(X)[:, 1] * 100).round(1)
    return pd.Series(probs, index=data.index, name="probabilidad_viral")


def _predicciones_cox(data: pd.DataFrame) -> pd.DataFrame:
    """Cox: prob breakout 6M (%), ventana y riesgo. Sin lifelines → NaN."""
    cph = cargar_modelo_cox()
    if cph is None or any(c not in data.columns for c in COX_FEATURES):
        print("⚠️  Modelo Cox o features ausentes: columnas Cox = NaN.")
        out = pd.DataFrame(index=data.index)
        out["prob_breakout_6m"] = np.nan
        out["mes_optimo_firma"] = pd.array([pd.NA] * len(data), dtype="Int64")
        out["mes_pico_riesgo"] = pd.array([pd.NA] * len(data), dtype="Int64")
        out["pico_riesgo_mensual"] = np.nan
        out["riesgo"] = "—"
        return out
    pred = predecir_lote(cph, data[COX_FEATURES]).copy()
    pred["prob_breakout_6m"] = (pred["prob_breakout_6m"] * 100).round(1)
    return pred


def _merge_pais(data: pd.DataFrame) -> pd.DataFrame:
    cohorte = pd.read_csv(RUTA_COHORTE, usecols=["artist_name", "pais_origen"])
    cohorte = cohorte.drop_duplicates("artist_name")
    data = data.merge(cohorte, on="artist_name", how="left")
    data["pais_origen"] = data["pais_origen"].fillna("Desconocido")
    return data


def _merge_crecimiento(data: pd.DataFrame) -> pd.DataFrame:
    if not os.path.exists(RUTA_CRECIMIENTO):
        return data
    crec = pd.read_csv(RUTA_CRECIMIENTO, usecols=COLS_CRECIMIENTO)
    return data.merge(crec, on="artist_name", how="left")


def _bandera_firma(data: pd.DataFrame) -> pd.Series:
    """es_firma_inmediata vía el dataclass (mismo contrato que las alertas)."""
    return pd.Series(
        [p.es_firma_inmediata() for p in iterar_perfiles(data)],
        index=data.index,
        name="es_firma_inmediata",
    )


@medir_rendimiento
def exportar_powerbi() -> pd.DataFrame:
    """Construye el dataset corporativo y lo escribe en Parquet + CSV."""
    data = _cargar_universo()
    data = _merge_adn(data)
    data["probabilidad_viral"] = _probabilidad_viral(data)
    data = pd.concat([data, _predicciones_cox(data)], axis=1)
    data = _merge_pais(data)
    data = _merge_crecimiento(data)
    data["es_firma_inmediata"] = _bandera_firma(data)
    data = data.sort_values("scouting_score", ascending=False).reset_index(
        drop=True
    )

    os.makedirs(DIR_SALIDA, exist_ok=True)
    data.to_parquet(RUTA_PARQUET, index=False)  # formato nativo para Power BI
    data.to_csv(RUTA_CSV, index=False, encoding="utf-8", lineterminator="\n")

    kb_pq = os.path.getsize(RUTA_PARQUET) / 1024
    kb_csv = os.path.getsize(RUTA_CSV) / 1024
    print(f"✅ {len(data)} artistas · {len(data.columns)} columnas")
    print(f"📦 Parquet: {RUTA_PARQUET} ({kb_pq:.1f} KB)")
    print(f"📄 CSV:     {RUTA_CSV} ({kb_csv:.1f} KB)")
    n_firma = int(data["es_firma_inmediata"].sum())
    n_ventana = int(data["mes_optimo_firma"].notna().sum())
    print(f"🔥 es_firma_inmediata: {n_firma} · con ventana de firma: {n_ventana}")
    return data


if __name__ == "__main__":
    exportar_powerbi()
