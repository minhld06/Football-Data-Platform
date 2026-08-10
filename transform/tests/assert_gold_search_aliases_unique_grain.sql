select entity_type, alias, count(*) as n
from {{ ref('search_aliases') }}
group by entity_type, alias
having count(*) > 1
