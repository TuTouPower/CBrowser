FROM python:3.15-slim-trixie@sha256:8c13a3f37a6a5b71498228e902c4b9f51c1f7900d49fabf71f9a650c6120e0d0

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
COPY src/backend/cbrowser/launch_args.py /app/cbrowser/launch_args.py
COPY src/backend/cbrowser/domain /app/cbrowser/domain
COPY src/backend/cbrowser/network_config.py /app/cbrowser/network_config.py
COPY src/backend/cbrowser/gateway /app/cbrowser/gateway
COPY src/backend/cbrowser/stream_agent/__init__.py /app/cbrowser/stream_agent/__init__.py
COPY src/backend/cbrowser/stream_agent/protocol.py /app/cbrowser/stream_agent/protocol.py
COPY src/backend/cbrowser/supervisor/__init__.py /app/cbrowser/supervisor/__init__.py
COPY src/backend/cbrowser/supervisor/agent_credentials.py /app/cbrowser/supervisor/agent_credentials.py

RUN chown -R appuser:appgroup /app

USER 1000:1000

ENV PYTHONPATH=/app

ENTRYPOINT ["python3", "-m", "cbrowser.gateway"]
