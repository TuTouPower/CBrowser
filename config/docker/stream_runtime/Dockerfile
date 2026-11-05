FROM python:3.15-slim-trixie@sha256:8c13a3f37a6a5b71498228e902c4b9f51c1f7900d49fabf71f9a650c6120e0d0 AS builder

USER root

# Optional build ARG for local build mirror acceleration if specified; defaults to empty (official Debian)
ARG APT_MIRROR=""
RUN if [ -n "$APT_MIRROR" ]; then sed -i "s|deb.debian.org|$APT_MIRROR|g" /etc/apt/sources.list.d/debian.sources; fi

# Build toolchain and -dev headers exist only in this stage (t024 AC-015 /
# A50): native wheels are compiled here and only the finished virtualenv is
# copied into the runtime image, which therefore carries no compiler.
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
    && rm -rf /var/lib/apt/lists/*

# Install locked Python packages into a self-contained virtualenv
COPY config/docker/stream_runtime/requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt && \
    rm -f /tmp/requirements.txt

FROM python:3.15-slim-trixie@sha256:8c13a3f37a6a5b71498228e902c4b9f51c1f7900d49fabf71f9a650c6120e0d0

USER root

# Optional build ARG for local build mirror acceleration if specified; defaults to empty (official Debian)
ARG APT_MIRROR=""
RUN if [ -n "$APT_MIRROR" ]; then sed -i "s|deb.debian.org|$APT_MIRROR|g" /etc/apt/sources.list.d/debian.sources; fi

# Runtime shared libraries and tools for Selkies 2.1.0 only: the runtime
# counterparts of the builder stage's -dev packages, with no toolchain.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    libx11-6 \
    libxext6 \
    libxfixes3 \
    libxtst6 \
    libpulse0 \
    libglib2.0-0 \
    libgstreamer1.0-0 \
    libgstreamer-plugins-base1.0-0 \
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

COPY --from=builder /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

# Ensure non-root cbrowser user (UID 1000, GID 1000) exists
RUN if ! id -u cbrowser >/dev/null 2>&1; then \
        groupadd -g 1000 cbrowser && \
        useradd -u 1000 -g cbrowser -s /bin/bash -m cbrowser; \
    fi

WORKDIR /app

# Copy entrypoint and whitelisted stream package code
COPY config/docker/stream_runtime/entrypoint.sh /app/entrypoint.sh
COPY src/backend/cbrowser/__init__.py /app/cbrowser/__init__.py
COPY src/backend/cbrowser/udp_mux.py /app/cbrowser/udp_mux.py
COPY src/backend/cbrowser/secret_files.py /app/cbrowser/secret_files.py
COPY src/backend/cbrowser/stream_agent /app/cbrowser/stream_agent

ENV PYTHONPATH=/app
RUN chown -R cbrowser:cbrowser /app && chmod +x /app/entrypoint.sh

USER cbrowser:cbrowser

ENTRYPOINT ["/usr/bin/tini", "--", "/app/entrypoint.sh"]
