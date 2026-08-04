# Player Extra Info CSV Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backfill `shirt_number` for every Premier League player (football_data_org never returns it) and `nationality`/`date_of_birth`/`shirt_number` for as many of the remaining 92 Understat-anchored gap players as possible, using a ChatGPT-compiled reference CSV of 2025-26 PL squads, by growing `player_extra_info.csv` from 2 rows to 527 and widening its role in `silver/players.sql` to cover fdo-anchored players too.

**Architecture:** One dbt seed (`transform/seeds/player_extra_info.csv`, unchanged shape, more rows) left-joined via `coalesce()` into *both* branches of `silver/players.sql`'s player-identity union (today only the `understat_only` branch uses it). The seed's rows are produced by matching the reference CSV against `silver.players` (Premier League only) through a multi-pass SQL matching script — not hand-typed — to avoid transcription error across 527 rows.

**Tech Stack:** dbt-core + dbt-postgres (existing `transform/` project), CSV seed, PostgreSQL (`unaccent`, `pg_trgm` extensions used only for the one-off matching script, not persisted in any model).

## Global Constraints

- Run all `dbt` commands from the `transform/` directory, with `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` set in the environment.
- `gold.player_profile` is a **view**; `silver.players` is a **table**. After touching the seed or `players.sql`, always run a full `dbt build` (or `dbt run` with no `--select`) — a scoped `dbt run --select players` does `drop ... cascade` on the table and silently leaves the dependent view stale. Verify against `gold.player_profile` directly, not just `silver.players`.
- `player_extra_info` only supplies bio fields (`nationality`/`date_of_birth`/`shirt_number`) keyed by `player_id`. It never touches team assignment — a stale `team_id` elsewhere in the pipeline doesn't block this work.
- Ligue-1 stays out of scope (the reference CSV is Premier-League-only; Ligue-1's gap is a separate, already-documented limitation).
- Design reference: [`docs/superpowers/specs/2026-08-04-player-extra-info-csv-backfill-design.md`](../specs/2026-08-04-player-extra-info-csv-backfill-design.md).
- Source reference CSV (user-supplied, not part of the repo): `C:\Users\Admin\Downloads\premier_league_2025_26_players.csv` — columns `team,name,nationality,date_of_birth,shirt_number`, 537 data rows, one row per 2025-26 Premier League squad member.

---

### Task 1: Resolve the reference CSV into `player_extra_info.csv`

**Files:**
- Modify: `transform/seeds/player_extra_info.csv` (currently 2 rows: Salah, Trossard — grows to 527)

**Interfaces:**
- Produces: seed table `player_extra_info` with the same columns as today (`player_id`, `nationality`, `date_of_birth`, `shirt_number`) — consumed by Task 2. No schema/test changes needed (`transform/seeds/_seeds.yml`'s `unique`/`not_null` tests on `player_id` and `dbt_project.yml`'s `+column_types` already cover this seed).

- [ ] **Step 1: Load the reference CSV into a temp Postgres table**

Requires the Docker Postgres container running (`docker compose ps` should show `postgres` as `Up`/`healthy`).

Run (from the project root, Git Bash):
```bash
docker compose exec -T postgres psql -U postgres -d football -c "
drop table if exists tmp_csv_players;
create table tmp_csv_players (team text, name text, nationality text, date_of_birth date, shirt_number int);
"
docker compose exec -T postgres psql -U postgres -d football -c "\copy tmp_csv_players from stdin with (format csv, header true)" < "/c/Users/Admin/Downloads/premier_league_2025_26_players.csv"
```
Expected: `CREATE TABLE` then `COPY 537`.

- [ ] **Step 2: Run the matching script and export the resolved rows**

Save this as `transform/seeds/_scratch_resolve_extra_info.sql` (delete it in Step 5 — it's a one-off migration script, not a project artifact):

```sql
create extension if not exists unaccent;
create extension if not exists pg_trgm;

drop table if exists tmp_resolved;
create temp table tmp_resolved as
with team_map(csv_team, team_id) as (
  values
  ('Arsenal',57),('Aston Villa',58),('Burnley',328),('AFC Bournemouth',1044),
  ('Brentford',402),('Brighton & Hove Albion',397),('Chelsea',61),('Crystal Palace',354),
  ('Everton',62),('Fulham',63),('Leeds United',341),('Liverpool',64),
  ('Manchester City',65),('Manchester United',66),('Newcastle United',67),
  ('Nottingham Forest',351),('Sunderland',71),('Tottenham Hotspur',73),
  ('West Ham United',563),('Wolverhampton Wanderers',76)
),
excluded(csv_team, csv_name) as (
  values
    -- Douglas Luiz transferred to Juventus in 2024; the CSV still lists him
    -- at Aston Villa, which looks like stale/hallucinated ChatGPT output.
    ('Aston Villa','Douglas Luiz Soares de Paulo'),
    -- Same surname, different real person from our existing "Bertrand Traoré"
    -- (Sunderland) — merging would corrupt his data.
    ('AFC Bournemouth','Hamed Traorè'),
    -- Same first+last name, different real person from our existing,
    -- already-resolved "João Pedro" (Chelsea) — too risky to merge blind.
    ('Nottingham Forest','João Pedro Ferreira da Silva')
),
manual_overrides(csv_team, csv_name, override_id) as (
  values
    ('AFC Bournemouth','Álex Jiménez Sánchez',100012168),
    ('AFC Bournemouth','Marcos Senesi Barón',46046),
    ('AFC Bournemouth','Junior Kroupi',204241),
    ('Aston Villa','Jamaldeen Jimoh-Aloba',100013310),
    ('Burnley','Lesley Ugochukwu',153555),
    ('Chelsea','Andrey Nascimento dos Santos',166366),
    ('Chelsea','Marc Cucurella Saseta',100007134),
    ('Crystal Palace','Yéremy Pino Santos',152505),
    ('Everton','Idrissa Gana Gueye',100000668),
    ('Everton','Norberto Bercique Gomes Betuncal',125044),
    ('Fulham','Raúl Jiménez Rodríguez',3305),
    ('Manchester City','Bernardo Mota Veiga de Carvalho e Silva',100003635),
    ('Manchester City','Sávio Moreira de Oliveira',146352),
    ('Manchester United','Carlos Henrique Casimiro',100002248),
    ('Sunderland','Eliezer Mayenda Dossou',100013718),
    ('Tottenham Hotspur','João Maria Lobo Alves Palhares Costa Palhinha Gonçalves',100010715),
    ('West Ham United','Adama Traoré Diarra',100000900),
    ('West Ham United','Luis Guilherme Lira dos Santos',100013026),
    ('West Ham United','Mateus Gonçalo Espanha Fernandes',187216),
    ('Wolverhampton Wanderers','André Trindade da Costa Neto',100013022),
    ('Wolverhampton Wanderers','Hugo Bueno López',100010140),
    ('Wolverhampton Wanderers','Pedro Cardoso de Lima',100013156),
    ('Wolverhampton Wanderers','Rodrigo Martins Gomes',100012756),
    ('Wolverhampton Wanderers','Toti Gomes',100010293),
    ('Wolverhampton Wanderers','Yerson Mosquera Valdelamar',100009958)
),
csv_norm as (
  select c.*, tm.team_id,
    regexp_replace(lower(unaccent(c.name)), '[^a-z0-9]+', ' ', 'g') as norm_words,
    regexp_replace(lower(unaccent(c.name)), '[^a-z0-9]+', '', 'g') as norm_nospace
  from tmp_csv_players c
  join team_map tm on tm.csv_team = c.team
  where not exists (select 1 from excluded e where e.csv_team = c.team and e.csv_name = c.name)
),
players_norm as (
  select p.player_id, p.player_name, p.team_id,
    regexp_replace(lower(unaccent(p.player_name)), '[^a-z0-9]+', ' ', 'g') as norm_words,
    regexp_replace(lower(unaccent(p.player_name)), '[^a-z0-9]+', '', 'g') as norm_nospace
  from silver.players p
  where p.league = 'premier-league'
),
unique_names as (
  select norm_nospace, min(player_id) pid, count(*) cnt from players_norm group by norm_nospace having count(*) = 1
),
ranked as (
  select cn.team, cn.name, cn.date_of_birth, cn.nationality, cn.shirt_number, pn.player_id,
    case
      when pn.norm_nospace = cn.norm_nospace and pn.team_id = cn.team_id then 1
      when un.pid = pn.player_id and pn.norm_nospace = cn.norm_nospace then 2
      when pn.team_id = cn.team_id and (pn.norm_nospace like '%'||cn.norm_nospace||'%' or cn.norm_nospace like '%'||pn.norm_nospace||'%') then 3
      when pn.team_id = cn.team_id and (string_to_array(pn.norm_words,' ') <@ string_to_array(cn.norm_words,' ')) then 3
      when pn.team_id = cn.team_id and similarity(pn.norm_nospace, cn.norm_nospace) >= 0.4 then 4
      else null
    end as method_rank
  from csv_norm cn
  join players_norm pn on true
  left join unique_names un on un.norm_nospace = cn.norm_nospace
),
automated as (
  select team, name, date_of_birth, nationality, shirt_number, player_id,
    row_number() over (partition by team, name order by method_rank asc) as rn
  from ranked
  where method_rank is not null
),
resolved as (
  select cn.team, cn.name, cn.date_of_birth, cn.nationality, cn.shirt_number,
    coalesce(mo.override_id, a.player_id) as player_id
  from csv_norm cn
  left join manual_overrides mo on mo.csv_team = cn.team and mo.csv_name = cn.name
  left join automated a on a.team = cn.team and a.name = cn.name and a.rn = 1
)
select player_id, nationality, date_of_birth, shirt_number
from resolved
where player_id is not null
order by player_id;

\copy tmp_resolved to stdout with (format csv, header true)
```

Run:
```bash
docker compose exec -T postgres psql -U postgres -d football -q -f - < transform/seeds/_scratch_resolve_extra_info.sql > transform/seeds/player_extra_info.csv
```
Expected: `transform/seeds/player_extra_info.csv` now has 528 lines (1 header + 527 data rows).

- [ ] **Step 3: Verify the row count and check for duplicate `player_id`s**

Run: `wc -l transform/seeds/player_extra_info.csv`
Expected: `528`.

Run:
```bash
docker compose exec -T postgres psql -U postgres -d football -c "
select count(*), count(distinct player_id) from tmp_resolved;
"
```
(Skip if `tmp_resolved` — a temp table — no longer exists in a new session; re-run Step 2's script if needed. This is a sanity check only, not required for the seed to be valid, since `unique`/`not_null` on `player_id` is already enforced by `transform/seeds/_seeds.yml` and will be re-checked in Step 5.)
Expected: both counts equal `527` (no `player_id` claimed by two different CSV rows).

- [ ] **Step 4: Spot-check a few rows**

Run: `grep -E "^(100001250|100007698|100002248|146352),|^10183," transform/seeds/player_extra_info.csv`
Expected:
```
10183,Portugal,1997-05-14,3
146352,Brazil,2004-04-10,26
100001250,Egypt,1992-06-15,11
100002248,Brazil,1992-02-23,18
100007698,Belgium,1994-12-04,19
```
(Salah/Trossard — the two pre-existing rows — are unchanged; 10183 is Rúben Dias; 146352 is Savinho; 100002248 is Casemiro, all matched via the CSV's full/legal names.)

- [ ] **Step 5: Load the seed and run its existing tests**

Run: `cd transform && dbt seed --select player_extra_info`
Expected: `Completed successfully`, `1 of 1 OK loaded seed file ... player_extra_info` with `527` rows (not the old `2`).

Run: `dbt test --select player_extra_info`
Expected: `Completed successfully`, 2 tests passed (`unique_player_extra_info_player_id`, `not_null_player_extra_info_player_id`) — this is the real duplicate-key guard, confirming Step 3's manual check.

- [ ] **Step 6: Clean up the scratch script**

```bash
rm transform/seeds/_scratch_resolve_extra_info.sql
docker compose exec -T postgres psql -U postgres -d football -c "drop table if exists tmp_csv_players;"
```

- [ ] **Step 7: Commit**

```bash
git add transform/seeds/player_extra_info.csv
git commit -m "feat: grow player_extra_info seed from 2 to 527 rows via CSV-matched backfill"
```

---

### Task 2: Widen `silver/players.sql` to use the seed for fdo-anchored players too

**Files:**
- Modify: `transform/models/silver/players.sql`

**Interfaces:**
- Consumes: seed `player_extra_info` (`player_id`, `nationality`, `date_of_birth`, `shirt_number`) — same interface as before, from Task 1.
- Produces: `silver.players.shirt_number` now populated for fdo-anchored players too (previously always `NULL` since football_data_org never returns it) — consumed downstream by `gold.player_profile` unchanged (it selects columns by name from `silver.players`).

- [ ] **Step 1: Edit the `fdo_players` CTE**

In `transform/models/silver/players.sql`, replace:

```sql
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
```

with:

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

- [ ] **Step 2: Rebuild fully**

Run: `dbt build` (from `transform/`, no `--select` — required per Global Constraints, since a scoped run would leave `gold.player_profile` stale).
Expected: `Completed successfully`, all models/seeds/tests green.

- [ ] **Step 3: Verify the null counts dropped**

Run:
```bash
docker compose exec -T postgres psql -U postgres -d football -c "
select
  count(*) filter (where nationality is null) as null_nat,
  count(*) filter (where date_of_birth is null) as null_dob,
  count(*) filter (where shirt_number is null) as null_shirt
from gold.player_profile
where league = 'premier-league';
"
```
Expected: all three counts well below the pre-change baseline (`92`/`93`/`662`) — `null_shirt` in particular should drop from `662` to roughly the ~10 rows this CSV couldn't resolve (see the spec's "left unresolved" list) plus any players not in the CSV's 20-team coverage.

- [ ] **Step 4: Confirm existing grain tests still pass**

Run: `dbt test --select players`
Expected: `Completed successfully` — `unique_players_player_id`, `not_null_players_player_id`, `not_null_players_player_name` all still pass.

- [ ] **Step 5: Commit**

```bash
git add transform/models/silver/players.sql
git commit -m "feat: backfill shirt_number for fdo-anchored players via player_extra_info seed"
```

---

### Task 3: Update documentation

**Files:**
- Modify: `docs/gold_data_contract.md`
- Modify: `CLAUDE.md`
- Modify: `transform/models/silver/_silver.yml`

**Interfaces:** none (documentation only).

- [ ] **Step 1: Update the English `shirt_number` row and "known limitations" bullet in `docs/gold_data_contract.md`**

Replace:
```
| `shirt_number` | int | Shirt number | Yes — `NULL` for understat-anchored players unless backfilled via the `player_extra_info.csv` seed (football_data_org is otherwise the only source with this field) |
```
with:
```
| `shirt_number` | int | Shirt number | Yes — football_data_org's squad endpoint never returns this field at all (confirmed: 0 of 1,180 crawled Premier League squad records have the key), so every player's value comes from the `player_extra_info.csv` seed; `NULL` for any player the seed doesn't cover |
```

Replace the bullet:
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
with:
```
- **`shirt_number` is never provided by football_data_org, for any player.**
  It's sourced entirely from the `player_extra_info.csv` seed, which also
  backfills `nationality`/`date_of_birth` for understat-anchored players (no
  football_data_org row at all) — keyed on `player_id` (see
  `docs/superpowers/specs/2026-08-03-player-extra-info-seed-design.md` and
  `docs/superpowers/specs/2026-08-04-player-extra-info-csv-backfill-design.md`).
  A player the seed doesn't cover simply has `NULL` for whichever field it
  would have supplied. `position` is handled differently: it's backfilled
  from Understat's own position tag for every understat-anchored player, not
  just seeded ones (see
  `docs/superpowers/specs/2026-08-03-squad-display-fixes-design.md`), so
  it's only `NULL` when Understat's raw tag is bare `S`.
```

- [ ] **Step 2: Update the French and Vietnamese `shirt_number` rows in `docs/gold_data_contract.md`**

Replace (French section):
```
| `shirt_number` | int | Numéro de maillot | Oui |
```
with:
```
| `shirt_number` | int | Numéro de maillot | Oui — jamais fourni par football_data_org ; provient entièrement du seed `player_extra_info.csv` |
```

Replace (Vietnamese section):
```
| `shirt_number` | int | Số áo | Có |
```
with:
```
| `shirt_number` | int | Số áo | Có — football_data_org không bao giờ cung cấp trường này; toàn bộ dữ liệu lấy từ seed `player_extra_info.csv` |
```

- [ ] **Step 3: Update `CLAUDE.md`'s seed description**

Replace:
```
`player_extra_info.csv` backfills `nationality`/`date_of_birth`/`shirt_number` for understat-anchored players (no football_data_org row at all, e.g. Mohamed Salah)
```
with:
```
`player_extra_info.csv` backfills `shirt_number` for every Premier League player (football_data_org never returns it) and `nationality`/`date_of_birth`/`shirt_number` for understat-anchored players (no football_data_org row at all, e.g. Mohamed Salah)
```

- [ ] **Step 4: Update the `players` model description in `transform/models/silver/_silver.yml`**

Replace:
```
                  Understat-anchored rows have NULL date_of_birth/nationality/shirt_number unless
                  backfilled via transform/seeds/player_extra_info.csv (keyed on the same computed
                  player_id; see docs/superpowers/specs/2026-08-03-player-extra-info-seed-design.md) —
                  football_data_org is otherwise the only source with those bio fields. team_id is now
```
with:
```
                  Understat-anchored rows have NULL date_of_birth/nationality/shirt_number unless
                  backfilled via transform/seeds/player_extra_info.csv (keyed on the same computed
                  player_id; see docs/superpowers/specs/2026-08-03-player-extra-info-seed-design.md and
                  docs/superpowers/specs/2026-08-04-player-extra-info-csv-backfill-design.md). fdo-anchored
                  rows use the same seed as a coalesce fallback for shirt_number specifically, since
                  football_data_org's squad endpoint never returns that field for anyone. team_id is now
```

- [ ] **Step 5: Commit**

```bash
git add docs/gold_data_contract.md CLAUDE.md transform/models/silver/_silver.yml
git commit -m "docs: document the widened player_extra_info seed scope"
```
