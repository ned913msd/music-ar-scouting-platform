#!/usr/bin/env python3
# ============================================================================
# touring_engine.py
# A&R Scouting Command Center | Touring Recommendation Engine (LatAm/ES/US)
#
# Qué hace:
#   Dado un artista (fans totales + rank de Deezer), estima la demanda por
#   ciudad sobre una cartera de 8 mercados clave y recomienda el venue y el
#   ROI bruto esperado de cada parada. Es un MOTOR DE SIMULACIÓN DE MERCADO:
#   la API pública de Deezer no expone el desglose de fans por ciudad (dato
#   premium), así que se modela como lo hacen las consultoras sin acceso a
#   Spotify for Artists — tamaño de mercado × conversión realista.
#
# Modelo (y por qué):
#   1. Reparto de fans PROPORCIONAL y CONSERVATIVO:
#         fans_ciudad = total_fans × multiplicador_i / Σ(multiplicadores)
#      Σ fans_ciudad = total_fans EXACTO (el reparto del tutorial dividía
#      entre 8 con Σmult=12.9 → inventaba un 44% de fans que no existen).
#   2. Conversión fan→ticket del 2% (base para artistas emergentes/medios),
#      ajustada por momentum: fuera del top 400k de rank, −20% de pull.
#   3. Venue por tramo de asistentes con precio de ticket POR TIER (un
#      estadio no cobra lo que un bar): $60 / $40 / $30 / $20.
#   4. Radio del marcador √escala (área ∝ asistentes): el radio lineal del
#      tutorial (asistentes/100) dibujaba círculos de 85px que tapaban países.
#
# Determinista: sin aleatoriedad — mismo artista → misma gira, siempre.
# ============================================================================

import math

import pandas as pd

# Cartera de mercados clave con su "Multiplicador de Mercado Musical"
# (1.0 = mercado base tipo Medellín; 2.5 = gigante tipo CDMX)
CIUDADES_MERCADO = [
    {"ciudad": "Medellín, CO", "lat": 6.2476, "lon": -75.5658, "multiplicador": 1.0},
    {"ciudad": "Bogotá, CO", "lat": 4.7110, "lon": -74.0721, "multiplicador": 1.5},
    {"ciudad": "Ciudad de México, MX", "lat": 19.4326, "lon": -99.1332, "multiplicador": 2.5},
    {"ciudad": "Buenos Aires, AR", "lat": -34.6037, "lon": -58.3816, "multiplicador": 2.0},
    {"ciudad": "Santiago, CL", "lat": -33.4489, "lon": -70.6693, "multiplicador": 1.2},
    {"ciudad": "Lima, PE", "lat": -12.0464, "lon": -77.0428, "multiplicador": 1.3},
    {"ciudad": "Madrid, ES", "lat": 40.4168, "lon": -3.7038, "multiplicador": 1.8},
    {"ciudad": "Miami, US", "lat": 25.7617, "lon": -80.1918, "multiplicador": 1.6},
]

_SUM_MULT = sum(c["multiplicador"] for c in CIUDADES_MERCADO)  # 12.9

TASA_CONVERSION_BASE = 0.02      # 2% de los fans de la ciudad compran ticket
RANK_UMBRAL_PULL = 400_000       # top 400k conserva el 100% del pull
PENALIZACION_RANK = 0.80         # fuera del umbral: −20% de conversión

# Escalera de venues: (límite asistentes, nombre, color mapa, precio ticket USD)
TIERS_VENUE = [
    (5_000, "Estadio / Arena Grande", "#FF4444", 60),
    (1_500, "Arena / Teatro Grande", "#FFA500", 40),
    (300, "Teatro / Club Grande", "#0066FF", 30),
    (0, "Club / Bar (No rentable)", "#6B7280", 20),
]

RADIO_MIN, RADIO_MAX = 8, 24     # px del marcador en el mapa


def _venue_para(asistentes: int):
    """Devuelve (venue, color, precio_ticket) según el tramo de asistentes."""
    for limite, nombre, color, precio in TIERS_VENUE:
        if asistentes > limite:
            return nombre, color, precio
    return TIERS_VENUE[-1][1], TIERS_VENUE[-1][2], TIERS_VENUE[-1][3]


def calcular_ruta_touring(artist_name, total_fans, deezer_rank):
    """Simula la gira del artista sobre la cartera de mercados.

    Returns: DataFrame con ciudad, fans_estimados, asistentes_estimados,
    venue_recomendado, ticket_price_usd, roi_estimado_usd, color, radio, lat, lon.
    Determinista: mismo input → mismo output.
    """
    total_fans = int(max(total_fans, 0))
    deezer_rank = int(max(deezer_rank or 0, 0))

    # Ajuste de pull por momentum: fuera del top 400k, menos conversión
    factor_rank = 1.0 if deezer_rank <= RANK_UMBRAL_PULL else PENALIZACION_RANK

    # Reparto proporcional con conservación EXACTA (método de restos mayores,
    # el mismo de la repartición de escaños): cuota flotante → parte entera →
    # los fans residuales van a las ciudades con mayor parte fraccionaria.
    # Truncar por ciudad (como un int() plano) perdía hasta 7 fans del total.
    cuotas = [total_fans * c["multiplicador"] / _SUM_MULT for c in CIUDADES_MERCADO]
    base = [int(q) for q in cuotas]
    residuales = total_fans - sum(base)
    orden_fraccional = sorted(
        range(len(cuotas)), key=lambda i: cuotas[i] - base[i], reverse=True
    )
    for i in orden_fraccional[:residuales]:
        base[i] += 1
    fans_por_ciudad = {
        c["ciudad"]: base[i] for i, c in enumerate(CIUDADES_MERCADO)
    }

    resultados = []
    for ciudad in CIUDADES_MERCADO:
        # Σ fans_ciudad == total_fans (exacto, ver arriba)
        fans_en_ciudad = fans_por_ciudad[ciudad["ciudad"]]
        asistentes = int(fans_en_ciudad * TASA_CONVERSION_BASE * factor_rank)
        venue, color, precio = _venue_para(asistentes)

        # Radio perceptual: el ÁREA del círculo es proporcional a los asistentes
        radio = int(min(RADIO_MAX, max(RADIO_MIN, math.sqrt(max(asistentes, 1)) / 4)))

        resultados.append(
            {
                "ciudad": ciudad["ciudad"],
                "lat": ciudad["lat"],
                "lon": ciudad["lon"],
                "fans_estimados": int(fans_en_ciudad),
                "asistentes_estimados": asistentes,
                "venue_recomendado": venue,
                "ticket_price_usd": precio,
                "roi_estimado_usd": asistentes * precio,
                "color": color,
                "radio": radio,
            }
        )

    df = pd.DataFrame(resultados).sort_values(
        "asistentes_estimados", ascending=False
    ).reset_index(drop=True)
    df.attrs["artista"] = artist_name
    return df


def resumen_gira(df_touring: pd.DataFrame) -> dict:
    """KPIs agregados de la gira para la vista del dashboard."""
    total_asistentes = int(df_touring["asistentes_estimados"].sum())
    roi_total = int(df_touring["roi_estimado_usd"].sum())
    top = df_touring.iloc[0]
    venues_viables = int(
        (df_touring["venue_recomendado"] != "Club / Bar (No rentable)").sum()
    )
    return {
        "total_asistentes": total_asistentes,
        "roi_total_usd": roi_total,
        "mercado_top": str(top["ciudad"]),
        "asistentes_top": int(top["asistentes_estimados"]),
        "venues_viables": venues_viables,
    }
