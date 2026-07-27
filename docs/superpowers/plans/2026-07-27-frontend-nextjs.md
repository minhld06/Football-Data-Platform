# Frontend (Next.js v1) Implementation Plan

> **For the student:** This plan is written to be executed by hand — copy each
> code block into the file path shown, then run the verification command
> before moving to the next task. Same mode as the Tuần 7+8 backend plan: you
> paste and understand every file yourself, no automated subagent execution.

**Goal:** Build a Next.js frontend with the roadmap's 5 minimum pages (home,
league, team, player, search), calling the existing FastAPI backend as a
separate service, plus the 3 new backend endpoints those pages need.

**Architecture:** Next.js App Router, every page a Server Component that
calls `lib/api.ts` fetch helpers directly against the FastAPI backend — no
client-side data-fetching library. The only Client Components are the
season dropdown and the search box, which just update the URL and let the
Server Component re-fetch. UI built from shadcn/ui primitives on Tailwind.

**Tech Stack:** Next.js 15 (App Router, TypeScript), Tailwind CSS, shadcn/ui,
FastAPI (existing `backend/`, extended with 3 endpoints).

Design spec: [2026-07-27-frontend-nextjs-design.md](../specs/2026-07-27-frontend-nextjs-design.md).

## Global Constraints

- Frontend does no direct DB access — every data read goes through the
  FastAPI backend over HTTP.
- Server Components only for data fetching (plain `fetch`, `cache: "no-store"`)
  — no SWR/React Query. Client Components (`"use client"`) only where user
  interaction requires it (season dropdown, search box).
- Reuse existing Pydantic schemas for the 3 new backend endpoints — no new
  gold models, no new response shapes.
- `API_URL` is a **server-only** env var (no `NEXT_PUBLIC_` prefix) — all
  fetches happen in Server Components, never in the browser.
- In Docker, the frontend reaches the backend via the service name
  `http://backend:8000`, not `localhost` — same gotcha already documented in
  `CLAUDE.md` for other services.
- Read-only, no auth — matches the backend's existing scope.
- `docs/ai-prompts.md` is out of scope (explicit user choice carried over
  from the backend build — do not create it).

---

## Task 1: Backend — 3 new endpoints (`matches/recent`, `leagues/{league}/matches`, `players/top-scorers`)

**Files:**
- Modify: `backend/routers/matches.py`
- Modify: `backend/routers/leagues.py`
- Modify: `backend/routers/players.py`

**Interfaces:**
- Consumes: `get_connection` from `backend/db.py`; `MatchResult`,
  `PlayerPerformance` from `backend/schemas.py`; `_resolve_season` (already
  defined in `leagues.py`).
- Produces: `GET /api/matches/recent`, `GET /api/leagues/{league}/matches`,
  `GET /api/players/top-scorers` — consumed by the frontend starting Task 3.

- [ ] **Step 1: Rewrite `backend/routers/matches.py`** — add `list_recent_matches`, registered before `get_match` so the route table reads top-to-bottom in specificity order

```python
from fastapi import APIRouter, HTTPException, Query

from db import get_connection
from schemas import MatchResult

router = APIRouter()


@router.get("/recent", response_model=list[MatchResult])
def list_recent_matches(league: str | None = None, limit: int = Query(default=10, le=50)):
    with get_connection() as conn, conn.cursor() as cur:
        if league:
            cur.execute(
                """
                SELECT * FROM gold.match_results
                WHERE status = 'FINISHED' AND league = %s
                ORDER BY utc_date DESC
                LIMIT %s
                """,
                (league, limit),
            )
        else:
            cur.execute(
                """
                SELECT * FROM gold.match_results
                WHERE status = 'FINISHED'
                ORDER BY utc_date DESC
                LIMIT %s
                """,
                (limit,),
            )
        return cur.fetchall()


@router.get("/{match_id}", response_model=MatchResult)
def get_match(match_id: int):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM gold.match_results WHERE source_match_id = %s", (match_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Match {match_id} not found")
        return row
```

- [ ] **Step 2: Add `list_league_matches` to `backend/routers/leagues.py`** — insert after `get_league_standings` (end of file)

```python
@router.get("/{league}/matches", response_model=list[MatchResult])
def list_league_matches(league: str, season: str | None = None):
    with get_connection() as conn, conn.cursor() as cur:
        resolved_season = _resolve_season(cur, league, season)
        if resolved_season is None:
            raise HTTPException(status_code=404, detail=f"League '{league}' not found")

        cur.execute(
            "SELECT * FROM gold.match_results WHERE league = %s AND season = %s ORDER BY utc_date",
            (league, resolved_season),
        )
        return cur.fetchall()
```

Also update the import line at the top of `backend/routers/leagues.py` to include `MatchResult`:

```python
from schemas import LeagueSummary, TeamSummary, LeagueStanding, MatchResult
```

- [ ] **Step 3: Rewrite `backend/routers/players.py`** — add `list_top_scorers`, registered before `get_player`

