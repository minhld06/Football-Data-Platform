-- =========================================================
-- Chatbot: read-only Postgres role for Text-to-SQL execution
-- Football Data Platform
-- =========================================================
-- The chatbot backend (backend/routers/chat.py) executes SQL that an LLM
-- generated from user input. That SQL must never run under the app's
-- normal DB user (POSTGRES_USER, which can write to bronze/silver/gold) —
-- a prompt-injected or malformed query could otherwise drop/alter/delete
-- data. This role can only SELECT from the gold schema.
--
-- Requires a password supplied at run time via a psql variable — never
-- hardcode a real password in this file. Set CHATBOT_DB_PASSWORD in .env,
-- then apply with:
--   psql -U postgres -d football -v chatbot_pw="$env:CHATBOT_DB_PASSWORD" -f infra/postgres/migrations/007_chatbot_readonly_role.sql

CREATE ROLE chatbot_ro WITH LOGIN PASSWORD :'chatbot_pw';

GRANT CONNECT ON DATABASE football TO chatbot_ro;
GRANT USAGE ON SCHEMA gold TO chatbot_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA gold TO chatbot_ro;

-- dbt (connected as POSTGRES_USER, default 'postgres') drops and recreates
-- gold tables on every `dbt run` — without this, chatbot_ro's SELECT grant
-- would be wiped out on the next build. Update the role name below if
-- POSTGRES_USER is changed from the default.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA gold GRANT SELECT ON TABLES TO chatbot_ro;
