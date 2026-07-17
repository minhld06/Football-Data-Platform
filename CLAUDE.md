# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Context

Full-cycle AI/Data Engineering internship project (stage). End-to-end football data platform built around the **Medallion Architecture** (Bronze → Silver → Gold):
1. **Crawlers** — collect raw data from three sources into `data/raw/`
2. **Ingestion** — load raw JSON files into the `bronze` PostgreSQL schema
3. **Silver/Gold** — planned dbt transformation layers (schemas exist, models not yet built)
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

Current priority is **Phase 1**, and scraping/data collection is underway. Source-specific implementation details are in [Crawlers](#crawlers-crawlers) and [Architecture](#architecture--key-data-flow) below. Common crawler utilities live in `crawlers/common/` (logger, rate limiter, retry, raw-file saving). Content hashing for dedup lives separately in `ingestion/core/hashing.py`.

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

## Architecture — Key Data Flow

```
data/raw/{source}/{entity}/{date}/*.json
         ↓ ingestion/ingest.py
bronze.raw_documents (PostgreSQL)
         ↓ (planned) dbt silver models
silver.*
         ↓ (planned) dbt gold models
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
| `POSTGRES_*` | docker-compose | DB credentials for Postgres container |
| `PGADMIN_*` | docker-compose | pgAdmin credentials |
| `MINIO_*` | docker-compose | MinIO object storage credentials |

## Current Priority

1. Make crawlers stable and explainable.
2. Ensure raw data is saved consistently.
3. Move shared logic into `crawlers/common/`.
4. Prepare Bronze ingestion.
5. Keep documentation updated.
6. Avoid premature optimization.

Phase 1 focuses on correctness and learning. Phase 2 focuses on scalability: Lakehouse infrastructure, Spark, Iceberg, ClickHouse, and local LLMs.
