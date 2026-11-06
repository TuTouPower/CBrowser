"""Content-addressed, immutable platform font sets.

Detection font names are pure file names drawn from real, present font files.
Selection basis:

- ``windows`` (8): from the Windows 11 Enterprise evaluation ISO fonts
  (``.scratch/t041/win_fonts/Windows/Fonts``), the eight core TrueType families
  most frequently probed by cross-site font fingerprinting scripts, including
  the ClearType default Calibri.
- ``office`` (10): from the same Windows Fonts directory, the Microsoft Office
  ClearType families (Calibri / Cambria / Candara / Consolas / Constantia /
  Corbel) plus their bold, italic and bold-italic variants.
- ``macos`` (20): from the local ``/System/Library/Fonts``, its ``Supplemental``
  directory and the PingFang asset under ``/System/Library/AssetsV2/``; twenty
  representative Latin and CJK families covering the fonts observed in the
  d033 fontconfig isolation probe, with PingFang as the distinguishing CJK face.

Only file names are recorded here; font bytes are never vendored into the
repository or any image.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

LOGGER = logging.getLogger(__name__)

FONTS_DIR_ENV = "CBROWSER_FONTS_DIR"
PLATFORMS: tuple[str, ...] = ("windows", "macos")
FONT_EXTENSIONS = {".ttf", ".ttc", ".otf", ".otc"}
SET_ID_PATTERN = re.compile(r"^[a-f0-9]{32,64}$")
HEX64_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_TEMP_MARKERS = ("~", ".tmp", ".temp", ".swp", ".part", ".crdownload", ".bak")

DETECTION_FONTS: dict[str, tuple[str, ...]] = {
    "windows": (
        "arial.ttf",
        "calibri.ttf",
        "cour.ttf",
        "georgia.ttf",
        "tahoma.ttf",
        "times.ttf",
        "trebuc.ttf",
        "verdana.ttf",
    ),
    "office": (
        "calibri.ttf",
        "calibrib.ttf",
        "calibrii.ttf",
        "calibriz.ttf",
        "cambria.ttc",
        "cambriab.ttf",
        "Candara.ttf",
        "consola.ttf",
        "constan.ttf",
        "corbel.ttf",
    ),
    "macos": (
        "PingFang.ttc",
        "Hiragino Sans GB.ttc",
        "STHeiti Light.ttc",
        "STHeiti Medium.ttc",
        "Songti.ttc",
        "Helvetica.ttc",
        "HelveticaNeue.ttc",
        "LucidaGrande.ttc",
        "Menlo.ttc",
        "Monaco.ttf",
        "Geneva.ttf",
        "Courier.ttc",
        "Times.ttc",
        "Avenir.ttc",
        "Avenir Next.ttc",
        "AppleSDGothicNeo.ttc",
        "Arial.ttf",
        "Arial Unicode.ttf",
        "Times New Roman.ttf",
        "Verdana.ttf",
    ),
}


def _is_font_file(name: str) -> bool:
    if not name or name.startswith(".") or name.startswith("~"):
        return False
    if name.lower().endswith(_TEMP_MARKERS):
        return False
    return Path(name).suffix.lower() in FONT_EXTENSIONS


def _safe_name(name: object) -> bool:
    if not isinstance(name, str) or not name or name in (".", ".."):
        return False
    if name.startswith(".") or name.startswith("~"):
        return False
    if "/" in name or "\\" in name or "\0" in name:
        return False
    return Path(name).name == name and Path(name).suffix.lower() in FONT_EXTENSIONS


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_root(root: Path | str | None) -> Path | None:
    if root is not None:
        return Path(root)
    value = os.environ.get(FONTS_DIR_ENV)
    return Path(value) if value else None


def _read_manifest(set_dir: Path) -> dict:
    try:
        data = json.loads((set_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _entry_pair(entry: object) -> tuple[str, str]:
    if isinstance(entry, dict):
        return str(entry["name"]), str(entry["sha256"])
    if isinstance(entry, (tuple, list)):
        if len(entry) == 2:
            return str(entry[0]), str(entry[1])
        if len(entry) == 3:
            return str(entry[0]), str(entry[2])
    raise TypeError(f"Unsupported font entry: {entry!r}")


def compute_set_id(entries) -> str:
    """Return the content-only id: sha256 over sorted ``name + NUL + sha256``.

    Only font names and content hashes participate; platform, source, source
    version and created_at never affect the resulting id.
    """
    pairs = [_entry_pair(entry) for entry in entries]
    hasher = hashlib.sha256()
    for name, digest in sorted(pairs, key=lambda pair: pair[0]):
        hasher.update(name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(digest.encode("ascii"))
    return hasher.hexdigest()


def discover_font_files(source_dirs) -> list[tuple[str, str, str]]:
    """Recursively collect ``(name, absolute_path, sha256)`` sorted by name."""
    found: dict[str, tuple[str, str]] = {}
    for source_dir in source_dirs:
        base = Path(source_dir)
        if not base.is_dir():
            LOGGER.warning("Font source directory does not exist: %s", base)
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or not _is_font_file(path.name):
                continue
            resolved = path.resolve()
            digest = _sha256_file(resolved)
            previous = found.get(path.name)
            if previous is not None and previous[1] != digest:
                raise ValueError(
                    f"Conflicting content for font name {path.name!r}: "
                    f"{previous[0]} vs {resolved}"
                )
            found[path.name] = (str(resolved), digest)
    return [(name, found[name][0], found[name][1]) for name in sorted(found)]


def _result(
    platform: str,
    set_id: str,
    target: Path,
    created: bool,
    integrity: dict,
) -> dict:
    return {
        "platform": platform,
        "set_id": set_id,
        "created": created,
        "dir": str(target),
        "file_count": integrity["file_count"],
        "integrity": integrity,
    }


def import_font_set(
    platform: str,
    source_dirs,
    source_version: str,
    *,
    root: Path | str | None = None,
    source: str | None = None,
    created_at: str | datetime | None = None,
) -> dict:
    """Publish fonts as an immutable set under ``root/platform/set_id``.

    An existing set directory is verified read-only and returned unchanged;
    nothing is overwritten or deleted.
    """
    if platform not in PLATFORMS:
        raise ValueError(f"Invalid platform: {platform!r}")
    base = _resolve_root(root)
    if base is None:
        raise ValueError(f"Font root is unset: pass root or set {FONTS_DIR_ENV}")
    entries = discover_font_files(source_dirs)
    if not entries:
        raise ValueError("No font files found in the source directories")

    set_id = compute_set_id(entries)
    platform_dir = base / platform
    target = platform_dir / set_id
    if target.is_dir():
        LOGGER.info("Font set already present, leaving it untouched: %s", target)
        return _result(platform, set_id, target, False, check_font_set(target))

    platform_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{set_id}-", dir=str(platform_dir)))
    try:
        for name, src_path, _ in entries:
            (staging / name).write_bytes(Path(src_path).read_bytes())
        if created_at is None:
            stamp = datetime.now(timezone.utc).isoformat()
        elif isinstance(created_at, datetime):
            stamp = created_at.isoformat()
        else:
            stamp = str(created_at)
        manifest = {
            "platform": platform,
            "source": source
            if source is not None
            else ", ".join(str(directory) for directory in source_dirs),
            "source_version": source_version,
            "created_at": stamp,
            "files": [
                {"name": name, "sha256": digest} for name, _, digest in entries
            ],
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if target.is_dir():
            LOGGER.info(
                "Font set appeared concurrently, leaving it untouched: %s", target
            )
            return _result(platform, set_id, target, False, check_font_set(target))
        os.replace(str(staging), str(target))
        LOGGER.info(
            "Published font set %s/%s with %d files",
            platform,
            set_id,
            len(entries),
        )
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return _result(platform, set_id, target, True, check_font_set(target))


def check_font_set(directory: Path | str) -> dict:
    """Verify a font set against its manifest and report detection coverage."""
    target = Path(directory)
    problems: list[str] = []
    missing_fonts: list[str] = []
    hash_mismatches: list[str] = []
    unregistered_fonts: list[str] = []

    manifest = _read_manifest(target)
    if not (target / "manifest.json").is_file():
        problems.append("manifest.json is missing")
    elif not manifest:
        problems.append("manifest.json is missing or unparseable")

    files = manifest.get("files")
    if not isinstance(files, list):
        problems.append("manifest files must be a list")
        files = []
    if not files:
        problems.append("manifest files is empty")

    registered: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict):
            problems.append("manifest entry must be an object")
            continue
        name = entry.get("name")
        digest = entry.get("sha256")
        if not _safe_name(name):
            problems.append(f"unsafe manifest entry name: {name!r}")
            continue
        registered.add(name)
        if not isinstance(digest, str) or not HEX64_PATTERN.fullmatch(digest):
            problems.append(f"invalid sha256 for {name}")
            continue
        font_path = target / name
        if not font_path.is_file():
            missing_fonts.append(name)
            problems.append(f"missing font file: {name}")
            continue
        if _sha256_file(font_path) != digest:
            hash_mismatches.append(name)
            problems.append(f"sha256 mismatch: {name}")

    disk_names: set[str] = set()
    if target.is_dir():
        for path in sorted(target.iterdir()):
            if path.is_file() and _is_font_file(path.name):
                disk_names.add(path.name)
                if path.name not in registered:
                    unregistered_fonts.append(path.name)
    if unregistered_fonts:
        problems.append(
            "unregistered font files: " + ", ".join(sorted(unregistered_fonts))
        )

    detection: dict[str, dict] = {}
    for label, names in DETECTION_FONTS.items():
        detection[label] = {
            "total": len(names),
            "matched": sum(1 for name in names if name in disk_names),
            "missing": [name for name in names if name not in disk_names],
        }

    return {
        "ok": not problems,
        "problems": problems,
        "missing_fonts": sorted(missing_fonts),
        "hash_mismatches": sorted(hash_mismatches),
        "unregistered_fonts": sorted(unregistered_fonts),
        "file_count": len(files),
        "detection": detection,
    }


def list_font_sets(root: Path | str | None = None) -> list[dict]:
    base = _resolve_root(root)
    if base is None or not base.is_dir():
        return []
    items: list[dict] = []
    for platform in PLATFORMS:
        platform_dir = base / platform
        if not platform_dir.is_dir():
            continue
        for set_dir in sorted(platform_dir.iterdir()):
            if not set_dir.is_dir():
                continue
            integrity = check_font_set(set_dir)
            manifest = _read_manifest(set_dir)
            items.append(
                {
                    "platform": platform,
                    "set_id": set_dir.name,
                    "source": manifest.get("source"),
                    "source_version": manifest.get("source_version"),
                    "created_at": manifest.get("created_at"),
                    "integrity": integrity,
                    "file_count": integrity["file_count"],
                }
            )
    items.sort(key=lambda item: (item["platform"], item["set_id"]))
    return items


def default_font_set(platform: str, root: Path | str | None = None) -> str | None:
    if platform not in PLATFORMS:
        return None
    candidates: list[tuple[datetime, str]] = []
    for item in list_font_sets(root):
        if item["platform"] != platform or not item["integrity"]["ok"]:
            continue
        created_at = item.get("created_at")
        if not isinstance(created_at, str):
            continue
        try:
            stamp = datetime.fromisoformat(created_at)
        except ValueError:
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        candidates.append((stamp, item["set_id"]))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: (pair[0], pair[1]))
    return candidates[-1][1]


def get_font_set(
    platform: str,
    set_id: str,
    root: Path | str | None = None,
) -> tuple[Path, dict] | None:
    if platform not in PLATFORMS:
        return None
    if not isinstance(set_id, str) or not SET_ID_PATTERN.fullmatch(set_id):
        return None
    base = _resolve_root(root)
    if base is None:
        return None
    target = base / platform / set_id
    if not target.is_dir() or not (target / "manifest.json").is_file():
        return None
    manifest = _read_manifest(target)
    if not manifest or manifest.get("platform") != platform:
        return None
    return (target, manifest)
