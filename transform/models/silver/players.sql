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
    ranked.player_id,
    coalesce(overrides.display_name, ranked.player_name) as player_name,
    ranked.position,
    ranked.date_of_birth,
    ranked.nationality,
    ranked.shirt_number,
    ranked.team_id,
    ranked.league,
    ranked.ingestion_time
from ranked
left join {{ ref('player_display_name_overrides') }} as overrides
    on overrides.player_id = ranked.player_id
where rn = 1