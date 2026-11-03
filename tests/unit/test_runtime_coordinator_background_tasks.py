"""Coordinator-owned background publish tasks (review hint, t007_code_f004)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from wait import wait_until
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.api.runtime_coordinator import RuntimeCoordinator
from cbrowser.domain.models import ProfileConfig
from cbrowser.services.profile_service import ProfileService


@pytest.fixture
async def profile_service(tmp_path: Path):
    db_path = tmp_path / "background_tasks.db"
    run_database_migrations(db_path)
    engine, maker = create_engine_and_maker(db_path)
    service = ProfileService(ProfileRepository(maker))
    yield service
    await engine.dispose()


@pytest.mark.asyncio
async def test_publish_change_later_tracks_task_and_logs_failure(
    profile_service, caplog
) -> None:
    profile = await profile_service.create_profile(ProfileConfig(name="p_publish"))
    coordinator = RuntimeCoordinator(
        supervisor_url=None,
        supervisor_token=None,
        profile_service=profile_service,
    )

    attempts: list[str] = []

    async def failing_publish(profile_id: str) -> None:
        attempts.append(profile_id)
        raise RuntimeError("background publish exploded")

    coordinator.publish_profile_change = failing_publish
    coordinator.publish_profile_change_later(profile.id)

    assert coordinator.publish_task_count == 1
    await wait_until(
        lambda: not coordinator._publish_tasks,
        timeout=5.0,
        interval=0.01,
        description="background publish tasks to drain",
    )

    assert attempts == [profile.id]
    assert coordinator.publish_task_count == 0
    assert "background publish exploded" in caplog.text


@pytest.mark.asyncio
async def test_stop_cancels_pending_publish_tasks(profile_service) -> None:
    coordinator = RuntimeCoordinator(
        supervisor_url=None,
        supervisor_token=None,
        profile_service=profile_service,
    )

    async def slow_publish(profile_id: str) -> None:
        await asyncio.Event().wait()

    coordinator.publish_profile_change = slow_publish
    coordinator.publish_profile_change_later("p_slow")
    assert coordinator.publish_task_count == 1

    await coordinator.stop()

    assert coordinator.publish_task_count == 0
