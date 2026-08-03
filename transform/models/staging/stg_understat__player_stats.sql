with player_stats_raw as (
    select season, league, ingestion_time, payload
    from {{ source('bronze', 'raw_documents') }}
    where source = 'understat'
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
        r.row_json ->> 'player_name' as raw_player_name,
        (r.row_json ->> 'id')::int as understat_id,
        m.team_id,
        (r.row_json ->> 'games')::int as apps,
        (r.row_json ->> 'time')::int as minutes,
        (r.row_json ->> 'goals')::int as goals,
        (r.row_json ->> 'assists')::int as assists,
        (r.row_json ->> 'xG')::numeric as xg,
        (r.row_json ->> 'xA')::numeric as xa,
        r.row_json ->> 'position' as raw_position
    from player_stats_rows r
    left join {{ ref('team_name_map') }} m
        on m.source = 'understat'
       and m.raw_team_name = r.row_json ->> 'team_title'
)

select
    rt.season,
    rt.league,
    rt.ingestion_time,
    rt.team_id,
    rt.raw_player_name,
    rt.understat_id,
    rt.apps,
    rt.minutes,
    rt.goals,
    rt.assists,
    rt.xg,
    rt.xa,
    -- Understat's JSON endpoint gives season totals only, not the per-90
    -- rates its own on-page table computes client-side — derive them the
    -- same way: xG / (minutes / 90). NULL when minutes is 0 (no minutes played).
    round(rt.xg / nullif(rt.minutes, 0)::numeric * 90, 3) as xg90,
    round(rt.xa / nullif(rt.minutes, 0)::numeric * 90, 3) as xa90,
    {{ normalize_understat_position('rt.raw_position') }} as position
from resolved_team rt
