"""Shared unit fixtures."""

from pathlib import Path

import pytest
import pytest_asyncio

from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.font_sets import import_font_set


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_v2.db"


@pytest_asyncio.fixture
async def db_context(temp_db_path: Path):
    run_database_migrations(temp_db_path)
    engine, session_maker = create_engine_and_maker(temp_db_path)
    yield engine, session_maker
    await engine.dispose()


@pytest.fixture
def fixture_font_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """t075: one imported windows font set on a private fonts root,
    with ``CBROWSER_FONTS_DIR`` pointed at it; returns the set_id.

    Start-flow tests whose subject is not fonts use it to give their
    configs the binding the fail-closed launch path requires since
    t075 (an unbound profile refuses to start).  The Supervisor-side
    check hashes the actual bytes, and ``import_font_set`` records the
    real hashes of the fixture content, so the set verifies."""
    source = tmp_path / "font-src"
    source.mkdir()
    (source / "arial.ttf").write_bytes(b"FONT:arial")
    (source / "calibri.ttf").write_bytes(b"FONT:calibri")
    root = tmp_path / "fonts"
    result = import_font_set("windows", [str(source)], "v1", root=str(root))
    monkeypatch.setenv("CBROWSER_FONTS_DIR", str(root))
    return result["set_id"]
