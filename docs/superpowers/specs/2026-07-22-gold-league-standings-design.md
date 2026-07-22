# Gold: `gold_league_standings`

Date: 2026-07-22

## Context

First gold model for the Week 5+6 minimum deliverable, following the entity-key
work in [2026-07-21-silver-entity-keys-design.md](2026-07-21-silver-entity-keys-design.md).
Per the roadmap: gold must be flat, self-descriptive, no complex joins at read
time.

## Decisions

- **Grain:** one row per `(league, season, team_id)`.
- **Base columns** (`position, played_games, won, draw, lost, points, goals_for,
  goals_against, goal_difference, form`) come from the **latest snapshot**
  (`max(ingestion_time)`) of `stg_football_data_org__standings` per
  `(league, season, team_id)` — football_data_org is the anchor source (see
  [2026-07-21 spec, Decision 1]).
- **Enrichment**: `xg, xga, xpts` are joined in from the **latest snapshot** of
  `stg_understat__standings`, matched on `(team_id, league, season)`. Chosen
  because understat is the only source with expected-goals metrics — no other
  source has them, so this isn't a conflict-resolution case, just an outer join
  to add columns. Left join: a missing understat row yields NULL xG columns
  rather than dropping the team.
- **Team attributes** (`team_name, short_name, tla`) come from `silver.teams`,
  not repeated from staging — gold should read the dimension, not re-derive it.
- **Prerequisite gap**: `stg_football_data_org__standings` and
  `stg_understat__standings` don't currently expose `ingestion_time`. Both need
  it added (select from the bronze source, pass through unnesting CTEs) before
  the "latest snapshot" dedup logic can work. `stg_statbunker__standings` is not
  used by this model (statbunker has no xG data and duplicates football_data_org's
  raw standings columns with no added value here).

## Out of scope

- Historical daily grain (rejected in favor of latest-per-team; see prior
  conversation — current crawled data is a single completed season with
  near-duplicate snapshots, so daily grain adds no value yet).
- `gold_team_form_last_5_matches` / `gold_head_to_head` — next gold model, not
  covered here.
