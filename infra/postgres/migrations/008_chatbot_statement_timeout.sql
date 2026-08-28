-- =========================================================
-- Chatbot: cap query runtime for the read-only role
-- Football Data Platform
-- =========================================================
-- validate_sql() (backend/chat_engine.py) whitelists tables and forces a
-- LIMIT, but a LIMIT only caps the *result*, not the work Postgres does to
-- produce it — an LLM-generated query can still join every allowed gold
-- table into a large cross product, or call a slow function like
-- pg_sleep(). Cap chatbot_ro's statement runtime so a bad query times out
-- instead of tying up a connection indefinitely.
--
-- Apply with:
--   psql -U postgres -d football -f infra/postgres/migrations/008_chatbot_statement_timeout.sql

ALTER ROLE chatbot_ro SET statement_timeout = '5s';
