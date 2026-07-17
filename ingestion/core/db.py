import os
import json
import logging
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb
from dotenv import load_dotenv

from psycopg.rows import dict_row
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Load biến môi trường từ file .env cùng cấp với ingest.py
load_dotenv()


'''def get_connection():
    """
    Tạo kết nối tới PostgreSQL, dùng thông tin từ .env
    """
    return psycopg.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )'''


UPSERT_SQL = """
    INSERT INTO bronze.raw_documents
        (source, entity_type, entity_id, payload, source_url, content_hash, season, league)
    VALUES
        (%(source)s, %(entity_type)s, %(entity_id)s, %(payload)s, %(source_url)s, %(content_hash)s, %(season)s, %(league)s)
    ON CONFLICT (source, entity_type, content_hash) DO NOTHING
    RETURNING id;
"""


def upsert_record(conn, record: dict) -> bool:
    """
    Insert 1 record vào bronze.raw_documents.
    Trả về True nếu insert thành công (record mới),
    False nếu bị bỏ qua do trùng content_hash (đã tồn tại).
    """
    with conn.cursor() as cur:
        cur.execute(UPSERT_SQL, {
            "source": record["source"],
            "entity_type": record["entity_type"],
            "entity_id": record["entity_id"],
            "payload": Jsonb(record["payload"]),
            "source_url": record["source_url"],
            "content_hash": record["content_hash"],
            "season": record["season"],
            "league": record["league"],
        })
        result = cur.fetchone()
        return result is not None
    

def get_connection_string() -> str:
    """Đọc connection string từ biến môi trường (.env)."""
    # ví dụ: postgresql://postgres:password@localhost:5432/football
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL chưa được set trong .env")
    return db_url

@contextmanager
def get_connection():
    """Context manager: tự động đóng connection khi xong việc."""
    conn = psycopg.connect(get_connection_string(), row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()