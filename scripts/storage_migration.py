#!/usr/bin/env python3
"""Host-directory to named-volume storage migration CLI (t080 / ADR 029).

Runs inside a one-shot container (or any environment) where the legacy
host directories and the target volume roots are plain paths:

    storage_migration.py inventory \
        --source-data-root /source-data --source-fonts-dir /source-fonts
    storage_migration.py run \
        --source-data-root /source-data --source-fonts-dir /source-fonts \
        --data-volume /vol-data --fonts-volume /vol-fonts \
        --runtime-volume /vol-runtime \
        --restore-point /points/point-YYYY... \
        --journal /vol-data/.storage-migration-journal.json
    storage_migration.py rollback --journal ... (same volume arguments)
    storage_migration.py status --journal ...

`inventory` is the dry-run: it prints the plan (per-target totals and the
plan digest) and writes nothing.  `run` executes the journaled phases;
re-running resumes.  The legacy source trees are never modified.

Exit codes: 0 ok; 1 failure; 2 writer refusal.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

from cbrowser.supervisor.storage_migration import (  # noqa: E402
    MigrationError,
    MigrationPlan,
    MigrationRunner,
    WriterActiveError,
    build_plan,
)


def _targets(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "data": Path(args.data_volume),
        "fonts": Path(args.fonts_volume),
        "runtime": Path(args.runtime_volume),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("inventory", "run"):
        p = sub.add_parser(name)
        p.add_argument("--source-data-root", required=True)
        p.add_argument("--source-fonts-dir", required=True)
        if name == "run":
            p.add_argument("--data-volume", required=True)
            p.add_argument("--fonts-volume", required=True)
            p.add_argument("--runtime-volume", required=True)
            p.add_argument("--restore-point", required=True)
            p.add_argument("--journal", required=True)
            p.add_argument("--expected-prefix", required=True)
            p.add_argument("--i-confirm-stack-stopped", action="store_true")
    for name in ("rollback", "status"):
        p = sub.add_parser(name)
        p.add_argument("--data-volume", required=True)
        p.add_argument("--fonts-volume", required=True)
        p.add_argument("--runtime-volume", required=True)
        p.add_argument("--journal", required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "inventory":
            plan = build_plan(Path(args.source_data_root), Path(args.source_fonts_dir))
            totals: dict[str, int] = {}
            counts: dict[str, int] = {}
            for record in plan.records:
                totals[record.target_kind] = (
                    totals.get(record.target_kind, 0) + record.size
                )
                counts[record.target_kind] = counts.get(record.target_kind, 0) + 1
            print(
                json.dumps(
                    {
                        "plan_digest": plan.digest(),
                        "total_bytes": plan.total_bytes,
                        "files": len(plan.records),
                        "per_target": {
                            kind: {"files": counts[kind], "bytes": totals[kind]}
                            for kind in sorted(totals)
                        },
                    },
                    indent=2,
                )
            )
            return 0
        if args.command == "status":
            journal = Path(args.journal)
            if not journal.is_file():
                print(json.dumps({"phase": "absent"}))
                return 0
            data = json.loads(journal.read_text(encoding="utf-8"))
            print(
                json.dumps(
                    {
                        "phase": data.get("phase"),
                        "run_id": data.get("run_id"),
                        "plan_digest": data.get("plan_digest"),
                        "placed": len(data.get("placed", [])),
                    },
                    indent=2,
                )
            )
            return 0
        if args.command == "run":
            plan = build_plan(Path(args.source_data_root), Path(args.source_fonts_dir))
            runner = MigrationRunner(
                plan=plan,
                targets=_targets(args),
                journal_path=Path(args.journal),
                restore_point=Path(args.restore_point),
                confirm_stack_stopped=args.i_confirm_stack_stopped,
                expected_prefix=args.expected_prefix,
            )
            print(json.dumps({"phase": runner.run(), "run_id": runner.run_id}))
            return 0
        if args.command == "rollback":
            # Rollback is journal-driven: the runner adopts the original
            # run's identity from the journal (t080 f004).  An explicit
            # empty plan replaces the old missing-path construction,
            # which build_plan now refuses (t080 f002).
            runner = MigrationRunner(
                plan=MigrationPlan.empty(),
                targets=_targets(args),
                journal_path=Path(args.journal),
            )
            print(json.dumps({"phase": runner.rollback()}))
            return 0
    except WriterActiveError as exc:
        print(f"writer refusal: {exc}", file=sys.stderr)
        return 2
    except MigrationError as exc:
        print(f"migration failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
