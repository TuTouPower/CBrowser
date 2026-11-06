#!/bin/bash
# Regenerate every image/gate requirements.txt from the single uv.lock source.
# Usage: scripts/generate_requirements.sh [--check]
#   (no args)  write the generated files in place
#   --check    compare in place, exit 1 on drift (developer/CI helper)
# The gate's authoritative drift check is
# tests/unit/test_t034_dependency_lock.py, which runs in the unit suite;
# this script is the regeneration entry point and shares the same export
# arguments with that test.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# The lock is resolved for Python 3.15 (the same minor as the runtime images).
# uv export is deterministic from uv.lock; no network access is required.
export UV_OFFLINE=1
export UV_NO_SYNC=1
# uv needs an interpreter satisfying requires-python to export; resolve it
# from the repo-pinned .mise.toml rather than hard-coding a local path.
UV_PYTHON="$(mise which python)" || {
    echo "mise python (pinned in .mise.toml) unavailable; install Python 3.15 first" >&2
    exit 1
}
: "${UV_PYTHON:?mise returned no python interpreter}"
export UV_PYTHON

REQ_GROUPS=(
    "api:config/docker/api_runtime/requirements.txt"
    "gateway:config/docker/gateway_runtime/requirements.txt"
    "supervisor:config/docker/supervisor_runtime/requirements.txt"
    "browser:config/docker/browser_runtime/requirements.txt"
    "stream:config/docker/stream_runtime/requirements.txt"
    "gate:scripts/gate-requirements.txt"
)

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

rc=0
for entry in "${REQ_GROUPS[@]}"; do
    group="${entry%%:*}"
    target="${entry#*:}"
    out="$tmp/$(echo "$target" | tr '/' '_')"
    uv export --only-group "$group" \
        --no-hashes --no-header --no-emit-project --no-emit-workspace \
        --format requirements.txt > "$out"
    if [ "${1:-}" = "--check" ]; then
        if ! diff -q "$target" "$out" >/dev/null 2>&1; then
            echo "requirements drift: $target is not uv.lock export of group '$group'" >&2
            diff -u "$target" "$out" | head -20 >&2 || true
            rc=1
        else
            echo "requirements ok: $target (group '$group')"
        fi
    else
        mkdir -p "$(dirname "$target")"
        cp "$out" "$target"
        echo "wrote $target (group '$group')"
    fi
done
exit "$rc"
