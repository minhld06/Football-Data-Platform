# Player Identity (sub-project 1 of player-level data)

Date: 2026-07-24

## Context

First step toward player-level data (squad, top scorers, xG/xA), needed before
Week 5 API endpoints like `/api/players/{id}`. The full feature spans three
crawlers (football_data_org squad, statbunker top scorers, understat xG) plus
staging/silver/gold across all of them — too large for one spec, so it's split
into two vertical slices:

1. **Player identity** (this spec) — football_data_org squad only. Mirrors how
   `silver.teams` anchors `team_id` on football_data_org: one source, numeric
   `player_id` already provided by the API, no cross-source name mapping needed.
2. **Player stats** (separate spec, later) — statbunker top scorers + understat
   xG/xA, joined onto `player_id` via a new `player_name_map.csv` seed. Depends
   on this spec being done first.

## Decisions

### Crawler (`crawlers/football_data_org/client.py`)

- New `get_squad(team_id)`: `GET /v4/teams/{id}`, same `retry_request` +
  `limiter.wait()` pattern as `get_standings`/`get_matches`. This endpoint takes
  no `season` param — it always returns the *current* squad, not a
  season-specific historical one (documented as a known limitation below).
- `crawl_competition()` extracts `team.id` from the `TOTAL` block of the
  `standings` response it already fetched in the same call (no extra file read,
  no extra API call) and loops `get_squad(team_id)` for each team, saving via
  `save_raw(squad, "football_data_org", "players", f"{competition_code}_{season}_{team_id}")`.
- Runs automatically as part of every `crawl_competition()` call (same cadence
  as standings/matches), not a separate manual step. Adds ~20 requests per
  competition (~2 min at the 6s rate limit) — accepted cost.
- Per-team failure (bad response, JSON error): log and skip that team, continue
  the loop. A failed `standings` fetch skips squad crawling entirely for that
  competition (no team_ids to loop).

### Ingestion

No code changes. `entity_type="players"` flows through the existing generic
`discovery.py`/`metadata.py` path. Verified by running
`python ingestion/ingest.py --source football_data_org` after the crawler change
and confirming new `bronze.raw_documents` rows with `entity_type='players'`.

### Staging — `stg_football_data_org__players.sql`

Reads `bronze.raw_documents` where `source='football_data_org'` and
`entity_type='players'`. Payload shape: top-level `id` (team id) + `squad`
array of `{id, name, position, dateOfBirth, nationality, shirtNumber}`. Unnests
`squad` to one row per player: `player_id, player_name, position,
date_of_birth, nationality, shirt_number, team_id, league, season,
ingestion_time`.

### Silver — `silver/players.sql`

`materialized='table'`. Dedupes on `player_id` via
`row_number() over (partition by player_id order by ingestion_time desc)`,
keeping `rn = 1` — same "latest snapshot wins" pattern as `silver.standings`.
This also resolves transfers: if a player's `team_id` changes between crawls,
the most recent crawl wins.

Grain: one row per `player_id` (like `silver.teams`). Tests in `_silver.yml`:
`unique` + `not_null` on `player_id` — no separate `assert_*.sql` grain test
needed, matching how `teams` (single-column grain) is tested today.

### Gold — `gold/player_profile.sql`

`materialized='view'`, not `table`. Left-joins `silver.players` to
`silver.teams` for `team_name`, and computes
`age = date_part('year', age(current_date, date_of_birth))`. Using a view
(rather than the `table` materialization every other gold model uses) means
`age` is always correct at query time instead of going stale between
`dbt build` runs — acceptable here because the join is a single non-aggregating
left join over a small table (~600-700 players total), so there's no read-time
cost that would justify pre-materializing.

Columns: `player_id, player_name, position, nationality, date_of_birth, age,
shirt_number, team_id, team_name, league`.

Grain: one row per `player_id`. Tests in `_gold.yml`: `unique` + `not_null` on
`player_id`.

### Known limitations (to document in `docs/gold_data_contract.md`)

- **Squad is current-only, not season-historical.** `GET /v4/teams/{id}` has no
  `season` param, so `gold.player_profile.team_id` always reflects the most
  recent crawl, regardless of which season's standings/matches happen to be
  associated in the filename. There's no way to reconstruct "which team was
  player X on during season 2025-2026" from this data. Accepted as a source
  constraint, not a bug — building historical squad tracking would require an
  SCD2 dbt snapshot (like `snapshot_football_data_org__standings.sql`) on
  `(player_id, team_id)`, deferred until a real feature need arises (e.g. a
  player career-history view).

## Testing plan

1. `python crawlers/football_data_org/client.py` — confirm
   `data/raw/football_data_org/players/{date}/PL_2025_{team_id}_*.json` and
   `FL1_2025_{team_id}_*.json` files are created for every team in both
   competitions.
2. `python ingestion/ingest.py --source football_data_org` — confirm new
   `bronze.raw_documents` rows with `entity_type='players'`.
3. `dbt build` in `transform/` — staging/silver/gold run clean, `unique`/
   `not_null` tests on `player_id` pass.
4. `select * from gold.player_profile limit 10` (and a few spot-check players)
   — verify `team_name`, `age`, `nationality` look correct.

## Out of scope

- Player stats (statbunker top scorers, understat xG/xA) — sub-project 2,
  separate spec, depends on this one.
- `player_name_map.csv` seed — not needed here; `player_id` is already a stable
  numeric key from football_data_org, unlike team names across sources.
- SCD2 snapshot for squad/transfer history — see known limitations above.
- Updating `CLAUDE.md` — the gold contract doc is already referenced from
  there; no structural changes needed to `CLAUDE.md` itself.
