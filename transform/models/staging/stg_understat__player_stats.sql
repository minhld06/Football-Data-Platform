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
        -- A mid-season transfer makes Understat's team_title a comma-joined
        -- list of every club the player appeared for this season, e.g.
        -- "Angers,Rennes". Which position (first vs last) is the *current*
        -- club is NOT consistent — verified manually across 24 cases and
        -- roughly half needed the first club, half the last, and two
        -- different players ("Abakar Sylla" / "Junior Mwanga") even shared
        -- the identical string "Nantes,Strasbourg" with opposite correct
        -- answers. So this can only be resolved per-player and per-season,
        -- never by parsing the string: override.team_id (keyed on
        -- understat_id + season, manually verified, see
        -- understat_transfer_team_override.csv) is the only source of truth
        -- for a comma-joined title. A transfer case with no override row yet
        -- resolves to NULL rather than a guess -- a wrong team_id is worse
        -- than a missing one. Keyed on season too because the same player
        -- has a different club (and title) in different seasons.
        coalesce(
            ov.team_id,
            case when r.row_json ->> 'team_title' like '%,%' then null else m_team.team_id end
        ) as team_id,
        (r.row_json ->> 'games')::int as apps,
        (r.row_json ->> 'time')::int as minutes,
        (r.row_json ->> 'goals')::int as goals,
        (r.row_json ->> 'assists')::int as assists,
        (r.row_json ->> 'xG')::numeric as xg,
        (r.row_json ->> 'xA')::numeric as xa,
        r.row_json ->> 'position' as raw_position
    from player_stats_rows r
    left join {{ ref('understat_transfer_team_override') }} ov
        on ov.understat_id = (r.row_json ->> 'id')::int
       and ov.season = r.season
    left join {{ ref('team_name_map') }} m_team
        on m_team.source = 'understat'
       and m_team.raw_team_name = trim(r.row_json ->> 'team_title')
    -- Understat occasionally attaches another club's lineup to a match (e.g.
    -- match 31948 PSG-Rennes carried a Russian club's XI), which then shows
    -- up as a real season row for the wrong team. Manually verified rows are
    -- dropped here; see understat_player_exclusion.csv.
    left join {{ ref('understat_player_exclusion') }} ex
        on ex.understat_id = (r.row_json ->> 'id')::int
       and ex.season = r.season
    where ex.understat_id is null
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
