"""Shared unit fixtures."""

from pathlib import Path

import pytest
import pytest_asyncio

from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.session import create_engine_and_maker


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_v2.db"


@pytest_asyncio.fixture
async def db_context(temp_db_path: Path):
    run_database_migrations(temp_db_path)
    engine, session_maker = create_engine_and_maker(temp_db_path)
    yield engine, session_maker
    await engine.dispose()
