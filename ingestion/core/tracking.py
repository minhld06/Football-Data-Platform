import logging
from datetime import datetime

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
