{{ config(severity='warn') }}

-- silver/players.sql only links an Understat player to an existing
-- football_data_org id when the normalized name matches exactly one fdo
-- player (fdo_players_by_unique_name) -- an ambiguous name is treated as
-- "no match" and gets its own understat_id+100000000 identity instead, to
-- avoid silently merging two different real people. This surfaces those
-- ambiguous cases so a human can check whether it's actually the same
-- person (needs a seeds/player_name_map.csv row) or genuinely two different
-- people sharing a name (no action needed).
with fdo_players as (
    select distinct player_id, player_name
    from {{ ref('stg_football_data_org__players') }}
),

fdo_name_counts as (
    select
        {{ normalize_player_name('player_name') }} as norm_name,
        count(distinct player_id) as fdo_player_count
    from fdo_players
    group by 1
),

understat_names as (
    select distinct raw_player_name
    from {{ ref('stg_understat__player_stats') }}
)

select u.raw_player_name, c.fdo_player_count
from understat_names u
join fdo_name_counts c
    on c.norm_name = {{ normalize_player_name('u.raw_player_name') }}
where c.fdo_player_count > 1
  and not exists (
      select 1
      from {{ ref('player_name_map') }} pm
      where pm.source = 'understat'
        and pm.raw_player_name = u.raw_player_name
  )
