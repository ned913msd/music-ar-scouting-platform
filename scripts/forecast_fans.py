#!/usr/bin/env python3
# ============================================================================
# forecast_fans.py
# A&R Scouting Command Center | Forecasting de crecimiento de fans (Módulo 5)
#
# Qué hace:
#   Proyecta el crecimiento de fans de un artista a 6 meses y genera el
#   gráfico que el dashboard de Streamlit muestra en el panel de Forecasting.
#
# Estrategia de motor (decisión de ingeniería, no de tutorial):
#   * Prophet (Meta) si está instalado y funciona → estacionalidad + bandas.
#   * Fallback transparente a LinearRegression (scikit-learn) con banda de
#     confianza 95% por residuos, si Prophet no está disponible o falla en el
#     entorno (su backend CmdStan es pesado de compilar en Windows).
#   El dashboard NO sabe qué motor corrió: consume el PNG y el resumen igual.
#
# Datos:
#   El histórico del curso (24 meses, KAROL G) alimenta el demo. La
#   infraestructura está lista para alimentar el modelo con snapshots reales:
#   cada corrida del robot (scripts/daily_update.py) ya es un punto temporal
#   del fandom; con 6+ snapshots el histórico simulado se sustituye por el
#   acumulado real sin cambiar una línea de este módulo.
#
# Uso:
#   ./venv/Scripts/python scripts/forecast_fans.py     → guarda PNG en notebooks/
#   import forecast_fans; forecast_fans.fit_and_forecast(save_png=False)
# ============================================================================

import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import os

import matplotlib

matplotlib.use("Agg")  # renderizado sin pantalla (CI + servidor)
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, "notebooks")
OUT_PNG = os.path.join(OUT_DIR, "karol_g_fans_forecast.png")

ARTISTA = "KAROL G"
MESES_FUTUROS = 6

# Con 24 puntos o menos no hay evidencia suficiente para estacionalidad anual
# (el propio Prophet lo advierte: solo 1-2 repeticiones del ciclo →
# descomposición inestable y valles falsos). Se activa solo con MÁS de 2 años.
MESES_MIN_ESTACIONALIDAD = 24


def _meses_futuros_historico(n_meses: int) -> pd.DatetimeIndex:
    """Últimos `n_meses` fines de mes terminando EN EL MES ACTUAL.

    El histórico del demo es 'evergreen': se ancla a hoy para que el forecast
    siempre proyecte los 6 meses siguientes, no fechas congeladas del ejemplo.
    """
    fin = pd.Timestamp.today().normalize() + pd.offsets.MonthEnd(0)
    return pd.date_range(end=fin, periods=n_meses, freq="ME")

# Histórico mensual simulado (fans de Deezer) — 24 meses, tendencia del curso
HISTORICO_FANS = [
    1_500_000, 1_650_000, 1_800_000, 2_000_000, 2_200_000, 2_450_000,
    2_700_000, 2_900_000, 3_100_000, 3_250_000, 3_400_000, 3_550_000,
    3_700_000, 3_850_000, 4_000_000, 4_200_000, 4_400_000, 4_600_000,
    4_800_000, 5_000_000, 5_200_000, 5_450_000, 5_700_000, 6_000_000,
]


def _prophet_forecast(y: np.ndarray):
    """Intenta Prophet; retorna (pred, lo, hi, fechas_futuras, engine) o None."""
    try:
        from prophet import Prophet
    except Exception:
        return None
    try:
        dfp = pd.DataFrame({"ds": _meses_futuros_historico(len(y)), "y": y})
        # Estacionalidad anual SOLO con evidencia suficiente (> 2 ciclos)
        m = Prophet(yearly_seasonality=len(y) > MESES_MIN_ESTACIONALIDAD)
        m.fit(dfp)
        futuro = m.make_future_dataframe(
            periods=MESES_FUTUROS, freq="ME", include_history=False
        )
        fc = m.predict(futuro).drop_duplicates(subset="ds").sort_values("ds")
        return (
            fc["yhat"].to_numpy(),
            fc["yhat_lower"].to_numpy(),
            fc["yhat_upper"].to_numpy(),
            fc["ds"],
            "Prophet (Meta)",
        )
    except Exception as e:
        print(f"ℹ️ Prophet instalado pero falló al ajustar ({type(e).__name__}: {e})")
        return None


