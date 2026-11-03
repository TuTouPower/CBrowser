#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."

HTTPS_PORT="${CBROWSER_HTTPS_PORT:-8443}"
export CBROWSER_HTTPS_PORT="$HTTPS_PORT"
export CBROWSER_PUBLIC_ORIGIN="${CBROWSER_PUBLIC_ORIGIN:-https://127.0.0.1:$HTTPS_PORT}"

mkdir -p config/deploy/secrets data/v2/{profiles,runtime,runtime-events,artifacts,spool,control,engine-cache}
for name in supervisor_key agent_key gateway_key gateway_api_key admin_password; do
  file="config/deploy/secrets/$name"
  [ -s "$file" ] || openssl rand -hex 32 > "$file"
  chmod 600 "$file"
done
mkdir -p data/v2/engine-cache/geoip

docker build -t cbrowser-browser:deploy -f config/docker/browser_runtime/Dockerfile .
docker build -t cbrowser-stream:deploy -f config/docker/stream_runtime/Dockerfile .
docker build -t cbrowser-supervisor:deploy -f config/docker/supervisor_runtime/Dockerfile .
docker build -t cbrowser-gateway:deploy -f config/docker/gateway_runtime/Dockerfile .
docker build -t cbrowser-api:deploy -f config/docker/api_runtime/Dockerfile .

docker build -t cbrowser-api:deploy -f config/docker/api_runtime/Dockerfile .

export CBROWSER_BROWSER_IMAGE="$(docker image inspect --format '{{.Id}}' cbrowser-browser:deploy)"
export CBROWSER_STREAM_IMAGE="$(docker image inspect --format '{{.Id}}' cbrowser-stream:deploy)"
export CBROWSER_SUPERVISOR_IMAGE="$(docker image inspect --format '{{.Id}}' cbrowser-supervisor:deploy)"

cat > config/deploy/compose.env <<ENV
CBROWSER_HTTPS_PORT=$CBROWSER_HTTPS_PORT
CBROWSER_PUBLIC_ORIGIN=$CBROWSER_PUBLIC_ORIGIN
CBROWSER_BROWSER_IMAGE=$CBROWSER_BROWSER_IMAGE
CBROWSER_STREAM_IMAGE=$CBROWSER_STREAM_IMAGE
CBROWSER_SUPERVISOR_IMAGE=$CBROWSER_SUPERVISOR_IMAGE
ENV
docker compose --env-file config/deploy/compose.env -f compose.yaml up -d
echo "CBrowser: https://127.0.0.1:$HTTPS_PORT"
echo "Compose env: config/deploy/compose.env"
echo "Admin password: $(cat config/deploy/secrets/admin_password)"
