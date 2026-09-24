from pyspark.sql import SparkSession

from migrate_bronze_to_iceberg import LOGGER, TARGET_TABLE, build_spark_session


def check_counts(spark: SparkSession) -> None:
    LOGGER.info("Query 1: rows per source / entity_type in %s", TARGET_TABLE)
    spark.sql(
        f"SELECT source, entity_type, count(*) AS n FROM {TARGET_TABLE} "
        "GROUP BY source, entity_type ORDER BY source, entity_type"
    ).show(truncate=False)
    LOGGER.info("Total rows: %d", spark.table(TARGET_TABLE).count())

def check_snapshots(spark: SparkSession) -> None:
    LOGGER.info("Query 2: Iceberg snapshots of %s", TARGET_TABLE)
    spark.sql(
        "SELECT committed_at, snapshot_id, operation, "
        "summary['added-records'] AS added_records, "
        "summary['total-records'] AS total_records "
        f"FROM {TARGET_TABLE}.snapshots ORDER BY committed_at"
    ).show(truncate=False)

def check_files(spark: SparkSession) -> None:
    LOGGER.info("Query 3: data files in the current snapshot of %s", TARGET_TABLE)
    spark.sql(
        "SELECT file_path, file_format, record_count, file_size_in_bytes "
        f"FROM {TARGET_TABLE}.files"
    ).show(truncate=False)

def check_time_travel(spark: SparkSession) -> None:
    first_snapshot_id = spark.sql(
        f"SELECT snapshot_id FROM {TARGET_TABLE}.snapshots ORDER BY committed_at LIMIT 1"
    ).first()["snapshot_id"]
    LOGGER.info("Query 4: time travel to the first snapshot %d", first_snapshot_id)
    spark.sql(
        f"SELECT count(*) AS n FROM {TARGET_TABLE} VERSION AS OF {first_snapshot_id}"
    ).show()

def main() -> None:
    spark = build_spark_session()
    try:
        check_counts(spark)
        check_snapshots(spark)
        check_files(spark)
        check_time_travel(spark)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()