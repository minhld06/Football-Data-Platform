# Player Stats (sub-project 2 of player-level data)

Date: 2026-07-25

## Context

Second and final step toward player-level data, building on
[`2026-07-24-player-identity-design.md`](2026-07-24-player-identity-design.md)
(sub-project 1), which delivered `gold.player_profile` (identity + current
team, football_data_org only, no stats). This spec adds goals (statbunker) and
xG/xA (understat), joined onto the `player_id` anchor established in
sub-project 1.

Both sources are covered in one spec/one build rather than split further,
because they share the same core problem — matching a source's own player
name string onto `player_id` — and both feed the same `gold.player_performance`
table.

Site structure was checked directly (not assumed) before writing this spec:

- **statbunker**: no competition-wide "Top Scorers" page. Scores are listed
  per club at `/competitions/TopGoalScorers?comp_id={comp_id}&club_id={club_id}`.
  `club_id` is not something we need to hardcode or look up separately — it's
  already embedded in the `<a href>` wrapping each team name on the standings
  page `get_standings()` already scrapes (`cols[1].find("a")`). The
  top-scorers page itself has no "team" column, since it's already scoped to
  one club.
- **understat**: no separate page needed. The player-stats table
  (`Player, Team, Apps, Min, G, A, xG, xA, xG90, xA90`) is the 4th `<table>` on
  the exact same `/league/{league}/{season}` page `get_standings()` already
  loads via Playwright — just a different table index. `xG`/`xA` have the same
  `+/-` suffix quirk already handled for `xG`/`xGA` in the existing standings
  parser. Edge case found: a player transferred mid-season shows a
  comma-joined team string (e.g. `"Bournemouth, Manchester City"`).

## Decisions

### Crawler — statbunker (`crawlers/statbunker/scraper.py`)

- `get_standings()`: add a `"club_id"` key to each row, parsed from the
  `href` of the `<a>` tag wrapping the team name in `cols[1]` (the same
  element `get_standings` already reads for the team name). Purely additive —
  existing consumers of the row dict are unaffected.
- New `get_top_scorers(comp_id, club_id)`: `GET
  /competitions/TopGoalScorers?comp_id={comp_id}&club_id={club_id}`, same
  `retry_request` pattern as `get_standings`. Parses the table into rows:
  `player, goals, fh, sh, fs, ls, h, a` (column order matches the page:
  first-half/second-half/from-start/from-bench-or-late-sub/home/away goal
  splits).
- `crawl_competition()`: after fetching `standings` (now carrying
  `club_id` per row), loop over each row and call
  `get_top_scorers(comp_id, row["club_id"])`. Before saving, inject
  `"team": row["team"]` into every player dict in that club's result (the
  source page has no team column because it's pre-scoped to one club — this
  is provenance metadata we already know from the loop, not fabricated data).
  Save via
  `save_raw(rows, "statbunker", "player_stats", f"{competition_code}_{season}_{club_id}")`.
- Per-club failure: log and skip that club, continue the loop — same
  resilience pattern as the football_data_org squad loop. A failed
  `standings` fetch skips top-scorer crawling entirely (no clubs to loop).

### Crawler — understat (`crawlers/understat/scraper.py`)

- Refactor `get_standings()` to separate "fetch HTML via Playwright" from
  "parse a specific table", so both standings and player stats can be parsed
  from a single page load: `_fetch_league_page_html(league, season)` (the
  existing Playwright logic, unchanged) feeding two parse functions,
  `_parse_standings_table(html)` (existing logic, moved as-is) and
  `_parse_player_stats_table(html)` (new).
- New `get_player_stats(league, season)`: calls `_fetch_league_page_html`,
  then `_parse_player_stats_table`, reading the 4th `<table>` on the page
  (index 3). Parses: `player, team (raw, may be comma-joined), apps, min, g,
  a, xg, xa, xg90, xa90`. `xg`/`xa` use the same `+/-`-suffix split already
  used for `xG`/`xGA`/`xPTS` in the standings parser.
