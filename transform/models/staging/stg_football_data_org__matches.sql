with matches_raw as (
    select season, league, ingestion_time, payload
    from {{ source('bronze', 'raw_documents') }}
    where source = 'football_data_org'
      and entity_type = 'matches'
),

matches_unnested as (
    select
        season,
        league,
        ingestion_time,
        jsonb_array_elements(payload -> 'matches') as match_json
    from matches_raw
)

select
    season,
    league,
    ingestion_time,
    (match_json ->> 'id')::int as source_match_id,
    (match_json ->> 'matchday')::int as matchday,
    match_json ->> 'status' as status,
    (match_json ->> 'utcDate')::timestamp as utc_date,
    (match_json -> 'homeTeam' ->> 'id')::int as home_team_id,
    (match_json -> 'awayTeam' ->> 'id')::int as away_team_id,
    (match_json -> 'score' -> 'fullTime' ->> 'home')::int as home_score,
    (match_json -> 'score' -> 'fullTime' ->> 'away')::int as away_score
from matches_unnested