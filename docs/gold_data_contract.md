# Gold Layer Data Contract — Football Data Platform

# 🇬🇧 English

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
resolvable team that season (this fallback also fires when understat/statbunker
rows exist but all resolved to a `NULL` team, e.g. a comma-joined
mid-season-transfer string — not only when there are literally zero rows).

| Column | Type | Meaning | Nullable? |
|---|---|---|---|
| `player_id` | int | Either football_data_org's own numeric id, or understat's native id + a fixed `100000000` offset | No |
| `player_name` | text | Full player name | No |
| `season` | text | `YYYY-YYYY` format | No |
| `team_id` | int | Team this player was attributed to **for this specific season** — see `silver.player_team_season` for the resolution logic | No — `player_team_season`'s `team_candidates` CTE only admits rows with a non-null team_id; a player+season with no resolvable team is omitted from the table entirely rather than appearing with `team_id = NULL` (see limitations) |
| `team_name` | text | Full team name, from `silver.teams` | Yes — same condition as `team_id` |
| `parent_team_id` | int | football_data_org's registered/current squad team_id for this player (see `silver.player_team_season.parent_team_id`) | Yes — same condition as `gold.player_profile.parent_team_id` |
| `parent_team_name` | text | Full team name for `parent_team_id`, from `silver.teams` | Yes — same condition as `parent_team_id` |
| `is_on_loan` | boolean | `true` when `team_id` and `parent_team_id` are both non-null and differ for this specific season, **and** that season still has at least one non-`FINISHED`/`AWARDED` match in `gold.match_results` | No — `false` when `parent_team_id` is `NULL` or the season has already concluded |
| `league` | text | Competition slug | No |
| `resolved_via` | text | Which source resolved `team_id` for this player+season: `understat`, `statbunker`, or `fdo_fallback` | No |
| `goals` | int | Season goals (statbunker) | **Yes** — null if this player has no statbunker row for this season |
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
- **A player+season is silently omitted from the table** if understat's only
  row for them that season has a comma-joined mid-season-transfer `team_title`
  (see below) **and** this player has no football_data_org row to fall back
  to (i.e. an understat-anchored identity, not an fdo one) — rare, since
  most such players also have a statbunker row that season with a resolvable
  team.
- **Understat mid-season transfers**: a comma-joined `team_title` value
  (e.g. `"Bournemouth,Manchester City"`) resolves to `NULL` and is filtered
  out of `team_candidates`, so a player+season with only this resolution
  attempt is silently **absent from the table** (not present with `team_id = NULL`)
  — rare, since most such players also have a statbunker row that season with a
  resolvable team.
- **`source_disagreement` in `silver.player_team_season`** (not exposed
  directly here) flags player+seasons where understat and statbunker both
  have a row but report different teams — a genuine mid-season transfer
  within one season. `understat` wins those ties silently; see
  `assert_player_team_season_source_agreement` (warn) to find them.
- **statbunker only covers Premier League clubs, but `goals` is not always
  `NULL` for a `league = 'ligue-1'` row.** A player who was in Ligue 1 all
  season with no Premier League stint will have `goals = NULL` (statbunker
  never covers Ligue 1 clubs directly). But `league` on a `player_team_season`
  row follows the *winning team* (understat, which has resolution priority),
  not the stat source — so a player who transferred from a Premier League
  club (statbunker-covered) to a Ligue 1 club mid-season can legitimately
  carry non-null statbunker-sourced `goals` from before the transfer on a row
  whose `league` is `ligue-1`.
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

## Out of scope

`gold_head_to_head` and match-event-level data (goal scorers, cards,
substitutions — a hypothetical `gold_match_events_enriched`) do not exist
yet; there is no crawler for match events. Team identity and match-level
results are now covered by `gold.team_profile` and `gold.match_results` (see
above). Player-level data is covered end-to-end by `gold.player_profile`
(identity) and `gold.player_performance` (goals/assists/xG/xA), both
Premier-League-only (see their known limitations above).

# 🇫🇷 Français

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

**Objectif** : Identité du joueur et équipe actuelle, pour la page frontend
`/api/players/{id}` et les recherches de joueurs par le chatbot.

**Grain** : 1 ligne par `player_id`. Vérifié par les tests `unique`/`not_null`
sur `player_id` dans `transform/models/gold/_gold.yml` (aucun fichier
`assert_*_unique_grain.sql` séparé n'est nécessaire — `player_id` seul
constitue le grain, comme `team_id` pour `silver.teams`).

