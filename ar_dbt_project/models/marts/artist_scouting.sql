{{ config(
    materialized='table'
) }}

-- ============================================================================
-- artist_scouting — Mart de scouting para el Director de A&R
-- Réplica exacta en SQL de la lógica del script pandas:
--   1. Data Quality:    descarta save_rate nulo y skip_rate > 1.0 (error de API)
--   2. Normalización:   save_rate/skip_rate/crecimiento a escala 0-1
--                       (skip_rate invertida: menos skip = mejor)
--   3. Scouting Score:  (save 40% + crecimiento 30% + skip 30%) * 100, redondeado a 2 decimales
--   4. Clasificación:   mismos bins que pd.cut([0,40,75,100]) → PDM FIRMAR/OBSERVAR/DESCARTAR
-- ============================================================================

with cleaned as (
    select *
    from {{ ref('stg_artists') }}
    where spotify_save_rate is not null
      and spotify_skip_rate <= 1.0
),

stats as (
    -- Normalizamos sobre el conjunto LIMPIO (igual que el script de pandas)
    select
        max(spotify_save_rate) as max_save,
        max(spotify_skip_rate) as max_skip,
        min(growth_rate_30d)   as min_growth,
        max(growth_rate_30d)   as max_growth
    from cleaned
),

scored as (
    select
        c.artist_name,
        c.genre,
        c.spotify_monthly_listeners,
        c.spotify_followers,
        c.spotify_save_rate,
        c.spotify_skip_rate,
        c.tiktok_video_posts,
        c.tiktok_total_views,
        c.growth_rate_30d,
        c.spotify_save_rate / s.max_save                    as norm_save_rate,
        1 - (c.spotify_skip_rate / s.max_skip)              as norm_skip_rate,
        (c.growth_rate_30d - s.min_growth)
            / (s.max_growth - s.min_growth)                 as norm_growth
    from cleaned c
    cross join stats s
),

final as (
    select
        *,
        round(
            (norm_save_rate * 0.40 + norm_growth * 0.30 + norm_skip_rate * 0.30) * 100,
            2
        ) as scouting_score
    from scored
)

select
    *,
    case
        when scouting_score > 75 then '🔥 FIRMAR AHORA'
        when scouting_score > 40 then '👀 OBSERVAR'
        else '⚠️ DESCARTAR'
    end as ar_recommendation
from final
