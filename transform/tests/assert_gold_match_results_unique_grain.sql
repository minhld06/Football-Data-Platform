select source_match_id, count(*) as n
from {{ ref('match_results') }}
group by source_match_id
having count(*) > 1