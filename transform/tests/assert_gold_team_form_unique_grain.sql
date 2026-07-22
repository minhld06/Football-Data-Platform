select league, season, team_id, count(*) as n
from {{ ref('team_form_last_5_matches') }}
group by league, season, team_id
having count(*) > 1
