# Player Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Crawl football_data_org squad data, land it in bronze, and build the
staging → silver → gold dbt chain so `gold.player_profile` exists as the first
player-level table (one row per player, current team, computed age).

**Architecture:** Medallion pipeline, same shape as the existing
standings/matches path: `crawl_competition()` fetches squads for every team in
the standings it just fetched → `save_raw()` → `ingestion/ingest.py` (no code
change, already generic) → bronze.raw_documents (`entity_type='players'`) →
dbt staging (unnest) → dbt silver (dedupe latest-wins) → dbt gold (view, joins
teams + computes age).

**Tech Stack:** Python (`requests`), PostgreSQL, dbt-core + dbt-postgres.

**Spec:** [docs/superpowers/specs/2026-07-24-player-identity-design.md](../specs/2026-07-24-player-identity-design.md)

## Global Constraints

- No `try/except` beyond what `retry_request()` already handles internally —
  per-team failures are logged and skipped, not wrapped in new defensive code.
- Follow existing repo test conventions: no pytest suite for crawlers/ingestion
  (none exists today for this code); correctness is verified by running the
  pipeline and inspecting output, and by dbt schema tests for the dbt layer.
- `gold.player_profile` must be `materialized='view'`, not `'table'` (every
  other gold model uses `'table'` — this one is intentionally different so
  `age` doesn't go stale between `dbt build` runs).
- `player_id` is the grain key throughout staging/silver/gold — never
  introduce a composite key or a name-based join for player identity (that's
  reserved for sub-project 2's stats-matching problem).
- Squad data reflects the *current* roster only (API has no `season` param) —
  don't write any logic that assumes `gold.player_profile.team_id` is accurate
  for past seasons.

---

## Task 1: Crawler — `get_squad()` + wire into `crawl_competition()`

**Files:**
- Modify: `crawlers/football_data_org/client.py`

**Interfaces:**
- Produces: `get_squad(team_id: int) -> dict` — returns the JSON body of
  `GET /v4/teams/{id}` (contains `id`, `name`, `squad: [...]`), or `{}` on
  failure. Consumed by `crawl_competition()` in this same task, and by nothing
  else yet (sub-project 2 does not touch this function).
- Produces: `extract_team_ids(standings: dict) -> list[int]` — pulls
  `team.id` out of the `TOTAL` block of a standings response. Used only
  inside `crawl_competition()`.

- [ ] **Step 1: Add `get_squad()`**

Insert after `get_matches()` (currently ends at line 48) in
`crawlers/football_data_org/client.py`:

```python
def get_squad(team_id):
    """Fetch a team's current squad. No season param exists for this endpoint —
    it always returns the present-day roster, not a season-specific historical one."""
    url = f"{BASE_URL}/teams/{team_id}"
    limiter.wait()
    response = retry_request(url, headers=HEADERS)
    if not response:
        logger.error(f"Failed to fetch squad for team {team_id}")
        return {}
    try:
        return response.json()
    except requests.exceptions.JSONDecodeError:
        logger.error(f"Response is not valid JSON for {url}: {response.text[:200]}")
        return {}
```

- [ ] **Step 2: Add `extract_team_ids()`**

Insert directly below `get_squad()`:

```python
def extract_team_ids(standings):
    """Parse team ids out of the TOTAL block of a standings response."""
    team_ids = []
    for block in standings.get("standings", []):
        if block.get("type") != "TOTAL":
            continue
        for row in block.get("table", []):
            team_id = row.get("team", {}).get("id")
            if team_id is not None:
                team_ids.append(team_id)
    return team_ids
```

- [ ] **Step 3: Wire squad crawling into `crawl_competition()`**

Replace the standings block inside `crawl_competition()` (currently):

```python
    standings = get_standings(competition_code, season)
    if standings:
        save_raw(standings, "football_data_org", "standings", f"{competition_code}_{season}")
    else:
        logger.error(f"Skipping standings save for {competition_code} because no data was fetched")
```

with:

```python
    standings = get_standings(competition_code, season)
    if standings:
        save_raw(standings, "football_data_org", "standings", f"{competition_code}_{season}")
        for team_id in extract_team_ids(standings):
            squad = get_squad(team_id)
            if squad:
                save_raw(squad, "football_data_org", "players", f"{competition_code}_{season}_{team_id}")
            else:
                logger.error(f"Skipping squad save for team {team_id} because no data was fetched")
    else:
        logger.error(f"Skipping standings save for {competition_code} because no data was fetched")
```

- [ ] **Step 4: Run the crawler and verify output**

```bash
python crawlers/football_data_org/client.py
```

Expected: log lines `Saved: ...\players\...` for every team in both PL and
FL1 (roughly 20 teams each), no unhandled exceptions, ends with `Done!`.

Then list the files created:

```bash
find data/raw/football_data_org/players -name "*.json" | wc -l
```

Expected: one file per team crawled today (~40 total across PL + FL1).

- [ ] **Step 5: Spot-check one raw file**

Open any file under `data/raw/football_data_org/players/<today>/` and confirm
it has a top-level `id` (team id) and a `squad` array where each element has
`id`, `name`, `position`, `dateOfBirth`, `nationality`, `shirtNumber`.

- [ ] **Step 6: Commit**

```bash
git add crawlers/football_data_org/client.py
git commit -m "feat: crawl football_data_org squad data per team"
```

---

## Task 2: Verify bronze ingestion picks up `entity_type='players'`

No code changes — `ingestion/ingest.py`'s discovery/metadata/db modules are
already generic on `entity_type` (confirmed: `ingestion/core/db.py` has no
hardcoded entity_type list). This task is a verification checkpoint before
building the dbt layer on top of it.

**Files:** none.

- [ ] **Step 1: Run ingestion scoped to football_data_org**

```bash
python ingestion/ingest.py --source football_data_org
```

Expected: log lines showing new files ingested, no errors. If Postgres isn't
already running, start it first: `docker compose up -d`.

- [ ] **Step 2: Confirm bronze rows exist**

```bash
psql -U postgres -d football -c "SELECT entity_type, league, season, COUNT(*) FROM bronze.raw_documents WHERE source='football_data_org' AND entity_type='players' GROUP BY 1,2,3;"
```

Expected: rows with `entity_type='players'`, `league` in
(`premier-league`,`ligue-1`), `season='2025-2026'`, one count row per
league/season combination with count matching the number of teams crawled.

(No commit — nothing changed in this task.)

---

## Task 3: dbt staging — `stg_football_data_org__players`

**Files:**
- Create: `transform/models/staging/stg_football_data_org__players.sql`
- Modify: `transform/models/staging/_staging.yml`

**Interfaces:**
- Produces: one row per `(team_id, player_id, ingestion_time)` with columns
  `season, league, ingestion_time, team_id, player_id, player_name, position,
  date_of_birth, nationality, shirt_number`. Consumed by Task 4
  (`silver/players.sql`) via `{{ ref('stg_football_data_org__players') }}`.

- [ ] **Step 1: Write the staging model**

Create `transform/models/staging/stg_football_data_org__players.sql`:

```sql
with players_raw as (
    select season, league, ingestion_time, payload
    from {{ source('bronze', 'raw_documents') }}
    where source = 'football_data_org'
      and entity_type = 'players'
),

squad_rows as (
    select
        season,
        league,
        ingestion_time,
        (payload ->> 'id')::int as team_id,
        jsonb_array_elements(payload -> 'squad') as player_json
    from players_raw
)

select
    season,
    league,
    ingestion_time,
    team_id,
    (player_json ->> 'id')::int as player_id,
    player_json ->> 'name' as player_name,
    player_json ->> 'position' as position,
    (player_json ->> 'dateOfBirth')::date as date_of_birth,
    player_json ->> 'nationality' as nationality,
    (player_json ->> 'shirtNumber')::int as shirt_number
from squad_rows
```

- [ ] **Step 2: Register the model in `_staging.yml`**

Add to `transform/models/staging/_staging.yml` (append after the
`stg_understat__standings` entry):

```yaml
  - name: stg_football_data_org__players
    description: "Staging model for football-data.org squad data. Grain is 1 row/player/snapshot.
                  Squad is current-only — the /v4/teams/{id} endpoint has no season param, so this
                  does not reflect a season-specific historical squad."
    columns:
      - name: player_id
        tests:
          - not_null
        description: "The player_id is the unique identifier for a player in football-data.org, used to join to the players model in silver."
      - name: team_id
        tests:
          - not_null
```

- [ ] **Step 3: Run and test the model**

```bash
cd transform
dbt run --select stg_football_data_org__players
dbt test --select stg_football_data_org__players
```

Expected: both commands complete with `Completed successfully`, 0 errors.

- [ ] **Step 4: Commit**

```bash
git add transform/models/staging/stg_football_data_org__players.sql transform/models/staging/_staging.yml
git commit -m "feat: add stg_football_data_org__players staging model"
```

---

## Task 4: dbt silver — `players`

**Files:**
- Create: `transform/models/silver/players.sql`
- Modify: `transform/models/silver/_silver.yml`

**Interfaces:**
- Consumes: `stg_football_data_org__players` columns as defined in Task 3.
- Produces: one row per `player_id` with columns `player_id, player_name,
  position, date_of_birth, nationality, shirt_number, team_id, league,
  ingestion_time`. Consumed by Task 5 (`gold/player_profile.sql`) via
  `{{ ref('players') }}`.

- [ ] **Step 1: Write the silver model**

Create `transform/models/silver/players.sql`:

```sql
{{ config(materialized='table') }}

with ranked as (
    select
        *,
        row_number() over (
            partition by player_id
            order by ingestion_time desc
        ) as rn
    from {{ ref('stg_football_data_org__players') }}
    where player_id is not null
)

select
    player_id,
    player_name,
    position,
    date_of_birth,
    nationality,
    shirt_number,
    team_id,
    league,
    ingestion_time
from ranked
where rn = 1
```

- [ ] **Step 2: Register the model in `_silver.yml`**

Add to `transform/models/silver/_silver.yml` (append after the `standings`
entry):

```yaml
  - name: players
    description: "Latest squad snapshot per player from football_data_org (used by gold models). Grain is 1 row/player_id — dedupes stg_football_data_org__players by taking the row with the newest ingestion_time per player, which also resolves transfers (most recent team wins)."
    columns:
      - name: player_id
        tests:
          - unique
          - not_null
      - name: player_name
        tests:
          - not_null
```

- [ ] **Step 3: Run and test the model**

```bash
cd transform
dbt run --select players
dbt test --select players
```

Expected: both complete successfully; the `unique`/`not_null` tests on
`player_id` pass (0 failures).

- [ ] **Step 4: Commit**

```bash
git add transform/models/silver/players.sql transform/models/silver/_silver.yml
git commit -m "feat: add silver.players model"
```

---

## Task 5: dbt gold — `player_profile`

**Files:**
- Create: `transform/models/gold/player_profile.sql`
- Modify: `transform/models/gold/_gold.yml`

**Interfaces:**
- Consumes: `silver.players` (Task 4) and `silver.teams` (existing,
  `team_id, team_name` columns).
- Produces: `gold.player_profile`, one row per `player_id`, columns
  `player_id, player_name, position, nationality, date_of_birth, age,
  shirt_number, team_id, team_name, league`. This is the final deliverable of
  this plan — no further tasks consume it.

- [ ] **Step 1: Write the gold model**

Create `transform/models/gold/player_profile.sql`:

```sql
{{ config(materialized='view') }}

select
    p.player_id,
    p.player_name,
    p.position,
    p.nationality,
    p.date_of_birth,
    date_part('year', age(current_date, p.date_of_birth))::int as age,
    p.shirt_number,
    p.team_id,
    t.team_name,
    p.league
from {{ ref('players') }} p
left join {{ ref('teams') }} t on t.team_id = p.team_id
```

- [ ] **Step 2: Register the model in `_gold.yml`**

Add to `transform/models/gold/_gold.yml` (append after the
`team_form_last_5_matches` entry):

```yaml
  - name: player_profile
    description: "One row per player: identity + current team. Grain is 1 row/player_id.
                  Logic: left join silver.players to silver.teams for team_name, compute age
                  from date_of_birth. Materialized as a view (not table like other gold models)
                  so age stays correct at query time instead of going stale between dbt builds.
                  "
    columns:
      - name: player_id
        tests:
          - unique
          - not_null
```

- [ ] **Step 3: Run and test the model**

```bash
cd transform
dbt run --select player_profile
dbt test --select player_profile
```

Expected: both complete successfully; `unique`/`not_null` on `player_id` pass.

- [ ] **Step 4: Spot-check the data**

```bash
psql -U postgres -d football -c "SELECT player_id, player_name, position, nationality, age, team_name, league FROM gold.player_profile ORDER BY random() LIMIT 10;"
```

Expected: 10 real-looking players with plausible ages (16-42), non-null
`team_name`, `league` in (`premier-league`,`ligue-1`).

- [ ] **Step 5: Commit**

```bash
git add transform/models/gold/player_profile.sql transform/models/gold/_gold.yml
git commit -m "feat: add gold.player_profile model"
```

---

## Task 6: Docs — update `docs/gold_data_contract.md`

**Files:**
- Modify: `docs/gold_data_contract.md`

- [ ] **Step 1: Add the `gold.player_profile` section**

Insert a new section after `## gold.team_form_last_5_matches` and before
`## Out of scope`:

```markdown
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
itself still only reflects the most recent crawl (see known limitation below).

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

**Known limitation**: `GET /v4/teams/{id}` (the source endpoint) has no
`season` parameter — it always returns the *current* squad. `team_id` here
reflects whichever team the player was on at the time of the most recent
crawl, not the team they played for during any specific past season. There is
no way to reconstruct historical squad membership from this table. Building
that would require a dedicated SCD2 dbt snapshot on `(player_id, team_id)`
(see `snapshots/snapshot_football_data_org__standings.sql` for the pattern) —
not built yet, since no current consumer needs season-accurate historical
squads.
```

- [ ] **Step 2: Update the "Out of scope" list**

In the `## Out of scope` section at the bottom of the file, change:

```markdown
`gold_top_scorers`, `gold_head_to_head`, `gold_player_performance_summary`, and
`gold_match_events_enriched` do not exist yet. No crawler currently collects
player-level or match-event-level data (only `standings` and `matches`
entity_types exist, both team-level) — building these would require new
crawling work first, not just new dbt models.
```

to:

```markdown
`gold_top_scorers`, `gold_head_to_head`, `gold_player_performance_summary`, and
`gold_match_events_enriched` do not exist yet. `gold.player_profile` (identity
only) now exists, but player *stats* (goals, xG/xA) require a separate
crawler + seed-mapping effort (statbunker top scorers, understat player xG) —
tracked as a follow-up sub-project, not built here. Match-event-level data
also has no crawler yet.
```

- [ ] **Step 3: Commit**

```bash
git add docs/gold_data_contract.md
git commit -m "docs: document gold.player_profile in the gold data contract"
```

---

## Task 7: End-to-end validation

**Files:** none — this task re-runs the full pipeline to confirm nothing else
broke, per the spec's testing plan.

- [ ] **Step 1: Full dbt build**

```bash
cd transform
dbt build
```

Expected: all models (existing + new) and all tests pass, 0 errors, 0 failures.

- [ ] **Step 2: Confirm grain one more time across the full build**

```bash
psql -U postgres -d football -c "SELECT COUNT(*), COUNT(DISTINCT player_id) FROM gold.player_profile;"
```

Expected: the two counts are equal (no duplicate `player_id` rows).

- [ ] **Step 3: Confirm league coverage**

```bash
psql -U postgres -d football -c "SELECT league, COUNT(*) FROM gold.player_profile GROUP BY league;"
```

Expected: two rows, `premier-league` and `ligue-1`, each with a plausible
player count (roughly 20 teams × ~25 players ≈ 400-600 per league).

No commit for this task — it's a validation pass, not a code change. If any
step fails, return to the relevant task above and fix before considering this
plan complete.
