import logging
import os

import boto3
import psycopg
import requests
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from psycopg import sql

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://localhost:9000")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "lakehouse")
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
ICEBERG_CATALOG_DB = os.environ.get("ICEBERG_CATALOG_DB", "iceberg_catalog")
ICEBERG_REST_URL = os.environ.get("ICEBERG_REST_URL", "http://localhost:8181")
ICEBERG_NAMESPACE = os.environ.get("ICEBERG_NAMESPACE", "bronze")
CLICKHOUSE_URL = os.environ.get("CLICKHOUSE_URL", "http://localhost:8123")
CLICKHOUSE_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "gold")


def ensure_postgres_database(dbname: str) -> None:
    with psycopg.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname="postgres",
        autocommit=True,
    ) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)
        ).fetchone()
        if exists:
            logger.info("Postgres database '%s' already exists", dbname)
            return
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
        logger.info("Created Postgres database '%s'", dbname)


def ensure_minio_bucket(bucket: str) -> None:
    s3 = boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=os.environ["MINIO_ROOT_USER"],
        aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"],
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}),
    )
    try:
        s3.head_bucket(Bucket=bucket)
        logger.info("MinIO bucket '%s' already exists", bucket)
        return
    except ClientError as e:
        if e.response["Error"]["Code"] not in ("404", "NoSuchBucket"):
            raise
    s3.create_bucket(Bucket=bucket)
    logger.info("Created MinIO bucket '%s'", bucket)


def ensure_iceberg_namespace(namespace: str) -> None:
    resp = requests.post(
        f"{ICEBERG_REST_URL}/v1/namespaces",
        json={"namespace": [namespace]},
        timeout=10,
    )
    if resp.status_code == 409:
        logger.info("Iceberg namespace '%s' already exists", namespace)
        return
    resp.raise_for_status()
    logger.info("Created Iceberg namespace '%s'", namespace)


def _clickhouse_query(query: str, params: dict[str, str] | None = None) -> str:
    resp = requests.post(
        CLICKHOUSE_URL,
        params={f"param_{key}": value for key, value in (params or {}).items()},
        data=query,
        auth=(os.environ["CLICKHOUSE_USER"], os.environ["CLICKHOUSE_PASSWORD"]),
        timeout=10,
    )
    if not resp.ok:
        raise RuntimeError(
            f"ClickHouse query failed (HTTP {resp.status_code}): {resp.text.strip()}"
        )
    return resp.text.strip()


def ensure_clickhouse_database(dbname: str) -> None:
    exists = _clickhouse_query(
        "SELECT count() FROM system.databases WHERE name = {name:String}",
        {"name": dbname},
    )
    if exists == "1":
        logger.info("ClickHouse database '%s' already exists", dbname)
        return
    _clickhouse_query("CREATE DATABASE {db:Identifier}", {"db": dbname})
    logger.info("Created ClickHouse database '%s'", dbname)


def main() -> None:
    ensure_postgres_database(ICEBERG_CATALOG_DB)
    ensure_minio_bucket(MINIO_BUCKET)
    ensure_iceberg_namespace(ICEBERG_NAMESPACE)
    ensure_clickhouse_database(CLICKHOUSE_DATABASE)


if __name__ == "__main__":
    main()