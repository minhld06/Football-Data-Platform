# Gold Layer Data Contract — Football Data Platform

This document describes the tables in the `gold` Postgres schema: what each row
represents, what each column means, and what downstream consumers (backend API,
frontend, chatbot) can rely on. It is meant to be read without opening any dbt
model or YAML file.

General rules that apply to every table below:
- All gold tables are `materialized='table'` — they hold a snapshot of data as of
  the last `dbt build` / `dbt run`, not a live/real-time view. New crawls only
  show up here after crawl → ingest → `dbt build`.
- Grain (the uniqueness guarantee for each table) is enforced by a dbt test in
  `transform/tests/`. If a consumer needs "exactly one row per X", that test is
  the source of truth — check `transform/tests/assert_gold_*_unique_grain.sql`
  before assuming a new column changes the grain.
- `team_id` is always the football_data_org numeric team id. It is the only
  stable identifier for a team across sources — never join gold tables on
  `team_name` (spelling varies across statbunker/understat).

---

## gold.league_standings

**Purpose**: League table (position, points, goal difference, expected-goals
metrics) for the "League Table" frontend page and standings-related chatbot
questions ("where is team X ranked").

**Grain**: 1 row per `(league, season, team_id)`. Enforced by
`assert_gold_league_standings_unique_grain`.

**Freshness**: Reflects the most recent football_data_org standings snapshot
ingested (picked by `ingestion_time`), enriched with the most recent Understat
snapshot for the same team/league/season. Not a live feed — only as fresh as
the last crawl + `dbt build`.

| Column | Type | Meaning | Nullable? |
|---|---|---|---|
| `league` | text | Competition slug, e.g. `premier-league`, `ligue-1` | No |
| `season` | text | Season, format `YYYY-YYYY` | No |
| `team_id` | int | Team identifier, anchored on football_data_org | No |
| `team_name` | text | Full team name | No |
| `team_short_name` | text | Shortened team name | No |
| `team_tla` | text | Three-letter abbreviation (e.g. `MUN`) | No |
| `position` | int | League table rank | No |
| `played_games` | int | Matches played this season | No |
| `won` / `draw` / `lost` | int | Season win/draw/loss counts | No |
| `points` | int | Season points total | No |
| `goals_for` / `goals_against` / `goal_difference` | int | Season goal tallies | No |
| `form` | text | Recent result string as reported by football_data_org (e.g. `WWDLW`) | Yes — null if the team hasn't played yet this season |
| `xg` | numeric | Expected goals (Understat) | **Yes** — null if this team could not be matched to an Understat row (see below) |
| `xga` | numeric | Expected goals against (Understat) | **Yes** — same condition as `xg` |
| `xpts` | numeric | Expected points (Understat) | **Yes** — same condition as `xg` |

**Known limitation**: `xg`/`xga`/`xpts` come from a `left join` against Understat
data. Understat identifies teams by name only, so the match depends on
`transform/seeds/team_name_map.csv` having a row for that team's Understat
spelling. A new or renamed team that hasn't been added to the seed will show up
with `xg`/`xga`/`xpts` as `NULL`, not an error — consumers must handle this as
"expected-goals data unavailable for this team," not treat it as missing/broken
data.

---

## gold.team_form_last_5_matches

**Purpose**: Each team's most recent run of results, for a "form guide" widget
and chatbot questions like "how has team X performed recently."

**Grain**: 1 row per `(league, season, team_id)`. Enforced by
`assert_gold_team_form_unique_grain`.

**Freshness**: Computed from `silver.matches` filtered to `status = 'FINISHED'`,
taking each team's 5 most recent matches by `utc_date` at the time of the last
`dbt build`. Only football_data_org currently supplies match-level data.

| Column | Type | Meaning | Nullable? |
|---|---|---|---|
| `league` | text | Competition slug | No |
| `season` | text | Season, format `YYYY-YYYY` | No |
| `team_id` | int | Team identifier, anchored on football_data_org | No |
| `team_name` | text | Full team name | No |
| `matches_played` | int | Number of finished matches counted, capped at 5 | No — **but can be 1–4** if the team hasn't yet played 5 finished matches this season. Do not assume this is always 5 |
| `wins` / `draws` / `losses` | int | Result counts across the counted matches | No |
| `points` | int | Points earned across the counted matches (3/1/0 per match) | No |
| `goals_for` / `goals_against` | int | Goals scored/conceded across the counted matches | No |
| `form` | text | Result string ordered oldest → newest (e.g. `LDWWW`) | No |

