{{ config(materialized='table') }}

with fdo_ranked as (
    select
        *,
        row_number() over (
            partition by player_id
            order by ingestion_time desc
        ) as rn
    from {{ ref('stg_football_data_org__players') }}
    where player_id is not null
),

fdo_deduped as (
    select * from fdo_ranked where rn = 1
),

fdo_players as (
    select
        fdo_deduped.player_id,
        coalesce(overrides.display_name, fdo_deduped.player_name) as player_name,
        fdo_deduped.player_name as raw_fdo_player_name,
        fdo_deduped.position,
        fdo_deduped.date_of_birth,
        fdo_deduped.nationality,
        fdo_deduped.shirt_number,
        fdo_deduped.team_id,
        fdo_deduped.league,
        fdo_deduped.ingestion_time
    from fdo_deduped
    left join {{ ref('player_display_name_overrides') }} as overrides
        on overrides.player_id = fdo_deduped.player_id
),

understat_distinct as (
    select distinct on ({{ normalize_player_name('raw_player_name') }})
        raw_player_name,
        understat_id,
        team_id,
        league,
        ingestion_time
    from {{ ref('stg_understat__player_stats') }}
    where understat_id is not null
    order by {{ normalize_player_name('raw_player_name') }}, ingestion_time desc
),

understat_matched_to_fdo as (
    select
        u.raw_player_name,
        u.understat_id,
        u.league,
        u.ingestion_time,
        coalesce(pm.player_id, f.player_id) as fdo_match_id
    from understat_distinct u
    left join {{ ref('player_name_map') }} pm
        on pm.source = 'understat'
       and pm.raw_player_name = u.raw_player_name
       and pm.team_id = u.team_id
    left join fdo_players f
        on {{ normalize_player_name('f.raw_fdo_player_name') }} = {{ normalize_player_name('u.raw_player_name') }}
),

understat_only as (
    select
        understat_id + 100000000 as player_id,
        raw_player_name as player_name,
        cast(null as text) as position,
        cast(null as date) as date_of_birth,
        cast(null as text) as nationality,
        cast(null as int) as shirt_number,
        cast(null as int) as team_id,
        league,
        ingestion_time
    from understat_matched_to_fdo
    where fdo_match_id is null
)

select player_id, player_name, position, date_of_birth, nationality, shirt_number, team_id, league, ingestion_time
from fdo_players
union all
select player_id, player_name, position, date_of_birth, nationality, shirt_number, team_id, league, ingestion_time
from understat_only
