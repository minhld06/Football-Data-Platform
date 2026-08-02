# Player Identity & Season-Scoped Team Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make squad/top-scorer/player-performance pages reflect who actually
played for a team during a given EPL season (season 2025-2026 today),
including players loaned to another EPL club, instead of
football_data_org's undated "current roster" snapshot — fixing both missing
players (e.g. Mohamed Salah, absent from fdo entirely) and wrong-team
players (e.g. Jack Grealish showing as Manchester City while his stat line is
actually his Everton loan).

**Architecture:** Two new/rewritten dbt models replace the current
fdo-only identity + always-current-team logic:
- `silver/players.sql` (rewritten) — player identity, unioning
  football_data_org's numeric `player_id` with a new fallback identity
  (understat's own native player id + a fixed offset) for players
  football_data_org has no row for at all.
- `silver/player_team_season.sql` (new) — one row per `(player_id, season)`
  with the correct team for that season (understat's team wins when
  present, then statbunker, then football_data_org's team as a last-resort
  fallback for players with zero stats that season) **and** that season's
  stat columns from both sources, so `gold/player_performance.sql` becomes a
  thin passthrough.

**Tech Stack:** dbt-core + dbt-postgres (existing), FastAPI backend
(existing) — no new libraries.

## Global Constraints

- Every dbt model change must pass `dbt build` cleanly (existing tables/tests
  unaffected unless this plan explicitly changes them).
- Preserve the existing, already-committed Savinho display-name-override
  mechanism (`transform/seeds/player_display_name_overrides.csv`,
  `transform/seeds/player_name_map.csv` rows for `understat,Sávio,65,146352`
  and `statbunker,Savinho,65,146352`) — do not remove or regress it.
- `/players/{id}` and `/teams/{id}` routes must keep working unchanged for
  the ~588 players/20 teams football_data_org already covers (no breaking
  change to existing numeric `player_id` values).
- Follow existing code style: `{{ ref(...) }}`, `{{ normalize_player_name(...) }}`
  macro, `row_number() over (... order by ingestion_time desc)` dedup
  pattern, warn-severity tests for name-matching gaps (never hard-fail
  `dbt build` on an unmapped name — that's expected, routine drift).

---

### Task 1: Add understat's native id to `stg_understat__player_stats`, drop its own player_id resolution

**Context for the implementer:** Understat's raw JSON already carries its own
stable numeric player id (e.g. `{"id": "8260", "player_name": "Erling Haaland", ...}`),
currently discarded. We need this id to anchor identity for players
football_data_org has no row for. Separately, this model currently resolves
its *own* `player_id` by joining `{{ ref('players') }}` (`silver.players`) —
that has to be removed here, because `silver/players.sql` is about to start
reading *from* this model (to build the identity list in Task 3), and dbt
does not allow circular `ref()`s. Player-id resolution for stat rows moves
to Task 4's new model instead, which is downstream of both.

**Files:**
- Modify: `transform/models/staging/stg_understat__player_stats.sql`
- Modify: `transform/models/staging/_staging.yml:80-97`

- [ ] **Step 1: Rewrite the model**

Replace the full contents of `transform/models/staging/stg_understat__player_stats.sql`:

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
        (r.row_json ->> 'xA')::numeric as xa
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
    round(rt.xa / nullif(rt.minutes, 0)::numeric * 90, 3) as xa90
from resolved_team rt
```

**Interfaces:**
- Produces: columns `season, league, ingestion_time, team_id, raw_player_name,
  understat_id, apps, minutes, goals, assists, xg, xa, xg90, xa90` (no more
  `player_id` column — removed).

- [ ] **Step 2: Update the schema doc**

In `transform/models/staging/_staging.yml`, replace the `stg_understat__player_stats`
entry (lines 80-97) with:

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
                  circular ref if this model tried to depend on it too)."
    columns:
      - name: raw_player_name
        tests:
          - not_null
```

- [ ] **Step 3: Run the model and check the new column**

```bash
cd transform
dbt run --select stg_understat__player_stats
```
Expected: `Completed successfully`.

```bash
docker compose exec -T postgres psql -U postgres -d football -c "select raw_player_name, understat_id from silver.stg_understat__player_stats where raw_player_name ilike '%haaland%';"
```
Expected: one row, `understat_id` = `8260`.

- [ ] **Step 4: Commit**

```bash
git add transform/models/staging/stg_understat__player_stats.sql transform/models/staging/_staging.yml
git commit -m "feat: capture understat's native player id, drop its player_id resolution"
```

---

### Task 2: Drop player_id resolution from `stg_statbunker__player_stats`

**Context for the implementer:** Same circular-dependency reason as Task 1.
statbunker has no native id of its own (checked directly: of 280 statbunker
premier-league players, all 280 match an existing understat player by name
after accounting for spelling/nickname differences — statbunker never
anchors a *new* identity), so unlike Task 1 there's no id to add here, just
the existing `player_id` resolution to remove.

**Files:**
- Modify: `transform/models/staging/stg_statbunker__player_stats.sql`
- Modify: `transform/models/staging/_staging.yml:58-79`

- [ ] **Step 1: Rewrite the model**

Replace the full contents of `transform/models/staging/stg_statbunker__player_stats.sql`:

```sql
with player_stats_raw as (
    select season, league, ingestion_time, payload
    from {{ source('bronze', 'raw_documents') }}
    where source = 'statbunker'
      and entity_type = 'player_stats'
),

player_stats_rows as (
    select
        season,
        league,
        ingestion_time,
        jsonb_array_elements(payload) as row_json
    from player_stats_raw
)

select
    r.season,
    r.league,
    r.ingestion_time,
    m.team_id,
    r.row_json ->> 'player' as raw_player_name,
    coalesce(nullif(r.row_json ->> 'goals', '-'), '0')::int as goals,
    coalesce(nullif(r.row_json ->> 'fh', '-'), '0')::int as fh,
    coalesce(nullif(r.row_json ->> 'sh', '-'), '0')::int as sh,
    coalesce(nullif(r.row_json ->> 'fs', '-'), '0')::int as fs,
    coalesce(nullif(r.row_json ->> 'ls', '-'), '0')::int as ls,
    coalesce(nullif(r.row_json ->> 'h', '-'), '0')::int as h,
    coalesce(nullif(r.row_json ->> 'a', '-'), '0')::int as a
from player_stats_rows r
left join {{ ref('team_name_map') }} m
    on m.source = 'statbunker'
   and m.raw_team_name = r.row_json ->> 'team'
```

**Interfaces:**
- Produces: columns `season, league, ingestion_time, team_id, raw_player_name,
  goals, fh, sh, fs, ls, h, a` (no more `player_id` column — removed).

- [ ] **Step 2: Update the schema doc**

In `transform/models/staging/_staging.yml`, replace the `stg_statbunker__player_stats`
entry (lines 58-79) with:

```yaml
  - name: stg_statbunker__player_stats
    description: "Staging model for StatBunker top-scorer data. Grain is 1 row/player/snapshot.
                  Scraped per-club (statbunker has no competition-wide top-scorers page). team_id
                  resolved via team_name_map.csv (NULL if unmapped). This model no longer resolves
                  player_id itself — that moved to silver/player_team_season.sql (would create a
                  circular ref if this model depended on silver.players). statbunker has no native
                  player id of its own; every statbunker player has been confirmed to also appear in
                  understat under some spelling, so it never anchors a new identity, only supplies
                  supplementary stat columns (fh/sh/fs/ls/h/a) once player_team_season resolves whose
                  row this is."
    columns:
      - name: raw_player_name
        tests:
          - not_null
```

- [ ] **Step 3: Run the model**

```bash
cd transform
dbt run --select stg_statbunker__player_stats
```
Expected: `Completed successfully`.

- [ ] **Step 4: Commit**

```bash
git add transform/models/staging/stg_statbunker__player_stats.sql transform/models/staging/_staging.yml
git commit -m "refactor: drop player_id resolution from stg_statbunker__player_stats"
```

---

### Task 3: Rewrite `silver/players.sql` — hybrid identity (fdo id, or understat id + offset)

**Context for the implementer:** This is Model A from the design spec
(`docs/superpowers/specs/2026-08-03-player-identity-season-team-design.md`).
Priority per person: football_data_org's `player_id` if they have one;
otherwise understat's native id + a fixed `100000000` offset (keeps the two
id spaces from ever colliding — observed football_data_org ids top out
around 270,684, so 100 million of headroom is safe). Dedup fdo↔understat via
`normalize_player_name()` — checked against fdo's **raw** name (before the
existing display-name override), not the overridden one, otherwise the
already-committed Savinho override (fdo raw name `"Sávio"` → displayed as
`"Savinho"`) would make this model think understat's `"Sávio"` row has no fdo
match and wrongly mint a second, duplicate identity for the same person.
`transform/seeds/player_name_map.csv` is also checked here (not just
normalization) — same seed file used everywhere else in this project,
already has the compensating `understat,Sávio,65,146352` row from the
existing Savinho fix.

