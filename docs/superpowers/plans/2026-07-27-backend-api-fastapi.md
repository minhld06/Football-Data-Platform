# Backend API (FastAPI, Phương án A) Implementation Plan

> **For the student:** This plan is written to be executed by hand — copy each
> code block into the file path shown, then run the verification command
> before moving to the next task. It intentionally does not use
> subagent-driven or fully-automated execution: the point of Tuần 7+8 is that
> you type/paste and understand every file yourself.

**Goal:** Stand up a standalone FastAPI backend (Phương án A) that exposes 10
read-only endpoints over `gold.*` Postgres tables, matching the Tuần 7+8
roadmap's minimum endpoint list.

**Architecture:** `backend/` is a separate Python service (its own
`requirements.txt`, own Docker image) that connects to the same Postgres
database ingestion already writes to, using the same `psycopg` v3 +
`dict_row` pattern as `ingestion/core/db.py`. FastAPI routers group endpoints
by resource (leagues, teams, players, matches, search); Pydantic models in
`schemas.py` define the response shape for each. No ORM — plain SQL, because
every query is a simple `SELECT` and an ORM would add a dependency without
adding clarity (see CLAUDE.md: "don't over-engineer Phase 1").

**Tech Stack:** FastAPI, Uvicorn, `psycopg[binary]` v3, Pydantic, python-dotenv.

## Global Constraints

- Backend is **read-only** — every query is a `SELECT`. No `INSERT`/`UPDATE`/`DELETE` code belongs in `backend/`.
- Query `gold.*`, not `silver.*`, from routers — per CLAUDE.md: "Prepare Week 5 backend/frontend work on top of `gold.*`". Two new gold models are added in Task 1 to make this possible for teams/matches.
- Reuse `ingestion`'s DB pattern (`psycopg.connect(..., row_factory=dict_row)` in a `contextmanager`) instead of inventing a new one.
- `DATABASE_URL` comes from `.env` via `python-dotenv`, same as ingestion — never hardcode credentials.
- dbt model names must be globally unique — cannot reuse `teams`/`matches` (already taken by `transform/models/silver/`). New gold models are named `team_profile` / `match_results` instead (matches the existing `player_profile` naming pattern).
- `GET /api/matches/{id}/events` from the roadmap is **not built** — there is no crawler for match-event data yet (confirmed: no gold/silver model, no crawler references events). Replaced by `GET /api/leagues/{id}/teams` to still reach 10 endpoints. Building an events crawler is a separate future task, not part of this plan.
- `/api/chat` (roadmap item, week 6) is out of scope for this plan.

---

## Task 1: Two new gold dbt models — `team_profile` and `match_results`

**Files:**
- Create: `transform/models/gold/team_profile.sql`
- Create: `transform/models/gold/match_results.sql`
- Create: `transform/tests/assert_gold_match_results_unique_grain.sql`
- Modify: `transform/models/gold/_gold.yml`
- Modify: `docs/gold_data_contract.md`

**Interfaces:**
- Produces: `gold.team_profile(team_id, team_name, team_short_name, team_tla, league)` — 1 row/`team_id`.
- Produces: `gold.match_results(source_match_id, league, season, matchday, status, utc_date, home_team_id, home_team_name, away_team_id, away_team_name, home_score, away_score)` — 1 row/`source_match_id`.

- [ ] **Step 1: Create `transform/models/gold/team_profile.sql`**

```sql
{{ config(materialized='view') }}

-- Thin passthrough of silver.teams, materialized as a view (same pattern as
-- player_profile) so team identity stays in sync without needing a rebuild.
select
    team_id,
    team_name,
    team_short_name,
    team_tla,
    league
from {{ ref('teams') }}
```

- [ ] **Step 2: Create `transform/models/gold/match_results.sql`**

```sql
{{ config(materialized='table') }}

-- silver.matches left-joined twice onto silver.teams so the API/frontend
-- never has to join at read time to show a team name next to a match.
select
    m.source_match_id,
    m.league,
    m.season,
    m.matchday,
    m.status,
    m.utc_date,
    m.home_team_id,
    ht.team_name as home_team_name,
    m.away_team_id,
    at.team_name as away_team_name,
    m.home_score,
    m.away_score
from {{ ref('matches') }} m
left join {{ ref('teams') }} ht on ht.team_id = m.home_team_id
left join {{ ref('teams') }} at on at.team_id = m.away_team_id
```

