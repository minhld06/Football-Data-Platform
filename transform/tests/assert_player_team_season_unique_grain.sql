select player_id, season, count(*) as n
from {{ ref('player_team_season') }}
group by player_id, season
having count(*) > 1
