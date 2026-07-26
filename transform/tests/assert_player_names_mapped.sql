{{ config(severity='warn') }}

select source, raw_player_name
from (
    select 'statbunker' as source, raw_player_name, player_id
    from {{ ref('stg_statbunker__player_stats') }}

    union all

    select 'understat' as source, raw_player_name, player_id
    from {{ ref('stg_understat__player_stats') }}
) unmapped_check
where player_id is null