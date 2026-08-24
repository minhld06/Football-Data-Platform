# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Context

Full-cycle AI/Data Engineering internship project (stage). End-to-end football data platform built around the **Medallion Architecture** (Bronze → Silver → Gold):
1. **Crawlers** — collect raw data from three sources into `data/raw/`
2. **Ingestion** — load raw JSON files into the `bronze` PostgreSQL schema
3. **Silver/Gold** — dbt transformation layer in `transform/` (staging, silver, gold models, an SCD2 snapshot, and schema tests are built and running)
4. **API / UI / Chatbot** — planned downstream layers
5. **Phase 2 (later)** — migrate from a PostgreSQL-centric stack to an open-source Lakehouse stack (MinIO + Iceberg + Spark + ClickHouse)

This is a learning-by-building project: correctness, explainability, and clean engineering practice matter more than premature optimization. The student must understand all generated code and be able to explain it during mentor review.

## Learning Roadmap (12 Weeks)

### Week 1 — Onboarding & Environment Setup
Python 3.11+, Node.js 20+, Docker Desktop, Git/GitHub, VS Code, Claude Code. Deliverables: repo, README, `.gitignore`, minimal `docker-compose.yml` (Postgres + pgAdmin), basic AI-literacy exercise (generate/understand/modify a small script).

### Week 2 — Scraping / Data Collection
Collect from ≥3 source types: API (`football-data.org`), static HTML (StatBunker), JS-rendered (Understat). Raw data under `data/raw/{source}/{entity}/{date}/`. Requirements: rate limiting, retry with exponential backoff, logging, respect robots.txt/ToS, no aggressive or parallel crawling of the same host, keep raw snapshots for reproducibility.

### Week 3 — Ingestion & Bronze Layer
Design Bronze/Silver/Gold Postgres schemas. Bronze keeps raw payloads + metadata (`source`, `entity_type`, `entity_id`, `payload`, `raw_html`, `source_url`, `content_hash`, `ingestion_time`, `season`, `league`). Ingestion must be idempotent — re-running must not duplicate records (`content_hash`-based dedup).

### Week 4 — Silver & Gold with dbt
Set up `dbt-core` + `dbt-postgres` (`profiles.yml`, `dbt_project.yml`). Staging/silver/gold models. Silver: clean, dedupe, type, unify entities. Gold: flat, query-friendly, no complex joins at read time. Expected: schema tests, source declarations, docs, lineage graph, passing `dbt build`.

### Week 5 — Backend API & Frontend v1
Backend: FastAPI (recommended) or Next.js API routes. Endpoints: leagues, standings, teams, team matches, players, player performance, matches, match events, search. Frontend: Next.js — home, league, team detail, player, match, search pages.

### Week 6 — Frontend v2 + Chatbot MVP
LLM chatbot via OpenRouter. Approach: Text-to-SQL over Gold, RAG over summaries/profiles, or hybrid. Requirements: model selector, football-only scope, prompt-injection guardrails, SQL whitelist (if Text-to-SQL), read-only DB user, default `LIMIT`, log request/model/latency/tokens/estimated cost.

### Week 7 — Phase 1 Checkpoint
Demo full Phase 1: crawlers, raw files, Bronze/Silver/Gold, dbt run/build, API, frontend, chatbot. Reviewed on code quality, architecture, docs, Git history, ability to explain code, Phase 2 readiness.

### Week 8 — Lakehouse Infrastructure
Docker Compose: MinIO, Iceberg REST Catalog, Spark Master/Worker, ClickHouse, optional JupyterLab. Goal: migrate Bronze from Postgres to Iceberg tables on MinIO. Use Docker service names (not `localhost`) inside the network; bootstrap scripts idempotent; MinIO bucket must exist before Spark writes; Spark/Iceberg/Hadoop/AWS-SDK versions must be compatible.

### Week 9 — Spark & dbt-spark
Configure Spark + Iceberg. Migrate dbt models `dbt-postgres → dbt-spark`. Demonstrate schema evolution: start with a `silver_matches` schema, add a column (e.g. `attendance`), confirm old rows read back as `NULL` and new rows populate it; bonus: column rename or time travel.

