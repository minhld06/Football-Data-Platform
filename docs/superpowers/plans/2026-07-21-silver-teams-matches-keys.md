# Silver Teams/Matches Entity Keys Implementation Plan

> **For agentic workers:** this plan is executed in **guided-teaching mode**, not
> subagent-driven or inline-autonomous execution. The user writes the SQL/YAML for
> each task; the assistant explains the goal, target schema, and join logic, then
> reviews what the user writes before moving to the next task. Do not write files
> for the user in this mode unless they ask for a code sample after attempting it
> themselves. Steps use checkbox (`- [ ]`) syntax for tracking progress.

**Goal:** Build the 4 staging models + 2 silver models (`silver.teams`,
`silver.matches`) for the Week 5+6 minimum deliverable, implementing the entity-key
design from [2026-07-21-silver-entity-keys-design.md](../specs/2026-07-21-silver-entity-keys-design.md).

**Architecture:** football_data_org's numeric `team.id` is the anchor for team
identity. statbunker/understat team names are resolved to that id via a
hand-written seed (`team_name_map.csv`), joined in their respective staging models.
`silver.matches` keys on `(source, source_match_id)` and references
`silver.teams.team_id` directly.

**Tech Stack:** dbt-core + dbt-postgres, models live under `transform/`.

## Global Constraints

- Team key = football_data_org `team.id` (int). No new surrogate key is minted.
- Seed file `transform/seeds/team_name_map.csv` columns: `source, raw_team_name,
  team_id` — hand-written, no auto-normalization logic.
- A build must **fail** (not silently produce NULL) if a statbunker/understat team
  name has no seed mapping — this is the Decision 2 safety net from the spec.
- Match key = composite `(source, source_match_id)`, `source` always populated even
  though only football_data_org currently produces match-level data.
- Silver models materialize as `table` (existing convention in `models/silver/teams.sql`);
  staging models use the project default `view` (`dbt_project.yml`).
- Per the course roadmap, each silver model needs **at least 3 schema tests**.
- Follow CLAUDE.md: no `try/except`-equivalent silent failure patterns — if a SQL
  join can produce an unexpected NULL that matters, there must be a test that turns
  it into a build failure.

---

## Reference data (ground truth, already extracted from bronze samples)

**football_data_org teams** (id → name, shortName, tla, competition) — anchor set,
covers both leagues in scope:

```
57  Arsenal FC / Arsenal / ARS / PL         58  Aston Villa FC / Aston Villa / AVL / PL
61  Chelsea FC / Chelsea / CHE / PL         62  Everton FC / Everton / EVE / PL
63  Fulham FC / Fulham / FUL / PL           64  Liverpool FC / Liverpool / LIV / PL
65  Manchester City FC / Man City / MCI/PL  66  Manchester United FC / Man United/MUN/PL
67  Newcastle United FC / Newcastle/NEW/PL  71  Sunderland AFC / Sunderland / SUN / PL
73  Tottenham Hotspur FC / Tottenham/TOT/PL 76  Wolverhampton Wanderers FC/Wolverhampton/WOL/PL
328 Burnley FC / Burnley / BUR / PL         341 Leeds United FC / Leeds United/LEE/PL
351 Nottingham Forest FC/Nottingham/NOT/PL  354 Crystal Palace FC/Crystal Palace/CRY/PL
397 Brighton & Hove Albion FC/Brighton Hove/BHA/PL  402 Brentford FC/Brentford/BRE/PL
563 West Ham United FC / West Ham / WHU/PL  1044 AFC Bournemouth / Bournemouth/BOU/PL
511 Toulouse FC / Toulouse / TOU / FL1      512 Stade Brestois 29 / Brest / BRE / FL1
516 Olympique de Marseille/Marseille/MAR/FL1 519 AJ Auxerre / Auxerre / AJA / FL1
521 Lille OSC / Lille / LIL / FL1           522 OGC Nice / Nice / NIC / FL1
523 Olympique Lyonnais/Olympique Lyon/LYO/FL1 524 Paris Saint-Germain FC/PSG/PSG/FL1
525 FC Lorient / Lorient / FCL / FL1        529 Stade Rennais FC 1901/Stade Rennais/REN/FL1
532 Angers SCO / Angers SCO / ANG / FL1     533 Le Havre AC / Le Havre / HAC / FL1
543 FC Nantes / Nantes / NAN / FL1          545 FC Metz / FC Metz / FCM / FL1
546 Racing Club de Lens / RC Lens / RCL/FL1 548 AS Monaco FC / Monaco / ASM / FL1
576 RC Strasbourg Alsace/Strasbourg/RC /FL1 1045 Paris FC / Paris FC / PFC / FL1
```

