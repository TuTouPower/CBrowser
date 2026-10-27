#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Cleaning up any old cbrowser-spike-ime resources ==="
docker rm -f cbrowser-spike-ime-stream cbrowser-spike-ime-browser 2>/dev/null || true
docker volume rm -f cbrowser-spike-ime-x11 cbrowser-spike-ime-pulse 2>/dev/null || true
docker network rm cbrowser-spike-ime-net 2>/dev/null || true

echo "=== Creating isolated network and volumes ==="
docker network create cbrowser-spike-ime-net
docker volume create cbrowser-spike-ime-x11
docker volume create cbrowser-spike-ime-pulse

echo "=== Starting cbrowser-spike-ime-browser ==="
docker run -d \
  --name cbrowser-spike-ime-browser \
  --network cbrowser-spike-ime-net \
  --ipc shareable \
  --shm-size 1g \
  -v cbrowser-spike-ime-x11:/tmp/.X11-unix \
  -v cbrowser-spike-ime-pulse:/tmp/pulse \
  -v "$DIR/entrypoint_browser.sh":/entrypoint_browser.sh:ro \
  --entrypoint /entrypoint_browser.sh \
  cbrowser-spike-runtime-browser:test

echo "=== Starting cbrowser-spike-ime-stream ==="
docker run -d \
  --name cbrowser-spike-ime-stream \
  --network cbrowser-spike-ime-net \
  --ipc container:cbrowser-spike-ime-browser \
  -p 127.0.0.1:18095:18095 \
  -p 127.0.0.1:30018:30018/udp \
  -v cbrowser-spike-ime-x11:/tmp/.X11-unix \
  -v cbrowser-spike-ime-pulse:/tmp/pulse \
  -v "$DIR/entrypoint_stream.sh":/entrypoint_stream.sh:ro \
  --entrypoint /entrypoint_stream.sh \
  cbrowser-spike-runtime-stream:test

echo "=== Containers started ==="
docker ps --filter "name=cbrowser-spike-ime" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
