from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.api.internal_supervisor import report_preview_observation
from cbrowser.api.runtime_coordinator import (
    RuntimeCoordinator,
    RuntimeEventBroadcaster,
)
from cbrowser.domain.models import (
    PreviewObservedRequest,
    ProfileConfig,
    ProfileRuntimeStatusEvent,
)
from cbrowser.preview import (
    PreviewMeta,
    PreviewPolicy,
    clear_preview,
    commit_preview,
    write_policy,
)
from cbrowser.services.profile_service import ProfileService


@pytest_asyncio.fixture
async def env(tmp_path: Path):
    db_path = tmp_path / "late.db"
    run_database_migrations(db_path)
    engine, session_maker = create_engine_and_maker(db_path)
    repo = ProfileRepository(session_maker)
    service = ProfileService(repo, data_root=tmp_path)
    broadcaster = RuntimeEventBroadcaster(maxlen=32)
    coordinator = RuntimeCoordinator(
        supervisor_url=None,
        supervisor_token=None,
        profile_service=service,
        event_broadcaster=broadcaster,
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(coordinator=coordinator))
    )
    yield SimpleNamespace(
        repo=repo,
        service=service,
        coordinator=coordinator,
        broadcaster=broadcaster,
        request=request,
        tmp_path=tmp_path,
    )
    await engine.dispose()


async def _new_bound_profile(env, instance: str = "inst-1") -> str:
    profile = await env.repo.create_profile(
        ProfileConfig(name="P"),
        user_data_dir=str(env.tmp_path / "udd" / "profile"),
    )
    await env.repo.bind_runtime_instance(profile.id, instance)
    return profile.id


def _seed_preview(env, profile_id: str) -> Path:
    directory = env.service.get_preview_dir(profile_id)
    policy = PreviewPolicy(enabled=True, epoch=0, runtime_instance_id="inst-1")
    write_policy(directory, policy)
    meta = PreviewMeta(
        captured_at="t-valid",
        runtime_instance_id="inst-1",
        policy_epoch=0,
    )
    assert commit_preview(directory, b"jpeg-seed", meta, policy) is True
    return directory


def _late_frame(directory: Path) -> None:
    clear_preview(directory)
    (directory / "frame_late.jpg").write_bytes(b"jpeg-late")


async def _assert_discarded(
    env,
    monkeypatch,
    profile_id: str,
    directory: Path,
    notification: PreviewObservedRequest,
) -> None:
    published: list[tuple[str, str]] = []

    async def spy(pid: str, captured_at: str) -> None:
        published.append((pid, captured_at))

    monkeypatch.setattr(env.coordinator, "publish_profile_preview", spy)

    assert (
        await env.service.record_preview_capture(
            profile_id,
            notification.captured_at,
            notification.runtime_instance_id,
            notification.policy_epoch,
        )
        is False
    )

    response = await report_preview_observation(
        profile_id, notification, env.request, env.service
    )
    assert response == {"status": "ok"}
    assert published == []
    assert list(directory.glob("*.jpg")) == []
    runtime = await env.service.get_runtime(profile_id)
    assert runtime.preview_captured_at != notification.captured_at


@pytest.mark.asyncio
async def test_disable_during_capture_drops_late_notification(env, monkeypatch) -> None:
    profile_id = await _new_bound_profile(env)
    directory = _seed_preview(env, profile_id)
    await env.service.update_profile(profile_id, {"capture_preview": False})
    write_policy(
        directory,
        PreviewPolicy(enabled=False, epoch=1, runtime_instance_id="inst-1"),
    )
    _late_frame(directory)

    await _assert_discarded(
        env,
        monkeypatch,
        profile_id,
        directory,
        PreviewObservedRequest(
            captured_at="t-late",
            runtime_instance_id="inst-1",
            policy_epoch=0,
        ),
    )


@pytest.mark.asyncio
async def test_old_epoch_notification_is_dropped(env, monkeypatch) -> None:
    profile_id = await _new_bound_profile(env)
    directory = _seed_preview(env, profile_id)
    await env.service.update_profile(profile_id, {"capture_preview": False})
    await env.service.update_profile(profile_id, {"capture_preview": True})
    _late_frame(directory)

    await _assert_discarded(
        env,
        monkeypatch,
        profile_id,
        directory,
        PreviewObservedRequest(
            captured_at="t-late",
            runtime_instance_id="inst-1",
            policy_epoch=1,
        ),
    )


@pytest.mark.asyncio
async def test_old_instance_after_reset_is_dropped(env, monkeypatch) -> None:
    profile_id = await _new_bound_profile(env)
    directory = _seed_preview(env, profile_id)
    await env.repo.report_observed_state(profile_id, "inst-1", "stopped")
    await env.service.reset_profile(profile_id)
    _late_frame(directory)

    await _assert_discarded(
        env,
        monkeypatch,
        profile_id,
        directory,
        PreviewObservedRequest(
            captured_at="t-late",
            runtime_instance_id="inst-1",
            policy_epoch=0,
        ),
    )


