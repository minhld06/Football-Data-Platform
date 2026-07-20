# Silver Entity Keys — Team & Match Identity (Week 5+6 dbt)

Date: 2026-07-21

## Context

Phase 1 crawlers collect data from three sources, but only two `entity_type`s exist,
both team-level:

| entity_type | source(s) | notes |
|---|---|---|
| `standings` | football_data_org, statbunker, understat | league table per team |
| `matches` | football_data_org only | fixtures + score, no events/lineups |

Sample payloads show the core problem this spec solves: the same club is spelled
differently across sources (e.g. `"AFC Bournemouth"` in statbunker vs `"Bournemouth"`
in understat), and only football_data_org carries a stable numeric team id.
statbunker and understat give team **names only**.

Scope for this spec: the minimum Week 5+6 deliverable — 4 staging models, 2 silver
models (`silver_teams`, `silver_matches`), 2 gold models. This spec covers only the
**entity key design** for `silver_teams`/`silver_matches`, since that decision is
hard to change once gold models and tests depend on it.

## Decision 1 — `silver_teams` key

- **Anchor on football_data_org's `team.id`** (int) as `team_id`, the primary key of
  `silver_teams`. This is the only source with a stable per-team id, and it already
  covers both leagues in scope (Premier League + Ligue 1).
- `silver_teams` columns: `team_id` (PK), `team_name` (canonical, from
  football_data_org), `short_name`, `tla`, `country`.
- statbunker and understat rows carry no id, so their raw team names must be
  **resolved to `team_id`** before reaching silver. This resolution happens in the
  staging layer (see Decision 4), not in silver — staging is where per-source quirks
  get cleaned up; silver only unions/dedupes already-resolved data.

Rejected alternatives:
- A brand-new surrogate key (e.g. hash of normalized name) independent of any
  source — adds an indirection layer even for football_data_org, which already has
  a perfectly good id. Not justified at this scale (2 leagues, ~38 teams).
- Natural key = auto-normalized name string (strip "AFC"/"FC"/year suffixes) — risks
  silent mismatches on irregular cases (e.g. "Stade Rennais FC 1901" vs "Rennes"),
  which a hand-written mapping avoids.

## Decision 2 — Team name mapping seed

- File: `transform/seeds/team_name_map.csv`, columns: `source, raw_team_name,
  team_id`.
- Hand-written, one row per distinct raw name seen in statbunker/understat
  standings payloads (~38 rows total). Loaded via `dbt seed`.
- `stg_statbunker__standings` and `stg_understat__standings` join this seed on
  `(source, raw_team_name)` to attach `team_id`.
- **Safety net**: a dbt test must fail the build if any distinct `raw_team_name` in
  those two staging models has no matching seed row (i.e., the join would produce a
  NULL `team_id`). This turns "crawler picked up a new/renamed team" into a loud
  build failure instead of a silently dropped join — consistent with the project's
  fail-fast-on-config-gaps rule in CLAUDE.md.

## Decision 3 — `silver_matches` key

- Primary key: composite `(source, source_match_id)`. Currently `source` is always
  `'football_data_org'` and `source_match_id` is that API's numeric `match.id`.
- `home_team_id` / `away_team_id` reference `silver_teams.team_id` directly — no
  seed join needed, since football_data_org already supplies the anchor id inline
  on each match's `homeTeam`/`awayTeam` object.
- The `source` column is kept even though only one source currently produces
  match-level data, so the key stays stable if Phase 2 adds another match-level
  source (e.g. detailed match events) — no migration needed later.

## Decision 4 — Minimum staging layout (4 models)

One staging model per `(source, entity_type)`, each a 1:1 light-cleaning pass over
its bronze payload (type casts, one row per record) plus, for the two name-only
sources, the seed join from Decision 2:

- `stg_football_data_org__standings`
- `stg_football_data_org__matches`
- `stg_statbunker__standings` — joins `team_name_map` seed for `team_id`
- `stg_understat__standings` — joins `team_name_map` seed for `team_id`

## Out of scope

- Gold model design (`gold_league_standings`, `gold_team_form_last_5_matches` /
  `gold_head_to_head`) — separate spec once staging/silver land.
- Player- and match-event-level entities (top scorers, player performance, match
  events) — no crawler currently collects this data; deferred until a crawling spec
  exists for those entity types.
