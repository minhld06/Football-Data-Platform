# Ingestion Service — Football Data Platform

# English

Script that loads raw JSON data from `data/raw/` into the `bronze` schema on PostgreSQL.

## Purpose

- Scan all (or filtered) JSON files under `data/raw/{source}/{entity}/{date}/`.
- Compute a `content_hash` for each file to ensure idempotency (re-running never creates duplicate records).
- Normalize `league`/`season` from the filename via a whitelist (see `core/metadata.py`).
- Upsert into the `bronze.raw_documents` table.

## Structure

````
ingestion/
├── ingest.py           # Entry point, orchestrates the whole pipeline
├── core/
│   ├── discovery.py     # Scans files, extracts source/entity_type/date from the path
│   ├── hashing.py       # Reads JSON, computes content_hash
│   ├── metadata.py      # Normalizes league/season via a whitelist
│   └── db.py            # Connects to Postgres, upserts into bronze
├── .env                 # DB connection info (do NOT commit to Git)
└── requirements.txt
````

## Setup

````powershell
cd ingestion
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
````

Create a `.env` file with:

````
DB_HOST=localhost
DB_PORT=5432
DB_NAME=football
DB_USER=postgres
DB_PASSWORD=<your Postgres password>
````

## Running

**Run everything (default):**

````powershell
python ingest.py
````

**Run with a filter by source and/or date:**

````powershell
python ingest.py --source football_data_org
python ingest.py --date 2026-07-08
python ingest.py --source football_data_org --date 2026-07-08
python ingest.py --full-rehash
````

The script will:
1. Scan JSON files under `data/raw/` (all of them, or filtered).
2. For each file: compute the hash, normalize league/season, upsert into `bronze.raw_documents`.
3. Log the number of new records (`[NEW]`) and the number skipped as duplicates (`[SKIP - already exists]`).

### Example output

````
2026-07-13 21:27:50 [INFO] Found 7 files to process
2026-07-13 21:27:51 [INFO] [NEW] football_data_org | matches | hash=06679241...
...
2026-07-13 21:27:51 [INFO] Done: 7 new records, 0 records skipped (duplicates).
````

## Idempotency — why re-running is always safe

`content_hash` is computed from the raw JSON content (after `sort_keys`), and **does not include** the ingestion timestamp. The `bronze.raw_documents` table has a `UNIQUE INDEX` on `(source, entity_type, content_hash)`. If the file's content hasn't changed, the hash stays the same → `ON CONFLICT DO NOTHING` automatically skips it, so no duplicate record is created.

If the file's content changes (e.g. re-crawling standings with updates), the hash will differ → it gets inserted as a new record, preserving the **immutable** nature of the Bronze layer.

## Ingested-file tracking — why re-runs get faster as the file count grows

Every time a file is successfully written to `bronze.raw_documents` (whether new, or skipped as a duplicate
`content_hash`), its relative path + mtime + size are recorded in `bronze.ingested_files`.
On the next run, a file whose mtime/size match the previous run is skipped, without being re-read/re-hashed —
so the cost of each run scales only with new/changed files, not with the total accumulated file count.

Use `--full-rehash` to bypass tracking and re-hash everything (e.g. when you suspect someone
hand-edited a raw file without changing its mtime).

## Current limitations / TODO
- [ ] `entity_id` is currently always `NULL` — because each file today is a collection (many matches/teams in one file), not a single entity.
- [ ] `source_url` isn't saved by the crawlers yet, currently left as `NULL`.
- [ ] `league`/`season` normalization relies on a fixed whitelist in `core/metadata.py` (`LEAGUE_CODES`) — needs manual updates when adding a new league.

## Validation

The `ingestion/validate.py` script checks the data in `bronze.raw_documents`:

````powershell
python ingestion/validate.py
````

