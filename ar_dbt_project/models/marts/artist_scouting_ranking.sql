{{
    config(
        materialized='table',
        description='Modelo de ranking de artistas para A&R basado en métricas de Spotify y TikTok. Calcula el Scouting Score para identificar talento con potencial de firma.',
        tags=['ar', 'scouting', 'music-analytics']
    )
}}

WITH raw_artists AS (
    -- raw_artists_data es una FUENTE (cargada por el pipeline Python), no un modelo dbt:
    -- se referencia con source(), no con ref(), para que el grafo de dependencias sea correcto.
    SELECT * FROM {{ source('music_raw', 'raw_artists_data') }}
),

-- Limpieza y validación de datos musicales
cleaned_artists AS (
    SELECT 
        artist_name,
        genre,
        spotify_monthly_listeners,
        spotify_followers,
        spotify_save_rate,
        spotify_skip_rate,
        tiktok_video_posts,
        tiktok_total_views,
        growth_rate_30d,
        
        -- Data Quality: Corregir valores atípicos
        CASE 
            WHEN spotify_skip_rate > 1.0 THEN 1.0
            WHEN spotify_skip_rate < 0 THEN 0
            ELSE spotify_skip_rate
        END as valid_skip_rate,
        
        CASE 
            WHEN spotify_save_rate > 1.0 THEN 1.0
            WHEN spotify_save_rate < 0 THEN 0
            ELSE spotify_save_rate
        END as valid_save_rate
        
    FROM raw_artists
    WHERE spotify_save_rate IS NOT NULL
    AND spotify_monthly_listeners > 0
),

-- Cálculo de métricas derivadas (KPIs de Music Business)
artist_metrics AS (
    SELECT 
        *,
        -- Follower to Listener Ratio (Salud de la base de fans)
        ROUND(spotify_followers * 1.0 / NULLIF(spotify_monthly_listeners, 0), 3) as follower_listener_ratio,
        
        -- TikTok Engagement Rate
        ROUND(tiktok_total_views * 1.0 / NULLIF(tiktok_video_posts, 0), 2) as tiktok_avg_views_per_video,
        
        -- Normalización para el scoring (0 a 1)
        ROUND(valid_save_rate / (SELECT MAX(valid_save_rate) FROM cleaned_artists), 4) as norm_save_rate,
        ROUND(1 - (valid_skip_rate / (SELECT MAX(valid_skip_rate) FROM cleaned_artists)), 4) as norm_skip_rate,
        ROUND(
            (growth_rate_30d - (SELECT MIN(growth_rate_30d) FROM cleaned_artists)) / 
            NULLIF((SELECT MAX(growth_rate_30d) FROM cleaned_artists) - (SELECT MIN(growth_rate_30d) FROM cleaned_artists), 0),
            4
        ) as norm_growth
        
    FROM cleaned_artists
),

-- Cálculo del Scouting Score (La fórmula del Music Data Analyst)
final_ranking AS (
    SELECT 
        artist_name,
        genre,
        spotify_monthly_listeners,
        spotify_followers,
        ROUND(valid_save_rate * 100, 2) as save_rate_percentage,
        ROUND(valid_skip_rate * 100, 2) as skip_rate_percentage,
        tiktok_video_posts,
        tiktok_total_views,
        ROUND(growth_rate_30d * 100, 2) as growth_rate_percentage,
        follower_listener_ratio,
        tiktok_avg_views_per_video,
        
        -- SCOUTING SCORE (Pesos basados en industria 2026/2027)
        -- Save Rate: 40% (La métrica reina - indica intención de escucha repetida)
        -- Crecimiento: 30% (Momentum viral)
        -- Skip Rate: 30% (Calidad de retención)
        ROUND(
            (
                (COALESCE(norm_save_rate, 0) * 0.40) + 
                (COALESCE(norm_growth, 0) * 0.30) + 
                (COALESCE(norm_skip_rate, 0) * 0.30)
            ) * 100,
            2
        ) as scouting_score,
        
        -- Clasificación para el Director de A&R
        CASE 
            WHEN (
                (COALESCE(norm_save_rate, 0) * 0.40) + 
                (COALESCE(norm_growth, 0) * 0.30) + 
                (COALESCE(norm_skip_rate, 0) * 0.30)
            ) * 100 >= 75 THEN '🔥 FIRMAR AHORA'
            WHEN (
                (COALESCE(norm_save_rate, 0) * 0.40) + 
                (COALESCE(norm_growth, 0) * 0.30) + 
                (COALESCE(norm_skip_rate, 0) * 0.30)
            ) * 100 >= 40 THEN '👀 OBSERVAR'
            ELSE '⚠️ DESCARTAR'
        END as ar_recommendation,
        
        -- Insight accionable
        CASE 
            WHEN spotify_save_rate > 0.10 AND growth_rate_30d > 0.20 THEN 'Alta retención + Crecimiento viral = PRIORIDAD'
            WHEN tiktok_total_views > 1000000 AND spotify_followers < 10000 THEN 'Viral en TikTok, convertir a Spotify'
            WHEN follower_listener_ratio > 0.5 THEN 'Base de fans leal, listo para monetizar'
            ELSE 'Requiere más datos'
        END as strategic_insight
        
    FROM artist_metrics
)

SELECT * FROM final_ranking
ORDER BY scouting_score DESC
