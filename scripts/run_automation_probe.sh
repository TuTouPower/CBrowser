#!/bin/bash
# Run the t032 probe in Linux arm64, separately from host Docker/Chrome E2E.
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
: "${CBROWSER_PROBE_TEST_IMAGE:?Set the probe image immutable sha256 ID}"
: "${CBROWSER_T029_ENGINE_CACHE:?Set the Linux arm64 engine cache directory}"
: "${CBROWSER_T029_REPORT_DIR:?Set an empty evidence directory}"
if [[ ! "$CBROWSER_PROBE_TEST_IMAGE" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo 'Probe image must be an immutable sha256 ID' >&2
  exit 2
fi
architecture="$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$CBROWSER_PROBE_TEST_IMAGE")"
[ "$architecture" = linux/arm64 ] || { echo "Expected linux/arm64, got $architecture" >&2; exit 2; }
version="${CBROWSER_T029_TARGET_ENGINE_VERSION:-146.0.7680.177.3}"
[ -x "$CBROWSER_T029_ENGINE_CACHE/chromium-$version/chrome" ] || { echo 'Selected engine missing' >&2; exit 2; }
mkdir -p "$CBROWSER_T029_REPORT_DIR"
report_dir="$(cd "$CBROWSER_T029_REPORT_DIR" && pwd)"
[ -z "$(ls -A "$report_dir")" ] || { echo 'Evidence directory must be empty' >&2; exit 2; }
cache_dir="$(cd "$CBROWSER_T029_ENGINE_CACHE" && pwd)"
docker image inspect --format '{"id":{{json .Id}},"os":{{json .Os}},"architecture":{{json .Architecture}}}' "$CBROWSER_PROBE_TEST_IMAGE" > "$report_dir/image.json"
name="cbrowser-t032-probe-$$"
mkdir -p "$REPO_ROOT/.scratch"
snapshot="$(mktemp -d "$REPO_ROOT/.scratch/t032_probe_source_XXXXXX")"
trap 'docker stop -t 5 "$name" >/dev/null 2>&1 || true; rm -rf "$snapshot"' EXIT
python3 - "$REPO_ROOT" "$snapshot" <<'PY_SNAPSHOT'
import pathlib, shutil, subprocess, sys
root, target = map(pathlib.Path, sys.argv[1:])
paths = subprocess.check_output([
    "git", "ls-files", "-z", "--", "src/backend", "tests", "scripts",
    "config", "schemas", "assets", "pyproject.toml",
], cwd=root).decode().split(chr(0))
for name in filter(None, paths):
    source = root / name
    if source.is_file():
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination, follow_symlinks=False)
PY_SNAPSHOT
# No Docker socket or production data is mounted. Production Python components
# execute in the probe's loopback topology; this is distinct from Stream E2E.
docker run --rm --init --name "$name" --platform linux/arm64 --shm-size=1g \
  --mount "type=bind,src=$snapshot,dst=/repo,readonly" \
  --mount "type=bind,src=$cache_dir,dst=/data/engine-cache,readonly" \
  --mount "type=bind,src=$report_dir,dst=/evidence" \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/repo/src/backend:/repo/tests/fixtures \
  -e CBROWSER_T029_ENGINE_CACHE=/data/engine-cache \
  -e "CBROWSER_T029_TARGET_ENGINE_VERSION=$version" \
  -e "CBROWSER_PROBE_CHROMIUM_EXECUTABLE=/data/engine-cache/chromium-$version/chrome" \
  -e CBROWSER_PROBE_CONTAINER_RUNTIME=1 \
  -e CBROWSER_T029_PROBE_E2E=1 -e T029_SAMPLES=5 \
  --workdir /repo --entrypoint /bin/sh "$CBROWSER_PROBE_TEST_IMAGE" \
  -c 'set -e; [ "$(id -u cbrowser)" = "$1" ] || usermod -u "$1" cbrowser; shift; exec runuser -u cbrowser -- "$@"' \
  probe "$(id -u)" python -m pytest tests/e2e/test_automation_compatibility_probe_e2e.py -q -rs \
  -o cache_dir=/tmp/pytest-cache --basetemp=/evidence/pytest \
  --junitxml=/evidence/probe.xml "$@"