**Files:**
- Modify: `transform/models/silver/players.sql`
- Modify: `transform/models/silver/_silver.yml:49-60`

**Interfaces:**
- Consumes: `stg_football_data_org__players` (`player_id, player_name,
  position, date_of_birth, nationality, shirt_number, team_id, league,
  ingestion_time`), `stg_understat__player_stats` (`raw_player_name,
  understat_id, league, ingestion_time` — from Task 1), `player_name_map`
  (`source, raw_player_name, team_id, player_id`), `player_display_name_overrides`
  (`player_id, display_name`).
- Produces: `player_id, player_name, position, date_of_birth, nationality,
  shirt_number, team_id, league, ingestion_time` — same column list as
  before (backward compatible), but `player_id` values now include the
  `understat_id + 100000000` space, and `team_id`/`position`/`date_of_birth`/
  `nationality`/`shirt_number` are `NULL` for those rows (no fdo bio data
  exists for them).

- [ ] **Step 1: Rewrite the model**

Replace the full contents of `transform/models/silver/players.sql`:

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

understat_distinct as (
    select distinct on ({{ normalize_player_name('raw_player_name') }})
        raw_player_name,
        understat_id,
        team_id,
        league,
        ingestion_time
    from {{ ref('stg_understat__player_stats') }}
    where understat_id is not null
    order by {{ normalize_player_name('raw_player_name') }}, ingestion_time desc
),

