# Team Squad + Top Scorer/Assist Widgets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a squad list plus team-scoped top scorer/top assist widgets to the team detail page, and a Top Assists widget (mirroring the existing Top Scorers widget) to the league page.

**Architecture:** Two new/extended read-only FastAPI endpoints over existing `gold.player_profile` / `gold.player_performance` tables (no dbt/gold changes), consumed by two new Next.js Server Components (`SquadTable`, `TopPerformersList`) wired into the existing `teams/[id]` and `leagues/[league]` pages.

**Tech Stack:** FastAPI + psycopg (`dict_row`), Next.js App Router (Server Components, TypeScript), Tailwind + shadcn/ui `Table`.

## Global Constraints

- Design source of truth: [`docs/superpowers/specs/2026-07-29-team-squad-top-performers-design.md`](../specs/2026-07-29-team-squad-top-performers-design.md).
- No dbt/gold schema changes — both features query existing gold tables as-is.
- `gold.player_profile` / `gold.player_performance` are Premier-League-only today (see `docs/gold_data_contract.md`) — Ligue 1 teams must render an empty state, not an error, for squad/top-performer sections.
- Neither backend nor frontend Docker service bind-mounts source (`docker-compose.yml` only mounts `data/`/`logs/`) — after any code edit, verification requires `docker compose build <service>` + `docker compose up -d <service>` before curl/browser checks, per the existing gotcha documented in `CLAUDE.md`.
- No comments explaining *what* code does; only non-obvious *why* (e.g. why an f-string is safe here).
- Backend has no route-level test infra (`backend/tests/` only unit-tests pure functions in `queries.py`, no `TestClient`/DB fixtures) — verification for backend tasks is manual `curl` against the running dev stack, matching existing project practice; do not introduce new test infra as part of this feature.
- Frontend type-check command: `npx tsc --noEmit` (run from `frontend/`).
- Known team ids for manual verification: `57` = Arsenal FC (Premier League, has squad + performance data), `519` = a Ligue 1 team (no squad/performance rows — must return empty, not error).

---

### Task 1: Backend — squad endpoint

**Files:**
- Modify: `backend/routers/teams.py`

**Interfaces:**
- Produces: `GET /api/teams/{team_id}/squad` → `list[PlayerProfile]` (existing schema, no changes). Returns `[]` (HTTP 200) for a team with no squad rows.

- [ ] **Step 1: Add the squad endpoint**

In `backend/routers/teams.py`, change the import line to also bring in `PlayerProfile`:

```python
from schemas import TeamProfile, MatchResult, TeamForm, PlayerProfile
```

Then append this function at the end of the file (after `get_team_form`):

```python
@router.get("/{team_id}/squad", response_model=list[PlayerProfile])
def get_team_squad(team_id: int):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM gold.player_profile
            WHERE team_id = %s
            ORDER BY CASE position
                WHEN 'Goalkeeper' THEN 1
                WHEN 'Defence' THEN 2
                WHEN 'Midfield' THEN 3
                WHEN 'Offence' THEN 4
                ELSE 5
              END,
              shirt_number NULLS LAST
            """,
            (team_id,),
        )
        return cur.fetchall()
```

- [ ] **Step 2: Rebuild and restart the backend container**

Run: `docker compose build backend && docker compose up -d backend`
Expected: build succeeds, container restarts without errors (`docker compose logs backend --tail 20` shows the uvicorn startup line, no traceback).

- [ ] **Step 3: Verify against a Premier League team (Arsenal, team_id 57)**

Run: `curl http://localhost:8000/api/teams/57/squad`
Expected: a JSON array of player objects, ordered goalkeepers first, then defence/midfield/offence, ascending by `shirt_number` within each group.

- [ ] **Step 4: Verify against a Ligue 1 team (team_id 519) returns empty, not an error**

