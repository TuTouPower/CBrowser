"""Coordinator-owned background publish tasks (review hint, t007_code_f004)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

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


@pytest.mark.asyncio
async def test_observation_sweep_selects_targets_by_batch(monkeypatch):
    # t083_code_f004: the 15 s observation sweep must page through
    # list_runtime_batch (one SELECT per batch), not one runtime read
    # per Profile.  The fake service deliberately offers no
    # get_runtime/list_profiles, so any per-Profile read would fail
    # the sweep instead of refreshing.
    runtimes = [
        SimpleNamespace(
            profile_id=f"p{i:03d}",
            desired_state="running" if i % 2 == 0 else "stopped",
            runtime_instance_id=f"inst_{i}" if i % 3 != 0 else None,
        )
        for i in range(250)
    ]
    calls: list = []

    async def list_runtime_batch(*, after_profile_id, limit):
        calls.append((after_profile_id, limit))
        if after_profile_id is None:
            start = 0
        else:
            start = next(
                i
                for i, r in enumerate(runtimes)
                if r.profile_id == after_profile_id
            ) + 1
        return runtimes[start : start + limit]

    service = SimpleNamespace(list_runtime_batch=list_runtime_batch)
    coordinator = RuntimeCoordinator(
        supervisor_url=None,
        supervisor_token=None,
        profile_service=service,
    )
    refreshed: list[str] = []

    async def refresh_transport(profile_id: str) -> None:
        refreshed.append(profile_id)

    async def refresh_search_defaults(profile_id: str) -> None:
        refreshed.append(profile_id)

    coordinator.refresh_transport = refresh_transport
    coordinator.refresh_search_defaults = refresh_search_defaults
    monkeypatch.setattr(
        RuntimeCoordinator, "OBSERVATION_REFRESH_INTERVAL_SEC", 0.05
    )
    coordinator._running = True
    task = asyncio.create_task(coordinator._observation_refresh_loop())
    try:
        await wait_until(
            lambda: refreshed,
            timeout=5.0,
            interval=0.01,
            description="first observation sweep to refresh",
        )
    finally:
        coordinator._running = False
        await asyncio.wait_for(task, timeout=5)
    # 250 runtimes at 200 per batch: exactly two fetches, the second
    # one keyed after the last Profile of the first batch.
    assert calls == [(None, 200), ("p199", 200)]
    expected = sorted(
        r.profile_id
        for r in runtimes
        if r.desired_state == "running"
        and r.runtime_instance_id is not None
    )
    assert sorted(set(refreshed)) == expected