- [ ] **Step 3: Create `transform/tests/assert_gold_match_results_unique_grain.sql`**

```sql
select source_match_id, count(*) as n
from {{ ref('match_results') }}
group by source_match_id
having count(*) > 1
```

- [ ] **Step 4: Add schema tests — append to `transform/models/gold/_gold.yml`** (under the existing `models:` key, after `player_performance`)

```yaml
  - name: team_profile
    description: "One row per team: identity (name, short name, TLA) and current league. Grain is 1 row/team_id.
                  Logic: thin passthrough of silver.teams, materialized as a view (same pattern as
                  player_profile) so it stays in sync as silver.teams changes without a rebuild.
                  "
    columns:
      - name: team_id
        tests:
          - unique
          - not_null

  - name: match_results
    description: "One row per match with home/away team names denormalized in. Grain is 1 row/source_match_id.
                  Logic: silver.matches left-joined twice onto silver.teams for home_team_name/away_team_name,
                  so the API/frontend never needs to join at read time.
                  "
    columns:
      - name: source_match_id
        tests:
          - unique
          - not_null
```

- [ ] **Step 5: Run dbt and verify**

```powershell
cd transform
dbt build --select team_profile match_results assert_gold_match_results_unique_grain
```

Expected: all models build, both new tests `PASS`.

- [ ] **Step 6: Update `docs/gold_data_contract.md`** — add two new sections after `## gold.player_performance` and before `## Out of scope`, following the exact format of the existing tables (grain, freshness, column table, known limitations if any). Also update the `## Out of scope` section to remove the now-stale "match-level data still has no crawler" framing for identity/results (results now exist; only *event*-level data is still out of scope).

- [ ] **Step 7: Commit**

```bash
git add transform/models/gold/team_profile.sql transform/models/gold/match_results.sql transform/tests/assert_gold_match_results_unique_grain.sql transform/models/gold/_gold.yml docs/gold_data_contract.md
git commit -m "feat: add gold.team_profile and gold.match_results for backend API"
```

---

## Task 2: Backend scaffold — project structure, DB connection, health check

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/db.py`
- Create: `backend/main.py`
- Create: `backend/routers/__init__.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: `get_connection()` — context manager yielding a `psycopg.Connection` with `row_factory=dict_row`, reading `DATABASE_URL` from env. Every later router imports this.

- [ ] **Step 1: Create `backend/requirements.txt`**

```
fastapi==0.136.3
uvicorn==0.48.0
pydantic==2.13.4
psycopg[binary]==3.2.3
python-dotenv==1.0.1
pytest==8.3.3
```

- [ ] **Step 2: Create `backend/db.py`** (same pattern as `ingestion/core/db.py`)

```python
import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()


def get_connection_string() -> str:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set in .env")
    return db_url


@contextmanager
def get_connection():
    """Context manager: automatically closes the connection when done."""
    conn = psycopg.connect(get_connection_string(), row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()
```

- [ ] **Step 3: Create `backend/routers/__init__.py`** (empty file, makes `routers` a package)

- [ ] **Step 4: Create `backend/main.py`**

```python
import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import leagues, teams, players, matches, search

load_dotenv()
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Football Data Platform API")

frontend_origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(leagues.router, prefix="/api/leagues", tags=["leagues"])
app.include_router(teams.router, prefix="/api/teams", tags=["teams"])
app.include_router(players.router, prefix="/api/players", tags=["players"])
app.include_router(matches.router, prefix="/api/matches", tags=["matches"])
app.include_router(search.router, prefix="/api/search", tags=["search"])


@app.get("/api/health")
def health():
    return {"status": "ok"}
```

Note: `main.py` imports `routers.leagues`, `.teams`, etc. which don't exist
yet — that's expected, they're created in later tasks. `uvicorn` will fail to
start until Task 3 exists; the health check becomes runnable once all five
router modules are in place (end of Task 7).

- [ ] **Step 5: Add `FRONTEND_ORIGIN` to `.env.example`**

Append this line to the existing `.env.example`:

```
FRONTEND_ORIGIN=http://localhost:3000
```

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/db.py backend/routers/__init__.py backend/main.py .env.example
git commit -m "feat: scaffold FastAPI backend project structure"
```

---

## Task 3: Response schemas — `backend/schemas.py`

**Files:**
- Create: `backend/schemas.py`

**Interfaces:**
- Produces: `LeagueSummary`, `TeamSummary`, `TeamProfile`, `LeagueStanding`, `TeamForm`, `MatchResult`, `PlayerProfile`, `PlayerPerformance`, `SearchResult` — Pydantic models used as `response_model=` in every router.

- [ ] **Step 1: Create `backend/schemas.py`**

```python
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class LeagueSummary(BaseModel):
    league: str
    seasons: list[str]


