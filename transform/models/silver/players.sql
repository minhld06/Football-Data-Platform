{{ config(materialized='table') }}

with ranked as (
    select
        *,
        row_number() over (
            partition by player_id
            order by ingestion_time desc
        ) as rn
    from {{ ref('stg_football_data_org__players') }}
    where player_id is not null
)

select
    player_id,
    player_name,
    position,
    date_of_birth,
    nationality,
    shirt_number,
    team_id,
    league,
    ingestion_time
from ranked
where rn = 1