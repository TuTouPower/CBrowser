from __future__ import annotations

import pytest

from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.domain.models import ProfileConfig


@pytest.mark.asyncio
async def test_capture_preview_epoch_bumps_without_config_version(db_context):
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    profile = await repo.create_profile(ProfileConfig(name="Preview"))
    assert await repo.get_preview_policy(profile.id) == (True, 0)
    version = profile.current_config_version

    off = await repo.update_profile(profile.id, {"capture_preview": False})
    assert off is not None
    assert off.config.capture_preview is False
    assert await repo.get_preview_policy(profile.id) == (False, 1)
    assert off.current_config_version == version

    on = await repo.update_profile(profile.id, {"capture_preview": True})
    assert on is not None
    assert await repo.get_preview_policy(profile.id) == (True, 2)
    assert on.current_config_version == version

    unchanged = await repo.update_profile(profile.id, {"name": "Renamed"})
    assert unchanged is not None
    assert await repo.get_preview_policy(profile.id) == (True, 2)


@pytest.mark.asyncio
async def test_record_preview_capture_fences_epoch_instance_and_clear(db_context):
    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    profile = await repo.create_profile(ProfileConfig(name="Preview"))
    await repo.bind_runtime_instance(profile.id, "inst-1", config_version=1)

    assert await repo.record_preview_capture(profile.id, "t1", "inst-1", 0) is True
    runtime = await repo.get_runtime(profile.id)
    assert runtime.preview_captured_at == "t1"

    assert await repo.record_preview_capture(profile.id, "t2", "inst-1", 1) is False
    assert await repo.record_preview_capture(profile.id, "t3", "inst-2", 0) is False
    runtime = await repo.get_runtime(profile.id)
    assert runtime.preview_captured_at == "t1"

    await repo.clear_preview_capture(profile.id)
    runtime = await repo.get_runtime(profile.id)
    assert runtime.preview_captured_at is None


@pytest.mark.asyncio
async def test_disabled_same_epoch_rejects_capture(db_context):
    _engine, maker = db_context
    repo = ProfileRepository(maker)
    profile = await repo.create_profile(ProfileConfig(name="Disabled", capture_preview=False))
    await repo.bind_runtime_instance(profile.id, "inst-1", config_version=1)
    enabled, epoch = await repo.get_preview_policy(profile.id)
    assert enabled is False
    assert await repo.record_preview_capture(profile.id, "late", "inst-1", epoch) is False
    assert (await repo.get_runtime(profile.id)).preview_captured_at is None
