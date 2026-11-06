"""t043: Selkies version pin consistency across lock, vendor script and ABI gate."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _locked_selkies() -> str:
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
    assert pinned == locked
    return pinned


def test_x11_keymap_version_gate_matches_lock() -> None:
    """The ABI adapter's supported-version gate must follow uv.lock.

    s012 spike verified the private ABI itself is unchanged between 2.1.0
    and 2.2.1; only the hard-coded version check is allowed to move.
    """
    from cbrowser.stream_agent import x11_keymap

    assert x11_keymap.SUPPORTED_SELKIES_VERSION == _locked_selkies()


def test_web_client_sha_manifest_matches_vendor_pin() -> None:
    """The SHA manifest must describe the pinned wheel's web client."""
    from scripts import vendor_selkies_web

    assert vendor_selkies_web.PINNED_SELKIES_VERSION == _locked_selkies()
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    wheel_hash = next(
        w["hash"].removeprefix("sha256:")
        for w in next(p for p in lock["package"] if p["name"] == "selkies")["wheels"]
        if w["url"].endswith(".whl")
    )
    assert vendor_selkies_web.PINNED_WHEEL_SHA256 == wheel_hash
    manifest = (
        REPO_ROOT / "config" / "selkies" / "selkies_web_sha256.txt"
    ).read_text(encoding="utf-8")
    assert "selkies_web/selkies-core.js" in manifest
    assert "selkies_web/src/selkies-core.js" not in manifest


def test_injection_marker_is_not_version_frozen() -> None:
    """vendor must inject before the first module tag, not a 2.1.0 bundle name."""
    source = (REPO_ROOT / "scripts" / "vendor_selkies_web.py").read_text(
        encoding="utf-8"
    )
    assert "index-BpOBp7NB.js" not in source
    # No hashed bundle name may be frozen in the vendor script at all.
    assert not re.search(r"assets/index-[A-Za-z0-9_-]+\.js", source)
    assert "module_match" in source
    assert re.search(r"type=\\?\"module", source) is not None
