#!/bin/bash
set -x
echo "=== Stopping cbrowser-spike-rtc-split-* resources ==="
docker rm -f cbrowser-spike-rtc-split-stream cbrowser-spike-rtc-split-browser cbrowser-spike-rtc-split-coturn 2>/dev/null || true
docker volume rm -f cbrowser-spike-rtc-split-x11 cbrowser-spike-rtc-split-pulse 2>/dev/null || true
docker network rm cbrowser-spike-rtc-split-net 2>/dev/null || true
echo "=== Cleanup finished ==="
