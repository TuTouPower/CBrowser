#!/bin/bash
echo "=== Stopping cbrowser-spike-ime containers ==="
docker rm -f cbrowser-spike-ime-stream cbrowser-spike-ime-browser 2>/dev/null || true
docker volume rm -f cbrowser-spike-ime-x11 cbrowser-spike-ime-pulse 2>/dev/null || true
docker network rm cbrowser-spike-ime-net 2>/dev/null || true
echo "=== cbrowser-spike-ime cleanup complete ==="
