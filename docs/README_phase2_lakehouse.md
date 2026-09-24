# Phase 2 Lakehouse Setup - Football Data Platform

# English

Stands up the Phase 2 Lakehouse stack (MinIO, Iceberg REST Catalog, Spark master/worker, ClickHouse, JupyterLab) and migrates the Bronze table `bronze.raw_documents` from Postgres into an Iceberg table on MinIO. Phase 1 (Postgres, dbt, backend, frontend) is not modified - Postgres stays the source of truth and the Iceberg table is a copy.

**Prerequisites**
- Docker Desktop and Git.
- Python 3.11+ on the host (only for the bootstrap script in step 4).
- Phase 1 done up to Bronze: follow steps 1-5 of [`README_docker_setup.md`](README_docker_setup.md) so that `bronze.raw_documents` exists and has rows. The migration job reads it.
- Several GB of free disk: the Spark JARs alone are about 390 MB, plus the Spark, ClickHouse and Jupyter images.

## 1. Configure `.env`

Besides the Phase 1 variables, these must be set in `.env` (see `.env.example`):
- `POSTGRES_USER`, `POSTGRES_PASSWORD` - read by the migration job and the bootstrap script.
- `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` - MinIO login, also used by Iceberg and Spark to write files.
- `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD` - ClickHouse login (the bootstrap script creates a database with them).

## 2. Download the Spark JARs

The JARs are gitignored (`infra/spark/jars/*.jar`), so a fresh clone must download them once. The versions are pinned because Spark, Iceberg, Hadoop and the AWS SDK must be compatible with each other.

| JAR | Why it is needed |
|---|---|
| `iceberg-spark-runtime-3.5_2.12-1.11.0` | Iceberg support inside Spark 3.5 (Scala 2.12) |
| `iceberg-aws-bundle-1.11.0` | Iceberg's S3 file access (`S3FileIO`) used to write to MinIO |
| `hadoop-aws-3.3.4`, `aws-java-sdk-bundle-1.12.262` | Hadoop `s3a://` support, kept for the later ClickHouse/dbt-spark work |
| `postgresql-42.7.13` | JDBC driver so Spark can read Postgres |

**Windows PowerShell:**
```powershell
$jarDir = "infra/spark/jars"
New-Item -ItemType Directory -Force $jarDir | Out-Null
$base = "https://repo1.maven.org/maven2"
$jars = @(
  "org/apache/iceberg/iceberg-spark-runtime-3.5_2.12/1.11.0/iceberg-spark-runtime-3.5_2.12-1.11.0.jar",
  "org/apache/iceberg/iceberg-aws-bundle/1.11.0/iceberg-aws-bundle-1.11.0.jar",
  "org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar",
  "com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar",
  "org/postgresql/postgresql/42.7.13/postgresql-42.7.13.jar"
)
foreach ($j in $jars) { Invoke-WebRequest -Uri "$base/$j" -OutFile "$jarDir/$($j.Split('/')[-1])" }
```

**macOS / Linux / Git Bash / WSL:**
```bash
mkdir -p infra/spark/jars
for j in \
  org/apache/iceberg/iceberg-spark-runtime-3.5_2.12/1.11.0/iceberg-spark-runtime-3.5_2.12-1.11.0.jar \
  org/apache/iceberg/iceberg-aws-bundle/1.11.0/iceberg-aws-bundle-1.11.0.jar \
  org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar \
  com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar \
  org/postgresql/postgresql/42.7.13/postgresql-42.7.13.jar
do curl -fL -o "infra/spark/jars/${j##*/}" "https://repo1.maven.org/maven2/$j"; done
```

## 3. Start the Lakehouse stack

```bash
docker compose --profile lakehouse up -d
docker compose --profile lakehouse ps
```
The `lakehouse` profile adds `iceberg-rest`, `spark-master`, `spark-worker`, `clickhouse` and `jupyter` next to the Phase 1 services; it never starts with a bare `docker compose up` or `.\manage.ps1 start`.

On a brand-new machine, Postgres creates the `iceberg_catalog` database by itself the first time it initializes its volume (`infra/postgres/init/01_iceberg_catalog.sql`). `iceberg-rest` needs that database to start.