### Week 10 — ClickHouse & Frontend Integration
ClickHouse queries Gold over Iceberg/MinIO. Backend supports datasource switching (`DATASOURCE=postgres` / `DATASOURCE=clickhouse`). Compare Postgres vs ClickHouse, especially on aggregation queries. Frontend mostly unchanged.

### Week 11 — Local LLM
Ollama or vLLM; candidate models Qwen2.5-7B-Instruct, Llama-3.1-8B-Instruct, Phi-3.5-mini (weaker machines). Integrate into the same chatbot interface. Compare cloud vs local on latency, quality, SQL-generation ability, cost, privacy/data residency.

### Week 12 — Capstone
Finalize technical report, slide deck, demo, repo cleanup, demo video, optional blog post. Presentation covers architecture, key design decisions, tradeoffs, benchmarks, lessons learned, future improvements.

## Current Project Stage

Current priority is **Phase 1**. Crawlers, Bronze ingestion, and the dbt Silver/Gold layer are built and working; downstream API/UI/chatbot layers (Week 5+) are next. Source-specific implementation details are in [Crawlers](#crawlers-crawlers), [Transform / dbt](#transform--dbt-transform), and [Architecture](#architecture--key-data-flow) below. Common crawler utilities live in `crawlers/common/` (logger, rate limiter, retry, raw-file saving). Content hashing for dedup lives separately in `ingestion/core/hashing.py`.

## Engineering Principles

**General**: prefer simple, working, explainable code. Don't over-engineer Phase 1 — optimize in Phase 2. Keep functions small, names clear, no hidden side effects. Don't duplicate logic that belongs in `common/`.

**Error handling**: don't add `try/except` blindly — use it for real external risk (HTTP, timeouts, JSON/HTML parsing, file I/O, DB connection/queries, env var loading, datetime parsing, unstable third-party libs). Never silently swallow errors (`except Exception: pass`). If a broad catch is necessary, log context, explain why it's broad, and re-raise serious errors. Rule (crawlers and ingestion alike): a single bad record/file may be skipped with logging, but config/DB/schema errors should fail fast.

**Logging**: prefer `logging`/the project logger over `print`. Include useful context (source, entity type, URL, file path, record ID, exception message) so logs are debuggable without opening the whole codebase.

## Data Rules

- **Raw data stays raw** — don't mutate Bronze payloads unnecessarily; keep enough metadata to trace provenance.
- **Bronze**: raw documents + metadata, supports replay/debugging/dedup/source comparison.
- **Silver**: cleaned, typed, deduplicated, source-specific staging, unified entities.
- **Gold**: flat, business-ready tables for frontend/chatbot/API — easy to query, no complex read-time joins.

## Security Rules

Never commit `.env`, API keys, passwords, tokens, secrets, `.venv/`, `__pycache__/`, or large raw datasets (unless intentionally sampled). Use `.env.example` for safe variable examples.

## Git Rules

Check `git status` before editing, review `git diff` after. Write meaningful commit messages (`feat: add statbunker crawler`, `fix: make bronze ingestion idempotent`) — avoid vague ones like `update`/`fix`/`final`.

## How Claude Should Work in This Repository

Before editing: read relevant files, explain current behavior, propose a short plan, show the intended diff, ask for approval if the change is large or risky.

While editing: keep changes minimal, avoid touching business logic unless asked, avoid unnecessary dependencies, explain why each change is needed, preserve existing style, update docs if behavior changes.

When reviewing: check error handling, logging, retry logic, idempotency, data paths, naming consistency, duplicated code, unsafe secrets, crawler fragility, database assumptions.

After editing: explain what changed, why, and how to test it.

## Running the Crawlers

All crawler commands run from the project root. Requires `.env` with `FOOTBALL_DATA_API_KEY`.

```powershell
# football-data.org (REST API, rate-limited to 10 req/min)
python crawlers/football_data_org/client.py

# StatBunker (static HTML scraping)
python crawlers/statbunker/scraper.py

# Understat (JS-rendered, uses Playwright)
python crawlers/understat/scraper.py
```

Output lands in `data/raw/{source}/{entity_type}/{YYYY-MM-DD}/{filename}_{HHMMSS_ffffff}.json`. To list raw files: `Get-ChildItem -Recurse data/raw -Filter *.json`.

First-time Playwright setup:
```powershell
pip install -r crawlers/requirements.txt
playwright install chromium
```

## Running the Ingestion Service

Requires PostgreSQL running (via Docker Compose) and `DATABASE_URL` in `.env`.

```powershell
# From project root — scans all of data/raw/
python ingestion/ingest.py

# Filter by source or date
python ingestion/ingest.py --source football_data_org
python ingestion/ingest.py --date 2026-07-14
python ingestion/ingest.py --source understat --date 2026-07-14

# Re-hash all matched files even if already tracked as ingested (bypasses bronze.ingested_files)
python ingestion/ingest.py --full-rehash
```

Ingestion is **idempotent**: re-running is safe. Deduplication uses a SHA-256 hash of the normalized JSON payload; `ON CONFLICT DO NOTHING` skips unchanged files.

Both crawlers and ingestion log to console **and** to a file under `logs/` (`crawler.log`, `ingestion.log`), overridable via `LOG_DIR`.

## Docker

`manage.ps1` (project root) wraps the commands below for the always-on services (postgres, pgadmin, minio, backend, frontend): `.\manage.ps1 start|stop|restart|status|logs|build`. It does not manage `crawlers`/`ingestion`/`dbt`, which stay one-shot `docker compose run --rm` commands.

```powershell
# Start infrastructure (Postgres + pgAdmin + MinIO)
docker compose up -d

# Inspect
docker compose ps
docker compose logs

# Stop infrastructure
docker compose down

# Run crawlers once
docker compose run --rm crawlers python crawlers/football_data_org/client.py

# Run ingestion once
docker compose run --rm ingestion

# Ingestion with args
docker compose run --rm ingestion --source football_data_org --date 2026-07-14
```

Services `crawlers` and `ingestion` use `profiles: [tools]` so they don't auto-start with `docker compose up`.

**Gotcha**: both Dockerfiles `COPY` source into the image at build time — `docker-compose.yml` only bind-mounts `data/` and `logs/`, not the source dirs. After editing crawler/ingestion code, rebuild before running, or `docker compose run` will silently use stale code:
```powershell
docker compose build crawlers ingestion
```

## Database Migrations

Migrations are plain SQL files applied manually:
```powershell
psql -U postgres -d football -f infra/postgres/migrations/001_bronze_raw_documents.sql
psql -U postgres -d football -f infra/postgres/migrations/002_silver_gold_schemas.sql
```

Migration `007_chatbot_readonly_role.sql` takes a psql variable instead of a hardcoded password (creates `chatbot_ro`, a read-only role scoped to `gold.*` that the chatbot backend will use to run LLM-generated SQL):
```powershell
psql -U postgres -d football -v chatbot_pw="$env:CHATBOT_DB_PASSWORD" -f infra/postgres/migrations/007_chatbot_readonly_role.sql
```

## Architecture — Key Data Flow

```
data/raw/{source}/{entity}/{date}/*.json
         ↓ ingestion/ingest.py
bronze.raw_documents (PostgreSQL)
         ↓ dbt staging + silver models (transform/models/staging, transform/models/silver)
silver.*
         ↓ dbt gold models (transform/models/gold)
gold.*
```

### Crawlers (`crawlers/`)

All crawlers share utilities from `crawlers/common/utils.py`:
- `save_raw(data, source, entity, filename)` — writes timestamped JSON to `data/raw/`
- `RateLimiter` — enforces minimum delay between requests
- `retry_request()` — GET with exponential backoff

Each source has its own module with a `crawl_competition()` function runnable as `__main__`:
- `football_data_org/client.py` — REST API (Premier League + Ligue 1)
- `statbunker/scraper.py` — HTML scraping with BeautifulSoup (PL only)
- `understat/scraper.py` — JS-rendered pages via Playwright (EPL + Ligue 1, includes xG/xGA/xPTS)

### Ingestion (`ingestion/`)

Pipeline in `ingest.py` orchestrates five modules:
- `core/discovery.py` — walks `data/raw/` and extracts `source`, `entity_type`, `date` from the path structure
- `core/hashing.py` — reads JSON and computes SHA-256 of `sort_keys`-normalized content
- `core/metadata.py` — maps filename prefixes (e.g. `PL_`, `EPL_`, `Ligue_1_`) to canonical `league`/`season` values via `LEAGUE_CODES` whitelist
- `core/db.py` — upserts into `bronze.raw_documents` using `psycopg3`
- `core/tracking.py` — tracks ingested files by path, mtime, and size to skip re-hashing unchanged files on re-runs

**Adding a new league**: update `LEAGUE_CODES` in `ingestion/core/metadata.py` and add the corresponding `comp_id` / league name to the relevant crawler.

### Transform / dbt (`transform/`)

dbt-core + dbt-postgres project. Run from `transform/` (needs `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` in the environment — `transform/profiles.yml` reads them via `env_var`):

```powershell
dbt build      # run models + tests + snapshot, in dependency order
dbt run        # models only
dbt test       # schema/grain tests only
dbt snapshot   # SCD2 standings history snapshot only
```

Layers:
- `models/staging/` — one `stg_*` model per source/entity, light typing/renaming only, reads from `bronze` via `_sources.yml`: `stg_football_data_org__{matches,players,standings}`, `stg_statbunker__{standings,player_stats}`, `stg_understat__{standings,player_stats}`
- `models/silver/` — cleaned, deduped, source-unified entities, all keyed on football_data_org's numeric id (the only stable cross-source key — never join on `team_name`/`player_name`): `teams`, `matches`, `standings`, `players`, `player_team_season` (season-scoped team resolution per player — see [`docs/gold_data_contract.md`](docs/gold_data_contract.md)'s `gold.player_performance`/`gold.player_profile` entries for the `resolved_via`/`parent_team_id`/`is_on_loan` fields it feeds)
- `models/gold/` — flat, business-ready tables, no complex read-time joins: `league_standings`, `team_form_last_5_matches`, `match_results`, `team_profile`, `player_profile`, `player_performance`, `team_standings_by_matchday`, `search_aliases`. `team_profile` and `player_profile` are materialized as **views** (not tables like the rest) so identity/age data stays current between dbt builds. Full column-by-column contract (including known nullability gotchas) is in [`docs/gold_data_contract.md`](docs/gold_data_contract.md) — read that before adding a gold consumer, don't re-derive it from the SQL
- `seeds/` — manual CSV name→id mappings for sources with no native id: `team_name_map.csv`, `player_name_map.csv`; `player_extra_info.csv` backfills `nationality`/`date_of_birth`/`shirt_number` for understat-anchored players (no football_data_org row at all, e.g. Mohamed Salah); `understat_transfer_team_override.csv` manually resolves `team_id` for mid-season-transfer players, keyed on `understat_id`, since Understat's `team_title` becomes a comma-joined string (e.g. `"Angers,Rennes"`) whose first-vs-last position isn't a reliable signal of the current club; `search_aliases_seed.csv` maps curated team/player nicknames (e.g. `mu`, `man c`, `mo salah`) to `team_id`/`player_id` for the backend's `GET /api/search` endpoint — unrelated to the source-name resolution seeds above
- `macros/` — `get_custom_schema.sql` (controls output schema naming), `normalize_player_name.sql` (name normalization used by the statbunker/understat player-matching fallback below)
- `snapshots/snapshot_football_data_org__standings.sql` — SCD2 history of standings over time

