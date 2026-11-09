"""t044: gate script and E2E-prerequisite contract tests.

These assert the observable shape of ``scripts/run_gates.sh`` and the
E2E suite rather than re-running the (Docker-bound) whole gate, so the
parallel / serial / evidence / cache contracts stay mechanically checked.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = (REPO_ROOT / "scripts" / "run_gates.sh").read_text(encoding="utf-8")
PYPROJECT = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")


def _e2e_files() -> list[Path]:
    return sorted((REPO_ROOT / "tests" / "e2e").glob("test_*.py"))


def test_gate_uses_xdist_two_phase_execution() -> None:
    """AC-001/AC-007: multiple workers plus a dedicated serial phase."""
    assert '-n "$WORKERS"' in GATE
    assert '-m "not serial"' in GATE
    assert '-n 0' in GATE
    assert '-m "serial"' in GATE
    assert 'merge_junit.py' in GATE


def test_gate_runs_backend_and_frontend_groups_concurrently() -> None:
    """AC-008: both groups run in background and are joined before E2E."""
    assert "backend_group &" in GATE
    assert "frontend_group &" in GATE
    assert 'wait "$pid_backend"' in GATE
    assert 'wait "$pid_frontend"' in GATE
    wait_pos = GATE.index('wait "$pid_frontend"')
    e2e_pos = GATE.index("image_packages", wait_pos)
    assert e2e_pos > wait_pos


def test_gate_evidence_order_is_fixed() -> None:
    """AC-004: suites.tsv is concatenated in a fixed order."""
    assert "SUITE_ORDER=" in GATE
    assert 'for name in $SUITE_ORDER' in GATE
    assert "gate_evidence_manifest.py" in GATE
    assert "suites.d/" in GATE


def test_gate_never_runs_design_tokens_generation() -> None:
    """AC-015: design:tokens (a write) is not a gate step; check stays."""
    assert "npm run design:tokens" not in GATE
    assert "npm run design:check" in GATE
    assert "npm run design:lint" in GATE
    assert "run_suite design_tokens" not in GATE


def test_gate_wires_lock_drift_and_image_package_checks() -> None:
    """AC-011: both verification tools are part of the gate."""
    assert "scripts/generate_requirements.sh --check" in GATE
    assert "scripts/verify_image_packages.py" in GATE
    assert "verify_image_packages_all" in GATE
    assert "requirements_check" in GATE


def test_gate_rebuilds_venv_clear() -> None:
    """A stale .scratch/gate_venv must not abort the gate with "already
    exists": the rebuild clears the target directory first."""
    assert "uv venv --clear" in GATE


def test_gate_wheel_cache_is_a_pre_step() -> None:
    """Clean clones lack .scratch/selkies_wheels (gitignored); the gate
    fetches the pinned wheel before any suite instead of failing in unit."""
    assert "ensure_selkies_wheel_cache" in GATE
    assert "-m scripts.ensure_selkies_wheel_cache" in GATE
    assert "CBROWSER_SELKIES_WHEEL_CACHE" in GATE
    assert ".scratch/selkies_wheels" in GATE


def test_gate_evidence_fails_closed_on_missing_suite_tsv() -> None:
    """A missing per-suite TSV (suite never ran) fails the gate instead of
    silently passing with a partial manifest."""
    assert "missing suite result" in GATE
    assert "manifest.json not written" in GATE
    assert "junit merge output missing" in GATE


def test_gate_reuses_shared_uv_cache() -> None:
    """AC-009: persistent cache + venv stamp; warm run logs no download."""
    assert "export UV_CACHE_DIR=" in GATE
    assert "CBROWSER_GATE_UV_CACHE" in GATE
    assert "REQ_HASH" in GATE
    assert "STAMP" in GATE
    assert "reuse cached venv" in GATE
    assert "no dependency download" in GATE


def test_e2e_prerequisites_have_no_bare_skip() -> None:
    """AC-005: every skip goes through the fail-closed helper."""
    # The two switch-gated probe suites are explicitly opted-in exceptions.
    exceptions = {
        "test_automation_compatibility_probe_e2e.py",
        "test_supervisor_reconciliation_e2e.py",
    }
    offenders: list[str] = []
    for path in _e2e_files():
        if path.name in exceptions:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("pytest.skip("):
                offenders.append(f"{path.name}:{lineno}")
    assert offenders == [], f"bare pytest.skip bypasses required mode: {offenders}"


def test_fingerprint_e2e_uses_persistent_fonts() -> None:
    """AC-006: no worktree-private .scratch font/engine paths remain."""
    text = (
        REPO_ROOT / "tests" / "e2e" / "test_fingerprint_platform_e2e.py"
    ).read_text(encoding="utf-8")
    assert ".scratch" not in text
    assert "win_fonts" not in text
    assert "t032/data/engine-cache" not in text
    assert "CBROWSER_E2E_FONTS_DIR" in text
    assert "fonts_platform" in text


def test_deprecation_warning_policy() -> None:
    """AC-012: unregistered DeprecationWarning fails; ignores are precise."""
    assert '"error::DeprecationWarning"' in PYPROJECT
    assert "ignore:Setting per-request cookies" in PYPROJECT
    assert "ignore:Bare functions are deprecated" in PYPROJECT
    assert "ignore:jsonschema.RefResolver is deprecated" in PYPROJECT
    # No blanket ignore of every DeprecationWarning.
    assert '"ignore::DeprecationWarning"' not in PYPROJECT


def _collect(*extra: str) -> set[str]:
    env = {**dict(__import__("os").environ), "PYTHONPATH": "src/backend:tests/fixtures"}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/e2e",
            "--collect-only",
            "-q",
            "--noconftest",
            *extra,
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return {
        line.strip()
        for line in result.stdout.splitlines()
        if "::" in line and not line.startswith((" ", "\t", "-"))
    }


def test_serial_marker_partitions_e2e_collection() -> None:
    """AC-001/AC-002: every collected case is either serial or parallel."""
    full = _collect()
    serial = _collect("-m", "serial")
    parallel = _collect("-m", "not serial")
    assert full, "no E2E cases collected"
    assert serial, "no serial cases collected"
    assert parallel, "no parallel cases collected"
    assert serial.isdisjoint(parallel)
    assert serial | parallel == full
