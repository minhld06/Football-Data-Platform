{{ config(materialized='table') }}

-- Manually curated team/player nickname -> id lookup for /search, e.g.
-- "mu"/"man u"/"man utd" -> Manchester United (team_id 66). See
-- docs/superpowers/specs/2026-08-10-search-alias-fuzzy-match-design.md.
select
    entity_type,
    lower(trim(alias)) as alias,
    entity_id
from {{ ref('search_aliases_seed') }}
