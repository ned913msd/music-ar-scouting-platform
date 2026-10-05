"""
Predice la ventana de firma óptima de un artista con el modelo de Cox
entrenado en scripts/entrenar_modelo_cox.py.

Uso:
    python scripts/prediccion_ventana_firma.py "Karol G"
    python scripts/prediccion_ventana_firma.py            # por defecto: Karol G

Salida: probabilidad de breakout a 6 meses, mes óptimo de firma, pico de
riesgo mensual y clasificación de riesgo.

NOTA técnica: lifelines NO implementa predict_hazard() para CoxPH con
baseline de Breslow (lanza NotImplementedError). El riesgo se deriva aquí
de la curva de supervivencia:  h(t_k) = 1 - S(t_k) / S(t_k-1)  (hazard
condicional mensual), que es exactamente la misma información.
"""

import os
import sys
import unicodedata

# Consolas Windows (cp1252) no imprimen emojis: forzar UTF-8 antes de todo
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import joblib
import numpy as np
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FEATURES = [
    "ratio_fans_rank",
    "top_track_dominance",
    "es_solista",
    "nombre_corto",
    "genero_encoded",
]

# Rejilla mensual: horizonte de 12 meses (mes 1 = días 0-30, mes 12 = 330-360)
TIMES = list(range(0, 361, 30))


def _normalizar(texto):
    """Minúsculas + sin acentos, para comparar nombres de artista."""
    texto = unicodedata.normalize("NFKD", str(texto).strip().lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def _clasificar_riesgo(prob):
    if prob < 0.10:
        return "Bajo"
    if prob < 0.30:
        return "Medio"
    return "Alto"


def predecir_ventana_firma(nombre_artista):
    """Devuelve el dict de predicción para un artista (None si no existe)."""

    model_path = os.path.join(REPO_ROOT, "models", "cox_model.pkl")
    seed_path = os.path.join(
        REPO_ROOT, "ar_dbt_project", "seeds", "deezer_artists_data.csv"
    )
    for path in (model_path, seed_path):
        if not os.path.exists(path):
            print(f"❌ Error: no se encontró {path}")
            return None

    cph = joblib.load(model_path)
    df = pd.read_csv(seed_path)

    faltantes = [c for c in FEATURES if c not in df.columns]
    if faltantes:
        print(f"❌ Error: faltan columnas {faltantes} en el seed.")
        print("   Corre scripts/extraer_adn_basico.py primero.")
        return None

    # El seed guarda el nombre en mayúsculas ("KAROL G"): comparar sin
    # distinción de mayúsculas ni acentos para que "Karol G" coincida.
    objetivo = _normalizar(nombre_artista)
    coincide = df["artist_name"].map(_normalizar) == objetivo
    if not coincide.any():
        print(f"❌ No se encontró el artista '{nombre_artista}' en el seed.")
        return None

    fila = df.loc[coincide].iloc[0]
    features_df = pd.DataFrame(
        [fila[FEATURES].astype(float).tolist()], columns=FEATURES, dtype=float
    )

    # --- Supervivencia --------------------------------------------------
    # H0 como función escalonada (Breslow) y no con predict_survival_function,
    # que interpola linealmente fuera del rango de eventos y devuelve
    # S(0) < 1. Misma fórmula que scripts/entrenar_modelo_cox.py.
    base = cph.baseline_cumulative_hazard_.iloc[:, 0]
    idx = base.index.to_numpy(dtype=float)
    vals = base.to_numpy(dtype=float)
    pos = np.searchsorted(idx, np.asarray(TIMES, dtype=float), side="right") - 1
    H0 = np.where(pos >= 0, vals[np.clip(pos, 0, None)], 0.0)
    ph = float(cph.predict_partial_hazard(features_df).iloc[0])
    S = np.exp(-H0 * ph)

    # Hazard condicional mensual: h_k = 1 - S(t_k)/S(t_k-1)
    riesgo_mensual = np.zeros(len(S))
    riesgo_mensual[1:] = 1.0 - S[1:] / np.where(S[:-1] > 0, S[:-1], np.nan)
    riesgo_mensual = np.nan_to_num(riesgo_mensual)

    prob_breakout_6m = float(1.0 - S[6])  # S(180 días) = mes 6
    mes = int(np.argmax(riesgo_mensual))  # índice 1..12
    pico_riesgo = float(riesgo_mensual[mes])
    # Sin riesgo dentro de los 12 meses: no hay mes pico que reportar
    mes_optimo_firma = max(mes, 1) if pico_riesgo > 1e-12 else None

    resultado = {
        "artista": fila["artist_name"],
        "prob_breakout_6m": round(prob_breakout_6m, 4),
        "mes_optimo_firma": mes_optimo_firma,
        "pico_riesgo_mensual": round(pico_riesgo, 4),
        "riesgo": _clasificar_riesgo(prob_breakout_6m),
        "features": features_df.iloc[0].to_dict(),
    }

    print(f"\n🪧 Ventana de firma óptima para {resultado['artista']}")
    print(f"   ▶ Probabilidad de breakout a 6 meses: {prob_breakout_6m:.2%}")
    if mes_optimo_firma is None:
        print("   ▶ Mes óptimo de firma: sin riesgo dentro de los 12 meses")
        print("   ▶ Pico de riesgo mensual: 0.00%")
    else:
        print(f"   ▶ Mes óptimo de firma: mes {mes_optimo_firma}")
        print(
            f"   ▶ Pico de riesgo mensual: {pico_riesgo:.2%} "
            f"(mes {mes_optimo_firma})"
        )
    print(f"   ▶ Clasificación de riesgo: {resultado['riesgo']}")
    print("   ▶ Features usadas:")
    for k in FEATURES:
        print(f"        {k:<22} {features_df.iloc[0][k]:.4f}")
    print()
    return resultado


if __name__ == "__main__":
    nombre = sys.argv[1] if len(sys.argv) > 1 else "Karol G"
    if predecir_ventana_firma(nombre) is None:
        sys.exit(1)