- `crawl_competition()`: fetches the page HTML once, calls both parse
  functions, saves standings as today plus a new
  `save_raw(player_rows, "understat", "player_stats", f"{league}_{season}")`.
  No extra page load, no extra rate-limit cost.

### Ingestion

No code changes. `entity_type="player_stats"` flows through the existing
generic `discovery.py`/`metadata.py` path, same as `entity_type="players"` in
sub-project 1. Verified by running `python ingestion/ingest.py --source
statbunker` and `--source understat` after the crawler changes and confirming
new `bronze.raw_documents` rows with `entity_type='player_stats'`.

### Name normalization — migration + macro

- New migration `infra/postgres/migrations/004_enable_unaccent_extension.sql`:
  `CREATE EXTENSION IF NOT EXISTS unaccent;` — applied manually like
  `001_bronze_raw_documents.sql`, `002_silver_gold_schemas.sql`, and
  `003_bronze_ingested_files.sql`.
- New macro `transform/macros/normalize_player_name.sql`:
  ```sql
  {% macro normalize_player_name(column_name) %}
    lower(regexp_replace(unaccent({{ column_name }}), '[^a-z0-9]+', ' ', 'g'))
  {% endmacro %}
  ```
  Strips accents, lowercases, collapses punctuation/whitespace differences
  (e.g. `"Viktor Gyokeres"` vs a hypothetical `"Viktor Gyökeres"` both
  normalize to `"viktor gyokeres"`).

### Seed — `transform/seeds/player_name_map.csv`

Columns: `source, raw_player_name, team_id, player_id`. Holds **exceptions
only** — names `normalize_player_name` fails to match (nicknames, transliteration
differences too large for accent-stripping to close), not a full manual
roster like `team_name_map.csv`. Starts empty or near-empty; rows are added
as `assert_player_names_mapped` (see Testing below) surfaces misses. This is
a deliberate deviation from the `team_name_map.csv` precedent: teams are ~20
per source and stable across a season, players are ~600+ across two stat
sources and change on every transfer window, so a fully manual seed would be
disproportionate upkeep for the value gained versus normalization.

### Staging — 2 new models

**`stg_statbunker__player_stats.sql`**: reads `bronze.raw_documents` where
`source='statbunker'` and `entity_type='player_stats'`, unnests the array.
Resolves `team_id` by joining `team_name_map` on `(source='statbunker',
raw_team_name = row.team)` — identical to `stg_statbunker__standings`.
Resolves `player_id` by first checking `player_name_map` (exact match on
`source`/`raw_player_name`/`team_id`), falling back to joining `silver.players`
on `normalize_player_name(player_name) = normalize_player_name(raw_player_name)
AND team_id = team_id` from the team-name-map join. Output columns:
`season, league, team_id, player_id, raw_player_name, goals, fh, sh, fs, ls,
h, a`.

**`stg_understat__player_stats.sql`**: same shape, reading
`entity_type='player_stats'` from `source='understat'`. One extra rule before
the `team_name_map` join: if `row.team` contains a comma (mid-season
transfer), skip the team lookup and leave `team_id` (and therefore
`player_id`, since it depends on team_id) as `NULL` rather than guessing which
of the listed teams is current. Output columns: `season, league, team_id,
player_id, raw_player_name, apps, minutes, goals, assists, xg, xa, xg90,
xa90`.

Neither model gets a `silver.*` promotion — mirrors how `stg_understat__standings`
is joined directly into `gold.league_standings` today without an intermediate
silver table, since football_data_org (via `silver.players`, from sub-project 1)
is already the identity anchor.

### Gold — `gold/player_performance.sql`

`materialized='table'`. Left-joins `silver.players` (base) to
`stg_statbunker__player_stats` and `stg_understat__player_stats` on
`player_id`.

