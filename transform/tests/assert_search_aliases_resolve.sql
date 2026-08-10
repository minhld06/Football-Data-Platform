{{ config(severity='warn') }}

-- A team/player alias whose entity_id no longer resolves (e.g. a team
-- relegated out of the dataset, or a player_id that shifted) silently
-- returns nothing from /api/search rather than erroring — this is a
-- non-fatal early warning, not a hard failure, matching
-- assert_team_names_mapped.sql/assert_player_names_mapped.sql's pattern.
select entity_type, alias, entity_id
from {{ ref('search_aliases') }}
where (entity_type = 'team' and entity_id not in (select team_id from {{ ref('team_profile') }}))
   or (entity_type = 'player' and entity_id not in (select player_id from {{ ref('player_profile') }}))
