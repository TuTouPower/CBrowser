"""Verify the built frontend contains vendored Selkies assets and the adapter."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
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


# Build-stamp input contract (t024 AC-016/A51).  The stamp records the exact
# input set that produced dist; generation and verification share this one
# definition so the two can never drift apart.
#
# - REQUIRED_INPUTS must exist or no stamp may be generated at all.
# - CONFIG_INPUTS are recorded present-or-absent; adding one later makes an
#   old dist stale.
# - Everything under src/ and public/ is an input; adding or deleting a file
#   changes the recorded set.
# - Vite root env files (.env, .env.*) at the frontend root are inputs by
#   Vite's own loading convention -- only files inside that declared
#   boundary are read, never arbitrary environment files.
# - Process environment values count only for names in ENV_VALUE_ALLOWLIST
#   (empty today: the build consumes no VITE_* values); only their hashes
#   are recorded.
REQUIRED_INPUTS = ("index.html", "package.json", "package-lock.json")
# Source directories that must exist for a stamp to be meaningful: a tree
# without src/ is not a buildable frontend, and silently stamping it would
# let an empty input set self-certify (t024 AC-016, review f008).
REQUIRED_DIRS = ("src",)
CONFIG_INPUTS = (
    "vite.config.ts",
    "vite.selkies.config.ts",
    "tsconfig.json",
)
REPO_INPUTS = ("DESIGN.md",)
SOURCE_DIRS = ("src", "public")
ENV_VALUE_ALLOWLIST: tuple[str, ...] = ()
STAMP_VERSION = 2


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frontend_input_manifest(
    frontend_dir: Path = REPO_ROOT / "src" / "frontend",
) -> dict:
    """Compute the declared build-input set with per-file content hashes.

    Raises RuntimeError when a required input is missing, so neither stamp
    generation nor freshness verification can proceed on an incomplete
    source tree.
    """
    files: dict[str, str] = {}
    for name in REQUIRED_INPUTS:
        path = frontend_dir / name
        if not path.is_file():
            raise RuntimeError(
                f"Required frontend build input missing: {path}; cannot stamp or verify"
            )
        files[name] = _file_sha256(path)
    for name in CONFIG_INPUTS:
        path = frontend_dir / name
        if path.is_file():
            files[name] = _file_sha256(path)
    for name in REPO_INPUTS:
        path = REPO_ROOT / name
        if path.is_file():
            files[f"repo:{name}"] = _file_sha256(path)
    for dirname in REQUIRED_DIRS:
        if not (frontend_dir / dirname).is_dir():
            raise RuntimeError(
                f"Required frontend source directory missing: {frontend_dir / dirname}; "
                "cannot stamp or verify"
            )
    for dirname in SOURCE_DIRS:
        root = frontend_dir / dirname
        if root.is_dir():
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    rel = path.relative_to(frontend_dir).as_posix()
                    files[rel] = _file_sha256(path)
    for path in sorted(frontend_dir.iterdir()):
        if path.is_file() and (path.name == ".env" or path.name.startswith(".env.")):
            files[path.name] = _file_sha256(path)
    env: dict[str, str] = {}
    for name in ENV_VALUE_ALLOWLIST:
        if name in os.environ:
            env[name] = hashlib.sha256(os.environ[name].encode()).hexdigest()
    return {"files": files, "env": env}


def _manifest_digest(manifest: dict) -> str:
    digest = hashlib.sha256()
    for rel in sorted(manifest["files"]):
        digest.update(rel.encode())
        digest.update(b"\0")
        digest.update(manifest["files"][rel].encode())
        digest.update(b"\0")
    for name in sorted(manifest["env"]):
        digest.update(f"env:{name}".encode())
        digest.update(b"\0")
        digest.update(manifest["env"][name].encode())
        digest.update(b"\0")
    return digest.hexdigest()


def frontend_source_hash(frontend_dir: Path = REPO_ROOT / "src" / "frontend") -> str:
    """Hash all source inputs that must be reflected in a fresh dist build."""
    return _manifest_digest(frontend_input_manifest(frontend_dir))


def write_frontend_build_stamp(
    dist_dir: Path, frontend_dir: Path = REPO_ROOT / "src" / "frontend"
) -> Path:
    manifest = frontend_input_manifest(frontend_dir)
    stamp = dist_dir / STAMP_NAME
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(
        json.dumps(
            {
                "version": STAMP_VERSION,
                "source_sha256": _manifest_digest(manifest),
                "files": manifest["files"],
                "env": manifest["env"],
            },
            sort_keys=True,
        )
        + "\n",
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
        recorded = json.loads(stamp.read_text(encoding="utf-8"))
        recorded_files = recorded["files"]
        recorded_env = recorded["env"]
        recorded_digest = recorded["source_sha256"]
        if recorded["version"] != STAMP_VERSION or not isinstance(
            recorded_files, dict
        ) or not isinstance(recorded_env, dict):
            raise ValueError("stamp shape")
    except (OSError, ValueError, KeyError, TypeError):
        raise RuntimeError("Frontend build stamp is unreadable; rebuild required") from None
    current = frontend_input_manifest(frontend_dir)
    if (
        recorded_files != current["files"]
        or recorded_env != current["env"]
        or recorded_digest != _manifest_digest(current)
    ):
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
    for utility in (".bg-primary", "--color-surface"):
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
