"""t041 AC-008 repository-side font hygiene guards (static, no Docker).

Platform font files must never be committed, baked into an image layer,
copied by the release script, or mounted read-write. These guards inspect
tracked files and source text only.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FONT_SUFFIXES = {".ttf", ".ttc", ".otf", ".otc", ".fon"}
EXCLUDED_PREFIXES = (".repo_template/", "docs/archive/")
DOCKER_DIR = ROOT / "config" / "docker"
BROWSER_DOCKERFILE = DOCKER_DIR / "browser_runtime" / "Dockerfile"
BASE_FONTS_DIR = "/opt/cbrowser-base-fonts"
FONT_DIR_MARKERS = ("CBROWSER_FONTS_DIR", "/data/fonts", "data/fonts")
FONT_EXT_RE = re.compile(r"\.(ttf|ttc|otf|otc|fon)\b", re.IGNORECASE)


def _tracked_files() -> list[str]:
    """Return NUL-safe list of git-tracked paths relative to the repo root."""
    output = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=ROOT, text=False
    ).decode("utf-8")
    return [name for name in output.split("\0") if name]


def _dockerfiles() -> list[Path]:
    """Every config/docker/*/Dockerfile in sorted order."""
    return sorted(DOCKER_DIR.glob("*/Dockerfile"))


def test_no_tracked_font_binaries() -> None:
    """AC-008: no platform font binary is committed to the repository."""
    hits = [
        name
        for name in _tracked_files()
        if Path(name).suffix.lower() in FONT_SUFFIXES
        and not name.startswith(EXCLUDED_PREFIXES)
    ]
    assert not hits, "Tracked font binaries found:\n" + "\n".join(hits)


def test_dockerfiles_do_not_copy_font_sets() -> None:
    """AC-008: no Dockerfile COPY bakes platform font files or the font dir into an image."""
    offenders: list[str] = []
    for dockerfile in _dockerfiles():
        for lineno, line in enumerate(
            dockerfile.read_text(encoding="utf-8").splitlines(), 1
        ):
            stripped = line.strip()
            if not stripped.upper().startswith("COPY"):
                continue
            if any(marker in line for marker in FONT_DIR_MARKERS) or FONT_EXT_RE.search(line):
                offenders.append(f"{dockerfile.relative_to(ROOT)}:{lineno}: {stripped}")
    assert not offenders, "Dockerfile COPY of font data:\n" + "\n".join(offenders)


def test_browser_runtime_base_fonts_dir_is_outside_default_scan_paths() -> None:
    """AC-008: the Browser image stages base fonts under /opt/cbrowser-base-fonts."""
    text = BROWSER_DOCKERFILE.read_text(encoding="utf-8")
    assert BASE_FONTS_DIR in text
    assert BASE_FONTS_DIR.startswith("/opt/")


def test_deploy_script_does_not_copy_font_directories() -> None:
    """AC-008: the release deployment script never copies a font directory."""
    text = (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    offenders = [
        line.strip()
        for line in text.splitlines()
        if re.search(r"\b(cp|rsync|tar|install)\b", line, re.IGNORECASE)
        and re.search(r"\bfonts\b", line, re.IGNORECASE)
    ]
    assert not offenders, "deploy.sh copies font directories:\n" + "\n".join(offenders)


def test_compose_font_directory_mounts_are_read_only() -> None:
    """AC-008: compose.yaml binds the shared font directory read-only."""
    text = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    mounts = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("-") and "/fonts" in line
    ]
    assert mounts, "compose.yaml has no font directory volume mounts"
    for mount in mounts:
        assert mount.endswith(":ro"), f"font mount is not read-only: {mount}"


def test_worktreeinclude_registers_shared_font_dir() -> None:
    """AC-008: task worktrees share the same font directory via .worktreeinclude."""
    path = ROOT / ".worktreeinclude"
    assert path.is_file()
    entries = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert any("data/fonts" in entry for entry in entries), (
        f".worktreeinclude does not register the font directory: {entries!r}"
    )


def test_font_sets_module_has_no_font_binaries() -> None:
    """AC-008: src/backend/cbrowser/font_sets ships only Python source, never font binaries."""
    module = ROOT / "src" / "backend" / "cbrowser" / "font_sets"
    assert module.is_dir(), f"missing font_sets module: {module}"
    files = [p for p in module.rglob("*") if p.is_file()]
    font_binaries = [
        str(p.relative_to(ROOT))
        for p in files
        if p.suffix.lower() in FONT_SUFFIXES
    ]
    assert not font_binaries, (
        "font binaries inside font_sets module:\n" + "\n".join(font_binaries)
    )
    non_python = [
        str(p.relative_to(ROOT))
        for p in files
        if "__pycache__" not in p.parts and p.suffix.lower() != ".py"
    ]
    assert not non_python, (
        "font_sets module contains non-Python files:\n" + "\n".join(non_python)
    )
    python_sources = [
        p for p in files
        if "__pycache__" not in p.parts and p.suffix == ".py"
    ]
    assert python_sources, "font_sets module has no Python sources"
