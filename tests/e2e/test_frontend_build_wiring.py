"""Mechanical wiring for the vendored Selkies frontend build."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.vendor_selkies_web import DEFAULT_MANIFEST_PATH  # noqa: E402
from scripts.verify_frontend_dist import (  # noqa: E402
    DEFAULT_MANIFEST,
    verify_frontend_dist,
)

ADAPTER_TAG = '<script src="./selkies_adapter.js"></script>'
MODULE_TAG = '<script type="module" crossorigin src="./assets/index.js"></script>'
ADAPTER_JS = "__cbrowserAdapterSource\n__cbrowserShimInstalled\n(() => {})();\n"


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
    assert scripts["postbuild"] == "npm run verify:selkies"
    assert "scripts/vendor_selkies_web.py" in scripts["vendor:selkies"]
    assert "scripts/verify_frontend_dist.py" in scripts["verify:selkies"]


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