Wait until the catalog answers before continuing (a few seconds after `up`):
```bash
curl http://localhost:8181/v1/config
```
```powershell
Invoke-RestMethod http://localhost:8181/v1/config
```
A JSON response means it is ready.

## 4. Run the bootstrap script

Creates, idempotently, everything a Spark job needs before it can write: the MinIO bucket `lakehouse`, the Iceberg namespace `bronze`, the ClickHouse database `gold` (and the Postgres database `iceberg_catalog` if it is somehow missing). Run it from the project root; it reads `.env` itself and talks to the services on `localhost`.

**Windows PowerShell:**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r infra/bootstrap/requirements.txt
python infra/bootstrap/bootstrap_lakehouse.py
```

**macOS / Linux / WSL:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r infra/bootstrap/requirements.txt
python infra/bootstrap/bootstrap_lakehouse.py
```
Each step logs `Created ...` or `... already exists`, so re-running is safe. A config or connection error stops the script immediately.

## 5. Migrate Bronze to Iceberg

`infra/spark/jobs/migrate_bronze_to_iceberg.py` reads `bronze.raw_documents` from Postgres over JDBC and writes it to the Iceberg table `lakehouse.bronze.raw_documents` on MinIO, then compares the row counts and fails if they differ. It runs inside the `spark-master` container.

**Windows PowerShell:**
```powershell
$jars = "/opt/spark/extra-jars/iceberg-spark-runtime-3.5_2.12-1.11.0.jar,/opt/spark/extra-jars/iceberg-aws-bundle-1.11.0.jar,/opt/spark/extra-jars/hadoop-aws-3.3.4.jar,/opt/spark/extra-jars/aws-java-sdk-bundle-1.12.262.jar,/opt/spark/extra-jars/postgresql-42.7.13.jar"
docker compose exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 --jars $jars /opt/spark/jobs/migrate_bronze_to_iceberg.py
```

**macOS / Linux / WSL** (on Git Bash for Windows, prefix the command with `MSYS_NO_PATHCONV=1`, otherwise Git Bash rewrites the `/opt/...` paths):
```bash
J=/opt/spark/extra-jars
JARS="$J/iceberg-spark-runtime-3.5_2.12-1.11.0.jar,$J/iceberg-aws-bundle-1.11.0.jar,$J/hadoop-aws-3.3.4.jar,$J/aws-java-sdk-bundle-1.12.262.jar,$J/postgresql-42.7.13.jar"
docker compose exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 --jars "$JARS" /opt/spark/jobs/migrate_bronze_to_iceberg.py
```
Success looks like `Postgres rows: N, Iceberg rows: N` near the end of the output and exit code 0. The job uses `createOrReplace()`, so re-running is safe: the table is replaced, not appended to, and each run adds an Iceberg snapshot.

## 6. Verify

`infra/spark/jobs/verify_bronze_iceberg.py` runs four Spark SQL checks on the new table: rows per `source`/`entity_type`, the `.snapshots` metadata table, the `.files` metadata table, and time travel (`VERSION AS OF` the oldest snapshot). Use the same command as step 5 with `/opt/spark/jobs/verify_bronze_iceberg.py` as the last argument.

