#!/usr/bin/env python3
"""Build the controlled Selkies server package from the pinned upstream wheel.

Route decided by spike s020 and adopted in t063: selkies 2.2.1 exposes no
public extension point for the WebRTC service class or the X11 keyboard,
so CBrowser ships a *controlled build* of the pinned upstream wheel --
the pristine wheel (SHA256 pinned by the committed identity manifest)
plus an ordered series of small, explicit, build-time patches under
``config/selkies/patches/``.  No upstream source is vendored into the
business tree and nothing is patched at runtime.

Identity is fully recorded in ``config/selkies/selkies_controlled_build.json``:
upstream version/filename/SHA256/URL, every patch file with its SHA256
and target, the controlled version and the expected output wheel SHA256,
and the web-client manifest (extracted from the same upstream wheel by
``scripts/vendor_selkies_web.py``) with its SHA256, so the server package
and the client assets are traceable to one pinned artifact.

The build is deterministic: fixed zip timestamps, fixed permissions,
ZIP_STORED, regenerated RECORD.  Same inputs produce the same bytes.
Every check fails closed: a hash mismatch, a patch whose context does
not match the pinned source exactly, or a drifted manifest aborts.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST_PATH = REPO_ROOT / "config" / "selkies" / "selkies_controlled_build.json"
DEFAULT_PATCHES_DIR = REPO_ROOT / "config" / "selkies" / "patches"
DEFAULT_CACHE_DIR = REPO_ROOT / ".scratch" / "selkies_wheels"
DEFAULT_OUT_DIR = REPO_ROOT / ".scratch" / "selkies_controlled"

BUILDER_ID = "scripts/build_selkies_controlled.py"
FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)
FIXED_EXTERNAL_ATTR = 0o644 << 16


class ControlledBuildError(RuntimeError):
    """Fail-closed build error (hash drift, patch mismatch, bad manifest)."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_manifest(manifest_path: Path) -> dict:
    if not manifest_path.is_file():
        raise ControlledBuildError(f"identity manifest not found: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ControlledBuildError(f"identity manifest unreadable: {exc}") from None
    if manifest.get("schema") != 1:
        raise ControlledBuildError("identity manifest schema must be 1")
    return manifest


_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def apply_unified_patch(source_text: str, patch_text: str) -> tuple[str, str]:
    """Apply one single-file unified diff with zero fuzz; fail closed.

    Returns ``(patched_text, target_path)``.  Context and removed lines
    must match the source exactly at the hunk's stated position (shifted
    only by earlier hunks of the same patch); anything else aborts, so a
    patch written for another upstream version can never apply silently.
    """
    lines = patch_text.splitlines(keepends=True)
    target: str | None = None
    source_path: str | None = None
    hunks: list[tuple[int, int, int, list[str], list[str]]] = []
    current: tuple[int, int, int, list[str], list[str]] | None = None
    for raw in lines:
        if raw.startswith("--- "):
            source_path = raw[4:].strip().removeprefix("a/")
            continue
        if raw.startswith("+++ "):
            target = raw[4:].strip().removeprefix("b/")
            continue
        match = _HUNK_RE.match(raw)
        if match:
            current = (
                int(match.group(1)),
                int(match.group(2)) if match.group(2) is not None else 1,
                int(match.group(4)) if match.group(4) is not None else 1,
                [],
                [],
            )
            hunks.append(current)
            continue
        if current is None:
            continue  # diff header noise (index lines etc.)
        old_lines, new_lines = current[3], current[4]
        if raw.startswith("\\"):
            raise ControlledBuildError("patches with '\\ No newline' markers are unsupported")
        prefix, body = raw[:1], raw[1:]
        if prefix == " ":
            old_lines.append(body)
            new_lines.append(body)
        elif prefix == "-":
            old_lines.append(body)
        elif prefix == "+":
            new_lines.append(body)
        elif raw.strip() == "":
            old_lines.append(raw)
            new_lines.append(raw)
        else:
            raise ControlledBuildError(f"unparseable patch line: {raw!r}")
    if target is None or source_path is None or target != source_path:
        raise ControlledBuildError("patch must name one target via --- a/X and +++ b/X")
    if not hunks:
        raise ControlledBuildError("patch contains no hunks")
    for start, declared_old, declared_new, old_lines, new_lines in hunks:
        if len(old_lines) != declared_old or len(new_lines) != declared_new:
            raise ControlledBuildError(
                f"patch hunk at line {start} declares -{declared_old}/+{declared_new} "
                f"but carries -{len(old_lines)}/+{len(new_lines)}"
            )

    source_lines = source_text.splitlines(keepends=True)
    delta = 0
    for start, _declared_old, _declared_new, old_lines, new_lines in hunks:
        index = start - 1 + delta
        if index < 0 or source_lines[index : index + len(old_lines)] != old_lines:
            raise ControlledBuildError(
                f"patch context mismatch in {target} at hunk starting line {start}"
            )
        source_lines[index : index + len(old_lines)] = new_lines
        delta += len(new_lines) - len(old_lines)
    return "".join(source_lines), target


def _record_line(path: str, data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
    return f"{path},sha256={digest},{len(data)}"


def build_controlled_wheel(
    source_wheel: Path,
    patches_dir: Path,
    manifest: dict,
    out_path: Path,
) -> dict:
    """Build the controlled wheel; return the computed identity dict."""
    upstream = manifest["upstream"]
    source_bytes = source_wheel.read_bytes()
    if _sha256(source_bytes) != upstream["wheel_sha256"]:
        raise ControlledBuildError(
            f"upstream wheel SHA256 mismatch: expected {upstream['wheel_sha256']}"
        )
    if source_wheel.name != upstream["wheel_filename"]:
        raise ControlledBuildError(
            f"upstream wheel filename mismatch: {source_wheel.name} != {upstream['wheel_filename']}"
        )

    patch_entries = manifest["patches"]
    patch_texts: dict[str, str] = {}
    for entry in patch_entries:
        patch_path = patches_dir / entry["file"]
        if not patch_path.is_file():
            raise ControlledBuildError(f"patch file missing: {patch_path}")
        patch_bytes = patch_path.read_bytes()
        if _sha256(patch_bytes) != entry["sha256"]:
            raise ControlledBuildError(f"patch SHA256 drift: {entry['file']}")
        patch_texts[entry["file"]] = patch_bytes.decode("utf-8")

    controlled_version = manifest["controlled"]["version"]
    if not controlled_version.startswith(upstream["version"] + "+"):
        raise ControlledBuildError(
            "controlled version must be '<upstream>+<local>': " + controlled_version
        )
    upstream_dist_info = f"selkies-{upstream['version']}.dist-info"
    controlled_dist_info = f"selkies-{controlled_version}.dist-info"

    build_stamp = {
        "builder": BUILDER_ID,
        "controlled_version": controlled_version,
        "identity_manifest": "config/selkies/selkies_controlled_build.json",
        "patches": [
            {"file": entry["file"], "sha256": entry["sha256"], "target": entry["target"]}
            for entry in patch_entries
        ],
        "upstream": {
            "name": upstream["name"],
            "version": upstream["version"],
            "wheel_filename": upstream["wheel_filename"],
            "wheel_sha256": upstream["wheel_sha256"],
        },
    }
    build_stamp_bytes = (
        json.dumps(build_stamp, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")

    with zipfile.ZipFile(source_wheel) as zin:
        infos = zin.infolist()
        contents: dict[str, bytes] = {info.filename: zin.read(info.filename) for info in infos}
        order = [info.filename for info in infos]

    patched_targets: set[str] = set()
    for entry in patch_entries:
        if entry["target"] not in contents:
            raise ControlledBuildError(f"patch target not in wheel: {entry['target']}")
        patched_text, target = apply_unified_patch(
            contents[entry["target"]].decode("utf-8"),
            patch_texts[entry["file"]],
        )
        if target != entry["target"]:
            raise ControlledBuildError(
                f"patch {entry['file']} targets {target}, manifest says {entry['target']}"
            )
        contents[entry["target"]] = patched_text.encode("utf-8")
        patched_targets.add(target)

    renamed: dict[str, bytes] = {}
    new_order: list[str] = []
    record_path = f"{controlled_dist_info}/RECORD"
    for name in order:
        if name.startswith(upstream_dist_info + "/"):
            new_name = controlled_dist_info + name[len(upstream_dist_info) :]
        else:
            new_name = name
        if name == f"{upstream_dist_info}/RECORD":
            continue  # regenerated below, kept at the same slot
        data = contents[name]
        if new_name == f"{controlled_dist_info}/METADATA":
            text = data.decode("utf-8")
            old_line = f"Version: {upstream['version']}\n"
            if text.count(old_line) != 1:
                raise ControlledBuildError("METADATA Version line not found exactly once")
            data = text.replace(old_line, f"Version: {controlled_version}\n").encode("utf-8")
        renamed[new_name] = data
        new_order.append(new_name)
        if new_name == "selkies/__init__.py":
            renamed["selkies/cbrowser_build.json"] = build_stamp_bytes
            new_order.append("selkies/cbrowser_build.json")
    new_order.append(record_path)
    if "selkies/cbrowser_build.json" not in renamed:
        raise ControlledBuildError("selkies/__init__.py not found; cannot place build stamp")

    record_lines = [
        _record_line(path, renamed[path]) for path in new_order if path != record_path
    ]
    record_lines.append(f"{record_path},,")
    renamed[record_path] = ("\n".join(record_lines) + "\n").encode("utf-8")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_STORED) as zout:
        for name in new_order:
            info = zipfile.ZipInfo(name, date_time=FIXED_DATE_TIME)
            info.create_system = 3
            info.external_attr = FIXED_EXTERNAL_ATTR
            zout.writestr(info, renamed[name])

    output_sha256 = _sha256(out_path.read_bytes())
    return {
        "upstream_wheel_sha256": upstream["wheel_sha256"],
        "patches": patch_entries,
        "patched_targets": sorted(patched_targets),
        "controlled_version": controlled_version,
        "wheel_filename": manifest["controlled"]["wheel_filename"],
        "wheel_sha256": output_sha256,
        "out_path": str(out_path),
    }


def _resolve_source_wheel(manifest: dict, source_arg: Path | None, allow_download: bool) -> Path:
    filename = manifest["upstream"]["wheel_filename"]
    if source_arg is not None:
        # An explicit source is authoritative: never silently fall back.
        if not source_arg.is_file():
            raise ControlledBuildError(f"explicit source wheel not found: {source_arg}")
        if _sha256(source_arg.read_bytes()) != manifest["upstream"]["wheel_sha256"]:
            raise ControlledBuildError(
                f"explicit source wheel hash mismatch: {source_arg} (fail closed)"
            )
        return source_arg
    cached = DEFAULT_CACHE_DIR / filename
    if cached.is_file():
        if _sha256(cached.read_bytes()) == manifest["upstream"]["wheel_sha256"]:
            return cached
        raise ControlledBuildError(
            f"cached wheel hash mismatch: {cached} (fail closed, no fallback)"
        )
    if not allow_download:
        raise ControlledBuildError(
            f"pinned wheel not in cache [{cached}]; "
            "populate out of band or pass --allow-download"
        )
    DEFAULT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(
            manifest["upstream"]["wheel_url"], timeout=60.0
        ) as resp:
            data = resp.read()
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise ControlledBuildError(
            f"upstream wheel download failed: {type(exc).__name__}: {exc}"
        ) from None
    if _sha256(data) != manifest["upstream"]["wheel_sha256"]:
        raise ControlledBuildError("downloaded wheel hash mismatch (fail closed)")
    cached.write_bytes(data)
    return cached


def compute_manifest_fields(manifest_path: Path, patches_dir: Path) -> dict:
    """Recompute the derivable manifest fields (patch/web/controlled hashes)."""
    manifest = load_manifest(manifest_path)
    computed = dict(manifest)
    computed["patches"] = [
        {
            "file": entry["file"],
            "sha256": _sha256((patches_dir / entry["file"]).read_bytes()),
            "target": entry["target"],
        }
        for entry in manifest["patches"]
    ]
    web = manifest.get("web_client", {})
    manifest_file = REPO_ROOT / web.get("manifest", "")
    if not manifest_file.is_file():
        raise ControlledBuildError(
            f"web client manifest not found for hash recompute: {manifest_file}"
        )
    web = dict(web)
    web["manifest_sha256"] = _sha256(manifest_file.read_bytes())
    computed["web_client"] = web
    return computed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--patches-dir", type=Path, default=DEFAULT_PATCHES_DIR)
    parser.add_argument("--source-wheel", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument(
        "--update-manifest",
        action="store_true",
        help="rewrite the manifest with recomputed patch/web/output hashes "
        "(regeneration only; afterwards re-run without this flag to verify "
        "the committed manifest against an independent build)",
    )
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        if args.update_manifest:
            manifest = compute_manifest_fields(args.manifest, args.patches_dir)
        source = _resolve_source_wheel(manifest, args.source_wheel, args.allow_download)
        out_path = args.out_dir / manifest["controlled"]["wheel_filename"]
        identity = build_controlled_wheel(source, args.patches_dir, manifest, out_path)
        expected = manifest["controlled"].get("wheel_sha256")
        if args.update_manifest:
            manifest["controlled"]["wheel_sha256"] = identity["wheel_sha256"]
            args.manifest.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(f"manifest updated: {args.manifest}")
        elif expected and expected != identity["wheel_sha256"]:
            raise ControlledBuildError(
                f"controlled wheel SHA256 drift: manifest {expected} != built {identity['wheel_sha256']}"
            )
        print(json.dumps(identity, indent=2, ensure_ascii=False))
    except ControlledBuildError as exc:
        print(f"controlled build failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
