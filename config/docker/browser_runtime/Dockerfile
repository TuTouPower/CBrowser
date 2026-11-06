# Independent, reproducible Browser Runtime image for CBrowser v2
FROM debian:trixie-slim@sha256:f6b08b09a05725f9431502d3b5714f5c4576e82c1a84fa1debe0c24a7e0c3ec4 AS xshm_probe_builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libx11-dev libxext-dev libc6-dev && rm -rf /var/lib/apt/lists/*
COPY tests/fixtures/runtime_probe/test_mitshm.c /tmp/test_mitshm.c
RUN gcc -O2 /tmp/test_mitshm.c -lX11 -lXext -o /test_mitshm

FROM debian:trixie-slim@sha256:f6b08b09a05725f9431502d3b5714f5c4576e82c1a84fa1debe0c24a7e0c3ec4 AS base_fonts_builder
# Base open-source fonts (plan 6.8, six apt packages) satisfy CloakBrowser's
# documented minimum install. They are Linux-flavoured, so they live under
# /opt/cbrowser-base-fonts outside fontconfig's default scan paths and are
# deliberately NOT whitelisted by the per-profile FONTCONFIG_FILE: a windows
# or macos fingerprint Profile must never see WenQuanYi, Unifont, FreeFont,
# IPAGothic or Loma. Only the bound platform font set is whitelisted.
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto-color-emoji \
    fonts-freefont-ttf \
    fonts-unifont \
    fonts-ipafont-gothic \
    fonts-wqy-zenhei \
    fonts-tlwg-loma-otf \
    && mkdir -p /opt/cbrowser-base-fonts \
    && cp -a /usr/share/fonts/. /opt/cbrowser-base-fonts/ \
    && rm -rf /var/lib/apt/lists/*

FROM python:3.15-slim-trixie@sha256:8c13a3f37a6a5b71498228e902c4b9f51c1f7900d49fabf71f9a650c6120e0d0

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

# Install system dependencies: X11, Openbox, PulseAudio, and Chromium runtime libraries
# (GTK 3 is loaded by Chromium for the page file chooser dialog)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tini \
    supervisor \
    xvfb \
    openbox \
    pulseaudio \
    pulseaudio-utils \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    x11-utils \
    xauth \
    xdotool \
    procps \
    ca-certificates \
    fonts-liberation \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# Install locked Python packages required for Browser Agent and CloakBrowser SDK
COPY config/docker/browser_runtime/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && \
    rm -f /tmp/requirements.txt

# Create non-root user 'cbrowser' with UID 1000 and GID 1000
RUN groupadd -g 1000 cbrowser && \
    useradd -u 1000 -g 1000 -m -s /bin/bash cbrowser

# Create mount points and runtime directories
RUN mkdir -p /app/src/backend \
    /data/engine-cache \
    /data/profiles \
    /data/runtime-events \
    /exchange/downloads \
    /run/cbrowser/runtime \
    /pulse \
    /tmp/.X11-unix \
    /home/cbrowser/.config && \
    chown -R cbrowser:cbrowser \
    /app \
    /data \
    /exchange \
    /run/cbrowser \
    /pulse \
    /home/cbrowser && \
    chmod 1777 /tmp /tmp/.X11-unix

# Environment configuration: strict unified engine cache, non-root paths
ENV HOME=/home/cbrowser \
    USER=cbrowser \
    CLOAKBROWSER_CACHE_DIR=/data/engine-cache \
    XDG_CACHE_HOME=/tmp/.cache \
    XDG_CONFIG_HOME=/tmp/.config \
    XDG_DATA_HOME=/tmp/.local/share \
    PULSE_RUNTIME_PATH=/tmp/pulse-runtime \
    PYTHONPATH=/app/src/backend

# Copy backend codebase and entrypoint
COPY src/backend/cbrowser /app/src/backend/cbrowser
COPY config/docker/browser_runtime/entrypoint.sh /app/entrypoint.sh
COPY --from=xshm_probe_builder /test_mitshm /usr/local/bin/test_mitshm
COPY --from=base_fonts_builder /opt/cbrowser-base-fonts /opt/cbrowser-base-fonts

USER root
RUN chmod 755 /usr/local/bin/test_mitshm /app/entrypoint.sh && \
    chown cbrowser:cbrowser /app/entrypoint.sh && \
    chown -R cbrowser:cbrowser /opt/cbrowser-base-fonts

USER cbrowser
WORKDIR /home/cbrowser

ENTRYPOINT ["/usr/bin/tini", "-g", "--", "/app/entrypoint.sh"]
CMD ["--help"]