class TeamSummary(BaseModel):
    team_id: int
    team_name: str
    team_short_name: Optional[str] = None
    team_tla: Optional[str] = None


class TeamProfile(TeamSummary):
    league: str


class LeagueStanding(BaseModel):
    league: str
    season: str
    team_id: int
    team_name: str
    team_short_name: Optional[str] = None
    team_tla: Optional[str] = None
    position: int
    played_games: int
    won: int
    draw: int
    lost: int
    points: int
    goals_for: int
    goals_against: int
    goal_difference: int
    form: Optional[str] = None
    xg: Optional[float] = None
    xga: Optional[float] = None
    xpts: Optional[float] = None


class TeamForm(BaseModel):
    league: str
    season: str
    team_id: int
    team_name: str
    matches_played: int
    wins: int
    draws: int
    losses: int
    points: int
    goals_for: int
    goals_against: int
    form: str


class MatchResult(BaseModel):
    source_match_id: int
    league: str
    season: str
    matchday: Optional[int] = None
    status: str
    utc_date: datetime
    home_team_id: int
    home_team_name: Optional[str] = None
    away_team_id: int
    away_team_name: Optional[str] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None


class PlayerProfile(BaseModel):
    player_id: int
    player_name: str
    position: Optional[str] = None
    nationality: Optional[str] = None
    date_of_birth: Optional[date] = None
    age: Optional[int] = None
    shirt_number: Optional[int] = None
    team_id: int
    team_name: Optional[str] = None
    league: str


class PlayerPerformance(BaseModel):
    player_id: int
    player_name: str
    team_id: int
    team_name: Optional[str] = None
    league: str
    goals: Optional[int] = None
    assists: Optional[int] = None
    apps: Optional[int] = None
    minutes: Optional[int] = None
    xg: Optional[float] = None
    xa: Optional[float] = None
    xg90: Optional[float] = None
    xa90: Optional[float] = None


class SearchResult(BaseModel):
    type: str
    id: int
    name: str
    subtitle: Optional[str] = None
```

- [ ] **Step 2: Commit**

```bash
git add backend/schemas.py
git commit -m "feat: add Pydantic response schemas for backend API"
```

---

## Task 4: Pure query-logic helpers + unit tests — `backend/queries.py`

This is the only place with non-trivial logic (season resolution, search
result shaping), so it's the only place that gets real unit tests — same
depth as `ingestion/tests/test_discovery.py` (pure functions, no live DB).

**Files:**
- Create: `backend/queries.py`
- Create: `backend/tests/test_queries.py`

**Interfaces:**
- Produces: `latest_season(seasons: list[str]) -> str | None`, `format_search_results(teams: list[dict], players: list[dict]) -> list[dict]` — used by `routers/leagues.py` and `routers/search.py` respectively.

- [ ] **Step 1: Write the failing tests — create `backend/tests/test_queries.py`**

```python
from queries import latest_season, format_search_results


def test_latest_season_picks_max_lexical_season():
    assert latest_season(["2023-2024", "2025-2026", "2024-2025"]) == "2025-2026"


def test_latest_season_empty_list_returns_none():
    assert latest_season([]) is None


