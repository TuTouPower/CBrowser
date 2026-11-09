#!/bin/bash
# Run the t032 probe in Linux arm64, separately from host Docker/Chrome E2E.
set -uo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"

REQUIRED_NODE_IDS=(
  "tests/e2e/test_automation_compatibility_probe_e2e.py::test_t032_probe_chain_and_dialog_recheck"
  "tests/e2e/test_automation_compatibility_probe_e2e.py::test_t032_probe_levels_recheck"
)

: "${CBROWSER_PROBE_TEST_IMAGE:?Set the probe image immutable sha256 ID}"
: "${CBROWSER_T029_ENGINE_CACHE:?Set the Linux arm64 engine cache directory}"
: "${CBROWSER_T029_REPORT_DIR:?Set an empty evidence directory}"

mkdir -p "$CBROWSER_T029_REPORT_DIR"
report_dir="$(cd "$CBROWSER_T029_REPORT_DIR" && pwd)"
preflight_file="$report_dir/preflight.txt"
: > "$preflight_file"
add_problem() { printf '%s\n' "$1" >> "$preflight_file"; }

version="${CBROWSER_T029_TARGET_ENGINE_VERSION:-146.0.7680.177.3}"
if [[ ! "$CBROWSER_PROBE_TEST_IMAGE" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  add_problem "probe image must be an immutable sha256 ID"
fi
architecture="$(
  docker image inspect --format '{{.Os}}/{{.Architecture}}' \
    "$CBROWSER_PROBE_TEST_IMAGE" 2>/dev/null || true
)"
[ "$architecture" = "linux/arm64" ] || \
  add_problem "expected linux/arm64, got ${architecture:-unresolvable}"
[ -d "$CBROWSER_T029_ENGINE_CACHE" ] || \
  add_problem "engine cache directory missing"
[ -x "$CBROWSER_T029_ENGINE_CACHE/chromium-$version/chrome" ] || \
  add_problem "selected engine missing: chromium-$version/chrome"
other_files="$(ls -A "$report_dir" | grep -v -x 'preflight.txt' || true)"
[ -z "$other_files" ] || add_problem "evidence directory must be empty"
if [ "$architecture" = "linux/arm64" ]; then
  runtime_probe="$(
    docker run --rm --entrypoint /bin/sh "$CBROWSER_PROBE_TEST_IMAGE" \
      -c 'printf "xvfb=%s\n" "$(command -v Xvfb || true)"; printf "uid=%s\n" "$(id -u cbrowser || true)"' \
      2>/dev/null || true
  )"
  echo "$runtime_probe" | grep -q '^xvfb=.' || \
    add_problem "Xvfb missing in probe image"
  echo "$runtime_probe" | grep -q '^uid=.' || \
    add_problem "probe image missing cbrowser user (permissions)"
fi

docker image inspect \
  --format '{"id":{{json .Id}},"os":{{json .Os}},"architecture":{{json .Architecture}}}' \
  "$CBROWSER_PROBE_TEST_IMAGE" > "$report_dir/image.json" 2>/dev/null || true

if [ -s "$preflight_file" ]; then
  echo "Real-engine probe preflight missing prerequisites:" >&2
  while IFS= read -r problem; do echo "  - $problem" >&2; done < "$preflight_file"
  if [ "${CBROWSER_REQUIRE_REAL_ENGINE:-0}" = "1" ]; then
    exit 2
  fi
  echo "real_engine: NOT_RUN (incomplete preflight; set CBROWSER_REQUIRE_REAL_ENGINE=1 to fail closed)" >&2
  exit 0
fi

selected_file="$report_dir/selected.txt"
printf '%s\n' "${REQUIRED_NODE_IDS[@]}" > "$selected_file"

name="cbrowser-t032-probe-$$"
mkdir -p "$REPO_ROOT/.scratch"
if ! snapshot="$(mktemp -d "$REPO_ROOT/.scratch/t032_probe_source_XXXXXX")"; then
  echo "cannot create source snapshot" >&2
  exit 2
fi
interrupted_file="$report_dir/interrupted"

cleanup() {
  docker stop -t 5 "$name" >/dev/null 2>&1 || true
  rm -rf "$snapshot"
}
on_interrupt() {
  : > "$interrupted_file"
  cleanup
  exit 130
}
trap cleanup EXIT
trap on_interrupt INT TERM

python3 - "$REPO_ROOT" "$snapshot" <<'PY_SNAPSHOT' || exit 2
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

cache_dir="$(cd "$CBROWSER_T029_ENGINE_CACHE" && pwd)"
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
  probe "$(id -u)" python -m pytest "${REQUIRED_NODE_IDS[@]}" -q -rs \
  -o cache_dir=/tmp/pytest-cache --basetemp=/evidence/pytest \
  --junitxml=/evidence/probe.xml
exit_code=$?

interrupted_args=()
if [ -f "$interrupted_file" ]; then
  interrupted_args=(--interrupted)
fi
# NOTE: the expansion below must stay in the guarded form: expanding an
# empty array bare is an unbound-variable error on bash 3.2 (macOS
# /bin/bash) under `set -u`.
python3 "$REPO_ROOT/scripts/automation_probe_evidence.py" \
  --junit "$report_dir/probe.xml" \
  --image-json "$report_dir/image.json" \
  --exit-code "$exit_code" \
  --selected "$selected_file" \
  --preflight "$preflight_file" \
  --log image.json --log probe.xml --log evidence.json \
  --output "$report_dir/evidence.json" \
  ${interrupted_args[@]+"${interrupted_args[@]}"}
evidence_rc=$?
if [ "$evidence_rc" -eq 0 ]; then
  echo "real_engine: all_passed (evidence.json)"
else
  echo "real_engine: NOT all_passed; see evidence.json and image.json" >&2
fi
exit "$evidence_rc"
