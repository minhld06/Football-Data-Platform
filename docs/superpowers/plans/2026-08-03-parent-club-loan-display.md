# Parent Club Loan Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a loaned player's parent (registered) club in the team squad list and on the player's own profile page, e.g. "on loan from Manchester City," derived automatically from an existing team_id mismatch already latent in the pipeline.

**Architecture:** A silver-layer change carries football_data_org's registered `team_id` through every row of `player_team_season` instead of only when it wins as a fallback (Task 1). Both gold player tables derive `parent_team_id`/`parent_team_name`/`is_on_loan` from it (Task 2). The backend exposes the three new fields on `PlayerProfile` only, since both consuming endpoints already share that schema (Task 3). The frontend renders an additive "on loan from X" annotation on the two surfaces the user asked for (Task 4). Task 5 rebuilds containers and verifies end-to-end.

**Tech Stack:** Next.js 16 (frontend), FastAPI + psycopg (backend), dbt-core 1.12 / dbt-postgres 1.11 (transform), PostgreSQL 16.

## Global Constraints

- Spec: [docs/superpowers/specs/2026-08-03-parent-club-loan-display-design.md](../specs/2026-08-03-parent-club-loan-display-design.md) — follow it exactly; do not add scope beyond its four decisions.
- `docs/gold_data_contract.md` must stay in sync with any gold schema change (project-wide rule in `CLAUDE.md`).
- No new crawler or loan/status field — this remains a derived display-layer signal from the existing `team_id` vs `parent_team_id` mismatch, not a new data source.
- Detecting loans to clubs outside the crawl's scope (EPL + Ligue 1) is explicitly out of scope — accepted gap, same root cause as the existing `resolved_via = 'fdo_fallback'` limitation.
- `PlayerPerformance` schema, `/players/{id}/performance`, and the top-scorers/top-assists lists are **not** touched — only `PlayerProfile` (used by the squad list and player profile page) gets the new fields.
- `backend`/`frontend` Docker services `COPY` source at build time (no bind mount) — code edits require `docker compose build <service>` + restart to take effect in the running containers.
- Local dbt runs use `transform/.venv/Scripts/dbt.exe` from the `transform/` directory, with `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` loaded from the repo-root `.env`.
- Postgres container name is `footballdataplatform-postgres-1` (confirmed via `docker compose ps`).

---

## Task 1: Silver — carry `parent_team_id` through `player_team_season`

**Files:**
- Modify: `transform/models/silver/player_team_season.sql:144-164` (final `select`)
- Modify: `transform/models/silver/_silver.yml:74-90` (`player_team_season` description)

**Interfaces:**
- Produces: `silver.player_team_season` gains a `parent_team_id` column — football_data_org's registered `team_id` for this player (from the `players_base` CTE already defined earlier in the same file), present on every row regardless of which source resolved `team_id`. `NULL` whenever `players_base.fdo_team_id` is `NULL` (understat-anchored players, or any Ligue 1 player).

- [ ] **Step 1: Add the `parent_team_id` column to the final select**

Edit `transform/models/silver/player_team_season.sql` — replace the final `select` statement (currently lines 144-164):

```sql
select
    tr.player_id,
    tr.season,
    tr.league,
    tr.team_id,
    tr.resolved_via,
    pb.fdo_team_id as parent_team_id,
    coalesce(d.source_disagreement, false) as source_disagreement,
    us.apps,
    us.minutes,
    us.goals as understat_goals,
    us.assists,
    us.xg,
    us.xa,
    us.xg90,
    us.xa90,
    sb.goals as statbunker_goals
from team_resolved tr
left join players_base pb on pb.player_id = tr.player_id
left join disagreement d on d.player_id = tr.player_id and d.season = tr.season
left join understat_latest us on us.player_id = tr.player_id and us.season = tr.season
left join statbunker_latest sb on sb.player_id = tr.player_id and sb.season = tr.season
```

(Only the new `pb.fdo_team_id as parent_team_id` line and its `left join players_base pb` are added — every other line is unchanged from the current file. `players_base` is defined earlier in this same file (the CTE `select player_id, player_name, team_id as fdo_team_id, league as fdo_league from {{ ref('players') }}`), so no new CTE is needed.)