Run: `curl -i http://localhost:8000/api/teams/519/squad`
Expected: `HTTP/1.1 200 OK` with body `[]`.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/teams.py
git commit -m "feat: add GET /api/teams/{team_id}/squad endpoint"
```

---

### Task 2: Backend — team-scoped top scorers + new top assists endpoint

**Files:**
- Modify: `backend/routers/players.py`

**Interfaces:**
- Produces: `GET /api/players/top-scorers` extended with optional `team_id: int` query param, in addition to existing `league`/`limit`.
- Produces: `GET /api/players/top-assists` (new) — same params (`league`, `team_id`, `limit`), `ORDER BY assists DESC`, response `list[PlayerPerformance]` (existing schema).

- [ ] **Step 1: Replace `list_top_scorers` and add `list_top_assists`**

In `backend/routers/players.py`, replace the existing `list_top_scorers` function (lines 9-31) with:

```python
@router.get("/top-scorers", response_model=list[PlayerPerformance])
def list_top_scorers(
    league: str | None = None,
    team_id: int | None = None,
    limit: int = Query(default=10, le=50),
):
    with get_connection() as conn, conn.cursor() as cur:
        # conditions are static strings built from trusted branches below;
        # only the values passed in `params` are interpolated into the query
        conditions = ["goals > 0"]
        params: list = []
        if league:
            conditions.append("league = %s")
            params.append(league)
        if team_id:
            conditions.append("team_id = %s")
            params.append(team_id)
        params.append(limit)
        cur.execute(
            f"""
            SELECT * FROM gold.player_performance
            WHERE {' AND '.join(conditions)}
            ORDER BY goals DESC
            LIMIT %s
            """,
            params,
        )
        return cur.fetchall()


@router.get("/top-assists", response_model=list[PlayerPerformance])
def list_top_assists(
    league: str | None = None,
    team_id: int | None = None,
    limit: int = Query(default=10, le=50),
):
    with get_connection() as conn, conn.cursor() as cur:
        conditions = ["assists > 0"]
        params: list = []
        if league:
            conditions.append("league = %s")
            params.append(league)
        if team_id:
            conditions.append("team_id = %s")
            params.append(team_id)
        params.append(limit)
        cur.execute(
            f"""
            SELECT * FROM gold.player_performance
            WHERE {' AND '.join(conditions)}
            ORDER BY assists DESC
            LIMIT %s
            """,
            params,
        )
        return cur.fetchall()
```

Both new/changed routes stay declared before `get_player`/`{player_id}` (unchanged position in the file), so FastAPI's routing precedence is unaffected.

- [ ] **Step 2: Rebuild and restart the backend container**

Run: `docker compose build backend && docker compose up -d backend`
Expected: build succeeds, no startup errors in `docker compose logs backend --tail 20`.

- [ ] **Step 3: Verify team-scoped top scorers (Arsenal, team_id 57)**

Run: `curl "http://localhost:8000/api/players/top-scorers?team_id=57&limit=5"`
Expected: up to 5 Arsenal players ordered by `goals` descending, all with `goals > 0` (e.g. Viktor Gyökeres first with 14 goals, per current data).

- [ ] **Step 4: Verify the new top-assists endpoint, league-scoped and team-scoped**

Run: `curl "http://localhost:8000/api/players/top-assists?league=premier-league&limit=10"`
Expected: 10 players ordered by `assists` descending, all with `assists > 0`.

Run: `curl "http://localhost:8000/api/players/top-assists?team_id=57&limit=5"`
Expected: up to 5 Arsenal players ordered by `assists` descending (e.g. Bukayo Saka and Declan Rice near the top, per current data).

- [ ] **Step 5: Verify a Ligue 1 team returns empty, not an error**

Run: `curl -i "http://localhost:8000/api/players/top-scorers?team_id=519&limit=5"`
Expected: `HTTP/1.1 200 OK` with body `[]`.

- [ ] **Step 6: Commit**

```bash
git add backend/routers/players.py
git commit -m "feat: add team_id filter to top-scorers, add top-assists endpoint"
```

---

### Task 3: Frontend — API client additions (`lib/api.ts`)

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/app/leagues/[league]/page.tsx:33` (signature-only fix to keep the build green)

