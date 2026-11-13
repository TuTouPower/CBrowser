FROM python:3.15-slim-trixie@sha256:8c13a3f37a6a5b71498228e902c4b9f51c1f7900d49fabf71f9a650c6120e0d0

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/sh -m appuser

COPY config/docker/api_runtime/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm -f /tmp/requirements.txt

COPY src/backend/__init__.py /app/__init__.py
COPY src/backend/cbrowser /app/cbrowser
COPY src/backend/migrations /app/migrations

RUN chown -R appuser:appgroup /app && \
    mkdir -p /data/db && \
    chown 1000:1000 /data/db

USER 1000:1000

EXPOSE 8000

CMD ["python3", "-m", "uvicorn", "cbrowser.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
