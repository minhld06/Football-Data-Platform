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
        coalesce(fdo_deduped.date_of_birth, extra.date_of_birth) as date_of_birth,
        coalesce(fdo_deduped.nationality, extra.nationality) as nationality,
        coalesce(fdo_deduped.shirt_number, extra.shirt_number) as shirt_number,
        fdo_deduped.team_id,
        fdo_deduped.league,
        fdo_deduped.ingestion_time
    from fdo_deduped
    left join {{ ref('player_display_name_overrides') }} as overrides
        on overrides.player_id = fdo_deduped.player_id
    left join {{ ref('player_extra_info') }} as extra
        on extra.player_id = fdo_deduped.player_id
),

understat_ranked as (
    select
        *,
        row_number() over (
            partition by understat_id
            order by ingestion_time desc
        ) as rn
    from {{ ref('stg_understat__player_stats') }}
    where understat_id is not null
),

understat_distinct as (
    select
        -- Understat's own JSON API returns names HTML-entity-escaped (e.g.
        -- "Jun&#039;ai Byfield"). normalize_player_name() already unescapes
        -- this for matching, but understat_only below uses raw_player_name
        -- directly as the display name, so it must be unescaped here too.
        replace(raw_player_name, '&#039;', '''') as raw_player_name,
        understat_id,
        team_id,
        league,
        position,
        ingestion_time
    from understat_ranked
    where rn = 1
),

understat_matched_to_fdo as (
    select
        u.raw_player_name,
        u.understat_id,
        u.league,
        u.position,
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
        u.understat_id + 100000000 as player_id,
        u.raw_player_name as player_name,
        u.position,
        extra.date_of_birth,
        extra.nationality,
        extra.shirt_number,
        cast(null as int) as team_id,
        u.league,
        u.ingestion_time
    from understat_matched_to_fdo u
    left join {{ ref('player_extra_info') }} extra
        on extra.player_id = u.understat_id + 100000000
    where u.fdo_match_id is null
)

select player_id, player_name, position, date_of_birth, nationality, shirt_number, team_id, league, ingestion_time
from fdo_players
union all
select player_id, player_name, position, date_of_birth, nationality, shirt_number, team_id, league, ingestion_time
from understat_only
