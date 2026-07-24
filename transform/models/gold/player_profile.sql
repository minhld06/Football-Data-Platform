{{ config(materialized='view') }}

select
    p.player_id,
    p.player_name,
    p.position,
    p.nationality,
    p.date_of_birth,
    date_part('year', age(current_date, p.date_of_birth))::int as age,
    p.shirt_number,
    p.team_id,
    t.team_name,
    p.league
from {{ ref('players') }} p
left join {{ ref('teams') }} t on t.team_id = p.team_id