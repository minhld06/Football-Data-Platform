-- =========================================================
-- Chatbot: schema + chat_logs table
-- Football Data Platform
-- =========================================================
-- Operational logging for the Text-to-SQL chatbot (backend/routers/chat.py).
-- Not part of the bronze/silver/gold medallion layers — this is app-level
-- bookkeeping, not pipeline data, hence its own schema.

CREATE SCHEMA IF NOT EXISTS chatbot;
COMMENT ON SCHEMA chatbot IS 'Application-level data for the chatbot feature (chat_logs) — not part of the bronze/silver/gold medallion layers';

CREATE TABLE chatbot.chat_logs (
  id                  BIGSERIAL PRIMARY KEY,
  conversation_id     TEXT NOT NULL,
  user_message        TEXT NOT NULL,
  model               TEXT NOT NULL,           -- OpenRouter model id, e.g. 'openai/gpt-4o-mini'
  sql_generated       TEXT,                     -- SQL the LLM produced; NULL if the request was rejected before SQL generation (off-topic/injection guard)
  response            TEXT,                     -- final answer text returned to the user; NULL if the request errored out
  prompt_tokens       INT,
  completion_tokens   INT,
  latency_ms          INT NOT NULL,
  cost_estimate_usd   NUMERIC(10, 6),
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_chat_logs_conversation ON chatbot.chat_logs(conversation_id);
CREATE INDEX ix_chat_logs_created_at ON chatbot.chat_logs(created_at);
