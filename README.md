# 🎵 A&R Scouting Command Center

**Data Product para identificación de talento musical con potencial de firma**

[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://www.python.org/)
[![dbt](https://img.shields.io/badge/dbt-Core-orange)](https://www.getdbt.com/)
[![DuckDB](https://img.shields.io/badge/DuckDB-Analytics-green)](https://duckdb.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-Dashboard-red)](https://streamlit.io/)
[![Deployed on Render](https://img.shields.io/badge/Deployed%20on-Render-46E3B7?style=for-the-badge&logo=render)](https://music-ar-scouting-platform.onrender.com/)

### 🌐 Demo en Vivo

**URL Pública:** [https://music-ar-scouting-platform.onrender.com/](https://music-ar-scouting-platform.onrender.com/)

> ⏱️ El servicio corre en el plan gratuito de Render: si estuvo inactivo, la primera carga puede tardar ~50 segundos mientras el servidor despierta (luego responde al instante). La base de datos se auto-inicializa desde el seed del repo gracias a `bootstrap_db.py`.

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
| **Extracción** | Python (Pandas, NumPy, Requests, Spotipy) | Pipeline ELT, simulación de APIs de monitoreo y extractores de datos reales (Deezer / Spotify) |
| **Almacenamiento** | DuckDB | Data warehouse analítico local |
| **Transformación** | dbt-core (+ dbt_utils) | Modelado, Scouting Score y tests de calidad |
| **Visualización** | Streamlit | Dashboard interactivo para stakeholders, auto-reparable en la nube |
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
| **Tests de calidad** | 26/26 PASS | Datos confiables para decidir |
| **Insights accionables** | 100% automatizados | Decisiones basadas en datos |

## 🚀 Cómo Usar Este Data Product

### Prerrequisitos

- Python **3.10–3.12** (dbt aún no soporta 3.13+; `setup.sh` selecciona la mejor versión disponible automáticamente)

### Instalación y ejecución

```bash
# 1. Clonar el repositorio
git clone https://github.com/ned913msd/music-ar-scouting-platform.git
cd music-ar-scouting-platform

# 2. Crear el entorno e instalar dependencias de desarrollo (Windows/Git Bash)
bash setup.sh
source venv/Scripts/activate

# 3. Ejecutar el pipeline E+L (50 artistas → DuckDB)
python pipeline/ar_scouting_pipeline.py

# 4. Datos reales de Deezer (opcional pero recomendado)
python deezer_data_extractor.py   # genera el CSV + tabla real_artists_raw en DuckDB

# 5. Transformaciones y tests con dbt (el seed convierte el CSV en tabla)
dbt deps --project-dir ar_dbt_project --profiles-dir ar_dbt_project
dbt seed --project-dir ar_dbt_project --profiles-dir ar_dbt_project
dbt run --project-dir ar_dbt_project --profiles-dir ar_dbt_project
dbt test --project-dir ar_dbt_project --profiles-dir ar_dbt_project

# 6. Levantar el dashboard
streamlit run app.py
```

Accede en: **http://localhost:8501**

> 💾 Resolución de la ruta del warehouse (en este orden): variable `MUSIC_AR_DB_PATH` → carpeta canónica del equipo (`Desktop/BASES DE DATOS DE PRUEBAS/`) → raíz del repo (portable, la nube).

## ☁️ Despliegue en la nube (Render) con app auto-reparable

El repo incluye `render.yaml` (blueprint): en Render → **New → Blueprint**, y el servicio se crea con build/start y variables ya configuradas.

La clave es `bootstrap_db.py`: si el contenedor limpio no encuentra el warehouse DuckDB, lo **reconstruye en segundos desde el seed versionado en el repo** (`ar_dbt_project/seeds/deezer_artists_data.csv`) replicando exactamente la lógica de scoring del mart dbt (50/30/20). Por eso la nube **no necesita dbt** (`requirements.txt` = runtime; `requirements-dev.txt` = dbt para desarrollo), la imagen instala rápido y la app siempre arranca, sin importar cuántas veces se reinicie el servidor. Verificado: bootstrap idempotente en directorio limpio, y el score reconstruido (KAROL G 89.85 🔥) es idéntico al del mart dbt.

Para probar la auto-reparación en local: `python bootstrap_db.py` (CLI de verificación).

### Consulta rápida del Director de A&R

```sql
SELECT artist_name, scouting_score, ar_recommendation, strategic_insight
FROM artist_scouting_deezer
WHERE ar_recommendation = '🔥 FIRMAR AHORA'
ORDER BY scouting_score DESC;
```

> El mart `artist_scouting_deezer` es el ranking sobre **datos reales de Deezer** (sección siguiente); `artist_scouting_ranking` conserva el modelo del dataset simulado.

### 🎬 Datos en vivo: API real (Deezer)

Además del dataset simulado, el producto extrae **datos reales de streaming** vía la API pública de Deezer (sin API key, sin login y sin Premium): fans reales (`nb_fan`), ranks de reproducción de tracks (escala 0–1M) y resolución inteligente de homónimos (coincidencia exacta de nombre + prominencia por fans).

```bash
# 10 artistas emergentes latino por defecto (o pásale los tuyos como argumentos)
python deezer_data_extractor.py
python deezer_data_extractor.py "Feid" "Tyla" "Grupo Frontera"
```

**Scouting Score con datos reales** (fórmula ajustada para Deezer, 50/30/20):

| Dimensión | Peso | Métrica real de Deezer |
|-----------|------|------------------------|
| Rank del artista | 50% | promedio del rank del top-10 de tracks (0–1.000.000) — proxy de fuerza de catálogo, ya que la API dejó de exponer `rank` a nivel artista |
| Fandom consolidado | 30% | `nb_fan` normalizado (base de fans reales) |
| Pico del mayor hit | 20% | rank del track más escuchado (escala absoluta 0–1M) |

Resultado de la corrida real sobre artistas emergentes (persistido como snapshot en `real_artists_raw` en DuckDB):

| Artista | Fans reales | Rank (proxy) | Score | Recomendación |
|---------|------------:|-------------:|------:|---------------|
| KAROL G | 3.411.808 | 796.911 | 89,85 | 🔥 FIRMAR AHORA |
| Myke Towers | 1.705.933 | 662.773 | 63,78 | 👀 OBSERVAR |
| Bizarrap | 1.124.709 | 614.038 | 56,94 | 👀 OBSERVAR |
| Feid | 905.383 | 671.329 | 54,83 | 👀 OBSERVAR |
| Peso Pluma | 507.388 | 658.050 | 53,28 | 👀 OBSERVAR |
| SAIKO | 53.984 | 452.220 | 34,10 | ⚠️ DESCARTAR |

Lectura de negocio: sobre una lista de emergentes, solo la artista ya consolidada (KAROL G) supera el umbral de firma — el modelo distingue talento en crecimiento de éxito establecido, exactamente el filtro que un equipo de A&R necesita.

#### Del CSV al warehouse: `dbt seed` → mart `artist_scouting_deezer`

El CSV generado se versiona como **seed de dbt** (`ar_dbt_project/seeds/`) y se convierte en tabla con `dbt seed`. El mart `artist_scouting_deezer` calcula el Scouting Score en SQL puro (50/30/20) con clamping de rangos, y el dashboard de Streamlit lo consume directamente: **fotos reales** de los artistas desde la CDN de Deezer, métricas por artista, link al perfil, filtros por recomendación/score y exportación CSV. Con los datos reales cargados: **26/26 tests en verde** (fans/rank en rango 0–1M, nombres únicos, recomendaciones válidas).

### ☁️ Spotify Web API (estado)

El extractor `spotify_data_extractor.py` está listo (Spotipy + `.env` + Client Credentials, sin ventana de navegador), pero **la política 2025 de Spotify exige que el dueño de la app tenga suscripción Premium activa** para permitir llamadas a la Web API. Al activar Premium, el script funciona tal cual está. Además, el endpoint `audio-features` fue deprecado por Spotify (27-11-2025); el extractor lo degrada con valores neutros.

> 🔐 Crea tu propio `.env` (no versionado) con `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` y `SPOTIFY_REDIRECT_URI=http://127.0.0.1:8501`.

## 🧪 Módulo 4 — ML: predicción de viralidad (en curso)

El dashboard dice *"cómo están los artistas hoy"*; el laboratorio de ML construye la respuesta a *"¿quién explotará en 6 meses?"* — firmar talento antes de que su precio suba.

**`notebooks/01_virality_prediction.ipynb`** — hipótesis definida con Product Thinking:

- **Objetivo**: predecir >70% de probabilidad de duplicar `deezer_fans` en 6 meses.
- **Features**: Deezer Rank actual · ratio de crecimiento de fans · popularidad del top track vs. promedio del género.
- **Target**: `is_viral` (1/0).
- **Datos actuales**: 10 artistas reales del warehouse (para diseño de features); dataset sintético de 10.000 artistas con series de tiempo para entrenar.

**Primer modelo entrenado y evaluado** (Random Forest, 100 árboles, max_depth 5 — notebook ejecutado end-to-end con salidas embebidas):

| Métrica | Valor | Lectura |
|---------|------:|---------|
| **ROC-AUC** | **0.9242** | Excelente (>0.70 ya se considera bueno en comportamiento humano) |
| Accuracy | 86% | 2.000 artistas de prueba (split 80/20 estratificado) |
| Precision (Viral) | 79% | Cuando el modelo dice "firmar", acierta 4 de 5 |
| Recall (Viral) | 91% | Encuentra 9 de cada 10 artistas que explotarán |

**Feature Importance** (el "por qué" para el VP de A&R):

```
monthly_growth_rate  76.97%  ← el momentum lo es todo
top/track_rank       17.59%
current_rank          3.21%
current_fans          2.03%  ← el tamaño actual casi no predice
```

> 💡 La lección de negocio, ahora con números: la tasa de crecimiento mensual es **~38× más predictiva** que el número de fans actuales. Un artista con 5.000 fans creciendo +25% mensual vale más que uno estancado en 100.000.

### 🔗 Del notebook a producción (serialización ML)

El modelo se serializa con `joblib` (`modelo_viralidad_rf.pkl` + `feature_names.pkl`) desde la última celda del notebook, y el dashboard lo carga cacheado (`@st.cache_resource`) para predecir en tiempo real: cada artista muestra su **Probabilidad de Viralidad (6M)** con barra de progreso, y la tabla completa incluye la columna `Prob. Viral 6M`. El proxy de crecimiento usado en inferencia está **calibrado al dominio de entrenamiento** `U(-0.05, 0.30)` (ratio de conversión oyente→fan escalado), para que los scores sean comparables con lo que el modelo aprendió.

```bash
# Abrir el laboratorio (requiere requirements-dev.txt)
jupyter notebook --notebook-dir notebooks
```

## 🤖 Módulo 5 — Automatización y Forecasting (de proyecto a negocio)

Un dashboard que se actualiza a mano es un proyecto de estudiante; uno que se actualiza solo, predice el futuro y no requiere tocar una tecla es un producto en operación.

### Actualización automática semanal (GitHub Actions)

El workflow **`.github/workflows/update_data.yml`** despierta cada lunes 13:00 UTC (8:00 AM Medellín; también ejecutable a mano con `workflow_dispatch`), consulta la API de Deezer para la cartera monitoreada y commitea el CSV fresco con el bot `github-actions[bot]`. Ese push dispara el redeploy de Render: datos nuevos en producción sin intervención humana.

- **`scripts/daily_update.py`** — el cerebro del robot: reutiliza el matcher de homónimos y el proxy de rank (top-10 de tracks) del extractor, hace **upsert por `artist_id`** sobre el seed existente (nunca borra artistas del portafolio) y actualiza **solo las 9 columnas núcleo** — las derivadas las recalcula el mart dbt, fuente única de verdad.
- Corrida de verificación con datos reales en movimiento: KAROL G +120 fans, Feid +91, Myke Towers +92 desde el snapshot anterior → seed → `dbt seed --full-refresh` → mart reconstruido → **26/26 tests PASS**.
- Nota de ingeniería: dbt-duckdb infiere el esquema del seed desde la tabla ya existente en el warehouse; al cambiar las columnas del CSV hay que usar `dbt seed --full-refresh` para que la tabla se recree desde el archivo.

### Forecasting de fans con Prophet

**`scripts/forecast_fans.py`** entrena Prophet (Meta) con un histórico mensual de fans y proyecta **6 meses hacia adelante**; el dashboard lo expone en la pestaña **📈 Forecasting** (con `st.cache_data`: el plan gratuito de Render no paga el re-entrenamiento en cada visita).

- Proyección **evergreen**: el histórico se ancla al mes actual, así el forecast siempre mira hacia adelante (nada de fechas congeladas de hace un año).
- **Estacionalidad anual adaptativa**: solo se activa con ≥24 meses de historial — con menos, Prophet no puede identificar el ciclo anual y produce valles falsos en la proyección (defecto detectado y corregido en ejecución real).
- Resultado verificado para KAROL G: 6.0M → **7.34M fans (+22.3%)** a 6 meses; el notebook compara motores: regresión lineal (sklearn) +15.5% vs Prophet +22.3% — Prophet captura el momentum no lineal del crecimiento.

## 🎓 Competencias Demostradas

Este proyecto demuestra habilidades de Music Data Analyst y Analytics Engineer:

- ✅ **Music Business**: entendimiento de métricas de streaming (Save Rate, Skip Rate, Follower Ratio, viralidad en TikTok)
- ✅ **Data Engineering**: pipeline ETL automatizado con Python hacia DuckDB + extractores de APIs reales (Deezer) con throttling y reintentos
- ✅ **API Integration**: consumo de Web APIs públicas con manejo de rate limits, deprecación de endpoints (audio-features) y políticas de acceso (Spotify Premium gate)
- ✅ **Analytics Engineering**: modelado con dbt (staging → marts), patrón ELT y grafo de dependencias
- ✅ **Data Quality**: 26 tests automatizados (rangos 0–100 y 0–1M, valores aceptados, unicidad) que ya cazaron un bug real de porcentajes
- ✅ **Product Management**: de problema de negocio → solución técnica → valor medible
- ✅ **UX-UI Design**: dashboard intuitivo con filtros, KPIs, top 10 y exportación CSV

## 🔮 Próximos Pasos (Roadmap)

- [x] Datos reales de streaming vía API pública de Deezer (fans, rank de reproducción, momentum de lanzamientos)
- [ ] Integración con Spotify Web API (bloqueada por política 2025: exige Premium del dueño de la app — extractor listo)
- [ ] Web scraping de datos de TikTok y YouTube
- [x] Modelo de Machine Learning integrado al dashboard: Random Forest (ROC-AUC 0.9242) serializado con joblib, prediciendo **Probabilidad de Viralidad 6M** por artista en producción
- [ ] Alertas automáticas cuando un artista entra en "Firmar Ahora"
- [x] **Sistema autónomo (Módulo 5)**: robot semanal de datos (GitHub Actions → Deezer API) + forecasting de fans 6M con Prophet integrado al dashboard
- [x] Blueprint de despliegue en la nube (Render) con app auto-reparable (`bootstrap_db.py` + `render.yaml`)
- [ ] Módulo de touring: cruce con datos geoespaciales para planificación de giras

## 👤 Sobre el Autor

**David NED Bustamante** · [LinkedIn](https://www.linkedin.com/in/nedbustamante/) · 📍 Medellín, Colombia · 📧 contacto.nedbustamante@gmail.com

*Music Data Analyst | Analytics Engineer | Full Stack Developer*

Especializado en construir productos de datos para la industria musical. Combino conocimiento profundo de Music Business (A&R, Marketing, SEO) con habilidades técnicas avanzadas (Python, SQL, dbt, Streamlit) para crear soluciones que los sellos y managers realmente usan.

Proyecto desarrollado como parte del portafolio profesional para roles de Music Data Analyst y Analytics Engineering en la industria musical.