**statbunker distinct `team` strings** (all Premier League, `source='statbunker'`):
`AFC Bournemouth, Arsenal, Aston Villa, Brentford, Brighton & Hove Albion, Burnley,
Chelsea, Crystal Palace, Everton, Fulham, Leeds United, Liverpool, Manchester City,
Manchester United, Newcastle United, Nottingham Forest, Sunderland, Tottenham
Hotspur, West Ham United, Wolverhampton Wanderers` (20 rows)

**understat distinct `team` strings** (`source='understat'`), EPL:
`Arsenal, Aston Villa, Bournemouth, Brentford, Brighton, Burnley, Chelsea, Crystal
Palace, Everton, Fulham, Leeds, Liverpool, Manchester City, Manchester United,
Newcastle United, Nottingham Forest, Sunderland, Tottenham, West Ham,
Wolverhampton Wanderers` (20 rows) — Ligue 1: `Angers, Auxerre, Brest, Le Havre,
Lens, Lille, Lorient, Lyon, Marseille, Metz, Monaco, Nantes, Nice, Paris FC, Paris
Saint Germain, Rennes, Strasbourg, Toulouse` (18 rows)

Note the mismatches to map carefully: `AFC Bournemouth` (statbunker) / `Bournemouth`
(understat) → `1044`; `Brighton & Hove Albion` (statbunker) / `Brighton` (understat)
→ `397`; `Leeds United` (statbunker) / `Leeds` (understat) → `341`; `Tottenham
Hotspur` (statbunker) / `Tottenham` (understat) → `73`; `West Ham United`
(statbunker) / `West Ham` (understat) → `563`; `Stade Rennais FC 1901` (fd_org) /
`Rennes` (understat) → `529`; `Paris Saint-Germain FC` (fd_org) / `Paris Saint
Germain` (understat) → `524`; `Racing Club de Lens` (fd_org) / `Lens` (understat) →
`546`; `Olympique Lyonnais` (fd_org) / `Lyon` (understat) → `523`; `RC Strasbourg
Alsace` (fd_org) / `Strasbourg` (understat) → `576`.

---

## Task 1: Team name mapping seed

**Files:**
- Create: `transform/seeds/team_name_map.csv`
- Test: `transform/tests/assert_team_names_mapped.sql` (singular test)

**Interfaces:**
- Produces: a seed table `team_name_map(source text, raw_team_name text, team_id
  integer)` that Tasks 4–5 join against.

**What to do:**
1. Using the reference data above, write `team_name_map.csv` with header
   `source,raw_team_name,team_id` and one row per statbunker name (20 rows,
   `source=statbunker`) and one row per understat name (38 rows,
   `source=understat`). 58 data rows total.
