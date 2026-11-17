#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Cleaning up any old cbrowser-spike-media resources ==="
docker rm -f cbrowser-spike-media-stream cbrowser-spike-media-browser 2>/dev/null || true
docker volume rm -f cbrowser-spike-media-x11 cbrowser-spike-media-pulse 2>/dev/null || true
docker network rm cbrowser-spike-media-net 2>/dev/null || true

echo "=== Creating isolated network and volumes ==="
docker network create cbrowser-spike-media-net
docker volume create cbrowser-spike-media-x11
docker volume create cbrowser-spike-media-pulse

echo "=== Starting cbrowser-spike-media-browser ==="
docker run -d \
  --name cbrowser-spike-media-browser \
  --network cbrowser-spike-media-net \
  --ipc shareable \
  --shm-size 1g \
  -v cbrowser-spike-media-x11:/tmp/.X11-unix \
  -v cbrowser-spike-media-pulse:/tmp/pulse \
  -v "$DIR/entrypoint_browser.sh":/entrypoint_browser.sh:ro \
  --entrypoint /entrypoint_browser.sh \
  cbrowser-spike-runtime-browser:test

echo "=== Starting cbrowser-spike-media-stream ==="
docker run -d \
  --name cbrowser-spike-media-stream \
  --network cbrowser-spike-media-net \
  --ipc container:cbrowser-spike-media-browser \
  -p 127.0.0.1:18081:18081 \
  -p 127.0.0.1:30006:30006/udp \
  -v cbrowser-spike-media-x11:/tmp/.X11-unix \
  -v cbrowser-spike-media-pulse:/tmp/pulse \
  -v "$DIR/entrypoint_stream.sh":/entrypoint_stream.sh:ro \
  --entrypoint /entrypoint_stream.sh \
  cbrowser-spike-runtime-stream:test

echo "=== Containers started ==="
docker ps --filter "name=cbrowser-spike-media" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
