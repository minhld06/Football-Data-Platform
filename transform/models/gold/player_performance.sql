{{ config(materialized='table') }}

with statbunker_ranked as (
    select
        *,
        row_number() over (
            partition by player_id
            order by ingestion_time desc
        ) as rn
    from {{ ref('stg_statbunker__player_stats') }}
    where player_id is not null
),

statbunker_latest as (
    select * from statbunker_ranked where rn = 1
),

understat_ranked as (
    select
        *,
        row_number() over (
            partition by player_id
            order by ingestion_time desc
        ) as rn
    from {{ ref('stg_understat__player_stats') }}
    where player_id is not null
),

understat_latest as (
    select * from understat_ranked where rn = 1
)

select
    p.player_id,
    p.player_name,
    p.team_id,
    t.team_name,
    p.league,
    sb.goals,
    us.assists,
    us.apps,
    us.minutes,
    us.xg,
    us.xa,
    us.xg90,
    us.xa90
from {{ ref('players') }} p
left join {{ ref('teams') }} t
    on t.team_id = p.team_id
left join statbunker_latest sb
    on sb.player_id = p.player_id
left join understat_latest us
    on us.player_id = p.player_id