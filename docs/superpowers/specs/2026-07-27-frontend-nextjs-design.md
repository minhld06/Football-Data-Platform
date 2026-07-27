# Frontend: Next.js v1 (Week 7+8)

Date: 2026-07-27

## Context

Backend (`backend/`, FastAPI, "Phương án A") is complete and stable (see
[project_backend_api memory]). This is the paired frontend deliverable for
Week 7+8: a Next.js app with the roadmap's 5 minimum pages, calling the
backend as a separate service — the frontend does no direct DB access.

Execution mode for this build (explicit user choice, consistent with the
backend build): complete, paste-ready code per file, reviewed and verified
after pasting — not explain-then-user-writes.

## Decisions

### 1. Backend gap: 3 new endpoints required first

Auditing the roadmap's page content against the 10 existing endpoints
surfaced two gaps — home page ("trận đấu gần đây", "top scorers") and league
page ("lịch thi đấu") need data no existing endpoint provides. Both gaps are
closed by adding 3 read-only endpoints, all reusing existing gold tables and
existing Pydantic schemas (no new gold models, no new schemas):

| Endpoint | Router | Query | Returns |
|---|---|---|---|
| `GET /api/matches/recent` | `matches.py`, registered **before** `/{match_id}` | `league: str \| None`, `limit: int = 10` (max 50) | `list[MatchResult]` — `gold.match_results` where `status='FINISHED'`, optional `league` filter, `ORDER BY utc_date DESC LIMIT`. |
| `GET /api/leagues/{league}/matches` | `leagues.py` | `season: str \| None` (defaults via existing `_resolve_season`), `limit: int \| None` | `list[MatchResult]` — `gold.match_results` where `league = %s AND season = %s`, `ORDER BY utc_date`. |
| `GET /api/players/top-scorers` | `players.py`, registered **before** `/{player_id}` | `league: str \| None`, `limit: int = 10` (max 50) | `list[PlayerPerformance]` — `gold.player_performance`, optional `league` filter, `ORDER BY goals DESC NULLS LAST LIMIT`. Returns `[]` for `league=ligue-1` (known limitation: `player_performance` is Premier-League-only — see `docs/gold_data_contract.md`). |

Route order matters only for readability here — FastAPI's `int`-typed path
converter for `{match_id}` / `{player_id}` won't match a non-numeric segment
like `recent` or `top-scorers`, but the new routes are still declared first
in each file to keep intent obvious.

### 2. Frontend routing (Next.js App Router, TypeScript)

```
frontend/
  app/
    layout.tsx              # Navbar (Home / Leagues / Search) + global styles
    page.tsx                # Home
    leagues/[league]/page.tsx
    teams/[id]/page.tsx
    players/[id]/page.tsx
    search/page.tsx
    not-found.tsx            # 404 (team/player/league not found)
    error.tsx                 # backend-down / fetch failure boundary
  components/
    ui/                       # shadcn/ui generated components (Card, Table, Badge, Select, Input)
    Navbar.tsx
    LeagueCard.tsx
    StandingsTable.tsx
    MatchList.tsx
    SeasonSelect.tsx           # Client Component — season dropdown
    TeamFormBadge.tsx
    SearchBox.tsx               # Client Component — controlled input, navigates to /search?q=
  lib/
    api.ts                     # fetch helpers, one per backend endpoint, base URL from process.env.API_URL
    types.ts                   # TS interfaces mirroring backend/schemas.py 1:1
  .env.local.example            # API_URL=http://localhost:8000
  Dockerfile
```

Every page is a Server Component that calls `lib/api.ts` functions directly
(plain `fetch`, no client-side data library) — matches "Phương án A": thin
frontend, backend does all the work. The only Client Components are the
season dropdown and the search input, both of which just update the URL via
`useRouter`/`useSearchParams` and let the Server Component re-fetch.

### 3. Page-by-page content

- **`/` (Home)** — `GET /api/leagues` (league cards linking to
  `/leagues/[league]`), `GET /api/matches/recent?limit=5`, `GET
  /api/players/top-scorers?limit=5`.
- **`/leagues/[league]`** — season resolved from `?season=` query param
  (defaults to latest via backend's existing `_resolve_season`).
  `SeasonSelect` populated from the `seasons` array already returned by `GET
  /api/leagues`. Fetches `GET /api/leagues/{league}/standings?season=` (table)
  and `GET /api/leagues/{league}/matches?season=` (fixture list). Standing
  rows link to `/teams/[id]`.
- **`/teams/[id]`** — `GET /api/teams/{id}` (profile), `GET
  /api/teams/{id}/form` (W-D-L badges), `GET /api/teams/{id}/matches` (recent
  matches list, each linking to the opposing team).
- **`/players/[id]`** — `GET /api/players/{id}` (profile), `GET
  /api/players/{id}/performance` (goals/assists/xG/xA — render `—` for any
  null field per the known Premier-League-only / unmatched-player gaps in the
  data contract, not an error state).
- **`/search`** — reads `?q=` from `searchParams`, calls `GET
  /api/search?q=` (min 2 chars enforced client-side before navigating),
  renders team/player results as links into their detail pages.

### 4. Error handling

- 404s (`get_team`/`get_player`/standings-with-unknown-league all return
  HTTP 404 from the backend already) are translated to Next's `notFound()` →
  `not-found.tsx`.
- Any other fetch failure (backend unreachable, 5xx) throws, caught by
  `error.tsx` at the route segment.
- No client-side loading spinners needed for initial load (Server Components
  render after fetch completes); the season/search navigations show Next's
  built-in route transition, no extra skeleton UI for this v1.

### 5. Docker integration

Add a `frontend` service to `docker-compose.yml`: builds `frontend/Dockerfile`,
port `3000:3000`, `depends_on: backend`, `environment: API_URL:
http://backend:8000` (Docker service name, not `localhost` — same gotcha
already documented in `CLAUDE.md` for other services). `backend`'s existing
`FRONTEND_ORIGIN` CORS setting already defaults to `http://localhost:3000`,
matching this frontend's dev port — no backend change needed there.

## Out of scope

- No client-side data-fetching library (SWR/React Query) — data volume
  (dozens of teams, hundreds of matches) doesn't justify the dependency.
- No authentication, no write operations — matches backend's read-only scope.
- Match-event-level UI (goal scorers, cards, subs) — no crawler produces this
  data anywhere in the platform (documented gap, see `project_backend_api`
  memory and `docs/gold_data_contract.md`).
- `docs/ai-prompts.md` — explicitly skipped by user choice for the backend
  build; same applies here unless the user asks otherwise.
- Styling polish / dark mode / animations beyond shadcn/ui defaults — v1 goal
  is 5 working, responsive, not-ugly pages per the roadmap, not a design
  pass.
