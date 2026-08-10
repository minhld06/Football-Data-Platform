-- =========================================================
-- Enable the pg_trgm extension (used by backend fuzzy search)
-- Football Data Platform
-- =========================================================
-- Lets /search tolerate minor typos (e.g. "Mancester" -> "Manchester")
-- via trigram similarity, without a dedicated search engine.

CREATE EXTENSION IF NOT EXISTS pg_trgm;
