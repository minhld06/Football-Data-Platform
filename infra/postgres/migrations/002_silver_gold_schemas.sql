CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
COMMENT ON SCHEMA silver IS 'Dữ liệu đã clean, dedup, typed — nguồn cho dbt models tầng silver';
COMMENT ON SCHEMA gold IS 'Dữ liệu đã aggregate, phục vụ API/UI/chatbot — nguồn cho dbt models tầng gold';