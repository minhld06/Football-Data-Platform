{{ config(materialized='table') }}

-- A season with no non-finished match left is over. Once it's over,
-- football_data_org's undated squad crawl reflects the following
-- transfer window's completed moves, not that season's registrations —
-- comparing it against that season's team_id then misreads a permanent
-- transfer as an active loan. See docs/gold_data_contract.md.
with season_in_progress as (
    select distinct league, season
    from {{ ref('match_results') }}
    where status not in ('FINISHED', 'AWARDED')
)

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
    (pts.parent_team_id is not null
        and pts.team_id is distinct from pts.parent_team_id
        and sip.season is not null) as is_on_loan,
    coalesce(pts.statbunker_goals, pts.understat_goals) as goals,
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
left join season_in_progress sip on sip.league = pts.league and sip.season = pts.season
