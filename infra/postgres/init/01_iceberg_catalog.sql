-- Runs once, when Postgres initializes an empty data volume (docker-entrypoint-initdb.d).
-- iceberg-rest exits at startup if this database is missing, so it must exist before the lakehouse profile starts.
CREATE DATABASE iceberg_catalog;
