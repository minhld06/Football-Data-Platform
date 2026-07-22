{{ config(materialized='table') }}

with standings_ranked as (
    select
        *,
        row_number() over (
            partition by league, season, team_id
            order by ingestion_time desc
        ) as rn
    from {{ ref('stg_football_data_org__standings') }}
)

select
    league,
    season,
    team_id,
    position,
    played_games,
    won,
    draw,
    lost,
    points,
    goals_for,
    goals_against,
    goal_difference,
    form,
    ingestion_time
from standings_ranked
where rn = 1
