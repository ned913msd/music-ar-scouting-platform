"""
Programación asíncrona (asyncio + aiohttp): colecta masiva sin espera
muerta.

El robot semanal consulta la API pública de Deezer por artista. La versión
secuencial duerme 0.35s por request y encadena red: N artistas = N ·
(latencia + sleeps). Esta versión lanza TODAS las peticiones con un
semáforo que limita la concurrencia (respeto con la API) y backoff
exponencial ante 429/5xx — la misma política de la versión síncrona, pero
sin serializar el tiempo de red.

La lógica pura de negocio (elegir entre homónimos y armar el registro
normalizado) vive en deezer_data_extractor y SE REUTILIZA: aquí solo
cambia el transporte (aiohttp en vez de requests).

CI llama a `obtener_lote(nombres)` (wrapper síncrono con @reintentar);
el event loop nunca se mezcla con el resto del script.
"""

import asyncio
import os
import sys
from typing import Any, Dict, List, Optional, Union

# Consolas Windows (cp1252) no imprimen emojis: forzar UTF-8 antes de todo
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import aiohttp

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from decoradores import reintentar  # noqa: E402
from deezer_data_extractor import (  # noqa: E402
    DEEZER_BASE,
    _armar_registro,
    _elegir_candidato,
)

LIMITE_CONEXIONES = 4  # concurrencia máxima (≈4 req en vuelo)
DELAY_AMABLE = 0.15  # micro-pausa async por request, amable con la API
MAX_INTENTOS = 4  # iguales que deezer_get() síncrono
ESTADOS_REINTENTO = (429, 500, 502, 503)

Resultado = Optional[Dict[str, Any]]


async def _deezer_get(
    session: aiohttp.ClientSession,
    path: str,
    semaphore: asyncio.Semaphore,
    **params: Any,
) -> Dict[str, Any]:
    """GET async contra Deezer: semáforo + backoff exponencial 429/5xx."""
    url = f"{DEEZER_BASE}{path}"
    async with semaphore:  # corta la concurrencia, no el orden
        for intento in range(MAX_INTENTOS):
            try:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        await asyncio.sleep(DELAY_AMABLE)
                        return await resp.json()
                    if resp.status in ESTADOS_REINTENTO:
                        espera = 2**intento
                        print(f"   ⏳ Deezer {resp.status}; reintento en {espera}s...")
                        await asyncio.sleep(espera)
                        continue
                    resp.raise_for_status()
            except aiohttp.ClientError:
                if intento == MAX_INTENTOS - 1:
                    raise
                await asyncio.sleep(2**intento)
    raise RuntimeError(f"Deezer no respondió tras {MAX_INTENTOS} intentos: {path}")


async def _buscar_artista(
    session: aiohttp.ClientSession,
    nombre: str,
    semaphore: asyncio.Semaphore,
) -> Resultado:
    """Un artista = búsqueda (5 candidatos) + top-10 de tracks. None si no existe."""
    results = await _deezer_get(
        session, "/search/artist", semaphore, q=nombre, limit=5
    )
    items = results.get("data", [])
    if not items:
        return None
    artist = _elegir_candidato(items, nombre)
    top = await _deezer_get(
        session, f"/artist/{artist['id']}/top", semaphore, limit=10
    )
    return _armar_registro(artist, top.get("data", []))


async def obtener_lote_async(
    nombres: List[str], limite: int = LIMITE_CONEXIONES
) -> List[Union[Resultado, BaseException]]:
    """Toda la lista a la vez (asyncio.gather). Orden = orden de `nombres`.

    return_exceptions=True: un artista caído no tumba el lote; la posición
    trae la excepción y el caller decide (la resiliencia de CI se queda).
    """
    semaphore = asyncio.Semaphore(limite)
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tareas = [_buscar_artista(session, n, semaphore) for n in nombres]
        return await asyncio.gather(*tareas, return_exceptions=True)


@reintentar(max_intentos=2, espera_base=2.0,
            excepciones=(aiohttp.ClientError, ConnectionError, asyncio.TimeoutError))
def obtener_lote(nombres: List[str]) -> List[Union[Resultado, BaseException]]:
    """Wrapper síncrono para CI/scripts: event loop + reintentos de lote."""
    return asyncio.run(obtener_lote_async(nombres))
