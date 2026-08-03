{{ config(severity='warn') }}

-- Mirrors transform/models/silver/player_team_season.sql's matching logic:
-- id-first for understat, then a name fallback that only resolves when the
-- normalized name maps to exactly one player_id (ambiguous names, e.g. two
-- real "Idrissa Gueye" players, resolve to no match rather than a wrong one).
with players_by_unique_name as (
    select {{ normalize_player_name('player_name') }} as norm_name,
           min(player_id) as player_id
    from {{ ref('players') }}
    group by 1
    having count(*) = 1
),

understat_check as (
    select
        'understat' as source,
        u.raw_player_name,
        coalesce(pm.player_id, p_by_id.player_id, p_by_name.player_id) as player_id
    from {{ ref('stg_understat__player_stats') }} u
    left join {{ ref('player_name_map') }} pm
        on pm.source = 'understat'
       and pm.raw_player_name = u.raw_player_name
       and pm.team_id = u.team_id
    left join {{ ref('players') }} p_by_id
        on p_by_id.player_id = u.understat_id + 100000000
    left join players_by_unique_name p_by_name
        on p_by_name.norm_name = {{ normalize_player_name('u.raw_player_name') }}
),

statbunker_check as (
    select
        'statbunker' as source,
        s.raw_player_name,
        coalesce(pm.player_id, p.player_id) as player_id
    from {{ ref('stg_statbunker__player_stats') }} s
    left join {{ ref('player_name_map') }} pm
        on pm.source = 'statbunker'
       and pm.raw_player_name = s.raw_player_name
       and pm.team_id = s.team_id
    left join players_by_unique_name p
        on p.norm_name = {{ normalize_player_name('s.raw_player_name') }}
)

select distinct source, raw_player_name
from (
    select * from understat_check
    union all
    select * from statbunker_check
) unmapped_check
where player_id is null