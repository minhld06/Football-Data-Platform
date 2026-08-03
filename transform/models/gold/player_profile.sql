{{ config(materialized='view') }}

with latest_team as (
    select distinct on (player_id)
        player_id, team_id, league, parent_team_id, season
    from {{ ref('player_team_season') }}
    order by player_id, season desc
),

-- A season with no non-finished match left is over. Once it's over,
-- football_data_org's undated squad crawl reflects the following
-- transfer window's completed moves, not that season's registrations —
-- comparing it against that season's team_id then misreads a permanent
-- transfer as an active loan. See docs/gold_data_contract.md.
season_in_progress as (
    select distinct league, season
    from {{ ref('match_results') }}
    where status not in ('FINISHED', 'AWARDED')
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
    (lt.parent_team_id is not null
        and lt.team_id is distinct from lt.parent_team_id
        and sip.season is not null) as is_on_loan,
    coalesce(lt.league, p.league) as league
from {{ ref('players') }} p
left join latest_team lt on lt.player_id = p.player_id
left join {{ ref('teams') }} t on t.team_id = lt.team_id
left join {{ ref('teams') }} pt on pt.team_id = lt.parent_team_id
left join season_in_progress sip on sip.league = lt.league and sip.season = lt.season
