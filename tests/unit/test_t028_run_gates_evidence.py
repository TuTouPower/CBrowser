"""t028 AC-006: run_gates.sh evidence mode.

Evidence mode runs every suite even when one fails, retains per-suite
command/exit code/JUnit/redacted log plus a manifest in the evidence
directory, and exits non-zero on any failure.  Default mode is
unchanged: it stops at the first failing suite.  The gate script is
driven end-to-end with stub `uv`/`npm` binaries so the shell behaviour
itself is under test.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

UV_STUB = """#!/bin/bash
if [ "$1" = "export" ]; then
  echo "uv $*" >> "$GATE_STUB_LOG"
  grp=""
  prev=""
  for a in "$@"; do
    if [ "$prev" = "--only-group" ]; then grp="$a"; fi
    prev="$a"
  done
  case "$grp" in
    api) cat config/docker/api_runtime/requirements.txt ;;
    gateway) cat config/docker/gateway_runtime/requirements.txt ;;
    supervisor) cat config/docker/supervisor_runtime/requirements.txt ;;
    browser) cat config/docker/browser_runtime/requirements.txt ;;
    stream) cat config/docker/stream_runtime/requirements.txt ;;
    gate) cat scripts/gate-requirements.txt ;;
  esac
  exit 0
fi
echo "uv $*" >> "$GATE_STUB_LOG"
echo "uv-output password=hunter2"
if [ "$1" = "venv" ]; then
  target="${@: -1}"
  mkdir -p "$target/bin"
  cat > "$target/bin/python" <<'PYEOF'
#!/bin/bash
echo "python $*" >> "$GATE_STUB_LOG"
if [ "$1" != "-m" ]; then
  # Script invocations (redactor, manifest builder) run for real.
  exec "$GATE_STUB_REAL_PY" "$@"
fi
for a in "$@"; do
  case "$a" in
    --junitxml=*)
      f="${a#--junitxml=}"
      mkdir -p "$(dirname "$f")"
      printf '<testsuites/>' > "$f"
      ;;
  esac
done
echo "suite output password=hunter2 Bearer abc.def-123"
if [ -n "${GATE_STUB_FAIL:-}" ] && [[ "$*" == *"$GATE_STUB_FAIL"* ]]; then
  exit 3
fi
exit 0
PYEOF
  chmod +x "$target/bin/python"
fi
exit 0
"""

NPM_STUB = """#!/bin/bash
echo "npm $*" >> "$GATE_STUB_LOG"
if [ -n "${GATE_STUB_NPM_FAIL:-}" ] && [[ "$*" == *"$GATE_STUB_NPM_FAIL"* ]]; then
  exit 4