**Known limitation**: Because `matches_played` can be less than 5 early in a
season, any UI/chatbot logic that assumes a fixed 5-match window must read
`matches_played` first rather than hardcoding "last 5."

---

## gold.player_profile

**Purpose**: Player identity and current team, for the `/api/players/{id}`
frontend page and chatbot player lookups.

**Grain**: 1 row per `player_id`. Enforced by `unique`/`not_null` tests on
`player_id` in `transform/models/gold/_gold.yml` (no separate
`assert_*_unique_grain.sql` file needed — `player_id` alone is the grain,
same as `team_id` for `silver.teams`).

**Freshness**: Unlike every other gold table, this one is `materialized='view'`,
not `'table'` — `age` is computed live at query time from `date_of_birth`, so
it's always correct without needing a `dbt build` to refresh it. `team_id`
itself still only reflects the most recent crawl (see known limitations below).

| Column | Type | Meaning | Nullable? |
|---|---|---|---|
| `player_id` | int | Player identifier from football_data_org | No |
| `player_name` | text | Full player name | No |
| `position` | text | Playing position as reported by football_data_org (e.g. `Centre-Back`) | Yes |
| `nationality` | text | Country name as reported by football_data_org (single source, not normalized) | Yes |
| `date_of_birth` | date | Date of birth | Yes |
| `age` | int | Computed at query time from `date_of_birth` | Yes — null if `date_of_birth` is null |
| `shirt_number` | int | Shirt number | Yes |
| `team_id` | int | Team identifier, anchored on football_data_org | No |
| `team_name` | text | Full team name, from `silver.teams` | Yes — null if `team_id` doesn't match any row in `silver.teams` |
| `league` | text | Competition slug the team currently plays in | No |

**Known limitations**:

- **Premier League only.** `crawl_competition()` only crawls squads when
  `crawl_squads=True` (see `crawlers/football_data_org/client.py`), and that's
  only set for Premier League (`PL`). Ligue 1 (`FL1`) is deliberately excluded:
  `GET /v4/teams/{id}` returns `200 OK` with `squad: []` for **every** Ligue 1
  team under the current football-data.org plan — this isn't a per-team gap,
  it's a competition-level data restriction. `gold.player_profile` will have
  **zero rows for Ligue 1** until the account's plan changes; this is a
  deliberate scope decision, not a bug.