- [ ] **Step 2: Update the model's yml description**

Edit `transform/models/silver/_silver.yml`, in the `player_team_season` entry (currently lines 74-90), append one sentence to the `description` string, right before the closing quote:

```yaml
  - name: player_team_season
    description: "Which team a player was on, and their stats, for a given season — the season-scoped
                  replacement for trusting football_data_org's undated 'current roster' as if it meant
                  'this season's roster'. Grain is 1 row/(player_id, season). team_id priority per row:
                  understat's team (freshest, correctly attributes loan players to the loan club) →
                  statbunker's team → football_data_org's current team_id as a last-resort fallback
                  (used when a player has zero stats rows with a resolvable team for that season —
                  either no stats rows at all, e.g. an unused third-choice keeper, or rows that
                  exist but all resolved to a NULL team, e.g. a comma-joined mid-season-transfer
                  string). resolved_via records which one won. source_disagreement is true
                  when understat and statbunker both have a row for this player+season but report
                  different teams (a genuine mid-season transfer within one season, distinct from the
                  between-seasons case this model exists to fix) — see
                  assert_player_team_season_source_agreement (warn). Stat columns
                  (apps/minutes/understat_goals/assists/xg/xa/xg90/xa90/statbunker_goals) are carried
                  through directly so gold.player_performance doesn't need to re-derive player_id
                  matching a third time. parent_team_id is football_data_org's registered team_id for
                  this player, carried through on every row (not only when it wins as resolved_via =
                  'fdo_fallback') — used by gold to detect loans when it disagrees with team_id. See
                  docs/superpowers/specs/2026-08-03-parent-club-loan-display-design.md."
    columns:
      - name: player_id
        tests:
          - not_null
      - name: season
        tests:
          - not_null
```

- [ ] **Step 3: Run the model and confirm no failures**