The script will:
1. Count records by `source`/`entity_type`/`league`/`season`, printed to the console and logged to `logs/validation.log`.
2. Compare against `ingestion/core/expected.py` (`EXPECTED_COMBOS`) to find combos that are completely missing — e.g. a source has no record for a season that another source already has data for.
3. Combos that have data but aren't declared in `EXPECTED_COMBOS` are logged at INFO level ("unexpected"), not counted as a gap — this can happen when a crawler is extended but the map hasn't been updated yet.

Exit code `1` if a gap is found, `0` if clean (usable for CI later on).

**Limitation:** only checks at the combo level (whether source/entity_type/league/season exists), it doesn't match individual matches/teams across sources — because `entity_id` in Bronze is currently always `NULL`. More detailed matching is left for the Silver layer.

# Français

Script qui charge les données JSON brutes de `data/raw/` vers le schéma `bronze` sur PostgreSQL.

## Objectif

- Parcourir tous les fichiers JSON (ou selon un filtre) dans `data/raw/{source}/{entity}/{date}/`.
- Calculer un `content_hash` pour chaque fichier afin de garantir l'idempotence (relancer plusieurs fois ne crée pas de doublons).
- Normaliser `league`/`season` à partir du nom de fichier via une whitelist (voir `core/metadata.py`).
- Upsert dans la table `bronze.raw_documents`.

## Structure

````
ingestion/
├── ingest.py           # Point d'entrée, orchestre tout le pipeline
├── core/
│   ├── discovery.py     # Parcourt les fichiers, extrait source/entity_type/date du chemin
│   ├── hashing.py       # Lit le JSON, calcule le content_hash
│   ├── metadata.py      # Normalise league/season via une whitelist
│   └── db.py            # Connexion à Postgres, upsert dans bronze
├── .env                 # Informations de connexion à la BDD (à NE PAS committer sur Git)
└── requirements.txt
````

## Installation

````powershell
cd ingestion
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
````

Créer un fichier `.env` avec :

````
DB_HOST=localhost
DB_PORT=5432
DB_NAME=football
DB_USER=postgres
DB_PASSWORD=<votre mot de passe Postgres>
````

## Exécution

**Exécuter l'ensemble (par défaut) :**

````powershell
python ingest.py
````

**Exécuter avec un filtre par source et/ou par date :**

````powershell
python ingest.py --source football_data_org
python ingest.py --date 2026-07-08
python ingest.py --source football_data_org --date 2026-07-08
python ingest.py --full-rehash
````

Le script va :
1. Parcourir les fichiers JSON dans `data/raw/` (tous, ou selon le filtre).
2. Pour chaque fichier : calculer le hash, normaliser league/season, upsert dans `bronze.raw_documents`.
3. Afficher le nombre de nouveaux enregistrements (`[NEW]`) et le nombre ignorés car en doublon (`[SKIP - already exists]`).

### Exemple de sortie

````
2026-07-13 21:27:50 [INFO] Found 7 files to process
2026-07-13 21:27:51 [INFO] [NEW] football_data_org | matches | hash=06679241...
...
2026-07-13 21:27:51 [INFO] Done: 7 new records, 0 records skipped (duplicates).
````

## Idempotence — pourquoi relancer plusieurs fois reste sûr

`content_hash` est calculé à partir du contenu JSON brut (après `sort_keys`), et **n'inclut pas** l'horodatage de l'ingestion. La table `bronze.raw_documents` possède un `UNIQUE INDEX` sur `(source, entity_type, content_hash)`. Si le contenu du fichier n'a pas changé, le hash reste identique → `ON CONFLICT DO NOTHING` l'ignore automatiquement, sans créer de doublon.

Si le contenu du fichier change (par exemple un re-crawl du classement avec des mises à jour), le hash sera différent → il sera inséré comme un nouvel enregistrement, préservant le caractère **immuable** de la couche Bronze.

## Suivi des fichiers ingérés — pourquoi les relances sont plus rapides quand le nombre de fichiers augmente

