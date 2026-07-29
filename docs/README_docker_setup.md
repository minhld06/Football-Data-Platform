# Docker Setup — Football Data Platform

# 🇬🇧 English

Runs the whole pipeline (crawlers → ingestion → dbt → backend → frontend) on any machine with just **Docker Desktop** and **Git** — no local Python, Node.js, or `psql` install needed. Every service runs in its own container.

## 1. Clone and configure

```bash
git clone https://github.com/minhld06/Football-Data-Platform.git
cd Football-Data-Platform
cp .env.example .env
```
Edit `.env`: set `FOOTBALL_DATA_API_KEY` (free key from [football-data.org](https://www.football-data.org)) and choose Postgres/pgAdmin/MinIO credentials.

## 2. Start Postgres

```bash
docker compose up -d postgres
```

## 3. Apply database migrations

No local `psql` required — this pipes each SQL file into `psql` running inside the `postgres` container:
```bash
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/001_bronze_raw_documents.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/002_silver_gold_schemas.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/003_bronze_ingested_files.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/004_enable_unaccent_extension.sql
```

## 4. Crawl raw data

`data/raw/` is gitignored, so a fresh clone starts empty — you must crawl (or copy an existing `data/raw/` folder from another machine):
```bash
docker compose run --rm crawlers python crawlers/football_data_org/client.py
docker compose run --rm crawlers python crawlers/statbunker/scraper.py
docker compose run --rm crawlers python crawlers/understat/scraper.py
```

## 5. Ingest into Bronze

```bash
docker compose run --rm ingestion
```
Idempotent — safe to re-run any time; already-ingested files are skipped.

## 6. Build Silver → Gold with dbt

```bash
docker compose build dbt
docker compose run --rm dbt build
```
Or individually: `docker compose run --rm dbt run` / `test` / `snapshot`.

## 7. Start the backend and frontend

```bash
docker compose up -d backend frontend
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend (Swagger) | http://localhost:8000/docs |
| pgAdmin | http://localhost:5050 |
| MinIO console | http://localhost:9001 |

## After editing code

Dockerfiles `COPY` source at build time — rebuild before re-running, or the container will keep using stale code:
```bash
docker compose build backend frontend
docker compose up -d backend frontend
```

## Stop / clean up

```bash
docker compose down       # stops containers, keeps data (pgdata/minio_data volumes)
docker system prune -f    # reclaims unused image/build-cache space, does not touch volumes
```

## First-run summary

```bash
docker compose up -d postgres
# apply the 4 migrations from step 3
docker compose run --rm crawlers python crawlers/football_data_org/client.py
docker compose run --rm crawlers python crawlers/statbunker/scraper.py
docker compose run --rm crawlers python crawlers/understat/scraper.py
docker compose run --rm ingestion
docker compose build dbt
docker compose run --rm dbt build
docker compose up -d backend frontend
```

`crawlers`, `ingestion`, and `dbt` use `profiles: [tools]`, so they never auto-start with `docker compose up` — they must be run explicitly via `docker compose run --rm <name>`.

# 🇫🇷 Français

Fait tourner tout le pipeline (crawlers → ingestion → dbt → backend → frontend) sur n'importe quelle machine avec seulement **Docker Desktop** et **Git** — aucune installation locale de Python, Node.js ou `psql` n'est nécessaire. Chaque service tourne dans son propre conteneur.

## 1. Cloner et configurer

```bash
git clone https://github.com/minhld06/Football-Data-Platform.git
cd Football-Data-Platform
cp .env.example .env
```
Modifiez `.env` : renseignez `FOOTBALL_DATA_API_KEY` (clé gratuite sur [football-data.org](https://www.football-data.org)) et choisissez les identifiants Postgres/pgAdmin/MinIO.

## 2. Démarrer Postgres

```bash
docker compose up -d postgres
```

## 3. Appliquer les migrations de la base de données

Aucun `psql` local requis — cela transmet chaque fichier SQL à `psql` exécuté dans le conteneur `postgres` :
```bash
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/001_bronze_raw_documents.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/002_silver_gold_schemas.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/003_bronze_ingested_files.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/004_enable_unaccent_extension.sql
```

## 4. Collecter les données brutes

`data/raw/` est ignoré par Git, donc un clone récent démarre vide — il faut lancer les crawlers (ou copier un dossier `data/raw/` existant depuis une autre machine) :
```bash
docker compose run --rm crawlers python crawlers/football_data_org/client.py
docker compose run --rm crawlers python crawlers/statbunker/scraper.py
docker compose run --rm crawlers python crawlers/understat/scraper.py
```

## 5. Ingérer dans Bronze

```bash
docker compose run --rm ingestion
```
Idempotent — peut être relancé à tout moment sans créer de doublons.

## 6. Construire Silver → Gold avec dbt

```bash
docker compose build dbt
docker compose run --rm dbt build
```
Ou individuellement : `docker compose run --rm dbt run` / `test` / `snapshot`.

## 7. Démarrer le backend et le frontend

```bash
docker compose up -d backend frontend
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend (Swagger) | http://localhost:8000/docs |
| pgAdmin | http://localhost:5050 |
| Console MinIO | http://localhost:9001 |

## Après une modification du code

Les Dockerfiles font un `COPY` du code source au moment du build — il faut reconstruire l'image avant de relancer, sinon le conteneur utilisera l'ancien code :
```bash
docker compose build backend frontend
docker compose up -d backend frontend
```

## Arrêt / nettoyage

```bash
docker compose down       # arrête les conteneurs, conserve les données (volumes pgdata/minio_data)
docker system prune -f    # libère l'espace des images/cache inutilisés, sans toucher aux volumes
```

# 🇻🇳 Tiếng Việt

Chạy toàn bộ pipeline (crawlers → ingestion → dbt → backend → frontend) trên bất kỳ máy nào chỉ với **Docker Desktop** và **Git** — không cần cài Python, Node.js, hay `psql` cục bộ. Mỗi service chạy trong container riêng.

## 1. Clone và cấu hình

```bash
git clone https://github.com/minhld06/Football-Data-Platform.git
cd Football-Data-Platform
cp .env.example .env
```
Mở `.env`, điền `FOOTBALL_DATA_API_KEY` (đăng ký free tại [football-data.org](https://www.football-data.org)) và đặt thông tin đăng nhập Postgres/pgAdmin/MinIO.

## 2. Bật Postgres

```bash
docker compose up -d postgres
```

## 3. Tạo schema (migration) — không cần cài `psql`

```bash
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/001_bronze_raw_documents.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/002_silver_gold_schemas.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/003_bronze_ingested_files.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/004_enable_unaccent_extension.sql
```

## 4. Thu thập dữ liệu thô

`data/raw/` bị `.gitignore`, nên máy mới clone về sẽ không có sẵn dữ liệu — phải crawl (hoặc copy thư mục `data/raw/` có sẵn từ máy khác):
```bash
docker compose run --rm crawlers python crawlers/football_data_org/client.py
docker compose run --rm crawlers python crawlers/statbunker/scraper.py
docker compose run --rm crawlers python crawlers/understat/scraper.py
```

## 5. Nạp vào Bronze

```bash
docker compose run --rm ingestion
```
Idempotent — chạy lại bao nhiêu lần cũng không tạo dữ liệu trùng.

## 6. Build Silver → Gold bằng dbt

```bash
docker compose build dbt
docker compose run --rm dbt build
```
Hoặc chạy riêng lẻ: `docker compose run --rm dbt run` / `test` / `snapshot`.

## 7. Bật backend và frontend

```bash
docker compose up -d backend frontend
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend (Swagger) | http://localhost:8000/docs |
| pgAdmin | http://localhost:5050 |
| MinIO console | http://localhost:9001 |

## Sau khi sửa code

Dockerfile `COPY` code vào image lúc build — sửa code xong phải rebuild trước khi chạy lại, nếu không container vẫn dùng code cũ:
```bash
docker compose build backend frontend
docker compose up -d backend frontend
```

## Tắt / dọn dẹp

```bash
docker compose down       # tắt container, giữ nguyên dữ liệu (volume pgdata/minio_data)
docker system prune -f    # dọn image/cache thừa, an toàn, không đụng volume
```
