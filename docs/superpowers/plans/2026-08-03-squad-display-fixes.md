# Squad Display Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three team-page display issues: redundant club name next to top scorer/assist entries, understat-only players landing in the squad's "Other" position group, and loaned-out (out-of-scope) players still appearing in their parent club's squad.

**Architecture:** Three independent fixes layered on the existing medallion pipeline: a frontend-only prop change (Task 1), a dbt staging/silver backfill using a new normalization macro (Task 2), and a dbt gold-column + backend filter change (Task 3). Task 4 rebuilds the Docker services and verifies all three end-to-end.

**Tech Stack:** Next.js 16 (frontend), FastAPI + psycopg (backend), dbt-core 1.12 / dbt-postgres 1.11 (transform), PostgreSQL 16.

## Global Constraints

- Spec: [docs/superpowers/specs/2026-08-03-squad-display-fixes-design.md](../specs/2026-08-03-squad-display-fixes-design.md) — follow it exactly; do not add scope beyond its three decisions.
- `docs/gold_data_contract.md` must stay in sync with any gold schema change (project-wide rule in `CLAUDE.md`).
- No new crawler or loan/status field — Decision 3 is a display-layer proxy using existing `resolved_via`, not a new data source.
- `backend`/`frontend` Docker services `COPY` source at build time (no bind mount) — code edits require `docker compose build <service>` + restart to take effect in the running containers, per `CLAUDE.md`'s documented gotcha.
- Local dbt runs use `transform/.venv/Scripts/dbt.exe` from the `transform/` directory, with `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` loaded from the repo-root `.env` (confirmed working via `dbt debug` — `DBT_HOST` defaults to `localhost`, correct since Postgres's 5432 is published to the host).

---

## Task 1: Frontend — hide club name on the team page's top-performer lists

**Files:**
- Modify: `frontend/components/TopPerformersList.tsx:4-40`
- Modify: `frontend/app/teams/[id]/page.tsx:53-54`

**Interfaces:**
- Produces: `TopPerformersList` gains an optional prop `showTeamName?: boolean` (default `true`, preserving current behavior everywhere it's not explicitly set to `false`).

- [ ] **Step 1: Add the `showTeamName` prop and make the club-name span conditional**

Edit `frontend/components/TopPerformersList.tsx` — replace the whole file:

```tsx
import Link from "next/link";
import type { PlayerPerformance } from "@/lib/types";

export default function TopPerformersList({
  title,
  players,
  stat,
  statLabel,
  showTeamName = true,
}: {
  title: string;
  players: PlayerPerformance[];
  stat: "goals" | "assists";
  statLabel: string;
  showTeamName?: boolean;
}) {
  return (
    <section>
      <h2 className="mb-4 text-xl font-semibold">{title}</h2>
      {players.length === 0 ? (
        <p className="text-sm text-muted-foreground">No data available.</p>
      ) : (
        <ol className="space-y-2">
          {players.map((p, i) => (
            <li key={p.player_id} className="flex items-center justify-between text-sm">
              <span>
                {i + 1}.{" "}
                <Link href={`/players/${p.player_id}`} className="hover:underline">
                  {p.player_name}
                </Link>
                {showTeamName && (
                  <>
                    {" "}
                    <span className="text-muted-foreground">({p.team_name})</span>
                  </>
                )}
              </span>
              <span className="font-semibold">
                {p[stat] ?? 0} {statLabel}
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
```

- [ ] **Step 2: Pass `showTeamName={false}` from the team page**

Edit `frontend/app/teams/[id]/page.tsx`, replace lines 52-55:

```tsx
      <div className="grid gap-8 md:grid-cols-2">
        <TopPerformersList title="Top Scorers" players={topScorers} stat="goals" statLabel="goals" showTeamName={false} />
        <TopPerformersList title="Top Assists" players={topAssists} stat="assists" statLabel="assists" showTeamName={false} />
      </div>
```

- [ ] **Step 3: Type-check the frontend**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors (or the same set of pre-existing errors as before this change — do not introduce new ones).

- [ ] **Step 4: Commit**

```bash
git add frontend/components/TopPerformersList.tsx frontend/app/teams/\[id\]/page.tsx
git commit -m "fix: hide redundant club name in team page top scorer/assist lists"
```

(Manual browser verification of this task happens together with Tasks 2-3 in Task 4, since the frontend container needs a rebuild regardless.)

---

## Task 2: dbt — backfill `position` for understat-anchored players

**Files:**
- Create: `transform/macros/normalize_understat_position.sql`
- Modify: `transform/models/staging/stg_understat__player_stats.sql`
- Modify: `transform/models/staging/_staging.yml:73-86`
- Modify: `transform/models/silver/players.sql`
- Modify: `transform/models/silver/_silver.yml:49-59`
- Modify: `docs/gold_data_contract.md` (the `position` row and "Known limitations" list under `gold.player_profile`, currently around lines 116 and 134-138)

**Interfaces:**
- Produces: `normalize_understat_position(column_name)` — a dbt macro returning a SQL `CASE` expression that maps Understat's raw `position` string (e.g. `"D M S"`) to one of `'Goalkeeper'`/`'Defence'`/`'Midfield'`/`'Offence'`, or `NULL` if unresolvable.
- Produces: `stg_understat__player_stats` gains a `position` column (already-normalized, one of the 4 values or `NULL`).
- Consumes (Task 3 doesn't touch this, listed for completeness): none from other tasks.

- [ ] **Step 1: Create the normalization macro**

Create `transform/macros/normalize_understat_position.sql`:

```sql
{% macro normalize_understat_position(column_name) %}
    case
        when {{ column_name }} is null then null
        when {{ column_name }} ~ '^GK' then 'Goalkeeper'
        when {{ column_name }} ~ '^D' then 'Defence'
        when {{ column_name }} ~ '^M' then 'Midfield'
        when {{ column_name }} ~ '^F' then 'Offence'
        else null
    end
{% endmacro %}
```

- [ ] **Step 2: Extract and normalize `position` in the staging model**

Edit `transform/models/staging/stg_understat__player_stats.sql` — in the `resolved_team` CTE, add the raw position field, and in the final `select`, add the normalized column:

```sql
with player_stats_raw as (
    select season, league, ingestion_time, payload
    from {{ source('bronze', 'raw_documents') }}
    where source = 'understat'
      and entity_type = 'player_stats'
),

player_stats_rows as (
    select
        season,
        league,
        ingestion_time,
        jsonb_array_elements(payload) as row_json
    from player_stats_raw
),

resolved_team as (
    select
        r.season,
        r.league,
        r.ingestion_time,
        r.row_json ->> 'player_name' as raw_player_name,
        (r.row_json ->> 'id')::int as understat_id,
        m.team_id,
        (r.row_json ->> 'games')::int as apps,
        (r.row_json ->> 'time')::int as minutes,
        (r.row_json ->> 'goals')::int as goals,
        (r.row_json ->> 'assists')::int as assists,
        (r.row_json ->> 'xG')::numeric as xg,
        (r.row_json ->> 'xA')::numeric as xa,
        r.row_json ->> 'position' as raw_position
    from player_stats_rows r
    left join {{ ref('team_name_map') }} m
        on m.source = 'understat'
       and m.raw_team_name = r.row_json ->> 'team_title'
)

select
    rt.season,
    rt.league,
    rt.ingestion_time,
    rt.team_id,
    rt.raw_player_name,
    rt.understat_id,
    rt.apps,
    rt.minutes,
    rt.goals,
    rt.assists,
    rt.xg,
    rt.xa,
    -- Understat's JSON endpoint gives season totals only, not the per-90
    -- rates its own on-page table computes client-side — derive them the
    -- same way: xG / (minutes / 90). NULL when minutes is 0 (no minutes played).
    round(rt.xg / nullif(rt.minutes, 0)::numeric * 90, 3) as xg90,
    round(rt.xa / nullif(rt.minutes, 0)::numeric * 90, 3) as xa90,
    {{ normalize_understat_position('rt.raw_position') }} as position
from resolved_team rt
```

- [ ] **Step 3: Update the staging model's yml description**

Edit `transform/models/staging/_staging.yml`, in the `stg_understat__player_stats` entry (lines 73-86), append one sentence to the `description` string, right before the closing quote:

```yaml
  - name: stg_understat__player_stats
    description: "Staging model for Understat player stats, fetched from Understat's own JSON data
                  endpoint (getLeagueData/{league}/{season}) rather than scraped from the on-page
                  table — that table is client-side paginated at 10 rows/page (~50+ pages for a full
                  league), so the endpoint is used directly to get the full roster in one response.
                  xg90/xa90 are derived (xg / (minutes/90)) since the endpoint doesn't return them
                  directly. Grain is 1 row/player/snapshot. team_id resolution is via team_name_map.csv
                  (NULL if unmapped, or if the row's team_title is a comma-joined mid-season-transfer
                  string that intentionally fails the join — see docs/gold_data_contract.md).
                  understat_id is Understat's own native numeric player id, passed through unchanged —
                  used by silver.players to anchor identity for players football_data_org has no row
                  for. This model no longer resolves player_id itself (moved to
                  silver/player_team_season.sql, which depends on silver.players and would create a
                  circular ref if this model tried to depend on it too). position is normalized via
                  normalize_understat_position() from Understat's own multi-tag position string (e.g.
                  'D M S') into football_data_org's 4-value vocabulary, or NULL if the raw string is
                  just 'S' (substitute-only, no primary position recorded)."
```

- [ ] **Step 4: Propagate `position` through `silver/players.sql`'s understat CTEs**

Edit `transform/models/silver/players.sql` — replace the whole file:

```sql
{{ config(materialized='table') }}

with fdo_ranked as (
    select
        *,
        row_number() over (
            partition by player_id
            order by ingestion_time desc
        ) as rn
    from {{ ref('stg_football_data_org__players') }}
    where player_id is not null
),

fdo_deduped as (
    select * from fdo_ranked where rn = 1
),

fdo_players as (
    select
        fdo_deduped.player_id,
        coalesce(overrides.display_name, fdo_deduped.player_name) as player_name,
        fdo_deduped.player_name as raw_fdo_player_name,
        fdo_deduped.position,
        fdo_deduped.date_of_birth,
        fdo_deduped.nationality,
        fdo_deduped.shirt_number,
        fdo_deduped.team_id,
        fdo_deduped.league,
        fdo_deduped.ingestion_time
    from fdo_deduped
    left join {{ ref('player_display_name_overrides') }} as overrides
        on overrides.player_id = fdo_deduped.player_id
),

understat_ranked as (
    select
        *,
        row_number() over (
            partition by understat_id
            order by ingestion_time desc
        ) as rn
    from {{ ref('stg_understat__player_stats') }}
    where understat_id is not null
),

understat_distinct as (
    select
        raw_player_name,
        understat_id,
        team_id,
        league,
        position,
        ingestion_time
    from understat_ranked
    where rn = 1
),

understat_matched_to_fdo as (
    select
        u.raw_player_name,
        u.understat_id,
        u.league,
        u.position,
        u.ingestion_time,
        coalesce(pm.player_id, f.player_id) as fdo_match_id
    from understat_distinct u
    left join {{ ref('player_name_map') }} pm
        on pm.source = 'understat'
       and pm.raw_player_name = u.raw_player_name
       and pm.team_id = u.team_id
    left join fdo_players f
        on {{ normalize_player_name('f.raw_fdo_player_name') }} = {{ normalize_player_name('u.raw_player_name') }}
),

understat_only as (
    select
        understat_id + 100000000 as player_id,
        raw_player_name as player_name,
        position,
        cast(null as date) as date_of_birth,
        cast(null as text) as nationality,
        cast(null as int) as shirt_number,
        cast(null as int) as team_id,
        league,
        ingestion_time
    from understat_matched_to_fdo
    where fdo_match_id is null
)

select player_id, player_name, position, date_of_birth, nationality, shirt_number, team_id, league, ingestion_time
from fdo_players
union all
select player_id, player_name, position, date_of_birth, nationality, shirt_number, team_id, league, ingestion_time
from understat_only
```

(Only the `understat_distinct`, `understat_matched_to_fdo`, and `understat_only` CTEs changed — `fdo_players` and the final `union all` select list are unchanged from the current file, reproduced here in full only because the plan format requires complete file contents.)

- [ ] **Step 5: Update `silver/players.sql`'s yml description**

Edit `transform/models/silver/_silver.yml`, in the `players` entry (lines 49-59), replace the `description` string:

```yaml
  - name: players
    description: "Player identity. Grain is 1 row/player_id. player_id is either football_data_org's
                  own numeric id (for the ~588 players it covers), or understat's native player id
                  + a fixed 100000000 offset for players understat knows about but football_data_org
                  has zero row for (e.g. Mohamed Salah) — see
                  docs/superpowers/specs/2026-08-03-player-identity-season-team-design.md. Dedup
                  between the two sources is by normalize_player_name() against football_data_org's
                  raw (pre-display-name-override) name, plus player_name_map.csv for exceptions.
                  Understat-anchored rows have NULL date_of_birth/nationality/shirt_number/team_id —
                  football_data_org is the only source with those bio fields, and team_id is now
                  resolved per-season in silver.player_team_season, not stored here. position is the
                  exception: understat-anchored rows get position backfilled from Understat's own
                  position tag via normalize_understat_position() (see
                  docs/superpowers/specs/2026-08-03-squad-display-fixes-design.md), so it's only NULL
                  for understat-anchored players whose raw tag was just 'S' (substitute-only, no
                  primary position recorded)."
    columns:
      - name: player_id
        tests:
          - unique
          - not_null
      - name: player_name
        tests:
          - not_null
```

- [ ] **Step 6: Run the affected models and confirm no failures**

```bash
cd "transform" && export $(grep -E '^POSTGRES_' ../.env | xargs) && ./.venv/Scripts/dbt.exe build --select stg_understat__player_stats players player_team_season player_profile player_performance
```
Expected: all models and tests `PASS` (0 `ERROR`, 0 unexpected `FAIL` — `assert_player_names_mapped` / `assert_player_team_season_source_agreement` are warn-severity and may show pre-existing warnings, that's expected per the spec they reference).

- [ ] **Step 7: Spot-check the backfill in psql**

```bash
docker exec footballdataplatform-postgres-1 psql -U postgres -d football -c "select player_id, player_name, position from gold.player_profile where player_id > 100000000 and position is not null limit 10;"
```
Expected: at least one row returned, `position` populated with one of `Goalkeeper`/`Defence`/`Midfield`/`Offence`.

- [ ] **Step 8: Update `docs/gold_data_contract.md`**

Edit `docs/gold_data_contract.md` — in the `gold.player_profile` table, update the `position` row (currently line 116):

Old:
```
| `position` | text | Playing position as reported by football_data_org — exactly one of `Goalkeeper`, `Defence`, `Midfield`, `Offence` | Yes — always `NULL` for understat-anchored players (football_data_org is the only source with this field) |
```
New:
```
| `position` | text | Playing position — one of `Goalkeeper`, `Defence`, `Midfield`, `Offence`. From football_data_org when a row exists there; backfilled from Understat's own position tag (via `normalize_understat_position()`) for understat-anchored players | Yes — `NULL` only for understat-anchored players whose raw Understat tag is bare `S` (substitute-only, no primary position recorded) |
```

And update the "Known limitations" bullet about bio fields (currently around lines 134-138):

Old:
```
- **understat-anchored players (no football_data_org row) have `NULL`
  bio fields.** `position`/`date_of_birth`/`nationality`/`shirt_number` are
  only ever populated from football_data_org — there's no seed backfilling
  them today (a `player_extra_info.csv` seed was discussed for this, not
  built).
```
New:
```
- **understat-anchored players (no football_data_org row) have `NULL`
  `date_of_birth`/`nationality`/`shirt_number`.** These three are only ever
  populated from football_data_org — there's no seed backfilling them today
  (a `player_extra_info.csv` seed was discussed for this, not built).
  `position` is the exception: it's backfilled from Understat's own position
  tag for these players (see
  `docs/superpowers/specs/2026-08-03-squad-display-fixes-design.md`), so it's
  only `NULL` when Understat's raw tag is bare `S`.
```

- [ ] **Step 9: Commit**

```bash
git add transform/macros/normalize_understat_position.sql transform/models/staging/stg_understat__player_stats.sql transform/models/staging/_staging.yml transform/models/silver/players.sql transform/models/silver/_silver.yml docs/gold_data_contract.md
git commit -m "feat: backfill player position from Understat for understat-anchored players"
```

---

## Task 3: dbt + backend — exclude fallback-only players from the squad list

**Files:**
- Modify: `transform/models/gold/player_performance.sql`
- Modify: `transform/models/gold/_gold.yml:47-55`
- Modify: `backend/routers/teams.py:56-84`
- Modify: `docs/gold_data_contract.md` (the `gold.player_performance` table and its "Freshness" prose, currently around lines 168-189)

**Interfaces:**
- Consumes: `silver.player_team_season.resolved_via` (existing column, values `'understat'`/`'statbunker'`/`'fdo_fallback'` — already built, confirmed present).
- Produces: `gold.player_performance` gains a `resolved_via` column (not exposed in the `PlayerPerformance` Pydantic schema — FastAPI's `response_model` drops undeclared fields from `SELECT *` rows automatically, confirmed by reading `backend/schemas.py` and the three call sites in `backend/routers/players.py` that already do `SELECT * FROM gold.player_performance`).

- [ ] **Step 1: Expose `resolved_via` in `gold.player_performance`**

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
```

- [ ] **Step 2: Update `gold/_gold.yml`'s `player_performance` description**

Edit `transform/models/gold/_gold.yml`, in the `player_performance` entry (lines 47-55), replace the `description` string:

```yaml
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
                  "
    columns:
      - name: player_id
        tests:
          - not_null
      - name: season
        tests:
          - not_null
```

- [ ] **Step 3: Run the affected model and confirm no failures**

```bash
cd "transform" && export $(grep -E '^POSTGRES_' ../.env | xargs) && ./.venv/Scripts/dbt.exe build --select player_performance
```
Expected: `player_performance` model and `assert_gold_player_performance_unique_grain` test both `PASS`.

- [ ] **Step 4: Spot-check `resolved_via` in psql**

```bash
docker exec footballdataplatform-postgres-1 psql -U postgres -d football -c "select player_name, team_name, resolved_via from gold.player_performance where resolved_via = 'fdo_fallback' limit 10;"
```
Expected: zero or more rows; if any exist, note one `player_name` to re-check after Step 6 confirms it's excluded from that player's team's squad response.

- [ ] **Step 5: Filter the squad query by `resolved_via`**

Edit `backend/routers/teams.py`, replace the `get_team_squad` function (lines 56-84):

```python
@router.get("/{team_id}/squad", response_model=list[PlayerProfile])
def get_team_squad(team_id: int, season: str | None = None):
    with get_connection() as conn, conn.cursor() as cur:
        query = """
            SELECT pp.player_id, pp.player_name, pp.position, pp.nationality,
                   pp.date_of_birth, pp.age, pp.shirt_number,
                   perf.team_id, perf.team_name, perf.league
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

(Only the added `AND perf.resolved_via <> 'fdo_fallback'` line changes; the rest of the function is unchanged from the current file, reproduced in full because the plan format requires complete file contents for any modified function.)

- [ ] **Step 6: Update `docs/gold_data_contract.md`'s `gold.player_performance` section**

Edit `docs/gold_data_contract.md` — add a new row to the `gold.player_performance` column table (after the existing `league` row, before `goals`):

```
| `resolved_via` | text | Which source resolved `team_id` for this player+season: `understat`, `statbunker`, or `fdo_fallback` | No |
```

And append a new bullet to that table's surrounding prose (near the existing "Freshness" paragraph, currently around lines 168-175):

```
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
```

- [ ] **Step 7: Commit**

```bash
git add transform/models/gold/player_performance.sql transform/models/gold/_gold.yml backend/routers/teams.py docs/gold_data_contract.md
git commit -m "fix: exclude fdo_fallback-only players from team squad list"
```

---

## Task 4: Rebuild containers and verify all three fixes end-to-end

**Files:** none (integration/verification only — no new file changes).

**Interfaces:** none produced; consumes the deliverables of Tasks 1-3.

- [ ] **Step 1: Rebuild the backend and frontend images**

```bash
docker compose build backend frontend
```
Expected: both images build successfully (no errors). Required because these Dockerfiles `COPY` source at build time — the running containers are still on the pre-change code until rebuilt.

- [ ] **Step 2: Restart the services with the new images**

```bash
docker compose up -d backend frontend
```
Expected: `docker compose ps` shows both `footballdataplatform-backend` and `footballdataplatform-frontend` as `Up`.

- [ ] **Step 3: Verify the squad-filter fix via the API directly**

Pick a team_id known (from Step 4 of Task 3) to have had a `fdo_fallback` player, or any Premier League team_id if none were found:

```bash
curl -s "http://localhost:8000/api/teams/{team_id}/squad" | python -c "import json,sys; data=json.load(sys.stdin); print(len(data)); print([p['player_name'] for p in data])"
```
Expected: if a `fdo_fallback` player existed for this team in Task 3 Step 4, their name is absent from this list.

- [ ] **Step 4: Verify all three fixes in the browser**

Open `http://localhost:3000/teams/{team_id}` for a Premier League team:
- Top Scorers / Top Assists entries show only the player name, no `(club name)` suffix.
- Squad table's "Other" position group is empty or much smaller than before (spot-check against the pre-fix screenshot/count if available).
- If this team had a known `fdo_fallback` player, they no longer appear in the squad table.

Open `http://localhost:3000/leagues/{league}` (e.g. `premier-league`):
- Top Scorers / Top Assists entries still show `(club name)` — unaffected, confirming `showTeamName` defaulting to `true` there.

- [ ] **Step 5: Confirm no regressions in the existing backend test suite**

```bash
cd "backend" && python -m pytest tests/ -v
```
Expected: all existing tests still `PASS` (this task introduces no new Python helper functions, so no new tests are added — this is a regression check only, matching the precedent set in `docs/superpowers/specs/2026-07-29-team-squad-top-performers-design.md`'s Testing section).
