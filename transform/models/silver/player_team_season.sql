{{ config(materialized='table') }}

with players_base as (
    select player_id, player_name, team_id as fdo_team_id, league as fdo_league
    from {{ ref('players') }}
),

-- Ambiguous names (e.g. two real "Idrissa Gueye" players in different leagues)
-- are dropped here rather than fanned out to multiple player_id matches, so an
-- ambiguous name resolves to no match instead of misattributing stats to the
-- wrong player.
players_by_unique_name as (
    select {{ normalize_player_name('player_name') }} as norm_name,
           min(player_id) as player_id
    from players_base
    group by 1
    having count(*) = 1
),

understat_matched as (
    select
        u.season,
        u.league,
        u.team_id,
        coalesce(pm.player_id, p_by_id.player_id, p_by_name.player_id) as player_id,
        u.apps,
        u.minutes,
        u.goals,
        u.assists,
        u.xg,
        u.xa,
        u.xg90,
        u.xa90,
        u.ingestion_time
    from {{ ref('stg_understat__player_stats') }} u
    left join {{ ref('player_name_map') }} pm
        on pm.source = 'understat'
       and pm.raw_player_name = u.raw_player_name
       and pm.team_id = u.team_id
    left join players_base p_by_id
        on p_by_id.player_id = u.understat_id + 100000000
    left join players_by_unique_name p_by_name
        on p_by_name.norm_name = {{ normalize_player_name('u.raw_player_name') }}
),

understat_ranked as (
    select *, row_number() over (
        partition by player_id, season order by ingestion_time desc
    ) as rn
    from understat_matched
    where player_id is not null
),

understat_latest as (
    select * from understat_ranked where rn = 1
),

statbunker_matched as (
    select
        s.season,
        s.league,
        s.team_id,
        coalesce(pm.player_id, p.player_id) as player_id,
        s.goals,
        s.ingestion_time
    from {{ ref('stg_statbunker__player_stats') }} s
    left join {{ ref('player_name_map') }} pm
        on pm.source = 'statbunker'
       and pm.raw_player_name = s.raw_player_name
       and pm.team_id = s.team_id
    left join players_by_unique_name p
        on p.norm_name = {{ normalize_player_name('s.raw_player_name') }}
),

statbunker_ranked as (
    select *, row_number() over (
        partition by player_id, season order by ingestion_time desc
    ) as rn
    from statbunker_matched
    where player_id is not null
),

statbunker_latest as (
    select * from statbunker_ranked where rn = 1
),

all_seasons as (
    select distinct season from understat_latest
    union
    select distinct season from statbunker_latest
),

-- LIMITATION: not season-bounded to when this player was actually at
-- fdo_team_id — fine with one season of data, but a future multi-season
-- crawl needs this scoped, or a player's current club will retroactively
-- backfill onto seasons they weren't there for.
fdo_fallback as (
    select
        p.player_id,
        s.season,
        p.fdo_league as league,
        p.fdo_team_id as team_id
    from players_base p
    cross join all_seasons s
    where p.fdo_team_id is not null
),

team_candidates as (
    select player_id, season, league, team_id, 1 as source_priority, 'understat' as resolved_via
    from understat_latest
    where team_id is not null
    union all
    select player_id, season, league, team_id, 2 as source_priority, 'statbunker' as resolved_via
    from statbunker_latest
    where team_id is not null
    union all
    select player_id, season, league, team_id, 3 as source_priority, 'fdo_fallback' as resolved_via
    from fdo_fallback
),

team_ranked as (
    select *, row_number() over (
        partition by player_id, season order by source_priority asc
    ) as rn
    from team_candidates
),

team_resolved as (
    select player_id, season, league, team_id, resolved_via
    from team_ranked
    where rn = 1
),

disagreement as (
    select
        u.player_id,
        u.season,
        (u.team_id is distinct from sb.team_id) as source_disagreement
    from understat_latest u
    join statbunker_latest sb
        on sb.player_id = u.player_id and sb.season = u.season
)

select
    tr.player_id,
    tr.season,
    tr.league,
    tr.team_id,
    tr.resolved_via,
    coalesce(d.source_disagreement, false) as source_disagreement,
    us.apps,
    us.minutes,
    us.goals as understat_goals,
    us.assists,
    us.xg,
    us.xa,
    us.xg90,
    us.xa90,
    sb.goals as statbunker_goals
from team_resolved tr
left join disagreement d on d.player_id = tr.player_id and d.season = tr.season
left join understat_latest us on us.player_id = tr.player_id and us.season = tr.season
left join statbunker_latest sb on sb.player_id = tr.player_id and sb.season = tr.season