**Gotcha**: StatBunker/Understat data has no native `team_id`/`player_id`, so it's resolved by name — first via `seeds/team_name_map.csv` / `seeds/player_name_map.csv`, then (players only) a `normalize_player_name()` fallback match against `silver.players` by name alone, with no `team_id` condition. That's intentional: StatBunker/Understat scope a player to the club they played for at scrape time, while `silver.players` reflects the *current* squad — the two disagree for anyone transferred mid-season, and requiring a `team_id` match was found to drop ~20-30% of otherwise-correct name matches. A team/player that fails to resolve produces `NULL` on the source-specific columns (e.g. `xg`/`xga`/`xpts` in `gold.league_standings`, stat columns in `gold.player_performance`) rather than an error — see `docs/gold_data_contract.md`.

Grain and mapping coverage are enforced by dedicated tests — check these before assuming a schema change is safe:
- `tests/assert_*_unique_grain.sql` — grain checks (`assert_silver_standings_unique_grain`, `assert_player_team_season_unique_grain`, `assert_player_name_map_unique_grain`, `assert_gold_league_standings_unique_grain`, `assert_gold_match_results_unique_grain`, `assert_gold_team_form_unique_grain`, `assert_gold_player_performance_unique_grain` (composite `(player_id, season)` grain), `assert_gold_team_standings_by_matchday_unique_grain`, `assert_gold_search_aliases_unique_grain`)
- `tests/assert_team_names_mapped.sql`, `tests/assert_player_names_mapped.sql` — warn-severity checks that source-specific names resolved to a `team_id`/`player_id` (not hard-failing, since unmapped names are expected routinely from transfers/new signings)
- `tests/assert_understat_fdo_name_collision.sql` — warn-severity check flagging an Understat player name that normalizes to more than one football_data_org player; `silver/players.sql` treats such a collision as "no match" (mints its own `understat_id`-offset id) rather than risk merging two different real people, so this surfaces the case for a human to add a `seeds/player_name_map.csv` row if it turns out to be the same person
- `tests/assert_player_team_season_source_agreement.sql` — warn-severity check flagging player+seasons where understat and statbunker report different teams (a genuine mid-season transfer)
- `tests/assert_is_on_loan_consistent.sql` — cross-checks `is_on_loan` agrees between `gold.player_profile` and `gold.player_performance`
- `tests/assert_search_aliases_resolve.sql` — warn-severity check that every `gold.search_aliases.entity_id` still resolves to a real team/player
- `tests/assert_snapshot_standings_one_current_row.sql` — exactly one open (`dbt_valid_to is null`) row per team in the SCD2 snapshot

