{{ config(materialized='table') }}

with matches_ranked as (
    select
        *,
        row_number() over (
            partition by source_match_id
            order by ingestion_time desc
        ) as rn
    from {{ ref('stg_football_data_org__matches') }}
)

select
    'football_data_org' as source,
    source_match_id,
    league,
    season,
    matchday,
    status,
    utc_date,
    home_team_id,
    away_team_id,
    home_score,
    away_score
from matches_ranked
where rn = 1