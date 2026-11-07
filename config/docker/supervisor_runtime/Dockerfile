FROM python:3.15-slim-trixie@sha256:8c13a3f37a6a5b71498228e902c4b9f51c1f7900d49fabf71f9a650c6120e0d0

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends iptables \
    && rm -rf /var/lib/apt/lists/*

COPY config/docker/supervisor_runtime/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && \
    rm -f /tmp/requirements.txt

COPY src/backend/cbrowser/__init__.py /app/cbrowser/__init__.py
COPY src/backend/cbrowser/udp_mux.py /app/cbrowser/udp_mux.py
COPY src/backend/cbrowser/secret_files.py /app/cbrowser/secret_files.py
COPY src/backend/cbrowser/launch_args.py /app/cbrowser/launch_args.py
COPY src/backend/cbrowser/preview.py /app/cbrowser/preview.py
COPY src/backend/cbrowser/supervisor /app/cbrowser/supervisor
COPY src/backend/cbrowser/services/__init__.py /app/cbrowser/services/__init__.py
COPY src/backend/cbrowser/services/tunnel_registry.py /app/cbrowser/services/tunnel_registry.py
COPY src/backend/cbrowser/domain /app/cbrowser/domain
COPY src/backend/cbrowser/font_sets /app/cbrowser/font_sets
COPY src/backend/cbrowser/gateway /app/cbrowser/gateway
COPY src/backend/cbrowser/runtime_agent /app/cbrowser/runtime_agent

ENV PYTHONPATH=/app

ENTRYPOINT ["python3", "-m", "cbrowser.supervisor"]