```bash
cd "transform" && export $(grep -E '^POSTGRES_' ../.env | xargs) && ./.venv/Scripts/dbt.exe build --select player_team_season
```
Expected: `player_team_season` model and `assert_player_team_season_unique_grain` / `assert_player_team_season_source_agreement` tests all `PASS` (the source_agreement test is warn-severity and may show pre-existing warnings — that's expected and unrelated to this change).

- [ ] **Step 4: Spot-check `parent_team_id` in psql**

```bash
docker exec footballdataplatform-postgres-1 psql -U postgres -d football -c "select player_id, season, team_id, parent_team_id, resolved_via from silver.player_team_season where team_id is distinct from parent_team_id and parent_team_id is not null limit 10;"
```
Expected: zero or more rows. If any are returned, each one is a candidate in-scope loan — note a `player_id` to re-check in Task 2's spot-check.

- [ ] **Step 5: Commit**

```bash
git add transform/models/silver/player_team_season.sql transform/models/silver/_silver.yml
git commit -m "feat: carry football_data_org's registered team_id through player_team_season"
```

---

## Task 2: Gold — derive `is_on_loan` and `parent_team_name` in both player tables

**Files:**
- Modify: `transform/models/gold/player_performance.sql`
- Modify: `transform/models/gold/player_profile.sql`
- Modify: `transform/models/gold/_gold.yml:33-69` (`player_profile` and `player_performance` descriptions)
- Create: `transform/tests/assert_is_on_loan_consistent.sql`
- Modify: `docs/gold_data_contract.md` (column tables and "Known limitations" bullets for both `gold.player_profile`, currently around lines 112-153, and `gold.player_performance`, currently around lines 180-219)

**Interfaces:**
- Consumes: `silver.player_team_season.parent_team_id` (from Task 1).
- Produces: both `gold.player_profile` and `gold.player_performance` gain `parent_team_id` (int, nullable), `parent_team_name` (text, nullable), `is_on_loan` (boolean, not null, `false` when nothing to compare).

- [ ] **Step 1: Add the three columns to `gold/player_performance.sql`**

Edit `transform/models/gold/player_performance.sql` — replace the whole file:

```sql
{{ config(materialized='table') }}

select
    pts.player_id,
    p.player_name,
    pts.season,
    pts.team_id,
    t.team_name,
    pts.league,
    pts.resolved_via,
    pts.parent_team_id,
    pt.team_name as parent_team_name,
    (pts.parent_team_id is not null and pts.team_id is distinct from pts.parent_team_id) as is_on_loan,
    pts.statbunker_goals as goals,
    pts.assists,
    pts.apps,
    pts.minutes,
    pts.xg,
    pts.xa,
    pts.xg90,
    pts.xa90
from {{ ref('player_team_season') }} pts
join {{ ref('players') }} p on p.player_id = pts.player_id
left join {{ ref('teams') }} t on t.team_id = pts.team_id
left join {{ ref('teams') }} pt on pt.team_id = pts.parent_team_id
```

- [ ] **Step 2: Add the same three columns to `gold/player_profile.sql`**

Edit `transform/models/gold/player_profile.sql` — replace the whole file:

```sql
{{ config(materialized='view') }}

with latest_team as (
    select distinct on (player_id)
        player_id, team_id, league, parent_team_id
    from {{ ref('player_team_season') }}
    order by player_id, season desc
)

select
    p.player_id,
    p.player_name,
    p.position,
    p.nationality,
    p.date_of_birth,
    date_part('year', age(current_date, p.date_of_birth))::int as age,
    p.shirt_number,
    lt.team_id,
    t.team_name,
    lt.parent_team_id,
    pt.team_name as parent_team_name,
    (lt.parent_team_id is not null and lt.team_id is distinct from lt.parent_team_id) as is_on_loan,
    coalesce(lt.league, p.league) as league
from {{ ref('players') }} p
left join latest_team lt on lt.player_id = p.player_id
left join {{ ref('teams') }} t on t.team_id = lt.team_id
left join {{ ref('teams') }} pt on pt.team_id = lt.parent_team_id
```

- [ ] **Step 3: Create the consistency test**

Create `transform/tests/assert_is_on_loan_consistent.sql`:

```sql
select player_id, season, team_id, parent_team_id, is_on_loan
from {{ ref('player_performance') }}
where is_on_loan
  and (parent_team_id is null or team_id = parent_team_id)
```

- [ ] **Step 4: Update `gold/_gold.yml`'s `player_profile` and `player_performance` descriptions**

Edit `transform/models/gold/_gold.yml`, replace the `player_profile` and `player_performance` entries (currently lines 33-69):

```yaml
  - name: player_profile
    description: "One row per player: identity + a convenience 'most recent season's team' (not a
                  season-scoped fact — see gold.player_performance for that). Grain is 1 row/player_id.
                  Logic: player identity from silver.players, team_id/team_name/league from the
                  player's latest row in silver.player_team_season (max(season)). parent_team_id/
                  parent_team_name are football_data_org's registered club, carried through the same
                  way; is_on_loan is true only when both team_id and parent_team_id are non-null and
                  differ (false, not NULL, when parent_team_id is NULL — nothing to compare against).
                  See docs/superpowers/specs/2026-08-03-parent-club-loan-display-design.md.
                  Materialized as a view (not table like other gold models) so age stays correct at
                  query time instead of going stale between dbt builds.
                  "
    columns:
      - name: player_id
        tests:
          - unique
          - not_null

  - name: player_performance
    description: "Player stats: goals (statbunker) + assists/apps/minutes/xG/xA (understat), with the
                  team they were attributed to *for that season* (from silver.player_team_season).
                  Grain is 1 row/(player_id, season) — changed from 1 row/player_id so a player's team
                  can differ correctly between seasons (and, for the same season, be a loan club
                  rather than football_data_org's parent-club roster). See
                  assert_gold_player_performance_unique_grain.sql for the grain test (a dedicated file,
                  unlike player_profile's single-column grain, because this grain is composite).
                  resolved_via ('understat'/'statbunker'/'fdo_fallback') records how team_id was
                  resolved — GET /teams/{id}/squad filters out 'fdo_fallback' rows so a player with
                  zero stats rows this season (whether an unused bench player or someone loaned to a
                  club outside the crawl's scope, e.g. Championship — both present identically as
                  zero rows) doesn't appear in the squad list under their parent club. See
                  docs/superpowers/specs/2026-08-03-squad-display-fixes-design.md.
                  parent_team_id/parent_team_name/is_on_loan surface the same 'registered vs match-day
                  club' comparison as player_profile above, at season grain; see
                  assert_is_on_loan_consistent.sql and
                  docs/superpowers/specs/2026-08-03-parent-club-loan-display-design.md.
                  "
    columns:
      - name: player_id
        tests:
          - not_null
      - name: season
        tests:
          - not_null
```

- [ ] **Step 5: Run the affected models and the new test**

```bash
cd "transform" && export $(grep -E '^POSTGRES_' ../.env | xargs) && ./.venv/Scripts/dbt.exe build --select player_performance player_profile assert_is_on_loan_consistent
```
Expected: `player_performance` and `player_profile` models `PASS`; `assert_is_on_loan_consistent` `PASS` (0 rows returned); `assert_gold_player_performance_unique_grain` and `player_profile`'s `unique`/`not_null` tests on `player_id` also `PASS` (no grain change).

- [ ] **Step 6: Spot-check `is_on_loan` in psql**

```bash
docker exec footballdataplatform-postgres-1 psql -U postgres -d football -c "select player_name, team_name, parent_team_name, is_on_loan from gold.player_performance where is_on_loan limit 20;"
```
Expected: zero or more rows; every returned row has `team_name` different from `parent_team_name`. If Task 1 Step 4 found a candidate `player_id`, confirm it appears here with `is_on_loan = true`.

```bash
docker exec footballdataplatform-postgres-1 psql -U postgres -d football -c "select player_name, team_name, parent_team_name, is_on_loan from gold.player_profile where player_name ilike '%phillips%';"
```
Expected: the known out-of-scope-loan example from the squad-display-fixes design (if still present in current data) shows `is_on_loan = false` — confirms the accepted gap, not a regression.

- [ ] **Step 7: Update `docs/gold_data_contract.md`**

Edit `docs/gold_data_contract.md` — in the `gold.player_profile` column table, insert two new rows after the existing `team_name` row and before the `league` row (currently between lines 122 and 123):

```
| `parent_team_id` | int | football_data_org's registered/current squad team_id for this player, independent of which club they're actually playing for this season (see `silver.player_team_season.parent_team_id`) | Yes — `NULL` whenever football_data_org has no squad row for this player (understat-anchored players, or any Ligue 1 player — football_data_org's squad crawl is Premier-League-only) |
| `parent_team_name` | text | Full team name for `parent_team_id`, from `silver.teams` | Yes — same condition as `parent_team_id` |
| `is_on_loan` | boolean | `true` when `team_id` and `parent_team_id` are both non-null and differ — the player's match-day club disagrees with their football_data_org registration | No — `false` (not `NULL`) whenever `parent_team_id` is `NULL`, since there's nothing to compare against |
```

Add a new bullet to that table's "Known limitations" list (after the existing `team_id` display-convenience bullet, currently ending around line 133):

```
- **`is_on_loan`/`parent_team_id` only detect in-scope loans.** A loan to a
  club outside the crawl's scope (e.g. Championship) produces zero
  Understat/StatBunker rows, so `team_id` falls back to the same value as
  `parent_team_id` — no mismatch, `is_on_loan` stays `false`. Same root
  cause as the `resolved_via = 'fdo_fallback'` gap documented under
  `gold.player_performance` below. See
  docs/superpowers/specs/2026-08-03-parent-club-loan-display-design.md.
```

In the `gold.player_performance` column table, insert the same two rows after `team_name` and before `league` (currently between lines 186 and 187):

```
| `parent_team_id` | int | football_data_org's registered/current squad team_id for this player (see `silver.player_team_season.parent_team_id`) | Yes — same condition as `gold.player_profile.parent_team_id` |
| `parent_team_name` | text | Full team name for `parent_team_id`, from `silver.teams` | Yes — same condition as `parent_team_id` |
| `is_on_loan` | boolean | `true` when `team_id` and `parent_team_id` are both non-null and differ, for this specific season | No — `false` when `parent_team_id` is `NULL` |
```

Add a bullet to that table's "Known limitations" list (near the existing `fdo_fallback` bullet, currently ending around line 210):

```
- **`is_on_loan` shares the same detection gap as the `fdo_fallback` filter
  above** — an out-of-scope loan can't be distinguished from "still at the
  registered club" using data this platform crawls. See
  docs/superpowers/specs/2026-08-03-parent-club-loan-display-design.md.
```

- [ ] **Step 8: Commit**

```bash
git add transform/models/gold/player_performance.sql transform/models/gold/player_profile.sql transform/models/gold/_gold.yml transform/tests/assert_is_on_loan_consistent.sql docs/gold_data_contract.md
git commit -m "feat: derive is_on_loan and parent club columns in gold player tables"
```

---

## Task 3: Backend — surface the new fields on `PlayerProfile`

**Files:**
- Modify: `backend/schemas.py:75-85` (`PlayerProfile`)
- Modify: `backend/routers/teams.py:56-84` (`get_team_squad`)

**Interfaces:**
- Consumes: `gold.player_profile.{parent_team_id,parent_team_name,is_on_loan}`, `gold.player_performance.{parent_team_id,parent_team_name,is_on_loan}` (from Task 2).
- Produces: `PlayerProfile` gains `parent_team_id: Optional[int]`, `parent_team_name: Optional[str]`, `is_on_loan: bool`.

- [ ] **Step 1: Add the three fields to `PlayerProfile`**

Edit `backend/schemas.py`, replace the `PlayerProfile` class (currently lines 75-85):

```python
class PlayerProfile(BaseModel):
    player_id: int
    player_name: str
    position: Optional[str] = None
    nationality: Optional[str] = None
    date_of_birth: Optional[date] = None
    age: Optional[int] = None
    shirt_number: Optional[int] = None
    team_id: Optional[int] = None
    team_name: Optional[str] = None
    parent_team_id: Optional[int] = None
    parent_team_name: Optional[str] = None
    is_on_loan: bool = False
    league: str
```

(`/players/{player_id}` in `backend/routers/players.py` does `SELECT * FROM gold.player_profile` already — no change needed there; the new gold columns pass straight through once the schema declares them.)

- [ ] **Step 2: Add the three fields to the squad query's explicit SELECT list**

Edit `backend/routers/teams.py`, replace the `get_team_squad` function (currently lines 56-84):

```python
@router.get("/{team_id}/squad", response_model=list[PlayerProfile])
def get_team_squad(team_id: int, season: str | None = None):
    with get_connection() as conn, conn.cursor() as cur:
        query = """
            SELECT pp.player_id, pp.player_name, pp.position, pp.nationality,
                   pp.date_of_birth, pp.age, pp.shirt_number,
                   perf.team_id, perf.team_name, perf.league,
                   perf.parent_team_id, perf.parent_team_name, perf.is_on_loan
            FROM gold.player_performance perf
            JOIN gold.player_profile pp ON pp.player_id = perf.player_id
            WHERE perf.team_id = %s
              AND perf.season = %s
              AND perf.resolved_via <> 'fdo_fallback'
            ORDER BY CASE pp.position
                WHEN 'Goalkeeper' THEN 1
                WHEN 'Defence' THEN 2
                WHEN 'Midfield' THEN 3
                WHEN 'Offence' THEN 4
                ELSE 5
              END,
              pp.shirt_number NULLS LAST
        """
        if season:
            cur.execute(query, (team_id, season))
        else:
            cur.execute(
                "SELECT max(season) FROM gold.player_performance"
            )
            latest_season = cur.fetchone()["max"]
            cur.execute(query, (team_id, latest_season))
        return cur.fetchall()
```

(Only the added `perf.parent_team_id, perf.parent_team_name, perf.is_on_loan` in the SELECT list changes — the squad list intentionally sources `is_on_loan` from `gold.player_performance`, the season-scoped table, not `gold.player_profile`, since the squad is already filtered to one `season`.)

- [ ] **Step 3: Run the existing backend test suite as a regression check**

```bash
cd "backend" && python -m pytest tests/ -v
```
Expected: all existing tests still `PASS` — this task adds no new pure-function logic (`queries.py` untouched), only schema fields and a SELECT list, so no new unit tests are needed; this is a regression check only.

- [ ] **Step 4: Commit**

```bash
git add backend/schemas.py backend/routers/teams.py
git commit -m "feat: surface parent club and loan status on PlayerProfile"
```

---

## Task 4: Frontend — render the "on loan from X" annotation

**Files:**
- Modify: `frontend/lib/types.ts:69-80` (`PlayerProfile` interface)
- Modify: `frontend/components/SquadTable.tsx:51-62` (name cell)
- Modify: `frontend/app/players/[id]/page.tsx:35-40` (header subtitle)

**Interfaces:**
- Consumes: `PlayerProfile.{parent_team_id,parent_team_name,is_on_loan}` (from Task 3).

- [ ] **Step 1: Add the three fields to the `PlayerProfile` interface**

Edit `frontend/lib/types.ts`, replace the `PlayerProfile` interface (currently lines 69-80):

```ts
export interface PlayerProfile {
  player_id: number;
  player_name: string;
  position: string | null;
  nationality: string | null;
  date_of_birth: string | null;
  age: number | null;
  shirt_number: number | null;
  team_id: number | null;
  team_name: string | null;
  parent_team_id: number | null;
  parent_team_name: string | null;
  is_on_loan: boolean;
  league: string;
}
```

- [ ] **Step 2: Annotate the squad table's name cell**

Edit `frontend/components/SquadTable.tsx`, replace the `<TableCell>` containing the player name link (currently lines 54-58, inside the row-mapping block):

```tsx
                    <TableCell>
                      <Link href={`/players/${p.player_id}`} className="hover:underline">
                        {p.player_name}
                      </Link>
                      {p.is_on_loan && (
                        <p className="text-xs text-muted-foreground">
                          On loan from {p.parent_team_name}
                        </p>
                      )}
                    </TableCell>
```

- [ ] **Step 3: Annotate the player profile page's subtitle**

Edit `frontend/app/players/[id]/page.tsx`, replace the subtitle `<p>` (currently lines 37-39):

```tsx
        <p className="text-sm text-muted-foreground">
          {player.position ?? "—"} · {player.team_name ?? "—"}
          {player.is_on_loan && ` (on loan from ${player.parent_team_name})`} ·{" "}
          {player.league}
        </p>
```

- [ ] **Step 4: Type-check the frontend**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors (or the same set of pre-existing errors as before this change — do not introduce new ones).

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/types.ts frontend/components/SquadTable.tsx frontend/app/players/\[id\]/page.tsx
git commit -m "feat: show on-loan annotation in squad list and player page"
```

---

## Task 5: Rebuild containers and verify end-to-end

**Files:** none (integration/verification only — no new file changes).

**Interfaces:** none produced; consumes the deliverables of Tasks 1-4.

- [ ] **Step 1: Rebuild the backend and frontend images**

```bash
docker compose build backend frontend
```
Expected: both images build successfully. Required because these Dockerfiles `COPY` source at build time — the running containers are still on the pre-change code until rebuilt.

- [ ] **Step 2: Restart the services with the new images**

```bash
docker compose up -d backend frontend
```
Expected: `docker compose ps` shows both `footballdataplatform-backend` and `footballdataplatform-frontend` as `Up`.

- [ ] **Step 3: Verify the API directly for a known loan case (if one exists)**

Using a `player_id` found on-loan in Task 2 Step 6 (or any Premier League team_id if none were found):

```bash
curl -s "http://localhost:8000/api/players/{player_id}" | python -m json.tool
```
Expected: response includes `"is_on_loan": true`, `"parent_team_id"`, and `"parent_team_name"` set to the registered club, different from `"team_name"`.

```bash
curl -s "http://localhost:8000/api/teams/{loan_club_team_id}/squad" | python -c "import json,sys; data=json.load(sys.stdin); print([p for p in data if p['is_on_loan']])"
```
Expected: the same player appears with `is_on_loan: true` in their current (loan) club's squad response.

- [ ] **Step 4: Verify in the browser**

Open `http://localhost:3000/teams/{loan_club_team_id}` — the on-loan player's row in the squad table shows a small "On loan from {parent club}" line under their name; every other player's row is unchanged.

Open `http://localhost:3000/players/{player_id}` for that same player — the subtitle reads "{position} · {current club} (on loan from {parent club}) · {league}".

Open a few ordinary (non-loaned) players' squad rows and profile pages — confirm no annotation appears and nothing else changed.

- [ ] **Step 5: Confirm no regressions in the existing backend test suite**

```bash
cd "backend" && python -m pytest tests/ -v
```
Expected: all existing tests still `PASS`.
