"""
Entrena el modelo de supervivencia de Cox (Fase 3): estima la probabilidad de
que un artista sufra un "breakout" a lo largo del tiempo y en qué momento
pega el riesgo.

Entrada : data/cohort_table.csv   (start_date, event_date, censored + features ADN)
Salida  : models/cox_model.pkl       modelo lifelines serializado con joblib
          models/survival_curve.png  curva de supervivencia de la cohorte

Uso: python scripts/entrenar_modelo_cox.py

NOTA (importante): el start_date de la cohorte es un placeholder (2024-01-01)
posterior a los eventos históricos (2023), lo que deja duraciones negativas e
inválidas para Cox. Este script por eso define un origen de estudio común
anterior a todos los eventos y lo reporta en el log. La corrección definitiva
es ajustar start_date en poblar_cohorte.py.
"""

import os
import sys
import warnings

# Consolas Windows (cp1252) no imprimen emojis: forzar UTF-8 antes de todo
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Backend sin GUI: la figura se guarda a PNG y nunca abre ventanas
# (obligatorio en CI/headless; en Windows evita congelar el proceso)
import matplotlib

matplotlib.use("Agg")

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from lifelines import CoxPHFitter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Features del ADN Básico (deben coincidir con scripts/extraer_adn_basico.py
# y con scripts/prediccion_ventana_firma.py, si no el modelo no se puede usar)
FEATURES = [
    "ratio_fans_rank",
    "top_track_dominance",
    "es_solista",
    "nombre_corto",
    "genero_encoded",
]

# Origen del estudio: fecha a la que entran los artistas a la observación.
# Debe ser anterior a TODOS los eventos para que la duración T >= 0, y lo
# bastante cercano para que los eventos caigan dentro del horizonte de
# predicción de 12 meses. Se deriva de los datos: primer día del año del
# evento más antiguo (2023-01-01 con la cohorte actual).
def calcular_origen(df):
    fechas = pd.concat([df["start_date"], df["event_date"].dropna()])
    fecha_min = fechas.min()
    origen = fecha_min.replace(
        month=1, day=1, hour=0, minute=0, second=0, microsecond=0
    )
    if (df["event_date"].dropna() < origen).any():
        origen = df["event_date"].min() - pd.Timedelta(days=1)
    return origen


def entrenar_modelo_cox():
    """Entrena el modelo Cox y lo guarda en models/. Devuelve el modelo."""

    print("🎯 Entrenando modelo de supervivencia de Cox...")

    cohort_path = os.path.join(REPO_ROOT, "data", "cohort_table.csv")
    if not os.path.exists(cohort_path):
        print(f"❌ Error: no se encontró {cohort_path}")
        return None

    df = pd.read_csv(cohort_path)
    print(f"📊 Cohorte cargada: {len(df)} artistas")

    faltantes = [c for c in FEATURES if c not in df.columns]
    if faltantes:
        print(f"❌ Error: faltan columnas {faltantes} en la cohorte.")
        print("   Corre scripts/extraer_adn_basico.py y scripts/poblar_cohorte.py")
        return None

    df["start_date"] = pd.to_datetime(df["start_date"])
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")

    # --- Duraciones (T) y evento (E) -------------------------------------
    # Origen de estudio: nunca posterior a la fecha más antigua de la cohorte
    origen = calcular_origen(df)

    previos = df["event_date"].notna() & (df["event_date"] < df["start_date"])
    if previos.any():
        print(
            f"⚠️  {int(previos.sum())} eventos son anteriores al start_date "
            f"({df['start_date'].dt.date.iloc[0]}) y dejarían T negativo."
        )
    print(
        f"🗓  Origen del estudio: {origen.date()} "
        "(primer día del año del evento más antiguo)"
    )

    fin = df["event_date"].fillna(pd.Timestamp.today().normalize())
    df["T"] = (fin - origen).dt.days.clip(lower=1).astype(float)
    df["E"] = (1 - df["censored"].astype(int)).clip(0, 1).astype(float)

    dentro_12m = int(((df["E"] == 1) & (df["T"] <= 360)).sum())
    if dentro_12m == 0:
        print(
            "⚠️  Ningún evento cae dentro de los primeros 360 días desde el "
            "origen: la probabilidad de breakout a 6 meses saldrá 0%."
        )
    else:
        print(f"📅 Eventos dentro del horizonte de 12 meses: {dentro_12m}")

    df_cox = (
        df[FEATURES + ["T", "E"]]
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
        .astype(float)
    )
    if df_cox.empty:
        print("❌ Error: no quedan filas limpias para entrenar.")
        return None

    n_eventos = int(df_cox["E"].sum())
    print(
        f"📉 Datos para Cox: {len(df_cox)} artistas · {n_eventos} eventos · "
        f"T {df_cox['T'].min():.0f}-{df_cox['T'].max():.0f} días"
    )
    if n_eventos < 20:
        print(
            f"⚠️  {n_eventos} eventos para {len(FEATURES)} covariables: el modelo "
            "no tiene potencia estadística (se recomienda ≥10-20 eventos por "
            "variable). Úsalo como demo, no como decisión real de firma."
        )

    # --- Ajuste ---------------------------------------------------------
    cph = CoxPHFitter(penalizer=0.1)
    with warnings.catch_warnings(record=True) as capturadas:
        warnings.simplefilter("always")
        cph.fit(df_cox, duration_col="T", event_col="E")
    for w in capturadas:
        print(f"⚠️  {w.category.__name__}: {str(w.message).splitlines()[0]}")

    print("\n" + "=" * 64)
    print("📊 RESUMEN DEL MODELO DE COX")
    print("=" * 64)
    cph.print_summary()

    print("\n📊 Hazard ratios (riesgo relativo de breakout):")
    for feat in FEATURES:
        hr = float(np.exp(cph.params_[feat]))
        direccion = "↑" if hr > 1 else "↓"
        print(f"   {direccion} {feat:<22} HR = {hr:>6.3f}")

    # --- Artefactos -----------------------------------------------------
    models_dir = os.path.join(REPO_ROOT, "models")
    os.makedirs(models_dir, exist_ok=True)
    model_path = os.path.join(models_dir, "cox_model.pkl")
    joblib.dump(cph, model_path)
    print(f"\n✅ Modelo guardado: {model_path}")

    _graficar_supervivencia(cph, df, model_path)
    return cph


def curvas_supervivencia(cph, dfx, times):
    """S(t) por sujeto usando el paso de Breslow (sin interpolar).

    lifelines interpola linealmente la curva fuera del rango de eventos, lo
    que deja S(0) < 1 y distorsiona las probabilidades. Aquí se evalúa el
    acumulado como función escalonada: H0(t) = H0(último evento <= t).
    """
    base = cph.baseline_cumulative_hazard_.iloc[:, 0]
    idx = base.index.to_numpy(dtype=float)
    vals = base.to_numpy(dtype=float)
    pos = np.searchsorted(idx, np.asarray(times, dtype=float), side="right") - 1
    H0 = np.where(pos >= 0, vals[np.clip(pos, 0, None)], 0.0)
    ph = cph.predict_partial_hazard(dfx).to_numpy(dtype=float)
    return np.exp(-np.outer(ph, H0))


def _graficar_supervivencia(cph, df, model_path):
    """Guarda la curva de supervivencia de la cohorte en models/."""

    times = list(range(0, int(df["T"].max()) + 31, 30))
    dfx = df[FEATURES].astype(float)
    curvas = curvas_supervivencia(cph, dfx, times)  # (sujetos, tiempos)
    promedio = curvas.mean(axis=0)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.plot(times, curvas.T, color="0.78", alpha=0.25, linewidth=0.8)
    ax.plot(
        times,
        promedio,
        color="#e63946",
        linewidth=2.5,
        label="Promedio de la cohorte",
    )
    ax.set_title(
        "Supervivencia — Probabilidad de NO haber hecho breakout (Cox)",
        fontsize=13,
        fontweight="bold",
    )
    ax.set_xlabel("Días desde el inicio del estudio")
    ax.set_ylabel("Probabilidad de NO breakout")
    ax.set_ylim(0, 1.02)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower left")

    png_path = os.path.join(os.path.dirname(model_path), "survival_curve.png")
    fig.savefig(png_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"📈 Curva guardada: {png_path}")


if __name__ == "__main__":
    if entrenar_modelo_cox() is None:
        sys.exit(1)
