select league, season, team_id, count(*) as n
from {{ ref('snapshot_football_data_org__standings') }}
where dbt_valid_to is null
group by league, season, team_id
having count(*) > 1
