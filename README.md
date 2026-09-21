# 🎵 A&R Scouting Command Center

**Data Product para identificación de talento musical con potencial de firma**

[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://www.python.org/)
[![dbt](https://img.shields.io/badge/dbt-Core-orange)](https://www.getdbt.com/)
[![DuckDB](https://img.shields.io/badge/DuckDB-Analytics-green)](https://duckdb.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-Dashboard-red)](https://streamlit.io/)

## 🎯 El Problema de Negocio

Los sellos discográficos y empresas de management reciben cientos de demos y perfiles de artistas emergentes cada semana. Los equipos de A&R (Artistas y Repertorio) no tienen tiempo de evaluar manualmente cada candidato, lo que resulta en:

- **Oportunidades perdidas**: artistas con potencial real no son descubiertos a tiempo
- **Decisiones subjetivas**: firmas basadas en "instinto" en lugar de datos
- **Ineficiencia operativa**: horas desperdiciadas evaluando artistas sin potencial

**Pregunta de negocio:** ¿Cómo podemos identificar automáticamente los artistas con mayor probabilidad de éxito comercial antes de que exploten?

## 🎯 La Solución

Desarrollé un **Data Product end-to-end** que:

1. **Ingiere métricas** de Spotify (Save Rate, Skip Rate, Monthly Listeners) y TikTok (Viralidad, Crecimiento)
2. **Calcula un Scouting Score** (0–100) basado en pesos de la industria 2026/2027:
   - Save Rate: **40%** (la métrica reina — indica intención de escucha repetida; empuja el track a Discover Weekly)
   - Crecimiento 30d: **30%** (momentum viral)
   - Skip Rate: **30%** (calidad de retención, invertida: menos skip es mejor)
3. **Clasifica artistas** en 3 categorías accionables:
   - 🔥 **FIRMAR AHORA**: score ≥ 75
   - 👀 **OBSERVAR**: score 40–74
   - ⚠️ **DESCARTAR**: score < 40
4. **Genera insights estratégicos** automáticos para el equipo de A&R (`strategic_insight`)
5. **Garantiza calidad de datos** con 16 tests automatizados en dbt (rangos 0–100, valores aceptados, unicidad)

## 🛠️ Stack Tecnológico

| Capa | Tecnología | Propósito |
|------|-----------|-----------|
| **Extracción** | Python (Pandas, NumPy) | Pipeline ETL y simulación de APIs de monitoreo |
| **Almacenamiento** | DuckDB | Data warehouse analítico local |
| **Transformación** | dbt-core (+ dbt_utils) | Modelado, Scouting Score y tests de calidad |
| **Visualización** | Streamlit | Dashboard interactivo para stakeholders |
| **Control de Versiones** | Git/GitHub | Documentación y colaboración |

## 📊 Arquitectura del Producto

```
[Python ETL] ──► [DuckDB] ──► [dbt Models] ──► [Streamlit Dashboard]
     │               │              │                  │
 Extracción     Almacenamiento  Transformación    Visualización
 (50 artistas)  (raw_artists_   (Scouting Score,  (A&R Command
                data cruda)     tests, insights)  Center)
```

Patrón **ELT**: el script extrae y carga crudos; toda la lógica de negocio vive versionada y testeable en dbt.

## 📈 KPIs del Producto

| Métrica | Valor | Impacto |
|---------|-------|---------|
| **Tiempo de evaluación** | De 2 semanas → 5 minutos | **99% reducción** |
| **Artistas analizados** | 50 en segundos | Escalabilidad total |
| **Calibración de scouting** | ~14% "Firmar Ahora" (7/46) | Filtrado de ruido efectivo |
| **Tests de calidad** | 16/16 PASS | Datos confiables para decidir |
| **Insights accionables** | 100% automatizados | Decisiones basadas en datos |

## 🚀 Cómo Usar Este Data Product

### Prerrequisitos

- Python **3.10–3.12** (dbt aún no soporta 3.13+; `setup.sh` selecciona la mejor versión disponible automáticamente)

### Instalación y ejecución

```bash
# 1. Clonar el repositorio
git clone https://github.com/ned913msd/music-ar-scouting-platform.git
cd music-ar-scouting-platform

# 2. Crear el entorno e instalar dependencias (Windows/Git Bash)
bash setup.sh
source venv/Scripts/activate

# 3. Ejecutar el pipeline E+L (50 artistas → DuckDB)
python pipeline/ar_scouting_pipeline.py

# 4. Transformaciones y tests con dbt
dbt deps --project-dir ar_dbt_project --profiles-dir ar_dbt_project
dbt run --project-dir ar_dbt_project --profiles-dir ar_dbt_project
dbt test --project-dir ar_dbt_project --profiles-dir ar_dbt_project

# 5. Levantar el dashboard
streamlit run app.py
```

Accede en: **http://localhost:8501**

> 💾 Por defecto el warehouse vive en `Desktop/BASES DE DATOS DE PRUEBAS/music_ar_product.duckdb` (convención del equipo). Para apuntar a otra ruta usa la variable de entorno `MUSIC_AR_DB_PATH`.

### Consulta rápida del Director de A&R

```sql
SELECT artist_name, genre, scouting_score, ar_recommendation, strategic_insight
FROM artist_scouting_ranking
WHERE ar_recommendation = '🔥 FIRMAR AHORA'
ORDER BY scouting_score DESC;
```

## 🎓 Competencias Demostradas

Este proyecto demuestra habilidades de Music Data Analyst y Analytics Engineer:

- ✅ **Music Business**: entendimiento de métricas de streaming (Save Rate, Skip Rate, Follower Ratio, viralidad en TikTok)
- ✅ **Data Engineering**: pipeline ETL automatizado con Python hacia DuckDB
- ✅ **Analytics Engineering**: modelado con dbt (staging → marts), patrón ELT y grafo de dependencias
- ✅ **Data Quality**: 16 tests automatizados (rangos, valores aceptados, unicidad) que ya cazaron un bug real de porcentajes
- ✅ **Product Management**: de problema de negocio → solución técnica → valor medible
- ✅ **UX-UI Design**: dashboard intuitivo con filtros, KPIs, top 10 y exportación CSV

## 🔮 Próximos Pasos (Roadmap)

- [ ] Integración con API real de Spotify (Spotipy)
- [ ] Web scraping de datos de TikTok y YouTube
- [ ] Modelo de Machine Learning para predicción de viralidad
- [ ] Alertas automáticas cuando un artista entra en "Firmar Ahora"
- [ ] Despliegue en la nube (Streamlit Cloud)
- [ ] Módulo de touring: cruce con datos geoespaciales para planificación de giras

## 👤 Sobre el Autor

**David NED Bustamante** · [LinkedIn](https://www.linkedin.com/in/nedbustamante/) · 📍 Medellín, Colombia · 📧 contacto.nedbustamante@gmail.com

*Music Data Analyst | Analytics Engineer | Full Stack Developer*

Especializado en construir productos de datos para la industria musical. Combino conocimiento profundo de Music Business (A&R, Marketing, SEO) con habilidades técnicas avanzadas (Python, SQL, dbt, Streamlit) para crear soluciones que los sellos y managers realmente usan.

Proyecto desarrollado como parte del portafolio profesional para roles de Music Data Analyst y Analytics Engineering en la industria musical.
