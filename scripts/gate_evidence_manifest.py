#!/usr/bin/env python3
"""Build the gate evidence manifest (t028 AC-006).

Reads the per-suite TSV written by ``scripts/run_gates.sh`` in evidence
mode (name, exit code, display command) and emits ``manifest.json`` in
the evidence directory: every suite's command, exit code, redacted log
path, JUnit path when the suite produced one, the image identities the
run was configured with (t028 AC-005), and the aggregate verdict.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--suites-tsv", required=True)
    args = parser.parse_args()

    evidence_dir = Path(args.evidence_dir)
    suites: list[dict[str, object]] = []
    for line in Path(args.suites_tsv).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        name, exit_code, command = line.split("\t", 2)
        entry: dict[str, object] = {
            "name": name,
            "command": command,
            "exit_code": int(exit_code),
            "log": f"logs/{name}.log",
        }
        junit = evidence_dir / "junit" / f"{name}.xml"
        if junit.is_file():
            entry["junit"] = f"junit/{name}.xml"
        suites.append(entry)

    # The identity helper needs pytest importable (it lives in the gate
    # venv); when this script runs as the environment-failure fallback
    # under a bare interpreter, identity collection may be impossible.
    # Record the failure explicitly instead of silently writing an empty
    # map: an empty image_identity must only ever mean "no image
    # variables were set", never "collection broke".
    try:
        sys.path.insert(0, str(REPO_ROOT / "tests" / "fixtures"))
        from e2e_env import collect_image_identity_evidence

        image_identity = collect_image_identity_evidence()
    except Exception as exc:  # noqa: BLE001 - surfaced in the manifest
        image_identity = {"error": f"{type(exc).__name__}: {exc}"}

    manifest = {
        "suites": suites,
        "image_identity": image_identity,
        "all_passed": all(entry["exit_code"] == 0 for entry in suites),
    }
    (evidence_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
