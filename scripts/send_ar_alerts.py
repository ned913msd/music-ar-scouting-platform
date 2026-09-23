#!/usr/bin/env python3
# ============================================================================
# send_ar_alerts.py
# A&R Scouting Command Center | Alertas proactivas de A&R vía Telegram
#
# Qué hace:
#   Lee el seed crudo (ar_dbt_project/seeds/deezer_artists_data.csv) y envía
#   a un chat/canal de Telegram la lista de artistas en categoría 🔥 FIRMAR
#   AHORA — usando LA MISMA FÓRMULA que el mart de dbt y el dashboard:
#
#     scouting_score = (norm_rank * 0.50) + (norm_fans * 0.30) +
#                      (norm_track_rank * 0.20)
#
#   La normalización es RELATIVA al portafolio (cada métrica se divide por el
#   máximo del conjunto), igual que en el mart. El umbral de decisión es el
#   MISMO del dashboard (score >= 75), no un atajo ad-hoc: si mañana cambia la
#   fórmula en dbt, la alerta se ajusta tocando una sola constante aquí.
#
#   Opcional: incluye el delta de fans vs. el snapshot anterior
#   (TELEGRAM_INCLUIR_DELTA=1) para ver el momentum de la semana.
#
# Credenciales (variables de entorno — NUNCA en el código):
#   TELEGRAM_BOT_TOKEN      token del bot (@BotFather)
#   TELEGRAM_CHAT_ID        chat/canal destino
#   TELEGRAM_INCLUIR_DELTA  "1" para añadir el delta de fans (opcional)
#
# Diseño:
#   * Exit 1 si faltan credenciales: en CI la ausencia de secrets debe verse
#     en rojo, no pasar en silencio con un warning.
#   * Sin artistas en FIRMAR AHORA también envía mensaje: un lunes sin
#     notificación sería indistinguible de un robot caído.
#   * Soporta HTML (parse_mode=HTML) con negritas y links a Deezer.
#
# Uso local:   TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... python scripts/send_ar_alerts.py
# Uso en CI:   python scripts/send_ar_alerts.py  (secrets inyectados por Actions)
# ============================================================================

import sys

# Consolas Windows (cp1252) no imprimen emojis: forzar UTF-8 antes de todo
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import os

import pandas as pd
import requests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED_CSV = os.path.join(
    REPO_ROOT, "ar_dbt_project", "seeds", "deezer_artists_data.csv"
)

# ----------------------------------------------------------------------------
# FÓRMULA DEL SCOUTING SCORE — debe coincidir con el mart de dbt
# (ar_dbt_project/models/marts/artist_scouting_deezer.sql). Pesos y umbral
# centralizados aquí para que alerta y dashboard nunca diverjan.
# ----------------------------------------------------------------------------
PESO_RANK = 0.50       # indicador principal de popularidad en Deezer
PESO_FANS = 0.30       # base de fans leales
PESO_TRACK = 0.20      # éxito del top track
UMBRAL_FIRMAR = 75     # score >= 75 → '🔥 FIRMAR AHORA' (igual que el mart)


def calcular_scouting_score(df: pd.DataFrame) -> pd.DataFrame:
    """Replica la lógica del mart dbt sobre el seed crudo.

    Devuelve el DataFrame con columnas scouting_score y ar_recommendation
    idénticas a las del dashboard (normalización relativa al portafolio).
    """
    cleaned = df[(df["artist_name"].notna()) & (df["deezer_fans"] > 0)].copy()

    # Clamps de data quality (mismos del mart)
    cleaned["valid_rank"] = cleaned["deezer_rank"].clip(lower=0, upper=1_000_000)
    cleaned["valid_fans"] = cleaned["deezer_fans"].clip(lower=0)

    max_fans = cleaned["valid_fans"].max()
    max_track = cleaned["top_track_rank"].max()

    norm_rank = cleaned["valid_rank"] / 1_000_000
    norm_fans = cleaned["valid_fans"] / max_fans if max_fans else 0.0
    norm_track = cleaned["top_track_rank"] / max_track if max_track else 0.0

    # Compuesto crudo 0-1: la clasificación usa el valor SIN redondear (igual
    # que el mart, que decide con la expresión completa y solo redondea al
    # presentar) — evita errores de borde en el umbral 75.
    score_raw = (
        norm_rank * PESO_RANK + norm_fans * PESO_FANS + norm_track * PESO_TRACK
    ) * 100
    cleaned["scouting_score"] = score_raw.round(2)  # presentación, como el mart

    cleaned["ar_recommendation"] = pd.cut(
        score_raw,
        bins=[0, 40, 75, float("inf")],
        labels=["⚠️ DESCARTAR", "👀 OBSERVAR", "🔥 FIRMAR AHORA"],
        right=False,          # [75, ∞) es FIRMAR: el umbral exacto sí firma
        include_lowest=True,
    )
    return cleaned


