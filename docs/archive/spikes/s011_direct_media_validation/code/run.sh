#!/bin/bash
set -euo pipefail

: "${CBROWSER_RUNTIME_TEST_IMAGE:?Provide the immutable Browser runtime image ID}"
: "${CBROWSER_STREAM_TEST_IMAGE:?Provide the immutable Stream runtime image ID}"
: "${CBROWSER_RUNTIME_ENGINE_CACHE:?Provide an initialized Linux engine cache path}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
SCRATCH="${SCRATCH:-$REPO_ROOT/.scratch/s011}"
mkdir -p "$SCRATCH/tmp" "$SCRATCH/basetemp" "$SCRATCH/cache"
export TMPDIR="$SCRATCH/tmp"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$REPO_ROOT/.scratch/uv_cache}"

PYTHONPATH="$REPO_ROOT/src/backend" uv run --no-project --python ">=3.12" \
  --with pytest --with pytest-asyncio --with playwright --with docker \
  --with httpx --with aiohttp --with pydantic --with websockets \
  python -m pytest "$REPO_ROOT/docs/spikes/s011_direct_media_validation/code/direct_media_probe.py" \
  -q --basetemp="$SCRATCH/basetemp" -o cache_dir="$SCRATCH/cache"
