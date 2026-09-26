-- The override seed is keyed on (understat_id, season). A duplicate pair would
-- fan out stg_understat__player_stats rows in the join, so fail hard on it.
select understat_id, season, count(*) as row_count
from {{ ref('understat_transfer_team_override') }}
group by understat_id, season
having count(*) > 1
