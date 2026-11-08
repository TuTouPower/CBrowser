#!/bin/sh
set -eu
CODE_ROOT="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$CODE_ROOT/../../../.." && pwd)"
ENGINE_CACHE="$(cd "$REPO_ROOT/../.cbrowser/engine-cache/chromium-146.0.7680.177.3" && pwd)"
IMAGE="sha256:1b75e318a2b7e6e0fdeba6d784773dd4848d2f91e7bba8650ded22d24c675513"
docker run --rm \
  --entrypoint sh \
  -v "$ENGINE_CACHE:/data/engine-cache/chromium-146.0.7680.177.3:ro" \
  -v "$CODE_ROOT:/probe:ro" \
  "$IMAGE" \
  -c "xvfb-run -a -s '-screen 0 1280x800x24' python3 /probe/probe_xvfb.py"
