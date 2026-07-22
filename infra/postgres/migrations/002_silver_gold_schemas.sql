CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
COMMENT ON SCHEMA silver IS 'Cleaned, deduped, typed data — source for silver-layer dbt models';
COMMENT ON SCHEMA gold IS 'Aggregated data serving the API/UI/chatbot — source for gold-layer dbt models';