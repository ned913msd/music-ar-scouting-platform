"""
🕵️ Radar de Fraude: detección de anomalías con Isolation Forest.

Identifica patrones de crecimiento inusuales en el universo scored que
pueden indicar streams falsos (bots), viralidad atípica o crecimiento
orgánico genuino. Features (todas numéricas, del mart de DuckDB):

  * deezer_fans, deezer_rank, top_track_rank → relación audiencia/posición
  * fan_rank_ratio → conversión de oyentes a fans (valores raros huelen a bot)
  * scoring_score → compuesto ponderado que ve el equipo de A&R

Arquitectura (misma que todo el módulo Python): el ML pesado vive en
este script y el dashboard solo consume artefactos:

  * models/isolation_forest_anomalias.pkl → pipeline COMPLETO
    (SimpleImputer + StandardScaler + IsolationForest). Un solo artefacto
    garantiza train/serve consistency: la mediana con la que se imputó el
    train viaja DENTRO del pipeline, así la inferencia futura jamás usa un
    scaler distinto al del entrenamiento (clásico bug de dos archivos).
  * data/anomalias.csv → etiquetas por artista que fusiona app.py (badge
    "Semáforo de Autenticidad" en las cards + vista Radar de Fraude).
    Solo contiene artist_name + las 3 columnas nuevas para que el merge
    no colisione con deezer_fans/scoring_score del mart.

El seed NO se toca: es un contrato de dbt (columnas núcleo) y las
etiquetas de anomalía son derivados, igual que el crecimiento semanal.

Isolation Forest: construye árboles aleatorios y aísla cada muestra;
las que se aíslan con pocas particiones (camino corto desde la raíz) son
anomalías. `contamination` = fracción esperada de anomalías. El
decision_function devuelve valores "cuanto más negativo, más
sospechoso"; su escala NO es universal (depende del número de features
y de la geometría del dataset), por eso los cortes del semáforo unen
los umbrales absolutos del producto (-0.5 / -0.2) con las cortantes
propias de los datos (P1 del score y frontera real del modelo), ver
_calcular_cortes().

Uso:
    python scripts/detectar_anomalias.py
"""

import os
import sys

# Consolas Windows (cp1252) no imprimen emojis: forzar UTF-8 antes de todo
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import bootstrap_db  # noqa: E402
from decoradores import medir_rendimiento  # noqa: E402

MODELOS_DIR = os.path.join(REPO_ROOT, "models")
RUTA_MODELO = os.path.join(MODELOS_DIR, "isolation_forest_anomalias.pkl")
RUTA_CSV = os.path.join(REPO_ROOT, "data", "anomalias.csv")

# Orden fijo: es el orden en que el pipeline espera las columnas en
# predict() — app.py y este script comparten la misma lista.
FEATURES_ANOMALIA = [
    "deezer_fans",
    "deezer_rank",
    "top_track_rank",
    "fan_rank_ratio",
    "scouting_score",
]

# Solo estas columnas viajan al CSV: fusionar más rompería el mart
# (deezer_fans, scoring_score, etc. ya existen en el dashboard).
# Los cortes viajan como columnas constantes para que la vista Radar
# dibuje las líneas exactamente donde se decidió (sin duplicar lógica).
COLS_SALIDA = [
    "artist_name",
    "anomalia",
    "score_anomalia",
    "nivel_riesgo",
    "corte_alerta",
    "corte_revisar",
]

# Umbrales absolutos del producto (piso de severidad, escala cross-dataset)
UMBRAL_ALERTA = -0.5
UMBRAL_REVISAR = -0.2


def _calcular_cortes(scores, predicciones):
    """Cortes del semáforo = unión(umbrales absolutos, datos reales).

    El decision_function de Isolation Forest no tiene escala fija: con 5
    features estandarizadas ninguna puntuación llegaba a -0.2, y el
    modelo aún así marcaba sus `contamination` anomalías → badge verde
    en artistas que el modelo acaba de flaggear (contradicción visible).
    Por eso:
      * corte_revisar = frontera REAL del modelo (la puntuación más alta
        entre las flaggeadas) unida al piso -0.2: TODA anomalía queda
        al menos en ámbar.
      * corte_alerta = P1 del score unido al piso -0.5: el peor 1% del
        universo va a rojo aunque -0.5 jamás se alcance.
    """
    q01 = float(pd.Series(scores).quantile(0.01))
    scores_anom = scores[predicciones == -1]
    frontera = float(pd.Series(scores_anom).max()) if len(scores_anom) else UMBRAL_REVISAR
    corte_alerta = max(q01, UMBRAL_ALERTA)
    corte_revisar = max(frontera, UMBRAL_REVISAR)
    return corte_alerta, corte_revisar


