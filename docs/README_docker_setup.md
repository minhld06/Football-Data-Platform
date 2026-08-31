# Docker Setup — Football Data Platform

# English

Runs the whole pipeline (crawlers → ingestion → dbt → backend → frontend) on any machine with just **Docker Desktop** and **Git** — no local Python, Node.js, or `psql` install needed. Every service runs in its own container.

## 1. Clone and configure

```bash
git clone https://github.com/minhld06/Football-Data-Platform.git
cd Football-Data-Platform
cp .env.example .env
cp frontend/.env.local.example frontend/.env.local
```
Edit `.env`:
- `FOOTBALL_DATA_API_KEY` — free key from [football-data.org](https://www.football-data.org) (needed by the crawlers).
- `OPENROUTER_API_KEY` — key from [openrouter.ai](https://openrouter.ai) (needed for the chatbot to answer; the rest of the app works without it).
- `POSTGRES_*`, `PGADMIN_*`, `MINIO_*` — pick your own credentials.
- `CHATBOT_DB_PASSWORD` — password for the chatbot's read-only DB role, used in step 3.

`frontend/.env.local`'s defaults already match the Docker network, so this step is mostly a safety net — but Next.js bakes `NEXT_PUBLIC_API_URL` into the browser bundle at build time, so the file must exist *before* you build the frontend image.

## 2. Start Postgres

```bash
docker compose up -d postgres
```

> **About `manage.ps1`:** this PowerShell wrapper (project root) runs `docker compose up -d` / `down` / `restart` / `status` / `logs` / `build` for the always-on services (postgres, pgadmin, minio, backend, frontend) — see `.\manage.ps1 -?`. On a first-time setup it's not a shortcut for *this* step, since `.\manage.ps1 start` brings up backend/frontend too, before migrations/data exist; it's most useful for step 7 onward and for daily start/stop. It never touches `crawlers`/`ingestion`/`dbt` — those stay one-shot `docker compose run --rm <name>` commands, with or without `manage.ps1`.

## 3. Apply database migrations

No local `psql` required — this pipes each SQL file into `psql` running inside the `postgres` container.

**macOS / Linux / Git Bash / WSL:**
```bash
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/001_bronze_raw_documents.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/002_silver_gold_schemas.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/003_bronze_ingested_files.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/004_enable_unaccent_extension.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/005_enable_pg_trgm_extension.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/006_chatbot_chat_logs.sql
docker compose exec -T postgres psql -U postgres -d football -v chatbot_pw="YOUR_CHATBOT_DB_PASSWORD" < infra/postgres/migrations/007_chatbot_readonly_role.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/008_chatbot_statement_timeout.sql
```

**Windows PowerShell** (PowerShell doesn't support `<` for input redirection, so use `Get-Content | ...` instead):
```powershell
Get-Content infra/postgres/migrations/001_bronze_raw_documents.sql | docker compose exec -T postgres psql -U postgres -d football
Get-Content infra/postgres/migrations/002_silver_gold_schemas.sql | docker compose exec -T postgres psql -U postgres -d football
Get-Content infra/postgres/migrations/003_bronze_ingested_files.sql | docker compose exec -T postgres psql -U postgres -d football
Get-Content infra/postgres/migrations/004_enable_unaccent_extension.sql | docker compose exec -T postgres psql -U postgres -d football
Get-Content infra/postgres/migrations/005_enable_pg_trgm_extension.sql | docker compose exec -T postgres psql -U postgres -d football
Get-Content infra/postgres/migrations/006_chatbot_chat_logs.sql | docker compose exec -T postgres psql -U postgres -d football
Get-Content infra/postgres/migrations/007_chatbot_readonly_role.sql | docker compose exec -T postgres psql -U postgres -d football -v chatbot_pw="YOUR_CHATBOT_DB_PASSWORD"
Get-Content infra/postgres/migrations/008_chatbot_statement_timeout.sql | docker compose exec -T postgres psql -U postgres -d football
```

For migration 007, replace `YOUR_CHATBOT_DB_PASSWORD` with the value you set for `CHATBOT_DB_PASSWORD` in `.env` — it creates the `chatbot_ro` role the backend uses to run LLM-generated SQL. Migrations 006–008 are only needed for the chatbot; skip them if you don't plan to use it (the rest of the app doesn't depend on them).

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
docker compose build backend frontend
docker compose up -d backend frontend
```
From here on, `.\manage.ps1 start` (= `docker compose up -d` for postgres/pgadmin/minio/backend/frontend) and `.\manage.ps1 status` / `logs` are a convenient daily-use alternative to typing raw `docker compose` commands.

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
`.\manage.ps1 build [service]` works the same way — but **`.\manage.ps1 restart` does NOT pick up the freshly built image**, it only restarts the existing container from whatever image it's currently on. After `.\manage.ps1 build`, use `docker compose up -d [service]` (not `restart`) to actually swap in the new image.

## Stop / clean up

```bash
docker compose down       # stops containers, keeps data (pgdata/minio_data volumes)
docker system prune -f    # reclaims unused image/build-cache space, does not touch volumes
```
`.\manage.ps1 stop` is equivalent to `docker compose down` (whole stack, data volumes kept).

## First-run summary

```bash
docker compose up -d postgres
# apply the 8 migrations from step 3 (skip 006-008 if you're not using the chatbot)
docker compose run --rm crawlers python crawlers/football_data_org/client.py
docker compose run --rm crawlers python crawlers/statbunker/scraper.py
docker compose run --rm crawlers python crawlers/understat/scraper.py
docker compose run --rm ingestion
docker compose build dbt
docker compose run --rm dbt build
docker compose build backend frontend
docker compose up -d backend frontend
```

`crawlers`, `ingestion`, and `dbt` use `profiles: [tools]`, so they never auto-start with `docker compose up` — they must be run explicitly via `docker compose run --rm <name>`.

# Français

Fait tourner tout le pipeline (crawlers → ingestion → dbt → backend → frontend) sur n'importe quelle machine avec seulement **Docker Desktop** et **Git** — aucune installation locale de Python, Node.js ou `psql` n'est nécessaire. Chaque service tourne dans son propre conteneur.

## 1. Cloner et configurer

```bash
git clone https://github.com/minhld06/Football-Data-Platform.git
cd Football-Data-Platform
cp .env.example .env
cp frontend/.env.local.example frontend/.env.local
```
Modifiez `.env` :
- `FOOTBALL_DATA_API_KEY` — clé gratuite sur [football-data.org](https://www.football-data.org) (nécessaire pour les crawlers).
- `OPENROUTER_API_KEY` — clé sur [openrouter.ai](https://openrouter.ai) (nécessaire pour que le chatbot réponde ; le reste de l'app fonctionne sans).
- `POSTGRES_*`, `PGADMIN_*`, `MINIO_*` — choisissez vos propres identifiants.
- `CHATBOT_DB_PASSWORD` — mot de passe du rôle DB en lecture seule du chatbot, utilisé à l'étape 3.

Les valeurs par défaut de `frontend/.env.local` correspondent déjà au réseau Docker, donc cette étape est surtout une sécurité — mais Next.js intègre `NEXT_PUBLIC_API_URL` dans le bundle du navigateur au moment du build, donc le fichier doit exister *avant* de construire l'image du frontend.

## 2. Démarrer Postgres

```bash
docker compose up -d postgres
```

> **À propos de `manage.ps1` :** ce wrapper PowerShell (racine du projet) exécute `docker compose up -d` / `down` / `restart` / `status` / `logs` / `build` pour les services toujours actifs (postgres, pgadmin, minio, backend, frontend) — voir `.\manage.ps1 -?`. Lors d'une première installation, ce n'est pas un raccourci pour *cette* étape, car `.\manage.ps1 start` démarre aussi backend/frontend avant que les migrations/données existent ; il est surtout utile à partir de l'étape 7 et pour l'usage quotidien. Il ne touche jamais à `crawlers`/`ingestion`/`dbt` — ceux-ci restent des commandes `docker compose run --rm <name>` ponctuelles, avec ou sans `manage.ps1`.

## 3. Appliquer les migrations de la base de données

Aucun `psql` local requis — cela transmet chaque fichier SQL à `psql` exécuté dans le conteneur `postgres`.

**macOS / Linux / Git Bash / WSL :**
```bash
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/001_bronze_raw_documents.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/002_silver_gold_schemas.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/003_bronze_ingested_files.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/004_enable_unaccent_extension.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/005_enable_pg_trgm_extension.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/006_chatbot_chat_logs.sql
docker compose exec -T postgres psql -U postgres -d football -v chatbot_pw="YOUR_CHATBOT_DB_PASSWORD" < infra/postgres/migrations/007_chatbot_readonly_role.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/008_chatbot_statement_timeout.sql
```

**Windows PowerShell** (PowerShell ne supporte pas `<` pour la redirection d'entrée, utilisez `Get-Content | ...`) :
```powershell
Get-Content infra/postgres/migrations/001_bronze_raw_documents.sql | docker compose exec -T postgres psql -U postgres -d football
Get-Content infra/postgres/migrations/002_silver_gold_schemas.sql | docker compose exec -T postgres psql -U postgres -d football
Get-Content infra/postgres/migrations/003_bronze_ingested_files.sql | docker compose exec -T postgres psql -U postgres -d football
Get-Content infra/postgres/migrations/004_enable_unaccent_extension.sql | docker compose exec -T postgres psql -U postgres -d football
Get-Content infra/postgres/migrations/005_enable_pg_trgm_extension.sql | docker compose exec -T postgres psql -U postgres -d football
Get-Content infra/postgres/migrations/006_chatbot_chat_logs.sql | docker compose exec -T postgres psql -U postgres -d football
Get-Content infra/postgres/migrations/007_chatbot_readonly_role.sql | docker compose exec -T postgres psql -U postgres -d football -v chatbot_pw="YOUR_CHATBOT_DB_PASSWORD"
Get-Content infra/postgres/migrations/008_chatbot_statement_timeout.sql | docker compose exec -T postgres psql -U postgres -d football
```

Pour la migration 007, remplacez `YOUR_CHATBOT_DB_PASSWORD` par la valeur définie pour `CHATBOT_DB_PASSWORD` dans `.env` — elle crée le rôle `chatbot_ro` utilisé par le backend pour exécuter le SQL généré par le LLM. Les migrations 006–008 ne servent qu'au chatbot ; ignorez-les si vous ne comptez pas l'utiliser (le reste de l'app n'en dépend pas).

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
docker compose build backend frontend
docker compose up -d backend frontend
```
À partir d'ici, `.\manage.ps1 start` (= `docker compose up -d` pour postgres/pgadmin/minio/backend/frontend) et `.\manage.ps1 status` / `logs` sont une alternative pratique pour l'usage quotidien, plutôt que de taper les commandes `docker compose` brutes.

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
`.\manage.ps1 build [service]` fonctionne pareil — mais **`.\manage.ps1 restart` ne prend PAS en compte l'image nouvellement construite**, il redémarre seulement le conteneur existant avec l'image actuelle. Après `.\manage.ps1 build`, utilisez `docker compose up -d [service]` (pas `restart`) pour basculer réellement sur la nouvelle image.

## Arrêt / nettoyage

```bash
docker compose down       # arrête les conteneurs, conserve les données (volumes pgdata/minio_data)
docker system prune -f    # libère l'espace des images/cache inutilisés, sans toucher aux volumes
```
`.\manage.ps1 stop` équivaut à `docker compose down` (tout le stack, volumes de données conservés).

## Résumé du premier lancement

```bash
docker compose up -d postgres
# appliquez les 8 migrations de l'étape 3 (ignorez 006-008 si vous n'utilisez pas le chatbot)
docker compose run --rm crawlers python crawlers/football_data_org/client.py
docker compose run --rm crawlers python crawlers/statbunker/scraper.py
docker compose run --rm crawlers python crawlers/understat/scraper.py
docker compose run --rm ingestion
docker compose build dbt
docker compose run --rm dbt build
docker compose build backend frontend
docker compose up -d backend frontend
```

# Tiếng Việt

Chạy toàn bộ pipeline (crawlers → ingestion → dbt → backend → frontend) trên bất kỳ máy nào chỉ với **Docker Desktop** và **Git** — không cần cài Python, Node.js, hay `psql` cục bộ. Mỗi service chạy trong container riêng.

## 1. Clone và cấu hình

```bash
git clone https://github.com/minhld06/Football-Data-Platform.git
cd Football-Data-Platform
cp .env.example .env
cp frontend/.env.local.example frontend/.env.local
```
Mở `.env` và điền:
- `FOOTBALL_DATA_API_KEY` — đăng ký free tại [football-data.org](https://www.football-data.org) (crawlers cần).
- `OPENROUTER_API_KEY` — lấy tại [openrouter.ai](https://openrouter.ai) (cần để chatbot trả lời được; các phần còn lại của app không phụ thuộc vào key này).
- `POSTGRES_*`, `PGADMIN_*`, `MINIO_*` — tự đặt thông tin đăng nhập.
- `CHATBOT_DB_PASSWORD` — mật khẩu cho role DB chỉ-đọc của chatbot, dùng ở bước 3.

`frontend/.env.local` mặc định đã khớp với network của Docker rồi nên bước này chủ yếu để phòng hờ — nhưng Next.js sẽ nhúng cứng `NEXT_PUBLIC_API_URL` vào bundle chạy trên trình duyệt ngay lúc build, nên file này phải tồn tại *trước khi* build image frontend.

## 2. Bật Postgres

```bash
docker compose up -d postgres
```

> **Về `manage.ps1`:** file PowerShell này (ở gốc repo) wrap sẵn `docker compose up -d` / `down` / `restart` / `status` / `logs` / `build` cho các service luôn chạy (postgres, pgadmin, minio, backend, frontend) — xem `.\manage.ps1 -?`. Ở lần setup đầu tiên, nó **không** thay được bước này, vì `.\manage.ps1 start` sẽ bật luôn cả backend/frontend trước khi có migration/dữ liệu — nên để dành nó cho bước 7 trở đi và cho việc bật/tắt hàng ngày. Nó không đụng tới `crawlers`/`ingestion`/`dbt` — các service này luôn phải chạy bằng `docker compose run --rm <tên>`, dù có hay không có `manage.ps1`.

## 3. Tạo schema (migration) — không cần cài `psql`

Lệnh dưới đây pipe từng file SQL vào `psql` chạy bên trong container `postgres`.

**macOS / Linux / Git Bash / WSL:**
```bash
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/001_bronze_raw_documents.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/002_silver_gold_schemas.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/003_bronze_ingested_files.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/004_enable_unaccent_extension.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/005_enable_pg_trgm_extension.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/006_chatbot_chat_logs.sql
docker compose exec -T postgres psql -U postgres -d football -v chatbot_pw="YOUR_CHATBOT_DB_PASSWORD" < infra/postgres/migrations/007_chatbot_readonly_role.sql
docker compose exec -T postgres psql -U postgres -d football < infra/postgres/migrations/008_chatbot_statement_timeout.sql
```

**Windows PowerShell** (PowerShell không hỗ trợ `<` để redirect input từ file, dùng `Get-Content | ...` thay thế):
```powershell
Get-Content infra/postgres/migrations/001_bronze_raw_documents.sql | docker compose exec -T postgres psql -U postgres -d football
Get-Content infra/postgres/migrations/002_silver_gold_schemas.sql | docker compose exec -T postgres psql -U postgres -d football
Get-Content infra/postgres/migrations/003_bronze_ingested_files.sql | docker compose exec -T postgres psql -U postgres -d football
Get-Content infra/postgres/migrations/004_enable_unaccent_extension.sql | docker compose exec -T postgres psql -U postgres -d football
Get-Content infra/postgres/migrations/005_enable_pg_trgm_extension.sql | docker compose exec -T postgres psql -U postgres -d football
Get-Content infra/postgres/migrations/006_chatbot_chat_logs.sql | docker compose exec -T postgres psql -U postgres -d football
Get-Content infra/postgres/migrations/007_chatbot_readonly_role.sql | docker compose exec -T postgres psql -U postgres -d football -v chatbot_pw="YOUR_CHATBOT_DB_PASSWORD"
Get-Content infra/postgres/migrations/008_chatbot_statement_timeout.sql | docker compose exec -T postgres psql -U postgres -d football
```

Ở migration 007, thay `YOUR_CHATBOT_DB_PASSWORD` bằng giá trị bạn đặt cho `CHATBOT_DB_PASSWORD` trong `.env` — migration này tạo role `chatbot_ro` mà backend dùng để chạy SQL do LLM sinh ra. Migration 006–008 chỉ phục vụ chatbot; có thể bỏ qua nếu bạn chưa cần dùng tính năng này (phần còn lại của app không phụ thuộc vào chúng).

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
docker compose build backend frontend
docker compose up -d backend frontend
```
Từ đây trở đi, `.\manage.ps1 start` (tương đương `docker compose up -d` cho postgres/pgadmin/minio/backend/frontend) và `.\manage.ps1 status` / `logs` là cách gọn hơn để dùng hàng ngày, thay vì gõ trực tiếp `docker compose`.

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
`.\manage.ps1 build [service]` làm y hệt vậy — nhưng **`.\manage.ps1 restart` KHÔNG load image vừa build**, nó chỉ khởi động lại container hiện có với image đang chạy. Sau `.\manage.ps1 build`, phải dùng `docker compose up -d [service]` (không phải `restart`) để thực sự chuyển sang image mới.

## Tắt / dọn dẹp

```bash
docker compose down       # tắt container, giữ nguyên dữ liệu (volume pgdata/minio_data)
docker system prune -f    # dọn image/cache thừa, an toàn, không đụng volume
```
`.\manage.ps1 stop` tương đương `docker compose down` (tắt cả stack, vẫn giữ volume dữ liệu).

## Tóm tắt lần chạy đầu tiên

```bash
docker compose up -d postgres
# áp dụng 8 migration ở bước 3 (bỏ qua 006-008 nếu chưa dùng chatbot)
docker compose run --rm crawlers python crawlers/football_data_org/client.py
docker compose run --rm crawlers python crawlers/statbunker/scraper.py
docker compose run --rm crawlers python crawlers/understat/scraper.py
docker compose run --rm ingestion
docker compose build dbt
docker compose run --rm dbt build
docker compose build backend frontend
docker compose up -d backend frontend
```
