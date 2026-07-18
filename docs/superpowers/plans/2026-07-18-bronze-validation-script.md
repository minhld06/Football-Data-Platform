# Bronze Validation Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `ingestion/validate.py`, a standalone script that counts `bronze.raw_documents` records by source/entity_type/league/season and flags combos that are missing compared to a declared "expected" map.

**Architecture:** Two new `ingestion/core/` modules (`expected.py` for the static expected-coverage map, `validation.py` for pure gap-detection logic) plus one new DB-access function in `core/db.py` (`fetch_counts`), wired together by a new `ingestion/validate.py` entry point that mirrors `ingest.py`'s logging/CLI conventions.

**Tech Stack:** Python 3.11+, psycopg3 (already a dependency), pytest.

## Global Constraints

- Reuse `core/db.get_connection()` for all DB access — do not open connections directly (per existing `ingestion/core/db.py` pattern).
- Use the project `logging` setup (console + file handler under `LOG_DIR`), never `print()` for script output — per CLAUDE.md logging rule.
- Infra errors (DB connection failure) must fail fast (`raise`), never be silently swallowed — per CLAUDE.md error-handling rule.
- Pure logic (gap detection) must be testable without a real DB connection, matching the existing `core/tracking.py` / `ingestion/tests/test_tracking.py` pattern.
- Follow existing Vietnamese docstring/comment style used throughout `ingestion/core/`.

---

### Task 1: Expected-coverage map + gap-detection logic (TDD)

**Files:**
- Create: `ingestion/core/expected.py`
- Create: `ingestion/core/validation.py`
- Test: `ingestion/tests/test_validation.py`

**Interfaces:**
- Consumes: nothing (pure data + pure functions, no DB).
- Produces:
  - `core.expected.EXPECTED_COMBOS: dict[str, dict[str, list[str]]]` — `{source: {entity_type: [league, ...]}}`, consumed by Task 3.
  - `core.validation.find_gaps(counts: list[dict], expected: dict) -> list[dict]` — each returned dict has keys `source`, `entity_type`, `league`, `season`. Consumed by Task 3.
  - `core.validation.find_unexpected_combos(counts: list[dict], expected: dict) -> list[dict]` — same shape as above. Consumed by Task 3.
  - Both functions expect `counts` as a list of dicts with at least keys `source`, `entity_type`, `league`, `season` (the `count` key, if present, is ignored).

- [ ] **Step 1: Write the failing tests**

Create `ingestion/tests/test_validation.py`:

```python
from core.validation import find_gaps, find_unexpected_combos

EXPECTED = {
    "football_data_org": {"matches": ["premier-league", "ligue-1"], "standings": ["premier-league", "ligue-1"]},
    "statbunker":         {"standings": ["premier-league"]},
    "understat":          {"standings": ["premier-league", "ligue-1"]},
}


def _row(source, entity_type, league, season, count=1):
    return {"source": source, "entity_type": entity_type, "league": league, "season": season, "count": count}


def test_no_gap_when_every_expected_combo_has_every_season():
    counts = [
        _row("football_data_org", "standings", "premier-league", "2025-2026"),
        _row("football_data_org", "matches", "premier-league", "2025-2026"),
        _row("football_data_org", "standings", "ligue-1", "2025-2026"),
        _row("football_data_org", "matches", "ligue-1", "2025-2026"),
        _row("statbunker", "standings", "premier-league", "2025-2026"),
        _row("understat", "standings", "premier-league", "2025-2026"),
        _row("understat", "standings", "ligue-1", "2025-2026"),
    ]

    gaps = find_gaps(counts, EXPECTED)

    assert gaps == []


def test_gap_when_source_missing_season_other_sources_have():
    counts = [
        _row("football_data_org", "standings", "premier-league", "2025-2026"),
        _row("football_data_org", "standings", "premier-league", "2026-2027"),
        _row("statbunker", "standings", "premier-league", "2025-2026"),
        # statbunker thiếu bản ghi cho season 2026-2027, dù football_data_org đã có
    ]

    gaps = find_gaps(counts, EXPECTED)

    assert {
        "source": "statbunker", "entity_type": "standings",
        "league": "premier-league", "season": "2026-2027",
    } in gaps


def test_no_gap_for_source_not_expected_to_have_league():
    # statbunker vốn không expected có ligue-1 -> không được coi là gap
    # dù ligue-1 xuất hiện ở nguồn khác.
    counts = [
        _row("football_data_org", "standings", "ligue-1", "2025-2026"),
    ]

    gaps = find_gaps(counts, EXPECTED)

    assert all(g["source"] != "statbunker" for g in gaps)


def test_combo_outside_expected_is_not_a_gap_but_is_flagged_unexpected():
    counts = [
        _row("football_data_org", "standings", "bundesliga", "2025-2026"),
    ]

    gaps = find_gaps(counts, EXPECTED)
    unexpected = find_unexpected_combos(counts, EXPECTED)

    assert gaps == []
    assert {
        "source": "football_data_org", "entity_type": "standings",
        "league": "bundesliga", "season": "2025-2026",
    } in unexpected
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `ingestion/` with its venv active):
```powershell
cd ingestion
python -m pytest tests/test_validation.py -v
```
Expected: `ModuleNotFoundError: No module named 'core.validation'` (or collection error) — the module doesn't exist yet.

- [ ] **Step 3: Write the implementation**

Create `ingestion/core/expected.py`:

```python
# Khai báo tĩnh: nguồn nào crawl entity_type/league nào (season-agnostic —
# season đổi theo thời gian nên không hardcode ở đây). Cập nhật thủ công
# khi thêm nguồn hoặc giải đấu mới, giống LEAGUE_CODES trong metadata.py.