**Interfaces:**
- Consumes: `PlayerProfile`, `PlayerPerformance` types (already exported from `frontend/lib/types.ts`, no changes needed there).
- Produces:
  - `getTeamSquad(teamId: number): Promise<PlayerProfile[]>`
  - `getTopScorers(opts?: { league?: string; teamId?: number; limit?: number }): Promise<PlayerPerformance[]>` — **signature change** from the old `getTopScorers(limit?, league?)`.
  - `getTopAssists(opts?: { league?: string; teamId?: number; limit?: number }): Promise<PlayerPerformance[]>` (new, same option shape as `getTopScorers`).

- [ ] **Step 1: Replace `getTopScorers` and add `getTopAssists`/`getTeamSquad`**

In `frontend/lib/api.ts`, replace the existing `getTopScorers` function (lines 55-58) with:

```ts
interface TopPerformersQuery {
  league?: string;
  teamId?: number;
  limit?: number;
}

function buildTopPerformersQuery({ league, teamId, limit = 10 }: TopPerformersQuery): string {
  const params = new URLSearchParams({ limit: String(limit) });
  if (league) params.set("league", league);
  if (teamId) params.set("team_id", String(teamId));
  return `?${params.toString()}`;
}

export function getTopScorers(opts: TopPerformersQuery = {}) {
  return apiFetch<PlayerPerformance[]>(`/api/players/top-scorers${buildTopPerformersQuery(opts)}`);
}

export function getTopAssists(opts: TopPerformersQuery = {}) {
  return apiFetch<PlayerPerformance[]>(`/api/players/top-assists${buildTopPerformersQuery(opts)}`);
}
```

At the end of the file, add:

```ts
export function getTeamSquad(teamId: number) {
  return apiFetch<PlayerProfile[]>(`/api/teams/${teamId}/squad`);
}
```

- [ ] **Step 2: Fix the one existing call site so the build stays green**

In `frontend/app/leagues/[league]/page.tsx:33`, change:

```ts
    getTopScorers(10, league),
```

to:

```ts
    getTopScorers({ limit: 10, league }),
```

- [ ] **Step 3: Type-check**

Run (from `frontend/`): `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts frontend/app/leagues/\[league\]/page.tsx
git commit -m "feat: add getTeamSquad/getTopAssists, generalize getTopScorers to options object"
```

---

### Task 4: Frontend — `TopPerformersList` component + league page Top Assists

**Files:**
- Create: `frontend/components/TopPerformersList.tsx`
- Modify: `frontend/app/leagues/[league]/page.tsx`

**Interfaces:**
- Consumes: `getTopScorers`, `getTopAssists` from `frontend/lib/api.ts` (Task 3); `PlayerPerformance` from `frontend/lib/types.ts`.
- Produces: `TopPerformersList` component, props `{ title: string; players: PlayerPerformance[]; stat: "goals" | "assists"; statLabel: string }` — reused by Task 6 (team page).

- [ ] **Step 1: Create the component**

```tsx
import Link from "next/link";
import type { PlayerPerformance } from "@/lib/types";

export default function TopPerformersList({
  title,
  players,
  stat,
  statLabel,
}: {
  title: string;
  players: PlayerPerformance[];
  stat: "goals" | "assists";
  statLabel: string;
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
                </Link>{" "}
                <span className="text-muted-foreground">({p.team_name})</span>
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

- [ ] **Step 2: Wire it into the league page, add Top Assists**

In `frontend/app/leagues/[league]/page.tsx`:

Replace the import block (lines 1-6) with:

```tsx
import { notFound } from "next/navigation";
import StandingsTable from "@/components/StandingsTable";
import MatchList from "@/components/MatchList";
import SeasonSelect from "@/components/SeasonSelect";
import TopPerformersList from "@/components/TopPerformersList";
import { getLeagues, getLeagueStandings, getLeagueMatches, getTopScorers, getTopAssists } from "@/lib/api";
```

(`Link` is dropped — it was only used inside the inline Top Scorers list, which now lives in `TopPerformersList`.)

Replace the `Promise.all` block (around line 30) with:

```tsx
  const [standings, matches, topScorers, topAssists] = await Promise.all([
    getLeagueStandings(league, season),
    getLeagueMatches(league, season),
    getTopScorers({ limit: 10, league }),
    getTopAssists({ limit: 10, league }),
  ]);
