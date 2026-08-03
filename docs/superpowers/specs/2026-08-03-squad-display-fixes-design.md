# Squad/Top-Performer Display Fixes

Date: 2026-08-03

## Context

Three display issues raised by the user while reviewing the team page built in
[2026-07-29-team-squad-top-performers-design.md](2026-07-29-team-squad-top-performers-design.md)
and the season-scoped team resolution just shipped in
[2026-08-03-player-identity-season-team-design.md](2026-08-03-player-identity-season-team-design.md):

1. `TopPerformersList` shows `(team_name)` next to every player on the team
   page — redundant there since every player on that list already belongs to
   the page's own team. (The same component is also used on the league page,
   where `team_name` is not redundant — players there come from different
   clubs.)
2. Players who exist only via understat (no football_data_org row — the
   `player_id + 100000000` id space from the 2026-08-03 identity design) have
   `NULL` `position`, so they land in `SquadTable.tsx`'s catch-all "Other"
   group. Confirmed by reading raw understat payloads
   (`data/raw/understat/player_stats/`): understat's own `position` field
   (e.g. `"D M S"`, `"F S"`, `"GK"`) is present but currently dropped —
   `stg_understat__player_stats.sql` never selects it.
3. Players on loan to a club outside the crawl's scope (EPL + Ligue 1) — e.g.
   Kalvin Phillips, loaned from Manchester City to a Championship club —
   still appear in Man City's squad. Root cause: `silver/player_team_season.sql`'s
   fallback-to-football_data_org-roster path (`resolved_via = 'fdo_fallback'`,
   used when a player has zero understat/statbunker rows for the season) is
   indistinguishable, by design, between "genuinely unused bench player" and
   "loaned to an uncrawled league" — both present as zero stats rows. This
   fallback was accepted as a deliberate trade-off in the 2026-08-03 identity
   design; this design revisits that trade-off specifically for squad
   *display* (see Decision 3 below — confirmed with the user that hiding both
   cases together is an acceptable cost).

## Decision 1 — drop team name from the team-page top-performer lists

`frontend/components/TopPerformersList.tsx` gains an optional prop:

```ts
{
  title: string;
  players: PlayerPerformance[];
  stat: "goals" | "assists";
  statLabel: string;
  showTeamName?: boolean; // default true
}
```

The `<span className="text-muted-foreground">({p.team_name})</span>` block
renders only when `showTeamName` is not `false`.

- `frontend/app/teams/[id]/page.tsx` — both `TopPerformersList` calls pass
  `showTeamName={false}`.
- `frontend/app/leagues/[league]/page.tsx` — unchanged (prop omitted, defaults
  to `true`).

No backend/dbt changes.

## Decision 2 — backfill `position` for understat-anchored players

Understat's `position` field lists every position tag the player has
appeared under, ordered by frequency, e.g. `"D M S"`. Checked every distinct
value across current raw data (16 values, ~1,980 rows): the **leading token**
alone is enough to classify correctly in every case except the single value
`"S"` (appears alone, meaning "only ever recorded coming on as a substitute,"
no primary position known — 282 of ~1,980 rows, but far fewer distinct
players since the same player recurs across daily crawl snapshots).

New macro `transform/macros/normalize_understat_position.sql`:

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

Changes:

- `stg_understat__player_stats.sql` — extract `row_json ->> 'position'` and
  apply the macro, exposed as a new `position` column alongside the existing
  stat columns.
- `silver/players.sql` — carry `position` through the `understat_distinct` /
  `understat_matched_to_fdo` CTEs (currently these only carry
  `raw_player_name`, `understat_id`, `team_id`, `league`, `ingestion_time`),
  and use the carried value in `understat_only` instead of the hardcoded
  `cast(null as text) as position`. Players who *do* match an existing
  football_data_org row keep using football_data_org's `position` unchanged
  (unaffected — `fdo_players` CTE is not touched).
- `docs/gold_data_contract.md` — update the `position` row for
  `gold.player_profile` to note understat is now a secondary source for
  understat-anchored players, and that a bare `"S"` tag (no primary position
  recorded) still results in `NULL`/"Other".

No frontend or backend changes — `SquadTable.tsx`'s "Other" grouping and
`backend/routers/teams.py`'s position `CASE` ordering already handle any
non-NULL value in the same 4-value vocabulary transparently.

## Decision 3 — exclude `fdo_fallback`-only players from the squad list

`silver/player_team_season.sql` already tags how each `(player_id, season)`
row's `team_id` was resolved via a `resolved_via` column
(`'understat'` / `'statbunker'` / `'fdo_fallback'`), but this column is not
currently exposed in `gold.player_performance`. Confirmed with the user: it's
acceptable that this also hides genuinely-unused bench players / new
signings with zero minutes this season, since that population is
indistinguishable from an out-of-scope loan using data this platform crawls
(no loan/status field exists anywhere in bronze raw data). Scope is
deliberately limited to the squad list; a loaned player's own profile page
(`gold.player_profile`, keyed on `player_id` alone, not season-scoped) is
unaffected and keeps showing the parent club — that remains correct
"registered club" information, not a squad-membership claim.

Changes:

- `gold/player_performance.sql` — add `pts.resolved_via` to the select list.
- `backend/routers/teams.py`, `/teams/{team_id}/squad` — add
  `AND perf.resolved_via <> 'fdo_fallback'` to the `WHERE` clause (both the
  explicit-season and default-latest-season branches).
- `docs/gold_data_contract.md` — document the new `resolved_via` column on
  `gold.player_performance` and the squad-list filtering behavior, including
  the explicit trade-off (a benched/unused player with genuinely zero
  minutes this season also disappears from the squad list, not just loanees).

No grain change (`(player_id, season)` unchanged) — the existing
`assert_gold_player_performance_unique_grain.sql` test is unaffected.

## Testing

- `dbt build` — confirm no new test failures; `resolved_via` is a pass-through
  column, doesn't touch grain or existing tests.
- Spot-check in psql: `select player_name, position from gold.player_profile
  where player_id > 100000000 and position is not null limit 20;` — should
  return understat-anchored players with a backfilled position.
- Spot-check: `select * from gold.player_performance where player_name ilike
  '%phillips%' and resolved_via = 'fdo_fallback';` — confirms the row exists
  and is now excluded by the squad query
  (`/teams/{man_city_id}/squad` should no longer list Kalvin Phillips).
- Manual frontend check (dev server): `/teams/{id}` — top scorer/assist show
  player names without `(team name)`; squad table shows fewer/no players in
  "Other"; a known loaned-out player (if one still exists in current data) is
  absent from the squad list. `/leagues/{league}` — top scorer/assist
  unchanged, still show `(team name)`.

## Out of scope

- `gold.player_profile.team_id` / the player's own profile page — not
  filtered by `resolved_via`; still shows the parent club for a loaned player.
- No new crawler or loan/status field — this remains a display-layer proxy,
  not a real signal.
- No change to `SquadTable.tsx`'s "Other" grouping logic itself — a residual
  "Other" group (bare `"S"` position tag) can still legitimately appear.
