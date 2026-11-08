#!/bin/bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"

# t044 AC-009: reuse a persistent shared uv cache and gate venv across
# runs. A changed gate-requirements.txt invalidates the venv stamp, so a
# warm cache logs no dependency download at all.
export UV_CACHE_DIR="${CBROWSER_GATE_UV_CACHE:-$REPO_ROOT/.scratch/gate_uv_cache}"
GATE_VENV="${CBROWSER_GATE_VENV:-$REPO_ROOT/.scratch/gate_venv}"
mkdir -p "$UV_CACHE_DIR"

if [ -n "${CBROWSER_GATE_SCRATCH:-}" ]; then
  SCRATCH="$CBROWSER_GATE_SCRATCH"
  CLEAN_SCRATCH=0
else
  SCRATCH="$(mktemp -d)"
  CLEAN_SCRATCH=1
  trap 'if [ "$CLEAN_SCRATCH" = "1" ]; then rm -rf "$SCRATCH"; fi' EXIT
fi
export TMPDIR="${TMPDIR:-$SCRATCH/tmp}"
mkdir -p "$TMPDIR"

cd "$REPO_ROOT"

EVIDENCE_DIR="${CBROWSER_GATE_EVIDENCE_DIR:-}"
GATE_PYTHON_MINOR="3.15"
PY="$GATE_VENV/bin/python"
WORKERS="${CBROWSER_GATE_WORKERS:-4}"
REQ_HASH="$(python3 -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' scripts/gate-requirements.txt)"
STAMP="$GATE_VENV/.requirements.sha256"

# Fixed order keeps evidence reproducible even though the backend and
# frontend groups run concurrently (t044 AC-004/AC-008).
SUITE_ORDER="requirements_check contract unit integration design_lint design_check frontend_test frontend_build"

prepare_env() {
  if [ -x "$PY" ] && [ "$(cat "$STAMP" 2>/dev/null || true)" = "$REQ_HASH" ]; then
    echo "gate env: reuse cached venv $GATE_VENV (no dependency download)"
    return 0
  fi
  echo "gate env: build venv $GATE_VENV (python $GATE_PYTHON_MINOR)"
  uv venv --python "$GATE_PYTHON_MINOR" "$GATE_VENV"
  uv pip install --python "$PY" -r scripts/gate-requirements.txt
  printf '%s' "$REQ_HASH" > "$STAMP"
}

# run_gate_suite <target> <pythonpath> <junit> <basetemp> [extra pytest args]
# Phase A runs everything not marked `serial` on WORKERS xdist workers;
# phase B runs only `serial` items in a single process, so timing-sensitive
# cases never overlap any other case (t044 AC-002/AC-007). The two JUnit
# files are merged so the suite still reports every case (AC-001/AC-004).
run_gate_suite() {
  local target="$1" pp="$2" junit="$3" basetemp="$4"
  shift 4
  local dir a b c1=0 c2=0
  dir="$(dirname "$junit")"
  mkdir -p "$dir" "$basetemp/parallel" "$basetemp/serial"
  a="$dir/.phase_parallel.xml"
  b="$dir/.phase_serial.xml"
  env PYTHONPATH="$pp" "$PY" -m pytest "$target" -q -n "$WORKERS" \
    -m "not serial" --basetemp="$basetemp/parallel" --junitxml="$a" "$@" || c1=$?
  env PYTHONPATH="$pp" "$PY" -m pytest "$target" -q -n 0 \
    -m "serial" --basetemp="$basetemp/serial" --junitxml="$b" "$@" || c2=$?
  "$PY" scripts/merge_junit.py --output "$junit" "$a" "$b"
  rm -f "$a" "$b"
  if [ "$c1" != 0 ]; then return "$c1"; fi
  if [ "$c2" != 0 ] && [ "$c2" != 5 ]; then return "$c2"; fi
  return 0
}

# run_suite <name> <display command> <command...>
# Each suite records its own TSV fragment; finish_evidence concatenates
# them in SUITE_ORDER so concurrent writes cannot scramble the manifest.
run_suite() {
  local name="$1" display="$2"
  shift 2
  local raw_log="$EVIDENCE_DIR/logs/$name.raw.log"
  local code=0
  echo "=== suite: $name: $display"
  "$@" >"$raw_log" 2>&1 || code=$?
  "$PY" scripts/redact_evidence.py <"$raw_log" >"$EVIDENCE_DIR/logs/$name.log"
  rm -f "$raw_log"
  printf '%s\t%s\t%s\n' "$name" "$code" "$display" > "$EVIDENCE_DIR/suites.d/$name.tsv"
  echo "=== suite: $name: exit $code"
}

