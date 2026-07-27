# backend/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies BEFORE copying code -> leverage Docker layer caching
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r ./backend/requirements.txt

# Copy backend code into the image
COPY backend ./backend

WORKDIR /app/backend

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]