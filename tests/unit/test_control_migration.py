"""t031 migration 0009: isolated-DB upgrade + backup/restore (AC-001)."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from cbrowser.adapters.database.migrations import (
    get_alembic_config,
    run_database_migrations,
)
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.domain.models import ProfileConfig
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.services.control_service import ProfileControlService


def _upgrade_to(db_path, revision: str) -> None:
    resolved = Path(db_path).resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(get_alembic_config(resolved), revision)


async def _seed(db_path):
    run_database_migrations(db_path)
    engine, maker = create_engine_and_maker(db_path)
    repo = ProfileRepository(maker)
    profile = await repo.create_profile(
        ProfileConfig(name="Migrate", fingerprint_seed=1)
    )
    svc = ProfileControlService(maker)
    await svc.claim(profile.id, "tok-1", "exec-1")
    await svc.handoff(profile.id, "human_input")
    await engine.dispose()
    return profile.id


def _read_control(db_path):
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT owner, generation, handoff_reason,"
            " agent_reclaim_allowed FROM profile_controls"
        ).fetchone()
        return row
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_migration_upgrade_backup_restore(tmp_path):
    db = tmp_path / "migrate.db"
    pid = await _seed(db)
    assert pid
    # Row persisted through the real Alembic upgrade path.
    assert _read_control(db) == ("user", 2, "human_input", 0)
    # Backup: plain file copy of the SQLite database.
    backup = tmp_path / "backup.db"
    shutil.copyfile(db, backup)
    # Restore: copy back over a fresh path and verify the state reads.
    restored = tmp_path / "restored.db"
    shutil.copyfile(backup, restored)
    assert _read_control(restored) == ("user", 2, "human_input", 0)
    # The restored database still upgrades/migrates cleanly (idempotent).
    run_database_migrations(restored)
    assert _read_control(restored) == ("user", 2, "human_input", 0)


@pytest.mark.asyncio
async def test_upgrade_from_0008_preserves_profiles(tmp_path):
    """Review t031_test_f003: a pre-t031 database (head 0008) holding a
    profile upgrades to 0009 with the profile intact and a default user
    control state (no control row is backfilled by the migration)."""
    db = tmp_path / "v0008.db"
    _upgrade_to(db, "0008_artifact_delete_intent")
    engine, maker = create_engine_and_maker(db)
    repo = ProfileRepository(maker)
    profile = await repo.create_profile(
        ProfileConfig(name="Legacy", fingerprint_seed=7)
    )
    await engine.dispose()

    _upgrade_to(db, "head")

    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT name FROM profiles WHERE id = ?", (profile.id,)
        ).fetchone()
        control_rows = conn.execute(
            "SELECT COUNT(*) FROM profile_controls WHERE profile_id = ?",
            (profile.id,),
        ).fetchone()[0]
    finally:
        conn.close()
    assert row == ("Legacy",)
    assert control_rows == 0
    # The control service reads a default user state for the legacy
    # profile without a persisted control row.
    _, maker2 = create_engine_and_maker(db)
    svc = ProfileControlService(maker2)
    state = await svc.get_state(profile.id)
    assert state.owner == "user"
    assert state.generation == 0
    assert state.agent_reclaim_allowed is True
