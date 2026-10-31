"""Single-source verification for the production Selkies client adapter.

The production ``selkies_adapter.js`` served next to the official Selkies web
client must be produced by the frontend build from
``src/frontend/src/features/browser-session/adapter.ts``. The vendoring script
only downloads/verifies official assets and injects the classic script tag.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import vendor_selkies_web as vendor_module  # noqa: E402
from scripts.vendor_selkies_web import vendor_selkies_web  # noqa: E402

ADAPTER_TS = (
    REPO_ROOT
    / "src"
    / "frontend"
    / "src"
    / "features"
    / "browser-session"
    / "adapter.ts"
)
ADAPTER_ENTRY_TS = (
    REPO_ROOT
    / "src"
    / "frontend"
    / "src"
    / "features"
    / "browser-session"
    / "selkies_adapter_entry.ts"
)
DIST_ADAPTER_JS = (
    REPO_ROOT / "src" / "frontend" / "dist" / "selkies" / "selkies_adapter.js"
)


def test_production_adapter_artifact_is_built_from_typescript_adapter() -> None:
    assert ADAPTER_TS.is_file(), "adapter.ts must remain the single implementation"
    assert ADAPTER_ENTRY_TS.is_file(), "classic-script entry point is required"
    assert DIST_ADAPTER_JS.is_file(), (
        "dist/selkies/selkies_adapter.js missing; "
        "run npm run build --prefix src/frontend"
    )

    built = DIST_ADAPTER_JS.read_text(encoding="utf-8")
    assert "__cbrowserAdapterSource" in built
    assert "features/browser-session/adapter.ts" in built

    # The injected tag is a classic script that must execute before the official
    # module bundle; a module build would not run in the required order.
    assert not re.search(r"^\s*(import|export)\s", built, re.MULTILINE), (
        "adapter build must be a classic IIFE script"
    )
    assert "__cbrowserShimInstalled" in built


def test_vendor_script_injects_built_adapter_without_embedding_it(
    tmp_path: Path,
) -> None:
    dest_dir = tmp_path / "selkies"
    cache_dir = REPO_ROOT / ".scratch" / "selkies_wheels"
    manifest_path = (
        REPO_ROOT / "tests" / "fixtures" / "gateway_probe" / "selkies_web_sha256.txt"
    )

    vendor_selkies_web(
        dest_dir=dest_dir,
        cache_dir=cache_dir,
        manifest_path=manifest_path,
    )

    assert not hasattr(vendor_module, "SELKIES_CLIENT_ADAPTER_JS"), (
        "vendor script must not carry an embedded adapter implementation"
    )
    assert not (dest_dir / "selkies_adapter.js").exists(), (
        "vendor script must not write the adapter; the frontend build owns it"
    )

    index_text = (dest_dir / "index.html").read_text(encoding="utf-8")
    adapter_tag = '<script src="./selkies_adapter.js"></script>'
    module_tag = (
        '<script type="module" crossorigin src="./assets/index-BpOBp7NB.js"></script>'
    )
    assert adapter_tag in index_text
    assert module_tag in index_text
    assert index_text.index(adapter_tag) < index_text.index(module_tag)


def test_vendor_no_inject_adapter_keeps_official_index(tmp_path: Path) -> None:
    dest_dir = tmp_path / "selkies"
    cache_dir = REPO_ROOT / ".scratch" / "selkies_wheels"
    manifest_path = (
        REPO_ROOT / "tests" / "fixtures" / "gateway_probe" / "selkies_web_sha256.txt"
    )

    vendor_selkies_web(
        dest_dir=dest_dir,
        cache_dir=cache_dir,
        manifest_path=manifest_path,
        inject_adapter=False,
    )

    index_text = (dest_dir / "index.html").read_text(encoding="utf-8")
    assert '<script src="./selkies_adapter.js"></script>' not in index_text
    assert (
        '<script type="module" crossorigin src="./assets/index-BpOBp7NB.js"></script>'
        in index_text
    )


def test_vendor_replaces_stale_destination_contents(tmp_path: Path) -> None:
    dest_dir = tmp_path / "selkies"
    dest_dir.mkdir()
    (dest_dir / "selkies_adapter.js").write_text("stale embedded adapter")
    (dest_dir / "leftover.txt").write_text("stale")

    vendor_selkies_web(
        dest_dir=dest_dir,
        cache_dir=REPO_ROOT / ".scratch" / "selkies_wheels",
        manifest_path=REPO_ROOT
        / "tests"
        / "fixtures"
        / "gateway_probe"
        / "selkies_web_sha256.txt",
    )

    assert not (dest_dir / "selkies_adapter.js").exists()
    assert not (dest_dir / "leftover.txt").exists()
    assert (dest_dir / "index.html").is_file()
