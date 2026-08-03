{{ config(severity='warn') }}

select player_id, season
from {{ ref('player_team_season') }}
where source_disagreement = true
