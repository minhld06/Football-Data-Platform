# Standings History Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve prior versions of football_data_org standings instead of silently overwriting them, so a reader can see that a row is an updated version of an earlier one.

**Architecture:** Add a `silver.standings` model that dedupes staging to "latest row per team" (pulling logic out of `gold.league_standings` so it isn't duplicated), then layer a `dbt snapshot` (SCD Type 2, `check` strategy) on top of that model to record every version transition in a dedicated `snapshots` schema.

**Tech Stack:** dbt-core 1.12.0 (dbt-postgres 1.11.0), PostgreSQL. No new packages required — composite `unique_key` lists are supported natively.

## Global Constraints

- dbt-core version is 1.12.0 — composite `unique_key` (list of columns) on snapshots works without `dbt_utils`.
- Snapshot config: `target_schema='snapshots'`, `unique_key=['league','season','team_id']`, `strategy='check'`, `check_cols` limited to the stat columns (`position, played_games, won, draw, lost, points, goals_for, goals_against, goal_difference, form`) — never `team_name` or `ingestion_time`.
- Custom singular tests in this project are bare SQL files under `transform/tests/*.sql` that `select` the *violating* rows — no `{% test %}` macro wrapper. A passing test returns 0 rows. Follow the existing style (see `transform/tests/assert_gold_league_standings_unique_grain.sql`).
- New silver models are `{{ config(materialized='table') }}`, matching `silver/teams.sql` and `silver/matches.sql`.
- Do not modify `transform/models/staging/stg_football_data_org__standings.sql` or any other staging model.
- `gold/league_standings.sql`'s understat (`us_standings`/`us_latest`) CTEs are untouched — out of scope for this plan.
- All new comments/docs are in English (project convention as of the "Change comments language VN -> ENG" commit).
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` must be exported into the shell before running anything below — `dbt`'s `env_var()` in `profiles.yml` reads OS environment variables (it does not load `.env` itself), and the `docker compose exec postgres psql ...` commands below also reference `$POSTGRES_USER`/`$POSTGRES_DB`. Once per terminal session, from the repo root:
  ```bash
  export $(grep -v '^#' .env | xargs)
  ```
  Environment variables persist across `cd` in the same shell, so this only needs to run once even though `dbt` commands are run from `transform/` and `docker compose`/`psql` commands are run from the repo root.
- Postgres must be running: `docker compose up -d postgres` from the repo root.
- `dbt` commands below assume the working directory is `transform/` and use the `transform/.venv` virtualenv's `dbt` executable (on PATH after activating the venv, or invoke it directly as `.venv/Scripts/dbt`).
- There is no `DATABASE_URL` in the host `.env` (only the `POSTGRES_*` vars) — `ingestion/ingest.py` requires `DATABASE_URL` and will raise `RuntimeError` without it, so any ingestion re-run in this plan goes through `docker compose run --rm ingestion ...`, which has `DATABASE_URL` baked into the container environment, rather than running `python ingestion/ingest.py` directly on the host.
- Design reference: [docs/superpowers/specs/2026-07-22-standings-history-snapshot-design.md](../specs/2026-07-22-standings-history-snapshot-design.md).

---

## File Structure

- Create: `transform/models/silver/standings.sql` — dedupes `stg_football_data_org__standings` to one row per `(league, season, team_id)` (latest by `ingestion_time`).
- Modify: `transform/models/silver/_silver.yml` — add doc/tests for the new `standings` model.
- Create: `transform/tests/assert_silver_standings_unique_grain.sql` — singular test asserting `silver.standings` grain.
- Modify: `transform/models/gold/league_standings.sql` — replace the inline `fd_standings`/`fd_latest` dedup CTEs with `ref('standings')`.
- Create: `transform/snapshots/snapshot_football_data_org__standings.sql` — the dbt snapshot definition (SCD Type 2 over `silver.standings`).
- Create: `transform/tests/assert_snapshot_standings_one_current_row.sql` — singular test asserting exactly one "current" row per key in the snapshot table.
- No other files change. The end-to-end verification in Task 4 touches only gitignored raw data under `data/raw/` — nothing there is committed.

---

### Task 1: `silver.standings` model, docs, and grain test

**Files:**
- Create: `transform/models/silver/standings.sql`
- Modify: `transform/models/silver/_silver.yml`
- Test: `transform/tests/assert_silver_standings_unique_grain.sql`

**Interfaces:**
- Consumes: `ref('stg_football_data_org__standings')` — columns `season, league, ingestion_time, team_id, team_name, team_short_name, team_tla, position, played_games, won, draw, lost, points, goals_for, goals_against, goal_difference, form` (see `transform/models/staging/stg_football_data_org__standings.sql`).
- Produces: model `standings`, referenced as `{{ ref('standings') }}`. Grain: one row per `(league, season, team_id)`. Columns: `league, season, team_id, position, played_games, won, draw, lost, points, goals_for, goals_against, goal_difference, form, ingestion_time`.

- [ ] **Step 1: Write the model**

Create `transform/models/silver/standings.sql`:

```sql
{{ config(materialized='table') }}

with standings_ranked as (
    select
        *,
        row_number() over (
            partition by league, season, team_id
            order by ingestion_time desc
        ) as rn
    from {{ ref('stg_football_data_org__standings') }}
)

select
    league,
    season,
    team_id,
    position,
    played_games,
    won,
    draw,
    lost,
    points,
    goals_for,
    goals_against,
    goal_difference,
    form,
    ingestion_time
from standings_ranked
where rn = 1
```

- [ ] **Step 2: Add docs and column tests**

In `transform/models/silver/_silver.yml`, add a new entry to the `models:` list, after the existing `matches` entry:

```yaml
  - name: standings
    description: "Latest standings snapshot per team from football_data_org (used by gold models). Grain is 1 row/(league, season, team_id) — dedupes stg_football_data_org__standings by taking the row with the newest ingestion_time per team."
    columns:
      - name: team_id
        tests:
          - not_null
      - name: league
        tests:
          - not_null
      - name: season
        tests:
          - not_null
```

- [ ] **Step 3: Add the grain test**

Create `transform/tests/assert_silver_standings_unique_grain.sql`:

```sql
select league, season, team_id, count(*) as n
from {{ ref('standings') }}
group by league, season, team_id
having count(*) > 1
```

- [ ] **Step 4: Build the model**

Run (from `transform/`):
```bash
dbt run --select standings
```
Expected: `Completed successfully`, 1 model run (`standings`), 0 errors.

- [ ] **Step 5: Run the tests and verify they pass**

Run:
```bash
dbt test --select standings assert_silver_standings_unique_grain
```
Expected: all tests `PASS` (the `not_null` tests on `team_id`/`league`/`season`, and `assert_silver_standings_unique_grain` returning 0 rows).

- [ ] **Step 6: Commit**

```bash
git add transform/models/silver/standings.sql transform/models/silver/_silver.yml transform/tests/assert_silver_standings_unique_grain.sql
git commit -m "feat: add silver.standings model deduped to latest row per team"
```

---

### Task 2: Refactor `gold.league_standings` to consume `silver.standings`

**Files:**
- Modify: `transform/models/gold/league_standings.sql`

**Interfaces:**
- Consumes: `ref('standings')` from Task 1 — columns `league, season, team_id, position, played_games, won, draw, lost, points, goals_for, goals_against, goal_difference, form, ingestion_time`.
- Produces: no interface change — `gold.league_standings`'s output columns and grain (`1 row/(league, season, team_id)`) stay identical to before this task; only the internal CTEs change.

- [ ] **Step 1: Replace the football_data_org dedup CTEs with `ref('standings')`**

Replace the full contents of `transform/models/gold/league_standings.sql` with:

```sql
{{ config(materialized='table') }}

with us_standings as (
    select
        *,
        row_number() over (
            partition by league, season, team_id
            order by ingestion_time desc
        ) as rn
    from {{ ref('stg_understat__standings') }}
    where team_id is not null
),

us_latest as (
    select *
    from us_standings
    where rn = 1
)

select
    fd.league,
    fd.season,
    fd.team_id,
    t.team_name,
    t.team_short_name,
    t.team_tla,
    fd.position,
    fd.played_games,
    fd.won,
    fd.draw,
    fd.lost,
    fd.points,
    fd.goals_for,
    fd.goals_against,
    fd.goal_difference,
    fd.form,
    us.xg,
    us.xga,
    us.xpts
from {{ ref('standings') }} fd
join {{ ref('teams') }} t
    on t.team_id = fd.team_id
left join us_latest us
    on us.team_id = fd.team_id
   and us.league = fd.league
   and us.season = fd.season
```

- [ ] **Step 2: Rebuild the full project**

Run (from `transform/`):
```bash
dbt run
```
Expected: `Completed successfully`, all models (`staging`, `silver`, `gold`) run with 0 errors.

- [ ] **Step 3: Run the full test suite and verify no regression**

Run:
```bash
dbt test
```
Expected: all tests `PASS`, including the pre-existing `assert_gold_league_standings_unique_grain` and `assert_gold_team_form_unique_grain` — confirms the refactor didn't change `league_standings`' grain or break the join to `teams`.

- [ ] **Step 4: Spot-check row counts match pre-refactor behavior**

Run (from the repo root; there is no `DATABASE_URL` in the host `.env`, and no host `psql` client is assumed — use the running `postgres` container instead):
```bash
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select count(*) from gold.league_standings;"
```
Expected: same row count as before the refactor (one row per team per league/season currently in `silver.standings`) — sanity check that switching from the inline CTE to `ref('standings')` didn't drop or duplicate rows.

- [ ] **Step 5: Commit**

```bash
git add transform/models/gold/league_standings.sql
git commit -m "refactor: gold.league_standings reads latest standings from silver.standings"
```

---

### Task 3: Snapshot definition and SCD2 integrity test

**Files:**
- Create: `transform/snapshots/snapshot_football_data_org__standings.sql`
- Test: `transform/tests/assert_snapshot_standings_one_current_row.sql`

**Interfaces:**
- Consumes: `ref('standings')` from Task 1.
- Produces: snapshot `snapshot_football_data_org__standings`, referenced as `{{ ref('snapshot_football_data_org__standings') }}`, materialized as a table in the `snapshots` schema. Columns: everything from `silver.standings` plus dbt's standard SCD2 metadata columns `dbt_scd_id, dbt_updated_at, dbt_valid_from, dbt_valid_to`. A row is "current" when `dbt_valid_to is null`.

- [ ] **Step 1: Write the snapshot**

Create `transform/snapshots/snapshot_football_data_org__standings.sql` (if it isn't already present with this exact content — a file with this content may already exist untracked in the working tree from earlier design discussion; verify it matches before reusing it):

```sql
{% snapshot snapshot_football_data_org__standings %}
{{
    config(
      target_schema='snapshots',
      unique_key=['league', 'season', 'team_id'],
      strategy='check',
      check_cols=['position','played_games','won','draw','lost','points',
                  'goals_for','goals_against','goal_difference','form'],
    )
}}
select * from {{ ref('standings') }}
{% endsnapshot %}
```

- [ ] **Step 2: Run the snapshot for the first time**

Run (from `transform/`):
```bash
dbt snapshot --select snapshot_football_data_org__standings
```
Expected: `Completed successfully`, 1 snapshot node inserted. This creates `snapshots.snapshot_football_data_org__standings` and seeds one row per `(league, season, team_id)` with `dbt_valid_from` set to now and `dbt_valid_to` null.

- [ ] **Step 3: Add the SCD2 integrity test**

Create `transform/tests/assert_snapshot_standings_one_current_row.sql`:

```sql
select league, season, team_id, count(*) as n
from {{ ref('snapshot_football_data_org__standings') }}
where dbt_valid_to is null
group by league, season, team_id
having count(*) > 1
```

- [ ] **Step 4: Run the test and verify it passes**

Run:
```bash
dbt test --select assert_snapshot_standings_one_current_row
```
Expected: `PASS` (0 rows returned — exactly one current row per team right after the first snapshot run).

- [ ] **Step 5: Commit**

```bash
git add transform/snapshots/snapshot_football_data_org__standings.sql transform/tests/assert_snapshot_standings_one_current_row.sql
git commit -m "feat: add SCD2 snapshot for football_data_org standings history"
```

---

### Task 4: End-to-end verification that history is preserved

**Files:**
- None committed — this task only touches gitignored raw data under `data/raw/` to simulate a bronze update, and runs queries to confirm the snapshot mechanism works as designed.

**Interfaces:**
- Consumes: the ingestion pipeline (`ingestion/ingest.py`), and every artifact from Tasks 1–3.
- Produces: a verified demonstration — no new interface for other tasks to depend on.

- [ ] **Step 1: Create a simulated "corrected" standings snapshot**

The 2025/2026 season has already finished, so standings won't change from a real re-crawl. Simulate a correction instead: copy the most recent real standings file into a new date folder with one team's points changed.

Create a new dated folder under `data/raw/football_data_org/standings/` (repo-root relative) containing a copy of the most recent real Premier League standings file, with Arsenal's (`team.id == 57`) `points` changed from `85` to `84`. Do this with a small script rather than hand-editing, to avoid JSON syntax mistakes, and to always pick up whichever file is actually the latest at the time this task runs (there may be newer crawls than the one that existed when this plan was written) rather than a hardcoded filename. Run from the repo root:

```bash
python -c "
import glob
import json
import os

candidates = glob.glob('data/raw/football_data_org/standings/*/PL_*.json')
src = max(candidates, key=os.path.getmtime)
dst = 'data/raw/football_data_org/standings/2999-01-01/PL_2025_correction_test.json'
os.makedirs(os.path.dirname(dst), exist_ok=True)
with open(src, encoding='utf-8') as f:
    data = json.load(f)
for row in data['standings'][0]['table']:
    if row['team']['id'] == 57:
        row['points'] = 84
with open(dst, 'w', encoding='utf-8') as f:
    json.dump(data, f)
print('source:', src)
print('wrote:', dst)
"
```
Expected output: two lines, `source: data/raw/football_data_org/standings/<some-date>/PL_....json` and `wrote: data/raw/football_data_org/standings/2999-01-01/PL_2025_correction_test.json`. The `2999-01-01` folder name is deliberately an obviously-fake date, both so it can't collide with a real crawl date and so it's easy to spot and delete in Step 6.

- [ ] **Step 2: Ingest the simulated file**

The host `.env` has no `DATABASE_URL` (only `POSTGRES_DB`/`USER`/`PASSWORD`), so run ingestion through the `ingestion` Docker service, which has `DATABASE_URL` baked into its container environment (per `docker-compose.yml`). `data/` is bind-mounted, so the file from Step 1 is visible to the container without a rebuild.

Run (from repo root):
```bash
docker compose run --rm ingestion --source football_data_org --date 2999-01-01
```
Expected: log output showing 1 new file ingested, 1 new row inserted into `bronze.raw_documents` (new `content_hash` since the payload changed).

- [ ] **Step 3: Rebuild silver/gold and re-run the snapshot**

Run (from `transform/`):
```bash
dbt run --select standings league_standings
dbt snapshot --select snapshot_football_data_org__standings
```
Expected: `standings` and `league_standings` rebuild successfully; the snapshot run reports 1 row **updated** (the closed/old version) and 1 row **inserted** (the new current version) — dbt prints this as part of the snapshot summary (e.g. `INSERT 1, UPDATE 1` or equivalent in the run log).

- [ ] **Step 4: Query and confirm two versions exist for the affected team**

Run:
```bash
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select team_id, points, dbt_valid_from, dbt_valid_to from snapshots.snapshot_football_data_org__standings where team_id = 57 order by dbt_valid_from;"
```
Expected: exactly 2 rows for `team_id = 57` —
- one with `points = 85` and `dbt_valid_to` set (closed, the original version)
- one with `points = 84` and `dbt_valid_to` null (current, the "corrected" version)

This confirms the mentor's requirement: the prior version is preserved and queryable, and a reader can see the current row is an update of an earlier one.

- [ ] **Step 5: Re-run the SCD2 integrity test**

Run (from `transform/`):
```bash
dbt test --select assert_snapshot_standings_one_current_row
```
Expected: `PASS` — even with 2 historical rows for team 57, still exactly one `dbt_valid_to is null` row per key.

- [ ] **Step 6 (optional cleanup): remove the simulated test data**

The simulated file lives under `data/raw/`, which is gitignored, so it was never at risk of being committed. If you want a clean local dataset afterward, delete the folder:
```bash
rm -rf data/raw/football_data_org/standings/2999-01-01
```
The bronze row and the extra snapshot version will remain in Postgres (by design — snapshots are append-only history), which is expected and fine to leave in place.
