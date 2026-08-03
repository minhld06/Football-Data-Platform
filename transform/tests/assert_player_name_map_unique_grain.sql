select source, raw_player_name, team_id, count(*) as n
from {{ ref('player_name_map') }}
group by source, raw_player_name, team_id
having count(*) > 1
