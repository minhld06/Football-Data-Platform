{{ config(materialized='table') }}

select
    pts.player_id,
    p.player_name,
    pts.season,
    pts.team_id,
    t.team_name,
    pts.league,
    pts.resolved_via,
    pts.parent_team_id,
    pt.team_name as parent_team_name,
    (pts.parent_team_id is not null and pts.team_id is distinct from pts.parent_team_id) as is_on_loan,
    pts.statbunker_goals as goals,
    pts.assists,
    pts.apps,
    pts.minutes,
    pts.xg,
    pts.xa,
    pts.xg90,
    pts.xa90
from {{ ref('player_team_season') }} pts
join {{ ref('players') }} p on p.player_id = pts.player_id
left join {{ ref('teams') }} t on t.team_id = pts.team_id
left join {{ ref('teams') }} pt on pt.team_id = pts.parent_team_id
