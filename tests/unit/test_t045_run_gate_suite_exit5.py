"""t045 AC-001: in-repo regression for run_gate_suite exit-5 symmetry.

Extracts the real ``run_gate_suite()`` function from ``scripts/run_gates.sh``
and drives it against tiny pytest suites, so the gate's two-phase exit-5
handling is covered by the unit gate instead of a scratch-only script.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_GATES = REPO_ROOT / "scripts" / "run_gates.sh"


def _shell_function() -> str:
    text = RUN_GATES.read_text(encoding="utf-8")
    start = text.index("run_gate_suite() {")
    end = text.index("\n}\n", start) + len("\n}\n")
    return text[start:end]


def _drive(
    tmp_path: Path, suite_source: str
) -> tuple[subprocess.CompletedProcess[str], Path | None]:
    target = tmp_path / "mini"
    target.mkdir()
    (target / "test_mini.py").write_text(suite_source, encoding="utf-8")
    junit = tmp_path / "out" / "mini.xml"
    basetemp = tmp_path / "basetemp"
    script = tmp_path / "drive.sh"
    script.write_text(
        "\n".join(
            [
                "#!/bin/bash",
                "set -uo pipefail",
                f"PY={shlex.quote(sys.executable)}",
                "WORKERS=2",
                _shell_function().rstrip("\n"),
                f"cd {shlex.quote(str(REPO_ROOT))}",
                "run_gate_suite "
                + " ".join(
                    shlex.quote(str(part))
                    for part in (target, "", junit, basetemp)
                ),
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
        timeout=180,
    )
    return result, junit if junit.is_file() else None


def _case_names(junit: Path | None) -> set[str]:
    if junit is None:
        return set()
    return {
        case.get("name", "")
        for case in ET.parse(junit).getroot().iter("testcase")
    }


def test_all_serial_suite_does_not_false_fail(tmp_path: Path) -> None:
    """Parallel phase empty (exit 5) must not fail the suite; serial results
    are still merged into the single junit (AC-001)."""
    result, junit = _drive(
        tmp_path,
        "import pytest\npytestmark = pytest.mark.serial\n"
        "def test_serial_only():\n    pass\n",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "test_serial_only" in _case_names(junit)


def test_all_parallel_suite_does_not_false_fail(tmp_path: Path) -> None:
    """Serial phase empty (exit 5) must not fail the suite."""
    result, junit = _drive(
        tmp_path, "def test_parallel_only():\n    pass\n"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "test_parallel_only" in _case_names(junit)


def test_both_phases_empty_suite_fails(tmp_path: Path) -> None:
    """Both phases empty must be reported as a failure, not silently passed."""
    result, _ = _drive(tmp_path, "# no test functions\n")
    assert result.returncode == 5, result.stdout + result.stderr
