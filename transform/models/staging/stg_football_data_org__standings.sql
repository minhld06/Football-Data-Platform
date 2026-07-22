with standings_raw as (
    select season, league, ingestion_time, payload
    from {{ source('bronze', 'raw_documents') }}
    where source = 'football_data_org'
      and entity_type = 'standings'
),

-- payload -> 'standings' is an array of blocks, each block has "type": TOTAL/HOME/AWAY
standings_blocks as (
    select
        season,
        league,
        ingestion_time,
        jsonb_array_elements(payload -> 'standings') as block
    from standings_raw
),

-- keep only the TOTAL block, then unnest further -> 'table' to get one row per team
standings_rows as (
    select
        season,
        league,
        ingestion_time,
        jsonb_array_elements(block -> 'table') as row_json
    from standings_blocks
    where block ->> 'type' = 'TOTAL'
)

select
    season,
    league,
    ingestion_time,
    (row_json -> 'team' ->> 'id')::int as team_id,
    row_json -> 'team' ->> 'name' as team_name,
    row_json -> 'team' ->> 'shortName' as team_short_name,
    row_json -> 'team' ->> 'tla' as team_tla,
    (row_json ->> 'position')::int as position,
    (row_json ->> 'playedGames')::int as played_games,
    (row_json ->> 'won')::int as won,
    (row_json ->> 'draw')::int as draw,
    (row_json ->> 'lost')::int as lost,
    (row_json ->> 'points')::int as points,
    (row_json ->> 'goalsFor')::int as goals_for,
    (row_json ->> 'goalsAgainst')::int as goals_against,
    (row_json ->> 'goalDifference')::int as goal_difference,
    row_json ->> 'form' as form
from standings_rows