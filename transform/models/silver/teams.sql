{{ config(materialized='table') }}

with teams as (
    select distinct
        team_id,
        team_name,
        team_short_name,
        team_tla,
        league
    from {{ ref('stg_football_data_org__standings') }}
)

select *
from teams
where team_id is not null