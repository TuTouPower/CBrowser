"""Unit tests for v2 backend foundation.

Tests domain, repository, 8 tables, and event convergence.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest
import pytest_asyncio
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
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.domain.models import Profile, ProfileConfig, Tag
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_v2.db"


@pytest_asyncio.fixture
async def db_context(temp_db_path: Path):
    engine, session_maker = create_engine_and_maker(temp_db_path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine, session_maker
    await engine.dispose()


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
async def test_eight_tables_exist(db_context):
    _engine, session_maker = db_context
    async with session_maker() as session:
        result = await session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        )
        tables = {row[0] for row in result.fetchall()}
        required_tables = {
            "profiles",
            "profile_config_versions",
            "profile_tags",
            "profile_runtimes",
            "artifacts",
            "settings",
            "runtime_events",
            "audit_events",
        }
        assert required_tables.issubset(tables)


@pytest.mark.asyncio
async def test_profile_crud_and_full_legacy_fields_roundtrip(db_context):
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    config = ProfileConfig(
        name="Test Profile Legacy",
        fingerprint_seed=123456,
        proxy="socks5://user:pass@127.0.0.1:1080",
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
        launch_args=["--flag-one", "--flag-two"],
        extension_paths=["/path/ext1"],
        allow_3p_cookies=False,
        set_google_default=True,
        capture_preview=True,
        restore_session=True,
        transparent_proxy=True,
        portable_cookies=False,
        notes="Important profile notes",
        sort_order=5,
        runtime_mode="docker",
        viewer_mode="webrtc",
    )
    tags = [Tag(tag="finance", color="#112233"), Tag(tag="secure", color=None)]

    # 1. Create
    profile = await repo.create_profile(config=config, tags=tags)
    assert profile.id is not None
    assert profile.config.name == "Test Profile Legacy"
    assert profile.config.fingerprint_seed == 123456
    assert profile.config.proxy == "socks5://user:pass@127.0.0.1:1080"
    assert profile.config.runtime_mode == "docker"
    assert profile.config.viewer_mode == "webrtc"
    assert profile.user_data_dir == f"/data/profiles/{profile.id}/profile"
    assert len(profile.tags) == 2
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
    assert {t.tag for t in fetched.tags} == {"finance", "secure"}

    # 3. Update
    updated_config = config.model_copy(
        update={
            "name": "Renamed Profile",
            "color_scheme": "light",
            "screen_width": 2560,
        }
    )
    updated = await repo.update_profile(
        profile.id,
        patch_data=updated_config,
        tags=[Tag(tag="updated", color="#445566")],
    )
    assert updated is not None
    assert updated.config.name == "Renamed Profile"
    assert updated.config.color_scheme == "light"
    assert updated.config.screen_width == 2560
    assert updated.current_config_version == 2
    assert len(updated.tags) == 1
    assert updated.tags[0].tag == "updated"

    # 4. Delete
    deleted = await repo.delete_profile(profile.id)
    assert deleted is True
    assert await repo.get_profile(profile.id) is None
    assert await repo.get_runtime(profile.id) is None


@pytest.mark.asyncio
async def test_immutable_config_version_snapshots_include_tags(db_context):
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    config_v1 = ProfileConfig(name="Initial Name", screen_width=1280, screen_height=720)
    profile = await repo.create_profile(
        config_v1, tags=[Tag(tag="v1_tag", color="#aaa")]
    )
    v1_id = profile.id

    # Mutate to v2
    config_v2 = profile.config.model_copy(
        update={"name": "Second Name", "screen_width": 1920}
    )
    await repo.update_profile(
        v1_id, patch_data=config_v2, tags=[Tag(tag="v2_tag", color="#bbb")]
    )

    # Mutate to v3
    config_v3 = config_v2.model_copy(
        update={"name": "Third Name", "screen_width": 2560}
    )
    await repo.update_profile(
        v1_id, patch_data=config_v3, tags=[Tag(tag="v3_tag", color="#ccc")]
    )

    # Check snapshots
    versions = await repo.list_config_versions(v1_id)
    assert len(versions) == 3
    assert [v.version for v in versions] == [1, 2, 3]

    v1_snapshot = await repo.get_config_version(v1_id, 1)
    assert v1_snapshot is not None
    assert v1_snapshot.config["name"] == "Initial Name"
    assert v1_snapshot.config["screen_width"] == 1280
    assert len(v1_snapshot.tags) == 1
    assert v1_snapshot.tags[0].tag == "v1_tag"

    v2_snapshot = await repo.get_config_version(v1_id, 2)
    assert v2_snapshot is not None
    assert v2_snapshot.config["name"] == "Second Name"
    assert v2_snapshot.config["screen_width"] == 1920
    assert v2_snapshot.tags[0].tag == "v2_tag"

    v3_snapshot = await repo.get_config_version(v1_id, 3)
    assert v3_snapshot is not None
    assert v3_snapshot.config["name"] == "Third Name"
    assert v3_snapshot.config["screen_width"] == 2560
    assert v3_snapshot.tags[0].tag == "v3_tag"


@pytest.mark.asyncio
async def test_actual_db_constraint_failure_rollback(db_context):
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    config = ProfileConfig(name="Constraint Rollback Profile")
    p = await repo.create_profile(config, tags=[])

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

    ext_conn.rollback()
    ext_conn.close()

    assert fetched is not None
    assert fetched.config.name == "Parallel Read Profile"
    assert elapsed < 1.0, f"Reader blocked on writer! Elapsed: {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_idempotent_create_tag_conflict_detected(db_context):
    """Reusing operation_id on create with different tags raises error."""
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    op_id = "op_tag_conflict_test"
    cfg = ProfileConfig(name="Tag Test Profile")
    await repo.create_profile(cfg, tags=[Tag(tag="tag_A")], operation_id=op_id)

    # Calling create with different tags must raise IdempotencyConflictError
    with pytest.raises(IdempotencyConflictError):
        await repo.create_profile(cfg, tags=[Tag(tag="tag_B")], operation_id=op_id)


@pytest.mark.asyncio
async def test_same_instance_rebind_and_observation_config_version_guard(db_context):
    """Same instance rebind or observation with unapplied version is rejected."""
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)

    p = await repo.create_profile(ProfileConfig(name="Version Guard Profile"))
    await repo.bind_runtime_instance(p.id, "inst_X", config_version=1)

    # Save v2
    await repo.update_profile(p.id, patch_data={"name": "v2 Name"})

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
