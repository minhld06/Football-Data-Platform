# Parent Club Display for Loaned Players

Date: 2026-08-03

## Context

No source in this platform (football_data_org, StatBunker, Understat) carries
an explicit loan/status flag — this is a documented limitation in
`docs/gold_data_contract.md` and was accepted as out of scope in
[2026-08-03-squad-display-fixes-design.md](2026-08-03-squad-display-fixes-design.md).
The user wants to surface a loaned player's parent (owning) club anyway,
in both the team squad list and the player's own profile page, e.g. "Jack
Grealish — on loan from Manchester City."

Two signals already exist separately in the pipeline for each
`(player_id, season)`, but are currently collapsed into one `team_id`:

- **Registered club**, from football_data_org's squad crawl
  (`players_base.fdo_team_id` in `transform/models/silver/player_team_season.sql`)
  — currently only surfaced when it wins as the last-resort
  `resolved_via = 'fdo_fallback'` candidate, otherwise discarded.
- **Match-day club**, from Understat/StatBunker stats rows (`team_id` as
  resolved today) — prioritized over the registered club because it
  "correctly attributes loan players to the loan club" (existing model
  comment).

When these two disagree, the player is on loan and the registered club is
the parent club. Confirmed with the user (see prior brainstorming turn):

- Detection is fully automatic, no new seed or crawler — comparing
  `team_id` (match-day) against `parent_team_id` (registered).
- **Known and accepted gap**: a loan to a club outside the crawl's scope
  (e.g. Championship) produces zero Understat/StatBunker rows, so `team_id`
  falls back to `parent_team_id` itself — `team_id == parent_team_id`, no
  mismatch, nothing detected. This is the same gap already documented for
  `resolved_via = 'fdo_fallback'`; this design does not attempt to close it.
- Display is additive: a small "on loan from X" annotation shown only when
  detected, no change to how non-loaned players render.

## Decision 1 — carry `parent_team_id` through `silver.player_team_season`

`transform/models/silver/player_team_season.sql` already computes
`players_base.fdo_team_id` per `player_id` (used inside the `fdo_fallback`
CTE), but only exposes it on the final output when it wins the
priority ranking. Add a left join from `players_base` onto the final
`select`, keyed on `player_id`, so `parent_team_id` is present on every row
regardless of which source resolved `team_id`:

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

`parent_team_id` is `NULL` whenever `players_base.fdo_team_id` is `NULL`
(understat-anchored players with no football_data_org row, or any Ligue 1
player — football_data_org's squad crawl is Premier-League-only per
`crawlers/football_data_org/client.py`). Same nullability condition as the
existing `fdo_fallback` CTE — no new gap introduced.

Grain (`(player_id, season)`) is unchanged. `transform/tests/assert_player_team_season_unique_grain.sql`
is unaffected.

## Decision 2 — derive `is_on_loan` / `parent_team_name` in gold

Both gold player tables get three new columns, computed identically:

- `parent_team_id` — pass through from `silver.player_team_season`
- `parent_team_name` — `silver.teams.team_name` for `parent_team_id`
- `is_on_loan` — `parent_team_id is not null and team_id is distinct from parent_team_id`

**`gold/player_performance.sql`**:

```sql
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

**`gold/player_profile.sql`** — `latest_team` CTE also carries `parent_team_id`
through from the player's latest `player_team_season` row (same
`distinct on (player_id) order by season desc` as today):

```sql
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

No grain change on either model — `player_profile` stays 1 row/`player_id`,
`player_performance` stays 1 row/`(player_id, season)`.

`docs/gold_data_contract.md` gets a new row for `parent_team_id`,
`parent_team_name`, `is_on_loan` in both tables' column tables, plus a
"Known limitations" bullet restating the out-of-scope-loan detection gap
from Decision 1 (already documented elsewhere for `resolved_via`, now
also true here — same root cause, one line cross-referencing the existing
bullet rather than duplicating it).

## Decision 3 — backend surfaces the new fields on `PlayerProfile` only