2. Run `dbt seed` (from `transform/`) and confirm it loads without error.
3. Write the singular test `assert_team_names_mapped.sql`. A singular test is just
   a `.sql` file under `transform/tests/` whose query should return **zero rows**
   for the test to pass — write a query that finds any distinct `(source,
   raw_team_name)` pair present in the statbunker/understat bronze standings
   payloads that has **no** matching row in `team_name_map`. (You'll be able to
   fully wire this once Tasks 4–5 exist, since it needs their `raw_team_name`
   column — it's fine to draft it against the seed + bronze directly for now.)
4. This test is the safety net from Decision 2 — it should fail loudly if a future
   crawl run introduces a team name not yet in the seed.

**Acceptance:** `dbt seed` succeeds; seed table has 58 rows; test file exists (full
green run happens after Task 5).

---

## Task 2: `stg_football_data_org__standings`

**Files:**
- Create: `transform/models/staging/stg_football_data_org__standings.sql`
- Modify: `transform/models/staging/_staging.yml` (create if it doesn't exist —
  schema tests for this model)

**Interfaces:**
- Consumes: `{{ source('bronze', 'raw_documents') }}` where `source =
  'football_data_org'` and `entity_type = 'standings'`.
- Produces columns: `team_id` (int), `team_name`, `short_name`, `tla`, `country`
  (from `competition`/`area` — check the payload's top-level `area.name` or
  `competition` structure), `season`, `position`, `played_games`, `won`, `draw`,
  `lost`, `points`, `goals_for`, `goals_against`, `goal_difference`, `form`. One
  row per team per standings snapshot.

**What to do:** The payload shape is `{ area, competition, season, standings: [{
  type: 'TOTAL', table: [{ position, team: {id, name, shortName, tla},
  playedGames, won, draw, lost, points, goalsFor, goalsAgainst, goalDifference,
  form }] }] }`. Only unnest `standings` where `type = 'TOTAL'` (ignore HOME/AWAY
  splits if present) using `jsonb_array_elements`, then unnest `table`. Cast
  numeric fields explicitly.

**Acceptance:** `dbt run --select stg_football_data_org__standings` succeeds; add
`unique`+`not_null` tests on `team_id` (composed with season if you materialize
multiple seasons) in `_staging.yml`; `dbt test --select
stg_football_data_org__standings` passes.

---

## Task 3: `stg_football_data_org__matches`

**Files:**
- Create: `transform/models/staging/stg_football_data_org__matches.sql`
- Modify: `transform/models/staging/_staging.yml`

**Interfaces:**
- Consumes: bronze rows where `source = 'football_data_org'`, `entity_type =
  'matches'`.
- Produces columns: `source_match_id` (int, from `match.id`), `competition_code`,
  `season`, `matchday`, `utc_date`, `status`, `home_team_id`, `away_team_id`,
  `home_score`, `away_score`. One row per match.

**What to do:** Similar unnesting to the existing `models/silver/teams.sql` (you
already have a working reference for `jsonb_array_elements(payload -> 'matches')`
and pulling `homeTeam ->> 'id'` etc.) — reuse that pattern, but this time keep one
row per match (not per team) and pull `score -> 'fullTime' ->> 'home'/'away'` for
the score.

**Acceptance:** `dbt run --select stg_football_data_org__matches` succeeds; add
`unique`+`not_null` on `source_match_id` in `_staging.yml`; tests pass.

---

## Task 4: `stg_statbunker__standings`

**Files:**
- Create: `transform/models/staging/stg_statbunker__standings.sql`
- Modify: `transform/models/staging/_staging.yml`

**Interfaces:**
- Consumes: bronze rows where `source = 'statbunker'`, `entity_type =
  'standings'`; joins `{{ ref('team_name_map') }}` filtered to
  `source='statbunker'` on `raw_team_name = payload row's team name`.
- Produces columns: `team_id` (int, resolved via seed — NOT NULL enforced by
  Task 1's test), `raw_team_name`, `season`, `rank`, `played`, `wins`, `draws`,
  `losses`, `goals_for`, `goals_against`, `goal_diff`, `points`.

**What to do:** The bronze payload here is a **flat JSON array** of row objects
(not nested under a key), so unnest with `jsonb_array_elements(payload)` directly.
Every field in the raw JSON is a string (`"38"`, `"85"`) — cast to `int`. Join to
`team_name_map` to resolve `team_id`; keep `raw_team_name` in the output too (the
Task 1 test needs it, and it's useful for debugging).

**Acceptance:** `dbt run --select stg_statbunker__standings` succeeds; add
`not_null` on `team_id` in `_staging.yml` (this is your first line of defense — if
the join produces NULL, this test catches it even before the singular test runs).

---

## Task 5: `stg_understat__standings`

**Files:**
- Create: `transform/models/staging/stg_understat__standings.sql`
- Modify: `transform/models/staging/_staging.yml`

**Interfaces:** Same shape as Task 4, but `source='understat'`, and this model
additionally carries `xg`, `xga`, `xpts` (present in the understat payload,
absent from statbunker's).

**What to do:** Same flat-array unnesting as Task 4. Join `team_name_map` filtered
to `source='understat'`.

**Acceptance:** `dbt run --select stg_understat__standings` succeeds; `not_null` on
`team_id`. Now go back to Task 1's singular test — wire it to union
`raw_team_name` from both `stg_statbunker__standings` and
`stg_understat__standings` where `team_id is null`, and run `dbt test --select
assert_team_names_mapped`. It should return 0 rows (pass). If it fails, you're
missing a seed row — fix the CSV, `dbt seed`, retest.

---

## Task 6: `silver.teams` (rewrite)

**Files:**
- Modify: `transform/models/silver/teams.sql`
- Modify: `transform/models/silver/_silver.yml` (create if it doesn't exist)

**Interfaces:**
- Consumes: `{{ ref('stg_football_data_org__standings') }}` (or `_matches` — either
  gives you `team_id`/`team_name`/`short_name`/`tla`; standings also gives you
  `country`), plus `{{ ref('stg_statbunker__standings') }}` and `{{
  ref('stg_understat__standings') }}` purely to confirm every `team_id` they
  resolve to already exists in the football_data_org set (it will, by
  construction of the seed).
- Produces: `silver.teams(team_id int primary key, team_name text, short_name
  text, tla text, country text)` — one row per team, deduped.

**What to do:** Replace the current matches-only version. Source canonical name
fields from football_data_org (per Decision 1 — it's the anchor, so its spelling
wins). `distinct` on `team_id` since the same team can appear across multiple
matches/standings snapshots and both PL+FL1 sources.

**Acceptance:** `dbt run --select silver.teams` succeeds (note: model file is
`teams.sql`, relation is `silver.teams` per `profiles.yml` schema config). In
`_silver.yml`, add at least 3 tests: `unique(team_id)`, `not_null(team_id)`,
`not_null(team_name)`. `dbt test --select silver.teams` passes.

---

## Task 7: `silver.matches` (new)

**Files:**
- Create: `transform/models/silver/matches.sql`
- Modify: `transform/models/silver/_silver.yml`

**Interfaces:**
- Consumes: `{{ ref('stg_football_data_org__matches') }}`.
- Produces: `silver.matches(source text, source_match_id int, competition_code
  text, season text, matchday int, utc_date timestamp, status text, home_team_id
  int, away_team_id int, home_score int, away_score int)`.

**What to do:** `source` is a literal `'football_data_org'` for every row today
(per Decision 3 — kept for future-proofing, not because there's a real second
source yet). `home_team_id`/`away_team_id` are pass-throughs from staging — no
join needed, football_data_org already gives ids that match `silver.teams.team_id`.

**Acceptance:** `dbt run --select silver.matches` succeeds. In `_silver.yml`, add
at least 3 tests: `unique` combination on `(source, source_match_id)` — dbt-utils
`unique_combination_of_columns` if the `dbt_utils` package is installed, otherwise
a singular test doing `group by source, source_match_id having count(*) > 1`;
`not_null(source_match_id)`; `relationships` test on `home_team_id` →
`silver.teams.team_id` (and ideally the same on `away_team_id`).

---

## Task 8: End-to-end verification

**Files:** none (verification only)

**What to do:**
1. From `transform/`, run `dbt seed && dbt run && dbt test`.
2. Confirm all 4 staging + 2 silver models build and every test passes — expect
   at least: 1 (Task1 singular) + 2 (Task2) + 1 (Task3 unique/not_null — pick 2) +
   1 (Task4 not_null) + 1 (Task5 not_null) + 3 (Task6) + 3 (Task7) tests green.
3. Spot-check row counts: `select count(*) from silver.teams` should be 38 (20 PL +
   18 Ligue 1); `select count(*) from silver.matches` should equal the number of
   match records ingested for PL+FL1 2025 season.
4. Commit everything (seed, staging models, silver models, schema ymls, singular
   test) in one commit: `feat: add staging + silver.teams/matches with unified
   team keys`.

**Acceptance:** `dbt build` (equivalent to seed+run+test) exits 0 with no failures.
