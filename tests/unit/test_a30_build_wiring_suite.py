"""A30: the frontend build-wiring checks must run in the regular unit suite.

The file only uses a temporary dist plus pure-Python verification, so the
gate's E2E skip would otherwise hide every negative case (D: A30).
"""

from __future__ import annotations

import re
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
