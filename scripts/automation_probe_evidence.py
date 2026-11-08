"""Fail-closed evidence gate for the real-engine automation probe suite.

A green host integration run (which may skip without Xvfb/engine) must never
stand in for the container probe.  ``evaluate_evidence`` folds image
identity, preflight, selected/executed cases, JUnit integrity, skip/xfail
handling, exit code and interruption into one verdict; ``main`` is the CLI
used by ``scripts/run_automation_probe.sh`` to write ``evidence.json``.
"""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED_PROBE_NODE_IDS: tuple[str, ...] = (
    "tests/e2e/test_automation_compatibility_probe_e2e.py"
    "::test_t032_probe_chain_and_dialog_recheck",
    "tests/e2e/test_automation_compatibility_probe_e2e.py"
    "::test_t032_probe_levels_recheck",
)

_IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class JUnitCase:
    node_id: str
    status: str


@dataclass
class ProbeVerdict:
    all_passed: bool
    reasons: list[str] = field(default_factory=list)
    executed: list[str] = field(default_factory=list)
    required_present: list[str] = field(default_factory=list)
    required_missing: list[str] = field(default_factory=list)
    required_skipped: list[str] = field(default_factory=list)
    required_xfail: list[str] = field(default_factory=list)
    required_failed: list[str] = field(default_factory=list)
    testcase_count: int = 0
    image_identity: dict = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)
    exit_code: int = 0
    interrupted: bool = False

    def to_dict(self) -> dict:
        return {
            "all_passed": self.all_passed,
            "reasons": list(self.reasons),
            "testcase_count": self.testcase_count,
            "zero_required_skips": (
                not self.required_skipped and not self.required_xfail
            ),
            "required_node_ids": list(REQUIRED_PROBE_NODE_IDS),
            "required_present": list(self.required_present),
            "required_missing": list(self.required_missing),
            "required_skipped": list(self.required_skipped),
            "required_xfail": list(self.required_xfail),
            "required_failed": list(self.required_failed),
            "executed": list(self.executed),
            "image_identity": dict(self.image_identity),
            "logs": list(self.logs),
            "exit_code": self.exit_code,
            "interrupted": self.interrupted,
        }


def preflight_problems(
    *,
    image_id: str | None,
    image_os_arch: str | None,
    engine_present: bool,
    xvfb_present: bool,
    permissions_ok: bool,
    report_dir_empty: bool,
) -> list[str]:
    problems: list[str] = []
    if not image_id or not _IMAGE_ID_RE.match(image_id):
        problems.append("probe image must be an immutable sha256:<64 hex> ID")
    if image_os_arch != "linux/arm64":
        problems.append(
            f"probe image must be linux/arm64, got {image_os_arch!r}"
        )
    if not engine_present:
        problems.append("selected target engine executable missing")
    if not xvfb_present:
        problems.append("Xvfb unavailable in probe image")
    if not permissions_ok:
        problems.append("probe runtime permissions check failed")
    if not report_dir_empty:
        problems.append("evidence directory must be empty")
    return problems


def _case_node_id(classname: str, name: str) -> str:
    return f"{classname.replace('.', '/')}.py::{name}"


def parse_junit(xml_text: str) -> list[JUnitCase]:
    root = ET.fromstring(xml_text)
    cases: list[JUnitCase] = []
    for node in root.iter("testcase"):
        node_id = _case_node_id(
            node.get("classname", ""), node.get("name", "")
        )
        if node.find("failure") is not None or node.find("error") is not None:
            status = "failure"
        else:
            skipped = node.find("skipped")
            if skipped is None:
                status = "passed"
            elif "xfail" in skipped.get("type", "") or (
                "xpass" in skipped.get("type", "")
            ):
                status = "xfail"
            else:
                status = "skipped"
        cases.append(JUnitCase(node_id, status))
    return cases


def evaluate_evidence(
    *,
    exit_code: int,
    interrupted: bool,
    preflight: list[str],
    junit_text: str | None,
    image_identity: dict | None,
    selected_node_ids: list[str],
    log_paths: list[str] | None = None,
) -> ProbeVerdict:
    reasons: list[str] = [f"preflight: {problem}" for problem in preflight]
    if interrupted:
        reasons.append("interrupted: probe run did not finish")
    if exit_code != 0:
        reasons.append(f"exit_code: probe pytest returned {exit_code}")
    if not image_identity:
        reasons.append("image_identity: missing from evidence")

    required = set(REQUIRED_PROBE_NODE_IDS)
    selection_missing = sorted(required - set(selected_node_ids))
    if selection_missing:
        reasons.append(f"selection_missing_required: {selection_missing}")

    cases: list[JUnitCase] = []
    junit_ok = True
    if junit_text is None or not junit_text.strip():
        reasons.append("junit: report missing")
        junit_ok = False
    else:
        try:
            cases = parse_junit(junit_text)
        except ET.ParseError:
            reasons.append("junit: report is corrupted")
            junit_ok = False
    if junit_ok and not cases:
        reasons.append("junit: zero testcases collected")

    executed = {case.node_id for case in cases}
    required_missing = (
        sorted(required - executed) if junit_ok else sorted(required)
    )
    if required_missing:
        reasons.append(f"required_cases_missing: {required_missing}")

    def _with_status(status: str) -> list[str]:
        return sorted(
            case.node_id
            for case in cases
            if case.node_id in required and case.status == status
        )

    required_skipped = _with_status("skipped")
    required_xfail = _with_status("xfail")
    required_failed = _with_status("failure")
    if required_skipped:
        reasons.append(f"required_cases_skipped: {required_skipped}")
    if required_xfail:
        reasons.append(f"required_cases_xfail_not_pass: {required_xfail}")
    if required_failed:
        reasons.append(f"required_cases_failed: {required_failed}")
    other_failed = sorted(
        case.node_id
        for case in cases
        if case.status == "failure" and case.node_id not in required
    )
    if other_failed:
        reasons.append(f"other_cases_failed: {other_failed}")

    return ProbeVerdict(
        all_passed=not reasons,
        reasons=reasons,
        executed=[case.node_id for case in cases],
        required_present=sorted(required & executed),
        required_missing=required_missing,
        required_skipped=required_skipped,
        required_xfail=required_xfail,
        required_failed=required_failed,
        testcase_count=len(cases),
        image_identity=dict(image_identity or {}),
        logs=list(log_paths or []),
        exit_code=exit_code,
        interrupted=interrupted,
    )


def _lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", required=True)
    parser.add_argument("--image-json", required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--selected", required=True)
    parser.add_argument("--preflight", default="")
    parser.add_argument("--interrupted", action="store_true")
    parser.add_argument("--log", action="append", default=[])
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    junit_path = Path(args.junit)
    junit_text = (
        junit_path.read_text(encoding="utf-8") if junit_path.is_file() else None
    )
    image_path = Path(args.image_json)
    image_identity = None
    if image_path.is_file():
        try:
            image_identity = json.loads(image_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            image_identity = None

    verdict = evaluate_evidence(
        exit_code=args.exit_code,
        interrupted=args.interrupted,
        preflight=_lines(Path(args.preflight)) if args.preflight else [],
        junit_text=junit_text,
        image_identity=image_identity,
        selected_node_ids=_lines(Path(args.selected)),
        log_paths=args.log,
    )
    Path(args.output).write_text(
        json.dumps(verdict.to_dict(), indent=2) + "\n", encoding="utf-8"
    )
    return 0 if verdict.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
