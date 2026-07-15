# ingestion/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Cài dependencies TRƯỚC khi copy code -> tận dụng Docker layer caching
COPY ingestion/requirements.txt ./ingestion/requirements.txt
RUN pip install --no-cache-dir -r ./ingestion/requirements.txt

# Copy code ingestion vào image
COPY ingestion ./ingestion


# Không có CMD/ENTRYPOINT cố định vì ingest.py nhận CLI args (--source, --date)
# -> để trống, chỉ định lệnh chạy khi "docker run" hoặc trong docker-compose
ENTRYPOINT ["python", "ingestion/ingest.py"]