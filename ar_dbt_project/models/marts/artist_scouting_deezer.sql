{{
    config(
        materialized='table',
        description='Modelo de ranking de artistas para A&R basado en datos REALES de Deezer API. Calcula Scouting Score usando fans, rank y popularidad de tracks.',
        tags=['ar', 'scouting', 'music-analytics', 'deezer']
    )
}}

WITH raw_deezer_data AS (
    SELECT * FROM {{ ref('deezer_artists_data') }}
),

-- Limpieza y validación
cleaned_data AS (
    SELECT 
        artist_name,
        artist_id,
        genero,
        deezer_fans,
        deezer_rank,
        picture_url,
        deezer_link,
        top_track_name,
        top_track_rank,
        top_track_duration,
        
        -- Data Quality: Validar que los datos sean razonables
        CASE 
            WHEN deezer_rank < 0 THEN 0
            WHEN deezer_rank > 1000000 THEN 1000000
            ELSE deezer_rank
        END as valid_rank,
        
        CASE 
            WHEN deezer_fans < 0 THEN 0
            ELSE deezer_fans
        END as valid_fans
        
    FROM raw_deezer_data
    WHERE artist_name IS NOT NULL
    AND deezer_fans > 0
),

-- Cálculo de métricas derivadas
artist_metrics AS (
    SELECT 
        *,
        -- Ratio Fans/Rank (eficiencia de conversión)
        ROUND(valid_fans * 1.0 / NULLIF(valid_rank, 0), 4) as fan_rank_ratio,
        
        -- Normalización para scoring (0 a 1)
        ROUND(valid_rank * 1.0 / 1000000, 4) as norm_rank,
        ROUND(valid_fans * 1.0 / (SELECT MAX(valid_fans) FROM cleaned_data), 4) as norm_fans,
        ROUND(top_track_rank * 1.0 / (SELECT MAX(top_track_rank) FROM cleaned_data), 4) as norm_track_rank
        
    FROM cleaned_data
),

-- Scouting Score final (adaptado para métricas de Deezer)
final_ranking AS (
    SELECT 
        artist_name,
        artist_id,
        genero,
        picture_url,
        deezer_link,
        deezer_fans,
        deezer_rank,
        top_track_name,
        top_track_rank,
        top_track_duration,
        fan_rank_ratio,
        
        -- SCOUTING SCORE (Pesos ajustados para Deezer)
        -- Rank: 50% (Indicador principal de popularidad en Deezer)
        -- Fans: 30% (Base de fans leales)
        -- Top Track Rank: 20% (Éxito de la canción más popular)
        ROUND(
            (
                (COALESCE(norm_rank, 0) * 0.50) + 
                (COALESCE(norm_fans, 0) * 0.30) + 
                (COALESCE(norm_track_rank, 0) * 0.20)
            ) * 100,
            2
        ) as scouting_score,
        
        -- Clasificación A&R (literales con emoji para coincidir con el
        -- pipeline y los tests: en el pegado del tutorial se perdieron)
        CASE 
            WHEN (
                (COALESCE(norm_rank, 0) * 0.50) + 
                (COALESCE(norm_fans, 0) * 0.30) + 
                (COALESCE(norm_track_rank, 0) * 0.20)
            ) * 100 >= 75 THEN '🔥 FIRMAR AHORA'
            WHEN (
                (COALESCE(norm_rank, 0) * 0.50) + 
                (COALESCE(norm_fans, 0) * 0.30) + 
                (COALESCE(norm_track_rank, 0) * 0.20)
            ) * 100 >= 40 THEN '👀 OBSERVAR'
            ELSE '⚠️ DESCARTAR'
        END as ar_recommendation,
        
        -- Insight estratégico basado en datos reales
        CASE 
            WHEN deezer_rank > 500000 AND deezer_fans > 100000 THEN 'Alto Rank + Base de Fans sólida = Éxito consolidado'
            WHEN deezer_rank > 300000 AND top_track_rank > 400000 THEN 'Crecimiento orgánico detectado, monitorear de cerca'
            WHEN fan_rank_ratio > 0.5 THEN 'Excelente conversión de oyentes a fans'
            ELSE 'Datos insuficientes o nicho muy específico'
        END as strategic_insight
        
    FROM artist_metrics
)

SELECT * FROM final_ranking
ORDER BY scouting_score DESC
