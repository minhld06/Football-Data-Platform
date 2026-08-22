# Gold Layer Data Contract — Football Data Platform

# English

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
| `form` | text | Result string ordered newest → oldest (e.g. `WWWDL`), matching `gold.league_standings.form`'s convention | No |

**Known limitation**: Because `matches_played` can be less than 5 early in a
season, any UI/chatbot logic that assumes a fixed 5-match window must read
`matches_played` first rather than hardcoding "last 5."

---

## gold.player_profile

**Purpose**: Player identity and a convenience "most recent season's team",
for the `/api/players/{id}` frontend page and chatbot player lookups.

**Grain**: 1 row per `player_id`. Enforced by `unique`/`not_null` tests on
`player_id` in `transform/models/gold/_gold.yml` (no separate
`assert_*_unique_grain.sql` file needed — `player_id` alone is the grain,
same as `team_id` for `silver.teams`).

**Freshness**: Unlike every other gold table, this one is `materialized='view'`,
not `'table'` — `age` is computed live at query time from `date_of_birth`, so
it's always correct without needing a `dbt build` to refresh it. `team_id`
comes from the player's most recent row in `silver.player_team_season`
(`max(season)`), not directly from football_data_org.

| Column | Type | Meaning | Nullable? |
|---|---|---|---|
| `player_id` | int | Either football_data_org's own numeric id, or understat's native id + a fixed `100000000` offset for players football_data_org has no row for | No |
| `player_name` | text | Full player name | No |
| `position` | text | Playing position — one of `Goalkeeper`, `Defence`, `Midfield`, `Offence`. From football_data_org when a row exists there; backfilled from Understat's own position tag (via `normalize_understat_position()`) for understat-anchored players | Yes — `NULL` only for understat-anchored players whose raw Understat tag is bare `S` (substitute-only, no primary position recorded) |
| `nationality` | text | Country name as reported by football_data_org (single source, not normalized) | Yes — `NULL` for understat-anchored players unless backfilled via the `player_extra_info.csv` seed (football_data_org is otherwise the only source with this field) |
| `date_of_birth` | date | Date of birth | Yes — `NULL` for understat-anchored players unless backfilled via the `player_extra_info.csv` seed (football_data_org is otherwise the only source with this field) |
| `age` | int | Computed at query time from `date_of_birth` | Yes — null if `date_of_birth` is null |
| `shirt_number` | int | Shirt number | Yes — `NULL` for understat-anchored players unless backfilled via the `player_extra_info.csv` seed (football_data_org is otherwise the only source with this field) |
| `team_id` | int | The team this player was resolved to for their most recent season in `silver.player_team_season` — **not** necessarily football_data_org's current roster (see `gold.player_performance` for the season-scoped source of truth) | Yes — null if the player has no `player_team_season` row at all |
| `team_name` | text | Full team name, from `silver.teams` | Yes — same condition as `team_id` |
| `parent_team_id` | int | football_data_org's registered/current squad team_id for this player, independent of which club they're actually playing for this season (see `silver.player_team_season.parent_team_id`) | Yes — `NULL` whenever football_data_org has no squad row for this player (understat-anchored players, or any Ligue 1 player — football_data_org's squad crawl is Premier-League-only) |
| `parent_team_name` | text | Full team name for `parent_team_id`, from `silver.teams` | Yes — same condition as `parent_team_id` |
| `is_on_loan` | boolean | `true` when `team_id` and `parent_team_id` are both non-null and differ, **and** the player's most recent season still has at least one non-`FINISHED`/`AWARDED` match in `gold.match_results` — the player's match-day club disagrees with their football_data_org registration while that season is still live | No — `false` (not `NULL`) whenever `parent_team_id` is `NULL` or the season has already concluded, since there's nothing reliable to compare against |
| `league` | text | Competition slug | No |

**Known limitations**:

- **`team_id` here is a display convenience, not a season-scoped fact.** For
  "who was on team X in season Y," always go through
  `gold.player_performance` (or `GET /teams/{id}/squad?season=Y`), never
  this column — this is exactly the bug this design fixes (previously
  `team_id` came straight from football_data_org's undated "current roster,"
  which showed loaned-out players at their parent club and had zero row for
  players football_data_org's squad crawl didn't cover at all).
- **understat-anchored players (no football_data_org row) have `NULL`
  `date_of_birth`/`nationality`/`shirt_number` unless backfilled.** These
  three are otherwise only ever populated from football_data_org — a manual
  seed, `transform/seeds/player_extra_info.csv`, backfills known gaps (keyed
  on the same computed `player_id`; see
  `docs/superpowers/specs/2026-08-03-player-extra-info-seed-design.md`).
  `position` is handled differently: it's backfilled from Understat's own
  position tag for every understat-anchored player, not just seeded ones
  (see
  `docs/superpowers/specs/2026-08-03-squad-display-fixes-design.md`), so
  it's only `NULL` when Understat's raw tag is bare `S`.
- **Premier League only.** football_data_org's squad crawl only covers
  Premier League (see `crawlers/football_data_org/client.py`); understat
  covers Ligue 1 too, but Ligue 1 players who have no football_data_org row
  will still show up here (understat anchors them independent of league) —
  Ligue 1 coverage for this table isn't a deliberate scope decision the way
  it is for `player_performance`'s statbunker column.
- **The 4-value `position` vocabulary above is hardcoded elsewhere.** The
  squad-ordering query in `backend/routers/teams.py`
  (`ORDER BY CASE pp.position WHEN 'Goalkeeper' THEN 1 ...`) and the
  `POSITION_GROUPS` constant in `frontend/components/SquadTable.tsx` both
  depend on exactly these 4 values — a future change to this domain (e.g. a
  new position value from football_data_org) must update both.
- **`is_on_loan`/`parent_team_id` only detect in-scope loans.** A loan to a
  club outside the crawl's scope (e.g. Championship) produces zero
  Understat/StatBunker rows, so `team_id` falls back to the same value as
  `parent_team_id` — no mismatch, `is_on_loan` stays `false`. Same root
  cause as the `resolved_via = 'fdo_fallback'` gap documented under
  `gold.player_performance` below. See
  docs/superpowers/specs/2026-08-03-parent-club-loan-display-design.md.
- **`is_on_loan` is suppressed once a season has fully concluded.** `parent_team_id`
  comes from football_data_org's undated "current roster," not a
  season-scoped fact (see the LIMITATION comment on
  `player_team_season.sql`'s `fdo_fallback` CTE). This isn't just a future
  risk: it happened with only one season of data — the football_data_org
  squad crawl (2026-07-28) was taken *after* the 2025-2026 season ended
  (last match 2026-05-24), during that summer's transfer window, so
  `parent_team_id` already reflected several players' completed permanent
  moves (e.g. Tielemans to Manchester United, Morgan Rogers to Chelsea,
  Marcos Senesi to Tottenham) while `team_id` still reflected the
  concluded season's stats — misreporting finished transfers as active
  loans. Fixed by requiring the season to still have an unfinished match
  in `gold.match_results` (see `player_profile.sql`'s `season_in_progress`
  CTE); once a season concludes, `is_on_loan` goes `false` for everyone in
  it — including genuinely still-loaned players (e.g. Grealish) — until a
  fresh in-season squad crawl exists for the next season. A permanent
  transfer that happens *mid*-season (e.g. the January window, while the
  season is still "in progress" by this test) is not covered by this fix
  and remains indistinguishable from a genuine loan — no real loan/status
  field exists anywhere in bronze data.

---

## gold.player_performance

**Purpose**: Player stats — goals, assists, minutes, xG/xA — with the team
they were attributed to for a given season, for the
`/api/players/{id}/performance` frontend page and chatbot questions like
"how many goals has player X scored" or "what's player X's xG."

**Grain**: 1 row per `(player_id, season)` — changed from `player_id` alone,
so a player's team can correctly differ between seasons, or (within one
season) be a loan club rather than football_data_org's parent-club roster.
Enforced by `transform/tests/assert_gold_player_performance_unique_grain.sql`
(a dedicated grain test, since the grain is now composite — the earlier
single-column `unique` test on `player_id` no longer applies).

**Freshness**: `materialized='table'` — reflects the most recent statbunker
and understat crawls as of the last `dbt build`. Team resolution priority per
`(player_id, season)`: understat's team (freshest, correctly attributes loan
players to the loan club) → statbunker's team → football_data_org's current
team as a last-resort fallback for players with zero stats rows with a
resolvable team that season. A mid-season transfer makes Understat's own
`team_title` a comma-joined list of every club the player appeared for that
season, e.g. `"Angers,Rennes"`. Which position in that list is the *current*
club is **not consistent** — manually verified across 24 comma-joined cases
(2026-08-04) and roughly half needed the first club, half the last, and two
different players (`"Abakar Sylla"` / `"Junior Mwanga"`) even shared the
identical string `"Nantes,Strasbourg"` with opposite correct answers, so this
can't be resolved by parsing the string at all — only per-player.
`stg_understat__player_stats` looks up `understat_id` in
`seeds/understat_transfer_team_override.csv` (manually verified, all 24
known cases seeded) first; only a comma-joined case with **no** override row
yet falls back to guessing "last club in the list," which should be treated
as an unverified guess, not a fact, until checked and added to the override
seed.

| Column | Type | Meaning | Nullable? |
|---|---|---|---|
| `player_id` | int | Either football_data_org's own numeric id, or understat's native id + a fixed `100000000` offset | No |
| `player_name` | text | Full player name | No |
| `season` | text | `YYYY-YYYY` format | No |
| `team_id` | int | Team this player was attributed to **for this specific season** — see `silver.player_team_season` for the resolution logic | No — `player_team_season`'s `team_candidates` CTE only admits rows with a non-null team_id; a player+season with no resolvable team is omitted from the table entirely rather than appearing with `team_id = NULL` (see limitations). In practice this is now rare: the last-club-wins match on comma-joined `team_title` (see Freshness above) resolves the previously-common mid-season-transfer case |
| `team_name` | text | Full team name, from `silver.teams` | Yes — same condition as `team_id` |
| `parent_team_id` | int | football_data_org's registered/current squad team_id for this player (see `silver.player_team_season.parent_team_id`) | Yes — same condition as `gold.player_profile.parent_team_id` |
| `parent_team_name` | text | Full team name for `parent_team_id`, from `silver.teams` | Yes — same condition as `parent_team_id` |
| `is_on_loan` | boolean | `true` when `team_id` and `parent_team_id` are both non-null and differ for this specific season, **and** that season still has at least one non-`FINISHED`/`AWARDED` match in `gold.match_results` | No — `false` when `parent_team_id` is `NULL` or the season has already concluded |
| `league` | text | Competition slug | No |
| `resolved_via` | text | Which source resolved `team_id` for this player+season: `understat`, `statbunker`, or `fdo_fallback` | No |
| `goals` | int | Season goals — statbunker's count, falling back to understat's own goals count when statbunker has no row for this player+season | **Yes** — null only if neither source has a row for this player+season |
| `assists` | int | Season assists (understat) | **Yes** — same condition as `xg` |
| `apps` | int | Appearances (understat) | **Yes** — same condition as `xg` |
| `minutes` | int | Minutes played (understat) | **Yes** — same condition as `xg` |
| `xg` | numeric | Expected goals (understat) | **Yes** — null if this player has no understat row for this season |
| `xa` | numeric | Expected assists (understat) | **Yes** — same condition as `xg` |
| `xg90` | numeric | Expected goals per 90 minutes (understat), derived as `xg / (minutes / 90)` | **Yes** — same condition as `xg`, also null if `minutes` is 0 |
| `xa90` | numeric | Expected assists per 90 minutes (understat), derived the same way | **Yes** — same condition as `xg90` |

**Known limitations**:

