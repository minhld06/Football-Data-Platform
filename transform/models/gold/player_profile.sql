{{ config(materialized='view') }}

with latest_team as (
    select distinct on (player_id)
        player_id, team_id, league
    from {{ ref('player_team_season') }}
    order by player_id, season desc
)

select
    p.player_id,
    p.player_name,
    p.position,
    p.nationality,
    p.date_of_birth,
    date_part('year', age(current_date, p.date_of_birth))::int as age,
    p.shirt_number,
    lt.team_id,
    t.team_name,
    coalesce(lt.league, p.league) as league
from {{ ref('players') }} p
left join latest_team lt on lt.player_id = p.player_id
left join {{ ref('teams') }} t on t.team_id = lt.team_id