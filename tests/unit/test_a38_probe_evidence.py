"""A38: fail-closed evidence gate for the real-engine automation probe.

The host integration suites legitimately skip without Xvfb/engine; a green
host run must never stand in for the container probe.  This module is pure
logic plus a CLI wrapper so the seven failure classes are unit-testable
without a real image/engine (real container execution is NOT_RUN here).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import automation_probe_evidence as evidence

N1 = (
    "tests/e2e/test_automation_compatibility_probe_e2e.py"
    "::test_t032_probe_chain_and_dialog_recheck"
)
N2 = (
    "tests/e2e/test_automation_compatibility_probe_e2e.py"
    "::test_t032_probe_levels_recheck"
)
REQUIRED = list(evidence.REQUIRED_PROBE_NODE_IDS)
REPO_ROOT = Path(__file__).resolve().parents[2]
GATES = REPO_ROOT / "scripts" / "run_gates.sh"
PROBE = REPO_ROOT / "scripts" / "run_automation_probe.sh"
IMAGE = {
    "id": "sha256:" + "a" * 64,
    "os": "linux",
    "architecture": "arm64",
}


def _junit_xml(*cases: tuple[str, str]) -> str:
    parts = [f'<testsuites><testsuite name="pytest" tests="{len(cases)}">']
    for node_id, status in cases:
        module, name = node_id.split("::")
        classname = module[:-3].replace("/", ".")
        parts.append(
            f'<testcase classname="{classname}" name="{name}" time="0.1">'
        )
        if status == "skipped":
            parts.append('<skipped type="pytest.skip" message="skip"/>')
        elif status == "xfail":
            parts.append('<skipped type="pytest.xfail" message="xfail"/>')
        elif status == "failure":
            parts.append('<failure message="boom"/>')
        elif status == "error":
            parts.append('<error message="boom"/>')
        parts.append("</testcase>")
    parts.append("</testsuite></testsuites>")
    return "".join(parts)


def _evaluate(**overrides):
    kwargs = dict(
        exit_code=0,
        interrupted=False,
        preflight=[],
        junit_text=_junit_xml((N1, "passed"), (N2, "passed")),
        image_identity=IMAGE,
        selected_node_ids=list(REQUIRED),
        log_paths=["probe.log", "image.json"],
    )
    kwargs.update(overrides)
    return evidence.evaluate_evidence(**kwargs)


def _preflight_ok() -> dict:
    return dict(
        image_id="sha256:" + "b" * 64,
        image_os_arch="linux/arm64",
        engine_present=True,
        xvfb_present=True,
        permissions_ok=True,
        report_dir_empty=True,
    )


def test_required_node_ids_match_probe_entry() -> None:
    assert set(REQUIRED) == {N1, N2}


def test_preflight_problems_lists_every_missing_item_at_once() -> None:
    problems = evidence.preflight_problems(
        image_id="latest",
        image_os_arch="linux/amd64",
        engine_present=False,
        xvfb_present=False,
        permissions_ok=False,
        report_dir_empty=False,
    )
    assert len(problems) == 6


def test_preflight_clean_when_all_present() -> None:
    assert evidence.preflight_problems(**_preflight_ok()) == []


def test_parse_junit_classifies_statuses() -> None:
    cases = evidence.parse_junit(
        _junit_xml(
            (N1, "skipped"),
            (N2, "xfail"),
        )
    )
    statuses = {case.node_id: case.status for case in cases}
    assert statuses[N1] == "skipped"
    assert statuses[N2] == "xfail"


def test_missing_preflight_not_all_passed() -> None:
    verdict = _evaluate(preflight=["Xvfb missing in probe image"])
    assert verdict.all_passed is False
    assert any("Xvfb" in reason for reason in verdict.reasons)


def test_missing_required_case_not_all_passed() -> None:
    verdict = _evaluate(junit_text=_junit_xml((N1, "passed")))
    assert verdict.all_passed is False
    assert N2 in verdict.required_missing


def test_selection_missing_required_not_all_passed() -> None:
    verdict = _evaluate(selected_node_ids=[N1])
    assert verdict.all_passed is False
    assert any("selection" in reason for reason in verdict.reasons)


def test_injected_skip_not_all_passed() -> None:
    verdict = _evaluate(
        junit_text=_junit_xml((N1, "skipped"), (N2, "passed"))
    )
    assert verdict.all_passed is False
    assert N1 in verdict.required_skipped


def test_xfail_not_counted_as_pass() -> None:
    verdict = _evaluate(
        junit_text=_junit_xml((N1, "xfail"), (N2, "passed"))
    )
    assert verdict.all_passed is False
    assert N1 in verdict.required_xfail


def test_test_failure_not_all_passed() -> None:
    verdict = _evaluate(
        exit_code=1,
        junit_text=_junit_xml((N1, "failure"), (N2, "passed")),
    )
    assert verdict.all_passed is False
    assert N1 in verdict.required_failed


def test_interruption_not_all_passed() -> None:
    verdict = _evaluate(interrupted=True)
    assert verdict.all_passed is False
    assert any("interrupt" in reason.lower() for reason in verdict.reasons)


def test_zero_collection_not_all_passed() -> None:
    verdict = _evaluate(junit_text=_junit_xml())
    assert verdict.all_passed is False
    assert verdict.testcase_count == 0


@pytest.mark.parametrize(
    "junit_text", [None, "", "not xml at all", "<testsuite><testcase"],
)
def test_corrupted_or_missing_evidence_not_all_passed(junit_text) -> None:
    verdict = _evaluate(junit_text=junit_text)
    assert verdict.all_passed is False
    assert any("junit" in reason.lower() for reason in verdict.reasons)


def test_missing_image_identity_not_all_passed() -> None:
    verdict = _evaluate(image_identity={})
    assert verdict.all_passed is False
    assert any("image_identity" in reason for reason in verdict.reasons)


def test_complete_success_all_passed_with_traceable_report() -> None:
    verdict = _evaluate()
    assert verdict.all_passed is True
    assert verdict.reasons == []
    assert verdict.testcase_count == 2
    assert verdict.required_skipped == []
    assert verdict.required_xfail == []
    assert set(verdict.required_present) == {N1, N2}
    report = verdict.to_dict()
    assert report["zero_required_skips"] is True
    assert report["image_identity"] == IMAGE
    assert "probe.log" in report["logs"]
    assert report["all_passed"] is True


def test_cli_writes_evidence_and_returns_pass_fail(
    tmp_path: Path,
) -> None:
    junit = tmp_path / "probe.xml"
    junit.write_text(
        _junit_xml((N1, "passed"), (N2, "passed")), encoding="utf-8"
    )
    image = tmp_path / "image.json"
    image.write_text(json.dumps(IMAGE), encoding="utf-8")
    selected = tmp_path / "selected.txt"
    selected.write_text("\n".join(REQUIRED) + "\n", encoding="utf-8")
    output = tmp_path / "evidence.json"
    rc = evidence.main(
        [
            "--junit",
            str(junit),
            "--image-json",
            str(image),
            "--exit-code",
            "0",
            "--selected",
            str(selected),
            "--log",
            "probe.log",
            "--output",
            str(output),
        ]
    )
    assert rc == 0
    assert json.loads(output.read_text(encoding="utf-8"))["all_passed"] is True

    rc = evidence.main(
        [
            "--junit",
            str(tmp_path / "missing.xml"),
            "--image-json",
            str(image),
            "--exit-code",
            "1",
            "--selected",
            str(selected),
            "--output",
            str(output),
        ]
    )
    assert rc == 1
    assert json.loads(output.read_text(encoding="utf-8"))["all_passed"] is False


def test_gate_summons_real_engine_suite_fail_closed() -> None:
    gates = GATES.read_text(encoding="utf-8")
    assert 'SUITE_ORDER="$SUITE_ORDER real_engine"' in gates
    assert "run_suite real_engine" in gates
    assert "bash scripts/run_automation_probe.sh" in gates
    assert "real_engine NOT_RUN" in gates


def test_gate_keeps_a16_readonly_protocol_drift_check() -> None:
    gates = GATES.read_text(encoding="utf-8")
    assert "protocol_drift_check" in gates
    assert "scripts/export_supervisor_protocol.py --check" in gates
    assert "npm run check:api" in gates
    assert "npm run design:tokens" not in gates
    assert "run_suite design_tokens" not in gates


def test_probe_entry_declares_required_cases_and_evidence() -> None:
    probe = PROBE.read_text(encoding="utf-8")
    for node_id in REQUIRED:
        assert node_id in probe
    assert "automation_probe_evidence.py" in probe
    assert "--junitxml=/evidence/probe.xml" in probe


def test_probe_empty_array_expansion_is_bash32_safe() -> None:
    """run_automation_probe.sh runs under `set -u` on bash 3.2 (macOS
    /bin/bash), where a bare "${arr[@]}" on an empty array is an
    unbound-variable error. The guarded form must be used instead."""
    probe = PROBE.read_text(encoding="utf-8")
    assert '${interrupted_args[@]+"${interrupted_args[@]}"}' in probe
    assert '\n  "${interrupted_args[@]}"\n' not in probe