```python
from fastapi import APIRouter, HTTPException, Query

from db import get_connection
from schemas import PlayerProfile, PlayerPerformance

router = APIRouter()


@router.get("/top-scorers", response_model=list[PlayerPerformance])
def list_top_scorers(league: str | None = None, limit: int = Query(default=10, le=50)):
    with get_connection() as conn, conn.cursor() as cur:
        if league:
            cur.execute(
                """
                SELECT * FROM gold.player_performance
                WHERE league = %s
                ORDER BY goals DESC NULLS LAST
                LIMIT %s
                """,
                (league, limit),
            )
        else:
            cur.execute(
                """
                SELECT * FROM gold.player_performance
                ORDER BY goals DESC NULLS LAST
                LIMIT %s
                """,
                (limit,),
            )
        return cur.fetchall()


@router.get("/{player_id}", response_model=PlayerProfile)
def get_player(player_id: int):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM gold.player_profile WHERE player_id = %s", (player_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Player {player_id} not found")
        return row


@router.get("/{player_id}/performance", response_model=PlayerPerformance)
def get_player_performance(player_id: int):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM gold.player_performance WHERE player_id = %s", (player_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Player {player_id} not found")
        return row
```

- [ ] **Step 4: Start the backend and verify manually**

```powershell
cd backend
python -m uvicorn main:app --reload --port 8000
```

```powershell
curl "http://localhost:8000/api/matches/recent?limit=3"
curl "http://localhost:8000/api/leagues/premier-league/matches?season=2024-2025"
curl "http://localhost:8000/api/players/top-scorers?limit=3"
curl "http://localhost:8000/api/players/top-scorers?league=ligue-1"
```

