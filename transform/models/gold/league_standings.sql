{{ config(materialized='table') }}

with us_standings as (
    select
        *,
        row_number() over (
            partition by league, season, team_id
            order by ingestion_time desc
        ) as rn
    from {{ ref('stg_understat__standings') }}
    where team_id is not null
),

us_latest as (
    select *
    from us_standings
    where rn = 1
)

select
    fd.league,
    fd.season,
    fd.team_id,
    t.team_name,
    t.team_short_name,
    t.team_tla,
    fd.position,
    fd.played_games,
    fd.won,
    fd.draw,
    fd.lost,
    fd.points,
    fd.goals_for,
    fd.goals_against,
    fd.goal_difference,
    fd.form,
    us.xg,
    us.xga,
    us.xpts
from {{ ref('standings') }} fd
join {{ ref('teams') }} t
    on t.team_id = fd.team_id
left join us_latest us
    on us.team_id = fd.team_id
   and us.league = fd.league
   and us.season = fd.season