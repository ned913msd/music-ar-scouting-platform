"""
Decoradores personalizados — comportamientos transversales sin ensuciar
la lógica de negocio.

Dos decoradores de producción, aplicados en puntos reales del producto:

  * @medir_rendimiento  — manda a stdout cuánto tarda cualquier función
    (se aplica a extraer_adn_basico, calcular_crecimiento y predecir_lote,
    las tres piezas pesadas del pipeline).
  * @reintentar          — reintentos con backoff exponencial para I/O
    fallible (se aplica al wrapper síncrono de la colecta asíncrona de
    Deezer: si el lote muere por red, CI reintenta sin tumbar la corrida).

@functools.wraps preserva nombre y docstring de la función original: los
logs y el introspection siguen mostrando el nombre real, no "wrapper".
"""

import functools
import time


def medir_rendimiento(func):
    """Imprime el tiempo de ejecución de `func` (perf_counter, segundos)."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        inicio = time.perf_counter()
        resultado = func(*args, **kwargs)
        duracion = time.perf_counter() - inicio
        print(f"⚡ '{func.__name__}' tardó {duracion:.4f}s")
        return resultado

    return wrapper


def reintentar(max_intentos=3, espera_base=1.0, excepciones=(Exception,)):
    """Reintenta `func` con backoff exponencial (espera_base · 2^n).

    El último intento propaga la excepción original: un fallo persistente
    se ve en CI, no queda silenciado.
    """

    def decorador(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for intento in range(1, max_intentos + 1):
                try:
                    return func(*args, **kwargs)
                except excepciones as e:
                    if intento == max_intentos:
                        raise
                    espera = espera_base * (2 ** (intento - 1))
                    print(
                        f"⚠️ '{func.__name__}' falló (intento {intento}/"
                        f"{max_intentos}): {e!r}; reintento en {espera:.1f}s"
                    )
                    time.sleep(espera)

        return wrapper

    return decorador
