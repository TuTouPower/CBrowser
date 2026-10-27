#!/bin/bash
set -euo pipefail

PROBE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Cleaning previous cbrowser-spike-rtc-split-stream and cbrowser-spike-rtc-split-browser ==="
docker rm -f cbrowser-spike-rtc-split-stream cbrowser-spike-rtc-split-browser 2>/dev/null || true
docker volume rm -f cbrowser-spike-rtc-split-x11 cbrowser-spike-rtc-split-pulse 2>/dev/null || true

echo "=== Creating isolated volumes ==="
docker volume create cbrowser-spike-rtc-split-x11
docker volume create cbrowser-spike-rtc-split-pulse

echo "=== Starting cbrowser-spike-rtc-split-browser ==="
docker run -d \
  --name cbrowser-spike-rtc-split-browser \
  --network cbrowser-spike-rtc-split-net \
  --ipc shareable \
  --shm-size 1g \
  -v cbrowser-spike-rtc-split-x11:/tmp/.X11-unix \
  -v cbrowser-spike-rtc-split-pulse:/tmp/pulse \
  -v "$PROBE_DIR/media_fixture/entrypoint_browser.sh":/entrypoint_browser.sh:ro \
  --entrypoint /entrypoint_browser.sh \
  cbrowser-spike-runtime-browser:test

echo "=== Starting cbrowser-spike-rtc-split-stream ==="
docker run -d \
  --name cbrowser-spike-rtc-split-stream \
  --network cbrowser-spike-rtc-split-net \
  --ipc container:cbrowser-spike-rtc-split-browser \
  -p 127.0.0.1:18091:18091 \
  -p 127.0.0.1:18092:18092 \
  -p 127.0.0.1:30016:30016/udp \
  -v cbrowser-spike-rtc-split-x11:/tmp/.X11-unix \
  -v cbrowser-spike-rtc-split-pulse:/tmp/pulse \
  -v "$PROBE_DIR":/probe:ro \
  --entrypoint /probe/stage2_stream_entrypoint.sh \
  cbrowser-spike-runtime-stream:test

echo "=== Containers started ==="
docker ps --filter "name=cbrowser-spike-rtc-split" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
