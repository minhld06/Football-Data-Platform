# ingestion/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies BEFORE copying code -> leverage Docker layer caching
COPY ingestion/requirements.txt ./ingestion/requirements.txt
RUN pip install --no-cache-dir -r ./ingestion/requirements.txt

# Copy ingestion code into the image
COPY ingestion ./ingestion


# No fixed CMD/ENTRYPOINT args because ingest.py accepts CLI args (--source, --date)
# -> left blank; specify the command to run via "docker run" or docker-compose
ENTRYPOINT ["python", "ingestion/ingest.py"]