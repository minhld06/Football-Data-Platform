with standings_raw as (
    select season, league, ingestion_time, payload
    from {{ source('bronze', 'raw_documents') }}
    where source = 'understat'
      and entity_type = 'standings'
),

standings_rows as (
    select
        season,
        league,
        ingestion_time,
        jsonb_array_elements(payload) as row_json
    from standings_raw
)

select
    r.season,
    r.league,
    r.ingestion_time,
    r.row_json ->> 'team' as raw_team_name,
    m.team_id,
    (r.row_json ->> 'rank')::int as rank,
    (r.row_json ->> 'played')::int as played,
    (r.row_json ->> 'wins')::int as wins,
    (r.row_json ->> 'draws')::int as draws,
    (r.row_json ->> 'losses')::int as losses,
    (r.row_json ->> 'goals_for')::int as goals_for,
    (r.row_json ->> 'goals_against')::int as goals_against,
    (r.row_json ->> 'points')::int as points,
    (r.row_json ->> 'xG')::numeric as xg,
    (r.row_json ->> 'xGA')::numeric as xga,
    (r.row_json ->> 'xPTS')::numeric as xpts
from standings_rows r
left join {{ ref('team_name_map') }} m
    on m.source = 'understat'
   and m.raw_team_name = r.row_json ->> 'team'