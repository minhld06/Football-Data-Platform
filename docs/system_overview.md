# System Overview — Football Data Platform

# English

## 1. Introduction

**Football Data Platform** is a full-cycle AI/Data Engineering internship project built around the **Medallion Architecture** (Bronze → Silver → Gold). It collects football data from three independent sources, transforms it through a versioned dbt pipeline, and serves it through a REST API, a web dashboard, and a Text-to-SQL chatbot.

- **Student**: Duy Minh LE — Sorbonne Université (L2-DANT)
- **Context**: AI internship at FSS (Financial Software Solutions)
- **Scope covered by this document**: Phase 1 (crawlers → Bronze → Silver/Gold → API → frontend → chatbot). Phase 2 (Lakehouse migration: MinIO, Iceberg, Spark, ClickHouse, local LLM) is planned but not yet started — see [Known limitations & future work](#11-known-limitations--future-work).

## 2. System architecture

```
┌────────────────┐   ┌────────────────┐   ┌────────────────┐
│ football-data   │   │  statbunker    │   │   understat     │
│ .org (REST API) │   │ (static HTML)  │   │ (Playwright/JS) │
└────────┬────────┘   └────────┬───────┘   └────────┬────────┘
         └─────────────────────┼────────────────────┘
                                ▼
          data/raw/{source}/{entity}/{date}/*.json
                                │  ingestion/ingest.py
                                │  (idempotent, SHA-256 content-hash dedup)
                                ▼
                 bronze.raw_documents  (PostgreSQL)
                                │  dbt: staging models (stg_*)
                                ▼
                 silver.*  (teams, matches, standings, players, player_team_season)
                                │  dbt: gold models
                                ▼
                 gold.*  (league_standings, match_results, player_performance, ...)
                                │
                 ┌──────────────┴───────────────┐
                 ▼                               ▼
      FastAPI backend (REST API)      Text-to-SQL chatbot (OpenRouter)
                 │                               │
                 └───────────────┬───────────────┘
                                  ▼
                    Next.js frontend (dashboard + chat widget)
```

Each layer has a distinct responsibility:
- **Bronze**: raw JSON payloads + metadata (`source`, `entity_type`, `content_hash`, `league`, `season`, `ingestion_time`) — supports replay, debugging, and source comparison.
- **Silver**: cleaned, deduplicated, source-unified entities, all keyed on football-data.org's numeric id (the only stable cross-source identifier).
- **Gold**: flat, business-ready tables — no complex joins at read time — consumed directly by the backend, frontend, and chatbot.

## 3. Tech stack

| Layer | Technology |
|---|---|
| Crawling | Python 3.11, `requests`, BeautifulSoup, Playwright |
| Database | PostgreSQL 16 |
| Transformation | dbt-core + dbt-postgres 1.11 |
| Backend API | FastAPI 0.136, psycopg3 |
| Frontend | Next.js 16 (App Router), React 19, Tailwind CSS v4 |
| Chatbot / LLM | OpenRouter (Text-to-SQL), 4 free-tier models |
| Infrastructure | Docker Compose (Postgres, pgAdmin, MinIO — MinIO staged ahead of Phase 2) |
| Testing | pytest (backend), dbt schema/grain tests (transform) |
| Tooling | Git/GitHub, VS Code, Claude Code CLI |

## 4. Data pipeline

### 4.1 Crawlers (`crawlers/`)

Three source types, each with its own collection method, sharing common utilities (`crawlers/common/`: rate limiter, retry with exponential backoff, structured logging, raw-file saving):

| Source | Type | Tool | Entities | Notes |
|---|---|---|---|---|
| football-data.org | REST API | `requests` | matches, standings, players | 10 req/min rate limit; official, structured JSON |
| statbunker | Static HTML | `requests` + BeautifulSoup | standings, player stats | Premier League only; no clear ToS/rate limit |
| understat | JS-rendered | Playwright | standings, player stats | xG/xGA/xPTS advanced metrics; EPL + Ligue 1 |

Raw output is saved to `data/raw/{source}/{entity}/{date}/*.json`, preserving every crawl snapshot for reproducibility.

### 4.2 Ingestion (`ingestion/`)

Loads raw JSON files into `bronze.raw_documents`. Idempotent by design: a SHA-256 hash of the normalized payload deduplicates re-runs (`ON CONFLICT DO NOTHING`), and a tracking table (`bronze.ingested_files`) skips re-hashing files whose mtime/size are unchanged, so cost scales with new files rather than the full accumulated history.

### 4.3 Transformation (dbt, `transform/`)

| Layer | Models | Purpose |
|---|---|---|
| Staging (`stg_*`) | 7 | One model per source/entity; light typing/renaming, reads from `bronze` |
| Silver | 5 (`teams`, `matches`, `standings`, `players`, `player_team_season`) | Cleaned, deduped, source-unified, keyed on football-data.org id |
| Gold | 8 (`league_standings`, `match_results`, `player_performance`, `player_profile`, `search_aliases`, `team_form_last_5_matches`, `team_profile`, `team_standings_by_matchday`) | Flat, query-ready, consumed directly by API/frontend/chatbot |
| Snapshot | 1 (`snapshot_football_data_org__standings`) | SCD2 history of standings over time |

15 dbt tests enforce grain uniqueness and cross-source mapping coverage (e.g. `assert_gold_league_standings_unique_grain`, `assert_player_names_mapped`, `assert_is_on_loan_consistent`) — full column-by-column contract, including nullability caveats, is documented in [`docs/gold_data_contract.md`](gold_data_contract.md).

## 5. Backend API

FastAPI application (`backend/`), 18 endpoints across 6 routers, all reading from `gold.*`:

| Router | Endpoints |
|---|---|
| `leagues` | `GET /api/leagues`, `GET /api/leagues/{league}/teams`, `GET /api/leagues/{league}/standings`, `GET /api/leagues/{league}/matches` |
| `teams` | `GET /api/teams/{team_id}`, `GET /api/teams/{team_id}/matches`, `GET /api/teams/{team_id}/form`, `GET /api/teams/{team_id}/squad` |
| `players` | `GET /api/players/top-scorers`, `GET /api/players/top-assists`, `GET /api/players/{player_id}`, `GET /api/players/{player_id}/performance` |
| `matches` | `GET /api/matches/recent`, `GET /api/matches/{match_id}` |
| `search` | `GET /api/search` |
| `chat` | `GET /api/chat/models`, `POST /api/chat` |
| — | `GET /api/health` |

## 6. Frontend

Next.js dashboard (`frontend/`) with a sports-dashboard visual identity, light/dark theme, and pages for leagues (`/leagues/[league]`), teams (`/teams/[id]`), players (`/players/[id]`), and search (`/search`). Reusable components include `StandingsTable`, `MatchList`, `SquadTable`, `TeamFormBadges`, `TopPerformersList`, `LeagueCard`, `SearchBox`, and an embedded `ChatWidget` for the chatbot.

## 7. Chatbot

Text-to-SQL chatbot over the `gold.*` schema, via OpenRouter, offering 4 free-tier models (OpenAI GPT-OSS 20B, Google Gemma 4 31B, NVIDIA Nemotron 3 Super/Nano). Two LLM calls per question — one to generate SQL, one to phrase the answer from the query results — separated by a **defense-in-depth guardrail layer**:

1. Heuristic pre-check for injection phrasing (rejects before any LLM/DB call).
2. System-prompt refusal contract for off-topic questions.
3. SQL whitelist/validator (single `SELECT`/`WITH` statement only, no DDL/DML keywords, table whitelist, forced `LIMIT 100`).
4. DB-role enforcement: the SQL runs under `chatbot_ro`, a read-only Postgres role scoped to `SELECT` on schema `gold` only.

Every request — success, refusal, or error — is logged to `chatbot.chat_logs` (model, generated SQL, tokens, latency, estimated cost). Full design rationale in [`docs/chatbot-design.md`](chatbot-design.md).

## 8. Testing & data quality

- **Backend**: 64 pytest tests across 4 files — `test_chat_engine.py` (37, guardrail/prompt unit tests), `test_chat_router.py` (9, `/api/chat` integration tests with faked LLM/DB), `test_openrouter_client.py` (7, HTTP client), `test_queries.py` (11, general query logic).
- **Transform (dbt)**: 15 tests covering grain uniqueness (error severity) and cross-source name-mapping coverage / consistency (warn severity, since unmapped names are expected routinely from transfers).

## 9. Deployment

Currently runs locally via Docker Compose (`docker-compose.yml`, wrapped by `manage.ps1`):

| Service | Role | Auto-starts with `up`? |
|---|---|---|
| `postgres` | PostgreSQL 16 | Yes |
| `pgadmin` | DB admin UI | Yes |
| `minio` | Object storage (staged for Phase 2) | Yes |
| `backend` | FastAPI API + chatbot | Yes |
| `frontend` | Next.js dashboard | Yes |
| `crawlers`, `ingestion`, `dbt` | One-shot jobs (`profiles: [tools]`) | No — run manually |

`backend` and `frontend` already have their own Dockerfiles, so a cloud deployment (e.g. Google Cloud Run + Cloud SQL for PostgreSQL) is a natural next step — see [Known limitations & future work](#11-known-limitations--future-work).

## 10. Known limitations & future work

- **Match-event-level data** (goal scorers, cards, substitutions) has no crawler yet — unstarted, unscheduled.
- **RAG chatbot approach** was scoped out for Phase 1 in favor of Text-to-SQL, since the data is already structured and relational; may be revisited if free-text/narrative questions become a real need.
- **Cloud deployment** is not yet done — optional Phase 1 deliverable, Google Cloud Run/Cloud SQL is the planned approach.
- **Phase 2** (Weeks 8–11, not started): migrate Bronze from Postgres to Iceberg tables on MinIO, dbt-postgres → dbt-spark, ClickHouse for Gold aggregation queries, local LLM (Ollama/vLLM) as a cloud-LLM alternative.

## 11. Conclusion

Phase 1 delivers a working, idempotent, and tested end-to-end pipeline — three heterogeneous data sources, a Medallion-architecture warehouse with dbt-enforced data quality, a documented REST API, a dashboard frontend, and a guardrailed Text-to-SQL chatbot — ready for the Week 7 checkpoint review and for the Phase 2 Lakehouse migration.

---

# Français

## 1. Introduction

**Football Data Platform** est un projet de stage AI/Data Engineering construit autour de l'**architecture Medallion** (Bronze → Silver → Gold). Il collecte des données football depuis trois sources indépendantes, les transforme via un pipeline dbt versionné, et les expose via une API REST, un tableau de bord web et un chatbot Text-to-SQL.

- **Étudiant** : Duy Minh LE — Sorbonne Université (L2-DANT)
- **Contexte** : stage IA chez FSS (Financial Software Solutions)
- **Périmètre de ce document** : Phase 1 (crawlers → Bronze → Silver/Gold → API → frontend → chatbot). La Phase 2 (migration Lakehouse : MinIO, Iceberg, Spark, ClickHouse, LLM local) est planifiée mais pas encore démarrée — voir [Limites connues et travaux futurs](#11-limites-connues-et-travaux-futurs).

## 2. Architecture du système

```
┌────────────────┐   ┌────────────────┐   ┌────────────────┐
│ football-data   │   │  statbunker    │   │   understat     │
│ .org (API REST) │   │ (HTML statique)│   │ (Playwright/JS) │
└────────┬────────┘   └────────┬───────┘   └────────┬────────┘
         └─────────────────────┼────────────────────┘
                                ▼
          data/raw/{source}/{entity}/{date}/*.json
                                │  ingestion/ingest.py
                                │  (idempotent, déduplication par hash SHA-256)
                                ▼
                 bronze.raw_documents  (PostgreSQL)
                                │  dbt : modèles staging (stg_*)
                                ▼
                 silver.*  (teams, matches, standings, players, player_team_season)
                                │  dbt : modèles gold
                                ▼
                 gold.*  (league_standings, match_results, player_performance, ...)
                                │
                 ┌──────────────┴───────────────┐
                 ▼                               ▼
      Backend FastAPI (API REST)       Chatbot Text-to-SQL (OpenRouter)
                 │                               │
                 └───────────────┬───────────────┘
                                  ▼
              Frontend Next.js (tableau de bord + chat widget)
```

Chaque couche a une responsabilité distincte :
- **Bronze** : payloads JSON bruts + métadonnées (`source`, `entity_type`, `content_hash`, `league`, `season`, `ingestion_time`) — permet le rejeu, le débogage et la comparaison des sources.
- **Silver** : entités nettoyées, dédupliquées, unifiées entre sources, toutes indexées sur l'id numérique de football-data.org (seul identifiant stable inter-sources).
- **Gold** : tables plates, prêtes à l'usage métier — sans jointures complexes à la lecture — consommées directement par le backend, le frontend et le chatbot.

## 3. Stack technique

| Couche | Technologie |
|---|---|
| Crawling | Python 3.11, `requests`, BeautifulSoup, Playwright |
| Base de données | PostgreSQL 16 |
| Transformation | dbt-core + dbt-postgres 1.11 |
| API backend | FastAPI 0.136, psycopg3 |
| Frontend | Next.js 16 (App Router), React 19, Tailwind CSS v4 |
| Chatbot / LLM | OpenRouter (Text-to-SQL), 4 modèles gratuits |
| Infrastructure | Docker Compose (Postgres, pgAdmin, MinIO — MinIO préparé pour la Phase 2) |
| Tests | pytest (backend), tests de schéma/grain dbt (transform) |
| Outils | Git/GitHub, VS Code, Claude Code CLI |

## 4. Pipeline de données

### 4.1 Crawlers (`crawlers/`)

Trois types de sources, chacune avec sa propre méthode de collecte, partageant des utilitaires communs (`crawlers/common/` : rate limiter, retry avec backoff exponentiel, logging structuré, sauvegarde des fichiers bruts) :

| Source | Type | Outil | Entités | Remarques |
|---|---|---|---|---|
| football-data.org | API REST | `requests` | matches, standings, players | Limite 10 req/min ; API officielle, JSON structuré |
| statbunker | HTML statique | `requests` + BeautifulSoup | standings, player stats | Premier League uniquement ; pas de ToS/rate limit clair |
| understat | HTML dynamique (JS) | Playwright | standings, player stats | Métriques avancées xG/xGA/xPTS ; EPL + Ligue 1 |

Les données brutes sont sauvegardées dans `data/raw/{source}/{entity}/{date}/*.json`, en conservant chaque snapshot de crawl pour la reproductibilité.

### 4.2 Ingestion (`ingestion/`)

Charge les fichiers JSON bruts dans `bronze.raw_documents`. Idempotent par conception : un hash SHA-256 du payload normalisé déduplique les ré-exécutions (`ON CONFLICT DO NOTHING`), et une table de suivi (`bronze.ingested_files`) évite de re-hasher les fichiers dont le mtime/la taille n'ont pas changé — le coût dépend donc des nouveaux fichiers, pas de tout l'historique accumulé.

### 4.3 Transformation (dbt, `transform/`)

| Couche | Modèles | Rôle |
|---|---|---|
| Staging (`stg_*`) | 7 | Un modèle par source/entité ; typage/renommage léger, lit depuis `bronze` |
| Silver | 5 (`teams`, `matches`, `standings`, `players`, `player_team_season`) | Nettoyé, dédupliqué, unifié entre sources, indexé sur l'id football-data.org |
| Gold | 8 (`league_standings`, `match_results`, `player_performance`, `player_profile`, `search_aliases`, `team_form_last_5_matches`, `team_profile`, `team_standings_by_matchday`) | Plat, prêt pour requêtage, consommé directement par API/frontend/chatbot |
| Snapshot | 1 (`snapshot_football_data_org__standings`) | Historique SCD2 des classements dans le temps |

15 tests dbt garantissent l'unicité du grain et la couverture du mapping inter-sources (ex. `assert_gold_league_standings_unique_grain`, `assert_player_names_mapped`, `assert_is_on_loan_consistent`) — le contrat détaillé colonne par colonne, avec les cas de nullabilité, est documenté dans [`docs/gold_data_contract.md`](gold_data_contract.md).

## 5. API backend

Application FastAPI (`backend/`), 18 endpoints répartis sur 6 routers, tous lisant depuis `gold.*` :

| Router | Endpoints |
|---|---|
| `leagues` | `GET /api/leagues`, `GET /api/leagues/{league}/teams`, `GET /api/leagues/{league}/standings`, `GET /api/leagues/{league}/matches` |
| `teams` | `GET /api/teams/{team_id}`, `GET /api/teams/{team_id}/matches`, `GET /api/teams/{team_id}/form`, `GET /api/teams/{team_id}/squad` |
| `players` | `GET /api/players/top-scorers`, `GET /api/players/top-assists`, `GET /api/players/{player_id}`, `GET /api/players/{player_id}/performance` |
| `matches` | `GET /api/matches/recent`, `GET /api/matches/{match_id}` |
| `search` | `GET /api/search` |
| `chat` | `GET /api/chat/models`, `POST /api/chat` |
| — | `GET /api/health` |

## 6. Frontend

Tableau de bord Next.js (`frontend/`) avec une identité visuelle « sports dashboard », thème clair/sombre, et des pages pour les ligues (`/leagues/[league]`), équipes (`/teams/[id]`), joueurs (`/players/[id]`) et la recherche (`/search`). Composants réutilisables : `StandingsTable`, `MatchList`, `SquadTable`, `TeamFormBadges`, `TopPerformersList`, `LeagueCard`, `SearchBox`, et un `ChatWidget` intégré pour le chatbot.

## 7. Chatbot

Chatbot Text-to-SQL sur le schéma `gold.*`, via OpenRouter, proposant 4 modèles gratuits (OpenAI GPT-OSS 20B, Google Gemma 4 31B, NVIDIA Nemotron 3 Super/Nano). Deux appels LLM par question — un pour générer le SQL, un pour formuler la réponse à partir des résultats — séparés par une **couche de guardrails en profondeur** :

1. Pré-vérification heuristique des formulations d'injection (rejet avant tout appel LLM/DB).
2. Contrat de refus au niveau du system prompt pour les questions hors-sujet.
3. Validateur/whitelist SQL (une seule instruction `SELECT`/`WITH`, aucun mot-clé DDL/DML, whitelist de tables, `LIMIT 100` forcé).
4. Application du rôle DB : le SQL s'exécute sous `chatbot_ro`, un rôle Postgres en lecture seule limité à `SELECT` sur le schéma `gold`.

Chaque requête — succès, refus ou erreur — est journalisée dans `chatbot.chat_logs` (modèle, SQL généré, tokens, latence, coût estimé). Justification complète du design dans [`docs/chatbot-design.md`](chatbot-design.md).

## 8. Tests & qualité des données

- **Backend** : 64 tests pytest répartis sur 4 fichiers — `test_chat_engine.py` (37, tests unitaires des guardrails/prompts), `test_chat_router.py` (9, tests d'intégration `/api/chat` avec LLM/DB simulés), `test_openrouter_client.py` (7, client HTTP), `test_queries.py` (11, logique de requêtes générales).
- **Transform (dbt)** : 15 tests couvrant l'unicité du grain (sévérité error) et la couverture/cohérence du mapping inter-sources (sévérité warn, car les noms non mappés sont attendus régulièrement lors des transferts).

## 9. Déploiement

Actuellement exécuté en local via Docker Compose (`docker-compose.yml`, encapsulé par `manage.ps1`) :

| Service | Rôle | Démarre avec `up` ? |
|---|---|---|
| `postgres` | PostgreSQL 16 | Oui |
| `pgadmin` | UI d'administration DB | Oui |
| `minio` | Stockage objet (préparé pour la Phase 2) | Oui |
| `backend` | API FastAPI + chatbot | Oui |
| `frontend` | Tableau de bord Next.js | Oui |
| `crawlers`, `ingestion`, `dbt` | Jobs ponctuels (`profiles: [tools]`) | Non — exécution manuelle |

`backend` et `frontend` disposent déjà de leur propre Dockerfile, ce qui rend un déploiement cloud (ex. Google Cloud Run + Cloud SQL for PostgreSQL) accessible comme prochaine étape — voir [Limites connues et travaux futurs](#11-limites-connues-et-travaux-futurs).

## 10. Limites connues et travaux futurs

- **Données au niveau des événements de match** (buteurs, cartons, remplacements) : pas encore de crawler — non démarré, non planifié.
- **Approche RAG pour le chatbot** : écartée en Phase 1 au profit du Text-to-SQL, les données étant déjà structurées et relationnelles ; pourra être reconsidérée si des questions en texte libre/narratives deviennent nécessaires.
- **Déploiement cloud** : pas encore réalisé — livrable optionnel de la Phase 1, Google Cloud Run/Cloud SQL est l'approche prévue.
- **Phase 2** (semaines 8–11, non démarrée) : migration de Bronze de Postgres vers des tables Iceberg sur MinIO, dbt-postgres → dbt-spark, ClickHouse pour les requêtes d'agrégation sur Gold, LLM local (Ollama/vLLM) comme alternative au LLM cloud.

## 11. Conclusion

La Phase 1 livre un pipeline de bout en bout fonctionnel, idempotent et testé — trois sources de données hétérogènes, un entrepôt en architecture Medallion avec qualité de données garantie par dbt, une API REST documentée, un frontend tableau de bord, et un chatbot Text-to-SQL sécurisé par des guardrails — prêt pour la revue de checkpoint de la semaine 7 et pour la migration Lakehouse de la Phase 2.

---

# Tiếng Việt

## 1. Giới thiệu

**Football Data Platform** là dự án thực tập AI/Data Engineering được xây dựng theo **kiến trúc Medallion** (Bronze → Silver → Gold). Dự án thu thập dữ liệu bóng đá từ ba nguồn độc lập, xử lý qua pipeline dbt được version hóa, và cung cấp dữ liệu qua REST API, dashboard web và chatbot Text-to-SQL.

- **Sinh viên**: Duy Minh LE — Sorbonne Université (L2-DANT)
- **Bối cảnh**: thực tập AI tại FSS (Financial Software Solutions)
- **Phạm vi tài liệu này**: Phase 1 (crawlers → Bronze → Silver/Gold → API → frontend → chatbot). Phase 2 (di chuyển sang Lakehouse: MinIO, Iceberg, Spark, ClickHouse, LLM local) đã được lên kế hoạch nhưng chưa bắt đầu — xem [Hạn chế hiện tại & hướng phát triển](#11-hạn-chế-hiện-tại--hướng-phát-triển).

## 2. Kiến trúc hệ thống

```
┌────────────────┐   ┌────────────────┐   ┌────────────────┐
│ football-data   │   │  statbunker    │   │   understat     │
│ .org (REST API) │   │ (HTML tĩnh)    │   │ (Playwright/JS) │
└────────┬────────┘   └────────┬───────┘   └────────┬────────┘
         └─────────────────────┼────────────────────┘
                                ▼
          data/raw/{source}/{entity}/{date}/*.json
                                │  ingestion/ingest.py
                                │  (idempotent, dedup bằng SHA-256 hash)
                                ▼
                 bronze.raw_documents  (PostgreSQL)
                                │  dbt: model staging (stg_*)
                                ▼
                 silver.*  (teams, matches, standings, players, player_team_season)
                                │  dbt: model gold
                                ▼
                 gold.*  (league_standings, match_results, player_performance, ...)
                                │
                 ┌──────────────┴───────────────┐
                 ▼                               ▼
        Backend FastAPI (REST API)      Chatbot Text-to-SQL (OpenRouter)
                 │                               │
                 └───────────────┬───────────────┘
                                  ▼
                Frontend Next.js (dashboard + chat widget)
```

Mỗi tầng có trách nhiệm riêng:
- **Bronze**: payload JSON thô + metadata (`source`, `entity_type`, `content_hash`, `league`, `season`, `ingestion_time`) — hỗ trợ replay, debug, và so sánh giữa các nguồn.
- **Silver**: entity đã được làm sạch, khử trùng lặp, hợp nhất giữa các nguồn, tất cả đều dùng id số của football-data.org làm khóa (identifier duy nhất ổn định xuyên nguồn).
- **Gold**: bảng phẳng, sẵn sàng cho nghiệp vụ — không cần join phức tạp khi đọc — được backend, frontend và chatbot sử dụng trực tiếp.

## 3. Tech stack

| Tầng | Công nghệ |
|---|---|
| Crawling | Python 3.11, `requests`, BeautifulSoup, Playwright |
| Database | PostgreSQL 16 |
| Transformation | dbt-core + dbt-postgres 1.11 |
| Backend API | FastAPI 0.136, psycopg3 |
| Frontend | Next.js 16 (App Router), React 19, Tailwind CSS v4 |
| Chatbot / LLM | OpenRouter (Text-to-SQL), 4 model free-tier |
| Infrastructure | Docker Compose (Postgres, pgAdmin, MinIO — MinIO chuẩn bị sẵn cho Phase 2) |
| Testing | pytest (backend), dbt schema/grain test (transform) |
| Công cụ | Git/GitHub, VS Code, Claude Code CLI |

## 4. Data pipeline

### 4.1 Crawlers (`crawlers/`)

Ba loại nguồn, mỗi nguồn có phương pháp thu thập riêng, dùng chung utility (`crawlers/common/`: rate limiter, retry với exponential backoff, logging có cấu trúc, lưu file raw):

| Nguồn | Loại | Công cụ | Entity | Ghi chú |
|---|---|---|---|---|
| football-data.org | REST API | `requests` | matches, standings, players | Giới hạn 10 req/phút; API chính thức, JSON có cấu trúc |
| statbunker | HTML tĩnh | `requests` + BeautifulSoup | standings, player stats | Chỉ có Premier League; không có ToS/rate limit rõ ràng |
| understat | HTML động (JS) | Playwright | standings, player stats | Có chỉ số nâng cao xG/xGA/xPTS; EPL + Ligue 1 |

Dữ liệu raw được lưu vào `data/raw/{source}/{entity}/{date}/*.json`, giữ lại từng snapshot crawl để đảm bảo khả năng tái tạo (reproducibility).

### 4.2 Ingestion (`ingestion/`)

Nạp file JSON raw vào `bronze.raw_documents`. Được thiết kế idempotent: hash SHA-256 của payload đã chuẩn hóa dùng để dedup khi chạy lại (`ON CONFLICT DO NOTHING`), và một bảng tracking (`bronze.ingested_files`) giúp bỏ qua việc hash lại các file có mtime/size không đổi — nhờ vậy chi phí chỉ tăng theo số file mới, không phải toàn bộ lịch sử đã tích lũy.

### 4.3 Transformation (dbt, `transform/`)

| Tầng | Số model | Vai trò |
|---|---|---|
| Staging (`stg_*`) | 7 | Mỗi model ứng với 1 nguồn/entity; chỉ typing/rename nhẹ, đọc từ `bronze` |
| Silver | 5 (`teams`, `matches`, `standings`, `players`, `player_team_season`) | Đã làm sạch, dedup, hợp nhất nguồn, dùng id football-data.org làm khóa |
| Gold | 8 (`league_standings`, `match_results`, `player_performance`, `player_profile`, `search_aliases`, `team_form_last_5_matches`, `team_profile`, `team_standings_by_matchday`) | Bảng phẳng, sẵn sàng truy vấn, được API/frontend/chatbot dùng trực tiếp |
| Snapshot | 1 (`snapshot_football_data_org__standings`) | Lịch sử SCD2 của bảng xếp hạng theo thời gian |

15 dbt test đảm bảo tính duy nhất của grain và độ phủ mapping xuyên nguồn (VD: `assert_gold_league_standings_unique_grain`, `assert_player_names_mapped`, `assert_is_on_loan_consistent`) — hợp đồng dữ liệu chi tiết từng cột, kèm các trường hợp nullable, được ghi trong [`docs/gold_data_contract.md`](gold_data_contract.md).

## 5. Backend API

Ứng dụng FastAPI (`backend/`), 18 endpoint chia trên 6 router, tất cả đọc từ `gold.*`:

| Router | Endpoint |
|---|---|
| `leagues` | `GET /api/leagues`, `GET /api/leagues/{league}/teams`, `GET /api/leagues/{league}/standings`, `GET /api/leagues/{league}/matches` |
| `teams` | `GET /api/teams/{team_id}`, `GET /api/teams/{team_id}/matches`, `GET /api/teams/{team_id}/form`, `GET /api/teams/{team_id}/squad` |
| `players` | `GET /api/players/top-scorers`, `GET /api/players/top-assists`, `GET /api/players/{player_id}`, `GET /api/players/{player_id}/performance` |
| `matches` | `GET /api/matches/recent`, `GET /api/matches/{match_id}` |
| `search` | `GET /api/search` |
| `chat` | `GET /api/chat/models`, `POST /api/chat` |
| — | `GET /api/health` |

## 6. Frontend

Dashboard Next.js (`frontend/`) với nhận diện hình ảnh kiểu "sports dashboard", theme sáng/tối, và các trang cho giải đấu (`/leagues/[league]`), đội bóng (`/teams/[id]`), cầu thủ (`/players/[id]`), và tìm kiếm (`/search`). Các component tái sử dụng gồm `StandingsTable`, `MatchList`, `SquadTable`, `TeamFormBadges`, `TopPerformersList`, `LeagueCard`, `SearchBox`, và `ChatWidget` được nhúng cho chatbot.

## 7. Chatbot

Chatbot Text-to-SQL trên schema `gold.*`, qua OpenRouter, cung cấp 4 model free-tier (OpenAI GPT-OSS 20B, Google Gemma 4 31B, NVIDIA Nemotron 3 Super/Nano). Mỗi câu hỏi gọi LLM 2 lần — một lần để sinh SQL, một lần để diễn giải câu trả lời từ kết quả truy vấn — được tách biệt bởi **lớp guardrail nhiều tầng**:

1. Kiểm tra heuristic phát hiện prompt injection (từ chối trước khi gọi LLM/DB).
2. Cơ chế từ chối ở system prompt cho câu hỏi ngoài phạm vi bóng đá.
3. Whitelist/validator SQL (chỉ chấp nhận 1 câu `SELECT`/`WITH`, không có từ khóa DDL/DML, whitelist bảng, ép `LIMIT 100`).
4. Thực thi bằng DB role riêng: SQL chạy dưới role `chatbot_ro` — role Postgres chỉ có quyền `SELECT` trên schema `gold`.

Mọi request — thành công, bị từ chối, hay lỗi — đều được log vào `chatbot.chat_logs` (model, SQL đã sinh, số token, độ trễ, chi phí ước tính). Lý do thiết kế chi tiết trong [`docs/chatbot-design.md`](chatbot-design.md).

## 8. Testing & chất lượng dữ liệu

- **Backend**: 64 test pytest trên 4 file — `test_chat_engine.py` (37, unit test cho guardrail/prompt), `test_chat_router.py` (9, integration test `/api/chat` với LLM/DB được fake), `test_openrouter_client.py` (7, HTTP client), `test_queries.py` (11, logic truy vấn chung).
- **Transform (dbt)**: 15 test bao phủ tính duy nhất của grain (severity error) và độ phủ/tính nhất quán của mapping xuyên nguồn (severity warn, vì tên chưa map được là chuyện bình thường khi có chuyển nhượng).

## 9. Deployment

Hiện đang chạy local qua Docker Compose (`docker-compose.yml`, được wrap bởi `manage.ps1`):

| Service | Vai trò | Tự start khi `up`? |
|---|---|---|
| `postgres` | PostgreSQL 16 | Có |
| `pgadmin` | UI quản trị DB | Có |
| `minio` | Object storage (chuẩn bị cho Phase 2) | Có |
| `backend` | API FastAPI + chatbot | Có |
| `frontend` | Dashboard Next.js | Có |
| `crawlers`, `ingestion`, `dbt` | Job chạy 1 lần (`profiles: [tools]`) | Không — chạy thủ công |

`backend` và `frontend` đã có sẵn Dockerfile riêng, nên deploy lên cloud (VD: Google Cloud Run + Cloud SQL for PostgreSQL) là bước tiếp theo khả thi — xem [Hạn chế hiện tại & hướng phát triển](#11-hạn-chế-hiện-tại--hướng-phát-triển).

## 10. Hạn chế hiện tại & hướng phát triển

- **Dữ liệu cấp độ sự kiện trận đấu** (ghi bàn, thẻ phạt, thay người): chưa có crawler — chưa bắt đầu, chưa lên lịch.
- **Hướng tiếp cận RAG cho chatbot**: bị loại khỏi Phase 1 để ưu tiên Text-to-SQL, vì dữ liệu đã có cấu trúc quan hệ sẵn; có thể cân nhắc lại nếu nhu cầu câu hỏi dạng văn bản tự do/tường thuật trở nên thực tế.
- **Deploy cloud**: chưa thực hiện — deliverable optional của Phase 1, hướng đi dự kiến là Google Cloud Run/Cloud SQL.
- **Phase 2** (tuần 8–11, chưa bắt đầu): di chuyển Bronze từ Postgres sang bảng Iceberg trên MinIO, dbt-postgres → dbt-spark, ClickHouse cho truy vấn aggregation trên Gold, LLM local (Ollama/vLLM) như phương án thay thế LLM cloud.

## 11. Kết luận

Phase 1 đã hoàn thiện một pipeline end-to-end hoạt động được, idempotent và có test đầy đủ — ba nguồn dữ liệu khác nhau, một data warehouse theo kiến trúc Medallion với chất lượng dữ liệu được đảm bảo bằng dbt, một REST API có tài liệu, một frontend dashboard, và một chatbot Text-to-SQL được bảo vệ bằng guardrail — sẵn sàng cho buổi review checkpoint tuần 7 và cho quá trình di chuyển sang Lakehouse ở Phase 2.
