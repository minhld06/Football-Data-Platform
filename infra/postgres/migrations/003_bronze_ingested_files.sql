-- =========================================================
-- Bronze: bảng theo dõi file raw đã ingest thành công
-- Football Data Platform
-- =========================================================
-- Dùng để bỏ qua việc đọc/hash lại các file JSON không đổi ở những lần
-- chạy ingest.py sau, thay vì phải quét lại toàn bộ data/raw/ mỗi lần.
-- Không thay thế content_hash dedup ở bronze.raw_documents — chỉ là
-- fast-path để tránh phải mở/parse/hash file khi không cần thiết.

CREATE TABLE bronze.ingested_files (
  file_path     TEXT PRIMARY KEY,   -- path tương đối so với RAW_DIR, vd: football_data_org/matches/2026-07-10/epl.json
  source        TEXT NOT NULL,
  entity_type   TEXT NOT NULL,
  mtime         TIMESTAMPTZ NOT NULL,
  size_bytes    BIGINT NOT NULL,
  ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_ingested_files_source ON bronze.ingested_files(source);