```

Replace the right-hand `<section>` that renders Top Scorers (the `<section>...Top Scorers...</section>` block) with:

```tsx
        <div className="space-y-8">
          <TopPerformersList title="Top Scorers" players={topScorers} stat="goals" statLabel="goals" />
          <TopPerformersList title="Top Assists" players={topAssists} stat="assists" statLabel="assists" />
        </div>
```

- [ ] **Step 3: Type-check**

Run (from `frontend/`): `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Rebuild, restart, and check in the browser**

Run: `docker compose build frontend && docker compose up -d frontend`
Then open `http://localhost:3000/leagues/premier-league` in a browser (or `curl -s http://localhost:3000/leagues/premier-league | grep -o "Top Assists"`).
Expected: page renders with "Top Scorers" and, directly below it in the same right-hand column, a new "Top Assists" list of 10 players.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/TopPerformersList.tsx frontend/app/leagues/\[league\]/page.tsx
git commit -m "feat: extract TopPerformersList component, add Top Assists to league page"
```

---

### Task 5: Frontend — `SquadTable` component

**Files:**
- Create: `frontend/components/SquadTable.tsx`

**Interfaces:**
- Consumes: `PlayerProfile` from `frontend/lib/types.ts`. Assumes the input array is already sorted by the backend (Task 1's `ORDER BY`) — this component only buckets by `position`, it does not re-sort within a bucket.
- Produces: `SquadTable` component, props `{ players: PlayerProfile[] }` — consumed by Task 6 (team page).

- [ ] **Step 1: Create the component**

```tsx
import Link from "next/link";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { PlayerProfile } from "@/lib/types";

const POSITION_GROUPS = ["Goalkeeper", "Defence", "Midfield", "Offence"];

