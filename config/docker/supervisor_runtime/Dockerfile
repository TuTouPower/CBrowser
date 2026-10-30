FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends iptables \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "docker>=7.0.0" \
    "httpx>=0.27.0" \
    "pydantic>=2.0.0" \
    "fastapi>=0.110.0" \
    "uvicorn>=0.28.0"

COPY src/backend/cbrowser/supervisor /app/cbrowser/supervisor
COPY src/backend/cbrowser/domain /app/cbrowser/domain

ENV PYTHONPATH=/app

ENTRYPOINT ["python3", "-m", "cbrowser.supervisor"]
