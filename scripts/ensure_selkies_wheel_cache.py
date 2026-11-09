#!/usr/bin/env python3
"""Ensure the pinned Selkies wheel is cached (gate pre-step).

``tests/unit/test_t045_selkies_wheel_cache.py`` and the E2E adapter suites
require the pinned wheel bytes at ``.scratch/selkies_wheels`` (or
``CBROWSER_SELKIES_WHEEL_CACHE``), which a clean clone does not have because
``.scratch`` is gitignored. The gate runs this before any suite so a clean
clone downloads the SHA256-pinned wheel once instead of failing in unit.
Warm runs reuse the cached file without any download.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts import vendor_selkies_web as vendor_module


def ensure_wheel_cache(cache_dir: Path) -> Path:
    """Return the verified pinned wheel, downloading it when absent."""
    return vendor_module.download_wheel(cache_dir)


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