def test_format_search_results_tags_type_and_shapes_fields():
    teams = [{"team_id": 1, "team_name": "Arsenal", "league": "premier-league"}]
    players = [{"player_id": 10, "player_name": "Bukayo Saka", "team_name": "Arsenal"}]

    results = format_search_results(teams, players)

    assert results == [
        {"type": "team", "id": 1, "name": "Arsenal", "subtitle": "premier-league"},
        {"type": "player", "id": 10, "name": "Bukayo Saka", "subtitle": "Arsenal"},
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

```powershell
cd backend
python -m pytest tests/test_queries.py -v
```

Expected: `FAIL` — `ModuleNotFoundError: No module named 'queries'` (file doesn't exist yet).

- [ ] **Step 3: Create `backend/queries.py`**

```python
def latest_season(seasons: list[str]) -> str | None:
    """Picks the most recent season from a list of 'YYYY-YYYY' strings.
    String comparison works because the format is zero-padded and lexically
    sortable (e.g. '2025-2026' > '2024-2025')."""
    return max(seasons) if seasons else None


def format_search_results(teams: list[dict], players: list[dict]) -> list[dict]:
    results = []
    for t in teams:
        results.append({
            "type": "team",
            "id": t["team_id"],
            "name": t["team_name"],
            "subtitle": t["league"],
        })
    for p in players:
        results.append({
            "type": "player",
            "id": p["player_id"],
            "name": p["player_name"],
            "subtitle": p["team_name"],
        })
    return results
```

- [ ] **Step 4: Run the tests to verify they pass**

```powershell
python -m pytest tests/test_queries.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/queries.py backend/tests/test_queries.py
git commit -m "feat: add season-resolution and search-formatting helpers with tests"
```

---

## Task 5: `GET /api/leagues`, `GET /api/leagues/{league}/teams`, `GET /api/leagues/{league}/standings`

**Files:**
- Create: `backend/routers/leagues.py`

**Interfaces:**
- Consumes: `get_connection` from `db.py`; `latest_season` from `queries.py`; `LeagueSummary`, `TeamSummary`, `LeagueStanding` from `schemas.py`.

- [ ] **Step 1: Create `backend/routers/leagues.py`**

```python
from fastapi import APIRouter, HTTPException

from db import get_connection
from queries import latest_season
from schemas import LeagueSummary, TeamSummary, LeagueStanding

router = APIRouter()


def _resolve_season(cur, league: str, season: str | None) -> str | None:
    if season:
        return season
    cur.execute(
        "SELECT DISTINCT season FROM gold.league_standings WHERE league = %s",
        (league,),
    )
    seasons = [row["season"] for row in cur.fetchall()]
    return latest_season(seasons)


@router.get("", response_model=list[LeagueSummary])
def list_leagues():
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT league, array_agg(DISTINCT season ORDER BY season DESC) AS seasons
            FROM gold.league_standings
            GROUP BY league
            ORDER BY league
            """
        )
        return cur.fetchall()


@router.get("/{league}/teams", response_model=list[TeamSummary])
def list_league_teams(league: str, season: str | None = None):
    with get_connection() as conn, conn.cursor() as cur:
        resolved_season = _resolve_season(cur, league, season)
        if resolved_season is None:
            raise HTTPException(status_code=404, detail=f"League '{league}' not found")

        cur.execute(
            """
            SELECT DISTINCT team_id, team_name, team_short_name, team_tla
            FROM gold.league_standings
            WHERE league = %s AND season = %s
            ORDER BY team_name
            """,
            (league, resolved_season),
        )
        return cur.fetchall()


@router.get("/{league}/standings", response_model=list[LeagueStanding])
def get_league_standings(league: str, season: str | None = None):
    with get_connection() as conn, conn.cursor() as cur:
        resolved_season = _resolve_season(cur, league, season)
        if resolved_season is None:
            raise HTTPException(status_code=404, detail=f"League '{league}' not found")

        cur.execute(
            "SELECT * FROM gold.league_standings WHERE league = %s AND season = %s ORDER BY position",
            (league, resolved_season),
        )
        return cur.fetchall()
```

- [ ] **Step 2: Start the server and verify manually**

```powershell
cd backend
python -m uvicorn main:app --reload --port 8000
```

In another terminal (adjust league/season to real values from your DB —
check with `SELECT DISTINCT league, season FROM gold.league_standings;` in
psql/pgAdmin first):

```powershell
curl http://localhost:8000/api/leagues
curl http://localhost:8000/api/leagues/premier-league/teams
curl http://localhost:8000/api/leagues/premier-league/standings
```

Expected: each returns a `200` with a JSON array matching the shapes in
`schemas.py`. An unknown league (e.g. `curl http://localhost:8000/api/leagues/not-a-league/standings`) should return `404`.

- [ ] **Step 3: Commit**

```bash
git add backend/routers/leagues.py
git commit -m "feat: add /api/leagues endpoints"
```

---

## Task 6: `GET /api/teams/{team_id}`, `GET /api/teams/{team_id}/matches`, `GET /api/teams/{team_id}/form`

**Files:**
- Create: `backend/routers/teams.py`

**Interfaces:**
- Consumes: `get_connection` from `db.py`; `TeamProfile`, `MatchResult`, `TeamForm` from `schemas.py`.

- [ ] **Step 1: Create `backend/routers/teams.py`**

```python
from fastapi import APIRouter, HTTPException

from db import get_connection
from schemas import TeamProfile, MatchResult, TeamForm

router = APIRouter()


@router.get("/{team_id}", response_model=TeamProfile)
def get_team(team_id: int):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM gold.team_profile WHERE team_id = %s", (team_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Team {team_id} not found")
        return row


@router.get("/{team_id}/matches", response_model=list[MatchResult])
def get_team_matches(team_id: int, season: str | None = None):
    with get_connection() as conn, conn.cursor() as cur:
        if season:
            cur.execute(
                """
                SELECT * FROM gold.match_results
                WHERE (home_team_id = %s OR away_team_id = %s) AND season = %s
                ORDER BY utc_date DESC
                """,
                (team_id, team_id, season),
            )
        else:
            cur.execute(
                """
                SELECT * FROM gold.match_results
                WHERE home_team_id = %s OR away_team_id = %s
                ORDER BY utc_date DESC
                """,
                (team_id, team_id),
            )
        return cur.fetchall()


@router.get("/{team_id}/form", response_model=TeamForm)
def get_team_form(team_id: int):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM gold.team_form_last_5_matches WHERE team_id = %s ORDER BY season DESC LIMIT 1",
            (team_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"No form data for team {team_id}")
        return row
```

- [ ] **Step 2: Verify manually** (server still running from Task 5; `--reload` picks up the new file automatically — but it will only start successfully once `players.py`, `matches.py`, `search.py` also exist, since `main.py` imports all five up front. If you want to smoke-test each router in isolation before all five exist, temporarily comment out the other `include_router` lines in `main.py` and uncomment them back before the final Task 8 verification.)

```powershell
curl http://localhost:8000/api/teams/57
curl http://localhost:8000/api/teams/57/matches
curl http://localhost:8000/api/teams/57/form
```

(Replace `57` with a real `team_id` from `SELECT team_id, team_name FROM gold.league_standings LIMIT 5;`.)

- [ ] **Step 3: Commit**

```bash
git add backend/routers/teams.py
git commit -m "feat: add /api/teams endpoints"
```

---

## Task 7: `GET /api/players/{player_id}`, `GET /api/players/{player_id}/performance`

**Files:**
- Create: `backend/routers/players.py`

**Interfaces:**
- Consumes: `get_connection` from `db.py`; `PlayerProfile`, `PlayerPerformance` from `schemas.py`.

- [ ] **Step 1: Create `backend/routers/players.py`**

```python
from fastapi import APIRouter, HTTPException

from db import get_connection
from schemas import PlayerProfile, PlayerPerformance

router = APIRouter()


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

- [ ] **Step 2: Verify manually**

```powershell
curl http://localhost:8000/api/players/PLAYER_ID
curl http://localhost:8000/api/players/PLAYER_ID/performance
```

(Get a real `player_id` from `SELECT player_id, player_name FROM gold.player_profile LIMIT 5;` — remember `gold.player_profile` is Premier-League-only per the data contract.)

- [ ] **Step 3: Commit**

```bash
git add backend/routers/players.py
git commit -m "feat: add /api/players endpoints"
```

---

## Task 8: `GET /api/matches/{match_id}`, `GET /api/search`, full server verification

**Files:**
- Create: `backend/routers/matches.py`
- Create: `backend/routers/search.py`

**Interfaces:**
- Consumes: `get_connection` from `db.py`; `MatchResult`, `SearchResult` from `schemas.py`; `format_search_results` from `queries.py`.

- [ ] **Step 1: Create `backend/routers/matches.py`**

```python
from fastapi import APIRouter, HTTPException

from db import get_connection
from schemas import MatchResult

router = APIRouter()


@router.get("/{match_id}", response_model=MatchResult)
def get_match(match_id: int):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM gold.match_results WHERE source_match_id = %s", (match_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Match {match_id} not found")
        return row
```

- [ ] **Step 2: Create `backend/routers/search.py`**

```python
from fastapi import APIRouter, Query

from db import get_connection
from queries import format_search_results
from schemas import SearchResult

router = APIRouter()


@router.get("", response_model=list[SearchResult])
def search(q: str = Query(min_length=2)):
    like_pattern = f"%{q}%"
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT team_id, team_name, league FROM gold.team_profile WHERE team_name ILIKE %s ORDER BY team_name LIMIT 10",
            (like_pattern,),
        )
        teams = cur.fetchall()

        cur.execute(
            "SELECT player_id, player_name, team_name FROM gold.player_profile WHERE player_name ILIKE %s ORDER BY player_name LIMIT 10",
            (like_pattern,),
        )
        players = cur.fetchall()

    return format_search_results(teams, players)
