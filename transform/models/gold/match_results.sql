{{ config(materialized='table') }}

-- silver.matches left-joined twice onto silver.teams so the API/frontend
-- never has to join at read time to show a team name next to a match.
select
    m.source_match_id,
    m.league,
    m.season,
    m.matchday,
    m.status,
    m.utc_date,
    m.home_team_id,
    ht.team_name as home_team_name,
    m.away_team_id,
    at.team_name as away_team_name,
    m.home_score,
    m.away_score
from {{ ref('matches') }} m
left join {{ ref('teams') }} ht on ht.team_id = m.home_team_id
left join {{ ref('teams') }} at on at.team_id = m.away_team_id