# transform/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# dbt requires git on PATH for "dbt deps" (package management)
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies BEFORE copying code -> leverage Docker layer caching
COPY transform/requirements.txt ./transform/requirements.txt
RUN pip install --no-cache-dir -r ./transform/requirements.txt

# Copy transform code into the image
COPY transform ./transform

WORKDIR /app/transform

# No fixed CMD/ENTRYPOINT args because dbt subcommands vary (build/run/test/snapshot)
# -> left blank; specify the command to run via "docker compose run"
ENTRYPOINT ["dbt"]
