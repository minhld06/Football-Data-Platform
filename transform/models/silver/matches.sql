{{ config(materialized='table') }}

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
from {{ ref('stg_football_data_org__matches') }}