understat_matched_to_fdo as (
    select
        u.raw_player_name,
        u.understat_id,
        u.league,
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
        cast(null as text) as position,
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

- [ ] **Step 2: Update the schema doc**

In `transform/models/silver/_silver.yml`, replace the `players` entry
(lines 49-60) with:

```yaml
  - name: players
    description: "Player identity. Grain is 1 row/player_id. player_id is either football_data_org's
                  own numeric id (for the ~588 players it covers), or understat's native player id
                  + a fixed 100000000 offset for players understat knows about but football_data_org
                  has zero row for (e.g. Mohamed Salah) — see
                  docs/superpowers/specs/2026-08-03-player-identity-season-team-design.md. Dedup
                  between the two sources is by normalize_player_name() against football_data_org's
                  raw (pre-display-name-override) name, plus player_name_map.csv for exceptions.
                  Understat-anchored rows have NULL position/date_of_birth/nationality/shirt_number/
                  team_id — football_data_org is the only source with bio fields, and team_id is now
                  resolved per-season in silver.player_team_season, not stored here."
    columns:
      - name: player_id
        tests:
          - unique
          - not_null
      - name: player_name
        tests:
          - not_null
```

- [ ] **Step 3: Run and test the model**

```bash
cd transform
dbt build --select players
```
Expected: `Completed successfully`, `unique`/`not_null` tests on `player_id` pass.

- [ ] **Step 4: Spot-check Salah now has an identity row**

```bash
docker compose exec -T postgres psql -U postgres -d football -c "select player_id, player_name, team_id from silver.players where player_name ilike '%salah%';"
```
Expected: one row, `player_id` >= `100000000`, `team_id` is `NULL` (resolved
later, per-season, in Task 4).

- [ ] **Step 5: Spot-check Savinho still resolves to the existing fdo id (no duplicate)**

```bash
docker compose exec -T postgres psql -U postgres -d football -c "select player_id, player_name from silver.players where player_name ilike '%savinho%' or player_name ilike '%s%vio%';"
```
Expected: exactly **one** row: `player_id = 146352`, `player_name = 'Savinho'`
(the existing override) — not two rows.

- [ ] **Step 6: Commit**

```bash
git add transform/models/silver/players.sql transform/models/silver/_silver.yml
git commit -m "feat: anchor player identity on understat's native id when football_data_org has no row"
```

---

### Task 4: New `silver/player_team_season.sql` — season-scoped team + stats resolution

**Context for the implementer:** This is Model B from the design spec, plus
a refinement discovered while planning: rather than only resolving *team*
per `(player_id, season)` and having `gold/player_performance.sql`
independently re-derive stat attachment, this model resolves `player_id` for
every statbunker/understat row (same joins as Task 3's fdo-matching, applied
per source) **and** carries the stat columns through directly — so
`gold/player_performance.sql` (Task 7) becomes a thin passthrough instead of
re-implementing the same matching logic a third time.

Team resolution priority per `(player_id, season)`: understat's team_id (if
not null) → statbunker's team_id (if not null) → football_data_org's
current team_id as a last-resort fallback (for players with zero stats that
season, e.g. an unused third-choice keeper). A player+season with zero
resolvable team (e.g. an understat-only identity whose one row that season
has a NULL team_id from a mid-season-transfer string, and no fdo row to fall
back to) simply produces no row for that season — consistent with this
project's existing "silently missing, not wrong" contract for unmapped data.

**Files:**
- Create: `transform/models/silver/player_team_season.sql`
- Modify: `transform/models/silver/_silver.yml` (add new entry)
- Create: `transform/tests/assert_player_team_season_unique_grain.sql`
- Create: `transform/tests/assert_player_team_season_source_agreement.sql`

