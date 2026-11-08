"""A30: the frontend build-wiring checks must run in the regular unit suite.

The file only uses a temporary dist plus pure-Python verification, so the
gate's E2E skip would otherwise hide every negative case (D: A30).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
UNIT_FILE = REPO_ROOT / "tests" / "unit" / "test_frontend_build_wiring.py"
E2E_FILE = REPO_ROOT / "tests" / "e2e" / "test_frontend_build_wiring.py"

EXPECTED_CASES = {
    "test_package_build_runs_vendor_and_verification",
    "test_frontend_gate_checks_pinned_node_version",
    "test_default_manifests_live_outside_tests",
    "test_valid_dist_passes",
    "test_missing_button_primary_class_fails",
    "test_default_palette_class_fails",
    "test_missing_adapter_fails",
    "test_module_adapter_fails",
    "test_missing_adapter_tag_fails",
    "test_adapter_must_load_before_module_bundle",
    "test_manifest_mismatch_fails",
}


def _unit_collection() -> list[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = "src/backend:tests/fixtures"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/unit",
            "--collect-only",
            "-q",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.splitlines()


def test_build_wiring_lives_in_unit_suite() -> None:
    assert UNIT_FILE.is_file()
    assert not E2E_FILE.exists()


def test_original_cases_preserved() -> None:
    source = UNIT_FILE.read_text(encoding="utf-8")
    found = set(re.findall(r"^def (test_\w+)\(", source, re.MULTILINE))
    assert found == EXPECTED_CASES


def test_no_e2e_prerequisites() -> None:
    source = UNIT_FILE.read_text(encoding="utf-8")
    for marker in ("require_e2e_env", "docker.from_env", "CBROWSER_", "HOST_CHROME"):
        assert marker not in source


def test_negative_cases_still_asserted() -> None:
    source = UNIT_FILE.read_text(encoding="utf-8")
    assert source.count("pytest.raises(RuntimeError") == 7


def test_regular_unit_collection_includes_each_case_once() -> None:
    lines = _unit_collection()
    prefix = "tests/unit/test_frontend_build_wiring.py::"
    collected = [line for line in lines if line.startswith(prefix)]
    assert len(collected) == len(EXPECTED_CASES)
    assert {
        line.split("::", 1)[1].strip() for line in collected
    } == EXPECTED_CASES
    assert not any(
        "tests/e2e/test_frontend_build_wiring.py::" in line for line in lines
    )