def _sklearn_forecast(y: np.ndarray):
    """Fallback: regresión lineal + banda 95% por residuos."""
    from sklearn.linear_model import LinearRegression

    x = np.arange(len(y)).reshape(-1, 1)
    modelo = LinearRegression().fit(x, y)
    resid_std = float(np.std(y - modelo.predict(x), ddof=1))
    x_fut = np.arange(len(y), len(y) + MESES_FUTUROS).reshape(-1, 1)
    pred = modelo.predict(x_fut)
    banda = 1.96 * resid_std * np.sqrt(1 + 1.0 / len(y))
    fechas = pd.date_range(
        _meses_futuros_historico(len(y))[-1] + pd.offsets.MonthEnd(1),
        periods=MESES_FUTUROS,
        freq="ME",
    )
    return pred, pred - banda, pred + banda, fechas, "scikit-learn (LinearRegression)"


def fit_and_forecast(save_png: bool = True):
    """Entrena, proyecta 6 meses y construye la figura. Retorna dict con todo."""
    y = np.asarray(HISTORICO_FANS, dtype=float)

    resultado = _prophet_forecast(y)
    if resultado is None:
        resultado = _sklearn_forecast(y)
    pred, lo, hi, fechas_fut, engine = resultado

    df_fc = pd.DataFrame(
        {
            "fecha": fechas_fut.dt.strftime("%Y-%m"),
            "fans_proyectados": pred.round(0).astype(int),
            "limite_inferior": lo.round(0).astype(int),
            "limite_superior": hi.round(0).astype(int),
        }
    )
    crecimiento_total = (pred[-1] / y[-1] - 1) * 100
    cagr = ((pred[-1] / y[-1]) ** (12.0 / MESES_FUTUROS) - 1) * 100

    # Figura: histórico + proyección + banda de confianza
    fechas_hist = _meses_futuros_historico(len(y))
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(fechas_hist, y / 1e6, "o-", color="#1f77b4", label="Histórico (24 meses)")
    ax.plot(
        fechas_fut, pred / 1e6, "s--", color="#d62728", label=f"Proyección 6 meses ({engine.split(' ')[0]})"
    )
    ax.fill_between(
        fechas_fut, lo / 1e6, hi / 1e6, color="#d62728", alpha=0.15, label="Banda de confianza 95%"
    )
    ax.set_title(f"Proyección de Crecimiento de Fans: {ARTISTA} (próximos 6 meses)", fontsize=13)
    ax.set_xlabel("Fecha")
    ax.set_ylabel("Fans en Deezer (millones)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()

    if save_png:
        os.makedirs(OUT_DIR, exist_ok=True)
        fig.savefig(OUT_PNG, dpi=120)
        print(f"🖼️ Gráfico guardado: {OUT_PNG}")

    return {
        "artista": ARTISTA,
        "engine": engine,
        "fans_hoy": int(y[-1]),
        "forecast": df_fc,
        "crecimiento_6m_pct": round(float(crecimiento_total), 1),
        "cagr_anualizado_pct": round(float(cagr), 1),
        "fig": fig,
    }


if __name__ == "__main__":
    r = fit_and_forecast(save_png=True)
    print(f"\n🔮 Motor de forecasting: {r['engine']}")
    print(f"   Fans hoy: {r['fans_hoy']:,}")
    print(f"\n{r['forecast'].to_string(index=False)}")
    print(f"\n📈 Crecimiento proyectado a 6 meses: +{r['crecimiento_6m_pct']}%")
    print(f"📈 CAGR anualizado: {r['cagr_anualizado_pct']}%")