Both consuming endpoints — `/teams/{id}/squad` (backend/routers/teams.py)
and `/players/{id}` (backend/routers/players.py) — return
`response_model=PlayerProfile` (the squad endpoint populates its team
fields from `gold.player_performance` columns, not `gold.player_profile`,
but shares the same Pydantic schema). Adding the three fields to
`PlayerProfile` alone covers both surfaces the user asked for.

`PlayerPerformance` (used by `/players/{id}/performance` and the
top-scorers/top-assists lists) is **not** touched — out of scope, see
below.

`backend/schemas.py`:

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

`backend/routers/teams.py`, `/teams/{team_id}/squad` — add
`perf.parent_team_id, perf.parent_team_name, perf.is_on_loan` to the
explicit `SELECT` list (both branches share one `query` string, so one
edit covers both).

`backend/routers/players.py`, `/players/{player_id}` — no SQL change
needed (`SELECT *` already picks up the new `gold.player_profile`
columns); the added `PlayerProfile` fields are enough.

## Decision 4 — frontend annotation

`frontend/lib/types.ts` — add the three fields to the `PlayerProfile`
interface, matching the backend schema:

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

`frontend/components/SquadTable.tsx` — inside the existing name `<TableCell>`,
render a muted-text second line when `is_on_loan`:

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

`frontend/app/players/[id]/page.tsx` — subtitle line adds the same
annotation:

```tsx
<p className="text-sm text-muted-foreground">
  {player.position ?? "—"} · {player.team_name ?? "—"}
  {player.is_on_loan && ` (on loan from ${player.parent_team_name})`} ·{" "}
  {player.league}
</p>
```

No change for non-loaned players (`is_on_loan` false) on either surface.

## Testing

- New dbt test `transform/tests/assert_is_on_loan_consistent.sql`
  (`severity='error'`, this is a pure boolean-logic check with no room for
  legitimate exceptions, unlike the warn-severity name-mapping tests):

  ```sql
  select player_id, season, team_id, parent_team_id, is_on_loan
  from {{ ref('player_performance') }}
  where is_on_loan
    and (parent_team_id is null or team_id = parent_team_id)
  ```

  Asserts `is_on_loan = true` never fires without both a non-null
  `parent_team_id` and an actual mismatch — guards the boolean expression
  itself, independent of `_gold.yml` docs.
- `dbt build` — confirm no new failures; `assert_player_team_season_unique_grain`,
  `assert_gold_player_performance_unique_grain`, and `player_profile`'s
  `unique`/`not_null` tests on `player_id` are all unaffected (no grain
  change).
- Spot-check in psql: `select player_name, team_name, parent_team_name,
  is_on_loan from gold.player_performance where is_on_loan limit 20;` —
  confirms at least the loans within crawl scope (EPL/Ligue 1) surface
  correctly, and every returned row has `team_name <> parent_team_name`.
- Spot-check: `select player_name, team_name, parent_team_name, is_on_loan
  from gold.player_profile where player_name ilike '%phillips%';` — the
  known out-of-scope-loan example from the squad-display-fixes design;
  expect `is_on_loan = false` here (confirms the accepted gap, not a
  regression).
- Manual frontend check (dev server): open the squad page for a club with
  at least one in-scope-loan player (if one exists in current data) and
  confirm the "On loan from X" line renders under their name; open that
  player's own `/players/{id}` page and confirm the subtitle shows the
  same annotation; open a few ordinary (non-loaned) players on both
  surfaces and confirm nothing changed for them.

## Out of scope

- Detecting loans to clubs outside the crawl's scope (EPL + Ligue 1) — no
  signal exists in bronze data for this case; same accepted gap as
  `resolved_via = 'fdo_fallback'` in the prior squad-display-fixes design.
- No new crawler, seed file, or manually-maintained loan mapping — this
  remains a derived display-layer signal, not a real "loan" fact from any
  source.
- `PlayerPerformance` schema, `/players/{id}/performance`, and the
  top-scorers/top-assists lists — not touched; the user's request was
  scoped to the squad list and the player's own profile page only.
- No change to `gold.team_profile` or any team-facing page — this is
  purely a player-facing annotation.
