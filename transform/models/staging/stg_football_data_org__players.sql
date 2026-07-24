with players_raw as (
    select season, league, ingestion_time, payload
    from {{ source('bronze', 'raw_documents') }}
    where source = 'football_data_org'
      and entity_type = 'players'
),

squad_rows as (
    select
        season,
        league,
        ingestion_time,
        (payload ->> 'id')::int as team_id,
        jsonb_array_elements(payload -> 'squad') as player_json
    from players_raw
)

select
    season,
    league,
    ingestion_time,
    team_id,
    (player_json ->> 'id')::int as player_id,
    player_json ->> 'name' as player_name,
    player_json ->> 'position' as position,
    (player_json ->> 'dateOfBirth')::date as date_of_birth,
    player_json ->> 'nationality' as nationality,
    (player_json ->> 'shirtNumber')::int as shirt_number
from squad_rows