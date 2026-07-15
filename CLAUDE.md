# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

End-to-end football data platform built around the **Medallion Architecture** (Bronze → Silver → Gold):
1. **Crawlers** — collect raw data from three sources into `data/raw/`
2. **Ingestion** — load raw JSON files into the `bronze` PostgreSQL schema
3. **Silver/Gold** — planned dbt transformation layers (schemas exist, models not yet built)
4. **API / UI / Chatbot** — planned downstream layers

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

Output lands in `data/raw/{source}/{entity_type}/{YYYY-MM-DD}/{filename}_{HHMMSS_ffffff}.json`.

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
```

Ingestion is **idempotent**: re-running is safe. Deduplication uses a SHA-256 hash of the normalized JSON payload; `ON CONFLICT DO NOTHING` skips unchanged files.

## Docker

```powershell
# Start infrastructure (Postgres + pgAdmin + MinIO)
docker compose up -d

# Run crawlers once
docker compose run --rm crawlers python crawlers/football_data_org/client.py

# Run ingestion once
docker compose run --rm ingestion

# Ingestion with args
docker compose run --rm ingestion --source football_data_org --date 2026-07-14
```

Services `crawlers` and `ingestion` use `profiles: [tools]` so they don't auto-start with `docker compose up`.

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

Pipeline in `ingest.py` orchestrates four modules:
- `core/discovery.py` — walks `data/raw/` and extracts `source`, `entity_type`, `date` from the path structure
- `core/hashing.py` — reads JSON and computes SHA-256 of `sort_keys`-normalized content
- `core/metadata.py` — maps filename prefixes (e.g. `PL_`, `EPL_`, `Ligue_1_`) to canonical `league`/`season` values via `LEAGUE_CODES` whitelist
- `core/db.py` — upserts into `bronze.raw_documents` using `psycopg3`

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

## Environment Variables

| Variable | Used by | Purpose |
|---|---|---|
| `FOOTBALL_DATA_API_KEY` | crawlers | API key for football-data.org |
| `DATABASE_URL` | ingestion | `postgresql://user:pass@host:port/db` |
| `RAW_DATA_DIR` | both | override default `data/raw/` path |
| `POSTGRES_*` | docker-compose | DB credentials for Postgres container |
| `PGADMIN_*` | docker-compose | pgAdmin credentials |
| `MINIO_*` | docker-compose | MinIO object storage credentials |
