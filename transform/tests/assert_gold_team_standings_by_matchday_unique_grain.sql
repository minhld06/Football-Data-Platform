select league, season, team_id, source_match_id, count(*) as n
from {{ ref('team_standings_by_matchday') }}
group by league, season, team_id, source_match_id
having count(*) > 1
