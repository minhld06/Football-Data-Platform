with player_stats_raw as (
    select season, league, ingestion_time, payload
    from {{ source('bronze', 'raw_documents') }}
    where source = 'statbunker'
      and entity_type = 'player_stats'
),

player_stats_rows as (
    select
        season,
        league,
        ingestion_time,
        jsonb_array_elements(payload) as row_json
    from player_stats_raw
),

resolved_team as (
    select
        r.season,
        r.league,
        r.ingestion_time,
        r.row_json ->> 'player' as raw_player_name,
        m.team_id,
        coalesce(nullif(r.row_json ->> 'goals', '-'), '0')::int as goals,
        coalesce(nullif(r.row_json ->> 'fh', '-'), '0')::int as fh,
        coalesce(nullif(r.row_json ->> 'sh', '-'), '0')::int as sh,
        coalesce(nullif(r.row_json ->> 'fs', '-'), '0')::int as fs,
        coalesce(nullif(r.row_json ->> 'ls', '-'), '0')::int as ls,
        coalesce(nullif(r.row_json ->> 'h', '-'), '0')::int as h,
        coalesce(nullif(r.row_json ->> 'a', '-'), '0')::int as a
    from player_stats_rows r
    left join {{ ref('team_name_map') }} m
        on m.source = 'statbunker'
       and m.raw_team_name = r.row_json ->> 'team'
)

select
    rt.season,
    rt.league,
    rt.ingestion_time,
    rt.team_id,
    rt.raw_player_name,
    coalesce(pm.player_id, sp.player_id) as player_id,
    rt.goals,
    rt.fh,
    rt.sh,
    rt.fs,
    rt.ls,
    rt.h,
    rt.a
from resolved_team rt
left join {{ ref('player_name_map') }} pm
    on pm.source = 'statbunker'
   and pm.raw_player_name = rt.raw_player_name
   and pm.team_id = rt.team_id
left join {{ ref('players') }} sp
    on {{ normalize_player_name('sp.player_name') }} = {{ normalize_player_name('rt.raw_player_name') }}
   and sp.team_id = rt.team_id
