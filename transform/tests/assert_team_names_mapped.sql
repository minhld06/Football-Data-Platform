select source, raw_team_name
from (
    select 'statbunker' as source, raw_team_name, team_id
    from {{ ref('stg_statbunker__standings') }}

    union all

    select 'understat' as source, raw_team_name, team_id
    from {{ ref('stg_understat__standings') }}
) unmapped_check
where team_id is null