@pytest.mark.asyncio
async def test_valid_observation_publishes_preview(env, monkeypatch) -> None:
    profile_id = await _new_bound_profile(env)
    published: list[tuple[str, str]] = []

    async def spy(pid: str, captured_at: str) -> None:
        published.append((pid, captured_at))

    monkeypatch.setattr(env.coordinator, "publish_profile_preview", spy)
    notification = PreviewObservedRequest(
        captured_at="t1", runtime_instance_id="inst-1", policy_epoch=0
    )
    response = await report_preview_observation(
        profile_id, notification, env.request, env.service
    )
    assert response == {"status": "ok"}
    assert published == [(profile_id, "t1")]
    runtime = await env.service.get_runtime(profile_id)
    assert runtime.preview_captured_at == "t1"


def _runtime_event(profile_id: str) -> ProfileRuntimeStatusEvent:
    return ProfileRuntimeStatusEvent(
        profile_id=profile_id,
        desired_state="running",
        observed_state="running",
        updated_at="2026-10-31T00:00:00Z",
    )


@pytest.mark.asyncio
async def test_preview_frames_never_enter_replay_history(env) -> None:
    broadcaster = env.broadcaster
    published = [await broadcaster.publish(_runtime_event(f"p{i}")) for i in range(4)]
    baseline = len(broadcaster._history)
    assert baseline == 4

    for index in range(50):
        await env.coordinator.publish_profile_preview("p1", f"t{index}")

    assert len(broadcaster._history) == baseline
    assert all(event.event == "runtime_state" for event in broadcaster._history)

    generator = broadcaster.subscribe(last_event_id=published[0].id)
    frames = []
    try:
        for _ in range(3):
            frames.append(await asyncio.wait_for(generator.__anext__(), timeout=1.0))
    finally:
        await generator.aclose()

    assert len(frames) == 3
    assert all("event: runtime_state" in frame for frame in frames)
    assert all("profile_preview" not in frame for frame in frames)
    assert all(
        f"id: {event.id}" in frame for frame, event in zip(frames, published[1:])
    )


@pytest.mark.asyncio
async def test_transient_frame_reaches_live_subscriber_without_history(env) -> None:
    broadcaster = env.broadcaster
    generator = broadcaster.subscribe()
    task = asyncio.create_task(generator.__anext__())
    await asyncio.sleep(0.01)
    await env.coordinator.publish_profile_preview("p1", "t-live")
    try:
        frame = await asyncio.wait_for(task, timeout=1.0)
    finally:
        await generator.aclose()

    assert frame.startswith("event: profile_preview\n")
    assert '"event":"profile_preview"' in frame
    assert '"profile_id":"p1"' in frame
    assert '"captured_at":"t-live"' in frame
    assert len(broadcaster._history) == 0


async def test_disabled_policy_same_epoch_never_notifies_or_updates(env, monkeypatch):
    profile = await env.repo.create_profile(
        ProfileConfig(name="Disabled", capture_preview=False)
    )
    await env.repo.bind_runtime_instance(profile.id, "inst-1")
    enabled, epoch = await env.repo.get_preview_policy(profile.id)
    assert enabled is False
    published = []

    async def publish(*args):
        published.append(args)

    monkeypatch.setattr(env.coordinator, "publish_profile_preview", publish)
    response = await report_preview_observation(
        profile.id,
        PreviewObservedRequest(
            captured_at="late", runtime_instance_id="inst-1", policy_epoch=epoch
        ),
        env.request,
        env.service,
    )
    assert response == {"status": "ok"}
    assert published == []
    assert (await env.repo.get_runtime(profile.id)).preview_captured_at is None


@pytest.mark.asyncio
async def test_browser_state_clone_excludes_current_and_retained_preview_frames(env):
    from cbrowser.preview import frame_path, read_meta

    source_id = "dup-src"
    udd = env.tmp_path / "profiles" / source_id / "profile"
    udd.mkdir(parents=True)
    (udd / "state.txt").write_text("browser-state")
    profile = await env.repo.create_profile(
        ProfileConfig(name="Source"), profile_id=source_id, user_data_dir=str(udd)
    )
    directory = _seed_preview(env, profile.id)
    policy = PreviewPolicy(enabled=True, epoch=0, runtime_instance_id="inst-1")
    assert commit_preview(
        directory,
        b"new-frame",
        PreviewMeta(captured_at="next", runtime_instance_id="inst-1", policy_epoch=0),
        policy,
    )
    originals = list(directory.glob("frame_*.jpg"))
    assert len(originals) == 2
    selected = frame_path(directory, read_meta(directory))
    clone = await env.service.duplicate_profile(
        profile.id, include_browser_state=True, name="Clone"
    )
    target = env.service.get_preview_dir(clone.id)
    assert list(target.glob("*.jpg")) == []
    assert not (target / "meta.json").exists()
    assert not (target / "policy.json").exists()
    assert (
        env.tmp_path / "profiles" / clone.id / "profile" / "state.txt"
    ).read_text() == "browser-state"
    assert all(p.is_file() for p in originals)
    assert selected.read_bytes() == b"new-frame"
