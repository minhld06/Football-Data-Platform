-- =========================================================
-- Bronze: table tracking raw files that have been successfully ingested
-- Football Data Platform
-- =========================================================
-- Used to skip re-reading/hashing unchanged JSON files on subsequent
-- ingest.py runs, instead of re-scanning all of data/raw/ every time.
-- Does not replace the content_hash dedup in bronze.raw_documents — it's just a
-- fast-path to avoid opening/parsing/hashing files when it isn't necessary.

CREATE TABLE bronze.ingested_files (
  file_path     TEXT PRIMARY KEY,   -- path relative to RAW_DIR, e.g.: football_data_org/matches/2026-07-10/epl.json
  source        TEXT NOT NULL,
  entity_type   TEXT NOT NULL,
  mtime         TIMESTAMPTZ NOT NULL,
  size_bytes    BIGINT NOT NULL,
  ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_ingested_files_source ON bronze.ingested_files(source);