# t044 AC-011: in E2E-required mode every runtime image's installed
# package set must match the exported uv.lock requirements.
verify_image_packages_all() {
  local pairs=(
    "CBROWSER_RUNTIME_TEST_IMAGE:config/docker/browser_runtime/requirements.txt"
    "CBROWSER_STREAM_TEST_IMAGE:config/docker/stream_runtime/requirements.txt"
    "CBROWSER_GATEWAY_IMAGE:config/docker/gateway_runtime/requirements.txt"
    "CBROWSER_SUPERVISOR_TEST_IMAGE:config/docker/supervisor_runtime/requirements.txt"
    "CBROWSER_API_TEST_IMAGE:config/docker/api_runtime/requirements.txt"
  )
  local rc=0 pair var req id
  for pair in "${pairs[@]}"; do
    var="${pair%%:*}"
    req="${pair#*:}"
    id="${!var:-}"
    if [ -n "$id" ]; then
      "$PY" scripts/verify_image_packages.py --image "$id" --requirements "$req" || rc=1
    fi
  done
  return "$rc"
}

# E2E runs a single-process collection preflight first. In required mode a
# missing prerequisite fails closed once, with an itemized message, instead
# of crashing each xdist worker (t044 AC-005) and scrambling failure
# attribution in the evidence (AC-004).
run_e2e_suite() {
  local junit="$1" basetemp="$2"
  export CBROWSER_E2E_REQUIRED=1
  if ! env PYTHONPATH=src/backend:tests/fixtures "$PY" -m pytest tests/e2e \
      --collect-only -q -n 0; then
    return 2
  fi
  run_gate_suite tests/e2e src/backend:tests/fixtures "$junit" "$basetemp"
}

