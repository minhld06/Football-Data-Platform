select league, season, team_id, count(*) as n
from {{ ref('standings') }}
group by league, season, team_id
having count(*) > 1
