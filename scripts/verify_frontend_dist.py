"""Verify the built frontend contains vendored Selkies assets and the adapter."""

from __future__ import annotations

import argparse
import hashlib
import json
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
STAMP_NAME = "build-stamp.json"

ADAPTER_TAG = '<script src="./selkies_adapter.js"></script>'
ADAPTER_MARKERS = ("__SELKIES_STREAMING_MODE__", "__getWebRTCStats")
MODULE_TAG = re.compile(r'<script[^>]+type="module"[^>]*>')


def frontend_source_hash(frontend_dir: Path = REPO_ROOT / "src" / "frontend") -> str:
    """Hash all source inputs that must be reflected in a fresh dist build."""
    digest = hashlib.sha256()
    candidates = [frontend_dir / "index.html", frontend_dir / "package.json"]
    for name in ("vite.config.ts", "vite.selkies.config.ts", "tailwind.config.ts", "tsconfig.json"):
        candidates.append(frontend_dir / name)
    candidates.append(frontend_dir / "package-lock.json")
    for root in (frontend_dir / "src", frontend_dir / "public"):
        candidates.extend(
            path for path in sorted(root.rglob("*")) if path.is_file()
        )
    for path in candidates:
        if not path.is_file():
            continue
        digest.update(path.relative_to(frontend_dir).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def write_frontend_build_stamp(
    dist_dir: Path, frontend_dir: Path = REPO_ROOT / "src" / "frontend"
) -> Path:
    stamp = dist_dir / STAMP_NAME
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(
        json.dumps({"source_sha256": frontend_source_hash(frontend_dir)}) + "\n",
        encoding="utf-8",
    )
    return stamp


def verify_frontend_build_freshness(
    dist_dir: Path, frontend_dir: Path = REPO_ROOT / "src" / "frontend"
) -> None:
    stamp = dist_dir / STAMP_NAME
    if not stamp.is_file():
        raise RuntimeError(
            f"Frontend build stamp missing at {stamp}; rebuild with npm run build"
        )
    try:
        recorded = json.loads(stamp.read_text(encoding="utf-8"))["source_sha256"]
    except (OSError, ValueError, KeyError, TypeError):
        raise RuntimeError("Frontend build stamp is unreadable; rebuild required") from None
    current = frontend_source_hash(frontend_dir)
    if recorded != current:
        raise RuntimeError(
            "Frontend dist is stale relative to current source; run npm run build"
        )


def verify_frontend_dist(
    dist_dir: Path, manifest_path: Path, *, check_freshness: bool = False
) -> None:
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

    css_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in (dist_dir / "assets").glob("*.css")
    )
    for utility in (".bg-primary", ".text-primary-foreground"):
        if utility not in css_text:
            raise RuntimeError(f"Generated CSS is missing {utility}")
    if check_freshness:
        verify_frontend_build_freshness(dist_dir)
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
    parser.add_argument("--check-freshness", action="store_true")
    args = parser.parse_args()
    verify_frontend_dist(args.dist, args.manifest, check_freshness=args.check_freshness)


if __name__ == "__main__":
    main()