EXPECTED_COMBOS = {
    "football_data_org": {
        "matches": ["premier-league", "ligue-1"],
        "standings": ["premier-league", "ligue-1"],
    },
    "statbunker": {
        "standings": ["premier-league"],
    },
    "understat": {
        "standings": ["premier-league", "ligue-1"],
    },
}
```

Create `ingestion/core/validation.py`:

```python
import logging

logger = logging.getLogger(__name__)


def find_gaps(counts: list[dict], expected: dict) -> list[dict]:
    """
    counts: list các dict {"source", "entity_type", "league", "season", "count"}
            (kết quả GROUP BY source, entity_type, league, season trên bronze.raw_documents).
    expected: EXPECTED_COMBOS — {source: {entity_type: [league, ...]}}.

    Với mỗi league, season "đáng lẽ phải có" được suy ra động = union mọi season
    đã thấy ở bất kỳ nguồn/entity_type nào cho league đó (không hardcode season).

    Trả về list gap: mỗi gap là 1 dict {"source", "entity_type", "league", "season"}
    ứng với 1 combo có trong `expected` nhưng không có bản ghi nào trong `counts`,
    trong khi season đó đã xuất hiện ở ít nhất 1 nguồn khác cho cùng league.
    """
    seasons_by_league: dict[str, set] = {}
    for row in counts:
        if row["league"] is None or row["season"] is None:
            continue
        seasons_by_league.setdefault(row["league"], set()).add(row["season"])

    present = {
        (row["source"], row["entity_type"], row["league"], row["season"])
        for row in counts
    }

    gaps = []
    for source, entity_types in expected.items():
        for entity_type, leagues in entity_types.items():
            for league in leagues:
                for season in seasons_by_league.get(league, set()):
                    if (source, entity_type, league, season) not in present:
                        gaps.append({
                            "source": source,
                            "entity_type": entity_type,
                            "league": league,
                            "season": season,
                        })
    return gaps


def find_unexpected_combos(counts: list[dict], expected: dict) -> list[dict]:
    """
    Trả về các combo (source, entity_type, league, season) đã có bản ghi trong
    `counts` nhưng (source, entity_type, league) không nằm trong `expected` —
    ví dụ crawler được mở rộng thêm giải đấu mới nhưng EXPECTED_COMBOS chưa cập
    nhật. Không phải lỗi (không tính là gap), chỉ để log mức INFO.
    """
    unexpected = []
    for row in counts:
        source, entity_type, league = row["source"], row["entity_type"], row["league"]
        expected_leagues = expected.get(source, {}).get(entity_type, [])
        if league not in expected_leagues:
            unexpected.append({
                "source": source,
                "entity_type": entity_type,
                "league": league,
                "season": row["season"],
            })
    return unexpected
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```powershell
cd ingestion
python -m pytest tests/test_validation.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add ingestion/core/expected.py ingestion/core/validation.py ingestion/tests/test_validation.py
git commit -m "feat: add gap-detection logic for bronze validation"
```

---

### Task 2: Counts query in `core/db.py`

**Files:**
- Modify: `ingestion/core/db.py`

**Interfaces:**
- Consumes: `conn` — a `psycopg.Connection` opened via `get_connection()` (already defined in this file, `row_factory=dict_row`).
- Produces: `core.db.fetch_counts(conn) -> list[dict]` — each dict has keys `source`, `entity_type`, `league`, `season`, `count`. Consumed by Task 3.

No new test file for this task: `core/db.py`'s existing functions (`upsert_record`, `get_connection`) have no unit tests in this repo either — they're thin DB wrappers, verified via the manual DB run in Task 3, consistent with existing project convention.

