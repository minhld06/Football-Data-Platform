-- =========================================================
-- Epic 5: Bronze schema — raw_documents table
-- Football Data Platform
-- =========================================================

CREATE SCHEMA IF NOT EXISTS bronze;

CREATE TABLE bronze.raw_documents (
  id              BIGSERIAL PRIMARY KEY,
  source          TEXT NOT NULL,           -- 'football-data-org', 'statbunker', 'understat'
  entity_type     TEXT NOT NULL,           -- 'match', 'standing'
  entity_id       TEXT,                    -- id from the original source, may be NULL if the source doesn't provide a clear id
  payload         JSONB NOT NULL,          -- the full raw JSON that was crawled
  source_url      TEXT,
  content_hash    TEXT NOT NULL,           -- sha256 of the payload, used for dedup
  ingestion_time  TIMESTAMPTZ NOT NULL DEFAULT now(),
  season          TEXT,                    -- '2025-2026'
  league          TEXT                     -- 'premier-league', 'ligue-1'
);

CREATE INDEX ix_raw_docs_source_entity ON bronze.raw_documents(source, entity_type);
CREATE INDEX ix_raw_docs_source_entity_id ON bronze.raw_documents(source, entity_id);
CREATE INDEX ix_raw_docs_payload ON bronze.raw_documents USING gin (payload);
CREATE UNIQUE INDEX uq_raw_docs_dedup ON bronze.raw_documents(source, entity_type, content_hash);