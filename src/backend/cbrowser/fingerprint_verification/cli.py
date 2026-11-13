"""CLI for local fingerprint measurement, diff comparison, and upgrade gate."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from cbrowser.domain.models import ProfileConfig
from cbrowser.engine_artifacts import EngineArtifactError

from .comparator import compare_reports, render_diff_markdown
from .probe_collector import measure_profile_with_browser_runner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="CBrowser local fingerprint baseline & engine upgrade regression gate"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    m = sub.add_parser("measure", help="Measure a ProfileConfig against pinned engine")
    m.add_argument("--profile-id", required=True)
    m.add_argument("--config-version", type=int, default=1)
    m.add_argument("--config-json", type=Path, required=True)
    m.add_argument("--engine-cache", type=Path, required=True)
    m.add_argument("--engine-build", default=None)
    m.add_argument("--fonts-dir", type=Path, default=None)
    m.add_argument("--samples", type=int, default=3)
    m.add_argument("--no-tls", action="store_true")
    m.add_argument("--display", default=":165")
    m.add_argument("--reuse-user-data", action="store_true")
    m.add_argument("--out", type=Path, required=True)

    c = sub.add_parser("compare", help="Compare baseline and candidate reports")
    c.add_argument("--baseline", type=Path, required=True)
    c.add_argument("--candidate", type=Path, required=True)
    c.add_argument("--approve-tls-shuffle", action="store_true")
    c.add_argument("--approve-storage-usage", action="store_true")
    c.add_argument("--out-json", type=Path, required=True)
    c.add_argument("--out-md", type=Path, default=None)

    args = parser.parse_args(argv)
    if args.command == "measure":
        raw_cfg = json.loads(args.config_json.read_text(encoding="utf-8"))
        cfg = ProfileConfig.model_validate(raw_cfg)
        try:
            report = asyncio.run(
                measure_profile_with_browser_runner(
                    profile_id=args.profile_id,
                    config_version=args.config_version,
                    config=cfg,
                    engine_cache_dir=args.engine_cache,
                    engine_build=args.engine_build,
                    fonts_dir=args.fonts_dir,
                    samples=args.samples,
                    use_tls=not args.no_tls,
                    display=args.display,
                    reuse_user_data=args.reuse_user_data,
                )
            )
        except EngineArtifactError as exc:
            print(f"Measurement refused ({exc.code}): {exc.detail}", file=sys.stderr)
            return 2
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(json.dumps({
            "profile_id": args.profile_id,
            "config_version": args.config_version,
            "engine_build": report["engine_artifact"]["engine_build"],
            "consistency_verdict": report["consistency"]["verdict"],
            "out": str(args.out),
        }))
        return 0

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    rules: dict[str, Any] = {}
    if args.approve_tls_shuffle:
        rules["tls_extension_shuffle_via_ja4"] = True
    if args.approve_storage_usage:
        rules["ignore_stateful_storage_usage"] = True
    diff = compare_reports(baseline, candidate, approved_rules=rules or None)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(diff, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if args.out_md is not None:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(render_diff_markdown(diff), encoding="utf-8")
    print(json.dumps({
        "upgrade_decision": diff["upgrade_decision"],
        "blocking_reasons": diff["blocking_reasons"],
        "diff_count": diff["summary"]["diff_count"],
    }))
    return 0 if diff["upgrade_decision"] == "approved" else 1


if __name__ == "__main__":
    raise SystemExit(main())