**Interfaces:**
- Consumes: `players` (Task 3's `player_id, player_name, team_id, league`),
  `stg_understat__player_stats`, `stg_statbunker__player_stats`,
  `player_name_map`.
- Produces: `player_id, season, league, team_id, resolved_via
  ('understat'|'statbunker'|'fdo_fallback'), source_disagreement (bool),
  apps, minutes, understat_goals, assists, xg, xa, xg90, xa90,
  statbunker_goals` — grain 1 row per `(player_id, season)`.

- [ ] **Step 1: Write the model**

Create `transform/models/silver/player_team_season.sql`:

```sql
{{ config(materialized='table') }}

with players_base as (
    select player_id, player_name, team_id as fdo_team_id, league as fdo_league
    from {{ ref('players') }}
),

understat_matched as (
    select
        u.season,
        u.league,
        u.team_id,
        coalesce(pm.player_id, p.player_id) as player_id,
        u.apps,
        u.minutes,
        u.goals,
        u.assists,
        u.xg,
        u.xa,
        u.xg90,
        u.xa90,
        u.ingestion_time
    from {{ ref('stg_understat__player_stats') }} u
    left join {{ ref('player_name_map') }} pm
        on pm.source = 'understat'
       and pm.raw_player_name = u.raw_player_name
       and pm.team_id = u.team_id
    left join players_base p
        on {{ normalize_player_name('p.player_name') }} = {{ normalize_player_name('u.raw_player_name') }}
),

understat_ranked as (
    select *, row_number() over (
        partition by player_id, season order by ingestion_time desc
    ) as rn
    from understat_matched
    where player_id is not null
),

understat_latest as (
    select * from understat_ranked where rn = 1
),

statbunker_matched as (
    select
        s.season,
        s.league,
        s.team_id,
        coalesce(pm.player_id, p.player_id) as player_id,
        s.goals,
        s.ingestion_time
    from {{ ref('stg_statbunker__player_stats') }} s
    left join {{ ref('player_name_map') }} pm
        on pm.source = 'statbunker'
       and pm.raw_player_name = s.raw_player_name
       and pm.team_id = s.team_id
    left join players_base p
        on {{ normalize_player_name('p.player_name') }} = {{ normalize_player_name('s.raw_player_name') }}
),

statbunker_ranked as (
    select *, row_number() over (
        partition by player_id, season order by ingestion_time desc
    ) as rn
    from statbunker_matched
    where player_id is not null
),

statbunker_latest as (
    select * from statbunker_ranked where rn = 1
),

all_seasons as (
    select distinct season from understat_latest
    union
    select distinct season from statbunker_latest
),

fdo_fallback as (
    select
        p.player_id,
        s.season,
        p.fdo_league as league,
        p.fdo_team_id as team_id
    from players_base p
    cross join all_seasons s
    where p.fdo_team_id is not null
),

team_candidates as (
    select player_id, season, league, team_id, 1 as source_priority, 'understat' as resolved_via
    from understat_latest
    where team_id is not null
    union all
    select player_id, season, league, team_id, 2 as source_priority, 'statbunker' as resolved_via
    from statbunker_latest
    where team_id is not null
    union all
    select player_id, season, league, team_id, 3 as source_priority, 'fdo_fallback' as resolved_via
    from fdo_fallback
),

team_ranked as (
    select *, row_number() over (
        partition by player_id, season order by source_priority asc
    ) as rn
    from team_candidates
),

team_resolved as (
    select player_id, season, league, team_id, resolved_via
    from team_ranked
    where rn = 1
),

disagreement as (
    select
        u.player_id,
        u.season,
        (u.team_id is distinct from sb.team_id) as source_disagreement
    from understat_latest u
    join statbunker_latest sb
        on sb.player_id = u.player_id and sb.season = u.season
)

select
    tr.player_id,
    tr.season,
    tr.league,
    tr.team_id,
    tr.resolved_via,
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
left join disagreement d on d.player_id = tr.player_id and d.season = tr.season
left join understat_latest us on us.player_id = tr.player_id and us.season = tr.season
left join statbunker_latest sb on sb.player_id = tr.player_id and sb.season = tr.season
```

- [ ] **Step 2: Add the schema doc entry**

In `transform/models/silver/_silver.yml`, append:

```yaml
  - name: player_team_season
    description: "Which team a player was on, and their stats, for a given season — the season-scoped
                  replacement for trusting football_data_org's undated 'current roster' as if it meant
                  'this season's roster'. Grain is 1 row/(player_id, season). team_id priority per row:
                  understat's team (freshest, correctly attributes loan players to the loan club) →
                  statbunker's team → football_data_org's current team_id as a last-resort fallback
                  (only used when a player has zero stats rows for that season, e.g. an unused
                  third-choice keeper). resolved_via records which one won. source_disagreement is true
                  when understat and statbunker both have a row for this player+season but report
                  different teams (a genuine mid-season transfer within one season, distinct from the
                  between-seasons case this model exists to fix) — see
                  assert_player_team_season_source_agreement (warn). Stat columns
                  (apps/minutes/understat_goals/assists/xg/xa/xg90/xa90/statbunker_goals) are carried
                  through directly so gold.player_performance doesn't need to re-derive player_id
                  matching a third time."
    columns:
      - name: player_id
        tests:
          - not_null
      - name: season
        tests:
          - not_null
```

- [ ] **Step 3: Write the grain test**

Create `transform/tests/assert_player_team_season_unique_grain.sql`:

```sql
select player_id, season, count(*) as n
from {{ ref('player_team_season') }}
group by player_id, season
having count(*) > 1
```

- [ ] **Step 4: Write the source-agreement warn test**

Create `transform/tests/assert_player_team_season_source_agreement.sql`:

```sql
{{ config(severity='warn') }}

select player_id, season
from {{ ref('player_team_season') }}
where source_disagreement = true
```

- [ ] **Step 5: Run and test the model**

```bash
cd transform
dbt build --select player_team_season
```
Expected: `Completed successfully`; note (don't necessarily fix) any warnings
from `assert_player_team_season_source_agreement`.

- [ ] **Step 6: Spot-check Grealish resolves to Everton for 2025-2026**

```bash
docker compose exec -T postgres psql -U postgres -d football -c "
select pts.player_id, p.player_name, pts.season, pts.team_id, t.team_name, pts.resolved_via
from silver.player_team_season pts
join silver.players p on p.player_id = pts.player_id
join silver.teams t on t.team_id = pts.team_id
where p.player_name ilike '%grealish%';
"
```
Expected: `team_name = 'Everton FC'`, `resolved_via = 'understat'` (or
`'statbunker'`), for `season = '2025-2026'`.

- [ ] **Step 7: Spot-check Salah resolves to Liverpool for 2025-2026**

```bash
docker compose exec -T postgres psql -U postgres -d football -c "
select pts.player_id, p.player_name, pts.season, t.team_name, pts.understat_goals, pts.assists
from silver.player_team_season pts
join silver.players p on p.player_id = pts.player_id
join silver.teams t on t.team_id = pts.team_id
where p.player_name ilike '%salah%';
"
```
Expected: `team_name = 'Liverpool FC'`, `understat_goals = 7`, `assists = 7`.

- [ ] **Step 8: Commit**

```bash
git add transform/models/silver/player_team_season.sql transform/models/silver/_silver.yml transform/tests/assert_player_team_season_unique_grain.sql transform/tests/assert_player_team_season_source_agreement.sql
git commit -m "feat: add season-scoped team+stats resolution model"
```

---

### Task 5: Rewrite `assert_player_names_mapped` for the new architecture

**Context for the implementer:** The existing test checks
`stg_statbunker__player_stats.player_id`/`stg_understat__player_stats.player_id`
for `NULL` — those columns no longer exist after Tasks 1-2 (moved to Task
4's model), so this test would fail to compile as-is. Rewrite it to
independently re-derive the same match (same pattern the old staging models
used) so it still surfaces names that fail to resolve to any `player_id`.

**Files:**
- Modify: `transform/tests/assert_player_names_mapped.sql`

- [ ] **Step 1: Rewrite the test**

Replace the full contents of `transform/tests/assert_player_names_mapped.sql`:

```sql
{{ config(severity='warn') }}

with understat_check as (
    select
        'understat' as source,
        u.raw_player_name,
        coalesce(pm.player_id, p.player_id) as player_id
    from {{ ref('stg_understat__player_stats') }} u
    left join {{ ref('player_name_map') }} pm
        on pm.source = 'understat'
       and pm.raw_player_name = u.raw_player_name
       and pm.team_id = u.team_id
    left join {{ ref('players') }} p
        on {{ normalize_player_name('p.player_name') }} = {{ normalize_player_name('u.raw_player_name') }}
),

statbunker_check as (
    select
        'statbunker' as source,
        s.raw_player_name,
        coalesce(pm.player_id, p.player_id) as player_id
    from {{ ref('stg_statbunker__player_stats') }} s
    left join {{ ref('player_name_map') }} pm
        on pm.source = 'statbunker'
       and pm.raw_player_name = s.raw_player_name
       and pm.team_id = s.team_id
    left join {{ ref('players') }} p
        on {{ normalize_player_name('p.player_name') }} = {{ normalize_player_name('s.raw_player_name') }}
)

select distinct source, raw_player_name
from (
    select * from understat_check
    union all
    select * from statbunker_check
) unmapped_check
where player_id is null
```

Note: for understat rows this can now only be `NULL` if
`normalize_player_name` fails to match **and** there's no
`player_name_map` row — since Task 3 already anchors every understat player
to *some* `player_id` (either fdo's or the offset one). A `NULL` here means
the name in this specific statbunker/understat row doesn't even
normalize-match the version of the name understat itself supplied to
`silver.players` — practically, this should stay close to empty; a nonzero
result likely means a genuine second spelling variant slipped through and a
`player_name_map.csv` row is needed exactly as before.

- [ ] **Step 2: Run the test**

```bash
cd transform
dbt test --select assert_player_names_mapped
```
Expected: runs without a compile error; note any warned rows.

- [ ] **Step 3: Commit**

```bash
git add transform/tests/assert_player_names_mapped.sql
git commit -m "fix: rewrite assert_player_names_mapped for the new identity architecture"
```

---

### Task 6: Rewrite `gold/player_profile.sql` — convenience "current team" from player_team_season

**Files:**
- Modify: `transform/models/gold/player_profile.sql`
- Modify: `transform/models/gold/_gold.yml:33-44`

**Interfaces:**
- Consumes: `players` (Task 3), `player_team_season` (Task 4), `teams`.
- Produces: same columns as before (`player_id, player_name, position,
  nationality, date_of_birth, age, shirt_number, team_id, team_name,
  league`) — grain still 1 row/`player_id`. `team_id`/`team_name` now come
  from the player's most recent season in `player_team_season` (falls back
  to nothing / `NULL` if a player somehow has zero `player_team_season` rows
  — shouldn't happen for any player who has ever had a stats row or an fdo
  team, but not hard-guaranteed for a brand new fdo signing crawled after
  the season's stats already finished and before any next-season stats
  exist).

- [ ] **Step 1: Rewrite the model**

Replace the full contents of `transform/models/gold/player_profile.sql`:

```sql
{{ config(materialized='view') }}

with latest_team as (
    select distinct on (player_id)
        player_id, team_id, league
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
    coalesce(lt.league, p.league) as league
from {{ ref('players') }} p
left join latest_team lt on lt.player_id = p.player_id
left join {{ ref('teams') }} t on t.team_id = lt.team_id
```

Note: `season` sorts correctly as a plain string in `YYYY-YYYY` format, so
`order by ... season desc` picks the latest season without extra parsing.

- [ ] **Step 2: Update the schema doc**

In `transform/models/gold/_gold.yml`, replace the `player_profile` entry
(lines 33-44) with:

```yaml
  - name: player_profile
    description: "One row per player: identity + a convenience 'most recent season's team' (not a
                  season-scoped fact — see gold.player_performance for that). Grain is 1 row/player_id.
                  Logic: player identity from silver.players, team_id/team_name/league from the
                  player's latest row in silver.player_team_season (max(season)). Materialized as a
                  view (not table like other gold models) so age stays correct at query time instead
                  of going stale between dbt builds.
                  "
    columns:
      - name: player_id
        tests:
          - unique
          - not_null
```

- [ ] **Step 3: Run and spot-check**

```bash
cd transform
dbt build --select player_profile
```
Expected: `Completed successfully`.

```bash
docker compose exec -T postgres psql -U postgres -d football -c "select * from gold.player_profile where player_name ilike '%salah%';"
docker compose exec -T postgres psql -U postgres -d football -c "select * from gold.player_profile where player_name ilike '%grealish%';"
```
Expected: Salah row now exists (`team_name = 'Liverpool FC'`); Grealish's
`team_name` is now `'Everton FC'` (previously `'Manchester City FC'`).

- [ ] **Step 4: Commit**

```bash
git add transform/models/gold/player_profile.sql transform/models/gold/_gold.yml
git commit -m "fix: player_profile shows the season-resolved current team, not fdo's undated roster"
```

---

### Task 7: Rewrite `gold/player_performance.sql` — grain becomes `(player_id, season)`

**Files:**
- Modify: `transform/models/gold/player_performance.sql`
- Modify: `transform/models/gold/_gold.yml:45-58`
- Create: `transform/tests/assert_gold_player_performance_unique_grain.sql`

**Interfaces:**
- Consumes: `player_team_season` (Task 4), `players`, `teams`.
- Produces: `player_id, player_name, season, team_id, team_name, league,
  goals, assists, apps, minutes, xg, xa, xg90, xa90` — grain now
  `(player_id, season)` (was `player_id`).

- [ ] **Step 1: Rewrite the model**

Replace the full contents of `transform/models/gold/player_performance.sql`:

```sql
{{ config(materialized='table') }}

select
    pts.player_id,
    p.player_name,
    pts.season,
    pts.team_id,
    t.team_name,
    pts.league,
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

- [ ] **Step 2: Write the new grain test**

Create `transform/tests/assert_gold_player_performance_unique_grain.sql`:

```sql
select player_id, season, count(*) as n
from {{ ref('player_performance') }}
group by player_id, season
having count(*) > 1
```

- [ ] **Step 3: Update the schema doc**

In `transform/models/gold/_gold.yml`, replace the `player_performance` entry
(lines 45-58) with:

```yaml
  - name: player_performance
    description: "Player stats: goals (statbunker) + assists/apps/minutes/xG/xA (understat), with the
                  team they were attributed to *for that season* (from silver.player_team_season).
                  Grain is 1 row/(player_id, season) — changed from 1 row/player_id so a player's team
                  can differ correctly between seasons (and, for the same season, be a loan club
                  rather than football_data_org's parent-club roster). See
                  assert_gold_player_performance_unique_grain.sql for the grain test (a dedicated file,
                  unlike player_profile's single-column grain, because this grain is composite).
                  "
    columns:
      - name: player_id
        tests:
          - not_null
      - name: season
        tests:
          - not_null
```

(Removed the `unique` test on `player_id` alone — no longer the grain; grain
uniqueness is now enforced by the new `assert_gold_player_performance_unique_grain.sql`.)

- [ ] **Step 4: Run and test**

```bash
cd transform
dbt build --select player_performance
```
Expected: `Completed successfully`, grain test passes.

- [ ] **Step 5: Spot-check Grealish's stats now show under Everton**

```bash
docker compose exec -T postgres psql -U postgres -d football -c "select * from gold.player_performance where player_name ilike '%grealish%';"
```
Expected: `team_name = 'Everton FC'`, `season = '2025-2026'`, `goals = 2`,
`assists = 6`, `apps = 20`, `minutes = 1645` (previously showed
`'Manchester City FC'` with the same stat line — now the team is correct).

- [ ] **Step 6: Commit**

```bash
git add transform/models/gold/player_performance.sql transform/models/gold/_gold.yml transform/tests/assert_gold_player_performance_unique_grain.sql
git commit -m "feat: player_performance grain becomes (player_id, season) with season-correct team"
```

---

### Task 8: Full `dbt build` verification pass

**Files:** none (verification only).

- [ ] **Step 1: Run the full build**

```bash
cd transform
dbt build
```
Expected: `Completed successfully` for all models; note (don't block on) any
`warn`-severity test output.

- [ ] **Step 2: Confirm no regressions on unrelated gold models**

```bash
docker compose exec -T postgres psql -U postgres -d football -c "select count(*) from gold.league_standings;"
docker compose exec -T postgres psql -U postgres -d football -c "select count(*) from gold.match_results;"
docker compose exec -T postgres psql -U postgres -d football -c "select count(*) from gold.team_profile;"
```
Expected: same row counts as before this plan (these models are untouched).

- [ ] **Step 3: Confirm the count of previously-missing players**

```bash
docker compose exec -T postgres psql -U postgres -d football -c "
select count(*) from gold.player_profile where team_name = 'Liverpool FC';
"
```
Expected: includes Salah now — count should be one higher than before this
plan (verify manually against the pre-change Liverpool squad list captured
earlier in this conversation if needed).

---

### Task 9: Backend — add `season` param, repoint squad query

**Files:**
- Modify: `backend/schemas.py:88-101`
- Modify: `backend/routers/teams.py:56-72`
- Modify: `backend/routers/players.py`

**Interfaces:**
- Produces: `PlayerPerformance.season: str` (new required field);
  `GET /teams/{team_id}/squad?season=...`, `GET /players/{player_id}/performance?season=...`,
  `GET /players/top-scorers?season=...`, `GET /players/top-assists?season=...`
  (all optional, default to the latest season present in
  `gold.player_performance` when omitted).

- [ ] **Step 1: Add `season` to the `PlayerPerformance` schema**

In `backend/schemas.py`, modify the `PlayerPerformance` class (currently
lines 88-101):

```python
class PlayerPerformance(BaseModel):
    player_id: int
    player_name: str
    season: str
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
```

- [ ] **Step 2: Rewrite `get_team_squad` in `backend/routers/teams.py`**

Replace the `get_team_squad` function (currently lines 56-72):

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

Note: `backend/db.py`'s `get_connection()` uses `psycopg.rows.dict_row` as
its `row_factory`, so `cur.fetchone()["max"]` is correct (confirmed by
reading that file, not assumed).

- [ ] **Step 3: Add `season` param to `backend/routers/players.py`**

Replace the full contents of `backend/routers/players.py`:

```python
from fastapi import APIRouter, HTTPException, Query

from db import get_connection
from schemas import PlayerProfile, PlayerPerformance

router = APIRouter()


def _latest_season(cur) -> str:
    # backend/db.py's get_connection() uses psycopg's dict_row row_factory,
    # so fetchone() returns a dict-like row here.
    cur.execute("SELECT max(season) FROM gold.player_performance")
    return cur.fetchone()["max"]


@router.get("/top-scorers", response_model=list[PlayerPerformance])
def list_top_scorers(
    league: str | None = None,
    team_id: int | None = None,
    season: str | None = None,
    limit: int = Query(default=10, le=50),
):
    with get_connection() as conn, conn.cursor() as cur:
        conditions = ["goals > 0"]
        params: list = []
        if league:
            conditions.append("league = %s")
            params.append(league)
        if team_id:
            conditions.append("team_id = %s")
            params.append(team_id)
        conditions.append("season = %s")
        params.append(season or _latest_season(cur))
        params.append(limit)
        cur.execute(
            f"""
            SELECT * FROM gold.player_performance
            WHERE {' AND '.join(conditions)}
            ORDER BY goals DESC, player_name
            LIMIT %s
            """,
            params,
        )
        return cur.fetchall()


@router.get("/top-assists", response_model=list[PlayerPerformance])
def list_top_assists(
    league: str | None = None,
    team_id: int | None = None,
    season: str | None = None,
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
        conditions.append("season = %s")
        params.append(season or _latest_season(cur))
        params.append(limit)
        cur.execute(
            f"""
            SELECT * FROM gold.player_performance
            WHERE {' AND '.join(conditions)}
            ORDER BY assists DESC, player_name
            LIMIT %s
            """,
            params,
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
def get_player_performance(player_id: int, season: str | None = None):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM gold.player_performance WHERE player_id = %s AND season = %s",
            (player_id, season or _latest_season(cur)),
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Player {player_id} not found")
        return row
```

- [ ] **Step 4: Start the backend and smoke-test the endpoints**

```bash
cd backend
uvicorn main:app --reload
```

In another terminal (adjust the port if `uvicorn` logs a different one):

```bash
curl "http://localhost:8000/teams/66/squad" | grep -i grealish
```
Expected: no match (Grealish is no longer on Man City's squad, team_id 66 —
confirm the actual Man City `team_id` from `gold.team_profile` first if 66
isn't it).

```bash
curl "http://localhost:8000/players/top-scorers?limit=50" | grep -i salah
```
Expected: a Salah row now appears.

- [ ] **Step 5: Commit**

```bash
git add backend/schemas.py backend/routers/teams.py backend/routers/players.py
git commit -m "feat: add season param to squad/performance/top-scorers/top-assists endpoints"
```

---

### Task 10: Update `docs/gold_data_contract.md` (English section)

**Context for the implementer:** This doc has English, French, and
Vietnamese copies of the same content in one file. This task only updates
the **English** section (lines 96-236) — translating the new sections to
French/Vietnamese is out of scope for this plan (see Out of Scope), since
it's a mechanical follow-up that doesn't block functional correctness.

**Files:**
- Modify: `docs/gold_data_contract.md:96-236`

- [ ] **Step 1: Replace the `gold.player_profile` section**

Replace lines 96-156 (the English `## gold.player_profile` section through
its `---` divider) with:

```markdown
## gold.player_profile

**Purpose**: Player identity and a convenience "most recent season's team",
for the `/api/players/{id}` frontend page and chatbot player lookups.

**Grain**: 1 row per `player_id`. Enforced by `unique`/`not_null` tests on
`player_id` in `transform/models/gold/_gold.yml` (no separate
`assert_*_unique_grain.sql` file needed — `player_id` alone is the grain,
same as `team_id` for `silver.teams`).

**Freshness**: Unlike every other gold table, this one is `materialized='view'`,
not `'table'` — `age` is computed live at query time from `date_of_birth`, so
it's always correct without needing a `dbt build` to refresh it. `team_id`
comes from the player's most recent row in `silver.player_team_season`
(`max(season)`), not directly from football_data_org.

| Column | Type | Meaning | Nullable? |
|---|---|---|---|
| `player_id` | int | Either football_data_org's own numeric id, or understat's native id + a fixed `100000000` offset for players football_data_org has no row for | No |
| `player_name` | text | Full player name | No |
| `position` | text | Playing position as reported by football_data_org — exactly one of `Goalkeeper`, `Defence`, `Midfield`, `Offence` | Yes — always `NULL` for understat-anchored players (football_data_org is the only source with this field) |
| `nationality` | text | Country name as reported by football_data_org (single source, not normalized) | Yes — same condition as `position` |
| `date_of_birth` | date | Date of birth | Yes — same condition as `position` |
| `age` | int | Computed at query time from `date_of_birth` | Yes — null if `date_of_birth` is null |
| `shirt_number` | int | Shirt number | Yes — same condition as `position` |
| `team_id` | int | The team this player was resolved to for their most recent season in `silver.player_team_season` — **not** necessarily football_data_org's current roster (see `gold.player_performance` for the season-scoped source of truth) | Yes — null if the player has no `player_team_season` row at all |
| `team_name` | text | Full team name, from `silver.teams` | Yes — same condition as `team_id` |
| `league` | text | Competition slug | No |

**Known limitations**:

- **`team_id` here is a display convenience, not a season-scoped fact.** For
  "who was on team X in season Y," always go through
  `gold.player_performance` (or `GET /teams/{id}/squad?season=Y`), never
  this column — this is exactly the bug this design fixes (previously
  `team_id` came straight from football_data_org's undated "current roster,"
  which showed loaned-out players at their parent club and had zero row for
  players football_data_org's squad crawl didn't cover at all).
- **understat-anchored players (no football_data_org row) have `NULL`
  bio fields.** `position`/`date_of_birth`/`nationality`/`shirt_number` are
  only ever populated from football_data_org — there's no seed backfilling
  them today (a `player_extra_info.csv` seed was discussed for this, not
  built).
- **Premier League only.** football_data_org's squad crawl only covers
  Premier League (see `crawlers/football_data_org/client.py`); understat
  covers Ligue 1 too, but Ligue 1 players who have no football_data_org row
  will still show up here (understat anchors them independent of league) —
  Ligue 1 coverage for this table isn't a deliberate scope decision the way
  it is for `player_performance`'s statbunker column.
- **The 4-value `position` vocabulary above is hardcoded elsewhere.** The
  squad-ordering query in `backend/routers/teams.py`
  (`ORDER BY CASE pp.position WHEN 'Goalkeeper' THEN 1 ...`) and the
  `POSITION_GROUPS` constant in `frontend/components/SquadTable.tsx` both
  depend on exactly these 4 values — a future change to this domain (e.g. a
  new position value from football_data_org) must update both.

---
```

- [ ] **Step 2: Replace the `gold.player_performance` section**

Replace lines 159-236 (the English `## gold.player_performance` section
through its `---` divider) with:

```markdown
## gold.player_performance

**Purpose**: Player stats — goals, assists, minutes, xG/xA — with the team
they were attributed to for a given season, for the
`/api/players/{id}/performance` frontend page and chatbot questions like
"how many goals has player X scored" or "what's player X's xG."

**Grain**: 1 row per `(player_id, season)` — changed from `player_id` alone,
so a player's team can correctly differ between seasons, or (within one
season) be a loan club rather than football_data_org's parent-club roster.
Enforced by `transform/tests/assert_gold_player_performance_unique_grain.sql`
(a dedicated grain test, since the grain is now composite — the earlier
single-column `unique` test on `player_id` no longer applies).

**Freshness**: `materialized='table'` — reflects the most recent statbunker
and understat crawls as of the last `dbt build`. Team resolution priority per
`(player_id, season)`: understat's team (freshest, correctly attributes loan
players to the loan club) → statbunker's team → football_data_org's current
team as a last-resort fallback for players with zero stats that season.

| Column | Type | Meaning | Nullable? |
|---|---|---|---|
| `player_id` | int | Either football_data_org's own numeric id, or understat's native id + a fixed `100000000` offset | No |
| `player_name` | text | Full player name | No |
| `season` | text | `YYYY-YYYY` format | No |
| `team_id` | int | Team this player was attributed to **for this specific season** — see `silver.player_team_season` for the resolution logic | Yes — null only if this player+season somehow resolved to no team at all (see limitations) |
| `team_name` | text | Full team name, from `silver.teams` | Yes — same condition as `team_id` |
| `league` | text | Competition slug | No |
| `goals` | int | Season goals (statbunker) | **Yes** — null if this player has no statbunker row for this season |
| `assists` | int | Season assists (understat) | **Yes** — same condition as `xg` |
| `apps` | int | Appearances (understat) | **Yes** — same condition as `xg` |
| `minutes` | int | Minutes played (understat) | **Yes** — same condition as `xg` |
| `xg` | numeric | Expected goals (understat) | **Yes** — null if this player has no understat row for this season |
| `xa` | numeric | Expected assists (understat) | **Yes** — same condition as `xg` |
| `xg90` | numeric | Expected goals per 90 minutes (understat), derived as `xg / (minutes / 90)` | **Yes** — same condition as `xg`, also null if `minutes` is 0 |
| `xa90` | numeric | Expected assists per 90 minutes (understat), derived the same way | **Yes** — same condition as `xg90` |

**Known limitations**:

- **Name matching is by normalized name only, not name + team**, same as
  before — see `normalize_player_name` (requires the Postgres `unaccent`
  extension) and `transform/seeds/player_name_map.csv` for exceptions.
- **A player+season can resolve to `NULL` `team_id`** if understat's only row
  for them that season has a comma-joined mid-season-transfer `team_title`
  (see below) **and** this player has no football_data_org row to fall back
  to (i.e. an understat-anchored identity, not an fdo one) — rare, since
  most such players also have a statbunker row that season with a resolvable
  team.
- **Understat mid-season transfers**: a comma-joined `team_title` value
  (e.g. `"Bournemouth,Manchester City"`) intentionally resolves that row's
  `team_id` to `NULL` rather than guessing which team is current — team
  resolution then falls through to statbunker, then football_data_org, per
  the priority order above.
- **`source_disagreement` in `silver.player_team_season`** (not exposed
  directly here) flags player+seasons where understat and statbunker both
  have a row but report different teams — a genuine mid-season transfer
  within one season. `understat` wins those ties silently; see
  `assert_player_team_season_source_agreement` (warn) to find them.
- **statbunker only covers Premier League.** `goals` will always be `NULL`
  for a Ligue 1 player.

---
```

- [ ] **Step 3: Commit**

```bash
git add docs/gold_data_contract.md
git commit -m "docs: update gold_data_contract.md for season-scoped player_profile/player_performance"
```

---

### Task 11: Manual end-to-end web verification

**Files:** none — browser verification only, per this project's rule that
UI changes must be checked in an actual browser before being called done.

- [ ] **Step 1: Start the frontend**

```bash
cd frontend
npm run dev
```

- [ ] **Step 2: Verify Liverpool's squad page shows Salah**

Navigate to the Liverpool team page's squad section in the browser. Confirm
"Mohamed Salah" appears (previously absent).

- [ ] **Step 3: Verify Grealish shows under Everton, not Manchester City**

Navigate to Everton's team page. Confirm "Jack Grealish" appears in the
squad with his 2025-26 stat line (2 goals, 6 assists). Navigate to
Manchester City's team page and confirm he does **not** appear there.

- [ ] **Step 4: Verify Savinho still shows correctly**

Navigate to Manchester City's team page. Confirm "Savinho" appears (not
"Sávio") with his stats intact (1 goal, 1 assist, 24 apps) — regression
check that Task 3 didn't disturb the existing fix.

- [ ] **Step 5: Verify league-wide top scorers still look sane**

Navigate to the league top scorers page. Confirm the list still shows
plausible names/goal counts (e.g. a known high scorer near the top) — sanity
check that the season-filtering default (latest season) didn't silently
empty the list.

## Out of Scope

- `player_extra_info.csv` seed for understat-anchored players' bio fields —
  referenced in the design spec as a future step, not built here.
- French/Vietnamese translation of the `docs/gold_data_contract.md` sections
  updated in Task 10 — English only in this plan.
- SCD2 history / full season-over-season squad browsing UI (a season
  selector on the squad page beyond the `?season=` query param) — this plan
  makes the data correctly season-scoped so that capability *can* be built
  later without rework, but no such frontend UI is included here.
- Ligue 1 statbunker coverage — statbunker's crawler only covers Premier
  League today; unchanged by this plan.