def _delta_fans(df: pd.DataFrame) -> pd.Series:
    """Delta de fans vs. el snapshot anterior (versión comprometida en git HEAD).

    En CI la alerta corre DESPUÉS de daily_update, que ya sobrescribió el seed:
    el snapshot previo solo existe en el último commit, así que se lee con
    `git show HEAD:`. Si git no está disponible o no hay versión previa,
    devuelve una serie vacía y el mensaje se envía sin deltas.
    """
    if "artist_name" not in df.columns:
        return pd.Series(dtype="float64")
    seed_relpath = os.path.relpath(SEED_CSV, REPO_ROOT).replace(os.sep, "/")
    try:
        import subprocess

        prev_raw = subprocess.run(
            ["git", "show", f"HEAD:{seed_relpath}"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
            timeout=15,
        ).stdout.decode("utf-8")
        import io

        prev = pd.read_csv(io.StringIO(prev_raw), encoding="utf-8")
    except Exception:
        return pd.Series(dtype="float64")
    if "deezer_fans" not in prev.columns or "artist_name" not in prev.columns:
        return pd.Series(dtype="float64")
    prev = prev.set_index("artist_name")["deezer_fans"]
    return (df.set_index("artist_name")["deezer_fans"] - prev).dropna()


def enviar_alerta_telegram(mensaje_html: str) -> bool:
    """Envía el mensaje a Telegram; True si la API aceptó el mensaje."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print(
            "❌ Faltan credenciales: define TELEGRAM_BOT_TOKEN y "
            "TELEGRAM_CHAT_ID (en local, como variables de entorno; en CI, "
            "como Secrets del repositorio)."
        )
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": mensaje_html,
        "parse_mode": "HTML",           # negritas, links, etc.
        "disable_web_page_preview": True,
    }
    try:
        response = requests.post(url, json=payload, timeout=15)
    except requests.RequestException as e:
        print(f"❌ Error de red al contactar Telegram: {e}")
        return False

    if response.status_code == 200:
        print("✅ Alerta enviada a Telegram exitosamente.")
        return True

    print(f"❌ Error al enviar alerta (HTTP {response.status_code}): {response.text}")
    return False


def revisar_y_alertar() -> int:
    print("🚨 Iniciando sistema de alertas A&R...")

    if not os.path.exists(SEED_CSV):
        print(f"❌ No se encontró el seed de datos: {SEED_CSV}")
        return 1

    df = pd.read_csv(SEED_CSV, encoding="utf-8-sig")
    df_puntajes = calcular_scouting_score(df)

    firmar = df_puntajes[
        df_puntajes["ar_recommendation"] == "🔥 FIRMAR AHORA"
    ].sort_values("scouting_score", ascending=False)

    print(
        f"\n📊 Portafolio evaluado con la fórmula del mart "
        f"({PESO_RANK:.0%} rank + {PESO_FANS:.0%} fans + {PESO_TRACK:.0%} track):"
    )
    resumen = df_puntajes[["artist_name", "scouting_score", "ar_recommendation"]]
    print(resumen.to_string(index=False))

    # Delta opcional de fans vs. snapshot anterior (momentum de la semana)
    deltas = _delta_fans(df) if os.getenv("TELEGRAM_INCLUIR_DELTA") == "1" else None

    mensaje = "🚨 <b>ALERTA A&amp;R: Oportunidades de Firma Detectadas</b>\n\n"
    if firmar.empty:
        mensaje += "Hoy <b>ningún artista</b> alcanza el umbral de firma (score &gt;= 75).\n"
        mensaje += "El sistema está vivo y vigilando. 🤖\n\n"
    else:
        mensaje += f"Se encontraron <b>{len(firmar)}</b> artistas con potencial inmediato:\n\n"
        for _, row in firmar.iterrows():
            mensaje += f"🔥 <b>{row['artist_name']}</b>\n"
            mensaje += f"   ├─ Fans: {int(row['deezer_fans']):,}\n"
            mensaje += f"   ├─ Rank: {int(row['deezer_rank']):,}\n"
            mensaje += f"   └─ Score: <b>{row['scouting_score']:.2f}</b> | "
            mensaje += f"<a href='{row['deezer_link']}'>Ver en Deezer</a>\n\n"
            if deltas is not None and row["artist_name"] in deltas.index:
                d = int(deltas[row["artist_name"]])
                signo = "📈" if d > 0 else ("📉" if d < 0 else "➖")
                mensaje += f"   {signo} Delta fans vs. semana anterior: {d:+,}\n\n"

    mensaje += "⚙️ <i>Generado automáticamente por A&amp;R Scouting Engine</i>"

    ok = enviar_alerta_telegram(mensaje)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(revisar_y_alertar())
