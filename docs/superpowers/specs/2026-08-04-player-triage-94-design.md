# Triage the 94 Premier League Understat-Anchored Players — Design

## Problem

The previous change ([`docs/superpowers/specs/2026-08-03-player-extra-info-seed-design.md`](2026-08-03-player-extra-info-seed-design.md)) built a general backfill mechanism (`transform/seeds/player_extra_info.csv`) for players missing `nationality`/`date_of_birth`/`shirt_number` because they have no football_data_org row at all, but only populated it with 2 rows (Salah, Trossard). Querying `silver.players` shows this is far from the whole picture:

```sql
select league, count(*) from silver.players where player_id >= 100000000 group by league;
--      league     | count
-- ----------------+-------
--  ligue-1        |   535
--  premier-league |    94
```

Ligue 1's 535 is the already-documented, deliberate scope limitation (football-data.org's current plan returns `squad: []` for every Ligue 1 team — not fixable by a seed at that scale). The Premier League's 94 is the real, previously-underestimated gap this spec addresses.

Investigating further split that 94 into two genuinely different root causes, confirmed by inspecting raw football_data_org squad payloads directly:

- **Genuine gaps** — the player really has no football_data_org row. Root cause: football_data_org's own squad crawl is incomplete for some teams, worst example Wolverhampton Wanderers (`data/raw/football_data_org/players/2026-07-24/PL_2025_76_173611_958848.json`) with only **11** squad members crawled, vs. 22-38 for every other Premier League team in the same crawl. This is where Salah/Trossard/most of Wolves' 20 fall.
- **Name-matching failures** — the player *does* have a football_data_org row, under a name `normalize_player_name()` doesn't catch: e.g. "Matty Cash" (fdo, `player_id` 11644) vs. "Matthew Cash" (Understat's own name for the same person, nickname variant) at Aston Villa, and "Hwang Heechan" (fdo, `player_id` 3354, confirmed present in the Wolves squad file above) vs. "Hee-Chan Hwang" (Understat, reversed Korean name order) at Wolves. These need a `player_name_map.csv` row, not a `player_extra_info.csv` row — once merged, the player already has full fdo bio data for free, and disappears from the 94 entirely.

## Goal

