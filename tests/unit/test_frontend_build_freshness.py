"""Frontend source-freshness gate."""

from pathlib import Path

import pytest
from scripts.verify_frontend_dist import (
    verify_frontend_build_freshness,
    write_frontend_build_stamp,
)


def _make_frontend(root: Path) -> Path:
    frontend = root / "frontend"
    (frontend / "src").mkdir(parents=True)
    (frontend / "src" / "main.ts").write_text("one", encoding="utf-8")
    (frontend / "index.html").write_text("<html></html>", encoding="utf-8")
    (frontend / "package.json").write_text("{}", encoding="utf-8")
    (frontend / "package-lock.json").write_text("{}", encoding="utf-8")
    return frontend


def test_stamp_rejects_stale_source(tmp_path: Path):
    frontend = _make_frontend(tmp_path)
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


def test_missing_required_input_blocks_stamp_generation(tmp_path: Path):
    """AC-016: a stamp must not be generated when a required input is gone."""
    frontend = _make_frontend(tmp_path)
    (frontend / "package-lock.json").unlink()
    dist = tmp_path / "dist"
    dist.mkdir()
    with pytest.raises(RuntimeError, match="Required frontend build input missing"):
        write_frontend_build_stamp(dist, frontend)
    assert not (dist / "build-stamp.json").exists()


def test_deleted_source_file_makes_dist_stale(tmp_path: Path):
    frontend = _make_frontend(tmp_path)
    extra = frontend / "src" / "extra.ts"
    extra.write_text("x", encoding="utf-8")
    dist = tmp_path / "dist"
    dist.mkdir()
    write_frontend_build_stamp(dist, frontend)
    extra.unlink()
    with pytest.raises(RuntimeError, match="stale"):
        verify_frontend_build_freshness(dist, frontend)


def test_added_config_input_makes_dist_stale(tmp_path: Path):
    frontend = _make_frontend(tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()
    write_frontend_build_stamp(dist, frontend)
    (frontend / "vite.config.ts").write_text("export {}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="stale"):
        verify_frontend_build_freshness(dist, frontend)


def test_removed_config_input_makes_dist_stale(tmp_path: Path):
    frontend = _make_frontend(tmp_path)
    (frontend / "vite.config.ts").write_text("export {}", encoding="utf-8")
    dist = tmp_path / "dist"
    dist.mkdir()
    write_frontend_build_stamp(dist, frontend)
    (frontend / "vite.config.ts").unlink()
    with pytest.raises(RuntimeError, match="stale"):
        verify_frontend_build_freshness(dist, frontend)


def test_added_vite_env_file_makes_dist_stale(tmp_path: Path):
    frontend = _make_frontend(tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()
    write_frontend_build_stamp(dist, frontend)
    (frontend / ".env.local").write_text("VITE_X=1", encoding="utf-8")
    with pytest.raises(RuntimeError, match="stale"):
        verify_frontend_build_freshness(dist, frontend)


def _run_collection_hook(root: Path, item_name: str, *, consumes_dist: bool = True):
    import runpy

    namespace = runpy.run_path(str(Path(__file__).resolve().parents[2] / "tests" / "e2e" / "conftest.py"))
    hook = namespace["pytest_collection_modifyitems"]
    hook.__globals__["REPO_ROOT"] = root

    # Materialize the fake suite file: a consuming suite references the
    # probe harness, a non-consuming one does not (the hook scopes the
    # freshness gate by actual consumption, not by filename).
    suite_file = root / "tests" / "e2e" / item_name
    suite_file.parent.mkdir(parents=True, exist_ok=True)
    suite_file.write_text(
        "from frontend_app_probe import harness  # noqa\n"
        if consumes_dist
        else "# supervisor-only suite\n",
        encoding="utf-8",
    )

    class Item:
        fspath = suite_file

    return hook, Item


def _make_repo_with_stale_dist(root: Path) -> None:
    frontend = root / "src" / "frontend"
    (frontend / "src").mkdir(parents=True)
    (frontend / "src" / "main.ts").write_text("one", encoding="utf-8")
    (frontend / "index.html").write_text("<html></html>", encoding="utf-8")
    (frontend / "package.json").write_text("{}", encoding="utf-8")
    (frontend / "package-lock.json").write_text("{}", encoding="utf-8")
    dist = frontend / "dist"
    dist.mkdir()
    write_frontend_build_stamp(dist, frontend)
    (frontend / "src" / "main.ts").write_text("two", encoding="utf-8")


def test_missing_src_directory_rejected_at_generation(tmp_path: Path) -> None:
    frontend = _make_frontend(tmp_path)
    import shutil

    shutil.rmtree(frontend / "src")
    with pytest.raises(RuntimeError, match="source directory missing"):
        write_frontend_build_stamp(tmp_path / "dist", frontend)


def test_e2e_collection_hook_rejects_stale_frontend(tmp_path: Path, monkeypatch):
    _make_repo_with_stale_dist(tmp_path)
    hook, Item = _run_collection_hook(tmp_path, "test_frontend_app_e2e.py")
    with pytest.raises(RuntimeError, match="stale"):
        hook(None, [Item()])


def test_e2e_collection_hook_rejects_stale_dist_for_non_frontend_names(
    tmp_path: Path, monkeypatch
):
    """AC-003: the gate follows actual dist presence, not the suite filename."""
    _make_repo_with_stale_dist(tmp_path)
    hook, Item = _run_collection_hook(tmp_path, "test_browser_runtime_e2e.py")
    with pytest.raises(RuntimeError, match="stale"):
        hook(None, [Item()])


def test_e2e_collection_hook_ignores_stale_dist_for_non_consumers(tmp_path: Path):
    _make_repo_with_stale_dist(tmp_path)
    hook, Item = _run_collection_hook(
        tmp_path, "test_supervisor_core_e2e.py", consumes_dist=False
    )
    # No consumer items collected: the stale dist must not block suites
    # that never touch it (AC-011 scoped prerequisites).
    hook(None, [Item()])
