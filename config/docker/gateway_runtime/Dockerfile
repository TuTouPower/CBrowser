FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/sh -m appuser

RUN pip install --no-cache-dir \
    "aiohttp>=3.9.0" \
    "pydantic>=2.0.0" \
    "httpx>=0.27.0"

COPY src/backend/cbrowser/__init__.py /app/cbrowser/__init__.py
COPY src/backend/cbrowser/gateway /app/cbrowser/gateway
COPY src/backend/cbrowser/rtc_config /app/cbrowser/rtc_config
COPY src/backend/cbrowser/stream_agent/__init__.py /app/cbrowser/stream_agent/__init__.py
COPY src/backend/cbrowser/stream_agent/protocol.py /app/cbrowser/stream_agent/protocol.py
COPY src/backend/cbrowser/supervisor/__init__.py /app/cbrowser/supervisor/__init__.py
COPY src/backend/cbrowser/supervisor/agent_credentials.py /app/cbrowser/supervisor/agent_credentials.py

RUN chown -R appuser:appgroup /app

USER 1000:1000

ENV PYTHONPATH=/app

ENTRYPOINT ["python3", "-m", "cbrowser.gateway"]
