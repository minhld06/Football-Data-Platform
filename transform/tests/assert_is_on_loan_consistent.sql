select player_id, season, team_id, parent_team_id, is_on_loan
from {{ ref('player_performance') }}
where is_on_loan
  and (parent_team_id is null or team_id = parent_team_id)

union all

select player_id, null as season, team_id, parent_team_id, is_on_loan
from {{ ref('player_profile') }}
where is_on_loan
  and (parent_team_id is null or team_id = parent_team_id)