Columns: `player_id, player_name, team_id, team_name, league, goals
(statbunker), assists (understat), apps (understat), minutes (understat), xg,
xa, xg90, xa90`. `team_name` comes from re-joining `silver.teams`, same as
`player_profile`.

Grain: one row per `player_id`. Tests in `_gold.yml`: `unique` + `not_null` on
`player_id`.

### Testing — `assert_player_names_mapped.sql`

Mirrors `assert_team_names_mapped.sql`: unions
`(source, raw_player_name)` from both new staging models where `player_id is
null`, i.e. rows that neither `player_name_map` nor normalized-name matching
could resolve. Unlike `assert_team_names_mapped` (default `error` severity,
appropriate for a small, stable team roster), this test is configured with
`{{ config(severity='warn') }}` — new signings and transfers appear often
enough that hard-failing `dbt build` on every unmatched name would block
routine runs. A warning still surfaces the gap so `player_name_map.csv` can be
updated, without stopping the pipeline.

### Known limitations (to document in `docs/gold_data_contract.md`)

- **Mid-season transfers on understat are unmapped, not misattributed.** A
  comma-joined `team` value on the understat player-stats table intentionally
  resolves to `NULL` `team_id`/`player_id` rather than guessing — same
  "silently null, not an error" contract already established for `xg`/`xga`
  on `gold.league_standings`.
- **Name matching can miss on first crawl after a transfer window.**
  `normalize_player_name` handles accent/case/punctuation differences but not
  nicknames or large transliteration differences (e.g. a source using a
  common nickname instead of the registered name). These show up as `warn`-severity
  test failures in `assert_player_names_mapped` and must be fixed by adding a
  row to `player_name_map.csv` — an ongoing manual step, smaller in volume
  than a fully manual seed but not eliminated.
- **statbunker goal-split columns (`fh/sh/fs/ls/h/a`) are not renamed or
  explained on the site itself** — carried through as-is (first half/second
  half/from start/from bench-or-late-sub/home/away, best-effort interpretation
  from column position) since they're supplementary, not load-bearing for any
  planned Week 5 endpoint.

## Testing plan

1. `python crawlers/statbunker/scraper.py` — confirm
   `data/raw/statbunker/player_stats/{date}/PL_2025-2026_{club_id}_*.json`
   created for all 20 clubs, each row carrying a `team` field.
2. `python crawlers/understat/scraper.py` — confirm
   `data/raw/understat/player_stats/{date}/EPL_2025-2026_*.json` and
   `Ligue_1_2025-2026_*.json` created.
3. `python ingestion/ingest.py --source statbunker` and `--source understat`
   — confirm new `bronze.raw_documents` rows with `entity_type='player_stats'`.
4. Apply `infra/postgres/migrations/004_enable_unaccent_extension.sql`.
5. `dbt build` in `transform/` — staging/gold run clean; `unique`/`not_null`
   on `gold.player_performance.player_id` pass; note (don't necessarily fix
   immediately) any `assert_player_names_mapped` warnings.
6. Spot-check `select * from gold.player_performance where goals is not null
   or xg is not null limit 20` — sanity-check a few known players (e.g.
   Haaland, Saka) have plausible goals/xg/xa values and correct `team_name`.
7. Add `player_name_map.csv` rows for any names surfaced by step 5, re-run
   `dbt build`, confirm the warning count drops.

## Out of scope

- `silver.player_stats` intermediate table — not needed; staging feeds gold
  directly, matching the `stg_understat__standings` → `gold.league_standings`
  precedent.
- Historical/season-over-season player stats — `gold.player_performance` is a
  current-snapshot table like `player_profile`, not a time series. A season
  dimension could be added later if a career-history view becomes a real
  requirement.
- Backfilling `player_name_map.csv` proactively for all players — seeded
  reactively from `assert_player_names_mapped` warnings, not written upfront.
- Ligue 1 support for statbunker — out of scope because the existing
  statbunker standings crawler only covers Premier League today
  (`COMPETITION_IDS` has one entry); player stats follows the same scope.
