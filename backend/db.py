import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()


def get_connection_string() -> str:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set in .env")
    return db_url


@contextmanager
def get_connection():
    """Context manager: automatically closes the connection when done."""
    conn = psycopg.connect(get_connection_string(), row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()