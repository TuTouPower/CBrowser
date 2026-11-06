#!/usr/bin/env python3
"""Merge per-phase JUnit XML files into one suite (t044 AC-004).

The gate runs most cases on xdist workers and the ``serial`` cases in a
single process.  Both phases emit JUnit XML; the evidence contract requires
one ``junit/<suite>.xml`` containing every case and each case's own result.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

_COUNTERS = ("tests", "failures", "errors", "skipped")


def merge_junit(paths: list[Path], out: Path) -> int:
    root = ET.Element("testsuites")
    merged = ET.SubElement(root, "testsuite", {"name": "merged"})
    counts = {key: 0 for key in _COUNTERS}
    total_time = 0.0
    for path in paths:
        tree = ET.parse(path)
        parsed = tree.getroot()
        suites = list(parsed) if parsed.tag == "testsuites" else [parsed]
        for suite in suites:
            if suite.tag != "testsuite":
                continue
            for key in _COUNTERS:
                raw = suite.get(key, "0") or "0"
                try:
                    counts[key] += int(raw)
                except ValueError:
                    pass
            try:
                total_time += float(suite.get("time", "0") or "0")
            except ValueError:
                pass
            for case in suite.findall("testcase"):
                merged.append(case)
    for key in _COUNTERS:
        merged.set(key, str(counts[key]))
    merged.set("time", f"{total_time:.3f}")
    out.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(out, encoding="utf-8", xml_declaration=True)
    return counts["tests"]


def main_with_args(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("inputs", nargs="+")
    args = parser.parse_args(argv)
    merge_junit([Path(p) for p in args.inputs], Path(args.output))
    return 0


def main() -> int:
    return main_with_args(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