export default function SquadTable({ players }: { players: PlayerProfile[] }) {
  if (players.length === 0) {
    return <p className="text-sm text-muted-foreground">No squad data available.</p>;
  }

  const groups = POSITION_GROUPS.map((group) => ({
    group,
    players: players.filter((p) => p.position === group),
  }));

  const ungrouped = players.filter((p) => !POSITION_GROUPS.includes(p.position ?? ""));
  if (ungrouped.length > 0) {
    groups.push({ group: "Other", players: ungrouped });
  }

  return (
    <div className="space-y-6">
      {groups
        .filter((g) => g.players.length > 0)
        .map(({ group, players: groupPlayers }) => (
          <div key={group}>
            <h3 className="mb-2 text-sm font-semibold text-muted-foreground">{group}</h3>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12">#</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Nationality</TableHead>
                  <TableHead className="text-right">Age</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {groupPlayers.map((p) => (
                  <TableRow key={p.player_id}>
                    <TableCell>{p.shirt_number ?? "—"}</TableCell>
                    <TableCell>
                      <Link href={`/players/${p.player_id}`} className="hover:underline">
                        {p.player_name}
                      </Link>
                    </TableCell>
                    <TableCell>{p.nationality ?? "—"}</TableCell>
                    <TableCell className="text-right">{p.age ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ))}
    </div>
  );
}
```

The `Other` fallback bucket exists because `position` is nullable in `gold.player_profile` (per the data contract) — without it, any player with a null or unrecognized position would silently disappear from the squad view instead of just not being neatly grouped.

- [ ] **Step 2: Type-check**

Run (from `frontend/`): `npx tsc --noEmit`
Expected: no errors. (Component isn't referenced by any page yet, so this only checks it compiles standalone.)

- [ ] **Step 3: Commit**

```bash
git add frontend/components/SquadTable.tsx
git commit -m "feat: add SquadTable component grouped by position"
```

---

### Task 6: Frontend — wire Squad + Top Scorer/Assist into the team page

**Files:**
- Modify: `frontend/app/teams/[id]/page.tsx`

**Interfaces:**
- Consumes: `getTeamSquad`, `getTopScorers`, `getTopAssists` (Task 3), `SquadTable` (Task 5), `TopPerformersList` (Task 4).

- [ ] **Step 1: Rewrite the page**

Replace the full contents of `frontend/app/teams/[id]/page.tsx` with:

```tsx
import TeamFormBadges from "@/components/TeamFormBadges";
import MatchList from "@/components/MatchList";
import SquadTable from "@/components/SquadTable";
import TopPerformersList from "@/components/TopPerformersList";
import {
  getTeam,
  getTeamForm,
  getTeamMatches,
  getTeamSquad,
  getTopScorers,
  getTopAssists,
} from "@/lib/api";

export default async function TeamPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const teamId = Number(id);

  const [team, matches, form, squad, topScorers, topAssists] = await Promise.all([
    getTeam(teamId),
    getTeamMatches(teamId),
    getTeamForm(teamId),
    getTeamSquad(teamId),
    getTopScorers({ teamId, limit: 5 }),
    getTopAssists({ teamId, limit: 5 }),
  ]);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">{team.team_name}</h1>
        <p className="text-sm text-muted-foreground">
          {team.team_tla ?? team.team_short_name ?? ""} · {team.league}
        </p>
      </div>

      {form && (
        <section>
          <h2 className="mb-2 text-xl font-semibold">Form (last 5 matches)</h2>
          <TeamFormBadges form={form.form} />
        </section>
      )}

      <section>
        <h2 className="mb-4 text-xl font-semibold">Squad</h2>
        <SquadTable players={squad} />
      </section>

      <div className="grid gap-8 md:grid-cols-2">
        <TopPerformersList title="Top Scorers" players={topScorers} stat="goals" statLabel="goals" />
        <TopPerformersList title="Top Assists" players={topAssists} stat="assists" statLabel="assists" />
      </div>

      <section>
        <h2 className="mb-4 text-xl font-semibold">Matches</h2>
        <MatchList matches={matches} />
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run (from `frontend/`): `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Rebuild, restart, and check both a Premier League and a Ligue 1 team**

Run: `docker compose build frontend && docker compose up -d frontend`

Open `http://localhost:3000/teams/57` (Arsenal FC).
Expected: "Squad" section shows players grouped under Goalkeeper/Defence/Midfield/Offence headings sorted by shirt number; "Top Scorers"/"Top Assists" show up to 5 players each with real goal/assist counts; Form and Matches sections still render as before.

Open `http://localhost:3000/teams/519` (a Ligue 1 team).
Expected: page loads without error; Squad shows "No squad data available.", Top Scorers/Top Assists each show "No data available." — no crash, no empty white page.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/teams/\[id\]/page.tsx
git commit -m "feat: add squad and team-scoped top scorer/assist sections to team page"
```

---

## Self-Review Notes

- **Spec coverage:** squad endpoint (Task 1), team-scoped top scorer/assist (Tasks 2, 3, 6), league-page Top Assists (Tasks 3, 4) — all spec sections have a covering task.
- **Placeholder scan:** no TBD/"add error handling"/stub steps; every step has runnable code and expected output.
- **Type consistency:** `TopPerformersQuery` (Task 3) is the single shape used identically in `getTopScorers`/`getTopAssists` and consumed the same way in Tasks 4 and 6 (`{ teamId, limit }` / `{ limit, league }`); `TopPerformersList` props (`title`, `players`, `stat`, `statLabel`) are identical across its three call sites (Tasks 4 ×2, Task 6 ×2); `SquadTable`'s `players: PlayerProfile[]` prop matches `getTeamSquad`'s return type exactly.