Then check the files by eye: open the MinIO console (http://localhost:9001), log in with `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`, and browse `lakehouse/warehouse/bronze/raw_documents/`. `data/` holds the `.parquet` files and `metadata/` holds the `.metadata.json`, manifest (`.avro`) and snapshot (`snap-*.avro`) files. After a re-run `data/` can contain more files than the `.files` query lists: older snapshots still reference the old files (that is what makes time travel possible).

| Service | URL |
|---|---|
| Spark master UI | http://localhost:8080 |
| Spark worker UI | http://localhost:8081 |
| MinIO console | http://localhost:9001 |
| Iceberg REST Catalog | http://localhost:8181/v1/config |
| ClickHouse HTTP | http://localhost:8123/ping |
| JupyterLab | http://localhost:8888 (the login token is printed in `docker compose logs jupyter`) |

## Stop / clean up

Stop only the Lakehouse services and leave Phase 1 running:
```bash
docker compose stop iceberg-rest spark-master spark-worker clickhouse jupyter
```
Do **not** use `docker compose --profile lakehouse down` for this: `down` removes the whole project, including postgres, backend and frontend. Data volumes (`pgdata`, `minio_data`) are kept by both commands.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `UnknownHostException: iceberg-rest` (or `postgres`, `minio`) | Those containers are not running. `docker compose up -d spark-master` starts only that one service. Run `docker compose --profile lakehouse up -d`. |
| `iceberg-rest` shows `Exited (1)`; logs say `database "iceberg_catalog" does not exist` | The Postgres volume was created before the init script existed, so it never ran. Create it once: `docker compose exec -T postgres psql -U postgres -c "CREATE DATABASE iceberg_catalog"`, then `docker compose --profile lakehouse up -d iceberg-rest`. |
| `NoSuchBucket` | The bootstrap script has not run yet (step 4). |
| `Missing required environment variable` | A variable from step 1 is missing in `.env`; recreate `spark-master` with `docker compose --profile lakehouse up -d spark-master` after fixing it. |
| Job hangs with `Initial job has not accepted any resources` | Executors cannot reach the driver. Add `--conf spark.driver.host=spark-master` to the `spark-submit` command. |
| After Docker Desktop or the machine restarts, everything is stopped | Run `docker compose --profile lakehouse up -d` again; volumes keep the data. |

## First-run summary

```bash
# Phase 1 through Bronze (README_docker_setup.md steps 1-5), then:
# download the 5 JARs (step 2)
docker compose --profile lakehouse up -d
curl http://localhost:8181/v1/config
python infra/bootstrap/bootstrap_lakehouse.py
# run migrate_bronze_to_iceberg.py, then verify_bronze_iceberg.py (steps 5-6)
```

# Français

Met en place la pile Lakehouse de la Phase 2 (MinIO, Iceberg REST Catalog, Spark master/worker, ClickHouse, JupyterLab) et migre la table Bronze `bronze.raw_documents` de Postgres vers une table Iceberg sur MinIO. La Phase 1 (Postgres, dbt, backend, frontend) n'est pas modifiée : Postgres reste la source de vérité et la table Iceberg n'en est qu'une copie.

**Prérequis**
- Docker Desktop et Git.
- Python 3.11+ sur la machine hôte (uniquement pour le script de bootstrap de l'étape 4).
- Phase 1 terminée jusqu'à Bronze : suivez les étapes 1 à 5 de [`README_docker_setup.md`](README_docker_setup.md) pour que `bronze.raw_documents` existe et contienne des lignes. Le job de migration la lit.
- Plusieurs Go d'espace disque libre : les JAR Spark représentent à eux seuls environ 390 Mo, auxquels s'ajoutent les images Spark, ClickHouse et Jupyter.

## 1. Configurer `.env`

En plus des variables de la Phase 1, ces variables doivent être définies dans `.env` (voir `.env.example`) :
- `POSTGRES_USER`, `POSTGRES_PASSWORD` - lues par le job de migration et par le script de bootstrap.
- `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` - identifiants MinIO, également utilisés par Iceberg et Spark pour écrire les fichiers.
- `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD` - identifiants ClickHouse (le script de bootstrap crée une base avec ces identifiants).

## 2. Télécharger les JAR Spark

Les JAR sont ignorés par Git (`infra/spark/jars/*.jar`) : un clone tout neuf doit les télécharger une fois. Les versions sont figées car Spark, Iceberg, Hadoop et le SDK AWS doivent être compatibles entre eux.

| JAR | Pourquoi il est nécessaire |
|---|---|
| `iceberg-spark-runtime-3.5_2.12-1.11.0` | Support d'Iceberg dans Spark 3.5 (Scala 2.12) |
| `iceberg-aws-bundle-1.11.0` | Accès S3 d'Iceberg (`S3FileIO`) utilisé pour écrire dans MinIO |
| `hadoop-aws-3.3.4`, `aws-java-sdk-bundle-1.12.262` | Support Hadoop `s3a://`, conservé pour les travaux ultérieurs ClickHouse/dbt-spark |
| `postgresql-42.7.13` | Pilote JDBC permettant à Spark de lire Postgres |

**Windows PowerShell :**
```powershell
$jarDir = "infra/spark/jars"
New-Item -ItemType Directory -Force $jarDir | Out-Null
$base = "https://repo1.maven.org/maven2"
$jars = @(
  "org/apache/iceberg/iceberg-spark-runtime-3.5_2.12/1.11.0/iceberg-spark-runtime-3.5_2.12-1.11.0.jar",
  "org/apache/iceberg/iceberg-aws-bundle/1.11.0/iceberg-aws-bundle-1.11.0.jar",
  "org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar",
  "com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar",
  "org/postgresql/postgresql/42.7.13/postgresql-42.7.13.jar"
)
foreach ($j in $jars) { Invoke-WebRequest -Uri "$base/$j" -OutFile "$jarDir/$($j.Split('/')[-1])" }
```

**macOS / Linux / Git Bash / WSL :**
```bash
mkdir -p infra/spark/jars
for j in \
  org/apache/iceberg/iceberg-spark-runtime-3.5_2.12/1.11.0/iceberg-spark-runtime-3.5_2.12-1.11.0.jar \
  org/apache/iceberg/iceberg-aws-bundle/1.11.0/iceberg-aws-bundle-1.11.0.jar \
  org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar \
  com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar \
  org/postgresql/postgresql/42.7.13/postgresql-42.7.13.jar
do curl -fL -o "infra/spark/jars/${j##*/}" "https://repo1.maven.org/maven2/$j"; done
```

## 3. Démarrer la pile Lakehouse

```bash
docker compose --profile lakehouse up -d
docker compose --profile lakehouse ps
```
Le profil `lakehouse` ajoute `iceberg-rest`, `spark-master`, `spark-worker`, `clickhouse` et `jupyter` à côté des services de la Phase 1 ; il ne démarre jamais avec un simple `docker compose up` ni avec `.\manage.ps1 start`.

Sur une machine toute neuve, Postgres crée lui-même la base `iceberg_catalog` la première fois qu'il initialise son volume (`infra/postgres/init/01_iceberg_catalog.sql`). `iceberg-rest` a besoin de cette base pour démarrer.

Attendez que le catalogue réponde avant de continuer (quelques secondes après `up`) :
```bash
curl http://localhost:8181/v1/config
```
```powershell
Invoke-RestMethod http://localhost:8181/v1/config
```
Une réponse JSON signifie qu'il est prêt.

## 4. Exécuter le script de bootstrap

Crée, de façon idempotente, tout ce dont un job Spark a besoin avant de pouvoir écrire : le bucket MinIO `lakehouse`, le namespace Iceberg `bronze`, la base ClickHouse `gold` (et la base Postgres `iceberg_catalog` si elle venait à manquer). À lancer depuis la racine du projet ; il lit `.env` lui-même et contacte les services sur `localhost`.

**Windows PowerShell :**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r infra/bootstrap/requirements.txt
python infra/bootstrap/bootstrap_lakehouse.py
```

**macOS / Linux / WSL :**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r infra/bootstrap/requirements.txt
python infra/bootstrap/bootstrap_lakehouse.py
```
Chaque étape journalise `Created ...` ou `... already exists`, donc le relancer est sans risque. Une erreur de configuration ou de connexion arrête immédiatement le script.

## 5. Migrer Bronze vers Iceberg

`infra/spark/jobs/migrate_bronze_to_iceberg.py` lit `bronze.raw_documents` depuis Postgres via JDBC et l'écrit dans la table Iceberg `lakehouse.bronze.raw_documents` sur MinIO, puis compare les nombres de lignes et échoue s'ils diffèrent. Il s'exécute dans le conteneur `spark-master`.

**Windows PowerShell :**
```powershell
$jars = "/opt/spark/extra-jars/iceberg-spark-runtime-3.5_2.12-1.11.0.jar,/opt/spark/extra-jars/iceberg-aws-bundle-1.11.0.jar,/opt/spark/extra-jars/hadoop-aws-3.3.4.jar,/opt/spark/extra-jars/aws-java-sdk-bundle-1.12.262.jar,/opt/spark/extra-jars/postgresql-42.7.13.jar"
docker compose exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 --jars $jars /opt/spark/jobs/migrate_bronze_to_iceberg.py
```

**macOS / Linux / WSL** (sous Git Bash pour Windows, préfixez la commande par `MSYS_NO_PATHCONV=1`, sinon Git Bash réécrit les chemins `/opt/...`) :
```bash
J=/opt/spark/extra-jars
JARS="$J/iceberg-spark-runtime-3.5_2.12-1.11.0.jar,$J/iceberg-aws-bundle-1.11.0.jar,$J/hadoop-aws-3.3.4.jar,$J/aws-java-sdk-bundle-1.12.262.jar,$J/postgresql-42.7.13.jar"
docker compose exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 --jars "$JARS" /opt/spark/jobs/migrate_bronze_to_iceberg.py
```
Un succès se traduit par `Postgres rows: N, Iceberg rows: N` vers la fin de la sortie et un code de retour 0. Le job utilise `createOrReplace()`, donc le relancer est sans risque : la table est remplacée et non complétée, et chaque exécution ajoute un snapshot Iceberg.

## 6. Vérifier

`infra/spark/jobs/verify_bronze_iceberg.py` exécute quatre contrôles Spark SQL sur la nouvelle table : lignes par `source`/`entity_type`, la table de métadonnées `.snapshots`, la table de métadonnées `.files`, et le voyage dans le temps (`VERSION AS OF` le plus ancien snapshot). Utilisez la même commande qu'à l'étape 5 avec `/opt/spark/jobs/verify_bronze_iceberg.py` comme dernier argument.

Vérifiez ensuite les fichiers à l'oeil : ouvrez la console MinIO (http://localhost:9001), connectez-vous avec `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`, et parcourez `lakehouse/warehouse/bronze/raw_documents/`. `data/` contient les fichiers `.parquet` et `metadata/` contient les fichiers `.metadata.json`, manifestes (`.avro`) et snapshots (`snap-*.avro`). Après une nouvelle exécution, `data/` peut contenir plus de fichiers que la requête `.files` n'en liste : les anciens snapshots référencent encore les anciens fichiers (c'est ce qui rend le voyage dans le temps possible).

| Service | URL |
|---|---|
| Interface Spark master | http://localhost:8080 |
| Interface Spark worker | http://localhost:8081 |
| Console MinIO | http://localhost:9001 |
| Iceberg REST Catalog | http://localhost:8181/v1/config |
| ClickHouse HTTP | http://localhost:8123/ping |
| JupyterLab | http://localhost:8888 (le jeton de connexion s'affiche dans `docker compose logs jupyter`) |

## Arrêt / nettoyage

Arrêter uniquement les services Lakehouse et laisser la Phase 1 tourner :
```bash
docker compose stop iceberg-rest spark-master spark-worker clickhouse jupyter
```
N'utilisez **pas** `docker compose --profile lakehouse down` pour cela : `down` supprime tout le projet, y compris postgres, backend et frontend. Les volumes de données (`pgdata`, `minio_data`) sont conservés par les deux commandes.

## Dépannage

| Symptôme | Cause et solution |
|---|---|
| `UnknownHostException: iceberg-rest` (ou `postgres`, `minio`) | Ces conteneurs ne tournent pas. `docker compose up -d spark-master` ne démarre que ce service. Lancez `docker compose --profile lakehouse up -d`. |
| `iceberg-rest` affiche `Exited (1)` ; les logs indiquent `database "iceberg_catalog" does not exist` | Le volume Postgres a été créé avant l'existence du script d'initialisation, qui ne s'est donc jamais exécuté. Créez la base une fois : `docker compose exec -T postgres psql -U postgres -c "CREATE DATABASE iceberg_catalog"`, puis `docker compose --profile lakehouse up -d iceberg-rest`. |
| `NoSuchBucket` | Le script de bootstrap n'a pas encore été exécuté (étape 4). |
| `Missing required environment variable` | Une variable de l'étape 1 manque dans `.env` ; après correction, recréez `spark-master` avec `docker compose --profile lakehouse up -d spark-master`. |
| Le job reste bloqué sur `Initial job has not accepted any resources` | Les executors n'arrivent pas à joindre le driver. Ajoutez `--conf spark.driver.host=spark-master` à la commande `spark-submit`. |
| Après un redémarrage de Docker Desktop ou de la machine, tout est arrêté | Relancez `docker compose --profile lakehouse up -d` ; les volumes conservent les données. |

## Résumé du premier lancement

```bash
# Phase 1 jusqu'à Bronze (README_docker_setup.md étapes 1-5), puis :
# télécharger les 5 JAR (étape 2)
docker compose --profile lakehouse up -d
curl http://localhost:8181/v1/config
python infra/bootstrap/bootstrap_lakehouse.py
# exécuter migrate_bronze_to_iceberg.py, puis verify_bronze_iceberg.py (étapes 5-6)
```

# Tiếng Việt

Dựng stack Lakehouse của Phase 2 (MinIO, Iceberg REST Catalog, Spark master/worker, ClickHouse, JupyterLab) và migrate bảng Bronze `bronze.raw_documents` từ Postgres sang một bảng Iceberg trên MinIO. Phase 1 (Postgres, dbt, backend, frontend) không bị sửa: Postgres vẫn là nguồn dữ liệu gốc, bảng Iceberg chỉ là bản sao.

**Yêu cầu trước khi bắt đầu**
- Docker Desktop và Git.
- Python 3.11+ trên máy chủ (chỉ dùng cho script bootstrap ở bước 4).
- Phase 1 đã xong tới Bronze: làm theo bước 1-5 của [`README_docker_setup.md`](README_docker_setup.md) để `bronze.raw_documents` tồn tại và có dữ liệu. Job migration đọc bảng này.
- Trống vài GB ổ đĩa: riêng các JAR của Spark đã khoảng 390 MB, chưa kể image Spark, ClickHouse và Jupyter.

## 1. Cấu hình `.env`

Ngoài các biến của Phase 1, cần có các biến sau trong `.env` (xem `.env.example`):
- `POSTGRES_USER`, `POSTGRES_PASSWORD` - job migration và script bootstrap đọc.
- `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` - tài khoản MinIO, Iceberg và Spark cũng dùng để ghi file.
- `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD` - tài khoản ClickHouse (script bootstrap dùng để tạo database).

## 2. Tải các JAR của Spark

Các JAR bị gitignore (`infra/spark/jars/*.jar`) nên bản clone mới phải tải một lần. Version được ghim cố định vì Spark, Iceberg, Hadoop và AWS SDK phải tương thích với nhau.

| JAR | Vì sao cần |
|---|---|
| `iceberg-spark-runtime-3.5_2.12-1.11.0` | Hỗ trợ Iceberg trong Spark 3.5 (Scala 2.12) |
| `iceberg-aws-bundle-1.11.0` | Truy cập S3 của Iceberg (`S3FileIO`) để ghi lên MinIO |
| `hadoop-aws-3.3.4`, `aws-java-sdk-bundle-1.12.262` | Hỗ trợ `s3a://` của Hadoop, giữ lại cho phần ClickHouse/dbt-spark về sau |
| `postgresql-42.7.13` | JDBC driver để Spark đọc được Postgres |

**Windows PowerShell:**
```powershell
$jarDir = "infra/spark/jars"
New-Item -ItemType Directory -Force $jarDir | Out-Null
$base = "https://repo1.maven.org/maven2"
$jars = @(
  "org/apache/iceberg/iceberg-spark-runtime-3.5_2.12/1.11.0/iceberg-spark-runtime-3.5_2.12-1.11.0.jar",
  "org/apache/iceberg/iceberg-aws-bundle/1.11.0/iceberg-aws-bundle-1.11.0.jar",
  "org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar",
  "com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar",
  "org/postgresql/postgresql/42.7.13/postgresql-42.7.13.jar"
)
foreach ($j in $jars) { Invoke-WebRequest -Uri "$base/$j" -OutFile "$jarDir/$($j.Split('/')[-1])" }
```

**macOS / Linux / Git Bash / WSL:**
```bash
mkdir -p infra/spark/jars
for j in \
  org/apache/iceberg/iceberg-spark-runtime-3.5_2.12/1.11.0/iceberg-spark-runtime-3.5_2.12-1.11.0.jar \
  org/apache/iceberg/iceberg-aws-bundle/1.11.0/iceberg-aws-bundle-1.11.0.jar \
  org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar \
  com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar \
  org/postgresql/postgresql/42.7.13/postgresql-42.7.13.jar
do curl -fL -o "infra/spark/jars/${j##*/}" "https://repo1.maven.org/maven2/$j"; done
```

## 3. Bật stack Lakehouse

```bash
docker compose --profile lakehouse up -d
docker compose --profile lakehouse ps
```
Profile `lakehouse` thêm `iceberg-rest`, `spark-master`, `spark-worker`, `clickhouse` và `jupyter` bên cạnh các service của Phase 1; nó không bao giờ tự chạy khi gõ `docker compose up` trần hay `.\manage.ps1 start`.

Trên máy hoàn toàn mới, Postgres tự tạo database `iceberg_catalog` ngay lần đầu khởi tạo volume (`infra/postgres/init/01_iceberg_catalog.sql`). `iceberg-rest` cần database này để khởi động.

Đợi catalog trả lời rồi mới làm tiếp (vài giây sau `up`):
```bash
curl http://localhost:8181/v1/config
```
```powershell
Invoke-RestMethod http://localhost:8181/v1/config
```
Có JSON trả về nghĩa là đã sẵn sàng.

## 4. Chạy script bootstrap

Tạo (idempotent) mọi thứ mà một Spark job cần có trước khi ghi được: bucket MinIO `lakehouse`, namespace Iceberg `bronze`, database ClickHouse `gold` (và database Postgres `iceberg_catalog` nếu chẳng may thiếu). Chạy từ thư mục gốc dự án; script tự đọc `.env` và gọi các service qua `localhost`.

**Windows PowerShell:**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r infra/bootstrap/requirements.txt
python infra/bootstrap/bootstrap_lakehouse.py
```

**macOS / Linux / WSL:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r infra/bootstrap/requirements.txt
python infra/bootstrap/bootstrap_lakehouse.py
```
Mỗi bước ghi log `Created ...` hoặc `... already exists`, nên chạy lại an toàn. Lỗi cấu hình hoặc lỗi kết nối sẽ dừng script ngay lập tức.

## 5. Migrate Bronze sang Iceberg

`infra/spark/jobs/migrate_bronze_to_iceberg.py` đọc `bronze.raw_documents` từ Postgres qua JDBC, ghi vào bảng Iceberg `lakehouse.bronze.raw_documents` trên MinIO, rồi so sánh số dòng hai phía và báo lỗi nếu lệch. Job chạy bên trong container `spark-master`.

**Windows PowerShell:**
```powershell
$jars = "/opt/spark/extra-jars/iceberg-spark-runtime-3.5_2.12-1.11.0.jar,/opt/spark/extra-jars/iceberg-aws-bundle-1.11.0.jar,/opt/spark/extra-jars/hadoop-aws-3.3.4.jar,/opt/spark/extra-jars/aws-java-sdk-bundle-1.12.262.jar,/opt/spark/extra-jars/postgresql-42.7.13.jar"
docker compose exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 --jars $jars /opt/spark/jobs/migrate_bronze_to_iceberg.py
```

**macOS / Linux / WSL** (trên Git Bash của Windows, thêm `MSYS_NO_PATHCONV=1` trước lệnh, nếu không Git Bash sẽ viết lại các đường dẫn `/opt/...`):
```bash
J=/opt/spark/extra-jars
JARS="$J/iceberg-spark-runtime-3.5_2.12-1.11.0.jar,$J/iceberg-aws-bundle-1.11.0.jar,$J/hadoop-aws-3.3.4.jar,$J/aws-java-sdk-bundle-1.12.262.jar,$J/postgresql-42.7.13.jar"
docker compose exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 --jars "$JARS" /opt/spark/jobs/migrate_bronze_to_iceberg.py
```
Thành công là thấy dòng `Postgres rows: N, Iceberg rows: N` gần cuối output và mã thoát 0. Job dùng `createOrReplace()` nên chạy lại an toàn: bảng bị thay thế chứ không bị cộng dồn, và mỗi lần chạy thêm một snapshot Iceberg.

## 6. Kiểm chứng

`infra/spark/jobs/verify_bronze_iceberg.py` chạy 4 truy vấn Spark SQL trên bảng mới: đếm dòng theo `source`/`entity_type`, bảng metadata `.snapshots`, bảng metadata `.files`, và time travel (`VERSION AS OF` snapshot cũ nhất). Dùng đúng lệnh ở bước 5, chỉ đổi tham số cuối thành `/opt/spark/jobs/verify_bronze_iceberg.py`.

Sau đó kiểm tra file bằng mắt: mở MinIO console (http://localhost:9001), đăng nhập bằng `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`, rồi vào `lakehouse/warehouse/bronze/raw_documents/`. Thư mục `data/` chứa các file `.parquet`, `metadata/` chứa các file `.metadata.json`, manifest (`.avro`) và snapshot (`snap-*.avro`). Sau khi chạy lại, `data/` có thể có nhiều file hơn số file mà truy vấn `.files` liệt kê: các snapshot cũ vẫn tham chiếu file cũ (chính điều này làm cho time travel hoạt động).

| Service | URL |
|---|---|
| Spark master UI | http://localhost:8080 |
| Spark worker UI | http://localhost:8081 |
| MinIO console | http://localhost:9001 |
| Iceberg REST Catalog | http://localhost:8181/v1/config |
| ClickHouse HTTP | http://localhost:8123/ping |
| JupyterLab | http://localhost:8888 (token đăng nhập được in trong `docker compose logs jupyter`) |

## Tắt / dọn dẹp

Chỉ dừng các service Lakehouse, để Phase 1 tiếp tục chạy:
```bash
docker compose stop iceberg-rest spark-master spark-worker clickhouse jupyter
```
**Đừng** dùng `docker compose --profile lakehouse down` cho việc này: `down` gỡ cả project, gồm cả postgres, backend và frontend. Volume dữ liệu (`pgdata`, `minio_data`) được giữ lại với cả hai lệnh.

## Xử lý sự cố

| Triệu chứng | Nguyên nhân và cách xử lý |
|---|---|
| `UnknownHostException: iceberg-rest` (hoặc `postgres`, `minio`) | Các container đó không chạy. `docker compose up -d spark-master` chỉ bật đúng service đó. Chạy `docker compose --profile lakehouse up -d`. |
| `iceberg-rest` báo `Exited (1)`; log ghi `database "iceberg_catalog" does not exist` | Volume Postgres được tạo trước khi có init script nên script chưa từng chạy. Tạo database một lần: `docker compose exec -T postgres psql -U postgres -c "CREATE DATABASE iceberg_catalog"`, rồi `docker compose --profile lakehouse up -d iceberg-rest`. |
| `NoSuchBucket` | Chưa chạy script bootstrap (bước 4). |
| `Missing required environment variable` | Thiếu một biến ở bước 1 trong `.env`; sau khi sửa, recreate `spark-master` bằng `docker compose --profile lakehouse up -d spark-master`. |
| Job treo với thông báo `Initial job has not accepted any resources` | Executor không kết nối ngược được tới driver. Thêm `--conf spark.driver.host=spark-master` vào lệnh `spark-submit`. |
| Sau khi Docker Desktop hoặc máy khởi động lại, mọi thứ đều dừng | Chạy lại `docker compose --profile lakehouse up -d`; volume vẫn giữ dữ liệu. |

## Tóm tắt lần chạy đầu tiên

```bash
# Phase 1 tới Bronze (README_docker_setup.md bước 1-5), rồi:
# tải 5 JAR (bước 2)
docker compose --profile lakehouse up -d
curl http://localhost:8181/v1/config
python infra/bootstrap/bootstrap_lakehouse.py
# chạy migrate_bronze_to_iceberg.py, rồi verify_bronze_iceberg.py (bước 5-6)
```