- **`GET /teams/{id}/squad` filters out `resolved_via = 'fdo_fallback'` rows.**
  This is a deliberate trade-off, not a bug: a player with zero understat/
  statbunker stats rows for the season is indistinguishable, using data this
  platform crawls, between "genuinely unused bench player" and "loaned to a
  club outside the crawl's scope" (e.g. Championship) — no loan/status field
  exists anywhere in bronze raw data. Hiding both together was accepted as
  the cost of hiding the latter. This filter is squad-list-only:
  `gold.player_profile.team_id` (the player's own profile page) is untouched
  and still shows the parent club for a loaned player, which remains correct
  "registered club" information. See
  docs/superpowers/specs/2026-08-03-squad-display-fixes-design.md.
- **`is_on_loan` shares the same detection gap as the `fdo_fallback` filter
  above** — an out-of-scope loan can't be distinguished from "still at the
  registered club" using data this platform crawls. See
  docs/superpowers/specs/2026-08-03-parent-club-loan-display-design.md.
- **`is_on_loan` is suppressed once a season has fully concluded.** Same
  fix and same real incident as documented under `gold.player_profile`
  above (Tielemans/Morgan Rogers/Senesi misreported as loans after their
  2025-2026-season stats were compared against a squad crawl taken during
  the following summer's transfer window) — `is_on_loan` now additionally
  requires the row's own `season` to still have an unfinished match in
  `gold.match_results`. A mid-season permanent transfer (season still
  "in progress" by this test) is not covered and remains indistinguishable
  from a genuine loan.
- **Name matching**: Understat-sourced rows resolve `player_id` by an exact
  match on `understat_id + 100000000` first (unambiguous), falling back to
  normalized-name matching only for the remaining case — an Understat row
  matching a football_data_org-anchored player. StatBunker has no native id,
  so it resolves by normalized name only. In both name-fallback cases, an
  ambiguous name (normalizing to more than one real player, e.g. two
  different "Idrissa Gueye" players in different leagues) resolves to **no
  match** rather than fanning out to — and misattributing stats to — the
  wrong player. See `normalize_player_name` (requires the Postgres `unaccent`
  extension) and `transform/seeds/player_name_map.csv` for exceptions.
- **Understat mid-season transfers**: `team_title` is a comma-joined list of
  every club the player appeared for that season when they transferred
  mid-season (e.g. `"Angers,Rennes"`). Before 2026-08-04, an unresolvable
  `team_title` dropped the player+season out of the table entirely — found
  via Ligue 1's Esteban Lepaul disappearing from `gold.player_performance`
  despite 21 real goals, because Ligue 1 has no statbunker fallback to hide
  the gap the way Premier League usually does. The first fix tried "last
  club in the list = current club," but manual verification across all 24
  comma-joined cases at the time found this holds for barely half of them —
  and two different players, `"Abakar Sylla"` and `"Junior Mwanga"`, shared
  the **identical** string `"Nantes,Strasbourg"` with opposite correct
  answers, proving the current club can't be determined by parsing the
  string at all, only by knowing the specific player. `stg_understat__player_stats`
  now looks up `understat_id` in `seeds/understat_transfer_team_override.csv`
  first (manually verified, all 24 then-known cases seeded); only a
  comma-joined case with no override row yet falls back to guessing the last
  club in the list, which should be read as an unverified guess, not a fact,
  until someone checks it and adds a row — the same reactive/partial pattern
  as `player_name_map.csv`.
- **`source_disagreement` in `silver.player_team_season`** (not exposed
  directly here) flags player+seasons where understat and statbunker both
  have a row but report different teams — a genuine mid-season transfer
  within one season. `understat` wins those ties silently; see
  `assert_player_team_season_source_agreement` (warn) to find them.
- **statbunker only covers Premier League clubs, so `goals` falls back to
  understat's own goals count whenever statbunker has no row for that
  player+season** — `coalesce(statbunker_goals, understat_goals)` in
  `gold/player_performance.sql`. This is what gives Ligue 1 players (and any
  Premier League player statbunker's name-matching missed) a real `goals`
  figure instead of always `NULL`; without it, every Ligue 1 player showed
  `NULL` regardless of how many they actually scored. Statbunker still wins
  when both sources have a row for the same player+season, since its Premier
  League coverage is treated as the more authoritative source there. A player
  who transferred from a Premier League club (statbunker-covered) to a Ligue 1
  club mid-season can legitimately carry statbunker-sourced `goals` from
  before the transfer on a row whose `league` is `ligue-1`, per the `league`
  column following the *winning team* (understat, which has team-resolution
  priority), not the stat source.
- **The dominant remaining match gap is full legal name vs. common name,
  nickname vs. legal first name (e.g. `"Josh Laurent"` vs. `"Joshua
  Laurent"`, `"Joe Gomez"` vs. `"Joseph Gomez"`), or a transliteration/
  spelling variant between the two sources** (e.g. `"Christian Romero"` vs.
  `"Cristian Romero"`, `"Yegor Yarmolyuk"` vs. `"Yehor Yarmolyuk"`,
  `"Mickey van de Ven"` vs. `"Micky van de Ven"`). `normalize_player_name`
  fixes case/accent/punctuation differences, not these gaps. Left unresolved,
  an understat row that fails to match spawns its own understat-anchored
  `player_id` instead of merging into the existing football_data_org player —
  i.e. the player appears **twice** in `gold.player_profile` under two
  spellings. This shows up as `NULL` stats for the football_data_org-anchored
  row (not an error) and as a `warn`-severity row in
  `assert_player_names_mapped`, resolved by adding a row to
  `player_name_map.csv`. Unlike `team_name_map.csv` (a complete manual roster
  for ~20 stable teams), `player_name_map.csv` is reactive and partial by
  design — ~600 players across two sources change every transfer window, so
  it's updated as gaps are found, not upfront. Before adding a row for a
  same-team, similar-name pair, verify it's actually one person (compare
  position and minutes played) — some near-identical names on the same squad
  are genuinely two different players (e.g. Metz's `"Ali Youssef"` /
  `"Ali Youssif"`, Nantes' `"Sadibou Sané"` / `"Ibou Sané"`).
- **Understat's own JSON API returns player names HTML-entity-escaped**
  (e.g. `"Jun&#039;ai Byfield"` for `"Jun'ai Byfield"`). `normalize_player_name`
  unescapes this before matching, and `silver.players` unescapes it again
  before assigning `player_name` for understat-anchored players, so it never
  reaches `gold.player_profile` — but a fresh understat crawl introducing a
  new escaped entity type (only `&#039;` has been observed so far) would slip
  through until added to that unescape step.

---

## gold.team_profile

**Purpose**: Team identity (name, short name, TLA) and current league, for
team-lookup use cases in the backend API (e.g. `GET /api/teams/{id}`) and any
consumer that needs a team name without pulling in season-scoped standings.

**Grain**: 1 row per `team_id`. Enforced by `unique`/`not_null` tests on
`team_id` in `transform/models/gold/_gold.yml`.

**Freshness**: `materialized='view'` — thin passthrough of `silver.teams`, so
it always reflects the latest `dbt run`'s silver layer without needing its
own table rebuild (same reasoning as `gold.player_profile`).

| Column | Type | Meaning | Nullable? |
|---|---|---|---|
| `team_id` | int | Team identifier, anchored on football_data_org | No |
| `team_name` | text | Full team name | No |
| `team_short_name` | text | Shortened team name | Yes |
| `team_tla` | text | Three-letter abbreviation (e.g. `MUN`) | Yes |
| `league` | text | Competition slug the team currently plays in | No |

**Known limitation**: same source as `silver.teams` — a team only appears
once it has shown up in at least one football_data_org standings snapshot.

---

## gold.match_results

**Purpose**: Match-level results (score, date, status) with home/away team
names denormalized in, for the `GET /api/matches/{id}` and
`GET /api/teams/{id}/matches` backend endpoints.

**Grain**: 1 row per `source_match_id`. Enforced by `unique`/`not_null` tests
on `source_match_id` in `transform/models/gold/_gold.yml`, plus
`assert_gold_match_results_unique_grain`.

**Freshness**: `materialized='table'` — reflects `silver.matches` as of the
last `dbt build`. Only football_data_org currently supplies match-level data.

| Column | Type | Meaning | Nullable? |
|---|---|---|---|
| `source_match_id` | int | Match identifier from football_data_org | No |
| `league` | text | Competition slug | No |
| `season` | text | Season, format `YYYY-YYYY` | No |
| `matchday` | int | Matchday number | Yes |
| `status` | text | Match status as reported by football_data_org (e.g. `FINISHED`, `SCHEDULED`) | No |
| `utc_date` | timestamp | Kickoff time (UTC) | No |
| `home_team_id` / `away_team_id` | int | Team identifiers, anchored on football_data_org | No |
| `home_team_name` / `away_team_name` | text | Team names, joined from `silver.teams` | Yes — null if the team id doesn't match any row in `silver.teams` |
| `home_score` / `away_score` | int | Full-time score | Yes — null for matches not yet played |

**Known limitation**: no match-event-level data (goal scorers, cards,
substitutions) exists anywhere in this platform yet — there is no crawler for
it. `gold.match_results` only covers match-level score/schedule data, not
events within a match.

---

## gold.team_standings_by_matchday

**Purpose**: Each team's cumulative league-table stats (played games, W/D/L,
points, goals) as of immediately after each of their own finished matches —
the building block for "standings as of date X" queries (e.g. "EPL table in
November"), without depending on how often a standings snapshot happens to be
taken.

**Grain**: 1 row per `(league, season, team_id, source_match_id)`. Enforced by
`assert_gold_team_standings_by_matchday_unique_grain`.

**Freshness**: `materialized='table'` — recomputed from `gold.match_results`
(`status = 'FINISHED'`) as of the last `dbt build`. Only football_data_org
currently supplies match-level data, so this table inherits that scope.

| Column | Type | Meaning | Nullable? |
|---|---|---|---|
| `league` | text | Competition slug | No |
| `season` | text | Season, format `YYYY-YYYY` | No |
| `team_id` | int | Team identifier, anchored on football_data_org | No |
| `source_match_id` | int | The match this cumulative row reflects — join back to `gold.match_results` for match detail | No |
| `utc_date` | timestamp | Kickoff time (UTC) of `source_match_id` — this row is valid from this timestamp until the team's next finished match | No |
| `played_games` | int | Row number of this match within the team's own finished-match history (1, 2, 3, ...) | No |
| `won` / `draw` / `lost` | int | Cumulative win/draw/loss count through this match | No |
| `points` | int | Cumulative points through this match (3/1/0 per match) | No |
| `goals_for` / `goals_against` / `goal_difference` | int | Cumulative goal tallies through this match | No |

**Known limitation**: No `position` column. Ranking teams against each other
requires comparing all teams as of the *same* date, and teams don't all play
on the same dates — so a consumer computing "standings as of date X" must
pick each team's latest row with `utc_date <= X` (e.g. `DISTINCT ON`) and rank
those together (`ORDER BY points DESC, goal_difference DESC, goals_for DESC`),
not read `position` off this table directly. That query-time ranking uses
only points/goal-difference/goals-for as tie-breakers — simpler than whatever
tie-break rule football_data_org applies to `gold.league_standings.position`
(which can include head-to-head or disciplinary points), so a team's
`position` computed this way can occasionally differ by one place from the
official standings in a tie. `xg`/`xga`/`xpts` are not available here — those
come from Understat's own periodic standings scrape, not per-match data (no
match-level xG crawler exists), so they can't be recomputed at an arbitrary
historical date the way W/D/L/points/goals can.

---

## gold.standings_history

**Purpose**: Historical league-table position for every team over time, so
"where was team X in the table in mid-November" or any as-of-a-past-date
standings question can be answered — `gold.league_standings` only ever
reflects the current/latest snapshot.

**Grain**: 1 row per `(league, season, team_id, valid_from)`. Enforced by
`assert_gold_standings_history_unique_grain`.

**Freshness**: `materialized='table'` — a thin passthrough of the
`snapshot_football_data_org__standings` SCD2 snapshot (`transform/snapshots/`),
renaming its `dbt_valid_from`/`dbt_valid_to` columns to `valid_from`/`valid_to`.
A new row only appears when `dbt snapshot` runs and detects a change in one of
its tracked columns (`position`, `played_games`, `won`, `draw`, `lost`,
`points`, `goals_for`, `goals_against`, `goal_difference`, `form`) since the
last snapshot run — **not** on every `dbt build`. If `dbt snapshot` is skipped
for a stretch (e.g. a few matchdays), history for that stretch is permanently
lost; there's no way to reconstruct it afterward.

| Column | Type | Meaning | Nullable? |
|---|---|---|---|
| `league` | text | Competition slug | No |
| `season` | text | Season, format `YYYY-YYYY` | No |
| `team_id` | int | Team identifier, anchored on football_data_org | No |
| `team_name` | text | Full team name | No |
| `team_short_name` | text | Shortened team name | Yes |
| `team_tla` | text | Three-letter abbreviation (e.g. `MUN`) | Yes |
| `position` | int | League table rank as of this row's validity window | No |
| `played_games` | int | Matches played as of this row's validity window | No |
| `won` / `draw` / `lost` | int | Win/draw/loss counts as of this row's validity window | No |
| `points` | int | Points total as of this row's validity window | No |
| `goals_for` / `goals_against` / `goal_difference` | int | Goal tallies as of this row's validity window | No |
| `form` | text | Recent result string as reported by football_data_org (e.g. `WWDLW`) | Yes |
| `valid_from` | timestamp | When this row's values became true (the `dbt snapshot` run that first observed them) | No |
| `valid_to` | timestamp | When this row's values stopped being true (the next `dbt snapshot` run that observed a change) | Yes — `NULL` means this is the team's current/latest state |

**How to answer "position as of date X"**: filter
`valid_from <= X AND (valid_to IS NULL OR valid_to > X)` per team, then that
row's `position` is the answer directly — no query-time re-ranking needed
(unlike `gold.team_standings_by_matchday`, which deliberately has no
`position` column). Note `valid_from`/`valid_to` are snapshot-run timestamps,
not match dates — a matchday played on a Saturday won't show up here until
whenever `dbt snapshot` next ran and noticed the change, which could be
same-day or days later depending on the crawl/build cadence.

**Known limitation**: same freshness caveat as `gold.team_standings_by_matchday`'s
`xg`/`xga`/`xpts` gap — this table only carries football_data_org's own
columns (no Understat expected-goals metrics), since the snapshot it wraps is
of `silver.standings`, not the Understat-enriched `gold.league_standings`.

---

## gold.search_aliases

**Purpose**: Manually curated nickname/abbreviation lookup (e.g. `mu`,
`man c`, `psg`, `mo salah`) consumed by the backend's `GET /api/search`
endpoint, so users don't have to type an exact substring of the official
team/player name.

**Grain**: 1 row per `(entity_type, alias)` pair — a team or player can
have several aliases. Uniqueness is enforced by
`assert_gold_search_aliases_unique_grain` (`transform/tests/`). `not_null`
is enforced on `entity_type`, `alias`, and `entity_id` in
`transform/seeds/_seeds.yml`, and on `entity_type`/`entity_id` in
`transform/models/gold/_gold.yml` (the gold model does not re-test
`alias` — it's a thin passthrough of the seed column, which is already
not-null there). A warn-severity `assert_search_aliases_resolve` test
(`transform/tests/`) flags any alias whose `entity_id` no longer resolves
to a real team/player (e.g. after a relegation or an id change).

**Freshness**: `materialized='table'` — static reference data, rebuilt on
`dbt build` like `gold.league_standings`/`gold.match_results`.

| Column | Type | Meaning | Nullable? |
|---|---|---|---|
| `entity_type` | text | `'team'` or `'player'` | No |
| `alias` | text | Lowercase, trimmed nickname/abbreviation | No |
| `entity_id` | int | Matches `team_id` (if `entity_type = 'team'`) or `player_id` (if `entity_type = 'player'`) elsewhere in `gold.*` | No |

**Known limitation**: coverage is manual and intentionally partial — full
coverage for all teams, but only a small curated set of well-known player
nicknames (most players are searchable by full/partial name via
`/api/search`'s substring match without needing an alias). See
`docs/superpowers/specs/2026-08-10-search-alias-fuzzy-match-design.md`.

---

## Out of scope

`gold_head_to_head` and match-event-level data (goal scorers, cards,
substitutions — a hypothetical `gold_match_events_enriched`) do not exist
yet; there is no crawler for match events. Team identity and match-level
results are now covered by `gold.team_profile` and `gold.match_results` (see
above). Player-level data is covered end-to-end by `gold.player_profile`
(identity) and `gold.player_performance` (goals/assists/xG/xA), both
Premier-League-only (see their known limitations above).

# Français

Ce document décrit les tables du schéma Postgres `gold` : ce que représente
chaque ligne, ce que signifie chaque colonne, et sur quoi les consommateurs en
aval (API backend, frontend, chatbot) peuvent s'appuyer. Il est conçu pour
être lu sans avoir besoin d'ouvrir un modèle dbt ou un fichier YAML.

Règles générales applicables à toutes les tables ci-dessous :
- Toutes les tables gold sont `materialized='table'` — elles contiennent un
  instantané des données à la date du dernier `dbt build` / `dbt run`, et non
  une vue en temps réel. Les nouveaux crawls n'apparaissent ici qu'après
  crawl → ingest → `dbt build`.
- Le grain (la garantie d'unicité de chaque table) est vérifié par un test
  dbt dans `transform/tests/`. Si un consommateur a besoin d'« exactement une
  ligne par X », ce test fait foi — vérifiez
  `transform/tests/assert_gold_*_unique_grain.sql` avant de supposer qu'une
  nouvelle colonne modifie le grain.
- `team_id` est toujours l'identifiant numérique d'équipe de football_data_org.
  C'est le seul identifiant stable pour une équipe à travers les sources — ne
  jamais faire de jointure sur les tables gold via `team_name` (l'orthographe
  varie entre statbunker/understat).

---

## gold.league_standings

**Objectif** : Table de classement (position, points, différence de buts,
indicateurs de buts attendus) pour la page frontend « Classement » (League
Table) et les questions du chatbot liées au classement (« quel est le rang de
l'équipe X »).

**Grain** : 1 ligne par `(league, season, team_id)`. Vérifié par
`assert_gold_league_standings_unique_grain`.

**Fraîcheur** : Reflète le dernier instantané de classement football_data_org
ingéré (sélectionné via `ingestion_time`), enrichi avec le dernier instantané
Understat pour la même équipe/league/saison. Ce n'est pas un flux en temps
réel — les données ne sont fraîches qu'à hauteur du dernier crawl +
`dbt build`.

| Colonne | Type | Signification | Nullable ? |
|---|---|---|---|
| `league` | text | Slug de la compétition, ex. `premier-league`, `ligue-1` | Non |
| `season` | text | Saison, format `YYYY-YYYY` | Non |
| `team_id` | int | Identifiant d'équipe, ancré sur football_data_org | Non |
| `team_name` | text | Nom complet de l'équipe | Non |
| `team_short_name` | text | Nom abrégé de l'équipe | Non |
| `team_tla` | text | Abréviation à trois lettres (ex. `MUN`) | Non |
| `position` | int | Rang dans le classement | Non |
| `played_games` | int | Matchs joués cette saison | Non |
| `won` / `draw` / `lost` | int | Nombre de victoires/nuls/défaites de la saison | Non |
| `points` | int | Total des points de la saison | Non |
| `goals_for` / `goals_against` / `goal_difference` | int | Totaux de buts de la saison | Non |
| `form` | text | Chaîne des résultats récents telle que rapportée par football_data_org (ex. `WWDLW`) | Oui — null si l'équipe n'a pas encore joué cette saison |
| `xg` | numeric | Buts attendus (Expected Goals, Understat) | **Oui** — null si cette équipe n'a pas pu être associée à une ligne Understat (voir ci-dessous) |
| `xga` | numeric | Buts attendus contre (Understat) | **Oui** — même condition que `xg` |
| `xpts` | numeric | Points attendus (Understat) | **Oui** — même condition que `xg` |

**Limite connue** : `xg`/`xga`/`xpts` proviennent d'un `left join` avec les
données Understat. Understat identifie les équipes uniquement par leur nom,
donc la correspondance dépend de la présence d'une ligne dans
`transform/seeds/team_name_map.csv` pour l'orthographe Understat de cette
équipe. Une équipe nouvelle ou renommée qui n'a pas encore été ajoutée au
seed apparaîtra avec `xg`/`xga`/`xpts` à `NULL`, ce qui n'est pas une erreur —
les consommateurs doivent interpréter cela comme « données de buts attendus
indisponibles pour cette équipe », et non comme une donnée manquante ou
cassée.

---

## gold.team_form_last_5_matches

**Objectif** : La série de résultats la plus récente de chaque équipe, pour
un widget « forme récente » et des questions du chatbot comme « quelle est la
forme récente de l'équipe X ».

**Grain** : 1 ligne par `(league, season, team_id)`. Vérifié par
`assert_gold_team_form_unique_grain`.

**Fraîcheur** : Calculée à partir de `silver.matches` filtrée sur
`status = 'FINISHED'`, en prenant les 5 matchs les plus récents de chaque
équipe selon `utc_date` au moment du dernier `dbt build`. Seul
football_data_org fournit actuellement des données au niveau du match.

| Colonne | Type | Signification | Nullable ? |
|---|---|---|---|
| `league` | text | Slug de la compétition | Non |
| `season` | text | Saison, format `YYYY-YYYY` | Non |
| `team_id` | int | Identifiant d'équipe, ancré sur football_data_org | Non |
| `team_name` | text | Nom complet de l'équipe | Non |
| `matches_played` | int | Nombre de matchs terminés comptabilisés, plafonné à 5 | Non — **mais peut être 1–4** si l'équipe n'a pas encore joué 5 matchs terminés cette saison. Ne pas supposer que c'est toujours 5 |
| `wins` / `draws` / `losses` | int | Nombre de victoires/nuls/défaites parmi les matchs comptabilisés | Non |
| `points` | int | Points obtenus parmi les matchs comptabilisés (3/1/0 par match) | Non |
| `goals_for` / `goals_against` | int | Buts marqués/encaissés parmi les matchs comptabilisés | Non |
| `form` | text | Chaîne de résultats ordonnée du plus récent au plus ancien (ex. `WWWDL`), même convention que `gold.league_standings.form` | Non |

**Limite connue** : Comme `matches_played` peut être inférieur à 5 en début
de saison, toute logique UI/chatbot supposant une fenêtre fixe de 5 matchs
doit d'abord lire `matches_played` plutôt que de coder en dur « les 5
derniers ».

---

## gold.player_profile

**Objectif** : Identité du joueur et une équipe "de la saison la plus
récente" fournie par commodité, pour la page frontend `/api/players/{id}`
et les recherches de joueurs par le chatbot.

**Grain** : 1 ligne par `player_id`. Vérifié par les tests `unique`/`not_null`
sur `player_id` dans `transform/models/gold/_gold.yml` (aucun fichier
`assert_*_unique_grain.sql` séparé n'est nécessaire — `player_id` seul
constitue le grain, comme `team_id` pour `silver.teams`).

**Fraîcheur** : Contrairement à toutes les autres tables gold, celle-ci est
`materialized='view'`, et non `'table'` — `age` est calculé en direct au
moment de la requête à partir de `date_of_birth`, donc toujours correct sans
nécessiter de `dbt build` pour se rafraîchir. `team_id` provient de la ligne
la plus récente du joueur dans `silver.player_team_season` (`max(season)`),
pas directement de football_data_org.

| Colonne | Type | Signification | Nullable ? |
|---|---|---|---|
| `player_id` | int | Soit l'id numérique propre à football_data_org, soit l'id natif understat + un offset fixe de `100000000` pour les joueurs sans ligne football_data_org | Non |
| `player_name` | text | Nom complet du joueur | Non |
| `position` | text | Poste — l'une des valeurs `Goalkeeper`, `Defence`, `Midfield`, `Offence`. Provient de football_data_org quand une ligne existe là-bas ; complété à partir du tag de poste propre à Understat (via `normalize_understat_position()`) pour les joueurs ancrés sur understat | Oui — `NULL` uniquement pour les joueurs ancrés sur understat dont le tag Understat brut est simplement `S` (remplaçant uniquement, aucun poste principal enregistré) |
| `nationality` | text | Nom du pays tel que rapporté par football_data_org (source unique, non normalisé) | Oui — `NULL` pour les joueurs ancrés sur understat, sauf complété via le seed `player_extra_info.csv` (football_data_org est sinon la seule source pour ce champ) |
| `date_of_birth` | date | Date de naissance | Oui — `NULL` pour les joueurs ancrés sur understat, sauf complété via le seed `player_extra_info.csv` (football_data_org est sinon la seule source pour ce champ) |
| `age` | int | Calculé au moment de la requête à partir de `date_of_birth` | Oui — null si `date_of_birth` est null |
| `shirt_number` | int | Numéro de maillot | Oui — `NULL` pour les joueurs ancrés sur understat, sauf complété via le seed `player_extra_info.csv` (football_data_org est sinon la seule source pour ce champ) |
| `team_id` | int | L'équipe à laquelle ce joueur a été résolu pour sa saison la plus récente dans `silver.player_team_season` — **pas nécessairement** l'effectif actuel de football_data_org (voir `gold.player_performance` pour la source de vérité par saison) | Oui — null si le joueur n'a aucune ligne `player_team_season` |
| `team_name` | text | Nom complet de l'équipe, provenant de `silver.teams` | Oui — même condition que `team_id` |
| `parent_team_id` | int | Le `team_id` de l'effectif enregistré/actuel du joueur selon football_data_org, indépendamment du club pour lequel il joue réellement cette saison (voir `silver.player_team_season.parent_team_id`) | Oui — `NULL` chaque fois que football_data_org n'a aucune ligne d'effectif pour ce joueur (joueurs ancrés sur understat, ou tout joueur de Ligue 1 — le crawl d'effectifs de football_data_org ne couvre que la Premier League) |
| `parent_team_name` | text | Nom complet de l'équipe pour `parent_team_id`, provenant de `silver.teams` | Oui — même condition que `parent_team_id` |
| `is_on_loan` | boolean | `true` quand `team_id` et `parent_team_id` sont tous deux non-nuls et différents, **et** que la saison la plus récente du joueur a encore au moins un match non-`FINISHED`/`AWARDED` dans `gold.match_results` — le club où le joueur évolue réellement diverge de son enregistrement football_data_org pendant que cette saison est encore en cours | Non — `false` (pas `NULL`) chaque fois que `parent_team_id` est `NULL` ou que la saison est déjà terminée, faute de point de comparaison fiable |
| `league` | text | Slug de la compétition | Non |

**Limites connues** :

- **`team_id` ici est une commodité d'affichage, pas un fait rattaché à une
  saison précise.** Pour « qui jouait dans l'équipe X en saison Y », toujours
  passer par `gold.player_performance` (ou `GET /teams/{id}/squad?season=Y`),
  jamais par cette colonne — c'est exactement le bug que corrige cette
  conception (auparavant `team_id` provenait directement de l'« effectif
  actuel » non daté de football_data_org, qui montrait les joueurs prêtés à
  leur club parent et n'avait aucune ligne pour les joueurs que le crawl
  d'effectifs de football_data_org ne couvrait pas du tout).
- **Les joueurs ancrés sur understat (aucune ligne football_data_org) ont
  `date_of_birth`/`nationality`/`shirt_number` à `NULL` sauf s'ils sont
  complétés.** Ces trois champs ne sont sinon jamais alimentés que par
  football_data_org — un seed manuel, `transform/seeds/player_extra_info.csv`,
  comble les manques connus (indexé sur le même `player_id` calculé ; voir
  `docs/superpowers/specs/2026-08-03-player-extra-info-seed-design.md`).
  `position` est traité différemment : il est complété à partir du propre tag
  de poste d'Understat pour chaque joueur ancré sur understat, pas seulement
  ceux du seed (voir
  `docs/superpowers/specs/2026-08-03-squad-display-fixes-design.md`), donc il
  n'est `NULL` que lorsque le tag brut d'Understat est simplement `S`.
- **Uniquement la Premier League.** Le crawl d'effectifs de football_data_org
  ne couvre que la Premier League (voir
  `crawlers/football_data_org/client.py`) ; understat couvre aussi la Ligue 1,
  mais les joueurs de Ligue 1 sans ligne football_data_org apparaissent quand
  même ici (understat les ancre indépendamment de la league) — la couverture
  Ligue 1 de cette table n'est pas une décision de périmètre délibérée comme
  elle l'est pour la colonne statbunker de `player_performance`.
- **Le vocabulaire à 4 valeurs de `position` ci-dessus est codé en dur
  ailleurs.** La requête de tri de l'effectif dans `backend/routers/teams.py`
  (`ORDER BY CASE pp.position WHEN 'Goalkeeper' THEN 1 ...`) et la constante
  `POSITION_GROUPS` de `frontend/components/SquadTable.tsx` dépendent toutes
  deux exactement de ces 4 valeurs — tout changement futur de ce domaine
  (ex. une nouvelle valeur de poste renvoyée par football_data_org) doit
  mettre à jour les deux.
- **`is_on_loan`/`parent_team_id` ne détectent que les prêts dans le
  périmètre couvert.** Un prêt vers un club hors du périmètre du crawl (ex.
  Championship) ne produit aucune ligne Understat/StatBunker, donc `team_id`
  retombe sur la même valeur que `parent_team_id` — aucun désaccord,
  `is_on_loan` reste `false`. Même cause racine que le manque
  `resolved_via = 'fdo_fallback'` documenté sous `gold.player_performance`
  ci-dessous. Voir
  docs/superpowers/specs/2026-08-03-parent-club-loan-display-design.md.
- **`is_on_loan` est désactivé une fois qu'une saison est totalement
  terminée.** `parent_team_id` provient de l'« effectif actuel » non daté de
  football_data_org, pas d'un fait rattaché à une saison (voir le commentaire
  LIMITATION du CTE `fdo_fallback` de `player_team_season.sql`). Ce n'est pas
  qu'un risque théorique : c'est arrivé avec une seule saison de données — le
  crawl d'effectifs football_data_org (2026-07-28) a été effectué *après* la
  fin de la saison 2025-2026 (dernier match le 2026-05-24), pendant le
  mercato estival, donc `parent_team_id` reflétait déjà plusieurs transferts
  définitifs achevés (ex. Tielemans vers Manchester United, Morgan Rogers
  vers Chelsea, Marcos Senesi vers Tottenham) alors que `team_id` reflétait
  encore les statistiques de la saison terminée — signalant à tort des
  transferts achevés comme des prêts actifs. Corrigé en exigeant que la
  saison ait encore un match non terminé dans `gold.match_results` (voir le
  CTE `season_in_progress` de `player_profile.sql`) ; une fois une saison
  terminée, `is_on_loan` passe à `false` pour tout le monde dans cette saison
  — y compris les joueurs réellement encore prêtés (ex. Grealish) — jusqu'à
  ce qu'un nouveau crawl d'effectif en cours de saison existe pour la saison
  suivante. Un transfert définitif survenant *en cours* de saison (ex. le
  mercato de janvier, pendant que la saison est encore « en cours » selon ce
  test) n'est pas couvert par ce correctif et reste indiscernable d'un
  véritable prêt — aucun champ prêt/statut réel n'existe nulle part dans les
  données bronze.

---

## gold.player_performance

**Objectif** : Statistiques du joueur — buts, passes décisives, minutes
jouées, xG/xA — avec l'équipe à laquelle elles ont été attribuées pour une
saison donnée, pour la page frontend `/api/players/{id}/performance` et des
questions du chatbot comme « combien de buts le joueur X a-t-il marqués » ou
« quel est le xG du joueur X ».

**Grain** : 1 ligne par `(player_id, season)` — changé par rapport à
`player_id` seul, afin que l'équipe d'un joueur puisse correctement différer
d'une saison à l'autre, ou (au sein d'une même saison) être un club de prêt
plutôt que l'effectif du club parent selon football_data_org. Vérifié par un
test de grain dédié,
`transform/tests/assert_gold_player_performance_unique_grain.sql` (le grain
étant désormais composite, l'ancien test `unique` sur la seule colonne
`player_id` ne s'applique plus).

**Fraîcheur** : `materialized='table'` — reflète les crawls statbunker et
understat les plus récents à la date du dernier `dbt build`. Priorité de
résolution d'équipe par `(player_id, season)` : équipe understat (la plus
fraîche, attribue correctement les joueurs prêtés au club de prêt) → équipe
statbunker → équipe actuelle selon football_data_org comme dernier recours
pour les joueurs sans aucune ligne de stats avec une équipe résolvable cette
saison-là.

| Colonne | Type | Signification | Nullable ? |
|---|---|---|---|
| `player_id` | int | Soit l'id numérique propre à football_data_org, soit l'id natif understat + un offset fixe de `100000000` | Non |
| `player_name` | text | Nom complet du joueur | Non |
| `season` | text | Format `YYYY-YYYY` | Non |
| `team_id` | int | Équipe à laquelle ce joueur a été attribué **pour cette saison précise** — voir `silver.player_team_season` pour la logique de résolution | Non — le CTE `team_candidates` de `player_team_season` n'admet que les lignes avec un `team_id` non nul ; un couple joueur+saison sans équipe résolvable est omis de la table plutôt que d'apparaître avec `team_id = NULL` (voir limites). En pratique ce cas est désormais rare : la correspondance « dernier club gagne » sur le `team_title` joint par virgule (voir Fraîcheur ci-dessus) résout le cas auparavant fréquent du transfert en cours de saison |
| `team_name` | text | Nom complet de l'équipe, provenant de `silver.teams` | Oui — même condition que `team_id` |
| `parent_team_id` | int | Le `team_id` de l'effectif enregistré/actuel du joueur selon football_data_org (voir `silver.player_team_season.parent_team_id`) | Oui — même condition que `gold.player_profile.parent_team_id` |
| `parent_team_name` | text | Nom complet de l'équipe pour `parent_team_id`, provenant de `silver.teams` | Oui — même condition que `parent_team_id` |
| `is_on_loan` | boolean | `true` quand `team_id` et `parent_team_id` sont tous deux non-nuls et différents pour cette saison précise, **et** que cette saison a encore au moins un match non-`FINISHED`/`AWARDED` dans `gold.match_results` | Non — `false` quand `parent_team_id` est `NULL` ou que la saison est déjà terminée |
| `league` | text | Slug de la compétition | Non |
| `resolved_via` | text | Quelle source a résolu `team_id` pour ce joueur+saison : `understat`, `statbunker`, ou `fdo_fallback` | Non |
| `goals` | int | Buts de la saison — décompte de statbunker, avec repli sur le décompte propre d'understat quand statbunker n'a pas de ligne pour ce joueur/saison | **Oui** — null uniquement si aucune des deux sources n'a de ligne pour ce joueur/saison |
| `assists` | int | Passes décisives de la saison (understat) | **Oui** — même condition que `xg` |
| `apps` | int | Nombre d'apparitions (understat) | **Oui** — même condition que `xg` |
| `minutes` | int | Minutes jouées (understat) | **Oui** — même condition que `xg` |
| `xg` | numeric | Buts attendus (understat) | **Oui** — null si ce joueur n'a pas de ligne understat pour cette saison |
| `xa` | numeric | Passes décisives attendues (understat) | **Oui** — même condition que `xg` |
| `xg90` | numeric | Buts attendus par 90 minutes (understat), calculé comme `xg / (minutes / 90)` car l'endpoint de données Understat ne le renvoie pas directement | **Oui** — même condition que `xg`, également null si `minutes` vaut 0 |
| `xa90` | numeric | Passes décisives attendues par 90 minutes (understat), calculées de la même manière | **Oui** — même condition que `xg90` |

**Limites connues** :

- **`GET /teams/{id}/squad` filtre les lignes `resolved_via = 'fdo_fallback'`.**
  Il s'agit d'un compromis délibéré, pas d'un bug : un joueur sans aucune
  ligne de stats understat/statbunker pour la saison est indiscernable, avec
  les données que cette plateforme crawl, entre « joueur de banc réellement
  inutilisé » et « prêté à un club hors du périmètre du crawl » (ex.
  Championship) — aucun champ prêt/statut n'existe nulle part dans les
  données bronze brutes. Masquer les deux ensemble a été accepté comme le
  coût pour masquer le second cas. Ce filtre ne concerne que la liste
  d'effectif : `gold.player_profile.team_id` (la page de profil du joueur
  lui-même) n'est pas affecté et montre toujours le club parent pour un
  joueur prêté, ce qui reste une information « club d'enregistrement »
  correcte. Voir
  docs/superpowers/specs/2026-08-03-squad-display-fixes-design.md.
- **`is_on_loan` partage la même lacune de détection que le filtre
  `fdo_fallback` ci-dessus** — un prêt hors périmètre ne peut pas être
  distingué de « toujours au club enregistré » avec les données que cette
  plateforme crawl. Voir
  docs/superpowers/specs/2026-08-03-parent-club-loan-display-design.md.
- **`is_on_loan` est désactivé une fois qu'une saison est totalement
  terminée.** Même correctif et même incident réel que documenté sous
  `gold.player_profile` ci-dessus (Tielemans/Morgan Rogers/Senesi signalés à
  tort comme prêtés après que leurs statistiques de la saison 2025-2026 ont
  été comparées à un crawl d'effectif pris pendant le mercato estival
  suivant) — `is_on_loan` exige désormais en plus que la propre `season` de
  la ligne ait encore un match non terminé dans `gold.match_results`. Un
  transfert définitif en cours de saison (saison encore « en cours » selon ce
  test) n'est pas couvert et reste indiscernable d'un véritable prêt.
- **La correspondance des noms se fait uniquement par nom normalisé, pas nom
  + équipe.** statbunker et understat identifient les joueurs par leur nom
  (pas d'id numérique partagé avec football_data_org). La correspondance
  normalise la casse/les accents/la ponctuation (`normalize_player_name`,
  nécessite l'extension Postgres `unaccent` —
  `infra/postgres/migrations/004_enable_unaccent_extension.sql`) et vérifie
  d'abord `transform/seeds/player_name_map.csv` pour les exceptions. Une
  version antérieure de cette jointure exigeait aussi que `team_id`
  corresponde à l'effectif *actuel* de `silver.players`, mais des tests en
  conditions réelles ont montré que cela faisait perdre ~20-30 % de
  correspondances par ailleurs correctes pour tout joueur transféré en cours
  de saison (`silver.players` reflète le dernier crawl, alors que
  statbunker/understat associent chaque ligne au club pour lequel le joueur a
  joué/marqué au moment du scrape). L'exigence de `team_id` a été retirée de
  la correspondance automatique ; `silver.players` n'a actuellement aucune
  collision de nom normalisé, donc le risque de faux match que cela accepte
  (deux joueurs de Premier League partageant un jour un nom complet normalisé
  identique) est surveillé, pas éliminé.
- **L'écart de correspondance restant le plus fréquent est le nom légal
  complet contre le nom usuel, un diminutif (ex. `"Josh Laurent"` contre
  `"Joshua Laurent"`, `"Joe Gomez"` contre `"Joseph Gomez"`), ou une variante
  de translittération/orthographe entre les deux sources** (ex.
  `"Christian Romero"` contre `"Cristian Romero"`, `"Mickey van de Ven"`
  contre `"Micky van de Ven"`). `normalize_player_name` corrige les
  différences de casse/accents/ponctuation, pas ces écarts-là. Si l'écart
  n'est pas résolu, la ligne understat qui échoue à se rattacher génère son
  propre `player_id` ancré understat au lieu de fusionner avec le joueur
  football_data_org existant — le joueur apparaît alors **deux fois** dans
  `gold.player_profile` sous deux orthographes. Cela se traduit par des
  statistiques `NULL` pour la ligne ancrée football_data_org (pas une erreur)
  et par une ligne de sévérité `warn` dans `assert_player_names_mapped`,
  résolue en ajoutant une ligne à `player_name_map.csv`. Contrairement à
  `team_name_map.csv` (une liste manuelle complète pour ~20 équipes stables),
  `player_name_map.csv` est volontairement réactif et partiel — ~600 joueurs
  répartis sur deux sources changent à chaque mercato, donc il est mis à jour
  au fur et à mesure que les écarts sont découverts, pas à l'avance. Avant
  d'ajouter une ligne pour une paire de noms similaires dans la même équipe,
  vérifier qu'il s'agit bien d'une seule personne (comparer poste et minutes
  jouées) — certains noms quasi identiques dans le même effectif sont bel et
  bien deux joueurs différents (ex. `"Ali Youssef"` / `"Ali Youssif"` à Metz,
  `"Sadibou Sané"` / `"Ibou Sané"` à Nantes).
- **L'API JSON d'Understat renvoie les noms de joueurs avec des entités HTML
  échappées** (ex. `"Jun&#039;ai Byfield"` pour `"Jun'ai Byfield"`).
  `normalize_player_name` les décode avant la correspondance, et
  `silver.players` les décode à nouveau avant d'assigner `player_name` pour
  les joueurs ancrés understat, donc cela n'atteint jamais
  `gold.player_profile` — mais un nouveau type d'entité échappée (seule
  `&#039;` a été observée jusqu'ici) introduit par un futur crawl passerait
  inaperçu tant qu'il ne serait pas ajouté à cette étape de décodage.
- **Transferts en cours de saison chez Understat** : `team_title` est une
  liste jointe par virgule de tous les clubs du joueur cette saison-là (ex.
  `"Angers,Rennes"`). Une première tentative de correction a supposé que
  « le dernier club de la liste = club actuel », mais une vérification
  manuelle des 24 cas a montré que cela ne tient que dans environ la moitié
  des cas — et deux joueurs différents, `"Abakar Sylla"` et
  `"Junior Mwanga"`, partageaient la chaîne **identique**
  `"Nantes,Strasbourg"` avec des réponses correctes opposées, prouvant que le
  club actuel ne peut pas être déduit de la chaîne seule, seulement joueur
  par joueur. `stg_understat__player_stats` cherche désormais `understat_id`
  dans `seeds/understat_transfer_team_override.csv` (vérifié manuellement,
  les 24 cas connus sont renseignés) ; seul un cas sans ligne de dérogation
  retombe sur la supposition « dernier club de la liste », à traiter comme
  une supposition non vérifiée, pas un fait, jusqu'à vérification et ajout
  d'une ligne — même logique réactive que `player_name_map.csv`.
- **statbunker ne couvre que la Premier League, donc `goals` se replie sur le
  décompte propre d'understat dès que statbunker n'a pas de ligne pour ce
  joueur/saison** — `coalesce(statbunker_goals, understat_goals)` dans
  `gold/player_performance.sql`. C'est ce qui donne aux joueurs de Ligue 1 (et
  à tout joueur de Premier League manqué par la correspondance par nom de
  statbunker) un vrai chiffre de `goals` au lieu d'un `NULL` systématique.
  statbunker reste prioritaire quand les deux sources ont une ligne pour le
  même joueur/saison, sa couverture Premier League étant considérée comme la
  source la plus fiable dans ce cas.
- **Les requêtes filtrées par équipe héritent de la limite de correspondance
  par nom ci-dessus.** Filtrer `gold.player_performance` par `team_id` (ex.
  la liste Top Buteurs/Passeurs à l'échelle de l'équipe sur la page détail
  équipe) renvoie les joueurs actuellement dans cet effectif — mais leurs
  `goals`/`assists` peuvent avoir été marqués en partie ou en totalité dans
  un autre club s'ils ont été transférés en cours de saison, puisque la
  correspondance par nom ci-dessus ne redérive jamais `team_id` par
  statistique. Ce n'est pas un nouveau trou de données, juste une
  conséquence de la limite déjà documentée ci-dessus, désormais directement
  visible dans une UI à l'échelle de l'équipe.

---

## gold.team_profile

**Objectif** : Identité de l'équipe (nom, nom abrégé, TLA) et championnat
actuel, pour les cas d'usage de recherche d'équipe dans l'API backend (ex.
`GET /api/teams/{id}`) et tout consommateur ayant besoin d'un nom d'équipe
sans avoir à récupérer le classement propre à une saison.

**Grain** : 1 ligne par `team_id`. Vérifié par les tests `unique`/`not_null`
sur `team_id` dans `transform/models/gold/_gold.yml`.

**Fraîcheur** : `materialized='view'` — simple passe-plat de `silver.teams`,
elle reflète donc toujours la couche silver du dernier `dbt run` sans
nécessiter de reconstruction de table dédiée (même logique que
`gold.player_profile`).

| Colonne | Type | Signification | Nullable ? |
|---|---|---|---|
| `team_id` | int | Identifiant d'équipe, ancré sur football_data_org | Non |
| `team_name` | text | Nom complet de l'équipe | Non |
| `team_short_name` | text | Nom abrégé de l'équipe | Oui |
| `team_tla` | text | Abréviation à trois lettres (ex. `MUN`) | Oui |
| `league` | text | Slug de la compétition dans laquelle l'équipe évolue actuellement | Non |

**Limite connue** : même source que `silver.teams` — une équipe n'apparaît
qu'à partir du moment où elle est présente dans au moins un instantané de
classement football_data_org.

---

## gold.match_results

**Objectif** : Résultats au niveau du match (score, date, statut) avec les
noms des équipes domicile/extérieur dénormalisés, pour les endpoints backend
`GET /api/matches/{id}` et `GET /api/teams/{id}/matches`.

**Grain** : 1 ligne par `source_match_id`. Vérifié par les tests
`unique`/`not_null` sur `source_match_id` dans
`transform/models/gold/_gold.yml`, ainsi que par
`assert_gold_match_results_unique_grain`.

**Fraîcheur** : `materialized='table'` — reflète `silver.matches` à la date
du dernier `dbt build`. Seul football_data_org fournit actuellement des
données au niveau du match.

| Colonne | Type | Signification | Nullable ? |
|---|---|---|---|
| `source_match_id` | int | Identifiant du match provenant de football_data_org | Non |
| `league` | text | Slug de la compétition | Non |
| `season` | text | Saison, format `YYYY-YYYY` | Non |
| `matchday` | int | Numéro de journée | Oui |
| `status` | text | Statut du match tel que rapporté par football_data_org (ex. `FINISHED`, `SCHEDULED`) | Non |
| `utc_date` | timestamp | Heure de coup d'envoi (UTC) | Non |
| `home_team_id` / `away_team_id` | int | Identifiants d'équipe, ancrés sur football_data_org | Non |
| `home_team_name` / `away_team_name` | text | Noms des équipes, joints depuis `silver.teams` | Oui — null si l'id d'équipe ne correspond à aucune ligne de `silver.teams` |
| `home_score` / `away_score` | int | Score final | Oui — null pour les matchs pas encore joués |

**Limite connue** : aucune donnée au niveau des événements de match
(buteurs, cartons, remplacements) n'existe encore nulle part sur cette
plateforme — il n'y a pas de crawler pour cela. `gold.match_results` ne
couvre que les données de score/calendrier au niveau du match, pas les
événements survenant pendant un match.

---

## gold.team_standings_by_matchday

**Objectif** : Statistiques cumulées de classement de chaque équipe (matchs
joués, V/N/D, points, buts) juste après chacun de ses propres matchs
terminés — le bloc de base pour les requêtes « classement à la date X » (ex.
« classement de la Premier League en novembre »), sans dépendre de la
fréquence à laquelle un instantané de classement est pris.

**Grain** : 1 ligne par `(league, season, team_id, source_match_id)`. Vérifié
par `assert_gold_team_standings_by_matchday_unique_grain`.

**Fraîcheur** : `materialized='table'` — recalculée à partir de
`gold.match_results` (`status = 'FINISHED'`) à la date du dernier
`dbt build`. Seul football_data_org fournit actuellement des données au
niveau du match, cette table hérite donc de ce périmètre.

| Colonne | Type | Signification | Nullable ? |
|---|---|---|---|
| `league` | text | Slug de la compétition | Non |
| `season` | text | Saison, format `YYYY-YYYY` | Non |
| `team_id` | int | Identifiant d'équipe, ancré sur football_data_org | Non |
| `source_match_id` | int | Le match auquel correspond cette ligne cumulée — rejoindre `gold.match_results` pour le détail du match | Non |
| `utc_date` | timestamp | Heure de coup d'envoi (UTC) de `source_match_id` — cette ligne est valide à partir de cet instant jusqu'au prochain match terminé de l'équipe | Non |
| `played_games` | int | Numéro de ce match dans l'historique des matchs terminés de l'équipe (1, 2, 3, ...) | Non |
| `won` / `draw` / `lost` | int | Nombre cumulé de victoires/nuls/défaites jusqu'à ce match | Non |
| `points` | int | Points cumulés jusqu'à ce match (3/1/0 par match) | Non |
| `goals_for` / `goals_against` / `goal_difference` | int | Totaux de buts cumulés jusqu'à ce match | Non |

**Limite connue** : Pas de colonne `position`. Classer les équipes entre
elles nécessite de les comparer toutes à la *même* date, or les équipes ne
jouent pas toutes aux mêmes dates — un consommateur calculant le « classement
à la date X » doit donc prendre la dernière ligne de chaque équipe avec
`utc_date <= X` (ex. `DISTINCT ON`) puis les classer ensemble
(`ORDER BY points DESC, goal_difference DESC, goals_for DESC`), plutôt que de
lire une colonne `position` directement dans cette table. Ce classement
calculé à la requête n'utilise que points/différence de buts/buts marqués
comme critères de départage — plus simple que la règle appliquée par
football_data_org pour `gold.league_standings.position` (qui peut inclure les
confrontations directes ou les points de discipline), donc une `position`
calculée ainsi peut occasionnellement différer d'un rang par rapport au
classement officiel en cas d'égalité. `xg`/`xga`/`xpts` ne sont pas
disponibles ici — ces valeurs proviennent de l'instantané périodique propre
d'Understat, pas de données par match (aucun crawler xG au niveau du match
n'existe), donc elles ne peuvent pas être recalculées à une date historique
arbitraire comme le sont V/N/D/points/buts.

---

## gold.standings_history

**Objectif** : Position historique dans le classement pour chaque équipe au
fil du temps, afin de répondre à « où en était l'équipe X au classement à la
mi-novembre » ou toute question de classement à une date passée —
`gold.league_standings` ne reflète toujours que l'instantané actuel/le plus
récent.

**Grain** : 1 ligne par `(league, season, team_id, valid_from)`. Vérifié par
`assert_gold_standings_history_unique_grain`.

**Fraîcheur** : `materialized='table'` — simple passthrough de l'instantané
SCD2 `snapshot_football_data_org__standings` (`transform/snapshots/`),
renommant ses colonnes `dbt_valid_from`/`dbt_valid_to` en
`valid_from`/`valid_to`. Une nouvelle ligne n'apparaît que lorsque
`dbt snapshot` s'exécute et détecte un changement dans l'une de ses colonnes
suivies (`position`, `played_games`, `won`, `draw`, `lost`, `points`,
`goals_for`, `goals_against`, `goal_difference`, `form`) depuis la dernière
exécution — **pas** à chaque `dbt build`. Si `dbt snapshot` est sauté pendant
une période (ex. quelques journées), l'historique de cette période est
définitivement perdu ; impossible de le reconstituer après coup.

| Colonne | Type | Signification | Nullable ? |
|---|---|---|---|
| `league` | text | Slug de la compétition | Non |
| `season` | text | Saison, format `YYYY-YYYY` | Non |
| `team_id` | int | Identifiant d'équipe, ancré sur football_data_org | Non |
| `team_name` | text | Nom complet de l'équipe | Non |
| `team_short_name` | text | Nom abrégé de l'équipe | Oui |
| `team_tla` | text | Abréviation à trois lettres (ex. `MUN`) | Oui |
| `position` | int | Rang au classement pendant la fenêtre de validité de cette ligne | Non |
| `played_games` | int | Matchs joués pendant la fenêtre de validité de cette ligne | Non |
| `won` / `draw` / `lost` | int | Victoires/nuls/défaites pendant la fenêtre de validité de cette ligne | Non |
| `points` | int | Total de points pendant la fenêtre de validité de cette ligne | Non |
| `goals_for` / `goals_against` / `goal_difference` | int | Totaux de buts pendant la fenêtre de validité de cette ligne | Non |
| `form` | text | Chaîne de résultats récents telle que rapportée par football_data_org (ex. `WWDLW`) | Oui |
| `valid_from` | timestamp | Quand les valeurs de cette ligne sont devenues vraies (l'exécution `dbt snapshot` qui les a observées pour la première fois) | Non |
| `valid_to` | timestamp | Quand les valeurs de cette ligne ont cessé d'être vraies (l'exécution `dbt snapshot` suivante ayant observé un changement) | Oui — `NULL` signifie que c'est l'état actuel/le plus récent de l'équipe |

**Comment répondre à « position à la date X »** : filtrer
`valid_from <= X AND (valid_to IS NULL OR valid_to > X)` par équipe, puis la
`position` de cette ligne est directement la réponse — aucun reclassement au
moment de la requête n'est nécessaire (contrairement à
`gold.team_standings_by_matchday`, qui n'a volontairement pas de colonne
`position`). Notez que `valid_from`/`valid_to` sont des horodatages
d'exécution de snapshot, pas des dates de match — une journée jouée un samedi
n'apparaîtra ici qu'au moment où `dbt snapshot` s'est exécuté ensuite et a
remarqué le changement, ce qui peut être le jour même ou plusieurs jours plus
tard selon la cadence de crawl/build.

**Limite connue** : même réserve de fraîcheur que le manque `xg`/`xga`/`xpts`
de `gold.team_standings_by_matchday` — cette table ne porte que les colonnes
propres à football_data_org (aucune métrique de buts attendus Understat),
puisque l'instantané qu'elle enveloppe est celui de `silver.standings`, pas
de `gold.league_standings` enrichi par Understat.

---

## gold.search_aliases

**Objectif** : Table de correspondance surnom/abréviation curatée
manuellement (ex. `mu`, `man c`, `psg`, `mo salah`) utilisée par
l'endpoint backend `GET /api/search`, pour que l'utilisateur n'ait pas
besoin de taper une sous-chaîne exacte du nom officiel de l'équipe/du
joueur.

**Grain** : 1 ligne par paire `(entity_type, alias)` — une équipe ou un
joueur peut avoir plusieurs alias. L'unicité est vérifiée par
`assert_gold_search_aliases_unique_grain` (`transform/tests/`). Le
`not_null` est vérifié sur `entity_type`, `alias` et `entity_id` dans
`transform/seeds/_seeds.yml`, et sur `entity_type`/`entity_id` dans
`transform/models/gold/_gold.yml` (le modèle gold ne re-teste pas `alias`
— c'est un simple passe-plat de la colonne du seed, déjà non-nulle à ce
niveau). Un test `assert_search_aliases_resolve` en sévérité `warn`
(`transform/tests/`) signale tout alias dont l'`entity_id` ne correspond
plus à une équipe/un joueur réel (ex. après une relégation ou un
changement d'id).

**Fraîcheur** : `materialized='table'` — donnée de référence statique,
reconstruite à chaque `dbt build`, comme `gold.league_standings`/
`gold.match_results`.

| Colonne | Type | Signification | Nullable ? |
|---|---|---|---|
| `entity_type` | text | `'team'` ou `'player'` | Non |
| `alias` | text | Surnom/abréviation en minuscules, sans espaces superflus | Non |
| `entity_id` | int | Correspond à `team_id` (si `entity_type = 'team'`) ou `player_id` (si `entity_type = 'player'`) ailleurs dans `gold.*` | Non |

**Limite connue** : la couverture est manuelle et volontairement partielle
— couverture complète pour toutes les équipes, mais seulement un petit
ensemble curaté de surnoms de joueurs bien connus (la plupart des joueurs
restent trouvables via la recherche par sous-chaîne de `/api/search` sans
alias dédié). Voir
`docs/superpowers/specs/2026-08-10-search-alias-fuzzy-match-design.md`.

---

## Hors périmètre

`gold_head_to_head` et les données au niveau des événements de match
(buteurs, cartons, remplacements — un hypothétique
`gold_match_events_enriched`) n'existent pas encore ; il n'y a pas de crawler
pour les événements de match. L'identité des équipes et les résultats au
niveau du match sont désormais couverts par `gold.team_profile` et
`gold.match_results` (voir ci-dessus). Les données au niveau du joueur sont
couvertes de bout en bout par `gold.player_profile` (identité) et
`gold.player_performance` (buts/passes décisives/xG/xA), toutes deux
limitées à la Premier League (voir leurs limites connues ci-dessus).

# Tiếng Việt

Tài liệu này mô tả các bảng trong schema Postgres `gold`: mỗi dòng đại diện
cho cái gì, mỗi cột có ý nghĩa gì, và các consumer downstream (backend API,
frontend, chatbot) có thể dựa vào đâu. Tài liệu được viết để đọc độc lập,
không cần mở model dbt hay file YAML nào.

Các quy tắc chung áp dụng cho mọi bảng bên dưới:
- Mọi bảng gold đều là `materialized='table'` — chứa snapshot dữ liệu tại
  thời điểm `dbt build` / `dbt run` gần nhất, không phải view thời gian
  thực. Dữ liệu crawl mới chỉ xuất hiện ở đây sau khi crawl → ingest →
  `dbt build`.
- Grain (đảm bảo tính duy nhất của mỗi bảng) được kiểm tra bởi một dbt test
  trong `transform/tests/`. Nếu consumer cần "chính xác một dòng cho mỗi X",
  test đó là nguồn xác thực — kiểm tra
  `transform/tests/assert_gold_*_unique_grain.sql` trước khi cho rằng một
  cột mới làm thay đổi grain.
- `team_id` luôn là id số của đội theo football_data_org. Đây là định danh
  ổn định duy nhất cho một đội xuyên suốt các nguồn — không bao giờ join
  các bảng gold theo `team_name` (cách viết khác nhau giữa
  statbunker/understat).

---

## gold.league_standings

**Mục đích**: Bảng xếp hạng (vị trí, điểm số, hiệu số bàn thắng, các chỉ số
kỳ vọng bàn thắng) phục vụ trang frontend "Bảng xếp hạng" (League Table) và
các câu hỏi chatbot liên quan đến xếp hạng ("đội X đang xếp hạng mấy").

**Grain**: 1 dòng cho mỗi `(league, season, team_id)`. Được đảm bảo bởi
`assert_gold_league_standings_unique_grain`.

**Độ mới dữ liệu**: Phản ánh snapshot bảng xếp hạng football_data_org được
ingest gần nhất (chọn theo `ingestion_time`), được bổ sung thêm snapshot
Understat gần nhất cho cùng đội/league/mùa giải. Không phải luồng dữ liệu
thời gian thực — chỉ mới bằng đúng lần crawl + `dbt build` gần nhất.

| Cột | Kiểu | Ý nghĩa | Có thể NULL? |
|---|---|---|---|
| `league` | text | Slug giải đấu, vd. `premier-league`, `ligue-1` | Không |
| `season` | text | Mùa giải, định dạng `YYYY-YYYY` | Không |
| `team_id` | int | Mã đội, neo theo football_data_org | Không |
| `team_name` | text | Tên đầy đủ của đội | Không |
| `team_short_name` | text | Tên viết tắt của đội | Không |
| `team_tla` | text | Viết tắt ba chữ cái (vd. `MUN`) | Không |
| `position` | int | Thứ hạng trong bảng xếp hạng | Không |
| `played_games` | int | Số trận đã đấu trong mùa | Không |
| `won` / `draw` / `lost` | int | Số trận thắng/hòa/thua trong mùa | Không |
| `points` | int | Tổng điểm trong mùa | Không |
| `goals_for` / `goals_against` / `goal_difference` | int | Tổng số bàn thắng/thua/hiệu số trong mùa | Không |
| `form` | text | Chuỗi kết quả gần đây theo football_data_org (vd. `WWDLW`) | Có — null nếu đội chưa thi đấu trận nào trong mùa này |
| `xg` | numeric | Bàn thắng kỳ vọng (Expected Goals, Understat) | **Có** — null nếu đội này không khớp được với dòng dữ liệu Understat (xem bên dưới) |
| `xga` | numeric | Bàn thua kỳ vọng (Understat) | **Có** — cùng điều kiện với `xg` |
| `xpts` | numeric | Điểm số kỳ vọng (Understat) | **Có** — cùng điều kiện với `xg` |

**Hạn chế đã biết**: `xg`/`xga`/`xpts` đến từ một `left join` với dữ liệu
Understat. Understat chỉ định danh đội theo tên, nên việc khớp phụ thuộc vào
việc `transform/seeds/team_name_map.csv` có dòng ứng với cách viết tên của
đội đó trên Understat. Một đội mới hoặc đổi tên mà chưa được thêm vào seed
sẽ hiển thị `xg`/`xga`/`xpts` là `NULL`, đây không phải lỗi — consumer cần
hiểu đây là "chưa có dữ liệu bàn thắng kỳ vọng cho đội này", không phải dữ
liệu bị thiếu/hỏng.

---

## gold.team_form_last_5_matches

**Mục đích**: Chuỗi kết quả gần nhất của mỗi đội, phục vụ widget "phong độ
gần đây" và các câu hỏi chatbot kiểu "đội X gần đây thi đấu thế nào".

**Grain**: 1 dòng cho mỗi `(league, season, team_id)`. Được đảm bảo bởi
`assert_gold_team_form_unique_grain`.

**Độ mới dữ liệu**: Tính từ `silver.matches` lọc theo `status = 'FINISHED'`,
lấy 5 trận gần nhất của mỗi đội theo `utc_date` tại thời điểm `dbt build`
gần nhất. Hiện chỉ football_data_org cung cấp dữ liệu ở mức trận đấu.

| Cột | Kiểu | Ý nghĩa | Có thể NULL? |
|---|---|---|---|
| `league` | text | Slug giải đấu | Không |
| `season` | text | Mùa giải, định dạng `YYYY-YYYY` | Không |
| `team_id` | int | Mã đội, neo theo football_data_org | Không |
| `team_name` | text | Tên đầy đủ của đội | Không |
| `matches_played` | int | Số trận đã kết thúc được tính, tối đa 5 | Không — **nhưng có thể là 1–4** nếu đội chưa đá đủ 5 trận đã kết thúc trong mùa này. Không nên mặc định luôn là 5 |
| `wins` / `draws` / `losses` | int | Số trận thắng/hòa/thua trong các trận được tính | Không |
| `points` | int | Số điểm đạt được trong các trận được tính (3/1/0 mỗi trận) | Không |
| `goals_for` / `goals_against` | int | Số bàn ghi được/để thủng trong các trận được tính | Không |
| `form` | text | Chuỗi kết quả sắp xếp từ cũ nhất → mới nhất (vd. `LDWWW`) | Không |

**Hạn chế đã biết**: Vì `matches_played` có thể nhỏ hơn 5 vào đầu mùa giải,
mọi logic UI/chatbot giả định cửa sổ cố định 5 trận phải đọc
`matches_played` trước, thay vì hardcode "5 trận gần nhất".

---

## gold.player_profile

**Mục đích**: Thông tin định danh cầu thủ và một đội "của mùa gần nhất" để
tiện tham khảo, phục vụ trang frontend `/api/players/{id}` và tra cứu cầu
thủ qua chatbot.

**Grain**: 1 dòng cho mỗi `player_id`. Được đảm bảo bởi test
`unique`/`not_null` trên `player_id` trong `transform/models/gold/_gold.yml`
(không cần file `assert_*_unique_grain.sql` riêng — chỉ `player_id` đã là
grain, giống `team_id` của `silver.teams`).

**Độ mới dữ liệu**: Khác với mọi bảng gold khác, bảng này là
`materialized='view'`, không phải `'table'` — `age` được tính trực tiếp tại
thời điểm truy vấn từ `date_of_birth`, nên luôn chính xác mà không cần
`dbt build` để làm mới. `team_id` lấy từ dòng gần nhất của cầu thủ trong
`silver.player_team_season` (`max(season)`), không lấy trực tiếp từ
football_data_org.

| Cột | Kiểu | Ý nghĩa | Có thể NULL? |
|---|---|---|---|
| `player_id` | int | Hoặc là id số riêng của football_data_org, hoặc là id gốc của understat cộng offset cố định `100000000` cho các cầu thủ không có dòng nào ở football_data_org | Không |
| `player_name` | text | Tên đầy đủ của cầu thủ | Không |
| `position` | text | Vị trí thi đấu — một trong 4 giá trị `Goalkeeper`, `Defence`, `Midfield`, `Offence`. Lấy từ football_data_org khi có dòng ở đó; backfill từ tag vị trí riêng của Understat (qua `normalize_understat_position()`) cho các cầu thủ neo theo understat | Có — chỉ `NULL` với cầu thủ neo theo understat có tag Understat gốc chỉ là `S` (chỉ là cầu thủ dự bị, không ghi nhận vị trí chính) |
| `nationality` | text | Tên quốc gia theo football_data_org (một nguồn duy nhất, chưa chuẩn hóa) | Có — `NULL` với cầu thủ neo theo understat, trừ khi được backfill qua seed `player_extra_info.csv` (football_data_org vốn là nguồn duy nhất có trường này) |
| `date_of_birth` | date | Ngày sinh | Có — `NULL` với cầu thủ neo theo understat, trừ khi được backfill qua seed `player_extra_info.csv` (football_data_org vốn là nguồn duy nhất có trường này) |
| `age` | int | Tính tại thời điểm truy vấn từ `date_of_birth` | Có — null nếu `date_of_birth` là null |
| `shirt_number` | int | Số áo | Có — `NULL` với cầu thủ neo theo understat, trừ khi được backfill qua seed `player_extra_info.csv` (football_data_org vốn là nguồn duy nhất có trường này) |
| `team_id` | int | Đội mà cầu thủ được resolve cho mùa gần nhất trong `silver.player_team_season` — **không nhất thiết** là đội hình hiện tại theo football_data_org (xem `gold.player_performance` để có nguồn xác thực theo từng mùa) | Có — null nếu cầu thủ không có dòng `player_team_season` nào |
| `team_name` | text | Tên đầy đủ của đội, lấy từ `silver.teams` | Có — cùng điều kiện với `team_id` |
| `parent_team_id` | int | `team_id` đội hình đăng ký/hiện tại của cầu thủ theo football_data_org, không phụ thuộc vào việc cầu thủ đang thực sự thi đấu cho câu lạc bộ nào mùa này (xem `silver.player_team_season.parent_team_id`) | Có — `NULL` khi football_data_org không có dòng đội hình nào cho cầu thủ này (cầu thủ neo theo understat, hoặc bất kỳ cầu thủ Ligue 1 nào — crawl đội hình của football_data_org chỉ giới hạn Premier League) |
| `parent_team_name` | text | Tên đầy đủ của đội ứng với `parent_team_id`, lấy từ `silver.teams` | Có — cùng điều kiện với `parent_team_id` |
| `is_on_loan` | boolean | `true` khi `team_id` và `parent_team_id` đều khác null và khác nhau, **và** mùa gần nhất của cầu thủ vẫn còn ít nhất một trận chưa `FINISHED`/`AWARDED` trong `gold.match_results` — câu lạc bộ thi đấu thực tế của cầu thủ không khớp với đăng ký football_data_org trong khi mùa giải đó vẫn đang diễn ra | Không — `false` (không phải `NULL`) khi `parent_team_id` là `NULL` hoặc mùa giải đã kết thúc, vì không có gì đáng tin cậy để so sánh |
| `league` | text | Slug giải đấu | Không |

**Hạn chế đã biết**:

- **`team_id` ở đây chỉ là tiện ích hiển thị, không phải một sự kiện gắn với
  mùa giải cụ thể.** Với câu hỏi "ai thi đấu cho đội X ở mùa Y", luôn dùng
  `gold.player_performance` (hoặc `GET /teams/{id}/squad?season=Y`), không
  bao giờ dùng cột này — đây chính xác là lỗi mà thiết kế này sửa (trước đây
  `team_id` lấy thẳng từ "đội hình hiện tại" không gắn ngày của
  football_data_org, khiến cầu thủ đang cho mượn hiển thị ở CLB chủ quản, và
  hoàn toàn không có dòng nào cho các cầu thủ mà crawl đội hình của
  football_data_org không bao phủ).
- **Cầu thủ neo theo understat (không có dòng football_data_org) có
  `date_of_birth`/`nationality`/`shirt_number` là `NULL` trừ khi được
  backfill.** Ba trường này vốn chỉ được điền từ football_data_org — một
  seed thủ công, `transform/seeds/player_extra_info.csv`, backfill các
  khoảng trống đã biết (khóa theo cùng `player_id` đã tính; xem
  `docs/superpowers/specs/2026-08-03-player-extra-info-seed-design.md`).
  `position` được xử lý khác: nó được backfill từ tag vị trí riêng của
  Understat cho mọi cầu thủ neo theo understat, không chỉ những cầu thủ có
  trong seed (xem
  `docs/superpowers/specs/2026-08-03-squad-display-fixes-design.md`), nên
  chỉ `NULL` khi tag gốc của Understat chỉ là `S`.
- **Chỉ có Premier League.** Crawl đội hình của football_data_org chỉ bao
  phủ Premier League (xem `crawlers/football_data_org/client.py`); understat
  cũng bao phủ Ligue 1, nhưng các cầu thủ Ligue 1 không có dòng
  football_data_org vẫn xuất hiện ở đây (understat neo họ độc lập với giải
  đấu) — phạm vi Ligue 1 của bảng này không phải quyết định phạm vi có chủ
  đích như với cột statbunker của `player_performance`.
- **Bộ 4 giá trị `position` ở trên bị hardcode ở nơi khác.** Câu truy vấn sắp
  xếp đội hình trong `backend/routers/teams.py`
  (`ORDER BY CASE pp.position WHEN 'Goalkeeper' THEN 1 ...`) và hằng số
  `POSITION_GROUPS` trong `frontend/components/SquadTable.tsx` đều phụ thuộc
  chính xác vào 4 giá trị này — nếu domain này thay đổi trong tương lai (vd.
  football_data_org trả về thêm giá trị vị trí mới), cần cập nhật cả hai nơi.
- **`is_on_loan`/`parent_team_id` chỉ phát hiện được các trường hợp cho mượn
  trong phạm vi crawl.** Một cầu thủ cho mượn tới CLB ngoài phạm vi crawl
  (vd. Championship) sẽ không có dòng Understat/StatBunker nào, nên `team_id`
  rơi về đúng giá trị của `parent_team_id` — không có sai khác, `is_on_loan`
  vẫn là `false`. Cùng nguyên nhân gốc với khoảng trống
  `resolved_via = 'fdo_fallback'` được ghi ở `gold.player_performance` bên
  dưới. Xem
  docs/superpowers/specs/2026-08-03-parent-club-loan-display-design.md.
- **`is_on_loan` bị tắt khi một mùa giải đã kết thúc hoàn toàn.**
  `parent_team_id` lấy từ "đội hình hiện tại" không gắn ngày của
  football_data_org, không phải một sự kiện gắn mùa giải (xem comment
  LIMITATION ở CTE `fdo_fallback` của `player_team_season.sql`). Đây không
  chỉ là rủi ro lý thuyết: nó đã xảy ra thật với chỉ một mùa dữ liệu — crawl
  đội hình football_data_org (2026-07-28) được thực hiện *sau khi* mùa
  2025-2026 kết thúc (trận cuối 2026-05-24), trong kỳ chuyển nhượng hè năm
  đó, nên `parent_team_id` đã phản ánh vài vụ chuyển nhượng vĩnh viễn đã hoàn
  tất (vd. Tielemans sang Manchester United, Morgan Rogers sang Chelsea,
  Marcos Senesi sang Tottenham) trong khi `team_id` vẫn phản ánh thống kê của
  mùa đã kết thúc — báo sai các vụ chuyển nhượng đã xong thành đang cho mượn.
  Đã sửa bằng cách yêu cầu mùa giải vẫn còn trận chưa kết thúc trong
  `gold.match_results` (xem CTE `season_in_progress` của `player_profile.sql`);
  khi một mùa kết thúc, `is_on_loan` chuyển thành `false` cho tất cả cầu thủ
  trong mùa đó — kể cả những cầu thủ thực sự vẫn đang được cho mượn (vd.
  Grealish) — cho tới khi có một lần crawl đội hình mới trong mùa tiếp theo.
  Một vụ chuyển nhượng vĩnh viễn diễn ra *giữa* mùa giải (vd. kỳ chuyển
  nhượng tháng 1, khi mùa giải vẫn "đang diễn ra" theo test này) không được
  fix này bao phủ và vẫn không thể phân biệt được với một vụ cho mượn thật —
  không có trường prêt/status thật nào tồn tại ở bất kỳ đâu trong dữ liệu
  bronze.

---

## gold.player_performance

**Mục đích**: Thống kê cầu thủ — bàn thắng, kiến tạo, số phút thi đấu,
xG/xA — kèm đội mà thống kê đó được gán cho, theo từng mùa giải, phục vụ
trang frontend `/api/players/{id}/performance` và các câu hỏi chatbot như
"cầu thủ X đã ghi bao nhiêu bàn" hoặc "xG của cầu thủ X là bao nhiêu".

**Grain**: 1 dòng cho mỗi `(player_id, season)` — thay đổi so với chỉ
`player_id`, để đội của một cầu thủ có thể khác nhau đúng giữa các mùa giải,
hoặc (trong cùng một mùa) là CLB đang cho mượn thay vì đội hình CLB chủ quản
theo football_data_org. Được đảm bảo bởi một test grain riêng,
`transform/tests/assert_gold_player_performance_unique_grain.sql` (vì grain
giờ là composite — test `unique` cũ trên một cột `player_id` không còn áp
dụng được).

**Độ mới dữ liệu**: `materialized='table'` — phản ánh các lần crawl
statbunker và understat gần nhất tính đến `dbt build` gần nhất. Thứ tự ưu
tiên khi resolve đội theo từng `(player_id, season)`: đội theo understat
(mới nhất, gán đúng cầu thủ cho mượn về CLB đang mượn) → đội theo statbunker
→ đội hiện tại theo football_data_org như phương án cuối cùng cho các cầu
thủ không có dòng thống kê nào với đội resolve được ở mùa đó.

| Cột | Kiểu | Ý nghĩa | Có thể NULL? |
|---|---|---|---|
| `player_id` | int | Hoặc là id số riêng của football_data_org, hoặc là id gốc của understat cộng offset cố định `100000000` | Không |
| `player_name` | text | Tên đầy đủ của cầu thủ | Không |
| `season` | text | Định dạng `YYYY-YYYY` | Không |
| `team_id` | int | Đội mà cầu thủ được gán **cho mùa cụ thể này** — xem `silver.player_team_season` để biết logic resolve | Không — CTE `team_candidates` của `player_team_season` chỉ nhận các dòng có `team_id` khác null; một cặp cầu thủ+mùa không resolve được đội sẽ bị bỏ hoàn toàn khỏi bảng thay vì xuất hiện với `team_id = NULL` (xem hạn chế). Trên thực tế trường hợp này giờ hiếm gặp: cơ chế "CLB cuối cùng thắng" trên `team_title` nối bằng dấu phẩy (xem Độ mới dữ liệu ở trên) đã giải quyết trường hợp chuyển nhượng giữa mùa vốn từng phổ biến |
| `team_name` | text | Tên đầy đủ của đội, lấy từ `silver.teams` | Có — cùng điều kiện với `team_id` |
| `parent_team_id` | int | `team_id` đội hình đăng ký/hiện tại của cầu thủ theo football_data_org (xem `silver.player_team_season.parent_team_id`) | Có — cùng điều kiện với `gold.player_profile.parent_team_id` |
| `parent_team_name` | text | Tên đầy đủ của đội ứng với `parent_team_id`, lấy từ `silver.teams` | Có — cùng điều kiện với `parent_team_id` |
| `is_on_loan` | boolean | `true` khi `team_id` và `parent_team_id` đều khác null và khác nhau cho mùa cụ thể này, **và** mùa đó vẫn còn ít nhất một trận chưa `FINISHED`/`AWARDED` trong `gold.match_results` | Không — `false` khi `parent_team_id` là `NULL` hoặc mùa giải đã kết thúc |
| `league` | text | Slug giải đấu | Không |
| `resolved_via` | text | Nguồn nào đã resolve `team_id` cho cầu thủ+mùa này: `understat`, `statbunker`, hoặc `fdo_fallback` | Không |
| `goals` | int | Số bàn thắng trong mùa — lấy từ statbunker, dự phòng bằng số bàn thắng riêng của understat khi statbunker không có dòng nào cho cầu thủ/mùa này | **Có** — null chỉ khi cả hai nguồn đều không có dòng nào cho cầu thủ/mùa này |
| `assists` | int | Số kiến tạo trong mùa (understat) | **Có** — cùng điều kiện với `xg` |
| `apps` | int | Số trận ra sân (understat) | **Có** — cùng điều kiện với `xg` |
| `minutes` | int | Số phút thi đấu (understat) | **Có** — cùng điều kiện với `xg` |
| `xg` | numeric | Bàn thắng kỳ vọng (understat) | **Có** — null nếu cầu thủ này không có dòng understat cho mùa này |
| `xa` | numeric | Kiến tạo kỳ vọng (understat) | **Có** — cùng điều kiện với `xg` |
| `xg90` | numeric | Bàn thắng kỳ vọng mỗi 90 phút (understat), tính bằng `xg / (minutes / 90)` vì endpoint dữ liệu của Understat không trả trực tiếp giá trị này | **Có** — cùng điều kiện với `xg`, cũng null nếu `minutes` bằng 0 |
| `xa90` | numeric | Kiến tạo kỳ vọng mỗi 90 phút (understat), tính theo cách tương tự | **Có** — cùng điều kiện với `xg90` |

**Hạn chế đã biết**:

- **`GET /teams/{id}/squad` lọc bỏ các dòng `resolved_via = 'fdo_fallback'`.**
  Đây là đánh đổi có chủ đích, không phải bug: một cầu thủ không có dòng
  thống kê understat/statbunker nào cho mùa này thì không thể phân biệt được,
  với dữ liệu mà nền tảng này crawl, giữa "cầu thủ dự bị thực sự không ra
  sân" và "đang cho mượn tới CLB ngoài phạm vi crawl" (vd. Championship) —
  không có trường prêt/status nào tồn tại trong dữ liệu bronze thô. Ẩn cả hai
  trường hợp cùng nhau được chấp nhận như cái giá để ẩn trường hợp thứ hai.
  Bộ lọc này chỉ áp dụng cho danh sách đội hình:
  `gold.player_profile.team_id` (trang hồ sơ riêng của cầu thủ) không bị ảnh
  hưởng và vẫn hiển thị CLB chủ quản cho cầu thủ đang cho mượn, vốn vẫn là
  thông tin "CLB đăng ký" chính xác. Xem
  docs/superpowers/specs/2026-08-03-squad-display-fixes-design.md.
- **`is_on_loan` có cùng khoảng trống phát hiện như bộ lọc `fdo_fallback` ở
  trên** — một vụ cho mượn ngoài phạm vi crawl không thể phân biệt được với
  "vẫn ở CLB đăng ký" bằng dữ liệu mà nền tảng này crawl. Xem
  docs/superpowers/specs/2026-08-03-parent-club-loan-display-design.md.
- **`is_on_loan` bị tắt khi một mùa giải đã kết thúc hoàn toàn.** Cùng fix và
  cùng sự cố thực tế như đã ghi ở `gold.player_profile` bên trên
  (Tielemans/Morgan Rogers/Senesi bị báo sai thành đang cho mượn sau khi
  thống kê mùa 2025-2026 của họ được so sánh với một lần crawl đội hình lấy
  trong kỳ chuyển nhượng hè năm sau) — `is_on_loan` giờ yêu cầu thêm rằng
  `season` của chính dòng đó vẫn còn trận chưa kết thúc trong
  `gold.match_results`. Một vụ chuyển nhượng vĩnh viễn diễn ra *giữa* mùa
  giải (mùa vẫn "đang diễn ra" theo test này) không được fix này bao phủ và
  vẫn không thể phân biệt được với một vụ cho mượn thật.
- **Việc khớp tên chỉ dựa trên tên đã chuẩn hóa, không kèm đội.** statbunker
  và understat định danh cầu thủ bằng tên (không có id số dùng chung với
  football_data_org). Việc khớp sẽ chuẩn hóa chữ hoa/thường, dấu, dấu câu
  (`normalize_player_name`, cần extension `unaccent` của Postgres —
  `infra/postgres/migrations/004_enable_unaccent_extension.sql`) và kiểm tra
  `transform/seeds/player_name_map.csv` trước để xử lý ngoại lệ. Một phiên
  bản trước đây của join này còn yêu cầu `team_id` khớp với đội hình *hiện
  tại* trong `silver.players`, nhưng kiểm thử thực tế cho thấy điều đó làm
  mất ~20-30% các match vốn đúng đối với cầu thủ chuyển nhượng giữa mùa
  (`silver.players` phản ánh lần crawl gần nhất, trong khi statbunker/understat
  gán mỗi dòng theo câu lạc bộ mà cầu thủ ghi bàn/thi đấu tại thời điểm
  scrape). Yêu cầu `team_id` đã được bỏ khỏi việc khớp tự động; `silver.players`
  hiện chưa có trường hợp trùng tên đã chuẩn hóa nào, nên rủi ro khớp sai mà
  điều này chấp nhận (hai cầu thủ Premier League nào đó trùng tên đầy đủ đã
  chuẩn hóa) đang được theo dõi, chứ chưa được loại bỏ hoàn toàn.
- **Khoảng trống khớp còn lại phổ biến nhất là tên pháp lý đầy đủ so với tên
  thường gọi, biệt danh (vd. `"Josh Laurent"` so với `"Joshua Laurent"`,
  `"Joe Gomez"` so với `"Joseph Gomez"`), hoặc một biến thể phiên âm/chính tả
  giữa hai nguồn** (vd. `"Christian Romero"` so với `"Cristian Romero"`,
  `"Mickey van de Ven"` so với `"Micky van de Ven"`) — `normalize_player_name`
  chỉ sửa khác biệt về chữ hoa/thường/dấu/dấu câu, không xử lý các khoảng
  trống này. Nếu không được xử lý, dòng understat khớp thất bại sẽ tự sinh ra
  một `player_id` neo theo understat riêng thay vì gộp vào cầu thủ
  football_data_org đã có sẵn — cầu thủ đó sẽ xuất hiện **hai lần** trong
  `gold.player_profile` dưới hai cách viết tên khác nhau. Trường hợp này hiển
  thị là stats `NULL` cho dòng neo theo football_data_org (không phải lỗi) và
  một dòng mức `warn` trong `assert_player_names_mapped`, được xử lý bằng
  cách thêm một dòng vào `player_name_map.csv`. Khác với `team_name_map.csv`
  (danh sách thủ công đầy đủ cho ~20 đội ổn định), `player_name_map.csv`
  được thiết kế mang tính phản ứng và không đầy đủ — ~600 cầu thủ từ hai
  nguồn thay đổi mỗi kỳ chuyển nhượng, nên được cập nhật khi phát hiện thiếu
  sót, không làm trước. Trước khi thêm một dòng cho cặp tên giống nhau trong
  cùng một đội, cần xác minh đó thực sự là cùng một người (so sánh vị trí thi
  đấu và số phút ra sân) — một số cặp tên gần giống nhau trong cùng đội hình
  thực chất là hai cầu thủ khác nhau (vd. `"Ali Youssef"` / `"Ali Youssif"`
  của Metz, `"Sadibou Sané"` / `"Ibou Sané"` của Nantes).
- **API JSON của Understat trả về tên cầu thủ dưới dạng đã escape HTML
  entity** (vd. `"Jun&#039;ai Byfield"` thay vì `"Jun'ai Byfield"`).
  `normalize_player_name` giải mã chuỗi này trước khi khớp, và
  `silver.players` giải mã lại một lần nữa trước khi gán vào `player_name`
  cho các cầu thủ neo theo understat, nên lỗi này không bao giờ lọt tới
  `gold.player_profile` — nhưng nếu một lần crawl understat mới phát sinh
  một loại entity escape khác (hiện mới chỉ ghi nhận `&#039;`), nó sẽ lọt
  qua cho tới khi được thêm vào bước giải mã đó.
  sót, không làm trước.
- **Chuyển nhượng giữa mùa trên Understat**: `team_title` là danh sách các
  CLB của cầu thủ trong mùa đó nối bằng dấu phẩy (vd. `"Angers,Rennes"`). Lần
  sửa đầu tiên giả định "đội cuối cùng trong danh sách = đội hiện tại",
  nhưng xác minh thủ công cả 24 trường hợp cho thấy giả định này chỉ đúng
  khoảng một nửa — và hai cầu thủ khác nhau, `"Abakar Sylla"` và
  `"Junior Mwanga"`, có cùng một chuỗi **y hệt** `"Nantes,Strasbourg"` nhưng
  đáp án đúng lại ngược nhau, chứng minh không thể suy ra đội hiện tại chỉ từ
  chuỗi văn bản, mà phải xét theo từng cầu thủ cụ thể.
  `stg_understat__player_stats` giờ tra `understat_id` trong
  `seeds/understat_transfer_team_override.csv` (đã xác minh thủ công, đủ 24
  trường hợp đã biết); chỉ trường hợp chưa có dòng override mới rơi về đoán
  "đội cuối cùng trong danh sách" — nên coi đó là một phỏng đoán chưa kiểm
  chứng, không phải sự thật, cho tới khi được xác minh và thêm vào seed —
  cùng cách làm phản ứng như `player_name_map.csv`.
- **statbunker chỉ bao phủ Premier League, nên `goals` dự phòng bằng số bàn
  thắng riêng của understat mỗi khi statbunker không có dòng nào cho cầu
  thủ/mùa đó** — `coalesce(statbunker_goals, understat_goals)` trong
  `gold/player_performance.sql`. Đây là điều giúp cầu thủ Ligue 1 (và bất kỳ
  cầu thủ Premier League nào bị bỏ sót do khớp tên của statbunker) có được số
  bàn thắng thật thay vì luôn là `NULL`. statbunker vẫn được ưu tiên khi cả
  hai nguồn đều có dòng cho cùng cầu thủ/mùa, vì phạm vi Premier League của
  nó được xem là nguồn đáng tin cậy hơn trong trường hợp đó.
- **Truy vấn lọc theo đội thừa hưởng hạn chế khớp theo tên ở trên.** Lọc
  `gold.player_performance` theo `team_id` (vd. danh sách Top ghi bàn/kiến
  tạo theo đội trên trang chi tiết đội) trả về các cầu thủ hiện đang thuộc
  đội hình đó — nhưng `goals`/`assists` của họ có thể đã được ghi nhận một
  phần hoặc toàn bộ ở một câu lạc bộ khác nếu họ chuyển nhượng giữa mùa, vì
  việc khớp theo tên ở trên không bao giờ tính lại `team_id` cho từng chỉ
  số. Đây không phải lỗ hổng dữ liệu mới, chỉ là hệ quả của hạn chế đã nêu ở
  trên, nay hiển thị rõ ràng hơn do có UI theo đội sử dụng dữ liệu này.

---

## gold.team_profile

**Mục đích**: Thông tin định danh đội (tên, tên viết tắt, TLA) và giải đấu
hiện tại, phục vụ các use case tra cứu đội trong API backend (vd.
`GET /api/teams/{id}`) và bất kỳ consumer nào cần tên đội mà không cần lấy
dữ liệu bảng xếp hạng theo mùa.

**Grain**: 1 dòng cho mỗi `team_id`. Được đảm bảo bởi test `unique`/`not_null`
trên `team_id` trong `transform/models/gold/_gold.yml`.

**Độ mới dữ liệu**: `materialized='view'` — chỉ truyền dữ liệu trực tiếp từ
`silver.teams`, nên luôn phản ánh tầng silver của lần `dbt run` gần nhất mà
không cần rebuild table riêng (cùng lý do như `gold.player_profile`).

| Cột | Kiểu | Ý nghĩa | Có thể NULL? |
|---|---|---|---|
| `team_id` | int | Mã đội, neo theo football_data_org | Không |
| `team_name` | text | Tên đầy đủ của đội | Không |
| `team_short_name` | text | Tên viết tắt của đội | Có |
| `team_tla` | text | Viết tắt ba chữ cái (vd. `MUN`) | Có |
| `league` | text | Slug giải đấu mà đội đang thi đấu hiện tại | Không |

**Hạn chế đã biết**: cùng nguồn với `silver.teams` — một đội chỉ xuất hiện
khi đã có mặt trong ít nhất một snapshot bảng xếp hạng của football_data_org.

---

## gold.match_results

**Mục đích**: Kết quả ở mức trận đấu (tỷ số, ngày, trạng thái) kèm tên đội
nhà/khách đã denormalize sẵn, phục vụ endpoint backend `GET /api/matches/{id}`
và `GET /api/teams/{id}/matches`.

**Grain**: 1 dòng cho mỗi `source_match_id`. Được đảm bảo bởi test
`unique`/`not_null` trên `source_match_id` trong
`transform/models/gold/_gold.yml`, cùng với
`assert_gold_match_results_unique_grain`.

**Độ mới dữ liệu**: `materialized='table'` — phản ánh `silver.matches` tính
đến `dbt build` gần nhất. Hiện chỉ football_data_org cung cấp dữ liệu ở mức
trận đấu.

| Cột | Kiểu | Ý nghĩa | Có thể NULL? |
|---|---|---|---|
| `source_match_id` | int | Mã trận đấu từ football_data_org | Không |
| `league` | text | Slug giải đấu | Không |
| `season` | text | Mùa giải, định dạng `YYYY-YYYY` | Không |
| `matchday` | int | Số vòng đấu | Có |
| `status` | text | Trạng thái trận đấu theo football_data_org (vd. `FINISHED`, `SCHEDULED`) | Không |
| `utc_date` | timestamp | Giờ bắt đầu trận đấu (UTC) | Không |
| `home_team_id` / `away_team_id` | int | Mã đội, neo theo football_data_org | Không |
| `home_team_name` / `away_team_name` | text | Tên đội, join từ `silver.teams` | Có — null nếu team id không khớp dòng nào trong `silver.teams` |
| `home_score` / `away_score` | int | Tỷ số chung cuộc | Có — null với các trận chưa diễn ra |

**Hạn chế đã biết**: chưa có dữ liệu ở mức sự kiện trận đấu (người ghi bàn,
thẻ phạt, thay người) ở bất kỳ đâu trong nền tảng này — chưa có crawler cho
việc này. `gold.match_results` chỉ bao phủ dữ liệu tỷ số/lịch thi đấu ở mức
trận đấu, không phải các sự kiện diễn ra trong trận.

---

## gold.team_standings_by_matchday

**Mục đích**: Số liệu bảng xếp hạng cộng dồn của mỗi đội (số trận đã đấu,
thắng/hòa/thua, điểm số, bàn thắng) ngay sau mỗi trận đã kết thúc của đội đó
— khối xây dựng cơ bản cho các truy vấn "bảng xếp hạng tại thời điểm X" (vd.
"bảng xếp hạng Ngoại hạng Anh vào tháng 11"), không phụ thuộc vào tần suất
chụp snapshot bảng xếp hạng.

**Grain**: 1 dòng cho mỗi `(league, season, team_id, source_match_id)`. Được
đảm bảo bởi `assert_gold_team_standings_by_matchday_unique_grain`.

**Độ mới dữ liệu**: `materialized='table'` — tính lại từ `gold.match_results`
(`status = 'FINISHED'`) tại thời điểm `dbt build` gần nhất. Hiện chỉ
football_data_org cung cấp dữ liệu ở mức trận đấu, nên bảng này kế thừa phạm
vi đó.

| Cột | Kiểu | Ý nghĩa | Có thể NULL? |
|---|---|---|---|
| `league` | text | Slug giải đấu | Không |
| `season` | text | Mùa giải, định dạng `YYYY-YYYY` | Không |
| `team_id` | int | Mã đội, neo theo football_data_org | Không |
| `source_match_id` | int | Trận đấu mà dòng cộng dồn này phản ánh — join ngược lại `gold.match_results` để lấy chi tiết trận đấu | Không |
| `utc_date` | timestamp | Giờ bắt đầu (UTC) của `source_match_id` — dòng này có hiệu lực từ thời điểm này cho tới trận kết thúc tiếp theo của đội | Không |
| `played_games` | int | Số thứ tự của trận này trong lịch sử các trận đã kết thúc của đội (1, 2, 3, ...) | Không |
| `won` / `draw` / `lost` | int | Số trận thắng/hòa/thua cộng dồn tính đến trận này | Không |
| `points` | int | Điểm số cộng dồn tính đến trận này (3/1/0 mỗi trận) | Không |
| `goals_for` / `goals_against` / `goal_difference` | int | Tổng số bàn thắng/thua/hiệu số cộng dồn tính đến trận này | Không |

**Hạn chế đã biết**: Không có cột `position`. Xếp hạng các đội với nhau cần
so sánh tất cả các đội tại *cùng* một thời điểm, trong khi các đội không thi
đấu cùng ngày — nên consumer muốn tính "bảng xếp hạng tại thời điểm X" phải
lấy dòng mới nhất của mỗi đội có `utc_date <= X` (vd. dùng `DISTINCT ON`) rồi
xếp hạng chung (`ORDER BY points DESC, goal_difference DESC, goals_for DESC`),
thay vì đọc trực tiếp cột `position` từ bảng này. Cách xếp hạng tại thời điểm
truy vấn này chỉ dùng điểm/hiệu số/bàn thắng làm tiêu chí phụ — đơn giản hơn
luật mà football_data_org áp dụng cho `gold.league_standings.position` (có
thể bao gồm đối đầu trực tiếp hoặc điểm kỷ luật), nên `position` tính theo
cách này đôi khi có thể lệch một bậc so với bảng xếp hạng chính thức khi có
đội bằng điểm/hiệu số/bàn thắng. `xg`/`xga`/`xpts` không có ở đây — các giá
trị này đến từ snapshot định kỳ riêng của Understat, không phải dữ liệu theo
từng trận (chưa có crawler xG ở mức trận đấu), nên không thể tính lại tại một
thời điểm lịch sử bất kỳ như W/D/L/điểm/bàn thắng.

---

## gold.standings_history

**Mục đích**: Vị trí lịch sử trên bảng xếp hạng của từng đội theo thời gian,
để trả lời câu hỏi kiểu "đội X đứng thứ mấy vào giữa tháng 11" hay bất kỳ câu
hỏi bảng xếp hạng tại một thời điểm trong quá khứ — `gold.league_standings`
chỉ luôn phản ánh snapshot hiện tại/mới nhất.

**Grain**: 1 dòng cho mỗi `(league, season, team_id, valid_from)`. Được đảm
bảo bởi `assert_gold_standings_history_unique_grain`.

**Độ mới dữ liệu**: `materialized='table'` — passthrough đơn giản của snapshot
SCD2 `snapshot_football_data_org__standings` (`transform/snapshots/`), đổi
tên cột `dbt_valid_from`/`dbt_valid_to` thành `valid_from`/`valid_to`. Chỉ có
dòng mới khi `dbt snapshot` chạy và phát hiện thay đổi ở 1 trong các cột được
theo dõi (`position`, `played_games`, `won`, `draw`, `lost`, `points`,
`goals_for`, `goals_against`, `goal_difference`, `form`) so với lần chạy
trước — **không phải** mỗi lần `dbt build`. Nếu `dbt snapshot` bị bỏ chạy
trong 1 khoảng thời gian (vd. vài vòng đấu), lịch sử của khoảng đó mất vĩnh
viễn, không có cách nào khôi phục lại sau đó.

| Cột | Kiểu | Ý nghĩa | Có thể NULL? |
|---|---|---|---|
| `league` | text | Slug giải đấu | Không |
| `season` | text | Mùa giải, định dạng `YYYY-YYYY` | Không |
| `team_id` | int | Mã đội, neo theo football_data_org | Không |
| `team_name` | text | Tên đầy đủ của đội | Không |
| `team_short_name` | text | Tên rút gọn của đội | Có |
| `team_tla` | text | Viết tắt 3 chữ cái (vd. `MUN`) | Có |
| `position` | int | Thứ hạng trên bảng xếp hạng trong khoảng hiệu lực của dòng này | Không |
| `played_games` | int | Số trận đã đấu trong khoảng hiệu lực của dòng này | Không |
| `won` / `draw` / `lost` | int | Số trận thắng/hòa/thua trong khoảng hiệu lực của dòng này | Không |
| `points` | int | Tổng điểm trong khoảng hiệu lực của dòng này | Không |
| `goals_for` / `goals_against` / `goal_difference` | int | Tổng bàn thắng/thua/hiệu số trong khoảng hiệu lực của dòng này | Không |
| `form` | text | Chuỗi kết quả gần đây theo football_data_org (vd. `WWDLW`) | Có |
| `valid_from` | timestamp | Thời điểm giá trị của dòng này bắt đầu đúng (lần `dbt snapshot` đầu tiên ghi nhận) | Không |
| `valid_to` | timestamp | Thời điểm giá trị của dòng này hết đúng (lần `dbt snapshot` kế tiếp ghi nhận thay đổi) | Có — `NULL` nghĩa là đây là trạng thái hiện tại/mới nhất của đội |

**Cách trả lời "vị trí tại thời điểm X"**: lọc
`valid_from <= X AND (valid_to IS NULL OR valid_to > X)` cho từng đội, rồi
`position` của dòng đó chính là câu trả lời — không cần xếp hạng lại lúc
truy vấn (khác với `gold.team_standings_by_matchday`, nơi cố tình không có
cột `position`). Lưu ý `valid_from`/`valid_to` là timestamp của lần chạy
snapshot, không phải ngày thi đấu — 1 vòng đấu diễn ra thứ Bảy sẽ chưa xuất
hiện ở đây cho tới khi `dbt snapshot` chạy lần kế tiếp và ghi nhận thay đổi,
có thể là cùng ngày hoặc vài ngày sau tùy tần suất crawl/build.

**Hạn chế đã biết**: cùng lưu ý về độ mới dữ liệu như phần thiếu
`xg`/`xga`/`xpts` của `gold.team_standings_by_matchday` — bảng này chỉ mang
các cột riêng của football_data_org (không có chỉ số expected-goals từ
Understat), vì snapshot mà nó bọc lại là của `silver.standings`, không phải
`gold.league_standings` đã được Understat làm giàu.

---

## gold.search_aliases

**Mục đích**: Bảng tra cứu biệt danh/viết tắt được curate thủ công (vd.
`mu`, `man c`, `psg`, `mo salah`), phục vụ endpoint `GET /api/search` bên
backend, để người dùng không cần gõ đúng substring của tên chính thức
đội/cầu thủ.

**Grain**: 1 dòng cho mỗi cặp `(entity_type, alias)` — một đội hoặc cầu
thủ có thể có nhiều alias. Tính duy nhất được đảm bảo bởi
`assert_gold_search_aliases_unique_grain` (`transform/tests/`). `not_null`
được đảm bảo trên `entity_type`, `alias`, `entity_id` trong
`transform/seeds/_seeds.yml`, và trên `entity_type`/`entity_id` trong
`transform/models/gold/_gold.yml` (model gold không test lại `alias` —
đây chỉ là passthrough từ cột của seed, vốn đã not_null ở đó). Một test
`assert_search_aliases_resolve` ở mức `warn` (`transform/tests/`) sẽ cảnh
báo khi `entity_id` của alias nào đó không còn khớp với team/player thực
tế (vd. sau khi xuống hạng hoặc đổi id).

**Độ mới dữ liệu**: `materialized='table'` — dữ liệu tham chiếu tĩnh, được
rebuild mỗi lần `dbt build`, giống `gold.league_standings`/
`gold.match_results`.

| Cột | Kiểu | Ý nghĩa | Có thể NULL? |
|---|---|---|---|
| `entity_type` | text | `'team'` hoặc `'player'` | Không |
| `alias` | text | Biệt danh/viết tắt, chữ thường, đã trim khoảng trắng | Không |
| `entity_id` | int | Khớp với `team_id` (nếu `entity_type = 'team'`) hoặc `player_id` (nếu `entity_type = 'player'`) ở nơi khác trong `gold.*` | Không |

**Hạn chế đã biết**: phạm vi bao phủ là thủ công và có chủ đích chưa đầy
đủ — bao phủ toàn bộ cho team, nhưng chỉ một tập nhỏ biệt danh cầu thủ nổi
tiếng được curate sẵn (đa số cầu thủ vẫn tìm được qua substring match của
`/api/search` mà không cần alias riêng). Xem
`docs/superpowers/specs/2026-08-10-search-alias-fuzzy-match-design.md`.

---

## Ngoài phạm vi

`gold_head_to_head` và dữ liệu ở mức sự kiện trận đấu (người ghi bàn, thẻ
phạt, thay người — một `gold_match_events_enriched` giả định) chưa tồn tại;
chưa có crawler cho các sự kiện trận đấu. Thông tin định danh đội và kết quả
ở mức trận đấu hiện đã được `gold.team_profile` và `gold.match_results` bao
phủ (xem ở trên). Dữ liệu ở mức cầu thủ được bao phủ toàn diện bởi
`gold.player_profile` (định danh) và `gold.player_performance` (bàn
thắng/kiến tạo/xG/xA), cả hai đều chỉ giới hạn ở Premier League (xem hạn chế
đã biết của từng bảng ở trên).
