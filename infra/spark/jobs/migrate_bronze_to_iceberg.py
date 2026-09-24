import logging
import os

from pyspark.sql import SparkSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
LOGGER = logging.getLogger("migrate_bronze_to_iceberg")

CATALOG = "lakehouse"
TARGET_TABLE = f"{CATALOG}.bronze.raw_documents"
PG_URL = "jdbc:postgresql://postgres:5432/football"
ICEBERG_REST_URL = "http://iceberg-rest:8181"
MINIO_ENDPOINT = "http://minio:9000"


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def build_spark_session() -> SparkSession:
    prefix = f"spark.sql.catalog.{CATALOG}"
    return (
        SparkSession.builder.appName("migrate_bronze_to_iceberg")
        .config(prefix, "org.apache.iceberg.spark.SparkCatalog")
        .config(f"{prefix}.type", "rest")
        .config(f"{prefix}.uri", ICEBERG_REST_URL)
        .config(f"{prefix}.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
        .config(f"{prefix}.s3.endpoint", MINIO_ENDPOINT)
        .config(f"{prefix}.s3.path-style-access", "true")
        .config(f"{prefix}.s3.access-key-id", require_env("MINIO_ROOT_USER"))
        .config(f"{prefix}.s3.secret-access-key", require_env("MINIO_ROOT_PASSWORD"))
        .config(f"{prefix}.client.region", "us-east-1")
        .getOrCreate()
    )


def main() -> None:
    spark = build_spark_session()
    try:
        spark.sql(f"SHOW NAMESPACES IN {CATALOG}").show()
    finally:
        spark.stop()


if __name__ == "__main__":
    main()