#!/usr/bin/env python3
"""Ensure the pinned Selkies wheel is cached (gate pre-step, offline).

``tests/unit/test_t045_selkies_wheel_cache.py`` and the E2E adapter suites
require the pinned wheel bytes at ``.scratch/selkies_wheels`` (or
``CBROWSER_SELKIES_WHEEL_CACHE``), which a clean clone does not have because
``.scratch`` is gitignored.  Per ``docs/specs/gate_verification.md:53`` and
``docs/blueprint/testing.md:372`` this pre-step initiates NO public network
request: a missing or hash-mismatched cache fails closed with a clear
message (same rule as ``vendor_selkies_web(..., allow_download=False)`` and
the E2E collection preflight — no fallback to the public wheel index).
Populate the cache out of band (pinned file + SHA256, see
``scripts/vendor_selkies_web.py``) and re-run the gate.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from scripts import vendor_selkies_web as vendor_module


def ensure_wheel_cache(cache_dir: Path) -> Path:
    """Return the verified pinned wheel; fail closed when absent/mismatched.

    Offline: never initiates a public download.  A missing file or a
    SHA256 mismatch raises (fail closed, no network fallback).
    """
    wheel_path = cache_dir / vendor_module.PINNED_WHEEL_FILENAME
    if not wheel_path.is_file():
        raise RuntimeError(
            f"Local Selkies wheel cache missing: {wheel_path}; "
            f"expected SHA256 {vendor_module.PINNED_WHEEL_SHA256} "
            f"(no public download; populate the cache out of band)"
        )
    actual = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
    if actual != vendor_module.PINNED_WHEEL_SHA256:
        raise RuntimeError(
            f"Local Selkies wheel SHA256 mismatch: {wheel_path}: "
            f"{vendor_module.PINNED_WHEEL_SHA256} != {actual} "
            f"(no public download; re-populate the cache)"
        )
    return wheel_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        wheel = ensure_wheel_cache(args.cache_dir)
    except Exception as exc:  # noqa: BLE001 - fail closed with a clear message
        print(f"selkies wheel cache unavailable: {exc}", file=sys.stderr)
        return 1
    print(f"selkies wheel: {wheel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
