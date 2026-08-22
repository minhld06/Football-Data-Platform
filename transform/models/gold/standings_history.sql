{{ config(materialized='table') }}

-- Wraps the SCD2 snapshot of silver.standings so "position as of date X"
-- questions can be answered without exposing the snapshots schema (out of
-- gold, not readable by chatbot_ro) or dbt's internal dbt_valid_from/
-- dbt_valid_to column names.

select
    s.league,
    s.season,
    s.team_id,
    t.team_name,
    t.team_short_name,
    t.team_tla,
    s.position,
    s.played_games,
    s.won,
    s.draw,
    s.lost,
    s.points,
    s.goals_for,
    s.goals_against,
    s.goal_difference,
    s.form,
    s.dbt_valid_from as valid_from,
    s.dbt_valid_to as valid_to
from {{ ref('snapshot_football_data_org__standings') }} s
join {{ ref('teams') }} t on t.team_id = s.team_id
