"""Verification of Selkies official web client vendoring and hash verification."""

from __future__ import annotations

import pytest

import tomllib
from pathlib import Path

from scripts.vendor_selkies_web import (  # noqa: E402
    DEFAULT_MANIFEST_PATH,
    PINNED_SELKIES_VERSION,
    PINNED_WHEEL_SHA256,
    verify_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
VENDORED_DIR = REPO_ROOT / "src" / "frontend" / "public" / "selkies"


def test_pinned_version_matches_lock() -> None:
    """The vendor pin must equal the version locked in pyproject/uv.lock.

    Replaces the removed hard-coded ``test_pinned_constants`` (which asserted
    the literal "2.1.0"): its expected value changed with the t043 upgrade,
    and in-place edits of an old test's expected output are forbidden.  The
    new assertion is version-agnostic and fails on any drift between the
    vendor script and the single uv.lock source (t034/t043).
    """
    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    stream_group = pyproject["dependency-groups"]["stream"]
    pinned = next(
        item.split("==", 1)[1]
        for item in stream_group
        if item.startswith("selkies==")
    )
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked = next(
        p["version"] for p in lock["package"] if p["name"] == "selkies"
    )
    assert PINNED_SELKIES_VERSION == pinned == locked
    # The wheel hash is the artifact identity behind the pin; lock it to
    # uv.lock's recorded wheel hash rather than a bare length check.
    wheel_hash = next(
        w["hash"].removeprefix("sha256:")
        for w in next(p for p in lock["package"] if p["name"] == "selkies")["wheels"]
        if w["url"].endswith(".whl")
    )
    assert PINNED_WHEEL_SHA256 == wheel_hash


def test_vendored_tree_matches_reference_manifest() -> None:
    """The tree actually vendored for browsers must verify against the
    reference manifest (t024 AC-018/A53: the pin alarm and the manifest
    integrity check run together, so a stale or drifted vendor output
    fails here even when the pins are untouched)."""
    assert VENDORED_DIR.is_dir(), (
        f"vendored Selkies tree missing at {VENDORED_DIR}; "
        "run the frontend build (prebuild vendors it) first"
    )
    # allow_patched: vendoring intentionally injects the adapter tag into
    # index.html and keeps the pristine file as index.html.official, which
    # is what the manifest is checked against for that one file.
    verify_manifest(VENDORED_DIR, DEFAULT_MANIFEST_PATH, allow_patched=True)

pytestmark = pytest.mark.e2e_images()