finish_evidence() {
  local name f code GATE_FAILURES=0
  : > "$EVIDENCE_DIR/suites.tsv"
  for name in $SUITE_ORDER; do
    f="$EVIDENCE_DIR/suites.d/$name.tsv"
    if [ -f "$f" ]; then cat "$f" >> "$EVIDENCE_DIR/suites.tsv"; fi
  done
  for f in "$EVIDENCE_DIR"/suites.d/*.tsv; do
    [ -f "$f" ] || continue
    code="$(cut -f2 "$f")"
    if [ "$code" != "0" ]; then GATE_FAILURES=1; fi
  done
  "$PY" scripts/gate_evidence_manifest.py \
    --evidence-dir "$EVIDENCE_DIR" --suites-tsv "$EVIDENCE_DIR/suites.tsv"
  echo "gate evidence: manifest at $EVIDENCE_DIR/manifest.json"
  return "$GATE_FAILURES"
}

# ---------------- environment (t044 AC-009) ----------------
if [ -n "$EVIDENCE_DIR" ]; then
  mkdir -p "$EVIDENCE_DIR/logs" "$EVIDENCE_DIR/junit" "$EVIDENCE_DIR/suites.d"
  : > "$EVIDENCE_DIR/logs/environment.raw.log"
  if ! prepare_env >>"$EVIDENCE_DIR/logs/environment.raw.log" 2>&1; then
    if ! "$PY" scripts/redact_evidence.py <"$EVIDENCE_DIR/logs/environment.raw.log" >"$EVIDENCE_DIR/logs/environment.log" 2>/dev/null; then
      echo "environment log redaction failed; raw log withheld from evidence" > "$EVIDENCE_DIR/logs/environment.log"
    fi
    rm -f "$EVIDENCE_DIR/logs/environment.raw.log"
    printf 'environment\t1\tuv venv + uv pip install -r scripts/gate-requirements.txt\n' > "$EVIDENCE_DIR/suites.tsv"
    "$PY" scripts/gate_evidence_manifest.py --evidence-dir "$EVIDENCE_DIR" --suites-tsv "$EVIDENCE_DIR/suites.tsv" 2>/dev/null \
      || python3 scripts/gate_evidence_manifest.py --evidence-dir "$EVIDENCE_DIR" --suites-tsv "$EVIDENCE_DIR/suites.tsv"
    echo "gate evidence: environment build failed; see $EVIDENCE_DIR/manifest.json" >&2
    exit 1
  fi
  if ! "$PY" scripts/redact_evidence.py <"$EVIDENCE_DIR/logs/environment.raw.log" >"$EVIDENCE_DIR/logs/environment.log"; then
    echo "environment log redaction failed; raw log withheld from evidence" > "$EVIDENCE_DIR/logs/environment.log"
    echo "gate evidence: warning: environment log redaction failed; raw log withheld" >&2
  fi
  rm -f "$EVIDENCE_DIR/logs/environment.raw.log"
else
  prepare_env
fi

if [ "${CBROWSER_RUN_E2E:-0}" = "1" ]; then
  SUITE_ORDER="$SUITE_ORDER image_packages e2e"
fi

# The product CBROWSER_FONTS_DIR must not leak into any gate suite: when
# set, the API binds a default font set to every new Profile and the
# Supervisor container cannot see that host directory, so real-stack E2E
# starts fail with font_set_unavailable. E2E reads the same persistent
# directory through the dedicated CBROWSER_E2E_FONTS_DIR instead.
unset CBROWSER_FONTS_DIR

# ---------------- evidence mode: concurrent groups (t044 AC-008) ----------------
if [ -n "$EVIDENCE_DIR" ]; then
  run_suite requirements_check "scripts/generate_requirements.sh --check" \
    bash scripts/generate_requirements.sh --check

  backend_group() {
    run_suite contract "$PY -m pytest .repo_template/tests -q -m contract" \
      "$PY" -m pytest .repo_template/tests -q -m contract \
      --junitxml="$EVIDENCE_DIR/junit/contract.xml"
    run_suite unit "env PYTHONPATH=src/backend pytest tests/unit -q -n $WORKERS" \
      run_gate_suite tests/unit src/backend "$EVIDENCE_DIR/junit/unit.xml" "$SCRATCH/basetemp/unit"
    run_suite integration "env PYTHONPATH=src/backend pytest tests/integration -q -n $WORKERS" \
      run_gate_suite tests/integration src/backend "$EVIDENCE_DIR/junit/integration.xml" "$SCRATCH/basetemp/integration"
  }
  frontend_group() {
    run_suite design_lint "npm run design:lint --prefix src/frontend" npm run design:lint --prefix src/frontend
    run_suite design_check "npm run design:check --prefix src/frontend" npm run design:check --prefix src/frontend
    run_suite frontend_test "npm test --prefix src/frontend" npm test --prefix src/frontend
    run_suite frontend_build "npm run build --prefix src/frontend" npm run build --prefix src/frontend
  }
  backend_group &
  pid_backend=$!
  frontend_group &
  pid_frontend=$!
  wait "$pid_backend" || true
  wait "$pid_frontend" || true

  if [ "${CBROWSER_RUN_E2E:-0}" = "1" ]; then
    run_suite image_packages "verify_image_packages.py per runtime image" \
      verify_image_packages_all
    run_suite e2e "env PYTHONPATH=src/backend:tests/fixtures pytest tests/e2e -q -n $WORKERS" \
      run_e2e_suite "$EVIDENCE_DIR/junit/e2e.xml" "$SCRATCH/basetemp/e2e"
  fi

  if finish_evidence; then exit 0; else exit 1; fi
fi

# ---------------- default mode: serial fail-fast ----------------
bash scripts/generate_requirements.sh --check
"$PY" -m pytest .repo_template/tests -q -m contract
run_gate_suite tests/unit src/backend "$SCRATCH/junit/unit.xml" "$SCRATCH/basetemp/unit"
run_gate_suite tests/integration src/backend "$SCRATCH/junit/integration.xml" "$SCRATCH/basetemp/integration"
npm run design:lint --prefix src/frontend
npm run design:check --prefix src/frontend
npm test --prefix src/frontend
npm run build --prefix src/frontend

if [ "${CBROWSER_RUN_E2E:-0}" = "1" ]; then
  run_e2e_suite "$SCRATCH/junit/e2e.xml" "$SCRATCH/basetemp/e2e"
fi
