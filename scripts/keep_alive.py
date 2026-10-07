#!/usr/bin/env python3
# ============================================================================
# keep_alive.py — ping periódico a los despliegues para evitar cold starts
#
# Qué hace:
#   Manda un GET cada 10 minutos a Render y a Streamlit Cloud. Render (free)
#   duerme la instancia a los 15 min sin tráfico y Streamlit Cloud libera
#   instancias inactivas: con este ping el dashboard responde en caliente
#   cuando lo abres, en vez de pagarr 30-60 s de arranque en frío.
#
# Uso:
#   python scripts/keep_alive.py           → bucle infinito (ideal en un
#                                            cron, un servicio o la Action)
#   python scripts/keep_alive.py --once    → un solo ping y sale (tests)
#   python scripts/keep_alive.py --cada 300 → intervalo en segundos
#
# Solo usa la librería estándar: no requiere dependencias del venv.
# ============================================================================

import argparse
import time
import urllib.error
import urllib.request

# Health endpoints: responden sin renderizar la app entera. Render (free)
# duerme a los 15 min; Streamlit Cloud libera instancias inactivas.
URLS = [
    "https://music-ar-scouting-platform.onrender.com/_stcore/health",
    "https://music-ar-scouting-platform-3gppcbtk6chqkpyyaxtc6y.streamlit.app/_stcore/health",
]

INTERVALO_DEFECTO_S = 10 * 60  # 10 min: por debajo del umbral de sleep (15 min)
TIMEOUT_S = 60  # un cold start de Render puede tardar >30 s


class _SinRedirecciones(urllib.request.HTTPRedirectHandler):
    """No sigue redirecciones (Streamlit Cloud manda a share.streamlit.io y
    el bucle de auth acaba en "too many redirects"). Devolver None hace que
    urllib lance HTTPError con el código original: respuesta = servidor vivo."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_SinRedirecciones())


def ping():
    """Un GET por despliegue. Nunca lanza: los fallos solo se imprimen.

    Cualquier respuesta HTTP (200, 303, 401...) cuenta como éxito: lo que
    importa es que el servidor despierte y responda, no el código.
    """
    marca = time.strftime("%Y-%m-%d %H:%M:%S")
    for url in URLS:
        try:
            req = urllib.request.Request(
                url, method="GET", headers={"User-Agent": "keep-alive/1.0"}
            )
            with _OPENER.open(req, timeout=TIMEOUT_S) as resp:
                print(f"[{marca}] {resp.status} {url}", flush=True)
        except urllib.error.HTTPError as exc:
            # El host respondió (p.ej. 303 de auth): sigue despierto.
            print(f"[{marca}] {exc.code} {url}", flush=True)
        except Exception as exc:
            print(
                f"[{marca}] fallo {url}: {type(exc).__name__}: {exc}",
                flush=True,
            )


def main():
    parser = argparse.ArgumentParser(
        description="Ping de keep-alive para Render y Streamlit Cloud"
    )
    parser.add_argument(
        "--once", action="store_true", help="un solo ping y salir"
    )
    parser.add_argument(
        "--cada",
        type=int,
        default=INTERVALO_DEFECTO_S,
        help="segundos entre pings (por defecto 600)",
    )
    args = parser.parse_args()

    while True:
        ping()
        if args.once:
            break
        time.sleep(max(30, args.cada))


if __name__ == "__main__":
    main()
