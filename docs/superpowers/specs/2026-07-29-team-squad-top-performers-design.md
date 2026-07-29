# Team Squad + Top Scorer/Assist Widgets

Date: 2026-07-29

## Context

Two additions to the existing frontend/backend (see
[2026-07-27-frontend-nextjs-design.md](2026-07-27-frontend-nextjs-design.md)
for the baseline architecture this builds on):

1. The team detail page (`/teams/[id]`) currently shows profile + form +
   matches only. It needs a **squad list** and the team's own **top scorer /
   top assist** (currently these only exist at league scope).
2. The league page (`/leagues/[league]`) currently shows Top Scorers next to
   the standings table. It needs a **Top Assists** section directly below it,
   in the same right-hand column.

Both features reuse data already in the gold layer — `gold.player_profile`
(squad/team_id) and `gold.player_performance` (goals/assists/team_id). No dbt
model, gold schema, or crawler changes are needed; see
`docs/gold_data_contract.md` for the existing column contracts these queries
rely on (notably: both tables are Premier-League-only today — a Ligue 1 team
page will show empty squad/top-performer sections, not an error).

Confirmed with user during brainstorming:
- Squad grouped by position (`Goalkeeper` / `Defence` / `Midfield` /
  `Offence` — these are the only 4 values that occur in
  `gold.player_profile.position`, verified against the live DB), sorted by
  shirt number within each group.
- Team-scoped top scorer/assist show **top 5** (vs. top 10 at league scope).
- Both team-scoped and league-scoped lists **exclude players with 0 or NULL**
  goals/assists — applied uniformly to both scopes for consistency, though at
  league scope this is a no-op (the real top 10 goal scorers always have
  >0 goals).

## Backend

### 1. `GET /api/teams/{team_id}/squad` — new endpoint in `teams.py`

```sql
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
```

Returns `list[PlayerProfile]` — existing schema, no changes needed. Returns
`[]` (not 404) for a team with no squad rows (e.g. any Ligue 1 team), same
convention as `list_league_teams`.

### 2. `players.py` — extend top-scorers, add top-assists

`list_top_scorers` gains an optional `team_id: int | None` query param
alongside the existing `league` param, and both this endpoint and the new
one add a `goals > 0` / `assists > 0` filter:

```sql
-- top-scorers (existing endpoint, extended)
SELECT * FROM gold.player_performance
WHERE goals > 0
  AND (%(league)s IS NULL OR league = %(league)s)
  AND (%(team_id)s IS NULL OR team_id = %(team_id)s)
ORDER BY goals DESC
LIMIT %(limit)s
```

```sql
-- top-assists (new endpoint, GET /api/players/top-assists)
SELECT * FROM gold.player_performance
WHERE assists > 0
  AND (%(league)s IS NULL OR league = %(league)s)
  AND (%(team_id)s IS NULL OR team_id = %(team_id)s)
ORDER BY assists DESC
LIMIT %(limit)s
```

Both return `list[PlayerPerformance]` (existing schema). `team_id` and
`league` can both be supplied but the frontend never does so today — pages
use one or the other.

## Frontend

### 1. `lib/api.ts`

```ts
getTeamSquad(teamId: number): Promise<PlayerProfile[]>

getTopScorers(opts: { league?: string; teamId?: number; limit?: number }): Promise<PlayerPerformance[]>
getTopAssists(opts: { league?: string; teamId?: number; limit?: number }): Promise<PlayerPerformance[]>
```

`getTopScorers`'s signature changes from positional `(limit, league)` to a
single options object so it can carry `teamId` too — the one existing call
site (`leagues/[league]/page.tsx`) is updated in the same change.
`getTopAssists` is new, mirrors `getTopScorers`.

### 2. New component `components/SquadTable.tsx`

Server Component, props: `{ players: PlayerProfile[] }`. Groups the
already-sorted list by `position` into 4 sections (skips a group entirely if
empty — relevant for Ligue 1 teams with no squad at all, and for edge cases
where a group has zero players). Each row: shirt number, player name (link to
`/players/[id]`), nationality, age. Reuses `components/ui/table.tsx`,
styled consistently with `StandingsTable.tsx`.

### 3. New shared component `components/TopPerformersList.tsx`

Replaces the `<ol>` block currently inlined in
`leagues/[league]/page.tsx`. Props:

```ts
{
  title: string;                 // "Top Scorers" | "Top Assists"
  players: PlayerPerformance[];
  stat: "goals" | "assists";
  statLabel: string;             // "goals" | "assists"
}
```

Renders the numbered list (rank, player name linking to `/players/[id]`,
team name, stat value) exactly as the current league-page markup does. Used
in 4 places: league top scorers, league top assists, team top scorers, team
top assists — avoids duplicating the JSX four times.

### 4. `app/teams/[id]/page.tsx`

Add two `Promise.all`-fetched calls: `getTeamSquad(teamId)`,
`getTopScorers({ teamId, limit: 5 })`, `getTopAssists({ teamId, limit: 5 })`.
New layout, inserted after the existing Form section and before Matches:

- "Squad" section (full width) — `<SquadTable players={squad} />`
- Two-column row: "Top Scorer" / "Top Assist" — each a
  `<TopPerformersList>`, empty-state text ("No data available.") if the list
  is empty, matching the league page's existing empty-state handling.

Matches section unchanged.

### 5. `app/leagues/[league]/page.tsx`

Add `getTopAssists({ limit: 10, league })` to the existing `Promise.all`.
In the right-hand column, directly below the existing Top Scorers section,
add a second `<TopPerformersList>` for Top Assists. Existing Top Scorers
block is refactored to use the same component instead of inline `<ol>`
(behavior-preserving — same data, same rendering, just extracted).

## Error handling

- `getTeamSquad` returning `[]` is a valid, expected state (Ligue 1 teams,
  or a Premier League team not yet crawled) — rendered as empty-state text,
  not an error, consistent with how `gold.player_profile`'s known
  limitations are already documented.
- No new 404 paths: `/api/teams/{team_id}/squad` and the top-scorer/assist
  endpoints all return `200` with `[]` on no rows, matching existing
  list-returning endpoints (`list_league_teams`, `list_top_scorers`) rather
  than the single-row endpoints that 404 (`get_team`, `get_player`).

## Testing

- No new pure-logic helper functions are introduced (the position ordering
  is a SQL `CASE`, not a Python function), so no new unit tests are needed
  beyond the existing `backend/tests/test_queries.py` pattern.
- Manual verification via the running dev stack (`docker compose up`):
  load `/teams/{id}` for a Premier League team (squad + top 5 populated) and
  a Ligue 1 team (squad + top performers empty, no crash), and `/leagues/premier-league`
  (Top Assists renders below Top Scorers with real data).

## Out of scope

- No historical/season-scoped squad (matches `gold.player_profile`'s
  current-squad-only limitation, documented in `docs/gold_data_contract.md`).
- No pagination or "view all" for squad/top-performer lists — squad sizes
  (~20-25) and top-N caps (5/10) are small enough to render in full.
- No change to `gold.player_profile` / `gold.player_performance` schemas or
  the underlying dbt models.
