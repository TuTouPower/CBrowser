#!/usr/bin/env python3
"""Deploy-time named-volume operations (t080 / ADR 029).

Invoked by scripts/deploy.sh inside a throwaway API-image container with
the target volumes mounted; deploy.sh never writes into a volume from
the host.

    deploy_volume_ops.py init-layout --data-root /data --runtime-root /runtime
    deploy_volume_ops.py copy-into --source /src/Caddyfile --dest-dir /data/network
    deploy_volume_ops.py verify-engine-cache --cache-dir /data/engine-cache
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "backend"))

DATA_LAYOUT = (
    "profiles",
    "runtime",
    "runtime-events",
    "artifacts",
    "spool",
    "control",
    "control/gates",
    "engine-cache/geoip",
    "network",
)
RUNTIME_LAYOUT = ("gates", "sockets", ".secrets")


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _stamp_volume_identity(root: Path, prefix: str, kind: str) -> None:
    """Write the volume identity marker the migration ownership check
    (AC-004) verifies before switching any data (t080 f003)."""
    marker = root / ".cbrowser-volume.json"
    payload = json.dumps(
        {"volume": f"{prefix}-{kind}", "prefix": prefix}, sort_keys=True
    )
    with marker.open("w", encoding="utf-8") as handle:
        handle.write(payload + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _init_layout(args: argparse.Namespace) -> int:
    data_root = Path(args.data_root)
    runtime_root = Path(args.runtime_root)
    for rel in DATA_LAYOUT:
        (data_root / rel).mkdir(parents=True, exist_ok=True)
    for rel in RUNTIME_LAYOUT:
        (runtime_root / rel).mkdir(parents=True, exist_ok=True)
    if args.prefix:
        _stamp_volume_identity(data_root, args.prefix, "data")
        _stamp_volume_identity(runtime_root, args.prefix, "runtime")
        if args.fonts_root:
            fonts_root = Path(args.fonts_root)
            fonts_root.mkdir(parents=True, exist_ok=True)
            _stamp_volume_identity(fonts_root, args.prefix, "fonts")
    return 0


def _copy_into(args: argparse.Namespace) -> int:
    source = Path(args.source)
    dest_dir = Path(args.dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    destination = dest_dir / source.name
    with source.open("rb") as src, destination.open("wb") as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())
    _fsync_dir(dest_dir)
    return 0


def _verify_engine_cache(args: argparse.Namespace) -> int:
    cache_dir = Path(args.cache_dir)
    if not cache_dir.is_dir():
        return 0
    from cbrowser.engine_artifacts import main as engine_main

    return engine_main(
        [
            "verify-cache",
            "--cache-dir",
            str(cache_dir),
            "--allow-empty",
            "--no-version-probe",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init-layout")
    p.add_argument("--data-root", required=True)
    p.add_argument("--runtime-root", required=True)
    p.add_argument("--fonts-root")
    p.add_argument("--prefix")
    p.set_defaults(func=_init_layout)
    p = sub.add_parser("copy-into")
    p.add_argument("--source", required=True)
    p.add_argument("--dest-dir", required=True)
    p.set_defaults(func=_copy_into)
    p = sub.add_parser("verify-engine-cache")
    p.add_argument("--cache-dir", required=True)
    p.set_defaults(func=_verify_engine_cache)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
