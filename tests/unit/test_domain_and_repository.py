"""Unit tests for backend foundation.

Tests domain, repository, 8 tables, and event convergence.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest
from cbrowser.adapters.database.models import (
    Base,
    ProfileConfigVersionModel,
)
from cbrowser.adapters.database.repository import (
    IdempotencyConflictError,
    InstanceConflictError,
    InvalidConfigVersionError,
    ProfileRepository,
)
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.domain.models import Profile, ProfileConfig
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


@pytest.mark.asyncio
async def test_sqlite_pragmas_wal_and_busy_timeout(db_context):
    _engine, session_maker = db_context
    async with session_maker() as session:
        wal_result = await session.execute(text("PRAGMA journal_mode;"))
        journal_mode = wal_result.scalar_one_or_none()
        assert str(journal_mode).lower() == "wal"

        timeout_result = await session.execute(text("PRAGMA busy_timeout;"))
        busy_timeout = timeout_result.scalar_one_or_none()
        assert busy_timeout == 5000


@pytest.mark.asyncio
async def test_profile_domain_tables_exist(db_context):
    _engine, session_maker = db_context
    async with session_maker() as session:
        result = await session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        )
        tables = {row[0] for row in result.fetchall()}
        required_tables = {
            "profiles",
            "profile_config_versions",
            "profile_groups",
            "proxies",
            "profile_runtimes",
            "artifacts",
            "settings",
            "runtime_events",
            "audit_events",
        }
        assert required_tables.issubset(tables)
        assert "profile_tags" not in tables


@pytest.mark.asyncio
async def test_profile_crud_roundtrip_with_refs(db_context):
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    group = await repo.create_group("Finance", "slate", 0)
    proxy = await repo.create_proxy(
        {
            "name": "crud-proxy",
            "scheme": "socks5",
            "host": "127.0.0.1",
            "port": 1080,
        }
    )
    config = ProfileConfig(
        name="Test Profile With Refs",
        fingerprint_seed=123456,
        group_id=group.id,
        proxy_id=proxy.id,
        timezone="America/New_York",
        locale="en-US",
        screen_width=1920,
        screen_height=1080,
        gpu_family="nvidia",
        humanize=True,
        human_preset="careful",
        geoip=True,
        clipboard_sync=True,
        auto_launch=False,
        color_scheme="dark",
        launch_args=["--no-first-run", "--lang=en-US"],
        extension_paths=["/path/ext1"],
        allow_3p_cookies=False,
        set_google_default=True,
        capture_preview=True,
        restore_session=True,
        transparent_proxy=True,
        portable_cookies=False,
        notes="Important profile notes",
        sort_order=5,
    )

    # 1. Create
    profile = await repo.create_profile(config=config)
    assert profile.id is not None
    assert profile.config.name == "Test Profile With Refs"
    assert profile.config.fingerprint_seed == 123456
    assert profile.config.group_id == group.id
    assert profile.config.proxy_id == proxy.id
    assert profile.user_data_dir == f"/data/profiles/{profile.id}/profile"
    assert profile.current_config_version == 1

    # Check runtime initialized
    runtime = await repo.get_runtime(profile.id)
    assert runtime is not None
    assert runtime.desired_state == "stopped"
    assert runtime.observed_state == "stopped"
    assert runtime.config_version == 1

    # 2. Read
    fetched = await repo.get_profile(profile.id)
    assert fetched is not None
    assert fetched.config == config
    assert fetched.config.group_id == group.id
    assert fetched.config.proxy_id == proxy.id

    # 3. Update a runtime-config field -> new version
    updated = await repo.update_profile(
        profile.id,
        patch_data={"screen_width": 2560, "color_scheme": "light"},
    )
    assert updated is not None
    assert updated.config.color_scheme == "light"
    assert updated.config.screen_width == 2560
    assert updated.current_config_version == 2
    assert updated.config.group_id == group.id
    assert updated.config.proxy_id == proxy.id

    # 4. Delete
    deleted = await repo.delete_profile(profile.id)
    assert deleted is True
    assert await repo.get_profile(profile.id) is None
    assert await repo.get_runtime(profile.id) is None


@pytest.mark.asyncio
async def test_display_numbers_are_not_reused_after_delete(db_context):
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    first = await repo.create_profile(config=ProfileConfig(name="one"))
    second = await repo.create_profile(config=ProfileConfig(name="two"))
    assert (first.display_number, second.display_number) == (1, 2)
    assert await repo.delete_profile(second.id) is True
    third = await repo.create_profile(config=ProfileConfig(name="three"))
    assert third.display_number == 3
    assert (await repo.get_profile(first.id)).display_number == 1


@pytest.mark.asyncio
async def test_actual_db_constraint_failure_rollback(db_context):
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    config = ProfileConfig(name="Constraint Rollback Profile")
    p = await repo.create_profile(config)

    # Attempt a raw SQL insert that violates foreign key or constraint
    with pytest.raises(IntegrityError):
        async with session_maker() as session, session.begin():
            # Violate foreign key with invalid profile_id
            session.add(
                ProfileConfigVersionModel(
                    id="invalid-fk-version",
                    profile_id="nonexistent-profile-uuid",
                    version=99,
                    snapshot="{}",
                )
            )

    # Verify no corrupted row was inserted
    versions = await repo.list_config_versions(p.id)
    assert len(versions) == 1
    assert versions[0].version == 1


@pytest.mark.asyncio
async def test_desired_state_intent_does_not_invent_observed_runtime(db_context):
    """User intent MUST NOT invent actual runtime.

    Setting desired=running leaves observed=stopped.
    """
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    profile = await repo.create_profile(ProfileConfig(name="Intent Profile"))
    rt = await repo.set_desired_state(profile.id, "running")

    assert rt.desired_state == "running"
    assert rt.observed_state == "stopped"  # NOT running! Real container hasn't started
    assert rt.runtime_instance_id is None


@pytest.mark.asyncio
async def test_stopping_intent_does_not_claim_observed_stopped_before_event(db_context):
    """Stopping intent must NOT claim observed stopped before real exit event."""
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    profile = await repo.create_profile(ProfileConfig(name="Stopping Intent Profile"))
    await repo.bind_runtime_instance(profile.id, "inst_live_1", config_version=1)
    await repo.report_observed_state(profile.id, "inst_live_1", "running")

    # User expresses intent to stop
    rt = await repo.set_desired_state(profile.id, "stopped")
    assert rt.desired_state == "stopped"
    # Container is still shutting down: observed_state remains running!
    assert rt.observed_state == "running"
    assert rt.runtime_instance_id == "inst_live_1"


@pytest.mark.asyncio
async def test_profile_config_update_does_not_mutate_runtime_bound_version(db_context):
    """Runtime.config_version is bound snapshot; profile update does not bump it."""
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    profile = await repo.create_profile(ProfileConfig(name="Initial Name"))
    await repo.bind_runtime_instance(profile.id, "inst_cfg_test", config_version=1)

    # User modifies profile configuration to v2
    updated = await repo.update_profile(
        profile.id, ProfileConfig(name="Updated Name", screen_width=2560)
    )
    assert updated.current_config_version == 2

    # Container is still running v1 snapshot!
    rt = await repo.get_runtime(profile.id)
    assert rt.config_version == 1


@pytest.mark.asyncio
async def test_idempotency_conflict_on_different_payload(db_context):
    """Reusing operation_id with different payload raises error."""
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    op_id = "op_unique_test_1"
    cfg1 = ProfileConfig(name="Initial Name")
    p1 = await repo.create_profile(cfg1, operation_id=op_id)

    # Replaying same payload returns same profile
    p1_replay = await repo.create_profile(cfg1, operation_id=op_id)
    assert p1_replay.id == p1.id

    # Reusing same op_id with different payload raises IdempotencyConflictError
    cfg2 = ProfileConfig(name="Completely Different Name")
    with pytest.raises(IdempotencyConflictError):
        await repo.create_profile(cfg2, operation_id=op_id)


@pytest.mark.asyncio
async def test_concurrent_updates_atomic_retry(db_context):
    """Concurrent updates with different operation_ids succeed."""
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    profile = await repo.create_profile(ProfileConfig(name="Base Profile"))
    pid = profile.id

    tasks = [
        repo.update_profile(
            pid,
            ProfileConfig(name=f"Concurrent Writer {i}"),
            operation_id=f"concurrent_op_{i}",
        )
        for i in range(6)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for r in results:
        assert isinstance(r, Profile), f"Expected Profile, got {r}"

    # Versions list should have 7 versions (1 initial + 6 updates)
    versions = await repo.list_config_versions(pid)
    assert len(versions) == 7
    final_p = await repo.get_profile(pid)
    assert final_p.current_config_version == 7


@pytest.mark.asyncio
async def test_disjoint_concurrent_patch_name_and_notes(db_context):
    """Concurrent disjoint patches in multiple rounds preserve both fields."""
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    p = await repo.create_profile(
        ProfileConfig(name="initial_name", notes="initial_notes")
    )
    pid = p.id

    for r in range(5):
        new_name = f"r{r}_name"
        new_notes = f"r{r}_notes"

        t1 = repo.update_profile(pid, patch_data={"name": new_name})
        t2 = repo.update_profile(pid, patch_data={"notes": new_notes})

        res1, res2 = await asyncio.gather(t1, t2)
        assert res1 is not None and res2 is not None

        # Verify current state in database has BOTH changes preserved
        curr = await repo.get_profile(pid)
        assert curr.config.name == new_name, f"Round {r}: name lost!"
        assert curr.config.notes == new_notes, f"Round {r}: notes lost!"


@pytest.mark.asyncio
async def test_operation_id_conflict_across_different_profiles(db_context):
    """Same operation_id across different profile IDs raises error."""
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    p1 = await repo.create_profile(ProfileConfig(name="Profile 1"))
    p2 = await repo.create_profile(ProfileConfig(name="Profile 2"))

    op_id = "op_shared_key_123"
    await repo.update_profile(
        p1.id, patch_data={"name": "P1 Updated"}, operation_id=op_id
    )

    # Calling update on p2 with same operation_id must raise IdempotencyConflictError
    with pytest.raises(IdempotencyConflictError):
        await repo.update_profile(
            p2.id, patch_data={"name": "P2 Updated"}, operation_id=op_id
        )


@pytest.mark.asyncio
async def test_late_bind_rejected_when_active_instance_exists(db_context):
    """Late bind of old instance cannot overwrite active instance without CAS."""
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    p = await repo.create_profile(ProfileConfig(name="Bind CAS Profile"))
    await repo.bind_runtime_instance(p.id, "inst_B", config_version=1)
    await repo.report_observed_state(p.id, "inst_B", "running")

    # Late bind of inst_A should raise InstanceConflictError
    with pytest.raises(InstanceConflictError):
        await repo.bind_runtime_instance(p.id, "inst_A", config_version=1)

    # Active instance B is preserved
    rt = await repo.get_runtime(p.id)
    assert rt.runtime_instance_id == "inst_B"
    assert rt.observed_state == "running"

    # Same instance re-bind is idempotent; does not regress observed_state
    await repo.bind_runtime_instance(p.id, "inst_B", config_version=1)
    rt2 = await repo.get_runtime(p.id)
    assert rt2.observed_state == "running"


@pytest.mark.asyncio
async def test_desired_state_idempotent_replay_does_not_clear_failure_count(db_context):
    """Replay of initial start operation_id after crash does NOT reset failure_count."""
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    p = await repo.create_profile(ProfileConfig(name="Replay Test Profile"))
    start_op_id = "op_start_initial_001"

    # Initial start
    rt1 = await repo.set_desired_state(p.id, "running", operation_id=start_op_id)
    assert rt1.desired_state == "running"

    # Bind and crash; the failure is an authoritative Supervisor observation.
    await repo.bind_runtime_instance(p.id, "inst_crash_1", config_version=1)
    await repo.report_observed_state(
        p.id, "inst_crash_1", "error", reason="process_lost"
    )

    rt_after_crash = await repo.get_runtime(p.id)
    assert rt_after_crash.failure_count == 1

    # Replay initial start with SAME operation_id
    rt_replay = await repo.set_desired_state(p.id, "running", operation_id=start_op_id)
    # Failure count MUST REMAIN 1, not reset to 0!
    assert rt_replay.failure_count == 1

    # Fresh manual retry (new operation_id) clears failure_count
    rt_fresh = await repo.set_desired_state(
        p.id, "running", operation_id="op_start_fresh_retry_002"
    )
    assert rt_fresh.failure_count == 0


@pytest.mark.asyncio
async def test_runtime_backoff_deadline_facts_are_persisted(db_context):
    """API records backoff_started_at / next_retry_at on an observed failure.

    next_retry_at is the authoritative server-side deadline, exactly
    backoff_started_at + AUTO_RETRY_DELAYS[failure_count - 1]. A running
    observation clears the stale backoff facts.
    """
    from datetime import datetime

    from cbrowser.domain.runtime_policy import AUTO_RETRY_DELAYS

    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    p = await repo.create_profile(ProfileConfig(name="Backoff Facts Profile"))
    await repo.set_desired_state(p.id, "running")

    for strike, delay in enumerate(AUTO_RETRY_DELAYS, start=1):
        instance_id = f"inst_crash_{strike}"
        await repo.bind_runtime_instance(p.id, instance_id, config_version=1)
        await repo.report_observed_state(
            p.id, instance_id, "error", reason="process_lost"
        )
        rt = await repo.get_runtime(p.id)
        assert rt.failure_count == strike
        assert rt.backoff_started_at is not None
        assert rt.next_retry_at is not None
        started = datetime.fromisoformat(rt.backoff_started_at)
        deadline = datetime.fromisoformat(rt.next_retry_at)
        assert (deadline - started).total_seconds() == delay

    await repo.bind_runtime_instance(p.id, "inst_recovered", config_version=1)
    await repo.report_observed_state(p.id, "inst_recovered", "running")
    rt_running = await repo.get_runtime(p.id)
    assert rt_running.backoff_started_at is None
    assert rt_running.next_retry_at is None


@pytest.mark.asyncio
async def test_wal_reader_parallelism_while_write_lock_held(
    db_context, temp_db_path: Path
):
    """Ordinary readers do not block when connection holds BEGIN IMMEDIATE."""
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    p = await repo.create_profile(ProfileConfig(name="Parallel Read Profile"))

    # External connection holds BEGIN IMMEDIATE
    ext_conn = sqlite3.connect(str(temp_db_path), timeout=0.1)
    ext_conn.execute("BEGIN IMMEDIATE;")

    import time

    t0 = time.time()
    # Read profile while write lock is held: must return promptly
    fetched = await repo.get_profile(p.id)
    elapsed = time.time() - t0

    # The write lock must still be held now (t024 AC-007/A28): the reader
    # returned while the writer lock was in force, which is the structural
    # proof it never blocked on it.  A second immediate writer must fail.
    probe_conn = sqlite3.connect(str(temp_db_path), timeout=0.1)
    try:
        with pytest.raises(sqlite3.OperationalError):
            probe_conn.execute("BEGIN IMMEDIATE;")
    finally:
        probe_conn.close()

    ext_conn.rollback()
    ext_conn.close()

    assert fetched is not None
    assert fetched.config.name == "Parallel Read Profile"
    # Original promptness bound (restored verbatim at review): the
    # structural proof above is the primary evidence; this bound keeps a
    # near-budget stall from passing as "prompt".
    assert elapsed < 1.0, f"Reader blocked on writer! Elapsed: {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_runtime_instance_config_version_guard_after_runtime_config_change(
    db_context,
):
    """Same instance rebind or observation with unapplied version is rejected."""
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    p = await repo.create_profile(ProfileConfig(name="Version Guard Profile"))
    await repo.bind_runtime_instance(p.id, "inst_X", config_version=1)

    # A runtime-config field change creates v2 (t035 AC-006); metadata-only
    # edits no longer produce a new version.
    await repo.update_profile(p.id, patch_data={"screen_width": 2560})

    # 1. Observation report with unapplied v2 on inst_X bound to 1 -> rejected
    with pytest.raises(InvalidConfigVersionError):
        await repo.report_observed_state(p.id, "inst_X", "running", config_version=2)

    # 2. Same instance re-bind with v2 -> rejected
    with pytest.raises(InvalidConfigVersionError):
        await repo.bind_runtime_instance(p.id, "inst_X", config_version=2)

    # 3. New instance inst_Y bound to v2 with CAS expected=inst_X -> succeeds
    rt_new = await repo.bind_runtime_instance(
        p.id, "inst_Y", config_version=2, expected_current_instance="inst_X"
    )
    assert rt_new.runtime_instance_id == "inst_Y"
    assert rt_new.config_version == 2


def test_exported_openapi_schema_matches_live_app():
    """Verify deep canonical equality between exported openapi schema and live app."""
    from cbrowser.api.app import create_app

    app = create_app()
    live_schema = app.openapi()
    openapi_file = (
        Path(__file__).resolve().parent.parent.parent
        / "schemas"
        / "openapi"
        / "cbrowser_v1.json"
    )
    exported_schema = json.loads(openapi_file.read_text(encoding="utf-8"))
    assert live_schema == exported_schema


def test_models_match_migrations(temp_db_path: Path):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    run_database_migrations(temp_db_path)
    engine, _ = create_engine_and_maker(temp_db_path)

    def _diff(connection):
        context = MigrationContext.configure(connection)
        return compare_metadata(context, Base.metadata)

    import asyncio

    async def run():
        try:
            async with engine.connect() as connection:
                return await connection.run_sync(_diff)
        finally:
            await engine.dispose()

    assert asyncio.run(run()) == []