**Fraîcheur** : Contrairement à toutes les autres tables gold, celle-ci est
`materialized='view'`, et non `'table'` — `age` est calculé en direct au
moment de la requête à partir de `date_of_birth`, donc toujours correct sans
nécessiter de `dbt build` pour se rafraîchir. `team_id` lui-même ne reflète
toujours que le crawl le plus récent (voir les limites connues ci-dessous).

| Colonne | Type | Signification | Nullable ? |
|---|---|---|---|
| `player_id` | int | Identifiant du joueur provenant de football_data_org | Non |
| `player_name` | text | Nom complet du joueur | Non |
| `position` | text | Poste tel que rapporté par football_data_org — exactement l'une des valeurs `Goalkeeper`, `Defence`, `Midfield`, `Offence` | Oui |
| `nationality` | text | Nom du pays tel que rapporté par football_data_org (source unique, non normalisé) | Oui — `NULL` pour les joueurs ancrés sur understat, sauf complété via le seed `player_extra_info.csv` |
| `date_of_birth` | date | Date de naissance | Oui — `NULL` pour les joueurs ancrés sur understat, sauf complété via le seed `player_extra_info.csv` |
| `age` | int | Calculé au moment de la requête à partir de `date_of_birth` | Oui — null si `date_of_birth` est null |
| `shirt_number` | int | Numéro de maillot | Oui |
| `team_id` | int | Identifiant d'équipe, ancré sur football_data_org | Non |
| `team_name` | text | Nom complet de l'équipe, provenant de `silver.teams` | Oui — null si `team_id` ne correspond à aucune ligne de `silver.teams` |
| `league` | text | Slug de la compétition dans laquelle l'équipe évolue actuellement | Non |

**Limites connues** :

- **Uniquement la Premier League.** `crawl_competition()` ne crawl les
  effectifs que lorsque `crawl_squads=True` (voir
  `crawlers/football_data_org/client.py`), ce qui n'est activé que pour la
  Premier League (`PL`). La Ligue 1 (`FL1`) est délibérément exclue :
  `GET /v4/teams/{id}` renvoie `200 OK` avec `squad: []` pour **chaque**
  équipe de Ligue 1 avec le forfait football-data.org actuel — ce n'est pas
  un manque par équipe, mais une restriction de données au niveau de la
  compétition. `gold.player_profile` aura **zéro ligne pour la Ligue 1** tant
  que le forfait du compte ne change pas ; c'est une décision de périmètre
  délibérée, pas un bug.
- **L'effectif est uniquement actuel, pas historique par saison.**
  `GET /v4/teams/{id}` n'a pas de paramètre `season` — il renvoie toujours
  l'effectif *actuel*. `team_id` ici reflète l'équipe du joueur au moment du
  crawl le plus récent, pas nécessairement l'équipe pour laquelle il a joué
  lors d'une saison passée précise (par ex. les transferts en cours de saison
  ne sont pas reflétés rétroactivement). Suivre l'historique des effectifs
  nécessiterait un snapshot dbt SCD2 dédié sur `(player_id, team_id)` (voir
  `snapshots/snapshot_football_data_org__standings.sql` pour le modèle) — pas
  encore construit, car aucun consommateur actuel n'a besoin d'un historique
  d'effectif précis par saison.
