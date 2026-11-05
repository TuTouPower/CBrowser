"""Mechanical wiring for the vendored Selkies frontend build."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.vendor_selkies_web import DEFAULT_MANIFEST_PATH  # noqa: E402
from scripts.verify_frontend_dist import (  # noqa: E402
    DEFAULT_MANIFEST,
    verify_frontend_dist,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

ADAPTER_TAG = '<script src="./selkies_adapter.js"></script>'
MODULE_TAG = '<script type="module" crossorigin src="./assets/index.js"></script>'
ADAPTER_JS = "window.__SELKIES_STREAMING_MODE__ = 'webrtc';\nwindow.__getWebRTCStats = async () => null;\n(() => {})();\n"


def _write_dist(
    tmp_path: Path,
    *,
    adapter_js: str = ADAPTER_JS,
    index_html: str | None = None,
    official_html: str = "<html><head></head><body></body></html>",
    official_digest: str | None = None,
) -> tuple[Path, Path]:
    dist = tmp_path / "dist"
    selkies = dist / "selkies"
    selkies.mkdir(parents=True)
    (selkies / "index.html.official").write_text(official_html, encoding="utf-8")
    if index_html is None:
        index_html = (
            "<html><head>\n"
            f"{ADAPTER_TAG}\n"
            f"{MODULE_TAG}\n"
            "</head></html>"
        )
    (selkies / "index.html").write_text(index_html, encoding="utf-8")
    (selkies / "selkies_adapter.js").write_text(adapter_js, encoding="utf-8")
    assets = dist / "assets"
    assets.mkdir()
    (assets / "index.css").write_text(
        ".bg-primary{background-color:var(--primary)}"
        ".text-primary-foreground{color:var(--primary-foreground)}\n",
        encoding="utf-8",
    )

    digest = official_digest or hashlib.sha256(
        official_html.encode("utf-8")
    ).hexdigest()
    manifest = tmp_path / "manifest.txt"
    manifest.write_text(f"{digest}  selkies_web/index.html\n", encoding="utf-8")
    return dist, manifest


def test_package_build_runs_vendor_and_verification() -> None:
    package = json.loads(
        (REPO_ROOT / "src" / "frontend" / "package.json").read_text(encoding="utf-8")
    )
    scripts = package["scripts"]
    assert scripts["prebuild"] == "npm run vendor:selkies"
    assert scripts["postbuild"] == "python3 ../../scripts/write_frontend_build_stamp.py && npm run verify:selkies"
    assert "scripts/vendor_selkies_web.py" in scripts["vendor:selkies"]
    assert "scripts/verify_frontend_dist.py" in scripts["verify:selkies"]


def test_frontend_gate_checks_pinned_node_version() -> None:
    """t033 AC-004: both npm test and npm run build fail on a wrong Node.

    The old wiring assertion above stays unchanged; this test covers the
    new engines/check:node gate so prebuild's vendor semantics remain
    verifiable independently.
    """
    package = json.loads(
        (REPO_ROOT / "src" / "frontend" / "package.json").read_text(encoding="utf-8")
    )
    assert package["engines"]["node"] == ">=26.0.0 <27"
    scripts = package["scripts"]
    assert scripts["check:node"] == "node scripts/check_node.mjs"
    assert scripts["pretest"] == "npm run check:node"
    assert scripts["build"].startswith("npm run check:node && ")
    checker = REPO_ROOT / "src" / "frontend" / "scripts" / "check_node.mjs"
    assert checker.is_file()
    body = checker.read_text(encoding="utf-8")
    assert "engines" in body and "process.exit(1)" in body
    assert "process.versions.node" in body


def test_default_manifests_live_outside_tests() -> None:
    assert DEFAULT_MANIFEST_PATH == DEFAULT_MANIFEST
    assert DEFAULT_MANIFEST.is_file()
    assert "config" in DEFAULT_MANIFEST.parts
    assert "tests" not in DEFAULT_MANIFEST.parts


def test_valid_dist_passes(tmp_path: Path) -> None:
    dist, manifest = _write_dist(tmp_path)
    verify_frontend_dist(dist, manifest)


def test_missing_adapter_fails(tmp_path: Path) -> None:
    dist, manifest = _write_dist(tmp_path)
    (dist / "selkies" / "selkies_adapter.js").unlink()
    with pytest.raises(RuntimeError, match="adapter missing"):
        verify_frontend_dist(dist, manifest)


def test_module_adapter_fails(tmp_path: Path) -> None:
    dist, manifest = _write_dist(
        tmp_path, adapter_js="export const adapter = true;\n"
    )
    with pytest.raises(RuntimeError, match="classic IIFE"):
        verify_frontend_dist(dist, manifest)


def test_missing_adapter_tag_fails(tmp_path: Path) -> None:
    dist, manifest = _write_dist(
        tmp_path,
        index_html=f"<html><head>{MODULE_TAG}</head></html>",
    )
    with pytest.raises(RuntimeError, match="exactly one adapter tag"):
        verify_frontend_dist(dist, manifest)


def test_adapter_must_load_before_module_bundle(tmp_path: Path) -> None:
    dist, manifest = _write_dist(
        tmp_path,
        index_html=f"<html><head>{MODULE_TAG}\n{ADAPTER_TAG}</head></html>",
    )
    with pytest.raises(RuntimeError, match="before the module bundle"):
        verify_frontend_dist(dist, manifest)


def test_manifest_mismatch_fails(tmp_path: Path) -> None:
    dist, manifest = _write_dist(tmp_path, official_digest="0" * 64)
    with pytest.raises(RuntimeError, match="SHA256 mismatch"):
        verify_frontend_dist(dist, manifest)
