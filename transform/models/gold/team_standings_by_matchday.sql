{{ config(materialized='table') }}

-- Reshapes each finished match into one row per team (their own goals_for/
-- goals_against/result), then cumulatively sums over each team's own match
-- history ordered by utc_date. No `position` column: ranking teams against
-- each other as of an arbitrary date is a query-time concern (each team may
-- have played a different number of games by that date), not something this
-- table can precompute per row. See docs/gold_data_contract.md.

with team_matches as (
    select
        league,
        season,
        home_team_id as team_id,
        source_match_id,
        utc_date,
        home_score as goals_for,
        away_score as goals_against,
        case when home_score > away_score then 1 else 0 end as won,
        case when home_score = away_score then 1 else 0 end as draw,
        case when home_score < away_score then 1 else 0 end as lost
    from {{ ref('match_results') }}
    where status = 'FINISHED'

    union all

    select
        league,
        season,
        away_team_id as team_id,
        source_match_id,
        utc_date,
        away_score as goals_for,
        home_score as goals_against,
        case when away_score > home_score then 1 else 0 end as won,
        case when home_score = away_score then 1 else 0 end as draw,
        case when away_score < home_score then 1 else 0 end as lost
    from {{ ref('match_results') }}
    where status = 'FINISHED'
),

with_points as (
    select
        *,
        won * 3 + draw as points
    from team_matches
)

select
    league,
    season,
    team_id,
    source_match_id,
    utc_date,
    row_number() over w as played_games,
    sum(won) over w as won,
    sum(draw) over w as draw,
    sum(lost) over w as lost,
    sum(points) over w as points,
    sum(goals_for) over w as goals_for,
    sum(goals_against) over w as goals_against,
    sum(goals_for) over w - sum(goals_against) over w as goal_difference
from with_points
window w as (
    partition by league, season, team_id
    order by utc_date, source_match_id
    rows between unbounded preceding and current row
)