```

Note: this is case-insensitive substring search (`ILIKE`), not typo-tolerant
fuzzy search. True fuzzy matching needs the `pg_trgm` Postgres extension —
skipped here as out-of-scope for Phase 1 (same "don't over-engineer"
principle as everywhere else in this codebase); worth a follow-up if the
frontend search box needs typo tolerance later.

- [ ] **Step 3: All five routers now exist — restart the server and verify the full API**

```powershell
cd backend
python -m uvicorn main:app --reload --port 8000
```

```powershell
curl http://localhost:8000/api/health
curl http://localhost:8000/api/matches/MATCH_ID
curl "http://localhost:8000/api/search?q=ars"
```

Also open `http://localhost:8000/docs` in a browser — FastAPI's
auto-generated Swagger UI should list all 10 endpoints. Click through 2–3 of
them with "Try it out" to confirm the response shapes match `schemas.py`.

- [ ] **Step 4: Commit**

```bash
git add backend/routers/matches.py backend/routers/search.py
git commit -m "feat: add /api/matches and /api/search endpoints"
```

---

## Task 9: Docker Compose integration

**Files:**
- Create: `backend/Dockerfile`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Create `backend/Dockerfile`**

```dockerfile
# backend/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies BEFORE copying code -> leverage Docker layer caching
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r ./backend/requirements.txt

# Copy backend code into the image
COPY backend ./backend

WORKDIR /app/backend

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Add a `backend` service to `docker-compose.yml`** — insert after the `ingestion` service, before the closing `volumes:` block:

```yaml
  backend:
    build:
      context: .
      dockerfile: backend/Dockerfile
    container_name: footballdataplatform-backend
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql://postgres:${POSTGRES_PASSWORD}@postgres:5432/football
      FRONTEND_ORIGIN: http://localhost:3000
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
```

Note: unlike `crawlers`/`ingestion`, `backend` has **no** `profiles: [tools]`
— it's a long-running server, not a one-shot job, so it should start
automatically with `docker compose up` alongside `postgres`.

- [ ] **Step 3: Verify**

```powershell
docker compose build backend
docker compose up -d postgres backend
curl http://localhost:8000/api/health
docker compose down
```

Expected: `{"status": "ok"}`.

- [ ] **Step 4: Commit**

```bash
git add backend/Dockerfile docker-compose.yml
git commit -m "feat: add backend service to docker-compose"
```

---

## Task 10: `docs/ai-prompts.md`

The roadmap deliverable asks for a running log of the prompts you actually
used with Claude Code this week — this is deliberately **not** filled in by
this plan, since the content has to be your real prompts, not fabricated
ones. Create the file with just a header so you have somewhere to log as you
go:

- [ ] **Step 1: Create `docs/ai-prompts.md`**

```markdown
# AI Prompts Log — Tuần 7+8 (Backend API)

