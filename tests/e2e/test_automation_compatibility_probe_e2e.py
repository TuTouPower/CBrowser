"""t032 recheck entry for the t029 automation compatibility probe.

t029 measured the probe in the cloud against the CloakBrowser linux-x64
binary under Xvfb.  t032 repeats the same probe inside the real arm64
image / container X11 / Stream environment and treats any disagreement
as authoritative over the t029 conclusions.  These tests are inert
unless CBROWSER_T029_PROBE_E2E=1 is set; they re-run the integration
probe suites and the L0-L6 sampling driver as subprocesses and only
assert that the probe completes and produces complete reports — the
verdicts themselves are t032's to record.

Prerequisites in the t032 environment (see docs/specs/
automation_compatibility.md): Playwright + cloakbrowser installed per
scripts/gate-requirements.txt, engine cache present
(CBROWSER_T029_ENGINE_CACHE or ~/.cache/cloakbrowser), Xvfb, and xte for
the XTEST leg (T029_XTE or PATH).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ENABLED = os.environ.get("CBROWSER_T029_PROBE_E2E") == "1"

pytestmark = [pytest.mark.skipif(
    not ENABLED,
    reason="t029 probe recheck runs only under CBROWSER_T029_PROBE_E2E=1 (t032)",
), pytest.mark.e2e_images()]


def _run_pytest_subset(report_dir: Path, *node_ids: str) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src" / "backend")
    env["CBROWSER_T029_REPORT_DIR"] = str(report_dir)
    log_path = report_dir / "chain.log"
    with log_path.open("w") as log:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q",
             "-o", f"cache_dir={report_dir / 'pytest-cache'}",
             f"--junitxml={report_dir / 'chain.xml'}", *node_ids],
            cwd=REPO_ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
            text=True, timeout=1800,
        )
    output = log_path.read_text()
    assert proc.returncode == 0, output[-6000:]
    cases = ET.parse(report_dir / "chain.xml").findall(".//testcase")
    assert len(cases) >= len(node_ids), "probe cases missing from JUnit"
    assert not any(case.find("skipped") is not None for case in cases), output[-6000:]


def test_t032_probe_chain_and_dialog_recheck(tmp_path: Path) -> None:
    integration = "tests/integration/test_automation_probe_chain.py"
    _run_pytest_subset(
        tmp_path,
        f"{integration}::test_probe_chain_target_engine_matrix_and_disconnect",
        f"{integration}::test_probe_chain_external_browser_close_rejected",
        f"{integration}::test_probe_chain_client_killed_mid_connection_survival",
        f"{integration}::test_probe_chain_dialog_contract",
        f"{integration}::test_probe_target_engine_dialog_contract",
        "tests/integration/test_agent_executor_chain.py",
    )
    for name in ("chain-target.json", "chain-dialog.json", "dialog-target.json"):
        report = tmp_path / name
        assert report.is_file(), f"probe report missing: {name}"
        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload["schema"] == "automation-probe-report/v1"


def test_t032_probe_levels_recheck(tmp_path: Path) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src" / "backend")
    env["CBROWSER_T029_REPORT_DIR"] = str(tmp_path)
    driver = (
        REPO_ROOT
        / "tests"
        / "fixtures"
        / "automation_probe"
        / "run_levels.py"
    )
    log_path = tmp_path / "levels.log"
    with log_path.open("w") as log:
        proc = subprocess.run(
            [sys.executable, str(driver)], cwd=REPO_ROOT, env=env,
            stdout=log, stderr=subprocess.STDOUT, text=True, timeout=3600,
        )
    assert proc.returncode == 0, log_path.read_text()[-6000:]
    report = json.loads((tmp_path / "levels.json").read_text(encoding="utf-8"))
    assert report["schema"] == "automation-probe-report/v1"
    for level in ("L0", "L1", "L2", "L3", "L4", "L5", "L6_cdp_input", "L6_xtest_input"):
        assert len(report["levels"][level]) >= 5, f"{level} under-sampled"
        verdict = report["summary"][level]["verdict"]
        assert verdict in {"baseline", "no_change", "new_changes", "insufficient"}
    comparison = report["input_comparison"]
    assert {"cdp", "xtest", "zoom", "focus_contention"} <= set(comparison)
    for entry in comparison["cdp"]:
        assert entry["client_error"] is not None
    for entry in comparison["xtest"]:
        assert entry["client_error"] is not None
        assert entry["frame_client_error"] is not None
    for entry in comparison["zoom"]:
        assert entry["keysym_attempted"] == ["ctrl+plus", "ctrl+equal"]
        assert entry["verdict"] in {
            "measured",
            "inconclusive_shortcut_ineffective",
        }
        assert entry["xtest_click"]["client_error"] is not None
        assert entry["cdp_click"]["client_error"] is not None
    for entry in comparison["focus_contention"]:
        assert isinstance(entry["has_focus_during_L3"], bool)
        assert entry["xtest_click"]["client_error"] is not None