Triage all 94 Premier League understat-anchored players into the two buckets above, and resolve each:
- Name-matching failures with **high-confidence** matches get merged via `player_name_map.csv`.
- Everything else (genuine gaps, and any name-matching case that isn't high-confidence) gets researched via WebSearch/WebFetch against public sources and added to `player_extra_info.csv` with real data. Players nothing reliable can be found for are simply left out of the seed — no special marker needed, same as today.

## Non-goals

- Ligue 1's 535 understat-anchored players — out of scope, per the documented, deliberate squad-crawl limitation.
- Building any fuzzy-matching tooling/script. Per-team lists are small enough (max 38 real fdo squad members, max 20 understat-anchored names) to eyeball directly — see Design section 1.
- Merging any name-matching case that isn't high-confidence (same team + unambiguously the same person, e.g. nickname or word-order variant). Ambiguous cases are treated as genuine gaps (researched, not merged) rather than risking a wrong merge that would corrupt two real players' data together.

## Design

### 1. Per-team triage, no new tooling

Work is organized one task per Premier League team (20 teams; one may have zero understat-anchored players and needs no task). For each team, two short lists are compared directly (no fuzzy-match script — team squads top out at 38 players, understat-anchored lists top out at 20):

- **Understat-anchored names for this team** — from `silver.player_team_season` joined to `silver.players` where `player_id >= 100000000`, already enumerated (see table below).
- **Real football_data_org squad** — the raw JSON already crawled at `data/raw/football_data_org/players/2026-07-24/PL_2025_{fdo_team_id}_173*.json` (each object has `id`, `name`, `position`, `dateOfBirth`, `nationality`, `shirtNumber` — the exact fields needed if a match is found here).

For each understat-anchored name, check whether it appears in the team's fdo squad list under a different spelling/order/nickname.

### 2. Classification outcomes

- **High-confidence match found** (e.g. nickname: Matty ↔ Matthew Cash; word-order: Hwang Heechan ↔ Hee-Chan Hwang; diacritic-only spelling differences `normalize_player_name()` should have caught but didn't) → add one row to `transform/seeds/player_name_map.csv`: `understat,<Understat's raw_player_name>,<fdo team_id>,<fdo player_id>` (the same shape as existing rows there, e.g. `understat,Alisson,64,1795`). The fdo `team_id`/`player_id` come directly from the squad JSON's `id` field for that matched entry.
- **No match, or match isn't high-confidence** → treat as a genuine gap. Look up the real person via WebSearch/WebFetch (Wikipedia or an official club/league source preferred for consistency) and add one row to `transform/seeds/player_extra_info.csv`: `player_id,nationality,date_of_birth,shirt_number` where `player_id = understat_id + 100000000` (same shape as the existing Salah/Trossard rows).
- **No reliable source found** (expected for some obscure academy/reserve names) → skip, add no row. This is indistinguishable from "not yet researched" today, and that's fine — no tracking column is being added for this (consistent with the prior seed design's no-provenance decision).

### 3. New test: uniqueness on `player_name_map.csv`

`transform/seeds/player_name_map.csv` has no schema tests today (it was out of scope for the prior spec, since that work didn't touch it). This work adds potentially a handful of new rows to it, so add a `unique` test on the combination of `(source, raw_player_name, team_id)` in `transform/seeds/_seeds.yml` (alongside the existing `player_extra_info` entry) — a duplicated key here would silently fan out the join in `understat_matched_to_fdo` exactly like the risk already guarded against for `player_extra_info.player_id`.

### 4. Rebuild discipline

The prior work's Task 2 cascade-dropped `gold.player_profile` by running `dbt run --select players` in isolation (table materialization does `drop ... cascade`, which also drops the dependent view). Every task in the follow-up plan that changes a seed or model must rebuild with `dbt build` (or at minimum `dbt run` with no `--select`), not a scoped `--select`, and verify against `gold.player_profile` (not just `silver.players`) — this is now a global constraint for the implementation plan, not merely a lesson noted after the fact.

## Reference: the 20 Premier League teams and their football_data_org squad crawl

| fdo `team_id` | Team | fdo squad size | Understat-anchored count |
|---|---|---|---|
| 1044 | AFC Bournemouth | 29 | 2 |
| 328 | Burnley FC | 30 | 5 |
| 341 | Leeds United FC | 30 | 0 |
| 351 | Nottingham Forest FC | 28 | 6 |
| 354 | Crystal Palace FC | 31 | 3 |
| 397 | Brighton & Hove Albion FC | 37 | 7 |
| 402 | Brentford FC | 34 | 3 |
| 563 | West Ham United FC | 27 | 4 |
| 57 | Arsenal FC | 29 | 1 |
| 58 | Aston Villa FC | 30 | 7 |
| 61 | Chelsea FC | 37 | 3 |
| 62 | Everton FC | 23 | 2 |
| 63 | Fulham FC | 22 | 1 |
| 64 | Liverpool FC | 29 | 3 |
| 65 | Manchester City FC | 32 | 4 |
| 66 | Manchester United FC | 38 | 3 |
| 67 | Newcastle United FC | 24 | 5 |
| 71 | Sunderland AFC | 32 | 7 |
| 73 | Tottenham Hotspur FC | 37 | 7 |
| 76 | Wolverhampton Wanderers FC | **11** | 20 |

(Understat-anchored counts sum to 93 in this table, not 94. The 94th, **Adama Traoré** (`player_id` 100000900), has zero rows in `silver.player_team_season` at all — confirmed by querying for understat-anchored players with no `player_team_season` row. His raw Understat record has `team_title: "Fulham,West Ham"` — the documented comma-joined mid-season-transfer case (see the `players` model's grain description in `transform/models/silver/_silver.yml`) that resolves to no team. He isn't covered by any single team's task as scoped above; check both the Fulham and West Ham fdo squad files for him during those two teams' tasks.)

Wolverhampton's squad crawl (11 players — every other team has 22+) is the single largest concentration of genuine gaps and confirms the root cause is football_data_org's own data completeness, not a matching bug specific to Wolves' players.

## Open items for implementation (not blocking spec approval)

- The actual per-player classification (match vs. gap) and the real nationality/DOB/shirt_number/fdo-id values are look-up work for the implementation plan's per-team tasks, not decided in this spec.
