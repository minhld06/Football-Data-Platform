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

def get_chatbot_connection_string() -> str:
    db_url = os.environ.get("CHATBOT_DATABASE_URL")
    if not db_url:
        raise RuntimeError("CHATBOT_DATABASE_URL is not set in .env")
    return db_url


@contextmanager
def get_chatbot_connection():
    """Read-only connection scoped to gold.* via the chatbot_ro role (see infra/postgres/migrations/007_chatbot_readonly_role.sql)."""
    conn = psycopg.connect(get_chatbot_connection_string(), row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()