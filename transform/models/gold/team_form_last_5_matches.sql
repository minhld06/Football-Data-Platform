{{ config(materialized='table') }}

with team_matches as (
    select
        league, season,
        home_team_id as team_id,
        utc_date, status,
        case
            when home_score > away_score then 'W'
            when home_score = away_score then 'D'
            else 'L'
        end as result,
        case
            when home_score > away_score then 3
            when home_score = away_score then 1
            else 0
        end as points,
        home_score as goals_for,
        away_score as goals_against
    from {{ ref('matches') }}

    union all

    select
        league, season,
        away_team_id as team_id,
        utc_date, status,
        case
            when away_score > home_score then 'W'
            when away_score = home_score then 'D'
            else 'L'
        end as result,
        case
            when away_score > home_score then 3
            when away_score = home_score then 1
            else 0
        end as points,
        away_score as goals_for,
        home_score as goals_against
    from {{ ref('matches') }}
),

finished as (
    select *
    from team_matches
    where status = 'FINISHED'
),

ranked as (
    select
        *,
        row_number() over (
            partition by league, season, team_id
            order by utc_date desc
        ) as recency_rank
    from finished
),

last_5 as (
    select *
    from ranked
    where recency_rank <= 5
)

select
    l.league,
    l.season,
    l.team_id,
    t.team_name,
    count(*) as matches_played,
    sum(case when l.result = 'W' then 1 else 0 end) as wins,
    sum(case when l.result = 'D' then 1 else 0 end) as draws,
    sum(case when l.result = 'L' then 1 else 0 end) as losses,
    sum(l.points) as points,
    sum(l.goals_for) as goals_for,
    sum(l.goals_against) as goals_against,
    string_agg(l.result, '' order by l.utc_date desc) as form
from last_5 l
join {{ ref('teams') }} t
    on t.team_id = l.team_id
group by l.league, l.season, l.team_id, t.team_name