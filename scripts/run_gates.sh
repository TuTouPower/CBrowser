#!/bin/bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
if [ -n "${CBROWSER_GATE_SCRATCH:-}" ]; then
  SCRATCH="$CBROWSER_GATE_SCRATCH"
  CLEAN_SCRATCH=0
else
  SCRATCH="$(mktemp -d)"
  CLEAN_SCRATCH=1
  trap 'if [ "$CLEAN_SCRATCH" = "1" ]; then rm -rf "$SCRATCH"; fi' EXIT
fi
export TMPDIR="${TMPDIR:-$SCRATCH/tmp}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$SCRATCH/uv_cache}"
mkdir -p "$TMPDIR" "$UV_CACHE_DIR"

cd "$REPO_ROOT"

pytest .repo_template/tests -q -m contract
PYTHONPATH=src:src/backend uv run --no-project --python ">=3.12" \
  --with pytest --with pytest-asyncio --with fastapi --with pydantic \
  --with httpx --with websockets --with "cloakbrowser==0.6.4" \
  python -m pytest src/backend/tests -q
PYTHONPATH=src/backend uv run --no-project --python ">=3.12" \
  --with pytest --with pytest-asyncio --with httpx --with aiosqlite \
  --with sqlalchemy --with alembic --with fastapi --with pydantic \
  --with uvicorn --with jsonschema --with websockets --with "cloakbrowser==0.6.4" \
  --with docker --with aiohttp --with argon2-cffi python -m pytest tests/unit -q
PYTHONPATH=src/backend uv run --no-project --python ">=3.12" \
  --with pytest --with pytest-asyncio --with httpx --with aiosqlite \
  --with "sqlalchemy[asyncio]" --with alembic --with fastapi --with pydantic \
  --with uvicorn --with jsonschema --with docker --with aiohttp \
  --with argon2-cffi --with websockets python -m pytest tests/integration -q
NODE_OPTIONS=--no-experimental-webstorage npm test --prefix src/frontend
npm run build --prefix src/frontend

if [ "${CBROWSER_RUN_E2E:-0}" = "1" ]; then
  export CBROWSER_E2E_REQUIRED=1
  PYTHONPATH=src/backend:tests/fixtures uv run --no-project --python ">=3.12" \
    --with pytest --with pytest-asyncio --with playwright --with docker \
    --with httpx --with aiohttp --with pydantic --with websockets \
    --with fastapi --with uvicorn --with "sqlalchemy[asyncio]" --with aiosqlite \
    --with alembic --with argon2-cffi --with jsonschema --with "cloakbrowser==0.6.4" \
    python -m pytest tests/e2e -q --basetemp="$SCRATCH/e2e"
fi
