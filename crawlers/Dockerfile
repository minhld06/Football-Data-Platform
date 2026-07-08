FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY crawlers/requirements.txt ./crawlers/requirements.txt

RUN pip install --upgrade pip \
    && pip install -r ./crawlers/requirements.txt

COPY crawlers ./crawlers

RUN mkdir -p /app/data/raw /app/logs

ENV PYTHONPATH=/app

CMD ["python", "-c", "print('Crawlers container with Playwright is ready')"]