Expected: first three return `200` with non-empty JSON arrays (adjust
`season` to a real value from your DB if `2024-2025` doesn't match). The last
call (`league=ligue-1`) is expected to return `[]` — known limitation,
`gold.player_performance` is Premier-League-only.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/matches.py backend/routers/leagues.py backend/routers/players.py
git commit -m "feat: add recent-matches, league-matches, and top-scorers endpoints"
```

---

## Task 2: Frontend project scaffold

**Files:**
- Create: `frontend/` (via `create-next-app`)
- Create: `frontend/.env.local` (not committed — see `.gitignore` check below)
- Create: `frontend/.env.local.example`

- [ ] **Step 1: Scaffold the Next.js project from the repo root**

```powershell
npx create-next-app@latest frontend --typescript --tailwind --eslint --app --no-src-dir --import-alias "@/*" --use-npm --turbopack
```

If prompted for anything not covered by these flags, accept the default
(press Enter).

- [ ] **Step 2: Initialize shadcn/ui**

```powershell
cd frontend
npx shadcn@latest init -d
```

- [ ] **Step 3: Add the components this project needs**

```powershell
npx shadcn@latest add card table badge select input button -y
```

Expected: `components/ui/card.tsx`, `table.tsx`, `badge.tsx`, `select.tsx`,
`input.tsx`, `button.tsx` now exist under `frontend/components/ui/`.

- [ ] **Step 4: Create `frontend/.env.local.example`**

```
API_URL=http://localhost:8000
```

- [ ] **Step 5: Create `frontend/.env.local`** (same content — this is your local dev value, not committed)

```
API_URL=http://localhost:8000
```

- [ ] **Step 6: Confirm `.env.local` is gitignored** — `create-next-app` already includes `.env*.local` in the generated `frontend/.gitignore`; verify it:

```powershell
cd frontend
git check-ignore -v .env.local
```

Expected: prints a match against `.env*.local` in `frontend/.gitignore`. If it prints nothing, add `.env*.local` to `frontend/.gitignore` before continuing.

- [ ] **Step 7: Verify the scaffold runs**

```powershell
npm run dev
```

Open `http://localhost:3000` in a browser — expect the default Next.js
starter page. Stop the server (Ctrl+C) once confirmed.

- [ ] **Step 8: Commit**

```bash
cd ..
git add frontend
git commit -m "feat: scaffold Next.js frontend with shadcn/ui"
```

---

## Task 3: Data layer — `lib/types.ts` and `lib/api.ts`

**Files:**
- Create: `frontend/lib/types.ts`
- Create: `frontend/lib/api.ts`

**Interfaces:**
- Produces (types): `LeagueSummary`, `TeamSummary`, `TeamProfile`,
  `LeagueStanding`, `TeamForm`, `MatchResult`, `PlayerProfile`,
  `PlayerPerformance`, `SearchResult`.
- Produces (functions): `getLeagues()`, `getLeagueStandings(league, season?)`,
  `getLeagueMatches(league, season?)`, `getRecentMatches(limit?)`,
  `getTopScorers(limit?)`, `getTeam(teamId)`, `getTeamMatches(teamId)`,
  `getTeamForm(teamId)`, `getPlayer(playerId)`,
  `getPlayerPerformance(playerId)`, `search(q)` — every later page task
  imports from here.

- [ ] **Step 1: Create `frontend/lib/types.ts`**

```typescript
export interface LeagueSummary {
  league: string;
  seasons: string[];
}

export interface TeamSummary {
  team_id: number;
  team_name: string;
  team_short_name: string | null;
  team_tla: string | null;
}

export interface TeamProfile extends TeamSummary {
  league: string;
}

export interface LeagueStanding {
  league: string;
  season: string;
  team_id: number;
  team_name: string;
  team_short_name: string | null;
  team_tla: string | null;
  position: number;
  played_games: number;
  won: number;
  draw: number;
  lost: number;
  points: number;
  goals_for: number;
  goals_against: number;
  goal_difference: number;
  form: string | null;
  xg: number | null;
  xga: number | null;
  xpts: number | null;
}

export interface TeamForm {
  league: string;
  season: string;
  team_id: number;
  team_name: string;
  matches_played: number;
  wins: number;
  draws: number;
  losses: number;
  points: number;
  goals_for: number;
  goals_against: number;
  form: string;
}

export interface MatchResult {
  source_match_id: number;
  league: string;
  season: string;
  matchday: number | null;
  status: string;
  utc_date: string;
  home_team_id: number;
  home_team_name: string | null;
  away_team_id: number;
  away_team_name: string | null;
  home_score: number | null;
  away_score: number | null;
}

export interface PlayerProfile {
  player_id: number;
  player_name: string;
  position: string | null;
  nationality: string | null;
  date_of_birth: string | null;
  age: number | null;
  shirt_number: number | null;
  team_id: number;
  team_name: string | null;
  league: string;
}

export interface PlayerPerformance {
  player_id: number;
  player_name: string;
  team_id: number;
  team_name: string | null;
  league: string;
  goals: number | null;
  assists: number | null;
  apps: number | null;
  minutes: number | null;
  xg: number | null;
  xa: number | null;
  xg90: number | null;
  xa90: number | null;
}

export interface SearchResult {
  type: "team" | "player";
  id: number;
  name: string;
  subtitle: string | null;
}
```

- [ ] **Step 2: Create `frontend/lib/api.ts`**

```typescript
import { notFound } from "next/navigation";
import type {
  LeagueSummary,
  TeamProfile,
  LeagueStanding,
  TeamForm,
  MatchResult,
  PlayerProfile,
  PlayerPerformance,
  SearchResult,
} from "./types";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (res.status === 404) {
    notFound();
  }
  if (!res.ok) {
    throw new Error(`Backend request failed: ${res.status} ${path}`);
  }
  return res.json() as Promise<T>;
}

async function apiFetchOptional<T>(path: string): Promise<T | null> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (res.status === 404) {
    return null;
  }
  if (!res.ok) {
    throw new Error(`Backend request failed: ${res.status} ${path}`);
  }
  return res.json() as Promise<T>;
}

export function getLeagues() {
  return apiFetch<LeagueSummary[]>("/api/leagues");
}

export function getLeagueStandings(league: string, season?: string) {
  const query = season ? `?season=${encodeURIComponent(season)}` : "";
  return apiFetch<LeagueStanding[]>(`/api/leagues/${league}/standings${query}`);
}

export function getLeagueMatches(league: string, season?: string) {
  const query = season ? `?season=${encodeURIComponent(season)}` : "";
  return apiFetch<MatchResult[]>(`/api/leagues/${league}/matches${query}`);
}

export function getRecentMatches(limit = 5) {
  return apiFetch<MatchResult[]>(`/api/matches/recent?limit=${limit}`);
}

export function getTopScorers(limit = 5) {
  return apiFetch<PlayerPerformance[]>(`/api/players/top-scorers?limit=${limit}`);
}

export function getTeam(teamId: number) {
  return apiFetch<TeamProfile>(`/api/teams/${teamId}`);
}

export function getTeamMatches(teamId: number) {
  return apiFetch<MatchResult[]>(`/api/teams/${teamId}/matches`);
}

export function getTeamForm(teamId: number) {
  return apiFetchOptional<TeamForm>(`/api/teams/${teamId}/form`);
}

export function getPlayer(playerId: number) {
  return apiFetch<PlayerProfile>(`/api/players/${playerId}`);
}

export function getPlayerPerformance(playerId: number) {
  return apiFetch<PlayerPerformance>(`/api/players/${playerId}/performance`);
}

export function search(q: string) {
  return apiFetch<SearchResult[]>(`/api/search?q=${encodeURIComponent(q)}`);
}
```

- [ ] **Step 3: Verify it compiles**

```powershell
cd frontend
npx tsc --noEmit
```

Expected: no errors (unused-export warnings are not errors and are fine —
these functions are consumed starting Task 4).

- [ ] **Step 4: Commit**

```bash
cd ..
git add frontend/lib
git commit -m "feat: add typed API client for backend endpoints"
```

---

## Task 4: Layout, Navbar, and Home page

**Files:**
- Modify: `frontend/app/layout.tsx`
- Create: `frontend/components/Navbar.tsx`
- Create: `frontend/components/LeagueCard.tsx`
- Create: `frontend/components/MatchList.tsx`
- Modify: `frontend/app/page.tsx`

**Interfaces:**
- Consumes: `getLeagues`, `getRecentMatches`, `getTopScorers` from
  `lib/api.ts`; `LeagueSummary`, `MatchResult` from `lib/types.ts`; shadcn
  `Card`/`CardHeader`/`CardTitle`/`CardContent` from `components/ui/card`.
- Produces: `<MatchList matches={MatchResult[]} />` — reused by Task 5 and
  Task 6.

- [ ] **Step 1: Replace `frontend/app/layout.tsx`**

```tsx
import type { Metadata } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";

export const metadata: Metadata = {
  title: "Football Data Platform",
  description:
    "Bảng xếp hạng, đội bóng, cầu thủ và trận đấu từ Premier League và Ligue 1",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="vi">
      <body className="min-h-screen bg-background text-foreground antialiased">
        <Navbar />
        <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
```

- [ ] **Step 2: Create `frontend/components/Navbar.tsx`**

```tsx
import Link from "next/link";

export default function Navbar() {
  return (
    <header className="border-b">
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
        <Link href="/" className="text-lg font-semibold">
          Football Data Platform
        </Link>
        <div className="flex gap-4 text-sm">
          <Link href="/" className="hover:underline">
            Trang chủ
          </Link>
          <Link href="/search" className="hover:underline">
            Tìm kiếm
          </Link>
        </div>
      </nav>
    </header>
  );
}
```

- [ ] **Step 3: Create `frontend/components/LeagueCard.tsx`**

```tsx
import Link from "next/link";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import type { LeagueSummary } from "@/lib/types";

const LEAGUE_LABELS: Record<string, string> = {
  "premier-league": "Premier League",
  "ligue-1": "Ligue 1",
};

export default function LeagueCard({ league }: { league: LeagueSummary }) {
  const label = LEAGUE_LABELS[league.league] ?? league.league;
  return (
    <Link href={`/leagues/${league.league}`}>
      <Card className="transition hover:border-primary">
        <CardHeader>
          <CardTitle>{label}</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          {league.seasons.length} mùa giải có dữ liệu · mới nhất: {league.seasons[0]}
        </CardContent>
      </Card>
    </Link>
  );
}
```

- [ ] **Step 4: Create `frontend/components/MatchList.tsx`**

```tsx
import Link from "next/link";
import type { MatchResult } from "@/lib/types";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function MatchList({ matches }: { matches: MatchResult[] }) {
  if (matches.length === 0) {
    return <p className="text-sm text-muted-foreground">Không có trận đấu nào.</p>;
  }

  return (
    <ul className="divide-y">
      {matches.map((m) => (
        <li key={m.source_match_id} className="flex items-center justify-between py-3 text-sm">
          <div className="flex items-center gap-2">
            <Link href={`/teams/${m.home_team_id}`} className="hover:underline">
              {m.home_team_name ?? m.home_team_id}
            </Link>
            <span className="font-medium">
              {m.home_score ?? "-"} : {m.away_score ?? "-"}
            </span>
            <Link href={`/teams/${m.away_team_id}`} className="hover:underline">
              {m.away_team_name ?? m.away_team_id}
            </Link>
          </div>
          <span className="text-muted-foreground">{formatDate(m.utc_date)}</span>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 5: Replace `frontend/app/page.tsx`**

```tsx
import LeagueCard from "@/components/LeagueCard";
import MatchList from "@/components/MatchList";
import { getLeagues, getRecentMatches, getTopScorers } from "@/lib/api";

export default async function HomePage() {
  const [leagues, recentMatches, topScorers] = await Promise.all([
    getLeagues(),
    getRecentMatches(5),
    getTopScorers(5),
  ]);

  return (
    <div className="space-y-10">
      <section>
        <h1 className="mb-4 text-2xl font-bold">Giải đấu</h1>
        <div className="grid gap-4 sm:grid-cols-2">
          {leagues.map((league) => (
            <LeagueCard key={league.league} league={league} />
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-4 text-xl font-semibold">Trận đấu gần đây</h2>
        <MatchList matches={recentMatches} />
      </section>

      <section>
        <h2 className="mb-4 text-xl font-semibold">Top ghi bàn</h2>
        {topScorers.length === 0 ? (
          <p className="text-sm text-muted-foreground">Chưa có dữ liệu.</p>
        ) : (
          <ol className="space-y-2">
            {topScorers.map((p, i) => (
              <li key={p.player_id} className="flex items-center justify-between text-sm">
                <span>
                  {i + 1}. {p.player_name}{" "}
                  <span className="text-muted-foreground">({p.team_name})</span>
                </span>
                <span className="font-semibold">{p.goals ?? 0} bàn</span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
```

- [ ] **Step 6: Run the dev server (backend must also be running from Task 1) and verify in a browser**

```powershell
cd frontend
npm run dev
```

Open `http://localhost:3000`. Expected: league cards, a "Trận đấu gần đây"
list, and a "Top ghi bàn" list all render with real data (not empty, unless
your DB genuinely has none).

- [ ] **Step 7: Commit**

```bash
cd ..
git add frontend/app/layout.tsx frontend/app/page.tsx frontend/components/Navbar.tsx frontend/components/LeagueCard.tsx frontend/components/MatchList.tsx
git commit -m "feat: add home page with leagues, recent matches, top scorers"
```

---

## Task 5: League page — standings, fixtures, season selector

**Files:**
- Create: `frontend/components/StandingsTable.tsx`
- Create: `frontend/components/SeasonSelect.tsx`
- Create: `frontend/app/leagues/[league]/page.tsx`

**Interfaces:**
- Consumes: `getLeagues`, `getLeagueStandings`, `getLeagueMatches` from
  `lib/api.ts`; `LeagueStanding` from `lib/types.ts`; `MatchList` from Task 4;
  shadcn `Table`/`Select` primitives.

- [ ] **Step 1: Create `frontend/components/StandingsTable.tsx`**

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
import type { LeagueStanding } from "@/lib/types";

export default function StandingsTable({ standings }: { standings: LeagueStanding[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>#</TableHead>
          <TableHead>Đội</TableHead>
          <TableHead className="text-right">Trận</TableHead>
          <TableHead className="text-right">T</TableHead>
          <TableHead className="text-right">H</TableHead>
          <TableHead className="text-right">B</TableHead>
          <TableHead className="text-right">HS</TableHead>
          <TableHead className="text-right">Điểm</TableHead>
          <TableHead className="text-right">xG</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {standings.map((row) => (
          <TableRow key={row.team_id}>
            <TableCell>{row.position}</TableCell>
            <TableCell>
              <Link href={`/teams/${row.team_id}`} className="hover:underline">
                {row.team_name}
              </Link>
            </TableCell>
            <TableCell className="text-right">{row.played_games}</TableCell>
            <TableCell className="text-right">{row.won}</TableCell>
            <TableCell className="text-right">{row.draw}</TableCell>
            <TableCell className="text-right">{row.lost}</TableCell>
            <TableCell className="text-right">{row.goal_difference}</TableCell>
            <TableCell className="text-right font-semibold">{row.points}</TableCell>
            <TableCell className="text-right text-muted-foreground">
              {row.xg !== null ? row.xg.toFixed(1) : "—"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
```

- [ ] **Step 2: Create `frontend/components/SeasonSelect.tsx`**

```tsx
"use client";

import { useRouter, useSearchParams } from "next/navigation";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export default function SeasonSelect({
  league,
  seasons,
  currentSeason,
}: {
  league: string;
  seasons: string[];
  currentSeason: string;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();

  function handleChange(season: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("season", season);
    router.push(`/leagues/${league}?${params.toString()}`);
  }

  return (
    <Select value={currentSeason} onValueChange={handleChange}>
      <SelectTrigger className="w-40">
        <SelectValue placeholder="Mùa giải" />
      </SelectTrigger>
      <SelectContent>
        {seasons.map((s) => (
          <SelectItem key={s} value={s}>
            {s}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
```

- [ ] **Step 3: Create `frontend/app/leagues/[league]/page.tsx`**

```tsx
import { notFound } from "next/navigation";
import StandingsTable from "@/components/StandingsTable";
import MatchList from "@/components/MatchList";
import SeasonSelect from "@/components/SeasonSelect";
import { getLeagues, getLeagueStandings, getLeagueMatches } from "@/lib/api";

const LEAGUE_LABELS: Record<string, string> = {
  "premier-league": "Premier League",
  "ligue-1": "Ligue 1",
};

export default async function LeaguePage({
  params,
  searchParams,
}: {
  params: Promise<{ league: string }>;
  searchParams: Promise<{ season?: string }>;
}) {
  const { league } = await params;
  const { season: seasonParam } = await searchParams;

  const leagues = await getLeagues();
  const leagueInfo = leagues.find((l) => l.league === league);
  if (!leagueInfo) {
    notFound();
  }

  const season = seasonParam ?? leagueInfo.seasons[0];
  const [standings, matches] = await Promise.all([
    getLeagueStandings(league, season),
    getLeagueMatches(league, season),
  ]);

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{LEAGUE_LABELS[league] ?? league}</h1>
        <SeasonSelect league={league} seasons={leagueInfo.seasons} currentSeason={season} />
      </div>

      <section>
        <h2 className="mb-4 text-xl font-semibold">Bảng xếp hạng</h2>
        <StandingsTable standings={standings} />
      </section>

      <section>
        <h2 className="mb-4 text-xl font-semibold">Lịch thi đấu</h2>
        <MatchList matches={matches} />
      </section>
    </div>
  );
}
```

- [ ] **Step 4: Verify in a browser**

```powershell
cd frontend
npm run dev
```

Open `http://localhost:3000/leagues/premier-league`. Expected: standings
table, fixture list, and a season dropdown that navigates to
`?season=...` and re-renders both sections. Also check
`http://localhost:3000/leagues/not-a-real-league` renders the Next.js
not-found page (built from Task 9 — until then it'll be the default Next.js
404).

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/components/StandingsTable.tsx frontend/components/SeasonSelect.tsx frontend/app/leagues
git commit -m "feat: add league standings and fixtures page"
```

---

## Task 6: Team detail page

**Files:**
- Create: `frontend/components/TeamFormBadges.tsx`
- Create: `frontend/app/teams/[id]/page.tsx`

**Interfaces:**
- Consumes: `getTeam`, `getTeamMatches`, `getTeamForm` from `lib/api.ts`;
  `MatchList` from Task 4; shadcn `Badge`.

- [ ] **Step 1: Create `frontend/components/TeamFormBadges.tsx`**

```tsx
import { Badge } from "@/components/ui/badge";

const VARIANT: Record<string, string> = {
  W: "bg-green-600 hover:bg-green-600",
  D: "bg-gray-400 hover:bg-gray-400",
  L: "bg-red-600 hover:bg-red-600",
};

export default function TeamFormBadges({ form }: { form: string }) {
  return (
    <div className="flex gap-1">
      {form.split("").map((letter, i) => (
        <Badge key={i} className={`${VARIANT[letter] ?? ""} text-white`}>
          {letter}
        </Badge>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Create `frontend/app/teams/[id]/page.tsx`**

```tsx
import TeamFormBadges from "@/components/TeamFormBadges";
import MatchList from "@/components/MatchList";
import { getTeam, getTeamForm, getTeamMatches } from "@/lib/api";

export default async function TeamPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const teamId = Number(id);

  const [team, matches, form] = await Promise.all([
    getTeam(teamId),
    getTeamMatches(teamId),
    getTeamForm(teamId),
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
          <h2 className="mb-2 text-xl font-semibold">Phong độ 5 trận gần nhất</h2>
          <TeamFormBadges form={form.form} />
        </section>
      )}

      <section>
        <h2 className="mb-4 text-xl font-semibold">Các trận đấu</h2>
        <MatchList matches={matches} />
      </section>
    </div>
  );
}
```

- [ ] **Step 3: Verify in a browser** — use a real `team_id` (e.g. from the
  standings table you just viewed, click a team name link)

Open `http://localhost:3000/teams/<a real team_id>`. Expected: team name,
form badges (if data exists), match list. Also test an invalid id, e.g.
`http://localhost:3000/teams/999999` — expected 404 page.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/TeamFormBadges.tsx frontend/app/teams
git commit -m "feat: add team detail page"
```

---

## Task 7: Player detail page

**Files:**
- Create: `frontend/app/players/[id]/page.tsx`

**Interfaces:**
- Consumes: `getPlayer`, `getPlayerPerformance` from `lib/api.ts`.

- [ ] **Step 1: Create `frontend/app/players/[id]/page.tsx`**

```tsx
import { getPlayer, getPlayerPerformance } from "@/lib/api";

function stat(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${value}`;
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-lg font-semibold">{value}</p>
    </div>
  );
}

export default async function PlayerPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const playerId = Number(id);

  const [player, performance] = await Promise.all([
    getPlayer(playerId),
    getPlayerPerformance(playerId),
  ]);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">{player.player_name}</h1>
        <p className="text-sm text-muted-foreground">
          {player.position ?? "—"} · {player.team_name ?? "—"} · {player.league}
        </p>
      </div>

      <section className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="Bàn thắng" value={stat(performance.goals)} />
        <Stat label="Kiến tạo" value={stat(performance.assists)} />
        <Stat label="Ra sân" value={stat(performance.apps)} />
        <Stat label="Phút thi đấu" value={stat(performance.minutes)} />
        <Stat label="xG" value={stat(performance.xg)} />
        <Stat label="xA" value={stat(performance.xa)} />
        <Stat label="xG/90" value={stat(performance.xg90)} />
        <Stat label="xA/90" value={stat(performance.xa90)} />
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Verify in a browser** — use a real Premier League `player_id`
  (query `SELECT player_id, player_name FROM gold.player_profile LIMIT 5;` if
  you don't have one handy; remember `gold.player_profile` is
  Premier-League-only)

Open `http://localhost:3000/players/<a real player_id>`. Expected: player
name, position/team/league line, 8 stat tiles (some may show `—` if that
player has no matched statbunker/understat data — that's the known
data-contract limitation, not a bug).

- [ ] **Step 3: Commit**

```bash
git add frontend/app/players
git commit -m "feat: add player detail page"
```

---

## Task 8: Search page

**Files:**
- Create: `frontend/components/SearchBox.tsx`
- Create: `frontend/app/search/page.tsx`

**Interfaces:**
- Consumes: `search` from `lib/api.ts`; `SearchResult` from `lib/types.ts`.

- [ ] **Step 1: Create `frontend/components/SearchBox.tsx`**

```tsx
"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export default function SearchBox({ initialQuery = "" }: { initialQuery?: string }) {
  const [value, setValue] = useState(initialQuery);
  const router = useRouter();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (value.trim().length < 2) return;
    router.push(`/search?q=${encodeURIComponent(value.trim())}`);
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <Input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Tìm đội bóng hoặc cầu thủ..."
        className="max-w-sm"
      />
      <Button type="submit">Tìm</Button>
    </form>
  );
}
```

- [ ] **Step 2: Create `frontend/app/search/page.tsx`**

```tsx
import Link from "next/link";
import SearchBox from "@/components/SearchBox";
import { search } from "@/lib/api";
import type { SearchResult } from "@/lib/types";

function resultHref(result: SearchResult): string {
  return result.type === "team" ? `/teams/${result.id}` : `/players/${result.id}`;
}

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const results = q && q.trim().length >= 2 ? await search(q.trim()) : [];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Tìm kiếm</h1>
      <SearchBox initialQuery={q ?? ""} />

      {q && (
        <div>
          {results.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Không tìm thấy kết quả cho &quot;{q}&quot;.
            </p>
          ) : (
            <ul className="divide-y">
              {results.map((r) => (
                <li key={`${r.type}-${r.id}`} className="py-3">
                  <Link href={resultHref(r)} className="hover:underline">
                    <span className="font-medium">{r.name}</span>{" "}
                    <span className="text-sm text-muted-foreground">
                      ({r.type === "team" ? "Đội bóng" : "Cầu thủ"}
                      {r.subtitle ? ` · ${r.subtitle}` : ""})
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verify in a browser**

Open `http://localhost:3000/search`, type a partial team or player name
(≥2 characters), submit. Expected: URL updates to `?q=...`, results list
appears with working links into `/teams/[id]` or `/players/[id]`.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/SearchBox.tsx frontend/app/search
git commit -m "feat: add search page"
```

---

## Task 9: 404 and error boundaries

**Files:**
- Create: `frontend/app/not-found.tsx`
- Create: `frontend/app/error.tsx`

- [ ] **Step 1: Create `frontend/app/not-found.tsx`**

```tsx
import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center gap-4 py-20 text-center">
      <h1 className="text-3xl font-bold">404</h1>
      <p className="text-muted-foreground">Không tìm thấy nội dung bạn yêu cầu.</p>
      <Link href="/" className="text-primary hover:underline">
        Quay về trang chủ
      </Link>
    </div>
  );
}
```

- [ ] **Step 2: Create `frontend/app/error.tsx`**

> **Note (Next.js 16.2+):** the installed Next.js version (16.2.12) replaced
> `error.tsx`'s `reset` prop with `unstable_retry` as of `v16.2.0` (`reset`
> still exists but the docs recommend `unstable_retry` in almost all cases —
> see `node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/error.md`).
> Use `unstable_retry` below, not `reset`.

```tsx
"use client";

export default function Error({
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  return (
    <div className="flex flex-col items-center gap-4 py-20 text-center">
      <h1 className="text-3xl font-bold">Đã có lỗi xảy ra</h1>
      <p className="text-muted-foreground">
        Không thể kết nối tới backend. Vui lòng kiểm tra server và thử lại.
      </p>
      <button
        onClick={() => unstable_retry()}
        className="rounded-md border px-4 py-2 text-sm hover:bg-accent"
      >
        Thử lại
      </button>
    </div>
  );
}
```

- [ ] **Step 3: Verify both boundaries manually**

For 404: revisit `http://localhost:3000/teams/999999` — expected the styled
404 page from Step 1 (instead of Next's generic default).

For the error boundary: stop the backend (`Ctrl+C` on the `uvicorn`
process), then reload any data-fetching page, e.g.
`http://localhost:3000/`. Expected: the styled error page from Step 2 with a
"Thử lại" button. Restart the backend afterward and confirm "Thử lại"
recovers the page.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/not-found.tsx frontend/app/error.tsx
git commit -m "feat: add 404 and error boundaries"
```

---

## Task 10: Responsive navbar — inline search input and mobile hamburger menu

Added mid-build per explicit user request (not in the original design spec):
an always-visible compact search input in the navbar, plus a hamburger menu
that collapses navigation on small screens for future links (e.g. a future
"Leagues" or "Chatbot" entry). Scope agreed with the user: the inline input
replaces the standalone "Search" link (Enter navigates to
`/search?q=...`, same as the existing `/search` page's `SearchBox`); the
hamburger is a responsive nav toggle only, no new menu items yet.

**Files:**
- Modify: `frontend/components/Navbar.tsx`

**Interfaces:**
- Consumes: `useRouter` from `next/navigation`; `Input` from
  `components/ui/input`; `Menu`, `X` icons from `lucide-react` (already a
  dependency via shadcn/ui).

- [ ] **Step 1: Replace `frontend/components/Navbar.tsx`**

```tsx
"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Menu, X } from "lucide-react";
import { Input } from "@/components/ui/input";

function NavSearchInput() {
  const [value, setValue] = useState("");
  const router = useRouter();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (value.trim().length < 2) return;
    router.push(`/search?q=${encodeURIComponent(value.trim())}`);
  }

  return (
    <form onSubmit={handleSubmit}>
      <Input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Search..."
        className="h-8 w-40 sm:w-56"
      />
    </form>
  );
}

export default function Navbar() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="border-b">
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:grid sm:grid-cols-3">
        <Link href="/" className="text-lg font-semibold">
          Football Data Platform
        </Link>

        <div className="hidden sm:flex sm:justify-center">
          <NavSearchInput />
        </div>

        <div className="hidden sm:flex sm:items-center sm:justify-end sm:gap-4">
          <Link href="/" className="text-sm hover:underline">
            Home
          </Link>
        </div>

        <button
          type="button"
          onClick={() => setMenuOpen((open) => !open)}
          className="flex h-8 w-8 items-center justify-center rounded-md border sm:hidden"
          aria-label="Toggle menu"
          aria-expanded={menuOpen}
        >
          {menuOpen ? <X className="size-5" /> : <Menu className="size-5" />}
        </button>
      </nav>

      {menuOpen && (
        <div className="flex flex-col gap-3 border-t px-4 py-3 sm:hidden">
          <Link
            href="/"
            className="text-sm hover:underline"
            onClick={() => setMenuOpen(false)}
          >
            Home
          </Link>
          <NavSearchInput />
        </div>
      )}
    </header>
  );
}
```

- [ ] **Step 2: Verify in a browser** — desktop width (≥640px): logo on the
  left, search input centered in the middle of the navbar, "Home" on the
  right, no hamburger button. Narrow the window below 640px (or use browser
  device toolbar): "Home" link and search input disappear from the header,
  hamburger button appears; clicking it reveals both stacked underneath,
  clicking "Home" in that panel closes it and navigates. Typing ≥2 characters
  and pressing Enter in either search input navigates to `/search?q=...`.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/Navbar.tsx
git commit -m "feat: add inline navbar search and responsive hamburger menu"
```

---

## Task 11: Docker Compose integration

**Files:**
- Create: `frontend/Dockerfile`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Create `frontend/Dockerfile`**

```dockerfile
# frontend/Dockerfile
FROM node:20-slim

WORKDIR /app

# Install dependencies BEFORE copying code -> leverage Docker layer caching
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./

RUN npm run build

EXPOSE 3000
CMD ["npm", "start"]
```

- [ ] **Step 2: Add a `frontend` service to `docker-compose.yml`** — insert
  after the `backend` service, before the closing `volumes:` block:

```yaml
  frontend:
    build:
      context: .
      dockerfile: frontend/Dockerfile
    container_name: footballdataplatform-frontend
    environment:
      API_URL: http://backend:8000
    ports:
      - "3000:3000"
    depends_on:
      - backend
```

- [ ] **Step 3: Verify full stack via Docker**

```powershell
docker compose build backend frontend
docker compose up -d postgres backend frontend
```

Open `http://localhost:3000` in a browser — expected the same working home
page as `npm run dev`, now served entirely from containers (frontend
container reaching backend container via the `backend` service name, not
`localhost`).

```powershell
docker compose down
```

- [ ] **Step 4: Commit**

```bash
git add frontend/Dockerfile docker-compose.yml
git commit -m "feat: add frontend service to docker-compose"
```

---

## Self-check against the roadmap's Week 7+8 frontend deliverables

| Roadmap item | This plan |
|---|---|
| Trang chủ: showcase giải đấu, trận gần đây, top scorers | Task 4 (+ Task 1 for the 2 missing backend endpoints it needed) |
| Trang giải đấu: bảng xếp hạng, lịch thi đấu | Task 5 (+ Task 1 for `leagues/{league}/matches`) |
| Trang đội bóng: thông tin đội, form W-D-L, trận gần nhất | Task 6 |
| Trang cầu thủ: profile, thống kê mùa | Task 7 |
| Trang tìm kiếm | Task 8 |
| ≥5 trang, responsive, dùng shadcn/ui + Tailwind | Tasks 4–8 (Tailwind responsive classes throughout: `sm:grid-cols-2`, `sm:grid-cols-4`); shadcn/ui via Task 2 |
| *(added mid-build, user request)* responsive navbar with inline search + hamburger menu | Task 10 |
| docker-compose.yml bổ sung service frontend | Task 11 |
| `docs/ai-prompts.md` | Explicitly out of scope — see Global Constraints |
