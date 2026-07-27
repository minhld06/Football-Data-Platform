{{ config(materialized='view') }}

-- Thin passthrough of silver.teams, materialized as a view (same pattern as
-- player_profile) so team identity stays in sync without needing a rebuild.
select
    team_id,
    team_name,
    team_short_name,
    team_tla,
    league
from {{ ref('teams') }}