Chaque fois qu'un fichier est écrit avec succès dans `bronze.raw_documents` (nouveau, ou ignoré car en doublon de
`content_hash`), son chemin relatif + mtime + taille sont enregistrés dans `bronze.ingested_files`.
Au prochain lancement, un fichier dont le mtime/la taille correspondent à la fois précédente est ignoré, sans être relu/re-haché —
le coût de chaque exécution n'est donc proportionnel qu'aux fichiers nouveaux/modifiés, pas au nombre total de fichiers accumulés.

Utiliser `--full-rehash` pour ignorer le suivi et tout re-hacher (par exemple en cas de doute qu'un fichier
raw ait été modifié manuellement sans changer son mtime).

## Limites actuelles / TODO
- [ ] `entity_id` est actuellement toujours `NULL` — car chaque fichier est aujourd'hui une collection (plusieurs matchs/équipes dans un seul fichier), pas une entité unique.
- [ ] `source_url` n'est pas encore enregistré par les crawlers, actuellement laissé à `NULL`.
- [ ] La normalisation de `league`/`season` repose sur une whitelist fixe dans `core/metadata.py` (`LEAGUE_CODES`) — à mettre à jour manuellement lors de l'ajout d'un nouveau championnat.

## Validation

Le script `ingestion/validate.py` vérifie les données dans `bronze.raw_documents` :

````powershell
python ingestion/validate.py
````

Le script va :
1. Compter les enregistrements par `source`/`entity_type`/`league`/`season`, affichés dans la console et enregistrés dans `logs/validation.log`.
2. Comparer avec `ingestion/core/expected.py` (`EXPECTED_COMBOS`) pour trouver les combinaisons totalement manquantes — par exemple une source sans enregistrement pour une saison alors qu'une autre source a déjà des données pour cette saison.
3. Les combinaisons ayant des données mais non déclarées dans `EXPECTED_COMBOS` sont journalisées au niveau INFO ("unexpected"), sans être comptées comme un manque — cela peut arriver quand un crawler est étendu mais que la map n'a pas encore été mise à jour.

Code de sortie `1` si un manque est détecté, `0` si tout est propre (utilisable pour la CI plus tard).

**Limite :** ne vérifie qu'au niveau de la combinaison (existence de source/entity_type/league/season), sans comparer chaque match/équipe individuellement entre les sources — car `entity_id` dans Bronze est actuellement toujours `NULL`. Une comparaison plus détaillée est laissée à la couche Silver.

# Tiếng Việt

Script nạp dữ liệu thô (raw JSON) từ `data/raw/` vào schema `bronze` trên PostgreSQL.

## Mục đích

- Quét toàn bộ (hoặc theo filter) file JSON trong `data/raw/{source}/{entity}/{date}/`.
- Tính `content_hash` cho từng file để đảm bảo idempotency (chạy lại nhiều lần không tạo bản ghi trùng).
- Chuẩn hóa `league`/`season` từ tên file qua whitelist (xem `core/metadata.py`).
- Upsert vào bảng `bronze.raw_documents`.

## Cấu trúc

````
ingestion/
├── ingest.py           # Entry point, điều phối toàn bộ pipeline
├── core/
│   ├── discovery.py     # Quét file, tách source/entity_type/date từ path
│   ├── hashing.py       # Đọc JSON, tính content_hash
│   ├── metadata.py      # Chuẩn hóa league/season qua whitelist
│   └── db.py            # Kết nối Postgres, upsert vào bronze
├── .env                 # Thông tin kết nối DB (KHÔNG commit lên Git)
└── requirements.txt
````

## Cài đặt

````powershell
cd ingestion
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
````

Tạo file `.env` với nội dung:

````
DB_HOST=localhost
DB_PORT=5432
DB_NAME=football
DB_USER=postgres
DB_PASSWORD=<mật khẩu Postgres>
````

## Chạy

**Chạy toàn bộ (mặc định):**

````powershell
python ingest.py
````

**Chạy có filter theo nguồn và/hoặc ngày:**

````powershell
python ingest.py --source football_data_org
python ingest.py --date 2026-07-08
python ingest.py --source football_data_org --date 2026-07-08
python ingest.py --full-rehash
````

