"""t044: gate script and E2E-prerequisite contract tests.

These assert the observable shape of ``scripts/run_gates.sh`` and the
E2E suite rather than re-running the (Docker-bound) whole gate, so the
parallel / serial / evidence / cache contracts stay mechanically checked.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = (REPO_ROOT / "scripts" / "run_gates.sh").read_text(encoding="utf-8")
PYPROJECT = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")


def _e2e_files() -> list[Path]:
    return sorted((REPO_ROOT / "tests" / "e2e").glob("test_*.py"))




















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
