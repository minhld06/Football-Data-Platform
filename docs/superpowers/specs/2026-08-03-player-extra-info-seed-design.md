# Player Extra Info Seed — Design

## Problem

`gold.player_profile.nationality`, `.date_of_birth`, and `.shirt_number` are
always `NULL` for "understat-anchored" players — players who have stats in
Understat/StatBunker but no row at all in football_data_org's squad crawl
for their team. This isn't a matching bug: confirmed by inspecting the raw
football_data_org squad payloads directly (e.g.
`data/raw/football_data_org/players/2026-07-24/PL_2025_64_..._281473.json`,
29 Liverpool players, no Mohamed Salah; the Arsenal payload has no Trossard
either) — football_data_org's own squad list is missing these players
upstream, so there's nothing for `silver/players.sql`'s name-matching to
join against. `nationality`/`date_of_birth`/`shirt_number` are only ever
sourced from football_data_org today (Understat/StatBunker don't carry
them), so any player missing from the fdo squad crawl loses all three
fields, no matter how good the name match is.

This has already surfaced for Salah and Trossard, and per the user, several
other players hit the same gap. Re-crawling football_data_org is not
expected to fix it (assumed to be a persistent gap in the free-tier squad
endpoint, not a stale snapshot).

## Goal

A general, reusable backfill mechanism: a manually-maintained seed that
fills in `nationality`/`date_of_birth`/`shirt_number` for any
understat-anchored player, extensible as new gaps are discovered — not a
one-off fix for just Salah/Trossard.

## Non-goals

- Not a fix for the upstream football_data_org squad crawl gap itself.
- Does not touch players who already have an fdo row (even if a future case
  turns up where fdo's own data has a null field for a matched player, that
  is out of scope for this change — confirmed with the user during
  brainstorming).
- No provenance/source column tracking where each manual value came from —
  consistent with the existing `player_display_name_overrides.csv` /
  `player_name_map.csv` seeds, which carry no such column either.

## Design

### 1. Seed file — `transform/seeds/player_extra_info.csv`

```
player_id,nationality,date_of_birth,shirt_number
```

- `player_id` is the **final, already-computed** id used elsewhere in
  `silver.players` for understat-anchored players: `understat_id + 100000000`.
  This mirrors the key style of `player_display_name_overrides.csv`,
  chosen over a `(source, raw_player_name, team_id)` key (the
  `player_name_map.csv` style) because it doesn't depend on name spelling
  or a team_id that can shift season to season — the two problems that
  already cause missed matches elsewhere in this pipeline.
- All three data columns are plain, nullable values — a row doesn't have to
  fill in all three if only some are known.
- Actual rows (Salah's and Trossard's real `player_id`, nationality, DOB,
  shirt number) are populated during implementation by looking their
  current `player_id` up in `gold.player_profile`/`silver.players`, not
  guessed here in the spec.
- Declare `column_types` in `transform/dbt_project.yml` under `seeds:`,
  matching the existing `player_name_map` entry's style:
  `player_id: integer`, `nationality: text`, `date_of_birth: date`,
  `shirt_number: integer`.

### 2. Join/precedence — `transform/models/silver/players.sql`

Only the `understat_only` CTE changes. The seed is left-joined on the same
computed `player_id`, and its columns replace the hard-coded `NULL` casts:

```sql
understat_only as (
    select
        u.understat_id + 100000000 as player_id,
        u.raw_player_name as player_name,
        u.position,
        extra.date_of_birth,
        extra.nationality,
        extra.shirt_number,
        cast(null as int) as team_id,
        u.league,
        u.ingestion_time
    from understat_matched_to_fdo u
    left join {{ ref('player_extra_info') }} extra
        on extra.player_id = u.understat_id + 100000000
    where u.fdo_match_id is null
)
```

`fdo_players` (the branch used whenever football_data_org has a row) is
untouched — football_data_org stays the sole and unconditional source of
truth whenever it has data, per the decision made during brainstorming.
A player with no seed row simply gets `NULL` via the left join, same as
today — this is purely additive.

### 3. Testing

Add `transform/seeds/_seeds.yml` (does not exist yet) with `unique` and
`not_null` tests on `player_extra_info.player_id`. Without this, a
duplicated key in the seed would silently fan out the left join in
`understat_only` and break the 1-row-per-player grain that
`assert_gold_league_standings_unique_grain`-style tests elsewhere in this
project assume. Existing seeds (`player_name_map`, `team_name_map`,
`player_display_name_overrides`) currently have no such schema.yml tests;
this spec only adds coverage for the new seed, not a retrofit of the
others — that's a separate, unrelated cleanup if ever wanted.

### 4. Documentation updates

- `docs/gold_data_contract.md` (all three language sections — EN, FR, VI):
  update the `nationality`/`date_of_birth` nullability notes (currently
  "always `NULL` for understat-anchored players") to reflect that they're
  `NULL` unless backfilled via `player_extra_info.csv`. Update/remove the
  "known limitations" bullet that currently says a
  `player_extra_info.csv` seed "was discussed for this, not built" — it
  now exists.
- `CLAUDE.md`: add `player_extra_info.csv` to the one-line list of seeds
  under "Transform / dbt" (`seeds/` bullet), alongside
  `team_name_map.csv` / `player_name_map.csv`.

## Open items for implementation (not blocking spec approval)

- Look up Salah's and Trossard's real understat-derived `player_id` (and
  any other already-known gaps the user has in mind) to seed the CSV with
  real rows rather than leaving it empty.
