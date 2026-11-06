"""t044 AC-004: two-phase JUnit evidence is merged without losing cases."""

from __future__ import annotations

import importlib.util
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "merge_junit", REPO_ROOT / "scripts" / "merge_junit.py"
)
assert _SPEC is not None and _SPEC.loader is not None
merge_junit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(merge_junit)

_PARALLEL = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="parallel" tests="3" failures="1" errors="0" skipped="1" time="1.25">
  <testcase classname="a" name="passes" time="0.1"/>
  <testcase classname="a" name="fails" time="0.2"><failure message="boom">trace</failure></testcase>
  <testcase classname="a" name="skips" time="0.0"><skipped message="nope"/></testcase>
</testsuite></testsuites>
"""

_SERIAL = """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="serial" tests="2" failures="0" errors="1" skipped="0" time="2.5">
  <testcase classname="b" name="serial_pass" time="0.3"/>
  <testcase classname="b" name="serial_error" time="0.4"><error message="err">trace</error></testcase>
</testsuite>
"""


def test_merge_keeps_every_case_and_sums_counts(tmp_path: Path) -> None:
    a = tmp_path / "parallel.xml"
    b = tmp_path / "serial.xml"
    out = tmp_path / "nested" / "merged.xml"
    a.write_text(_PARALLEL, encoding="utf-8")
    b.write_text(_SERIAL, encoding="utf-8")

    total = merge_junit.merge_junit([a, b], out)

    root = ET.parse(out).getroot()
    assert root.tag == "testsuites"
    suite = root.find("testsuite")
    assert suite is not None
    assert total == 5
    assert suite.get("tests") == "5"
    assert suite.get("failures") == "1"
    assert suite.get("errors") == "1"
    assert suite.get("skipped") == "1"
    assert suite.get("time") == "3.750"

    cases = {(c.get("classname"), c.get("name")): c for c in suite.findall("testcase")}
    assert set(cases) == {
        ("a", "passes"),
        ("a", "fails"),
        ("a", "skips"),
        ("b", "serial_pass"),
        ("b", "serial_error"),
    }
    assert cases[("a", "fails")].find("failure") is not None
    assert cases[("a", "skips")].find("skipped") is not None
    assert cases[("b", "serial_error")].find("error") is not None


def test_merge_handles_empty_phase(tmp_path: Path) -> None:
    a = tmp_path / "parallel.xml"
    b = tmp_path / "serial.xml"
    out = tmp_path / "merged.xml"
    a.write_text(_PARALLEL, encoding="utf-8")
    b.write_text("<testsuites/>", encoding="utf-8")

    assert merge_junit.merge_junit([a, b], out) == 3
    suite = ET.parse(out).getroot().find("testsuite")
    assert suite is not None
    assert suite.get("tests") == "3"


def test_merge_cli(tmp_path: Path) -> None:
    a = tmp_path / "a.xml"
    b = tmp_path / "b.xml"
    out = tmp_path / "out.xml"
    a.write_text(_PARALLEL, encoding="utf-8")
    b.write_text(_SERIAL, encoding="utf-8")
    rc = merge_junit.main_with_args(["--output", str(out), str(a), str(b)])
    assert rc == 0
    assert out.is_file()
