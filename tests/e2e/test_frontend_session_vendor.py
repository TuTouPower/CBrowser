"""Verification of Selkies 2.1.0 official web client vendoring and hash verification."""

from __future__ import annotations

from pathlib import Path

from scripts.vendor_selkies_web import (  # noqa: E402
    DEFAULT_MANIFEST_PATH,
    PINNED_SELKIES_VERSION,
    PINNED_WHEEL_SHA256,
    verify_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
VENDORED_DIR = REPO_ROOT / "src" / "frontend" / "public" / "selkies"


def test_pinned_constants() -> None:
    """Change alarm for the pin values themselves (kept from the original
    test): a deliberate pin bump is the only way this test should fail."""
    assert PINNED_SELKIES_VERSION == "2.1.0"
    assert (
        PINNED_WHEEL_SHA256
        == "8bde6207ca921cb2f38c3204fafe18d40b5578165894818ae1ca9e46fca7b966"
    )


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
