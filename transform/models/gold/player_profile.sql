{{ config(materialized='view') }}

with latest_team as (
    select distinct on (player_id)
        player_id, team_id, league, parent_team_id
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
    lt.parent_team_id,
    pt.team_name as parent_team_name,
    (lt.parent_team_id is not null and lt.team_id is distinct from lt.parent_team_id) as is_on_loan,
    coalesce(lt.league, p.league) as league
from {{ ref('players') }} p
left join latest_team lt on lt.player_id = p.player_id
left join {{ ref('teams') }} t on t.team_id = lt.team_id
left join {{ ref('teams') }} pt on pt.team_id = lt.parent_team_id
