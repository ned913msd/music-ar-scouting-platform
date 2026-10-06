"""
Predice la ventana de firma óptima de un artista con el modelo de Cox
entrenado en scripts/entrenar_modelo_cox.py.

Uso (CLI):
    python scripts/prediccion_ventana_firma.py "Karol G"
    python scripts/prediccion_ventana_firma.py            # por defecto: Karol G

Salida: probabilidad de breakout a 6 meses, mes óptimo de firma (ventana
límite POR ARTISTA: mes en que su riesgo acumulado cruza el 10%, o "—" si
no lo cruza en el año), mes del pico de riesgo poblacional y clasificación
de riesgo.

La app (app.py) reutiliza este mismo módulo: `predecir_lote()` devuelve las
tres columnas para todo el universo en un solo paso vectorizado.

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
MES_BREAKOUT = TIMES.index(180)  # índice de los 180 días = mes 6
UMBRAL_PICO = 1e-12  # por debajo: el mes pico no existe (riesgo nulo)
# Mismo corte que clasificar_riesgo(): por debajo de 10% el riesgo es "Bajo"
UMBRAL_RIESGO = 0.10


def cargar_modelo():
    """Carga models/cox_model.pkl (None si no existe o lifelines no está)."""
    ruta = os.path.join(REPO_ROOT, "models", "cox_model.pkl")
    if not os.path.exists(ruta):
        return None
    try:
        return joblib.load(ruta)
    except Exception:
        return None


def _normalizar(texto):
    """Minúsculas + sin acentos, para comparar nombres de artista."""
    texto = unicodedata.normalize("NFKD", str(texto).strip().lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def clasificar_riesgo(prob):
    """Umbrales del producto: 6M breakout <10% Bajo · <30% Medio · resto Alto."""
    if prob < 0.10:
        return "Bajo"
    if prob < 0.30:
        return "Medio"
    return "Alto"


def curva_supervivencia(cph, X, times=None):
    """S(t) por sujeto usando el paso de Breslow (sin interpolar).

    lifelines interpola linealmente la curva fuera del rango de eventos, lo
    que deja S(0) < 1 y distorsiona las probabilidades. Aquí se evalúa el
    acumulado como función escalonada: H0(t) = H0(último evento <= t).
    Devuelve un array (sujetos, tiempos).
    """
    times = TIMES if times is None else times
    base = cph.baseline_cumulative_hazard_.iloc[:, 0]
    idx = base.index.to_numpy(dtype=float)
    vals = base.to_numpy(dtype=float)
    pos = np.searchsorted(idx, np.asarray(times, dtype=float), side="right") - 1
    H0 = np.where(pos >= 0, vals[np.clip(pos, 0, None)], 0.0)
    ph = cph.predict_partial_hazard(X).to_numpy(dtype=float)
    return np.exp(-np.outer(ph, H0))


def riesgo_mensual(S):
    """Hazard condicional mensual h_k = 1 - S(t_k)/S(t_k-1) por sujeto."""
    riesgo = np.zeros_like(S)
    anterior = np.where(S[:, :-1] > 0, S[:, :-1], np.nan)
    riesgo[:, 1:] = 1.0 - S[:, 1:] / anterior
    return np.nan_to_num(riesgo)


def mes_cruce_riesgo(S, umbral=UMBRAL_RIESGO):
    """Primer mes en que la prob. acumulada de breakout cruza `umbral`.

    En Cox el riesgo es proporcional: la FORMA temporal (mes del pico) la
    comparte toda la población, así que el mes pico sale igual para todos.
    Lo que sí difiere por artista es el NIVEL de riesgo (partial hazard), y
    por eso se mide contra un umbral absoluto: el mes en que el artista deja
    de ser "Riesgo Bajo" (>10%, el mismo corte que usa clasificar_riesgo).

    Devuelve (mes, prob_acumulada_12m): mes 1..12, o 0 si no cruza el umbral
    dentro del año (su riesgo se mantiene Bajo los 12 meses).
    """
    acumulada = 1.0 - S  # prob. acumulada de breakout por mes (sujetos, 13)
    anual = acumulada[:, -1]
    cruza = acumulada >= umbral
    cruza[:, 0] = False  # el mes 0 (t=0) no cuenta
    mes = np.where(anual >= umbral, cruza.argmax(axis=1), 0)
    return mes, anual


def predecir_lote(cph, X):
    """Predice para todo un DataFrame con las columnas FEATURES.

    Devuelve prob_breakout_6m (0-1), mes_optimo_firma (1-12 o NA si no hay
    riesgo en el año), mes_pico_riesgo (mes del pico poblacional),
    pico_riesgo_mensual y riesgo. Las filas sin features completas quedan
    como NaN / '—' en vez de romper el lote.
    """
    features = X[FEATURES].astype(float)
    valido = np.isfinite(features.to_numpy()).all(axis=1)

    prob = np.full(len(features), np.nan)
    pico = np.full(len(features), np.nan)
    mes = np.zeros(len(features), dtype=int)
    mes_pico = np.zeros(len(features), dtype=int)
    riesgo = np.array(["—"] * len(features), dtype=object)

    if valido.any():
        S = curva_supervivencia(cph, features.loc[valido])
        h = riesgo_mensual(S)
        mes_crudo = h.argmax(axis=1)
        prob_v = 1.0 - S[:, MES_BREAKOUT]
        pico_v = h[np.arange(len(mes_crudo)), mes_crudo]
        # h[:, k] cubre los días ((k-1)*30, k*30] → el índice ya ES el mes
        mes_v = np.where(pico_v > UMBRAL_PICO, mes_crudo, 0)
        # Ventana de firma POR ARTISTA: mes en que su riesgo cruza el 10%
        limite_v, _ = mes_cruce_riesgo(S)

        prob[valido] = prob_v
        pico[valido] = pico_v
        mes[valido] = limite_v
        mes_pico[valido] = mes_v
        riesgo[valido] = [clasificar_riesgo(p) for p in prob_v]

    mes_col = pd.Series(mes, index=features.index, dtype="Int64").replace(0, pd.NA)
    pico_col = (
        pd.Series(mes_pico, index=features.index, dtype="Int64").replace(0, pd.NA)
    )
    return pd.DataFrame(
        {
            "prob_breakout_6m": prob.round(4),
            "mes_optimo_firma": mes_col,
            "mes_pico_riesgo": pico_col,
            "pico_riesgo_mensual": pico.round(4),
            "riesgo": riesgo,
        },
        index=features.index,
    )


def predecir_ventana_firma(nombre_artista):
    """Devuelve el dict de predicción para un artista (None si no existe)."""

    seed_path = os.path.join(
        REPO_ROOT, "ar_dbt_project", "seeds", "deezer_artists_data.csv"
    )
    for path in (
        os.path.join(REPO_ROOT, "models", "cox_model.pkl"),
        seed_path,
    ):
        if not os.path.exists(path):
            print(f"❌ Error: no se encontró {path}")
            return None

    cph = cargar_modelo()
    if cph is None:
        print("❌ Error: no se pudo cargar el modelo Cox (¿falta lifelines?).")
        return None
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

    pred = predecir_lote(cph, features_df).iloc[0]
    prob = float(pred["prob_breakout_6m"])
    pico = float(pred["pico_riesgo_mensual"])
    mes = None if pd.isna(pred["mes_optimo_firma"]) else int(pred["mes_optimo_firma"])
    mes_pico = None if pd.isna(pred["mes_pico_riesgo"]) else int(pred["mes_pico_riesgo"])

    resultado = {
        "artista": fila["artist_name"],
        "prob_breakout_6m": round(prob, 4),
        "mes_optimo_firma": mes,
        "mes_pico_riesgo": mes_pico,
        "pico_riesgo_mensual": round(pico, 4),
        "riesgo": pred["riesgo"],
        "features": features_df.iloc[0].to_dict(),
    }

    print(f"\n🪧 Ventana de firma óptima para {resultado['artista']}")
    print(f"   ▶ Probabilidad de breakout a 6 meses: {prob:.2%}")
    if mes is None:
        print("   ▶ Mes óptimo de firma: su riesgo no cruza el 10% en 12 meses")
    else:
        print(
            f"   ▶ Mes óptimo de firma: mes {mes} "
            f"(su riesgo acumulado cruza el 10% ahí)"
        )
    if mes_pico is None:
        print("   ▶ Pico de riesgo: 0.00%")
    else:
        print(
            f"   ▶ Pico de riesgo poblacional: mes {mes_pico} · "
            f"{pico:.2%} (igual para toda la cohorte: riesgo proporcional)"
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
