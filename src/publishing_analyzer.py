import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, List, Tuple

plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")

class PublishingAnalyzer:
    """
    Analizador de impacto de tasas de publishing en ingresos y valor de catálogo.
    """
    
    def __init__(self):
        self.scenarios = {
            'Amazon Music (13.4%)': 0.134,
            'Status Quo (15.35%)': 0.1535,
            'NMPA/NSAI (20%)': 0.20
        }
        
        self.payout_rates = {
            'Spotify': 0.004,
            'Apple Music': 0.007,
            'Amazon Music': 0.004,
            'YouTube Music': 0.002,
            'Deezer': 0.006
        }
    
    def calcular_regalias(self, streams_mensuales: int, plataforma: str = 'Spotify', años_proyeccion: int = 5) -> pd.DataFrame:
        tasa_stream = self.payout_rates.get(plataforma, 0.004)
        resultados = []
        
        for año in range(2028, 2028 + años_proyeccion):
            factor_crecimiento = (1.05) ** (año - 2028)
            streams_anuales = streams_mensuales * 12 * factor_crecimiento
            
            for escenario, tasa in self.scenarios.items():
                regalia_anual = streams_anuales * tasa_stream * tasa
                resultados.append({
                    'Año': año,
                    'Escenario': escenario,
                    'Tasa_Publishing': tasa,
                    'Streams_Anuales': int(streams_anuales),
                    'Regalía_Anual_USD': round(regalia_anual, 2)
                })
        return pd.DataFrame(resultados)

    def calcular_valor_catalogo(self, streams_mensuales: int, plataforma: str = 'Spotify', años_proyeccion: int = 5, multiplicador_valor: float = 10.0) -> Dict[str, float]:
        df = self.calcular_regalias(streams_mensuales, plataforma, años_proyeccion)
        valores = {}
        for escenario in self.scenarios.keys():
            df_escenario = df[df['Escenario'] == escenario]
            ingresos_totales = df_escenario['Regalía_Anual_USD'].sum()
            valores[escenario] = round(ingresos_totales * multiplicador_valor, 2)
        return valores