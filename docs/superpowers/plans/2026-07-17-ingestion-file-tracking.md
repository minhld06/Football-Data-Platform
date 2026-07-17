# Ingestion File-Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `ingestion/ingest.py` from re-reading and re-hashing every raw JSON file on every run by tracking which files were already ingested successfully.

**Architecture:** A new Postgres table `bronze.ingested_files` records `(file_path, source, entity_type, mtime, size_bytes)` for every file that was successfully written to `bronze.raw_documents`. On each run, `ingest.py` loads this table, filters out files whose `mtime`+`size_bytes` haven't changed, and only reads/hashes the remainder. A `--full-rehash` CLI flag bypasses the filter for manual full reconciliation. The `content_hash`-based dedup on `bronze.raw_documents` is untouched and remains the final safety net against duplicate content.

**Tech Stack:** Python 3.11, psycopg3, PostgreSQL, pytest (new dev dependency for this feature).

**Spec:** `docs/superpowers/specs/2026-07-17-ingestion-file-tracking-design.md`

## Global Constraints

- Comments/docstrings in Vietnamese, matching the existing style in `ingestion/core/*.py` and `ingestion/ingest.py` — explain *why*, not what.
- Use the project `logging` logger (already configured in `ingest.py`), never `print`. Include context (source, entity_type, path) in log messages, matching existing log lines.
- Don't add broad `try/except`. Only catch real external risk (DB, file I/O, JSON parsing). Never silently swallow — log context and either skip the single file/record or re-raise. Config/DB/schema errors fail fast; a single bad file/record may be skipped with logging.
- Ingestion must remain idempotent: re-running at any point, with or without `--full-rehash`, must never create duplicate rows in `bronze.raw_documents`. The new tracking table only adds a fast-path skip — it must never be the thing that decides whether a Bronze row gets written.
- Only mark a file in `bronze.ingested_files` after its Bronze write has actually succeeded (insert or duplicate-skip). Never mark on a caught exception.
- YAGNI: no batching/pagination optimization for loading the tracking table in this phase (single `SELECT`, optionally filtered by `--source`). That's an explicit Phase-2-if-needed concern per the spec.
- Python 3.11+ type hints in the existing style (`list[dict]`, `dict`).
- Don't commit `.env`. Migrations are plain SQL applied manually via `psql`, not auto-run — same as `001_bronze_raw_documents.sql` and `002_silver_gold_schemas.sql`.

---

### Task 1: Migration — `bronze.ingested_files` table

**Files:**
- Create: `infra/postgres/migrations/003_bronze_ingested_files.sql`

**Interfaces:**
- Produces: table `bronze.ingested_files(file_path TEXT PRIMARY KEY, source TEXT, entity_type TEXT, mtime TIMESTAMPTZ, size_bytes BIGINT, ingested_at TIMESTAMPTZ)`, index `ix_ingested_files_source`. Task 4 queries and writes this table.

- [ ] **Step 1: Write the migration file**

```sql
-- =========================================================
-- Bronze: bảng theo dõi file raw đã ingest thành công
-- Football Data Platform
-- =========================================================
-- Dùng để bỏ qua việc đọc/hash lại các file JSON không đổi ở những lần
-- chạy ingest.py sau, thay vì phải quét lại toàn bộ data/raw/ mỗi lần.
-- Không thay thế content_hash dedup ở bronze.raw_documents — chỉ là
-- fast-path để tránh phải mở/parse/hash file khi không cần thiết.

CREATE TABLE bronze.ingested_files (
  file_path     TEXT PRIMARY KEY,   -- path tương đối so với RAW_DIR, vd: football_data_org/matches/2026-07-10/epl.json
  source        TEXT NOT NULL,
  entity_type   TEXT NOT NULL,
  mtime         TIMESTAMPTZ NOT NULL,
  size_bytes    BIGINT NOT NULL,
  ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_ingested_files_source ON bronze.ingested_files(source);
```

- [ ] **Step 2: Apply the migration to local Postgres and verify**

