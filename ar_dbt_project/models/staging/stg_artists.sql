-- stg_artists: capa staging. Tipa las columnas crudas y las deja listas para
-- la lógica de negocio. NO limpia: la calidad de datos se aplica en el mart
-- (igual que en el script original de pandas, donde dropna/filtrado preceden al score).

with source as (
    select * from {{ source('music_raw', 'raw_artists_data') }}
)

select
    artist_name,
    genre,
    spotify_monthly_listeners,
    spotify_followers,
    cast(spotify_save_rate as double) as spotify_save_rate,
    cast(spotify_skip_rate  as double) as spotify_skip_rate,
    tiktok_video_posts,
    tiktok_total_views,
    cast(growth_rate_30d as double)  as growth_rate_30d
from source
