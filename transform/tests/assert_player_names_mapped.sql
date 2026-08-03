{{ config(severity='warn') }}

with understat_check as (
    select
        'understat' as source,
        u.raw_player_name,
        coalesce(pm.player_id, p.player_id) as player_id
    from {{ ref('stg_understat__player_stats') }} u
    left join {{ ref('player_name_map') }} pm
        on pm.source = 'understat'
       and pm.raw_player_name = u.raw_player_name
       and pm.team_id = u.team_id
    left join {{ ref('players') }} p
        on {{ normalize_player_name('p.player_name') }} = {{ normalize_player_name('u.raw_player_name') }}
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
    left join {{ ref('players') }} p
        on {{ normalize_player_name('p.player_name') }} = {{ normalize_player_name('s.raw_player_name') }}
)

select distinct source, raw_player_name
from (
    select * from understat_check
    union all
    select * from statbunker_check
) unmapped_check
where player_id is null