Run (adjust `-U`/`-d` if your local setup differs, matching `CLAUDE.md`'s existing migration instructions):

```powershell
psql -U postgres -d football -f infra/postgres/migrations/003_bronze_ingested_files.sql
psql -U postgres -d football -c "\d bronze.ingested_files"
```

Expected: `\d` output shows columns `file_path` (PK), `source`, `entity_type`, `mtime`, `size_bytes`, `ingested_at`, and index `ix_ingested_files_source`.

- [ ] **Step 3: Commit**

```bash
git add infra/postgres/migrations/003_bronze_ingested_files.sql
git commit -m "feat: add bronze.ingested_files tracking table migration"
```

---

### Task 2: Extend `discover_files()` with `rel_path`, `mtime`, `size_bytes`

**Files:**
- Modify: `ingestion/core/discovery.py`
- Modify: `ingestion/requirements.txt`
- Test: `ingestion/tests/test_discovery.py`

**Interfaces:**
- Consumes: nothing new (pure filesystem read).
- Produces: `discover_files(raw_dir, source_filter=None, date_filter=None) -> list[dict]` — each dict now additionally has `"rel_path": str` (POSIX-style path relative to `raw_dir`), `"mtime": datetime` (UTC, tz-aware), `"size_bytes": int`, alongside the existing `"path"`, `"source"`, `"entity_type"`, `"date"` keys. Task 3's `filter_pending_files` and Task 5's `build_records` consume `rel_path`/`mtime`/`size_bytes`.

- [ ] **Step 1: Add pytest to requirements**

Edit `ingestion/requirements.txt`, append:

```
pytest==8.3.3
```

Install it:

```powershell
cd ingestion
.venv\Scripts\pip.exe install -r requirements.txt
```

- [ ] **Step 2: Write the failing test**

Create `ingestion/tests/test_discovery.py`:

```python
from datetime import datetime

from core.discovery import discover_files


def test_discover_files_includes_rel_path_mtime_size(tmp_path):
    raw_dir = tmp_path / "raw"
    file_dir = raw_dir / "football_data_org" / "matches" / "2026-07-10"
    file_dir.mkdir(parents=True)
    file_path = file_dir / "PL_2025_120000_000000.json"
    file_path.write_text('{"a": 1}', encoding="utf-8")

    files = discover_files(raw_dir)

    assert len(files) == 1
    f = files[0]
    assert f["rel_path"] == "football_data_org/matches/2026-07-10/PL_2025_120000_000000.json"
    assert f["source"] == "football_data_org"
    assert f["entity_type"] == "matches"
    assert f["date"] == "2026-07-10"
    assert isinstance(f["mtime"], datetime)
    assert f["mtime"].tzinfo is not None
    assert f["size_bytes"] == file_path.stat().st_size
```

- [ ] **Step 3: Run test to verify it fails**

```powershell
cd ingestion
.venv\Scripts\python.exe -m pytest tests/test_discovery.py -v
```

Expected: FAIL with `KeyError: 'rel_path'` (the field doesn't exist yet).

- [ ] **Step 4: Implement**

Replace the body of `discover_files` in `ingestion/core/discovery.py`:

```python
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

def discover_files(raw_dir: Path, source_filter: str = None, date_filter: str = None):
    """
    Quét toàn bộ file JSON trong raw_dir theo cấu trúc:
    data/raw/{source}/{entity}/{date}/*.json

    Trả về list các dict chứa path + metadata đã tách, kèm rel_path/mtime/size_bytes
    dùng để so khớp với bronze.ingested_files (tránh phải đọc/hash lại file không đổi).
    """
    files_found = []

    for file_path in raw_dir.rglob("*.json"):
        # file_path ví dụ: data/raw/football-data-org/matches/2026-07-10/epl.json

        # .parts trả về tuple từng phần của đường dẫn
        # ('data', 'raw', 'football-data-org', 'matches', '2026-07-10', 'epl.json')
        parts = file_path.parts

        try:
            # Tìm vị trí của "raw" trong path, để lấy 3 phần ngay sau nó
            raw_index = parts.index(raw_dir.name)
            source = parts[raw_index + 1]
            entity_type = parts[raw_index + 2]
            date_str = parts[raw_index + 3]
        except (ValueError, IndexError):
            logger.warning(f"Bỏ qua file có cấu trúc đường dẫn không hợp lệ: {file_path}")
            continue

        # Áp filter nếu người dùng có truyền --source / --date
        if source_filter and source != source_filter:
            continue
        if date_filter and date_str != date_filter:
            continue

        stat = file_path.stat()

        files_found.append({
            "path": file_path,
            # Path tương đối so với raw_dir, dùng làm khóa tracking — ổn định
            # dù chạy trực tiếp trên host hay trong container Docker, khác với
            # absolute path sẽ đổi theo môi trường chạy.
            "rel_path": file_path.relative_to(raw_dir).as_posix(),
            "source": source,
            "entity_type": entity_type,
            "date": date_str,
            "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            "size_bytes": stat.st_size,
        })

    return files_found
```

- [ ] **Step 5: Run test to verify it passes**

```powershell
cd ingestion
.venv\Scripts\python.exe -m pytest tests/test_discovery.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ingestion/requirements.txt ingestion/core/discovery.py ingestion/tests/test_discovery.py
git commit -m "feat: add rel_path/mtime/size_bytes to discover_files output"
```

---

### Task 3: `filter_pending_files()` — pure filtering logic

**Files:**
- Create: `ingestion/core/tracking.py`
- Test: `ingestion/tests/test_tracking.py`

**Interfaces:**
- Consumes: file dicts shaped like Task 2's `discover_files()` output (needs at least `rel_path`, `mtime`, `size_bytes` keys).
- Produces: `filter_pending_files(files: list[dict], tracked: dict, full_rehash: bool = False) -> list[dict]`, where `tracked` is `{rel_path: (mtime, size_bytes)}`. Task 5's `build_records` calls this.

- [ ] **Step 1: Write the failing tests**

Create `ingestion/tests/test_tracking.py`:

```python
from datetime import datetime, timezone

from core.tracking import filter_pending_files

MTIME_A = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
MTIME_B = datetime(2026, 7, 11, 9, 30, 0, tzinfo=timezone.utc)


def _file(rel_path, mtime, size_bytes):
    return {"rel_path": rel_path, "mtime": mtime, "size_bytes": size_bytes}


def test_file_never_seen_is_kept():
    files = [_file("a.json", MTIME_A, 100)]
    tracked = {}

    result = filter_pending_files(files, tracked)

    assert result == files


def test_file_unchanged_mtime_and_size_is_skipped():
    files = [_file("a.json", MTIME_A, 100)]
    tracked = {"a.json": (MTIME_A, 100)}

    result = filter_pending_files(files, tracked)

    assert result == []


def test_file_with_different_mtime_is_kept():
    files = [_file("a.json", MTIME_B, 100)]
    tracked = {"a.json": (MTIME_A, 100)}

    result = filter_pending_files(files, tracked)

    assert result == files


def test_file_with_same_mtime_but_different_size_is_kept():
    files = [_file("a.json", MTIME_A, 999)]
    tracked = {"a.json": (MTIME_A, 100)}

    result = filter_pending_files(files, tracked)

    assert result == files


def test_full_rehash_keeps_all_files_regardless_of_tracking():
    files = [_file("a.json", MTIME_A, 100), _file("b.json", MTIME_B, 200)]
    tracked = {"a.json": (MTIME_A, 100), "b.json": (MTIME_B, 200)}

    result = filter_pending_files(files, tracked, full_rehash=True)

    assert result == files
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
cd ingestion
.venv\Scripts\python.exe -m pytest tests/test_tracking.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'core.tracking'`.

- [ ] **Step 3: Implement minimal code**

Create `ingestion/core/tracking.py`:

```python
import logging

logger = logging.getLogger(__name__)


def filter_pending_files(files: list[dict], tracked: dict, full_rehash: bool = False) -> list[dict]:
    """
    Lọc ra các file cần đọc/hash: file chưa từng thấy trong bronze.ingested_files,
    hoặc mtime/size khác với lần ingest thành công gần nhất.

    tracked: dict {rel_path: (mtime, size_bytes)} load từ bronze.ingested_files.
    full_rehash=True: bỏ qua tracking hoàn toàn, trả về mọi file (dùng khi nghi ngờ
    raw bị sửa tay mà mtime/size không đổi).
    """
    if full_rehash:
        return files

    pending = []
    for f in files:
        seen = tracked.get(f["rel_path"])
        if seen is not None and seen == (f["mtime"], f["size_bytes"]):
            continue
        pending.append(f)
    return pending
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
cd ingestion
.venv\Scripts\python.exe -m pytest tests/test_tracking.py -v
```

Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add ingestion/core/tracking.py ingestion/tests/test_tracking.py
git commit -m "feat: add filter_pending_files to skip unchanged tracked files"
```

---

### Task 4: `load_tracked_files()` and `mark_ingested()` — DB access

**Files:**
- Modify: `ingestion/core/tracking.py`

**Interfaces:**
- Consumes: `conn` — a `psycopg.Connection` opened via `core.db.get_connection()` (row factory `dict_row`, matching `core/db.py`'s existing pattern).
- Produces:
  - `load_tracked_files(conn, source_filter: str = None) -> dict` returning `{rel_path: (mtime, size_bytes)}`.
  - `mark_ingested(conn, file_path: str, source: str, entity_type: str, mtime: datetime, size_bytes: int) -> None`.
  Task 5's `main()` calls both.

No automated test for this task — the project has no test-database harness yet (`ingestion/core/db.py`'s existing `upsert_record`/`get_connection` also have none). Verified manually against a real local Postgres in Task 5's end-to-end check.

- [ ] **Step 1: Implement**

Add to `ingestion/core/tracking.py` (below the existing `filter_pending_files`):

```python
from datetime import datetime

LOAD_TRACKED_SQL = """
    SELECT file_path, mtime, size_bytes
    FROM bronze.ingested_files
    {where_clause};
"""

MARK_INGESTED_SQL = """
    INSERT INTO bronze.ingested_files
        (file_path, source, entity_type, mtime, size_bytes, ingested_at)
    VALUES
        (%(file_path)s, %(source)s, %(entity_type)s, %(mtime)s, %(size_bytes)s, now())
    ON CONFLICT (file_path) DO UPDATE
        SET mtime = EXCLUDED.mtime,
            size_bytes = EXCLUDED.size_bytes,
            ingested_at = EXCLUDED.ingested_at;
"""


def load_tracked_files(conn, source_filter: str = None) -> dict:
    """
    Đọc bronze.ingested_files thành dict {rel_path: (mtime, size_bytes)}.
    Nếu có source_filter, chỉ lấy dòng khớp source. Không lọc theo ngày —
    bảng này không lưu ngày; discover_files() đã tự lọc theo --date rồi,
    nên load dư vài dòng của ngày khác ở đây là vô hại.
    """
    where_clause = ""
    params = {}
    if source_filter:
        where_clause = "WHERE source = %(source)s"
        params["source"] = source_filter

    sql = LOAD_TRACKED_SQL.format(where_clause=where_clause)

    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    return {row["file_path"]: (row["mtime"], row["size_bytes"]) for row in rows}


def mark_ingested(conn, file_path: str, source: str, entity_type: str, mtime: datetime, size_bytes: int) -> None:
    """Ghi/refresh 1 dòng tracking — chỉ gọi sau khi file đã upsert thành công vào bronze.raw_documents."""
    with conn.cursor() as cur:
        cur.execute(MARK_INGESTED_SQL, {
            "file_path": file_path,
            "source": source,
            "entity_type": entity_type,
            "mtime": mtime,
            "size_bytes": size_bytes,
        })
```

- [ ] **Step 2: Manual smoke check against local Postgres**

Requires Task 1's migration already applied and `DATABASE_URL` set in `ingestion/.env`.

```powershell
cd ingestion
.venv\Scripts\python.exe -c "
from datetime import datetime, timezone
from core.db import get_connection
from core.tracking import load_tracked_files, mark_ingested

with get_connection() as conn:
    mark_ingested(conn, 'football_data_org/matches/2026-07-10/test.json', 'football_data_org', 'matches', datetime.now(timezone.utc), 123)
    conn.commit()
    print(load_tracked_files(conn, source_filter='football_data_org'))
"
```

Expected: prints a dict containing `'football_data_org/matches/2026-07-10/test.json': (datetime(...), 123)`.

Clean up the test row:

```powershell
psql -U postgres -d football -c "DELETE FROM bronze.ingested_files WHERE file_path = 'football_data_org/matches/2026-07-10/test.json';"
```

- [ ] **Step 3: Commit**

```bash
git add ingestion/core/tracking.py
git commit -m "feat: add load_tracked_files/mark_ingested DB access for tracking table"
```

---

### Task 5: Wire tracking into `ingest.py`, add `--full-rehash`, update docs

**Files:**
- Modify: `ingestion/ingest.py`
- Modify: `docs/README_ingestion.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: `discover_files` (Task 2), `filter_pending_files`, `load_tracked_files`, `mark_ingested` (Tasks 3–4).
- Produces: updated `build_records(raw_dir, source_filter=None, date_filter=None, tracked_files=None, full_rehash=False) -> list[dict]` (records now also carry `rel_path`/`mtime`/`size_bytes`), and CLI flag `--full-rehash` on `ingest.py`.

- [ ] **Step 1: Update imports and `build_records()`**

In `ingestion/ingest.py`, update the import block:

```python
from core.discovery import discover_files
from core.hashing import read_and_hash
from core.metadata import parse_league_season
from core.db import get_connection, upsert_record
from core.tracking import load_tracked_files, mark_ingested, filter_pending_files
```

Replace `build_records`:

```python
def build_records(raw_dir: Path, source_filter: str = None, date_filter: str = None,
                   tracked_files: dict = None, full_rehash: bool = False) -> list[dict]:
    '''Hàm quét thư mục raw_dir, lọc ra file mới/đã đổi, đọc + tính hash rồi build thành list record dict để insert vào DB.'''
    files = discover_files(raw_dir, source_filter=source_filter, date_filter=date_filter)
    logger.info(f"Tìm thấy {len(files)} file khớp filter")

    pending_files = filter_pending_files(files, tracked_files or {}, full_rehash=full_rehash)
    logger.info(f"{len(pending_files)} file cần đọc/hash (bỏ qua {len(files) - len(pending_files)} file không đổi so với lần ingest trước)")

    records = []
    for f in pending_files:
        try:
            hash_result = read_and_hash(f["path"])
            league_season = parse_league_season(f["path"].name)
        except (OSError, json.JSONDecodeError, ValueError) as e:
            logger.error(f"Bỏ qua file lỗi {f['path']}: {e}")
            continue

        record = {
            "source": f["source"],
            "entity_type": f["entity_type"],
            "entity_id": None,
            "payload": hash_result["raw_payload"],
            "content_hash": hash_result["content_hash"],
            "source_url": None,
            "league": league_season["league"],
            "season": league_season["season"],
            "rel_path": f["rel_path"],
            "mtime": f["mtime"],
            "size_bytes": f["size_bytes"],
        }
        records.append(record)

    return records
```

- [ ] **Step 2: Add `--full-rehash` CLI flag**

In `parse_args()`, after the `--date` argument:

```python
    parser.add_argument(
        "--full-rehash",
        action="store_true",
        help="Bỏ qua bronze.ingested_files, đọc/hash lại toàn bộ file khớp filter (dùng khi nghi ngờ raw bị sửa tay mà mtime/size không đổi)"
    )
```

- [ ] **Step 3: Wire tracking into `main()`**

Replace `main()`:

```python
def main():
    '''Hàm chính để chạy quá trình ingest.'''
    args = parse_args()

    if args.source or args.date:
        logger.info(f"Chạy với filter: source={args.source}, date={args.date}")
    else:
        logger.info("Chạy quét toàn bộ data/raw/ (không có filter)")
    if args.full_rehash:
        logger.info("--full-rehash: bỏ qua bronze.ingested_files, hash lại toàn bộ file khớp filter")

    inserted_count = 0
    skipped_count = 0
    failed_count = 0

    try:
        with get_connection() as conn:
            tracked_files = load_tracked_files(conn, source_filter=args.source)
            records = build_records(
                RAW_DIR,
                source_filter=args.source,
                date_filter=args.date,
                tracked_files=tracked_files,
                full_rehash=args.full_rehash,
            )

            for r in records:
                try:
                    is_new = upsert_record(conn, r)
                    mark_ingested(conn, r["rel_path"], r["source"], r["entity_type"], r["mtime"], r["size_bytes"])
                    conn.commit()
                except (psycopg.DataError, psycopg.IntegrityError) as e:
                    conn.rollback()
                    failed_count += 1
                    logger.error(
                        f"Bỏ qua record lỗi dữ liệu: {r['source']} | {r['entity_type']} | "
                        f"hash={r['content_hash'][:8]}...: {e}"
                    )
                    continue

                if is_new:
                    inserted_count += 1
                    logger.info(f"[MỚI] {r['source']} | {r['entity_type']} | hash={r['content_hash'][:8]}...")
                else:
                    skipped_count += 1
                    logger.info(f"[SKIP - đã tồn tại] {r['source']} | {r['entity_type']} | hash={r['content_hash'][:8]}...")
    except psycopg.OperationalError as e:
        logger.error(f"Không kết nối được database: {e}")
        raise

    logger.info(
        f"Hoàn tất: {inserted_count} record mới, {skipped_count} record bị bỏ qua (trùng), "
        f"{failed_count} record lỗi."
    )
```

Note `upsert_record` and `mark_ingested` now share one transaction/commit — if the Bronze upsert fails, the tracking row is rolled back too via the same `except` block, so a file is never marked "ingested" without its Bronze row actually landing.

- [ ] **Step 4: End-to-end manual verification**

Requires Task 1's migration applied and at least one real raw JSON file under `data/raw/`.

```powershell
cd "G:\Football Data Platform"
python ingestion/ingest.py
python ingestion/ingest.py
```

Expected: first run logs `[MỚI]` for each file and ends with `X record mới, 0 record bị bỏ qua`. Second run logs `N file khớp filter` and `0 file cần đọc/hash (bỏ qua N file không đổi so với lần ingest trước)` — i.e. no files get hashed on the second run.

Then touch a file's content without changing anything else and confirm it gets picked up:

```powershell
# chỉnh sửa nhẹ 1 file JSON bất kỳ trong data/raw/ (vd thêm khoảng trắng), rồi chạy lại
python ingestion/ingest.py
```

Expected: log shows exactly 1 file in "cần đọc/hash" for that changed file.

Finally verify `--full-rehash`:

```powershell
python ingestion/ingest.py --full-rehash
```

Expected: log shows all matched files back in "cần đọc/hash" regardless of tracking state; `bronze.raw_documents` row counts are unchanged (all skipped as duplicates by `content_hash`).

- [ ] **Step 5: Update docs**

In `docs/README_ingestion.md`:
- Under "Chạy có filter theo nguồn và/hoặc ngày", add:
  ```powershell
  python ingest.py --full-rehash
  ```
- Add a new subsection after "Idempotency" explaining `bronze.ingested_files`:
  ```markdown
  ## Tracking file đã ingest — vì sao chạy lại nhanh hơn khi số file tăng

  Mỗi lần 1 file được ghi thành công vào `bronze.raw_documents` (mới hoặc bị skip do trùng
  `content_hash`), path tương đối + mtime + size của file được ghi vào `bronze.ingested_files`.
  Lần chạy sau, file có mtime/size khớp với lần trước sẽ được bỏ qua, không đọc/hash lại —
  chi phí mỗi lần chạy chỉ còn tỉ lệ với số file mới/đổi, không phải tổng số file tích lũy.

  Dùng `--full-rehash` để bỏ qua tracking và hash lại toàn bộ (ví dụ khi nghi ngờ ai đó sửa
  tay file raw mà không đổi mtime).
  ```

In `CLAUDE.md`:
- In "Running the Ingestion Service", add `python ingestion/ingest.py --full-rehash` to the command list with a short comment.
- In "Database Schema (`bronze.raw_documents`)" section, add a short paragraph noting the companion `bronze.ingested_files` tracking table and its purpose.

- [ ] **Step 6: Commit**

```bash
git add ingestion/ingest.py docs/README_ingestion.md CLAUDE.md
git commit -m "feat: skip re-hashing unchanged raw files via bronze.ingested_files tracking"
```

---

## Self-Review Notes

- **Spec coverage**: migration (Task 1), `rel_path`/`mtime`/`size_bytes` in discovery (Task 2), pure filter logic + its 5 test cases from the spec (Task 3), DB read/write (Task 4), CLI `--full-rehash` + wiring + error-handling rule (only track on success) + docs (Task 5) — all spec sections covered.
- **Placeholder scan**: no TBD/TODO; every step has full code or exact commands with expected output.
- **Type consistency**: `filter_pending_files(files, tracked, full_rehash=False)` signature matches between Task 3's implementation and Task 5's `build_records` call. `load_tracked_files`/`mark_ingested` signatures match between Task 4's implementation and Task 5's `main()` call. `tracked` dict shape `{rel_path: (mtime, size_bytes)}` is consistent across Tasks 3, 4, and the spec.
