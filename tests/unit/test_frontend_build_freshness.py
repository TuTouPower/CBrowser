"""Frontend source-freshness gate."""

from pathlib import Path

import pytest
from scripts.verify_frontend_dist import (
    verify_frontend_build_freshness,
    write_frontend_build_stamp,
)


def test_stamp_rejects_stale_source(tmp_path: Path):
    frontend = tmp_path / "frontend"
    (frontend / "src").mkdir(parents=True)
    (frontend / "src" / "main.ts").write_text("one", encoding="utf-8")
    (frontend / "index.html").write_text("<html></html>", encoding="utf-8")
    dist = tmp_path / "dist"
    dist.mkdir()
    write_frontend_build_stamp(dist, frontend)
    verify_frontend_build_freshness(dist, frontend)
    (frontend / "src" / "main.ts").write_text("two", encoding="utf-8")
    with pytest.raises(RuntimeError, match="stale"):
        verify_frontend_build_freshness(dist, frontend)


def test_missing_stamp_fails_closed(tmp_path: Path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    dist = tmp_path / "dist"
    dist.mkdir()
    with pytest.raises(RuntimeError, match="stamp missing"):
        verify_frontend_build_freshness(dist, frontend)


def test_unreadable_or_incomplete_stamp_fails_closed(tmp_path: Path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    dist = tmp_path / "dist"
    dist.mkdir()
    stamp = dist / "build-stamp.json"
    stamp.write_text("not-json", encoding="utf-8")
    with pytest.raises(RuntimeError, match="unreadable"):
        verify_frontend_build_freshness(dist, frontend)
    stamp.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="unreadable"):
        verify_frontend_build_freshness(dist, frontend)


def test_e2e_collection_hook_rejects_stale_frontend(tmp_path: Path, monkeypatch):
    import runpy

    root = tmp_path
    frontend = root / "src" / "frontend"
    (frontend / "src").mkdir(parents=True)
    (frontend / "src" / "main.ts").write_text("one", encoding="utf-8")
    (frontend / "index.html").write_text("<html></html>", encoding="utf-8")
    dist = frontend / "dist"
    dist.mkdir()
    write_frontend_build_stamp(dist, frontend)
    (frontend / "src" / "main.ts").write_text("two", encoding="utf-8")

    namespace = runpy.run_path("tests/e2e/conftest.py")
    hook = namespace["pytest_collection_modifyitems"]
    hook.__globals__["REPO_ROOT"] = root

    class Item:
        fspath = root / "tests" / "e2e" / "test_frontend_app_e2e.py"

    with pytest.raises(RuntimeError, match="stale"):
        hook(None, [Item()])
