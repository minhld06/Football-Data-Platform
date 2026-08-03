# Player Extra Info Seed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backfill `nationality`/`date_of_birth`/`shirt_number` for understat-anchored players (players with no football_data_org squad row, e.g. Mohamed Salah, Leandro Trossard) via a manually-maintained seed, so `gold.player_profile` stops showing `NULL` for these fields for players who genuinely have known values.

**Architecture:** A new dbt seed `player_extra_info.csv`, keyed on the same computed `player_id` (`understat_id + 100000000`) already used for understat-anchored rows in `silver.players`, left-joined into the `understat_only` CTE of `transform/models/silver/players.sql`. Purely additive — the `fdo_players` branch (used whenever football_data_org has a row) is untouched, so football_data_org remains the unconditional source of truth whenever it has data.

**Tech Stack:** dbt-core + dbt-postgres (existing `transform/` project), CSV seed, PostgreSQL.

## Global Constraints

- Run all `dbt` commands from the `transform/` directory, with `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` set in the environment (see `transform/profiles.yml`).
- Seed key is the final computed `player_id` (`understat_id + 100000000`), not `(source, raw_player_name, team_id)` — decided during brainstorming to avoid name-spelling/team_id-drift issues that already cause missed matches elsewhere.
- Seed only fills gaps for understat-anchored players (no football_data_org row at all). Never touches the `fdo_players` branch — football_data_org stays the unconditional source of truth whenever it has a row.
- No provenance/source column in the seed — matches the existing `player_name_map.csv` / `player_display_name_overrides.csv` seeds.
- Design reference: [`docs/superpowers/specs/2026-08-03-player-extra-info-seed-design.md`](../specs/2026-08-03-player-extra-info-seed-design.md).

---

### Task 1: Add the `player_extra_info` seed

**Files:**
- Create: `transform/seeds/player_extra_info.csv`
- Create: `transform/seeds/_seeds.yml`
- Modify: `transform/dbt_project.yml`

**Interfaces:**
- Produces: seed table `player_extra_info` with columns `player_id (int, unique, not null)`, `nationality (text)`, `date_of_birth (date)`, `shirt_number (int)` — consumed by Task 2.

- [ ] **Step 1: Create the seed CSV with real data for the two known gaps**

Mohamed Salah's Understat id is `1250` (confirmed in `data/raw/understat/player_stats/2026-07-26/EPL_2025-2026_102544_926171.json`), so his computed `player_id` is `100001250`. Leandro Trossard's Understat id is `7698`, so his computed `player_id` is `100007698`.

Write `transform/seeds/player_extra_info.csv`:

```csv
player_id,nationality,date_of_birth,shirt_number
100001250,Egypt,1992-06-15,11
100007698,Belgium,1994-12-04,19
```

- [ ] **Step 2: Declare column types in `transform/dbt_project.yml`**

Modify the `seeds:` block (currently only has a `player_name_map` entry):

```yaml
seeds:
  transform:
    player_name_map:
      +column_types:
        source: text
        raw_player_name: text
        team_id: integer
        player_id: integer
    player_extra_info:
      +column_types:
        player_id: integer
        nationality: text
        date_of_birth: date
        shirt_number: integer
```

- [ ] **Step 3: Add schema tests in `transform/seeds/_seeds.yml`**

This file doesn't exist yet — create it:

```yaml
version: 2

seeds:
  - name: player_extra_info
    description: "Manual backfill of nationality/date_of_birth/shirt_number for understat-anchored
                  players (no football_data_org squad row at all, e.g. Mohamed Salah, Leandro
                  Trossard) — football_data_org is otherwise the only source with these fields.
                  Keyed on the same computed player_id used in silver.players
                  (understat_id + 100000000). See
                  docs/superpowers/specs/2026-08-03-player-extra-info-seed-design.md."
    columns:
      - name: player_id
        tests:
          - unique
          - not_null
```

- [ ] **Step 4: Load the seed**

Run: `dbt seed --select player_extra_info`
Expected: `Completed successfully` with `1 of 1 OK loaded seed file ... player_extra_info`.

- [ ] **Step 5: Run the schema tests**

