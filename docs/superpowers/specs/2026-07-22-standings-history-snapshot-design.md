# Snapshot: `snapshot_football_data_org__standings`

Date: 2026-07-22

## Context

Mentor raised a concern: when bronze data changes, a straight silver/gold
rebuild overwrites the previous state with no way for a reader to tell
"this is version 2, here was version 1." `gold_league_standings`
([2026-07-22-gold-league-standings-design.md](2026-07-22-gold-league-standings-design.md))
takes only the latest snapshot per team and discards the rest — bronze
technically retains prior versions (append-only via `content_hash`), but
nothing in silver/gold surfaces that lineage to a reader. This spec adds an
SCD Type 2 history layer via `dbt snapshot`.

## Decisions

- **New model `silver.standings`**: dedupes `stg_football_data_org__standings`
  to one row per `(league, season, team_id)`, using `row_number() over
  (partition by league, season, team_id order by ingestion_time desc)` — the
  same latest-snapshot logic currently inlined in `gold_league_standings`'s
  `fd_standings`/`fd_latest` CTEs, pulled out so it isn't duplicated.
- **`gold_league_standings` refactor**: replaces its `fd_standings`/`fd_latest`
  CTEs with `select * from {{ ref('standings') }}`. The `us_standings`/
  `us_latest` (understat) CTEs are untouched — out of scope, see below.
- **Snapshot scope**: football_data_org standings only, for now. Naming
  (`snapshot_football_data_org__standings`) leaves room for
  `snapshot_statbunker__standings` / `snapshot_understat__standings` later
  without a redesign.
- **Snapshot source**: `ref('standings')` (the new silver model), not the raw
  staging model — staging keeps one row per ingestion snapshot (multiple rows
  per team), which violates the row-per-unique-key requirement dbt snapshot
  needs from its source query. `silver.standings` is the "current state"
  table dbt snapshot is designed to sit on top of.
- **Snapshot config**: `target_schema='snapshots'` (dedicated schema,
  separate from silver/gold, so the history layer is self-explanatory),
  `unique_key=['league','season','team_id']` (composite list key, supported
  natively by dbt-core 1.12), `strategy='check'` on the stat columns only
  (`position, played_games, won, draw, lost, points, goals_for,
  goals_against, goal_difference, form`) — excludes `team_name`/
  `ingestion_time` to avoid false-positive versioning on metadata that isn't
  the thing being tracked.
- **New test**: `tests/assert_snapshot_standings_one_current_row.sql`,
  checking exactly one row with `dbt_valid_to is null` per
  `(league, season, team_id)` in the snapshot table — same custom-test
  convention as the existing `assert_*_unique_grain.sql` tests.
- **Manual verification plan** (season 25/26 has ended, so standings won't
  change organically): run `dbt run` + `dbt snapshot` once to seed the first
  version; hand-edit one team's `points`/`position` in a raw standings JSON
  file under `data/raw/football_data_org/standings/`, re-ingest via
  `docker compose run --rm ingestion` (the host `.env` has no `DATABASE_URL`,
  so `python ingestion/ingest.py` can't run directly outside the container;
  new `content_hash` → new bronze row), then `dbt run` + `dbt snapshot`
  again; query
  `snapshots.snapshot_football_data_org__standings where team_id = X order by
  dbt_valid_from` and confirm two rows — one closed (`dbt_valid_to` set), one
  current (`dbt_valid_to is null`).

## Out of scope

- `gold_league_standings` does **not** switch to reading from the snapshot
  table — it keeps reading current data from `silver.standings` directly.
  The snapshot is an additive history layer, not (yet) the source of truth
  for "current" gold output.
- `statbunker` / `understat` standings snapshots — same reasoning as the
  `gold_league_standings` spec: understat's `team_id` is seed-mapped and can
  be null, statbunker adds no new columns. Deferred until there's a concrete
  need.
- Snapshotting `matches` — matches only meaningfully change (status
  transitions, scores) during an active season; current crawled data is the
  completed 25/26 season, so there's nothing to demonstrate yet. Revisit
  once the 26/27 season crawl is live.
- **Capture fidelity is bounded by `dbt snapshot` cadence, not by every bronze
  version.** The snapshot only records what's current in `silver.standings`
  (itself an overwrite-materialized "latest" model) at the moment `dbt
  snapshot` runs. If two corrections land between two `dbt snapshot`
  invocations (e.g. points go 85 → 84 → 86, each following its own `dbt
  run`), the intermediate `84` is never written to the snapshot table — only
  85 (closed) and 86 (current) appear. Bronze still retains every version via
  `content_hash`, so no data is lost, but the SCD2 history layer is not a
  complete audit trail of every bronze change, only of every state observed
  at a snapshot run. Acceptable for Phase 1; revisit if a stronger guarantee
  is needed later (e.g. running `dbt snapshot` after every ingestion, or
  snapshotting closer to bronze).
