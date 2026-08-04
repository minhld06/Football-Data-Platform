# Player Extra Info — CSV Backfill (Shirt Numbers + Remaining PL Bio Gaps) — Design

## Problem

Two related gaps in `gold.player_profile.nationality`/`.date_of_birth`/`.shirt_number`, confirmed by querying the current build:

```
league          | total | null_nationality | null_date_of_birth | null_shirt_number
premier-league  |   664 |               92 |                  93 |               662
```

1. **`shirt_number` is `NULL` for essentially every Premier League player**, including the 570 who *do* have a football_data_org row. This isn't a crawler bug: I inspected the raw crawled JSON directly (`data/raw/football_data_org/players/2026-07-24/*.json`, all 1,180 PL squad records across every team) and confirmed `shirtNumber` is not a key football_data_org's (free-tier) squad endpoint ever returns — 0 of 1,180 records have it. `player_extra_info.csv` (built in
   [`2026-08-03-player-extra-info-seed-design.md`](2026-08-03-player-extra-info-seed-design.md)) only backfills understat-anchored players, so this systemic gap was never in scope for it.
2. **92 of the 94 Premier League understat-anchored players still have no `nationality`/`date_of_birth`/`shirt_number`.** The prior seed shipped with only 2 rows filled in (Salah, Trossard). A follow-up spec to triage the remaining 94 one-by-one via per-team manual research
   (`2026-08-04-player-triage-94-design.md`) was written and then abandoned (deleted from the repo this morning) in favor of the approach here: the user had ChatGPT compile a reference CSV of every 2025-26 Premier League squad's `team, name, nationality, date_of_birth, shirt_number` (`premier_league_2025_26_players.csv`, 537 rows), instead of researching each player individually.

Ligue-1 has a similar, larger gap (535/553 null), but that's already documented as a deliberate, out-of-scope limitation (football_data_org's plan returns `squad: []` for every Ligue-1 team). The CSV is Premier-League-only, so Ligue-1 stays out of scope here too.

## Goal

