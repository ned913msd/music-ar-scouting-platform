"""
Estructuras de datos robustas: el "contrato" de un artista vigilado.

En vez de pasar diccionarios y filas de DataFrame por todos lados —donde
un typo en la clave falla en tiempo de ejecución—, el pipeline de alertas
trabaja con `PerfilArtista`, un dataclass con atributos tipados y la
regla de negocio encapsulada en métodos:

  * es_firma_inmediata()  — score alto + riesgo de breakout ya activo.
  * dispara_alerta(...)   — los umbrales configurables del panel Alertas.

`iterar_perfiles(df)` es un generador: recorre el universo una fila a la
vez (itertuples) sin materializar 151 objetos de más, y el consumidor
puede cortar antes (corto-circuito) si la primera fila ya cumple.
"""

from dataclasses import dataclass
from typing import Optional

# Umbrales del "veredicto" permanente (los mismos que usa el mart de dbt
# para ar_recommendation): prob_breakout_6m está en escala 0-100.
UMBRAL_FIRMA_SCORE = 80.0
UMBRAL_FIRMA_BREAKOUT = 50.0


def _es_nulo(valor) -> bool:
    """None / NaN / pd.NA → True, sin importar pandas (itertuples cede
    escalares de numpy y, en columnas Int64, pd.NA)."""
    if valor is None:
        return True
    try:
        return bool(valor != valor)  # NaN != NaN → True; pd.NA → bool() lanza
    except (TypeError, ValueError):
        return True


def _a_float(valor, default=0.0) -> float:
    """Nulos → default; el resto a float (acepta numpy scalars)."""
    if _es_nulo(valor):
        return default
    return float(valor)


def _a_int_opcional(valor) -> Optional[int]:
    """Nulos → None; el resto a int (mes óptimo de firma, etc.)."""
    if _es_nulo(valor):
        return None
    return int(valor)


@dataclass
class PerfilArtista:
    """Contrato de un artista del universo scouting."""

    nombre: str
    deezer_fans: int
    scouting_score: float
    probabilidad_breakout: float  # Cox, escala 0-100
    genero: str
    mes_optimo_firma: Optional[int] = None  # 1..12 o None si no cruza

    def es_firma_inmediata(self) -> bool:
        """Regla de negocio permanente: score alto + breakout ya activo."""
        return (
            self.scouting_score >= UMBRAL_FIRMA_SCORE
            and self.probabilidad_breakout >= UMBRAL_FIRMA_BREAKOUT
        )

    def dispara_alerta(
        self, score_min: float, prob_min: float, mes_max: int
    ) -> bool:
        """Los umbrales configurables del panel Alertas A&R.

        Semántica idéntica a la máscara pandas que reemplazó:
        un artista SIN ventana de firma nunca dispara (mes None).
        """
        if self.scouting_score < score_min:
            return False
        if self.probabilidad_breakout < prob_min:
            return False
        if self.mes_optimo_firma is None or self.mes_optimo_firma > mes_max:
            return False
        return True

    @classmethod
    def desde_mapping(cls, m) -> "PerfilArtista":
        """Construye desde una fila de DataFrame / dict tolerando NaN."""
        return cls(
            nombre=str(m["artist_name"]),
            deezer_fans=int(_a_float(m.get("deezer_fans"))),
            scouting_score=_a_float(m.get("scouting_score")),
            probabilidad_breakout=_a_float(m.get("prob_breakout_6m")),
            genero="—" if _es_nulo(m.get("genero")) else str(m.get("genero")),
            mes_optimo_firma=_a_int_opcional(m.get("mes_optimo_firma")),
        )


def iterar_perfiles(df):
    """Generador de PerfilArtista a partir de un DataFrame del universo."""
    for fila in df.itertuples(index=False):
        yield PerfilArtista.desde_mapping(fila._asdict())