- **Squad is current-only, not season-historical.** `GET /v4/teams/{id}` has no
  `season` parameter — it always returns the *current* squad. `team_id` here
  reflects whichever team the player was on at the time of the most recent
  crawl, not necessarily the team they played for during any specific past
  season (e.g. mid-season transfers won't be reflected retroactively).
  Building historical squad tracking would require a dedicated SCD2 dbt
  snapshot on `(player_id, team_id)` (see
  `snapshots/snapshot_football_data_org__standings.sql` for the pattern) — not
  built yet, since no current consumer needs season-accurate historical squads.
- **`/v4/teams/{id}` has its own request quota**, separate from the general
  10 req/min rate limit — observed in practice as `403` responses partway
  through a crawl even for previously-successful requests. Per-team failures
  are logged and skipped (`crawl_competition()` continues with the next team),
  so a quota hit during a crawl just means that team's squad is missing from
  bronze until a later, successful crawl backfills it — not a crash, and not
  silently wrong data.

---

## gold.player_performance

**Purpose**: Player stats — goals, assists, minutes, xG/xA — for the
`/api/players/{id}/performance` frontend page and chatbot questions like
"how many goals has player X scored" or "what's player X's xG."

**Grain**: 1 row per `player_id`. Enforced by `unique`/`not_null` tests on
`player_id` in `transform/models/gold/_gold.yml` (same pattern as
`player_profile` — no separate `assert_*_unique_grain.sql` needed).

**Freshness**: `materialized='table'` — reflects the most recent statbunker
and understat crawls as of the last `dbt build`, each deduped to its latest
snapshot per player (same "latest wins" pattern as `gold.league_standings`'s
Understat join). Base identity (`player_id`, `player_name`, `team_id`) comes
from the same source as `gold.player_profile` (`silver.players`), so it
inherits that table's Premier-League-only, current-squad-only limitations
(see `gold.player_profile` above).

| Column | Type | Meaning | Nullable? |
|---|---|---|---|
| `player_id` | int | Player identifier from football_data_org | No |
| `player_name` | text | Full player name | No |
| `team_id` | int | Team identifier, anchored on football_data_org | No |
| `team_name` | text | Full team name, from `silver.teams` | Yes |
| `league` | text | Competition slug the team currently plays in | No |
| `goals` | int | Season goals (statbunker) | **Yes** — null if this player couldn't be matched to a statbunker row (see below) |
| `assists` | int | Season assists (understat) | **Yes** — same condition as `xg` |
| `apps` | int | Appearances (understat) | **Yes** — same condition as `xg` |
| `minutes` | int | Minutes played (understat) | **Yes** — same condition as `xg` |
| `xg` | numeric | Expected goals (understat) | **Yes** — null if this player couldn't be matched to an understat row |
| `xa` | numeric | Expected assists (understat) | **Yes** — same condition as `xg` |
| `xg90` | numeric | Expected goals per 90 minutes (understat), derived as `xg / (minutes / 90)` since Understat's data endpoint doesn't return it directly | **Yes** — same condition as `xg`, also null if `minutes` is 0 |
| `xa90` | numeric | Expected assists per 90 minutes (understat), derived the same way | **Yes** — same condition as `xg90` |

**Known limitations**:

- **Name matching is by normalized name only, not name + team.** statbunker
  and understat identify players by name (no shared numeric id with
  football_data_org). Matching normalizes case/accents/punctuation
  (`normalize_player_name`, requires the Postgres `unaccent` extension —
  `infra/postgres/migrations/004_enable_unaccent_extension.sql`) and checks
  `transform/seeds/player_name_map.csv` first for exceptions. An earlier
  version of this join also required `team_id` to match `silver.players`'
  *current* squad, but live testing found that dropped ~20-30% of otherwise-
  correct matches for anyone transferred mid-season (`silver.players`
  reflects the latest crawl, while statbunker/understat scope each row to
  the club a player scored/played for at scrape time). The `team_id`
  requirement was removed from the automatic match; `silver.players`
  currently has zero normalized-name collisions, so the false-match risk
  this accepts (two Premier League players someday sharing an identical
  normalized full name) is monitored, not eliminated.
- **The dominant remaining match gap is full legal name vs. common name**,
  e.g. football_data_org's `"Alisson Becker"` vs. understat's `"Alisson"` —
  `normalize_player_name` fixes spelling/accent differences, not
  nickname-vs-full-name gaps. This shows up as `NULL` stats for that player
  (not an error) and as a `warn`-severity row in `assert_player_names_mapped`,
  resolved by adding a row to `player_name_map.csv`. Unlike `team_name_map.csv`
  (a complete manual roster for ~20 stable teams), `player_name_map.csv` is
  reactive and partial by design — ~600 players across two sources change
  every transfer window, so it's updated as gaps are found, not upfront.
- **Understat mid-season transfers**: a comma-joined `team_title` value (e.g.
  `"Bournemouth,Manchester City"`) intentionally resolves `team_id` to `NULL`
  rather than guessing which team is current — `player_id` (and therefore
  stats) can still resolve via the name-only match even when `team_id` is
  `NULL`.
- **statbunker only covers Premier League** (`crawlers/statbunker/scraper.py`'s
  `COMPETITION_IDS` has one entry). `goals` will always be `NULL` for any
  player outside that scope — moot in practice today since `silver.players`
  itself is already Premier-League-only.

---

## Out of scope

`gold_head_to_head` and `gold_match_events_enriched` do not exist yet.
Player-level data is now covered end-to-end by `gold.player_profile`
(identity) and `gold.player_performance` (goals/assists/xG/xA), both
Premier-League-only (see their known limitations above). Match-event-level
data still has no crawler.