Use the CSV to:
- Backfill `shirt_number` for every Premier League player where football_data_org has no such field (extending `player_extra_info`'s role from "understat-anchored only" to a general fallback for any player).
- Backfill `nationality`/`date_of_birth`/`shirt_number` for as many of the 92 remaining understat-anchored gaps as the CSV can resolve with confidence.

This **revises** the prior spec's non-goal ("does not touch players who already have an fdo row") — that constraint was correct when `player_extra_info` only needed to cover 2 known cases; it doesn't hold now that the systemic shirt_number gap is understood.

## Non-goals

- Ligue-1 — out of scope, per the existing documented limitation.
- Correcting `silver.players.team_id` staleness (loans/transfers where our system's team assignment disagrees with the CSV's current squad list, e.g. Marcos Senesi shown as Tottenham in our data vs. Bournemouth in the CSV). `player_extra_info` only supplies bio fields keyed by `player_id`; it doesn't touch team assignment, so a stale `team_id` elsewhere in the pipeline doesn't block or corrupt this backfill.
- Building generic fuzzy-matching tooling as project infrastructure. The matching below is one-time, ad-hoc SQL run against a temp table to produce the seed's row list — not a reusable macro or model.
- Creating new `player_id`s. The seed can only backfill a player who already has a row in `silver.players` (via football_data_org or Understat/StatBunker). CSV rows for people absent from all three sources are left unresolved (see below) — that would need new crawler work, which is unstarted, unscheduled future work per `CLAUDE.md`.
- Merging any of this into `player_name_map.csv` (the fdo-vs-Understat identity-reconciliation seed). This CSV is a third, independent bio-data source — resolving it only requires matching CSV rows to an *existing* `player_id` in `silver.players`, not reconciling fdo and Understat's own identities against each other. That reconciliation problem (e.g. "Matty Cash" vs. "Matthew Cash") is unrelated and untouched by this work.

## Design

### 1. Matching CSV rows to an existing `player_id`

The CSV has no stable id — matching is by `team` + `name` against `silver.players` (Premier League only). Team names differ cosmetically (`"Arsenal"` vs. `"Arsenal FC"`), handled with a 20-row `team_map` VALUES list joined to `silver.teams.team_id`.

Four automated passes, tried in order of confidence, using `normalize_player_name()`-style normalization (`unaccent`, lowercase, strip non-alphanumerics):

1. **Exact match** on normalized name + `team_id`.
2. **Unique name-only match** (drop the team constraint, but only when exactly one PL player has that normalized name) — catches transfers our crawled data hasn't caught up to (e.g. Harvey Elliott, Donyell Malen moving to Aston Villa this summer).
3. **Word-subset / substring containment within the same team** — catches the CSV's frequent use of full legal names against our shorter public names (e.g. `"David Raya Martín"` → `"David Raya"`, `"Rúben dos Santos Gato Alves Dias"` → `"Rúben Dias"`).
4. **Trigram similarity ≥ 0.4, same team** (Postgres `pg_trgm`) — catches remaining spelling/order variants (e.g. `"Endo Wataru"` → `"Wataru Endō"`, `"Hwang Hee-chan"` → `"Hwang Heechan"`).

These four passes resolve 502 of 537 rows unambiguously (verified: zero `player_id` claimed by more than one CSV row).

**Remaining ~35 rows** were checked individually against known football facts rather than trusted to a similarity score, since a wrong automated merge would silently corrupt a different real person's data (the exact failure mode already documented for name-matching elsewhere in this project). This added ~25 more confident matches — nickname/alternate-name pairs such as:
- `"Sávio Moreira de Oliveira"` → `"Savinho"` (already documented: this project overrode his display name from "Sávio" to "Savinho")
- `"Carlos Henrique Casimiro"` → `"Casemiro"`, `"Norberto Bercique Gomes Betuncal"` → `"Beto"`, `"João Maria Lobo Alves Palhares Costa Palhinha Gonçalves"` → `"João Palhinha"` — well-known public nicknames
- Various full-name-vs-short-name pairs the automated passes narrowly missed (e.g. `"Yerson Mosquera Valdelamar"` → `"Yerson Mosquera"`, `"Hugo Bueno López"` → `"Hugo Bueno"`)

**Left unresolved (~10 rows), no seed row added — same "skip, no marker" convention `player_extra_info` already uses today:**
- No row exists in *any* of our 3 sources at all (e.g. Nayef Aguerd, Odsonne Édouard, Angel Gomes, Fer López, Lucas Tolentino Coelho de Lima) — nothing for the seed to key on.
- Same-surname collision risk, where a wrong merge would overwrite a *different* real, already-correct person's data: CSV's `"Hamed Traoré"` (Bournemouth) vs. our existing `"Bertrand Traoré"` (Sunderland) — different people; CSV's `"João Pedro Ferreira da Silva"` (Nottingham Forest) vs. our existing, already-resolved `"João Pedro"` (Chelsea) — too risky to merge without independent confirmation.
- `"Douglas Luiz Soares de Paulo"` listed at Aston Villa in the CSV — he transferred to Juventus in 2024 and is not in the Premier League this season. This looks like stale/hallucinated CSV data (a general risk of an LLM-compiled reference list); excluded rather than trusted.

### 2. Seed file — `transform/seeds/player_extra_info.csv`

Same shape as today (`player_id,nationality,date_of_birth,shirt_number`), grown from 2 rows to the ~527 resolved above. For fdo-anchored players, only `shirt_number` will actually be new data (they already have `nationality`/`date_of_birth` from football_data_org) — but the CSV's values for all three columns are written regardless; `coalesce()` in the model (below) decides what's actually used, so no harm in a seed row supplying a value the model never reads. `not_null`/`unique` tests on `player_id` in `transform/seeds/_seeds.yml` already exist and don't need changes — growing the row count doesn't change the grain.

### 3. Model change — `transform/models/silver/players.sql`

Today, only the `understat_only` CTE joins `player_extra_info`. Add the same join to `fdo_players`, coalescing rather than overwriting so football_data_org's own data always wins when present:

```sql
fdo_players as (
    select
        fdo_deduped.player_id,
        coalesce(overrides.display_name, fdo_deduped.player_name) as player_name,
        fdo_deduped.player_name as raw_fdo_player_name,
        fdo_deduped.position,
        coalesce(fdo_deduped.date_of_birth, extra.date_of_birth) as date_of_birth,
        coalesce(fdo_deduped.nationality, extra.nationality) as nationality,
        coalesce(fdo_deduped.shirt_number, extra.shirt_number) as shirt_number,
        fdo_deduped.team_id,
        fdo_deduped.league,
        fdo_deduped.ingestion_time
    from fdo_deduped
    left join {{ ref('player_display_name_overrides') }} as overrides
        on overrides.player_id = fdo_deduped.player_id
    left join {{ ref('player_extra_info') }} as extra
        on extra.player_id = fdo_deduped.player_id
),
```

`understat_only` is unchanged (it already does this join). No change to `_seeds.yml` or `dbt_project.yml`'s `column_types` — same seed shape.

### 4. Documentation updates

- `docs/gold_data_contract.md` — all three language sections (EN/FR/VI): the `shirt_number` row currently reads "`NULL` for understat-anchored players unless backfilled" (EN) or has no nullability note at all (FR/VI, already inconsistent with EN before this change). Update to reflect that `shirt_number` is unconditionally sourced from `player_extra_info.csv` for *every* PL player, since football_data_org never provides it — not just understat-anchored ones. Update the "known limitations" prose bullet (currently describing `player_extra_info.csv` as covering only understat-anchored gaps) to describe the widened scope.
- `CLAUDE.md` — the `player_extra_info.csv` seed description already exists in the seeds bullet; no change needed there (it doesn't currently claim an understat-only scope).

## Rebuild discipline (carried over from the abandoned triage spec)

`gold.player_profile` is a **view**; `silver.players` is a **table**. Rebuilding `silver.players` alone (`dbt run --select players`) does a `drop ... cascade`, which drops the dependent view too. Any implementation task touching the seed or `players.sql` must run a full `dbt build` (or at minimum `dbt run` with no `--select`), and verify the result against `gold.player_profile` directly — not just `silver.players`.

## Open items for implementation (not blocking spec approval)

- The actual seed CSV (final `player_id → nationality/date_of_birth/shirt_number` rows) is produced by re-running the matching SQL above against the live database and exporting via `\copy`, not hand-transcribed — avoids transcription error across ~527 rows.
- Verify row counts before/after in `gold.player_profile` (null counts for `nationality`/`date_of_birth`/`shirt_number`, Premier League only) as the acceptance check.