fi
exit 0
"""


def _stub_bin(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "stubbin"
    bin_dir.mkdir()
    for name, body in (("uv", UV_STUB), ("npm", NPM_STUB)):
        stub = bin_dir / name
        stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)
    return bin_dir


def _run_gates(tmp_path: Path, extra_env: dict[str, str]) -> subprocess.CompletedProcess:
    bin_dir = _stub_bin(tmp_path)
    env = dict(os.environ)
    env.pop("TMPDIR", None)
    env.pop("CBROWSER_RUN_E2E", None)
    # A parent gate run exports its evidence directory; without clearing
    # it this nested run writes into the parent's evidence tree, deletes
    # its in-flight per-suite logs and corrupts the outer manifest.
    env.pop("CBROWSER_GATE_EVIDENCE_DIR", None)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["GATE_STUB_LOG"] = str(tmp_path / "stub.log")
    env["GATE_STUB_REAL_PY"] = sys.executable
    env["CBROWSER_GATE_SCRATCH"] = str(tmp_path / "scratch")
    env["CBROWSER_GATE_VENV"] = str(tmp_path / "gate_venv")
    env["CBROWSER_GATE_UV_CACHE"] = str(tmp_path / "uv_cache")
    env.update(extra_env)
    return subprocess.run(
        ["bash", "scripts/run_gates.sh"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _stub_log(tmp_path: Path) -> str:
    log = tmp_path / "stub.log"
    return log.read_text(encoding="utf-8") if log.exists() else ""


def test_evidence_mode_runs_all_suites_and_records_failure(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    result = _run_gates(
        tmp_path,
        {
            "CBROWSER_GATE_EVIDENCE_DIR": str(evidence),
            "GATE_STUB_FAIL": "tests/integration",
        },
    )
    assert result.returncode != 0

    # Every suite ran despite the integration failure.
    log = _stub_log(tmp_path)
    assert ".repo_template/tests" in log
    assert "tests/unit" in log
    assert "tests/integration" in log
    assert "npm run design:lint" in log
    assert "npm run design:check" in log
    assert "npm run design:tokens" not in log
    assert "npm test" in log
    assert "npm run build" in log

    manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
    suites = {entry["name"]: entry for entry in manifest["suites"]}
    assert list(suites) == [
        "requirements_check",
        "contract",
        "unit",
        "integration",
        "design_lint",
        "design_check",
        "frontend_test",
        "frontend_build",
    ]
    assert suites["requirements_check"]["exit_code"] == 0
    assert "generate_requirements.sh --check" in suites["requirements_check"]["command"]
    assert suites["contract"]["exit_code"] == 0
    assert suites["integration"]["exit_code"] == 3
    assert suites["frontend_build"]["exit_code"] == 0
    assert manifest["all_passed"] is False
    assert "pytest" in suites["integration"]["command"]
    assert suites["integration"]["junit"] == "junit/integration.xml"
    assert (evidence / "junit" / "contract.xml").is_file()
    assert (evidence / "junit" / "unit.xml").is_file()

    # Retained logs are redacted: stub suites print secret-shaped text.
    integration_log = (evidence / "logs" / "integration.log").read_text(
        encoding="utf-8"
    )
    assert "hunter2" not in integration_log
    assert "abc.def-123" not in integration_log
    assert "<redacted>" in integration_log

    # The environment build log goes through the same redaction.
    environment_log = (evidence / "logs" / "environment.log").read_text(
        encoding="utf-8"
    )
    assert "hunter2" not in environment_log
    assert "<redacted>" in environment_log
    assert not (evidence / "logs" / "environment.raw.log").exists()


def test_evidence_mode_all_pass_exits_zero(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    result = _run_gates(
        tmp_path, {"CBROWSER_GATE_EVIDENCE_DIR": str(evidence)}
    )
    assert result.returncode == 0
    manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["all_passed"] is True
    assert all(entry["exit_code"] == 0 for entry in manifest["suites"])


@pytest.mark.serial
def test_evidence_dir_reuse_cleans_stale_files(tmp_path: Path) -> None:
    """Reusing an evidence dir must not go false-green on stale files: old
    suites.d/junit/logs fragments are cleared before the run.

    Heavy end-to-end gate drive: serial to avoid contending with other
    concurrent gate drives (t044 AC-002/AC-007 timing-sensitive).
    """
    evidence = tmp_path / "evidence"
    (evidence / "suites.d").mkdir(parents=True)
    (evidence / "junit").mkdir(parents=True)
    (evidence / "logs").mkdir(parents=True)
    # Stale pass from a previous run for a suite that will run again, plus
    # stale fragments for suites not in this run's order (e2e, retired).
    (evidence / "suites.d" / "unit.tsv").write_text(
        "unit\t0\tstale cmd\n", encoding="utf-8"
    )
    (evidence / "suites.d" / "e2e.tsv").write_text(
        "e2e\t0\tstale e2e\n", encoding="utf-8"
    )
    (evidence / "suites.d" / "design_tokens.tsv").write_text(
        "design_tokens\t0\tstale\n", encoding="utf-8"
    )
    (evidence / "junit" / "stale.xml").write_text("<testsuites/>", encoding="utf-8")
    (evidence / "logs" / "stale.log").write_text("stale\n", encoding="utf-8")
    result = _run_gates(
        tmp_path, {"CBROWSER_GATE_EVIDENCE_DIR": str(evidence)}
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (evidence / "junit" / "stale.xml").exists()
    assert not (evidence / "logs" / "stale.log").exists()
    assert not (evidence / "suites.d" / "design_tokens.tsv").exists()
    assert not (evidence / "suites.d" / "e2e.tsv").exists()
    manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
    assert [s["name"] for s in manifest["suites"]] == [
        "requirements_check",
        "contract",
        "unit",
        "integration",
        "design_lint",
        "design_check",
        "frontend_test",
        "frontend_build",
    ]
    assert manifest["all_passed"] is True


def test_default_mode_still_stops_at_first_failure(tmp_path: Path) -> None:
    result = _run_gates(tmp_path, {"GATE_STUB_FAIL": "tests/integration"})
    assert result.returncode != 0
    log = _stub_log(tmp_path)
    assert "tests/integration" in log
    # set -e semantics preserved: later suites never started.
    assert "npm test" not in log
    assert not (tmp_path / "evidence").exists()


def test_redact_evidence_script() -> None:
    sample = (
        "Authorization: Bearer tok123\n"
        "login password=hunter2 ok\n"
        '"token": "abc123", cbrowser_session=sessvalue; other\n'
        "plain line stays\n"
    )
    result = subprocess.run(
        [sys.executable, "scripts/redact_evidence.py"],
        cwd=REPO_ROOT,
        input=sample,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "tok123" not in result.stdout
    assert "hunter2" not in result.stdout
    assert "abc123" not in result.stdout
    assert "sessvalue" not in result.stdout
    assert "plain line stays" in result.stdout
    assert result.stdout.count("<redacted>") >= 4


def _finish_evidence_function() -> str:
    text = (REPO_ROOT / "scripts" / "run_gates.sh").read_text(encoding="utf-8")
    start = text.index("finish_evidence() {")
    end = text.index("\n}\n", start) + len("\n}\n")
    return text[start:end]


def _drive_finish_evidence(tmp_path: Path, present: dict[str, int]) -> subprocess.CompletedProcess:
    import shlex

    evidence = tmp_path / "evidence"
    (evidence / "logs").mkdir(parents=True)
    (evidence / "junit").mkdir(parents=True)
    suites_d = evidence / "suites.d"
    suites_d.mkdir(parents=True)
    for name, code in present.items():
        (suites_d / f"{name}.tsv").write_text(
            f"{name}\t{code}\tcmd {name}\n", encoding="utf-8"
        )
    script = tmp_path / "drive.sh"
    script.write_text(
        "\n".join(
            [
                "#!/bin/bash",
                "set -uo pipefail",
                f"PY={shlex.quote(sys.executable)}",
                f"EVIDENCE_DIR={shlex.quote(str(evidence))}",
                'SUITE_ORDER="requirements_check contract unit"',
                _finish_evidence_function().rstrip("\n"),
                "finish_evidence",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=120,
    )


def test_finish_evidence_missing_suite_tsv_fails_closed(tmp_path: Path) -> None:
    """A suite that never wrote its TSV (missing, not failed) fails the
    gate instead of passing with a partial manifest."""
    result = _drive_finish_evidence(
        tmp_path, {"requirements_check": 0, "contract": 0}
    )
    assert result.returncode != 0
    assert "missing suite result: unit" in result.stderr
    manifest = json.loads(
        (tmp_path / "evidence" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["all_passed"] is False


def test_finish_evidence_all_present_still_passes(tmp_path: Path) -> None:
    result = _drive_finish_evidence(
        tmp_path,
        {"requirements_check": 0, "contract": 0, "unit": 0},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads(
        (tmp_path / "evidence" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["all_passed"] is True


def _run_suite_function() -> str:
    text = (REPO_ROOT / "scripts" / "run_gates.sh").read_text(encoding="utf-8")
    start = text.index("run_suite() {")
    end = text.index("\n}\n", start) + len("\n}\n")
    return text[start:end]


def _drive_run_suite(
    tmp_path: Path, *, py: str, suite_cmd: list[str]
) -> subprocess.CompletedProcess:
    import shlex

    evidence = tmp_path / "evidence"
    (evidence / "logs").mkdir(parents=True)
    (evidence / "suites.d").mkdir(parents=True)
    script = tmp_path / "drive_run.sh"
    cmd = " ".join(shlex.quote(c) for c in suite_cmd)
    script.write_text(
        "\n".join(
            [
                "#!/bin/bash",
                "set -uo pipefail",
                f"PY={shlex.quote(py)}",
                f"EVIDENCE_DIR={shlex.quote(str(evidence))}",
                _run_suite_function().rstrip("\n"),
                f"run_suite mysuite 'cmd mysuite' {cmd}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=120,
    )


def test_finish_evidence_stale_extra_tsv_does_not_false_green(
    tmp_path: Path,
) -> None:
    """An old extra TSV (e.g. a retired suite or a previous E2E run) must
    not sneak into the manifest or flip the verdict to pass."""
    import shlex

    evidence = tmp_path / "evidence"
    (evidence / "logs").mkdir(parents=True)
    (evidence / "junit").mkdir(parents=True)
    suites_d = evidence / "suites.d"
    suites_d.mkdir(parents=True)
    for name in ("requirements_check", "contract", "unit"):
        (suites_d / f"{name}.tsv").write_text(
            f"{name}\t0\tcmd {name}\n", encoding="utf-8"
        )
    # Stale files from a previous run / retired suite.
    (suites_d / "design_tokens.tsv").write_text(
        "design_tokens\t0\told cmd\n", encoding="utf-8"
    )
    (suites_d / "e2e.tsv").write_text("e2e\t0\told e2e\n", encoding="utf-8")
    script = tmp_path / "drive.sh"
    script.write_text(
        "\n".join(
            [
                "#!/bin/bash",
                "set -uo pipefail",
                f"PY={shlex.quote(sys.executable)}",
                f"EVIDENCE_DIR={shlex.quote(str(evidence))}",
                'SUITE_ORDER="requirements_check contract unit"',
                _finish_evidence_function().rstrip("\n"),
                "finish_evidence",
                "",
            ]
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads(
        (evidence / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["all_passed"] is True
    assert [s["name"] for s in manifest["suites"]] == [
        "requirements_check",
        "contract",
        "unit",
    ]


def test_finish_evidence_stale_extra_tsv_ignored(
    tmp_path: Path,
) -> None:
    """A stale extra TSV (previous run / retired suite) is ignored: it
    neither sneaks into the manifest nor flips the verdict (cleaning
    already removed such files; this is defense in depth against reuse
    without cleaning)."""
    import shlex

    evidence = tmp_path / "evidence"
    (evidence / "logs").mkdir(parents=True)
    (evidence / "junit").mkdir(parents=True)
    suites_d = evidence / "suites.d"
    suites_d.mkdir(parents=True)
    for name in ("requirements_check", "contract", "unit"):
        (suites_d / f"{name}.tsv").write_text(
            f"{name}\t0\tcmd {name}\n", encoding="utf-8"
        )
    (suites_d / "e2e.tsv").write_text("e2e\t1\told e2e\n", encoding="utf-8")
    script = tmp_path / "drive.sh"
    script.write_text(
        "\n".join(
            [
                "#!/bin/bash",
                "set -uo pipefail",
                f"PY={shlex.quote(sys.executable)}",
                f"EVIDENCE_DIR={shlex.quote(str(evidence))}",
                'SUITE_ORDER="requirements_check contract unit"',
                _finish_evidence_function().rstrip("\n"),
                "finish_evidence",
                "",
            ]
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads(
        (evidence / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["all_passed"] is True
    assert [s["name"] for s in manifest["suites"]] == [
        "requirements_check",
        "contract",
        "unit",
    ]


def test_run_suite_redaction_failure_withholds_raw(tmp_path: Path) -> None:
    """Redaction failure must not leave an unredacted raw log behind."""
    result = _drive_run_suite(tmp_path, py="false", suite_cmd=["echo", "hello"])
    evidence = tmp_path / "evidence"
    # Suite itself succeeded (echo 0); redaction failed (false).
    assert not (evidence / "logs" / "mysuite.raw.log").exists()
    log = (evidence / "logs" / "mysuite.log").read_text(encoding="utf-8")
    assert "withheld" in log
    assert "hello" not in log
    tsv = (evidence / "suites.d" / "mysuite.tsv").read_text(encoding="utf-8")
    assert tsv.startswith("mysuite\t0\t")


def test_finish_evidence_manifest_failure_fails_closed(tmp_path: Path) -> None:
    """When the manifest builder fails, finish_evidence fails closed."""
    import shlex

    evidence = tmp_path / "evidence"
    (evidence / "logs").mkdir(parents=True)
    (evidence / "junit").mkdir(parents=True)
    suites_d = evidence / "suites.d"
    suites_d.mkdir(parents=True)
    for name in ("requirements_check", "contract", "unit"):
        (suites_d / f"{name}.tsv").write_text(
            f"{name}\t0\tcmd {name}\n", encoding="utf-8"
        )
    script = tmp_path / "drive.sh"
    script.write_text(
        "\n".join(
            [
                "#!/bin/bash",
                "set -uo pipefail",
                "PY=false",
                f"EVIDENCE_DIR={shlex.quote(str(evidence))}",
                'SUITE_ORDER="requirements_check contract unit"',
                _finish_evidence_function().rstrip("\n"),
                "finish_evidence",
                "",
            ]
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=120,
    )
    assert result.returncode != 0