- [ ] **Step 1: Add the query and function**

In `ingestion/core/db.py`, add after `UPSERT_SQL`/`upsert_record` (i.e. after line 60):

```python
COUNTS_SQL = """
    SELECT source, entity_type, league, season, COUNT(*) AS count
    FROM bronze.raw_documents
    GROUP BY source, entity_type, league, season
    ORDER BY source, entity_type, league, season;
"""


def fetch_counts(conn) -> list[dict]:
    """Đếm số bản ghi trong bronze.raw_documents theo source/entity_type/league/season."""
    with conn.cursor() as cur:
        cur.execute(COUNTS_SQL)
        return cur.fetchall()
```

- [ ] **Step 2: Verify existing tests still pass**

Run:
```powershell
cd ingestion
python -m pytest -v
```
Expected: all previously-passing tests (`test_discovery.py`, `test_tracking.py`, `test_validation.py`) still pass — this change is additive only.

- [ ] **Step 3: Commit**

```bash
git add ingestion/core/db.py
git commit -m "feat: add fetch_counts query for bronze validation"
```

---

### Task 3: `ingestion/validate.py` entry point + docs

**Files:**
- Create: `ingestion/validate.py`
- Modify: `docs/README_ingestion.md`

**Interfaces:**
- Consumes:
  - `core.db.get_connection()`, `core.db.fetch_counts(conn)` (Task 2)
  - `core.expected.EXPECTED_COMBOS` (Task 1)
  - `core.validation.find_gaps(counts, expected)`, `core.validation.find_unexpected_combos(counts, expected)` (Task 1)
- Produces: a runnable script `python ingestion/validate.py`, exit code `0` (no gaps) or `1` (gaps found), logging to console + `logs/validation.log`.

- [ ] **Step 1: Write `ingestion/validate.py`**

```python
import logging
import os
from pathlib import Path

import psycopg

from core.db import get_connection, fetch_counts
from core.expected import EXPECTED_COMBOS
from core.validation import find_gaps, find_unexpected_combos

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = Path(os.environ.get("LOG_DIR", str(_PROJECT_ROOT / "logs")))
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "validation.log", encoding="utf-8"),
    ],
)

logger = logging.getLogger(__name__)


def print_counts_table(counts: list[dict]) -> None:
    logger.info("=== Số bản ghi theo source/entity_type/league/season ===")
    for row in counts:
        logger.info(
            f"{row['source']:<20} {row['entity_type']:<10} "
            f"{row['league'] or '-':<16} {row['season'] or '-':<10} {row['count']}"
        )


def main() -> int:
    try:
        with get_connection() as conn:
            counts = fetch_counts(conn)
    except psycopg.OperationalError as e:
        logger.error(f"Không kết nối được database: {e}")
        raise

    if not counts:
        logger.warning("bronze.raw_documents đang rỗng — chưa có gì để validate.")
        return 0

    print_counts_table(counts)

    unexpected = find_unexpected_combos(counts, EXPECTED_COMBOS)
    for u in unexpected:
        logger.info(
            f"[NGOÀI KỲ VỌNG] {u['source']} | {u['entity_type']} | {u['league']} | {u['season']} "
            f"— không có trong EXPECTED_COMBOS, có thể cần cập nhật core/expected.py"
        )

    gaps = find_gaps(counts, EXPECTED_COMBOS)
    if gaps:
        logger.error(f"Phát hiện {len(gaps)} gap:")
        for g in gaps:
            logger.error(
                f"[GAP] {g['source']} thiếu {g['entity_type']} cho {g['league']} "
                f"season {g['season']} (nguồn khác đã có dữ liệu season này)"
            )
        return 1

    logger.info("Không phát hiện gap nào.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run it against the real database**

Requires Postgres running (`docker compose up -d`) and `ingestion/.env` with `DATABASE_URL` set (already required by `ingest.py`).

Run:
```powershell
cd ingestion
python validate.py
```
Expected: a counts table logged to console, matching current `bronze.raw_documents` contents (currently only `standings`/`matches` for `football_data_org`, `statbunker`, `understat` per `data/raw/` — see Task 1's `EXPECTED_COMBOS`), an exit code (`echo $LASTEXITCODE` in PowerShell) of `0` or `1` depending on whether every expected combo already has data for every season present, and a new/updated `logs/validation.log` file.

- [ ] **Step 3: Add a "Validation" section to `docs/README_ingestion.md`**

Append after the existing "## Giới hạn hiện tại / TODO" section (end of file):

```markdown

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
```

- [ ] **Step 4: Commit**

```bash
git add ingestion/validate.py docs/README_ingestion.md
git commit -m "feat: add ingestion/validate.py for bronze gap detection"
```
