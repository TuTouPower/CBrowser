# syntax=docker/dockerfile:1.4
FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337

USER root

# Optional build ARG for local build mirror acceleration if specified; defaults to empty (official Debian)
ARG APT_MIRROR=""
RUN if [ -n "$APT_MIRROR" ]; then sed -i "s|deb.debian.org|$APT_MIRROR|g" /etc/apt/sources.list.d/debian.sources; fi

# Install native dependencies and tini for Selkies 2.1.0 runtime
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    build-essential \
    libx11-dev \
    libxext-dev \
    libxfixes-dev \
    libxtst-dev \
    libpulse-dev \
    libglib2.0-dev \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-tools \
    pulseaudio-utils \
    x11-utils \
    x11-xkb-utils \
    procps \
    curl \
    tini \
    && rm -rf /var/lib/apt/lists/*

# Install locked Python packages
COPY config/docker/stream_runtime/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && \
    rm -f /tmp/requirements.txt

# Ensure non-root cbrowser user (UID 1000, GID 1000) exists
RUN if ! id -u cbrowser >/dev/null 2>&1; then \
        groupadd -g 1000 cbrowser && \
        useradd -u 1000 -g cbrowser -s /bin/bash -m cbrowser; \
    fi

WORKDIR /app

# Copy entrypoint and whitelisted stream package code
COPY config/docker/stream_runtime/entrypoint.sh /app/entrypoint.sh
COPY src/backend/cbrowser/__init__.py /app/cbrowser/__init__.py
COPY src/backend/cbrowser/secret_files.py /app/cbrowser/secret_files.py
COPY src/backend/cbrowser/stream_agent /app/cbrowser/stream_agent

ENV PYTHONPATH=/app
RUN chown -R cbrowser:cbrowser /app && chmod +x /app/entrypoint.sh

USER cbrowser:cbrowser

ENTRYPOINT ["/usr/bin/tini", "--", "/app/entrypoint.sh"]
