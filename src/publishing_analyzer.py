import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, List, Tuple

# Configuración de estilos para los gráficos
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
        
        # Tasas promedio por stream (USD) - datos estimados 2024
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


def visualizar_escenarios(df_regalias: pd.DataFrame):
    """
    Genera visualización comparativa de escenarios y la guarda como imagen.
    """
    plt.figure(figsize=(12, 6))
    
    sns.lineplot(
        data=df_regalias,
        x='Año',
        y='Regalía_Anual_USD',
        hue='Escenario',
        marker='o',
        linewidth=2
    )
    
    plt.title(
        'Impacto de Tasas de Publishing en Regalías Anuales\n'
        'Artista con 100K streams/mes en Spotify (2028-2032)',
        fontsize=14,
        fontweight='bold'
    )
    plt.xlabel('Año', fontsize=12)
    plt.ylabel('Regalía Anual (USD)', fontsize=12)
    plt.legend(title='Escenario', bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('publishing_scenarios.png', dpi=300, bbox_inches='tight')
    print("✅ Gráfico guardado como 'publishing_scenarios.png'")
    plt.show()


if __name__ == "__main__":
    print("=" * 70)
    print("🎵 PUBLISHING INTELLIGENCE ANALYZER - EJECUCIÓN DE PRUEBA")
    print("=" * 70)
    
    analyzer = PublishingAnalyzer()
    
    # 1. Prueba de Proyección de Regalías (100K streams/mes)
    print("\n📊 1. PROYECCIÓN DE REGALÍAS (100K streams/mes en Spotify)")
    print("-" * 70)
    df_regalias = analyzer.calcular_regalias(streams_mensuales=100000, plataforma='Spotify', años_proyeccion=5)
    print(df_regalias.to_string(index=False))
    
    # 2. Prueba de Valor de Catálogo (500 canciones * 50K streams = 25M streams/mes)
    print("\n💰 2. VALOR ESTIMADO DEL CATÁLOGO (500 canciones, 50K streams/mes c/u)")
    print("-" * 70)
    streams_totales = 500 * 50000
    valores_catalogo = analyzer.calcular_valor_catalogo(
        streams_mensuales=streams_totales,
        plataforma='Spotify',
        años_proyeccion=5,
        multiplicador_valor=10.0
    )
    
    for escenario, valor in valores_catalogo.items():
        print(f"• {escenario}: ${valor:,.2f} USD")
    
    valor_max = max(valores_catalogo.values())
    valor_min = min(valores_catalogo.values())
    diferencia = valor_max - valor_min
    porcentaje_variacion = (diferencia / valor_min) * 100
    
    print(f"\n⚠️ Diferencia entre mejor y peor escenario: ${diferencia:,.2f} USD")
    print(f"   Esto representa un {porcentaje_variacion:.1f}% de variación en el valor del catálogo.")
    
    # 3. Análisis de Impacto Relativo
    print("\n📈 3. ANÁLISIS DE IMPACTO RELATIVO vs STATUS QUO")
    print("-" * 70)
    sq_rate = 0.1535
    nmpa_rate = 0.20
    ganancia_nmpa = ((nmpa_rate - sq_rate) / sq_rate) * 100
    print(f"• Escenario NMPA/NSAI (20%) vs Status Quo (15.35%): +{ganancia_nmpa:.1f}% en ingresos.")
    
    # 4. Generar Gráfico
    print("\n📉 4. GENERANDO VISUALIZACIÓN...")
    visualizar_escenarios(df_regalias)
    
    print("\n✅ EJECUCIÓN COMPLETADA CON ÉXITO.")
    print("=" * 70)