#!/bin/bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROBE_DIR="$(cd "$DIR/.." && pwd)"

# Clean previous containers/networks if any
echo "=== Cleaning old cbrowser-spike-rtc-split-* containers ==="
docker rm -f cbrowser-spike-rtc-split-coturn cbrowser-spike-rtc-split-stream cbrowser-spike-rtc-split-browser 2>/dev/null || true
docker network rm cbrowser-spike-rtc-split-net 2>/dev/null || true
docker volume rm -f cbrowser-spike-rtc-split-x11 cbrowser-spike-rtc-split-pulse 2>/dev/null || true

# Generate secure random secret only inside private scratch
SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
echo "$SECRET" > "$PROBE_DIR/probe_work/turn_secret.txt"
chmod 600 "$PROBE_DIR/probe_work/turn_secret.txt"

# Generate private 0600 configuration file to avoid CLI argv exposure
CONF_FILE="$PROBE_DIR/probe_work/turnserver.conf"
cat << EOF > "$CONF_FILE"
listening-port=3478
min-port=40000
max-port=40020
realm=cbrowser.local
use-auth-secret
static-auth-secret=${SECRET}
external-ip=172.29.0.10
verbose
EOF
chmod 600 "$CONF_FILE"

# Create network with fixed subnet
echo "=== Creating Docker network cbrowser-spike-rtc-split-net (172.29.0.0/16) ==="
docker network create --subnet=172.29.0.0/16 cbrowser-spike-rtc-split-net

# Start Coturn using mounted private config file (DO NOT pass -n which disables config file)
echo "=== Starting cbrowser-spike-rtc-split-coturn with private config ==="
docker run -d \
  --name cbrowser-spike-rtc-split-coturn \
  --network cbrowser-spike-rtc-split-net \
  --ip 172.29.0.10 \
  -p 127.0.0.1:13478:3478 \
  -p 127.0.0.1:13478:3478/udp \
  -p 127.0.0.1:40000-40020:40000-40020/udp \
  -v "$CONF_FILE":/etc/turnserver.conf:ro \
  --entrypoint /usr/bin/turnserver \
  coturn/coturn:latest \
  -c /etc/turnserver.conf \
  --log-file=stdout

echo "Waiting for coturn to be ready..."
sleep 2

echo "Coturn started. Image digest:"
docker inspect --format='{{index .RepoDigests 0}}' coturn/coturn:latest || true