- **`/v4/teams/{id}` a son propre quota de requêtes**, distinct de la limite
  générale de 10 req/min — observé en pratique sous forme de réponses `403`
  en plein milieu d'un crawl, même pour des requêtes ayant précédemment
  réussi. Les échecs par équipe sont journalisés puis ignorés
  (`crawl_competition()` continue avec l'équipe suivante), donc atteindre le
  quota pendant un crawl signifie simplement que l'effectif de cette équipe
  manque dans bronze jusqu'à ce qu'un crawl ultérieur réussi le complète — ni
  un crash, ni une donnée silencieusement incorrecte.
- **Le vocabulaire à 4 valeurs de `position` ci-dessus est codé en dur
  ailleurs.** La requête de tri de l'effectif dans `backend/routers/teams.py`
  (`ORDER BY CASE position WHEN 'Goalkeeper' THEN 1 ...`) et la constante
  `POSITION_GROUPS` de `frontend/components/SquadTable.tsx` dépendent toutes
  deux exactement de ces 4 valeurs — tout changement futur de ce domaine
  (ex. une nouvelle valeur de poste renvoyée par football_data_org) doit
  mettre à jour les deux.

---

## gold.player_performance

**Objectif** : Statistiques du joueur — buts, passes décisives, minutes
jouées, xG/xA — pour la page frontend `/api/players/{id}/performance` et des
questions du chatbot comme « combien de buts le joueur X a-t-il marqués » ou
« quel est le xG du joueur X ».

**Grain** : 1 ligne par `player_id`. Vérifié par les tests `unique`/`not_null`
sur `player_id` dans `transform/models/gold/_gold.yml` (même schéma que
`player_profile` — aucun `assert_*_unique_grain.sql` séparé nécessaire).

**Fraîcheur** : `materialized='table'` — reflète les crawls statbunker et
understat les plus récents à la date du dernier `dbt build`, chacun
dédupliqué sur son dernier instantané par joueur (même logique « le plus
récent gagne » que la jointure Understat de `gold.league_standings`).
L'identité de base (`player_id`, `player_name`, `team_id`) provient de la
même source que `gold.player_profile` (`silver.players`), elle hérite donc
des limites de cette table (Premier League uniquement, effectif actuel
uniquement — voir `gold.player_profile` ci-dessus).

| Colonne | Type | Signification | Nullable ? |
|---|---|---|---|
| `player_id` | int | Identifiant du joueur provenant de football_data_org | Non |
| `player_name` | text | Nom complet du joueur | Non |
| `team_id` | int | Identifiant d'équipe, ancré sur football_data_org | Non |
| `team_name` | text | Nom complet de l'équipe, provenant de `silver.teams` | Oui |
| `league` | text | Slug de la compétition dans laquelle l'équipe évolue actuellement | Non |
| `goals` | int | Buts de la saison (statbunker) | **Oui** — null si ce joueur n'a pas pu être associé à une ligne statbunker (voir ci-dessous) |
| `assists` | int | Passes décisives de la saison (understat) | **Oui** — même condition que `xg` |
| `apps` | int | Nombre d'apparitions (understat) | **Oui** — même condition que `xg` |
| `minutes` | int | Minutes jouées (understat) | **Oui** — même condition que `xg` |
| `xg` | numeric | Buts attendus (understat) | **Oui** — null si ce joueur n'a pas pu être associé à une ligne understat |
| `xa` | numeric | Passes décisives attendues (understat) | **Oui** — même condition que `xg` |
| `xg90` | numeric | Buts attendus par 90 minutes (understat), calculé comme `xg / (minutes / 90)` car l'endpoint de données Understat ne le renvoie pas directement | **Oui** — même condition que `xg`, également null si `minutes` vaut 0 |
| `xa90` | numeric | Passes décisives attendues par 90 minutes (understat), calculées de la même manière | **Oui** — même condition que `xg90` |

**Limites connues** :

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
- **Transferts en cours de saison chez Understat** : une valeur `team_title`
  jointe par virgule (ex. `"Bournemouth,Manchester City"`) résout
  intentionnellement `team_id` à `NULL` plutôt que de deviner quelle équipe
  est actuelle — `player_id` (et donc les statistiques) peut néanmoins être
  résolu via la correspondance par nom seul, même quand `team_id` est `NULL`.
- **statbunker ne couvre que la Premier League** (`COMPETITION_IDS` dans
  `crawlers/statbunker/scraper.py` n'a qu'une seule entrée). `goals` sera
  toujours `NULL` pour tout joueur hors de ce périmètre — sans conséquence
  pratique aujourd'hui puisque `silver.players` lui-même se limite déjà à la
  Premier League.
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

# 🇻🇳 Tiếng Việt

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

**Mục đích**: Thông tin định danh cầu thủ và đội hiện tại, phục vụ trang
frontend `/api/players/{id}` và tra cứu cầu thủ qua chatbot.

**Grain**: 1 dòng cho mỗi `player_id`. Được đảm bảo bởi test
`unique`/`not_null` trên `player_id` trong `transform/models/gold/_gold.yml`
(không cần file `assert_*_unique_grain.sql` riêng — chỉ `player_id` đã là
grain, giống `team_id` của `silver.teams`).

**Độ mới dữ liệu**: Khác với mọi bảng gold khác, bảng này là
`materialized='view'`, không phải `'table'` — `age` được tính trực tiếp tại
thời điểm truy vấn từ `date_of_birth`, nên luôn chính xác mà không cần
`dbt build` để làm mới. Bản thân `team_id` vẫn chỉ phản ánh lần crawl gần
nhất (xem hạn chế đã biết bên dưới).

| Cột | Kiểu | Ý nghĩa | Có thể NULL? |
|---|---|---|---|
| `player_id` | int | Mã cầu thủ từ football_data_org | Không |
| `player_name` | text | Tên đầy đủ của cầu thủ | Không |
| `position` | text | Vị trí thi đấu theo football_data_org — chỉ nhận đúng một trong 4 giá trị `Goalkeeper`, `Defence`, `Midfield`, `Offence` | Có |
| `nationality` | text | Tên quốc gia theo football_data_org (một nguồn duy nhất, chưa chuẩn hóa) | Có — `NULL` với cầu thủ neo theo understat, trừ khi được backfill qua seed `player_extra_info.csv` |
| `date_of_birth` | date | Ngày sinh | Có — `NULL` với cầu thủ neo theo understat, trừ khi được backfill qua seed `player_extra_info.csv` |
| `age` | int | Tính tại thời điểm truy vấn từ `date_of_birth` | Có — null nếu `date_of_birth` là null |
| `shirt_number` | int | Số áo | Có |
| `team_id` | int | Mã đội, neo theo football_data_org | Không |
| `team_name` | text | Tên đầy đủ của đội, lấy từ `silver.teams` | Có — null nếu `team_id` không khớp dòng nào trong `silver.teams` |
| `league` | text | Slug giải đấu mà đội đang thi đấu hiện tại | Không |

**Hạn chế đã biết**:

- **Chỉ có Premier League.** `crawl_competition()` chỉ crawl đội hình khi
  `crawl_squads=True` (xem `crawlers/football_data_org/client.py`), và điều
  này chỉ được bật cho Premier League (`PL`). Ligue 1 (`FL1`) bị loại trừ có
  chủ đích: `GET /v4/teams/{id}` trả về `200 OK` với `squad: []` cho **mọi**
  đội Ligue 1 theo gói football-data.org hiện tại — đây không phải thiếu sót
  từng đội, mà là giới hạn dữ liệu ở mức giải đấu. `gold.player_profile` sẽ
  **không có dòng nào cho Ligue 1** cho đến khi gói tài khoản thay đổi; đây
  là quyết định phạm vi có chủ đích, không phải lỗi.
- **Đội hình chỉ là hiện tại, không có lịch sử theo mùa.**
  `GET /v4/teams/{id}` không có tham số `season` — luôn trả về đội hình
  *hiện tại*. `team_id` ở đây phản ánh đội mà cầu thủ thuộc về tại thời
  điểm crawl gần nhất, không nhất thiết là đội họ thi đấu trong một mùa giải
  cụ thể trong quá khứ (vd. chuyển nhượng giữa mùa sẽ không được phản ánh
  hồi tố). Muốn theo dõi lịch sử đội hình cần một snapshot dbt SCD2 riêng
  trên `(player_id, team_id)` (xem
  `snapshots/snapshot_football_data_org__standings.sql` để tham khảo mẫu) —
  chưa được xây dựng, vì hiện chưa có consumer nào cần lịch sử đội hình
  chính xác theo mùa.
- **`/v4/teams/{id}` có quota request riêng**, tách biệt với rate limit
  chung 10 req/phút — trên thực tế quan sát thấy phản hồi `403` giữa chừng
  crawl, kể cả với các request từng thành công trước đó. Lỗi theo từng đội
  được ghi log và bỏ qua (`crawl_competition()` tiếp tục với đội tiếp theo),
  nên việc hết quota trong lúc crawl chỉ có nghĩa là đội hình của đội đó
  thiếu trong bronze cho đến khi một lần crawl thành công sau đó bổ sung lại
  — không phải crash, và không phải dữ liệu sai lệch âm thầm.
- **Bộ 4 giá trị `position` ở trên bị hardcode ở nơi khác.** Câu truy vấn sắp
  xếp đội hình trong `backend/routers/teams.py`
  (`ORDER BY CASE position WHEN 'Goalkeeper' THEN 1 ...`) và hằng số
  `POSITION_GROUPS` trong `frontend/components/SquadTable.tsx` đều phụ thuộc
  chính xác vào 4 giá trị này — nếu domain này thay đổi trong tương lai (vd.
  football_data_org trả về thêm giá trị vị trí mới), cần cập nhật cả hai nơi.

---

## gold.player_performance

**Mục đích**: Thống kê cầu thủ — bàn thắng, kiến tạo, số phút thi đấu,
xG/xA — phục vụ trang frontend `/api/players/{id}/performance` và các câu
hỏi chatbot như "cầu thủ X đã ghi bao nhiêu bàn" hoặc "xG của cầu thủ X là
bao nhiêu".

**Grain**: 1 dòng cho mỗi `player_id`. Được đảm bảo bởi test
`unique`/`not_null` trên `player_id` trong `transform/models/gold/_gold.yml`
(giống mẫu của `player_profile` — không cần `assert_*_unique_grain.sql`
riêng).

**Độ mới dữ liệu**: `materialized='table'` — phản ánh các lần crawl
statbunker và understat gần nhất tính đến `dbt build` gần nhất, mỗi nguồn
được khử trùng lặp về snapshot mới nhất theo từng cầu thủ (cùng cơ chế "mới
nhất thắng" như join Understat trong `gold.league_standings`). Thông tin
định danh cơ bản (`player_id`, `player_name`, `team_id`) lấy từ cùng nguồn
với `gold.player_profile` (`silver.players`), nên kế thừa các hạn chế của
bảng đó (chỉ Premier League, chỉ đội hình hiện tại — xem `gold.player_profile`
ở trên).

| Cột | Kiểu | Ý nghĩa | Có thể NULL? |
|---|---|---|---|
| `player_id` | int | Mã cầu thủ từ football_data_org | Không |
| `player_name` | text | Tên đầy đủ của cầu thủ | Không |
| `team_id` | int | Mã đội, neo theo football_data_org | Không |
| `team_name` | text | Tên đầy đủ của đội, lấy từ `silver.teams` | Có |
| `league` | text | Slug giải đấu mà đội đang thi đấu hiện tại | Không |
| `goals` | int | Số bàn thắng trong mùa (statbunker) | **Có** — null nếu cầu thủ này không khớp được với dòng dữ liệu statbunker (xem bên dưới) |
| `assists` | int | Số kiến tạo trong mùa (understat) | **Có** — cùng điều kiện với `xg` |
| `apps` | int | Số trận ra sân (understat) | **Có** — cùng điều kiện với `xg` |
| `minutes` | int | Số phút thi đấu (understat) | **Có** — cùng điều kiện với `xg` |
| `xg` | numeric | Bàn thắng kỳ vọng (understat) | **Có** — null nếu cầu thủ này không khớp được với dòng dữ liệu understat |
| `xa` | numeric | Kiến tạo kỳ vọng (understat) | **Có** — cùng điều kiện với `xg` |
| `xg90` | numeric | Bàn thắng kỳ vọng mỗi 90 phút (understat), tính bằng `xg / (minutes / 90)` vì endpoint dữ liệu của Understat không trả trực tiếp giá trị này | **Có** — cùng điều kiện với `xg`, cũng null nếu `minutes` bằng 0 |
| `xa90` | numeric | Kiến tạo kỳ vọng mỗi 90 phút (understat), tính theo cách tương tự | **Có** — cùng điều kiện với `xg90` |

**Hạn chế đã biết**:

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
- **Chuyển nhượng giữa mùa trên Understat**: giá trị `team_title` nối bằng
  dấu phẩy (vd. `"Bournemouth,Manchester City"`) được cố ý gán `team_id` là
  `NULL` thay vì đoán đội nào là hiện tại — `player_id` (và do đó là stats)
  vẫn có thể được xác định qua khớp theo tên, kể cả khi `team_id` là `NULL`.
- **statbunker chỉ bao phủ Premier League** (`COMPETITION_IDS` trong
  `crawlers/statbunker/scraper.py` chỉ có một mục). `goals` sẽ luôn là
  `NULL` với bất kỳ cầu thủ nào ngoài phạm vi này — trên thực tế không ảnh
  hưởng vì bản thân `silver.players` đã chỉ giới hạn ở Premier League.
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

## Ngoài phạm vi

`gold_head_to_head` và dữ liệu ở mức sự kiện trận đấu (người ghi bàn, thẻ
phạt, thay người — một `gold_match_events_enriched` giả định) chưa tồn tại;
chưa có crawler cho các sự kiện trận đấu. Thông tin định danh đội và kết quả
ở mức trận đấu hiện đã được `gold.team_profile` và `gold.match_results` bao
phủ (xem ở trên). Dữ liệu ở mức cầu thủ được bao phủ toàn diện bởi
`gold.player_profile` (định danh) và `gold.player_performance` (bàn
thắng/kiến tạo/xG/xA), cả hai đều chỉ giới hạn ở Premier League (xem hạn chế
đã biết của từng bảng ở trên).