Prompts used with Claude Code this week, kept for reuse. Add one entry per
prompt that produced something worth keeping.

## [date] — [what it produced]

```
[the actual prompt text]
```
```

- [ ] **Step 2: Commit**

```bash
git add docs/ai-prompts.md
git commit -m "docs: start ai-prompts log for Tuần 7+8"
```

---

## Self-check against the roadmap's endpoint list

| Roadmap item | This plan |
|---|---|
| `GET /api/leagues` | Task 5 |
| `GET /api/leagues/{id}/standings?season=` | Task 5 (league is a slug, not a numeric id — see Global Constraints) |
| `GET /api/teams/{id}` | Task 6 |
| `GET /api/teams/{id}/matches?season=` | Task 6 |
| `GET /api/players/{id}` | Task 7 |
| `GET /api/players/{id}/performance?season=` | Task 7 (no per-season split in `gold.player_performance` yet — returns career-to-date stats) |
| `GET /api/matches/{id}` | Task 8 |
| `GET /api/matches/{id}/events` | **Not built** — no data source (see Global Constraints) |
| `GET /api/search?q=` | Task 8 |
| `POST /api/chat` | Out of scope (Week 6) |
| *(extra, to reach 10)* `GET /api/leagues/{id}/teams?season=` | Task 5 |
| *(extra, to reach 10)* `GET /api/teams/{id}/form` | Task 6 |
