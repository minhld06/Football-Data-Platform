import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def filter_pending_files(files: list[dict], tracked: dict, full_rehash: bool = False) -> list[dict]:
    """
    Filters down to the files that need reading/hashing: files never seen in bronze.ingested_files,
    or whose mtime/size differ from the last successful ingest.

    tracked: dict {rel_path: (mtime, size_bytes)} loaded from bronze.ingested_files.
    full_rehash=True: bypasses tracking entirely and returns every file (use when
    raw files may have been hand-edited without changing mtime/size).
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
    Reads bronze.ingested_files into a dict {rel_path: (mtime, size_bytes)}.
    If source_filter is given, only rows matching that source are loaded. Not filtered by date —
    this table doesn't store a date; discover_files() already filters by --date,
    so loading a few extra rows from other dates here is harmless.
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
    """Writes/refreshes a tracking row — only call after the file has been successfully upserted into bronze.raw_documents."""
    with conn.cursor() as cur:
        cur.execute(MARK_INGESTED_SQL, {
            "file_path": file_path,
            "source": source,
            "entity_type": entity_type,
            "mtime": mtime,
            "size_bytes": size_bytes,
        })
