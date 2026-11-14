FROM python:3.15-slim-trixie@sha256:8c13a3f37a6a5b71498228e902c4b9f51c1f7900d49fabf71f9a650c6120e0d0

# t065: proxy auth-forwarder image. Stdlib only — no pip install step, no
# third-party packages: the forwarder speaks HTTP proxy protocol and
# SOCKS5 with asyncio alone, so the image carries nothing an attacker
# could turn into a second egress path.
USER root

# Optional build ARG for local build mirror acceleration if specified; defaults to empty (official Debian)
ARG APT_MIRROR=""
RUN if [ -n "$APT_MIRROR" ]; then sed -i "s|deb.debian.org|$APT_MIRROR|g" /etc/apt/sources.list.d/debian.sources; fi

# tini is the gated entrypoint's process supervisor (the Supervisor starts
# this container with the gated entrypoint, which execs tini first).
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    tini \
    && rm -rf /var/lib/apt/lists/*

# Ensure non-root cbrowser user (UID 1000, GID 1000) exists
RUN if ! id -u cbrowser >/dev/null 2>&1; then \
        groupadd -g 1000 cbrowser && \
        useradd -u 1000 -g cbrowser -s /bin/bash -m cbrowser; \
    fi

WORKDIR /app

# Copy entrypoint and the whitelisted forwarder package code only:
# __init__ + redact (stdlib-only redaction) + the proxy_forwarder package.
# No other cbrowser module is reachable from this image.
COPY config/docker/proxy_forwarder_runtime/entrypoint.sh /app/entrypoint.sh
COPY src/backend/cbrowser/__init__.py /app/cbrowser/__init__.py
COPY src/backend/cbrowser/redact.py /app/cbrowser/redact.py
COPY src/backend/cbrowser/proxy_forwarder /app/cbrowser/proxy_forwarder

ENV PYTHONPATH=/app
RUN chown -R cbrowser:cbrowser /app && chmod +x /app/entrypoint.sh

USER cbrowser:cbrowser

ENTRYPOINT ["/usr/bin/tini", "--", "/app/entrypoint.sh"]