Run: `dbt test --select player_extra_info`
Expected: `Completed successfully`, 2 tests passed (`unique_player_extra_info_player_id`, `not_null_player_extra_info_player_id`).

- [ ] **Step 6: Commit**

```bash
git add transform/seeds/player_extra_info.csv transform/seeds/_seeds.yml transform/dbt_project.yml
git commit -m "feat: add player_extra_info seed for understat-anchored player bio backfill"
```

---

### Task 2: Wire the seed into `silver.players`

**Files:**
- Modify: `transform/models/silver/players.sql`

**Interfaces:**
- Consumes: seed `player_extra_info` (`player_id`, `nationality`, `date_of_birth`, `shirt_number`) from Task 1.
- Produces: `silver.players.nationality`/`.date_of_birth`/`.shirt_number` now populated for any understat-anchored `player_id` present in the seed — consumed downstream by `gold.player_profile` (no changes needed there; it selects `*` worth of columns straight from `silver.players` by name).

- [ ] **Step 1: Edit the `understat_only` CTE**

In `transform/models/silver/players.sql`, replace:

```sql
understat_only as (
    select
        understat_id + 100000000 as player_id,
        raw_player_name as player_name,
        position,
        cast(null as date) as date_of_birth,
        cast(null as text) as nationality,
        cast(null as int) as shirt_number,
        cast(null as int) as team_id,
        league,
        ingestion_time
    from understat_matched_to_fdo
    where fdo_match_id is null
)
```

with:

```sql
understat_only as (
    select
        u.understat_id + 100000000 as player_id,
        u.raw_player_name as player_name,
        u.position,
        extra.date_of_birth,
        extra.nationality,
        extra.shirt_number,
        cast(null as int) as team_id,
        u.league,
        u.ingestion_time
    from understat_matched_to_fdo u
    left join {{ ref('player_extra_info') }} extra
        on extra.player_id = u.understat_id + 100000000
    where u.fdo_match_id is null
)
```

- [ ] **Step 2: Run the model**

Run: `dbt run --select players`
Expected: `Completed successfully`, `players` materialized as a table with no errors.

- [ ] **Step 3: Verify Salah and Trossard now have bio data**

Run: `psql -U postgres -d football -c "select player_id, player_name, nationality, date_of_birth, shirt_number from silver.players where player_id in (100001250, 100007698);"`
Expected: two rows — `100001250 | Mohamed Salah | Egypt | 1992-06-15 | 11` and `100007698 | Leandro Trossard | Belgium | 1994-12-04 | 19`.

- [ ] **Step 4: Run the existing grain tests to confirm nothing broke**

Run: `dbt test --select players`
Expected: `Completed successfully` — `unique_players_player_id` and `not_null_players_player_id`/`not_null_players_player_name` (declared in `transform/models/silver/_silver.yml`) still pass.

- [ ] **Step 5: Commit**

```bash
git add transform/models/silver/players.sql
git commit -m "feat: backfill understat-anchored player bio fields from player_extra_info seed"
```

---

### Task 3: Update documentation

**Files:**
- Modify: `docs/gold_data_contract.md`
- Modify: `CLAUDE.md`
- Modify: `transform/models/silver/_silver.yml`

**Interfaces:** none (documentation only).

- [ ] **Step 1: Update the English section of `docs/gold_data_contract.md`**

Replace:

```
| `nationality` | text | Country name as reported by football_data_org (single source, not normalized) | Yes — always `NULL` for understat-anchored players (football_data_org is the only source with this field) |
| `date_of_birth` | date | Date of birth | Yes — always `NULL` for understat-anchored players (football_data_org is the only source with this field) |
```

with:

```
| `nationality` | text | Country name as reported by football_data_org (single source, not normalized) | Yes — `NULL` for understat-anchored players unless backfilled via the `player_extra_info.csv` seed (football_data_org is otherwise the only source with this field) |
| `date_of_birth` | date | Date of birth | Yes — `NULL` for understat-anchored players unless backfilled via the `player_extra_info.csv` seed (football_data_org is otherwise the only source with this field) |
```

Then replace the "known limitations" bullet:

