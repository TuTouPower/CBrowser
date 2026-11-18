"""Per-instance verification of the font set a Browser actually mounts.

t075 readiness contract: an environment may only be reported usable
after the set bound to *this* instance has been verified where it is
consumed — inside the Browser container, against the actual mount —
and after the Profile's generated fontconfig has been applied:

- the mount directory exists and is non-empty;
- its ``manifest.json`` parses, names this platform, and lists files
  that are all present **with content matching the manifest sha256**
  (a same-named but substituted file fails here — the Supervisor's
  pre-start ``check_font_set`` covers the host directory, this layer
  re-proves the mount the instance actually received);
- the *filtered* view (fontconfig with the Profile's CJK switch
  applied) still contains fonts — an empty effective set, a missing
  required Chinese capability when CJK is on, or a Chinese leak when
  CJK is off are all hard failures;
- when CJK is on, at least one Chinese face must also *render* real
  CJK glyphs (FreeType rasterization proof, see
  ``glyph_render.prove_cjk_render``) — a font that merely enumerates
  ``zh`` coverage but shapes everything to ``.notdef`` fails here;
- detection-font coverage gaps are *optional* coverage: they are
  reported separately (``missing_optional``) and never fail the
  instance, so the UI/health surfaces can distinguish "required
  rendering capability broken" from "some probe fonts absent".

The verdict is a plain dict so the Runner can persist it into
``runner_info.json`` verbatim and the Agent can gate ``/health``
readiness on it without re-scanning or re-hashing anything.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Callable

from cbrowser.font_sets.manifest import DETECTION_FONTS, PLATFORM_DETECTION_LABELS
from cbrowser.runtime_agent.glyph_render import (
    GlyphRenderError,
    GlyphRenderUnavailable,
    prove_cjk_render,
)

# Failure reasons are stable machine-readable tokens; they point at
# the asset / font capability, never at another platform's fonts.
FAILURE_BINDING_MISSING = "font_binding_missing"
FAILURE_MOUNT_MISSING = "font_mount_missing"
FAILURE_MANIFEST_INVALID = "font_manifest_invalid"
FAILURE_PLATFORM_MISMATCH = "font_platform_mismatch"
FAILURE_FILES_MISSING = "font_files_missing"
FAILURE_CONTENT_MISMATCH = "font_content_mismatch"
FAILURE_NO_EFFECTIVE_FONTS = "font_no_effective_fonts"
FAILURE_CJK_REQUIRED_MISSING = "font_cjk_required_missing"
FAILURE_CJK_LEAK = "font_cjk_leak"
FAILURE_CJK_RENDER_FAILED = "font_cjk_render_failed"
FAILURE_RENDER_UNAVAILABLE = "font_render_unavailable"
FAILURE_LISTING_FAILED = "font_listing_failed"

# An fc-list probe returns (file name, language tags) per visible face.
FontLister = Callable[[Path], list[tuple[str, tuple[str, ...]]]]
# A render probe proves one font file really renders CJK glyphs.
GlyphProver = Callable[[Path], bool]


def _default_font_lister(fontconfig_path: Path) -> list[tuple[str, tuple[str, ...]]]:
    """List the faces the given fontconfig exposes, via real fontconfig.

    ``fc-list`` honours ``FONTCONFIG_FILE``, so the listing is exactly
    the filtered view Chromium will get, reject rules included.
    """
    env = dict(os.environ, FONTCONFIG_FILE=str(fontconfig_path))
    completed = subprocess.run(
        ["fc-list", "-f", "%{file}\t%{lang}\n", ":"],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=True,
    )
    entries: list[tuple[str, tuple[str, ...]]] = []
    for line in completed.stdout.splitlines():
        if "\t" not in line:
            continue
        file_name, langs = line.split("\t", 1)
        entries.append(
            (Path(file_name).name, tuple(tag for tag in langs.split("|") if tag))
        )
    return entries


def _is_chinese(tags: tuple[str, ...]) -> bool:
    return any(tag == "zh" or tag.startswith("zh-") for tag in tags)


def _failed(
    failure: str,
    font_set_id: str | None,
    missing_optional: list[str] | None = None,
    effective_fonts: int = 0,
) -> dict:
    return {
        "status": "failed",
        "failure": failure,
        "font_set_id": font_set_id,
        "missing_optional": missing_optional or [],
        "effective_fonts": effective_fonts,
    }


def _load_manifest(set_dir: Path) -> tuple[dict | None, str | None]:
    """Parse the set manifest; return ``(manifest, failure)``."""
    try:
        manifest = json.loads(
            (set_dir / "manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValueError):
        return None, FAILURE_MANIFEST_INVALID
    if not isinstance(manifest, dict):
        return None, FAILURE_MANIFEST_INVALID
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        return None, FAILURE_MANIFEST_INVALID
    for entry in files:
        if not isinstance(entry, dict):
            return None, FAILURE_MANIFEST_INVALID
        if not isinstance(entry.get("name"), str) or not entry["name"]:
            return None, FAILURE_MANIFEST_INVALID
        if not isinstance(entry.get("sha256"), str) or not entry["sha256"]:
            return None, FAILURE_MANIFEST_INVALID
    return manifest, None


def _check_manifest_files(set_dir: Path, manifest: dict) -> str | None:
    """Existence + sha256 content check for every manifest entry."""
    for entry in manifest["files"]:
        path = set_dir / entry["name"]
        if not path.is_file():
            return FAILURE_FILES_MISSING
        digest = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(chunk)
        except OSError:
            return FAILURE_FILES_MISSING
        if digest.hexdigest() != entry["sha256"]:
            return FAILURE_CONTENT_MISMATCH
    return None


def _assess_effective_fonts(
    entries: list[tuple[str, tuple[str, ...]]], include_cjk_fonts: bool
) -> tuple[str | None, int]:
    """Capability verdict for the filtered view; ``(failure, count)``."""
    if not entries:
        return FAILURE_NO_EFFECTIVE_FONTS, 0
    chinese = [entry for entry in entries if _is_chinese(entry[1])]
    if include_cjk_fonts and not chinese:
        return FAILURE_CJK_REQUIRED_MISSING, len(entries)
    if not include_cjk_fonts and chinese:
        return FAILURE_CJK_LEAK, len(entries)
    return None, len(entries)


def _prove_cjk_render(
    set_dir: Path,
    entries: list[tuple[str, tuple[str, ...]]],
    glyph_prover: GlyphProver | None,
) -> str | None:
    """Render proof for the CJK faces in the filtered view.

    Tries each Chinese face in lister order until one proves; fails
    only when none does.  A missing renderer is its own failure — the
    proof cannot be skipped silently.
    """
    prover = glyph_prover or prove_cjk_render
    for name, tags in entries:
        if not _is_chinese(tags):
            continue
        try:
            if prover(set_dir / name):
                return None
        except GlyphRenderUnavailable:
            return FAILURE_RENDER_UNAVAILABLE
        except (GlyphRenderError, OSError, ValueError):
            continue
    return FAILURE_CJK_RENDER_FAILED


def verify_mounted_font_set(
    *,
    mount_root: Path,
    platform: str,
    font_set_id: str | None,
    include_cjk_fonts: bool,
    fontconfig_path: Path,
    font_lister: FontLister | None = None,
    glyph_prover: GlyphProver | None = None,
) -> dict:
    """Verify the mounted set for one runtime instance.

    ``mount_root`` is the container-side font root (``/run/cbrowser/
    fonts`` in production).  Returns the verdict dict described in the
    module docstring; never raises for asset problems — every asset
    failure is a ``failed`` verdict with a stable reason.
    """
    if not font_set_id:
        return _failed(FAILURE_BINDING_MISSING, None)
    set_dir = mount_root / platform / font_set_id
    if not set_dir.is_dir():
        return _failed(FAILURE_MOUNT_MISSING, font_set_id)
    manifest, failure = _load_manifest(set_dir)
    if failure is not None or manifest is None:
        return _failed(failure or FAILURE_MANIFEST_INVALID, font_set_id)
    manifest_platform = manifest.get("platform")
    if manifest_platform is not None and manifest_platform != platform:
        return _failed(FAILURE_PLATFORM_MISMATCH, font_set_id)
    failure = _check_manifest_files(set_dir, manifest)
    if failure is not None:
        return _failed(failure, font_set_id)

    lister = font_lister or _default_font_lister
    try:
        entries = lister(fontconfig_path)
    except (OSError, subprocess.SubprocessError):
        return _failed(FAILURE_LISTING_FAILED, font_set_id)
    failure, effective = _assess_effective_fonts(entries, include_cjk_fonts)
    if failure is not None:
        return _failed(failure, font_set_id, effective_fonts=effective)
    if include_cjk_fonts:
        failure = _prove_cjk_render(set_dir, entries, glyph_prover)
        if failure is not None:
            return _failed(failure, font_set_id, effective_fonts=effective)

    return {
        "status": "verified",
        "failure": None,
        "font_set_id": font_set_id,
        "missing_optional": _optional_coverage(manifest, platform),
        "effective_fonts": effective,
    }


def _optional_coverage(manifest: dict, platform: str) -> list[str]:
    """Detection fonts the set itself does not carry.

    Judged against the manifest (what the set contains), not against
    the filtered view — a carried Chinese font hidden by the CJK
    switch is policy, not a coverage gap.  Split out of
    ``verify_mounted_font_set`` so the orchestrator stays under the
    complexity threshold (t075 code f004).
    """
    carried = {entry["name"] for entry in manifest["files"]}
    return sorted(
        {
            name
            for label in PLATFORM_DETECTION_LABELS.get(platform, ())
            for name in DETECTION_FONTS.get(label, ())
            if name not in carried
        }
    )