### Database Schema (`bronze.raw_documents`)

| Column | Notes |
|---|---|
| `source` | `football_data_org`, `statbunker`, `understat` |
| `entity_type` | `matches`, `standings` |
| `payload` | full raw JSON as JSONB |
| `content_hash` | SHA-256 of normalized payload; unique per `(source, entity_type, content_hash)` |
| `league` | canonical slug: `premier-league`, `ligue-1` |
| `season` | normalized to `YYYY-YYYY` format |
| `entity_id`, `source_url` | currently always NULL |

A companion table, `bronze.ingested_files`, tracks the relative path/mtime/size of each raw file that has already been ingested. On each run, `ingest.py` skips reading/hashing files whose mtime and size match the previous run, so cost scales with new/changed files rather than the total accumulated file count. Use `--full-rehash` to bypass this tracking table.

## Environment Variables

| Variable | Used by | Purpose |
|---|---|---|
| `FOOTBALL_DATA_API_KEY` | crawlers | API key for football-data.org |
| `DATABASE_URL` | ingestion | `postgresql://user:pass@host:port/db` |
| `RAW_DATA_DIR` | both | override default `data/raw/` path |
| `LOG_DIR` | both | override default `logs/` path for log files |
| `POSTGRES_*` | docker-compose, dbt | DB credentials for Postgres container; also read by `transform/profiles.yml` for dbt runs |
| `PGADMIN_*` | docker-compose | pgAdmin credentials |
| `MINIO_*` | docker-compose | MinIO object storage credentials |
| `OPENROUTER_API_KEY` | backend (chatbot) | API key for OpenRouter, used by the Text-to-SQL chatbot to call LLMs |
| `CHATBOT_DB_PASSWORD` | docker-compose | Password for the `chatbot_ro` read-only role (see [Database Migrations](#database-migrations)); docker-compose builds `CHATBOT_DATABASE_URL` from it for the backend service |

## Current Priority

1. Keep crawlers and ingestion stable and explainable.
2. Extend the dbt silver/gold layer as new entities/sources are added. Player-level data (staging/silver/gold) is already built; match-event-level data (goal scorers, cards, subs) has no crawler yet and is unstarted, unscheduled future work.
3. Keep `docs/gold_data_contract.md` in sync with any gold schema change.
4. Prepare Week 5 backend/frontend work on top of `gold.*`.
5. Keep documentation updated.
6. Avoid premature optimization.

Phase 1 focuses on correctness and learning. Phase 2 focuses on scalability: Lakehouse infrastructure, Spark, Iceberg, ClickHouse, and local LLMs.
