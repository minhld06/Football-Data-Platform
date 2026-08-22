select league, season, team_id, valid_from, count(*) as n
from {{ ref('standings_history') }}
group by league, season, team_id, valid_from
having count(*) > 1
