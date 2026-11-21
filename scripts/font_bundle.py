"""Publish the content-addressed font sets carried in a Browser image."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

from cbrowser.font_sets.manifest import (  # noqa: E402
    FONT_EXTENSIONS,
    PLATFORMS,
    SET_ID_PATTERN,
    check_font_set,
    compute_set_id,
    discover_font_files,
    import_font_set,
)

LOGGER = logging.getLogger(__name__)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def seed(archive: Path, lock: dict, destination: Path) -> None:
    """Validate both input sets before publishing either into the named volume."""
    if digest(archive) != lock["sha256"]:
        raise ValueError("Font bundle SHA-256 mismatch")

    locked_sets = lock["sets"]
    if (
        not isinstance(locked_sets, dict)
        or set(locked_sets) != set(PLATFORMS)
        or any(
            not isinstance(set_id, str) or len(set_id) != 64 or not SET_ID_PATTERN.fullmatch(set_id)
            for set_id in locked_sets.values()
        )
    ):
        raise ValueError("Font lock must contain valid Windows and macOS set IDs")

    sets = {PurePosixPath(platform, set_id) for platform, set_id in locked_sets.items()}
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".font_bundle_", dir=destination) as directory:
        stage = Path(directory)
        with tarfile.open(archive, "r|zst") as bundle:
            for member in bundle:
                path = PurePosixPath(member.name)
                if member.isdir() and any(path in (*item.parents, item) for item in sets):
                    continue
                if (
                    not member.isfile()
                    or path.parent not in sets
                    or (path.name != "manifest.json" and path.suffix.lower() not in FONT_EXTENSIONS)
                ):
                    raise ValueError(f"Unexpected archive member: {member.name!r}")
                target = stage.joinpath(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as output, bundle.extractfile(member) as contents:
                    shutil.copyfileobj(contents, output)

        manifests = {}
        for path in sorted(sets):
            source = stage.joinpath(*path.parts)
            if not check_font_set(source)["ok"]:
                raise ValueError(f"Invalid bundled font set: {path}")
            manifest = json.loads((source / "manifest.json").read_text())
            set_id = compute_set_id(discover_font_files([source]))
            if manifest["platform"] != path.parts[0] or set_id != path.name:
                raise ValueError(f"Bundled font identity mismatch: {path}")
            manifests[path] = manifest
        for path, manifest in manifests.items():
            import_font_set(
                manifest["platform"],
                [stage.joinpath(*path.parts)],
                manifest["source_version"],
                root=destination,
                source=manifest["source"],
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("lock", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--compare-lock-from-stdin", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        image_lock = json.loads(args.lock.read_text())
        if args.compare_lock_from_stdin:
            deployment_lock = json.load(sys.stdin)
            if any(image_lock[key] != deployment_lock[key] for key in ("sha256", "sets")):
                raise ValueError("Browser image and deployment font locks differ")
        seed(args.archive, image_lock, args.destination)
    except (OSError, ValueError, KeyError, tarfile.TarError) as exc:
        LOGGER.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
