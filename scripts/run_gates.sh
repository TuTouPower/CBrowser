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

# Evidence mode (t028 AC-006): when CBROWSER_GATE_EVIDENCE_DIR names a
# directory, every suite runs to completion even if an earlier suite
# fails; per-suite commands, exit codes, JUnit files and redacted logs
# are retained in that directory with a manifest.json index, and the
# script exits non-zero if any suite failed.  Without the variable the
# historical behaviour is unchanged: set -e stops at the first failure
# and the scratch directory is deleted by the trap above.
EVIDENCE_DIR="${CBROWSER_GATE_EVIDENCE_DIR:-}"

# Build the gate environment once from the pinned dependency lock
# (scripts/gate-requirements.txt, t024 AC-009/A30).  Every suite below runs
# in this single environment, so a gate run is reproducible from an empty
# cache and no longer depends on live resolution of unpinned package sets.
VENV="$SCRATCH/venv"
if [ -n "$EVIDENCE_DIR" ]; then
  mkdir -p "$EVIDENCE_DIR/logs" "$EVIDENCE_DIR/junit"
  : > "$EVIDENCE_DIR/suites.tsv"
  build_ok=1
  uv venv --python 3.12 "$VENV" >"$EVIDENCE_DIR/logs/environment.raw.log" 2>&1 || build_ok=0
  if [ "$build_ok" = 1 ]; then
    uv pip install --python "$VENV/bin/python" -r scripts/gate-requirements.txt >>"$EVIDENCE_DIR/logs/environment.raw.log" 2>&1 || build_ok=0
  fi
  # The retained environment log goes through the same redaction as
  # every suite log before it lands in the evidence directory.  If
  # redaction itself fails, the raw log is withheld (explicit
  # placeholder) rather than silently retained unredacted.
  if ! python3 scripts/redact_evidence.py <"$EVIDENCE_DIR/logs/environment.raw.log" >"$EVIDENCE_DIR/logs/environment.log"; then
    printf 'environment log redaction failed; raw log withheld from evidence\n' >"$EVIDENCE_DIR/logs/environment.log"
    echo "gate evidence: warning: environment log redaction failed; raw log withheld" >&2
  fi
  rm -f "$EVIDENCE_DIR/logs/environment.raw.log"
  if [ "$build_ok" = 0 ]; then
    printf 'environment\t1\tuv venv + uv pip install -r scripts/gate-requirements.txt\n' >> "$EVIDENCE_DIR/suites.tsv"
    "$VENV/bin/python" scripts/gate_evidence_manifest.py \
      --evidence-dir "$EVIDENCE_DIR" --suites-tsv "$EVIDENCE_DIR/suites.tsv" \
      2>/dev/null || python3 scripts/gate_evidence_manifest.py \
      --evidence-dir "$EVIDENCE_DIR" --suites-tsv "$EVIDENCE_DIR/suites.tsv"
    echo "gate evidence: environment build failed; see $EVIDENCE_DIR/manifest.json" >&2
    exit 1
  fi
else
  uv venv --python 3.12 "$VENV"
  uv pip install --python "$VENV/bin/python" -r scripts/gate-requirements.txt
fi
PY="$VENV/bin/python"

if [ -n "$EVIDENCE_DIR" ]; then
  GATE_FAILURES=0

  # run_suite <name> <command...>: run one suite, retain its redacted
  # log, and record name/exit code/command for the manifest.  Never
  # aborts the remaining suites.
  run_suite() {
    local name="$1"
    shift
    local raw_log="$EVIDENCE_DIR/logs/$name.raw.log"
    local code=0
    echo "=== suite: $name: $*"
    "$@" >"$raw_log" 2>&1 || code=$?
    "$PY" scripts/redact_evidence.py <"$raw_log" >"$EVIDENCE_DIR/logs/$name.log"
    rm -f "$raw_log"
    printf '%s\t%s\t%s\n' "$name" "$code" "$*" >>"$EVIDENCE_DIR/suites.tsv"
    if [ "$code" != "0" ]; then
      GATE_FAILURES=1
    fi
    echo "=== suite: $name: exit $code"
  }

  run_suite contract "$PY" -m pytest .repo_template/tests -q -m contract \
    --junitxml="$EVIDENCE_DIR/junit/contract.xml"
  run_suite unit env PYTHONPATH=src/backend "$PY" -m pytest tests/unit -q \
    --junitxml="$EVIDENCE_DIR/junit/unit.xml"
  run_suite integration env PYTHONPATH=src/backend "$PY" -m pytest tests/integration -q \
    --junitxml="$EVIDENCE_DIR/junit/integration.xml"
  run_suite frontend_test env NODE_OPTIONS=--no-experimental-webstorage \
    npm test --prefix src/frontend
  run_suite frontend_build npm run build --prefix src/frontend

  if [ "${CBROWSER_RUN_E2E:-0}" = "1" ]; then
    export CBROWSER_E2E_REQUIRED=1
    run_suite e2e env PYTHONPATH=src/backend:tests/fixtures "$PY" -m pytest tests/e2e -q \
      --basetemp="$SCRATCH/e2e" --junitxml="$EVIDENCE_DIR/junit/e2e.xml"
  fi

  "$PY" scripts/gate_evidence_manifest.py \
    --evidence-dir "$EVIDENCE_DIR" --suites-tsv "$EVIDENCE_DIR/suites.tsv"
  echo "gate evidence: manifest at $EVIDENCE_DIR/manifest.json"
  exit "$GATE_FAILURES"
fi

"$PY" -m pytest .repo_template/tests -q -m contract
PYTHONPATH=src/backend "$PY" -m pytest tests/unit -q
PYTHONPATH=src/backend "$PY" -m pytest tests/integration -q
NODE_OPTIONS=--no-experimental-webstorage npm test --prefix src/frontend
npm run build --prefix src/frontend

if [ "${CBROWSER_RUN_E2E:-0}" = "1" ]; then
  export CBROWSER_E2E_REQUIRED=1
  PYTHONPATH=src/backend:tests/fixtures "$PY" -m pytest tests/e2e -q --basetemp="$SCRATCH/e2e"
fi
