"""AC-011 (A46): idempotent replay is defined in one repository helper.

Identical replays (including after a commit race) return the original
result, a reused operation id with a different signature is a conflict,
and replaying against a since-deleted target has a predictable outcome:
update -> None, create -> the same profile identity restored.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from cbrowser.adapters.database import models as db_models
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.repository import (
    IdempotencyConflictError,
    ProfileRepository,
)
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.domain.models import ProfileConfig, utc_now_iso


@pytest.fixture
async def repo(tmp_path: Path):
    db = tmp_path / "idempotency.db"
    run_database_migrations(db)
    engine, maker = create_engine_and_maker(db)
    yield ProfileRepository(maker)
    await engine.dispose()


def _payload(name: str = "Idem") -> dict:
    return {"config": {"name": name}, "tags": []}


@pytest.mark.asyncio
async def test_concurrent_create_with_same_operation_returns_one_profile(repo):
    config = ProfileConfig(name="Idem", fingerprint_seed=3)
    results = await asyncio.gather(
        repo.create_profile(
            config, operation_id="op-create-1", req_payload=_payload()
        ),
        repo.create_profile(
            config, operation_id="op-create-1", req_payload=_payload()
        ),
    )
    assert results[0].id == results[1].id
    assert len(await repo.list_profiles()) == 1


@pytest.mark.asyncio
async def test_create_replay_with_different_signature_conflicts(repo):
    config = ProfileConfig(name="Idem", fingerprint_seed=3)
    await repo.create_profile(
        config, operation_id="op-create-2", req_payload=_payload()
    )
    with pytest.raises(IdempotencyConflictError):
        await repo.create_profile(
            config,
            operation_id="op-create-2",
            req_payload=_payload(name="Other"),
        )


@pytest.mark.asyncio
async def test_create_replay_after_delete_restores_same_identity(repo):
    config = ProfileConfig(name="Idem", fingerprint_seed=3)
    created = await repo.create_profile(
        config, operation_id="op-create-3", req_payload=_payload()
    )
    assert await repo.delete_profile(created.id) is True
    replayed = await repo.create_profile(
        config, operation_id="op-create-3", req_payload=_payload()
    )
    assert replayed.id == created.id
    assert replayed.config.name == "Idem"


@pytest.mark.asyncio
async def test_update_replay_applies_once_and_deleted_target_returns_none(repo):
    created = await repo.create_profile(ProfileConfig(name="Idem"))
    first = await repo.update_profile(
        created.id, {"notes": "once"}, operation_id="op-update-1"
    )
    assert first is not None
    version_after_first = first.current_config_version
    replay = await repo.update_profile(
        created.id, {"notes": "once"}, operation_id="op-update-1"
    )
    assert replay is not None
    assert replay.current_config_version == version_after_first

    with pytest.raises(IdempotencyConflictError):
        await repo.update_profile(
            created.id, {"notes": "changed"}, operation_id="op-update-1"
        )

    assert await repo.delete_profile(created.id) is True
    assert (
        await repo.update_profile(
            created.id, {"notes": "once"}, operation_id="op-update-1"
        )
        is None
    )


@pytest.mark.asyncio
async def test_concurrent_update_with_same_operation_applies_once(repo):
    created = await repo.create_profile(ProfileConfig(name="Idem"))
    results = await asyncio.gather(
        repo.update_profile(
            created.id, {"notes": "race"}, operation_id="op-update-race"
        ),
        repo.update_profile(
            created.id, {"notes": "race"}, operation_id="op-update-race"
        ),
    )
    assert all(result is not None for result in results)
    versions = {result.current_config_version for result in results}
    assert len(versions) == 1
    final = await repo.get_profile(created.id)
    assert final is not None
    assert final.current_config_version == versions.pop()


def test_orm_timestamps_use_the_single_domain_implementation():
    # SQLAlchemy wraps column-default callables, so identity is checked by
    # provenance: every ORM timestamp default must be the domain function.
    import cbrowser.domain.models as domain_models

    assert db_models.utc_now_iso is domain_models.utc_now_iso is utc_now_iso
    for model in (
        db_models.ProfileModel,
        db_models.ProfileConfigVersionModel,
        db_models.ProfileRuntimeModel,
        db_models.ArtifactModel,
        db_models.SettingModel,
        db_models.RuntimeEventModel,
        db_models.AuditEventModel,
        db_models.AdminModel,
        db_models.SessionModel,
        db_models.AutomationTokenModel,
    ):
        for column_name in ("created_at", "updated_at"):
            column = model.__table__.c.get(column_name)
            if column is None or column.default is None:
                continue
            fn = column.default.arg
            assert fn.__module__ == domain_models.__name__, (model, column_name)
            assert fn.__qualname__ == "utc_now_iso", (model, column_name)


@pytest.mark.asyncio
async def test_create_commit_race_recovers_through_integrity_error(repo):
    """Deterministic race injection (review t021_test_f001): the audit
    pre-check is made to miss exactly once — as if the competing request
    had not committed yet at check time — so the insert proceeds and the
    audit primary key produces a genuine IntegrityError at commit. The
    recovery branch must then resolve to the competitor's profile."""
    config = ProfileConfig(name="Idem", fingerprint_seed=3)
    winner = await repo.create_profile(
        config, operation_id="op-race-1", req_payload=_payload()
    )

    real_match = repo._match_operation_audit
    calls = {"count": 0}

    async def miss_first_match(session, operation_id, sig_hash):
        calls["count"] += 1
        if calls["count"] == 1:
            return None
        return await real_match(session, operation_id, sig_hash)

    repo._match_operation_audit = miss_first_match
    try:
        recovered = await repo.create_profile(
            config, operation_id="op-race-1", req_payload=_payload()
        )
    finally:
        repo._match_operation_audit = real_match
    # First call was the rigged pre-check; the recovery re-check is the
    # second — proving the IntegrityError branch (not the sequential
    # replay path) produced the result.
    assert calls["count"] == 2
    assert recovered.id == winner.id
    assert len(await repo.list_profiles()) == 1