def clasificar_nivel_riesgo(score, corte_alerta, corte_revisar):
    """Semáforo de autenticidad a partir del decision_function.

    🔴 ALERTA: score ≤ corte_alerta (peor 1% o piso -0.5)
    🟡 Revisar: score ≤ corte_revisar (frontera del modelo o piso -0.2)
    🟢 Normal: el resto. Mismos cortes en cards y tabla del Radar.
    """
    if score <= corte_alerta:
        return "🔴 ALERTA"
    if score <= corte_revisar:
        return "🟡 Revisar"
    return "🟢 Normal"


def construir_pipeline(contamination=0.05):
    """Imputer + scaler + IsolationForest como UN artefacto (train/serve)."""
    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "iforest",
                IsolationForest(
                    n_estimators=100,
                    contamination=contamination,
                    random_state=42,
                    verbose=0,
                ),
            ),
        ]
    )


def _cargar_universo():
    """Mart scored desde el warehouse (auto-repara desde el seed si hace falta)."""
    db = bootstrap_db.resolve_db_path()
    bootstrap_db.ensure_database(db)
    bootstrap_db.ensure_table(db)
    conn = bootstrap_db.get_connection(db)
    return pd.read_sql_query("SELECT * FROM artist_scouting_deezer", conn)


@medir_rendimiento
def detectar_anomalias_artistas(contamination=0.05):
    """Entrena Isolation Forest sobre el mart y escribe modelo + CSV.

    Devuelve el DataFrame con las 3 columnas de anomalía para que los
    tests puedan verificar la paridad sin releer archivos.
    """
    print("🕵️ Iniciando detección de anomalías con Isolation Forest...")

    df = _cargar_universo()
    features = [f for f in FEATURES_ANOMALIA if f in df.columns]

    if len(features) < 3:
        print(f"❌ Se encontraron solo {len(features)} features numéricas: {features}")
        print("   Necesitas al menos 3 del mart scored para detectar anomalías.")
        return None

    print(f"📊 Usando {len(features)} features: {features}")

    X = df[features]
    pipeline = construir_pipeline(contamination)
    pipeline.fit(X)

    # Isolation Forest devuelve: 1 = normal, -1 = anomalía
    predicciones = pipeline.predict(X)
    scores = pipeline.decision_function(X)
    corte_alerta, corte_revisar = _calcular_cortes(scores, predicciones)

    resultado = pd.DataFrame(
        {
            "artist_name": df["artist_name"].values,
            "anomalia": predicciones.astype(int),
            "score_anomalia": scores,
            "nivel_riesgo": [
                clasificar_nivel_riesgo(s, corte_alerta, corte_revisar)
                for s in scores
            ],
            "corte_alerta": corte_alerta,
            "corte_revisar": corte_revisar,
        }
    )

    # Artefactos: el pipeline (inferencia futura) y el CSV (dashboard)
    os.makedirs(MODELOS_DIR, exist_ok=True)
    joblib.dump(pipeline, RUTA_MODELO)
    os.makedirs(os.path.dirname(RUTA_CSV), exist_ok=True)
    resultado.to_csv(RUTA_CSV, index=False, encoding="utf-8", lineterminator="\n")
    print(f"✅ Modelo guardado en {RUTA_MODELO}")
    print(f"✅ Etiquetas guardadas en {RUTA_CSV}")

    # Resumen de resultados
    total = len(resultado)
    normales = int((resultado["anomalia"] == 1).sum())
    anomalos = int((resultado["anomalia"] == -1).sum())
    print("\n📊 RESUMEN DE DETECCIÓN:")
    print(f"   Total de artistas analizados: {total}")
    print(f"   🟢 Crecimiento normal: {normales} ({normales / total * 100:.1f}%)")
    print(f"   🔴 Anomalías detectadas: {anomalos} ({anomalos / total * 100:.1f}%)")
    print(f"   ✂️ Cortes: ALERTA ≤ {corte_alerta:.3f} · REVISAR ≤ {corte_revisar:.3f}")
    conteo = resultado["nivel_riesgo"].value_counts()
    print(
        "   🚦 Semáforo: "
        + " · ".join(
            f"{nivel}: {int(conteo.get(nivel, 0))}"
            for nivel in ("🔴 ALERTA", "🟡 Revisar", "🟢 Normal")
        )
    )

    if anomalos > 0:
        print("\n🔍 TOP 5 ARTISTAS CON MAYOR SOSPECHA:")
        top = resultado[resultado["anomalia"] == -1].nsmallest(5, "score_anomalia")
        for _, fila in top.iterrows():
            print(
                f"   - {fila['artist_name']}: Score {fila['score_anomalia']:.3f} "
                f"({fila['nivel_riesgo']})"
            )

    return resultado


if __name__ == "__main__":
    detectar_anomalias_artistas()