Script sẽ:
1. Quét file JSON trong `data/raw/` (toàn bộ hoặc theo filter).
2. Với mỗi file: tính hash, chuẩn hóa league/season, upsert vào `bronze.raw_documents`.
3. In log số lượng record mới (`[MỚI]`) và số lượng bị bỏ qua do trùng (`[SKIP - đã tồn tại]`).

### Ví dụ output

````
2026-07-13 21:27:50 [INFO] Tìm thấy 7 file cần xử lý
2026-07-13 21:27:51 [INFO] [MỚI] football_data_org | matches | hash=06679241...
...
2026-07-13 21:27:51 [INFO] Hoàn tất: 7 record mới, 0 record bị bỏ qua (trùng).
````

## Idempotency — vì sao chạy lại nhiều lần vẫn an toàn

`content_hash` được tính từ nội dung JSON gốc (đã `sort_keys`), **không bao gồm** thời điểm ingest. Bảng `bronze.raw_documents` có `UNIQUE INDEX` trên `(source, entity_type, content_hash)`. Nếu nội dung file không đổi, hash không đổi → `ON CONFLICT DO NOTHING` sẽ tự động bỏ qua, không tạo bản ghi trùng.

Nếu nội dung file thay đổi (ví dụ crawl lại standings có cập nhật), hash sẽ khác → được insert như 1 bản ghi mới, giữ đúng tính chất **immutable** của tầng Bronze.

## Tracking file đã ingest — vì sao chạy lại nhanh hơn khi số file tăng

Mỗi lần 1 file được ghi thành công vào `bronze.raw_documents` (mới hoặc bị skip do trùng
`content_hash`), path tương đối + mtime + size của file được ghi vào `bronze.ingested_files`.
Lần chạy sau, file có mtime/size khớp với lần trước sẽ được bỏ qua, không đọc/hash lại —
chi phí mỗi lần chạy chỉ còn tỉ lệ với số file mới/đổi, không phải tổng số file tích lũy.

Dùng `--full-rehash` để bỏ qua tracking và hash lại toàn bộ (ví dụ khi nghi ngờ ai đó sửa
tay file raw mà không đổi mtime).

## Giới hạn hiện tại / TODO
- [ ] `entity_id` hiện luôn là `NULL` — vì mỗi file hiện tại là 1 collection (nhiều trận đấu/nhiều đội trong 1 file), không phải 1 entity đơn lẻ.
- [ ] `source_url` chưa được crawler lưu lại, hiện để `NULL`.
- [ ] Chuẩn hóa `league`/`season` dựa trên whitelist cố định trong `core/metadata.py` (`LEAGUE_CODES`) — cần cập nhật thủ công khi thêm giải đấu mới.

## Validation

Script `ingestion/validate.py` kiểm tra dữ liệu trong `bronze.raw_documents`:

````powershell
python ingestion/validate.py
````

Script sẽ:
1. Đếm số bản ghi theo `source`/`entity_type`/`league`/`season`, in ra console + log vào `logs/validation.log`.
2. So với `ingestion/core/expected.py` (`EXPECTED_COMBOS`) để tìm combo bị thiếu hoàn toàn — ví dụ một nguồn không có bản ghi cho 1 season mà nguồn khác đã có dữ liệu season đó.
3. Combo có dữ liệu nhưng không khai báo trong `EXPECTED_COMBOS` được log mức INFO ("ngoài kỳ vọng"), không tính là gap — có thể do crawler được mở rộng nhưng map chưa cập nhật.

Exit code `1` nếu phát hiện gap, `0` nếu sạch (dùng được cho CI sau này).

**Giới hạn:** chỉ kiểm tra ở mức combo (source/entity_type/league/season có tồn tại hay không), không so khớp từng trận đấu/đội cụ thể giữa các nguồn — vì `entity_id` trong Bronze hiện luôn `NULL`. So khớp chi tiết hơn để dành cho tầng Silver.
