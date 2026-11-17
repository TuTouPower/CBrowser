#!/bin/bash
echo "=== Stopping cbrowser-spike-media containers ==="
docker rm -f cbrowser-spike-media-stream cbrowser-spike-media-browser 2>/dev/null || true
docker volume rm -f cbrowser-spike-media-x11 cbrowser-spike-media-pulse 2>/dev/null || true
docker network rm cbrowser-spike-media-net 2>/dev/null || true
echo "=== cbrowser-spike-media cleanup complete ==="
