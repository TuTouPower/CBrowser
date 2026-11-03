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

# Build the gate environment once from the pinned dependency lock
# (scripts/gate-requirements.txt, t024 AC-009/A30).  Every suite below runs
# in this single environment, so a gate run is reproducible from an empty
# cache and no longer depends on live resolution of unpinned package sets.
VENV="$SCRATCH/venv"
uv venv --python 3.12 "$VENV"
uv pip install --python "$VENV/bin/python" -r scripts/gate-requirements.txt
PY="$VENV/bin/python"

"$PY" -m pytest .repo_template/tests -q -m contract
PYTHONPATH=src/backend "$PY" -m pytest tests/unit -q
PYTHONPATH=src/backend "$PY" -m pytest tests/integration -q
NODE_OPTIONS=--no-experimental-webstorage npm test --prefix src/frontend
npm run build --prefix src/frontend

if [ "${CBROWSER_RUN_E2E:-0}" = "1" ]; then
  export CBROWSER_E2E_REQUIRED=1
  PYTHONPATH=src/backend:tests/fixtures "$PY" -m pytest tests/e2e -q --basetemp="$SCRATCH/e2e"
fi
