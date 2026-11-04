FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/sh -m appuser

COPY config/docker/gateway_runtime/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && \
    rm -f /tmp/requirements.txt

COPY src/backend/cbrowser/__init__.py /app/cbrowser/__init__.py
COPY src/backend/cbrowser/udp_mux.py /app/cbrowser/udp_mux.py
COPY src/backend/cbrowser/secret_files.py /app/cbrowser/secret_files.py
COPY src/backend/cbrowser/gateway /app/cbrowser/gateway
COPY src/backend/cbrowser/stream_agent/__init__.py /app/cbrowser/stream_agent/__init__.py
COPY src/backend/cbrowser/stream_agent/protocol.py /app/cbrowser/stream_agent/protocol.py
COPY src/backend/cbrowser/supervisor/__init__.py /app/cbrowser/supervisor/__init__.py
COPY src/backend/cbrowser/supervisor/agent_credentials.py /app/cbrowser/supervisor/agent_credentials.py

RUN chown -R appuser:appgroup /app

USER 1000:1000

ENV PYTHONPATH=/app

ENTRYPOINT ["python3", "-m", "cbrowser.gateway"]