```
- **understat-anchored players (no football_data_org row) have `NULL`
  `date_of_birth`/`nationality`/`shirt_number`.** These three are only ever
  populated from football_data_org — there's no seed backfilling them today
  (a `player_extra_info.csv` seed was discussed for this, not built).
  `position` is the exception: it's backfilled from Understat's own position
  tag for these players (see
  `docs/superpowers/specs/2026-08-03-squad-display-fixes-design.md`), so it's
  only `NULL` when Understat's raw tag is bare `S`.
```

with:

```
- **understat-anchored players (no football_data_org row) have `NULL`
  `date_of_birth`/`nationality`/`shirt_number` unless backfilled.** These
  three are otherwise only ever populated from football_data_org — a manual
  seed, `transform/seeds/player_extra_info.csv`, backfills known gaps (keyed
  on the same computed `player_id`; see
  `docs/superpowers/specs/2026-08-03-player-extra-info-seed-design.md`).
  `position` is handled differently: it's backfilled from Understat's own
  position tag for every understat-anchored player, not just seeded ones
  (see
  `docs/superpowers/specs/2026-08-03-squad-display-fixes-design.md`), so
  it's only `NULL` when Understat's raw tag is bare `S`.
```

- [ ] **Step 2: Update the French section of `docs/gold_data_contract.md`**

Replace:

```
| `nationality` | text | Nom du pays tel que rapporté par football_data_org (source unique, non normalisé) | Oui |
| `date_of_birth` | date | Date de naissance | Oui |
```

with:

```
| `nationality` | text | Nom du pays tel que rapporté par football_data_org (source unique, non normalisé) | Oui — `NULL` pour les joueurs ancrés sur understat, sauf complété via le seed `player_extra_info.csv` |
| `date_of_birth` | date | Date de naissance | Oui — `NULL` pour les joueurs ancrés sur understat, sauf complété via le seed `player_extra_info.csv` |
```

- [ ] **Step 3: Update the Vietnamese section of `docs/gold_data_contract.md`**

Replace:

```
| `nationality` | text | Tên quốc gia theo football_data_org (một nguồn duy nhất, chưa chuẩn hóa) | Có |
| `date_of_birth` | date | Ngày sinh | Có |
```

with:

```
| `nationality` | text | Tên quốc gia theo football_data_org (một nguồn duy nhất, chưa chuẩn hóa) | Có — `NULL` với cầu thủ neo theo understat, trừ khi được backfill qua seed `player_extra_info.csv` |
| `date_of_birth` | date | Ngày sinh | Có — `NULL` với cầu thủ neo theo understat, trừ khi được backfill qua seed `player_extra_info.csv` |
```

- [ ] **Step 4: Add the new seed to `CLAUDE.md`**

Replace:

```
- `seeds/` — manual CSV name→id mappings for sources with no native id: `team_name_map.csv`, `player_name_map.csv`
```

with:

```
- `seeds/` — manual CSV name→id mappings for sources with no native id: `team_name_map.csv`, `player_name_map.csv`; `player_extra_info.csv` backfills `nationality`/`date_of_birth`/`shirt_number` for understat-anchored players (no football_data_org row at all, e.g. Mohamed Salah)
```

- [ ] **Step 5: Update the `players` model description in `transform/models/silver/_silver.yml`**

Replace:

```
                  Understat-anchored rows have NULL date_of_birth/nationality/shirt_number/team_id —
                  football_data_org is the only source with those bio fields, and team_id is now
                  resolved per-season in silver.player_team_season, not stored here. position is the
```

with:

```
                  Understat-anchored rows have NULL date_of_birth/nationality/shirt_number unless
                  backfilled via transform/seeds/player_extra_info.csv (keyed on the same computed
                  player_id; see docs/superpowers/specs/2026-08-03-player-extra-info-seed-design.md) —
                  football_data_org is otherwise the only source with those bio fields. team_id is now
                  resolved per-season in silver.player_team_season, not stored here. position is the
```

- [ ] **Step 6: Commit**

```bash
git add docs/gold_data_contract.md CLAUDE.md transform/models/silver/_silver.yml
git commit -m "docs: document player_extra_info seed backfill in gold contract and CLAUDE.md"
```
