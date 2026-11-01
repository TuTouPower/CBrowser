FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337

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
COPY src/backend/cbrowser/supervisor /app/cbrowser/supervisor
COPY src/backend/cbrowser/domain /app/cbrowser/domain

ENV PYTHONPATH=/app

ENTRYPOINT ["python3", "-m", "cbrowser.supervisor"]
