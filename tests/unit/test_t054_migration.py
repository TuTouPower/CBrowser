"""t054 AC-007: migration 0008 deletes the runtime network transaction state.

The network transaction/pending/applied state lived as ``network.*`` rows
in the ``settings`` table (no dedicated tables). The 0008 upgrade deletes
every such row; the downgrade is a documented no-op (deleted rows have no
restore path by design, and the code that would read them is deleted in
the same task).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from cbrowser.adapters.database.migrations import (
    get_alembic_config,
    run_database_migrations,
)

REVISION_0007 = "1a8db6b91744"
REVISION_0008 = "3751fed02a4a"

NETWORK_KEYS = (
    "network.pending_config",
    "network.applied_version",
    "network.active_operation",
    "network.operation.op-1",
    "network.execution_generation",
    "network.transaction.current",
    "network.version.1",
)


def _revision_of_head(tmp_path: Path) -> str:
    from alembic.script import ScriptDirectory

    cfg = get_alembic_config(tmp_path / "head.db")
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1, heads
    return heads[0]


def test_head_is_0008_and_single(tmp_path: Path) -> None:
    assert _revision_of_head(tmp_path) == REVISION_0008


def test_upgrade_deletes_all_network_settings_rows(tmp_path: Path) -> None:
    db = tmp_path / "net-rows.db"
    cfg = get_alembic_config(db)
    command.upgrade(cfg, REVISION_0007)
    conn = sqlite3.connect(db)
    try:
        now = "2026-01-01T00:00:00+00:00"
        # Migration 0003 already seeds some network.* rows; REPLACE so the
        # fixture covers both the seeded keys and keys 0003 never wrote.
        for key in NETWORK_KEYS:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                (key, '{"network": "legacy"}', now),
            )
        conn.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            ("unrelated.keep", "keep-me", now),
        )
        conn.commit()
    finally:
        conn.close()
    run_database_migrations(db)
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT key FROM settings WHERE key LIKE 'network.%'"
        ).fetchall()
        assert rows == []
        kept = conn.execute(
            "SELECT value FROM settings WHERE key = 'unrelated.keep'"
        ).fetchone()
        assert kept is not None and kept[0] == "keep-me"
    finally:
        conn.close()
    command.check(get_alembic_config(db))


@pytest.mark.asyncio
async def test_api_boots_after_network_rows_deleted(tmp_path: Path) -> None:
    from cbrowser.adapters.database.repository import ProfileRepository
    from cbrowser.adapters.database.session import create_engine_and_maker
    from cbrowser.domain.models import ProfileConfig

    db = tmp_path / "boot.db"
    cfg = get_alembic_config(db)
    command.upgrade(cfg, REVISION_0007)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            ("network.applied_version", '{"network": "legacy"}',
             "2026-01-01T00:00:00+00:00"),
        )
        conn.commit()
    finally:
        conn.close()
    run_database_migrations(db)
    engine, maker = create_engine_and_maker(db)
    try:
        repo = ProfileRepository(maker)
        created = await repo.create_profile(
            ProfileConfig(name="After", fingerprint_seed=3)
        )
        assert created.id
        assert await repo.get_profile(created.id) is not None
    finally:
        await engine.dispose()
