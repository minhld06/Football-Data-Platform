{{ config(materialized='table') }}

with matches as (
    select payload
    from {{ source('bronze', 'raw_documents') }}
    where source = 'football_data_org'
      and entity_type = 'matches'
),

teams_raw as (
    select jsonb_array_elements(matches.payload -> 'matches') as match_json
    from matches
),

teams as (
    select
        (match_json -> 'homeTeam' ->> 'id')::int as team_id,
        match_json -> 'homeTeam' ->> 'name' as team_name,
        match_json -> 'homeTeam' ->> 'shortName' as team_short_name,
        match_json -> 'homeTeam' ->> 'tla' as team_tla
    from teams_raw
    union
    select
        (match_json -> 'awayTeam' ->> 'id')::int,
        match_json -> 'awayTeam' ->> 'name',
        match_json -> 'awayTeam' ->> 'shortName',
        match_json -> 'awayTeam' ->> 'tla'
    from teams_raw
)

select distinct * from teams
where team_id is not null
