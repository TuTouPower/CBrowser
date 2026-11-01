"""Verify the built frontend contains vendored Selkies assets and the adapter."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:  # repository layout
    from scripts.vendor_selkies_web import verify_manifest
except ImportError:  # image layout: /app/scripts/verify_frontend_dist.py
    from vendor_selkies_web import verify_manifest

DEFAULT_DIST = REPO_ROOT / "src" / "frontend" / "dist"
DEFAULT_MANIFEST = REPO_ROOT / "config" / "selkies" / "selkies_web_sha256.txt"

ADAPTER_TAG = '<script src="./selkies_adapter.js"></script>'
ADAPTER_MARKERS = ("__cbrowserAdapterSource", "__cbrowserShimInstalled")
MODULE_TAG = re.compile(r'<script[^>]+type="module"[^>]*>')


def verify_frontend_dist(dist_dir: Path, manifest_path: Path) -> None:
    """Fail closed when the production dist is incomplete or mismatched."""
    selkies_dir = dist_dir / "selkies"
    index_path = selkies_dir / "index.html"
    adapter_path = selkies_dir / "selkies_adapter.js"

    if not index_path.is_file():
        raise RuntimeError(f"Selkies index missing: {index_path}")
    if not adapter_path.is_file():
        raise RuntimeError(f"Selkies adapter missing: {adapter_path}")

    adapter = adapter_path.read_text(encoding="utf-8")
    if not adapter.strip():
        raise RuntimeError("Selkies adapter is empty")
    if re.search(r"^\s*(import|export)\s", adapter, re.MULTILINE):
        raise RuntimeError("Selkies adapter must be a classic IIFE script")
    for marker in ADAPTER_MARKERS:
        if marker not in adapter:
            raise RuntimeError(f"Selkies adapter missing marker: {marker}")

    index = index_path.read_text(encoding="utf-8")
    if index.count(ADAPTER_TAG) != 1:
        raise RuntimeError("Selkies index must contain exactly one adapter tag")
    module_match = MODULE_TAG.search(index)
    if module_match is None:
        raise RuntimeError("Selkies index has no official module bundle")
    if index.index(ADAPTER_TAG) > module_match.start():
        raise RuntimeError("Selkies adapter must load before the module bundle")

    verify_manifest(selkies_dir, manifest_path=manifest_path, allow_patched=True)
    print(f"Verified frontend dist: {selkies_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Verify vendored Selkies assets, hash manifest and built adapter in dist"
        )
    )
    parser.add_argument(
        "--dist",
        type=Path,
        default=DEFAULT_DIST,
        help="Frontend dist directory to verify",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Reference sha256 manifest file",
    )
    args = parser.parse_args()
    verify_frontend_dist(args.dist, args.manifest)


if __name__ == "__main__":
    main()
