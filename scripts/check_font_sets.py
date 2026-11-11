#!/usr/bin/env python3
"""Preflight check for the deploy-time font directory (t051 AC-009/AC-010).

Scans ``<fonts-dir>/<platform>/<set-id>`` with the shared
``cbrowser.font_sets.manifest`` rules and reports every set's integrity.
Exit 0 always: a missing directory or a directory with no valid set is a
warning, never a deploy blocker — the deploy continues and the API falls
back to its built-in fonts.

    python3 scripts/check_font_sets.py --fonts-dir <dir>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "backend"))

from cbrowser.font_sets.manifest import list_font_sets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fonts-dir", required=True, help="Host font directory")
    args = parser.parse_args(argv)
    root = Path(args.fonts_dir)
    if not root.is_dir():
        print(
            f"WARNING: fonts directory {args.fonts_dir} does not exist; "
            "no platform font sets will be mounted. Deploy continues with "
            "the built-in fonts. To add fonts, import a set with "
            "scripts/import_font_set.py --platform windows|macos "
            f"--source <dir> --fonts-dir {args.fonts_dir}."
        )
        return 0
    sets = list_font_sets(root)
    valid = [item for item in sets if item["integrity"]["ok"]]
    for item in sets:
        status = "ok" if item["integrity"]["ok"] else "INVALID"
        line = (
            f"font set {item['platform']}/{item['set_id']}: {status} "
            f"({item['file_count']} files)"
        )
        problems = item["integrity"]["problems"]
        if problems:
            line += " - " + "; ".join(problems)
        print(line)
    if not valid:
        print(
            f"WARNING: no valid font set found under {args.fonts_dir}; "
            "deploy continues with the built-in fonts. Import a set with "
            "scripts/import_font_set.py --platform windows|macos "
            f"--source <dir> --fonts-dir {args.fonts_dir}."
        )
    else:
        print(
            f"font sets ok: {len(valid)} valid set(s) under {args.fonts_dir}."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
