"""Private SSE snapshots and snapshot/live handoff (t022 A44 / AC-012)."""

from __future__ import annotations

import asyncio

import pytest
from cbrowser.api.runtime_coordinator import RuntimeEventBroadcaster
from cbrowser.domain.models import ProfileRuntimeStatusEvent


def _event(profile_id: str, observed: str = "running") -> ProfileRuntimeStatusEvent:
    return ProfileRuntimeStatusEvent(
        profile_id=profile_id,
        desired_state="running",
        observed_state=observed,
        updated_at="2026-10-31T00:00:00Z",
    )


def _id_of(frame: str) -> str:
    for line in frame.splitlines():
        if line.startswith("id: "):
            return line[4:]
    raise AssertionError(f"frame has no id: {frame!r}")


@pytest.mark.asyncio
async def test_snapshot_is_private_and_carries_live_base_point() -> None:
    """A44: snapshot frames never enter the shared history and all carry
    the base point id (last live sequence when the snapshot was taken)."""
    broadcaster = RuntimeEventBroadcaster(maxlen=10)
    live = await broadcaster.publish(_event("p_live"))

    async def provider() -> list[ProfileRuntimeStatusEvent]:
        return [_event("p_snap_a"), _event("p_snap_b")]

    generator = broadcaster.subscribe(initial_snapshot_provider=provider)
    try:
        frame_a = await asyncio.wait_for(generator.__anext__(), timeout=1.0)
        frame_b = await asyncio.wait_for(generator.__anext__(), timeout=1.0)
    finally:
        await generator.aclose()

    assert "p_snap_a" in frame_a and "p_snap_b" in frame_b
    assert _id_of(frame_a) == live.id == _id_of(frame_b)

    # A second subscriber replaying from before the live event receives
    # only the live event: the first subscriber's snapshot rows are not in
    # the shared history and cannot be replayed to anyone else.
    epoch = live.id.rsplit(":", 1)[0]
    replay = broadcaster.subscribe(last_event_id=f"{epoch}:0")
    try:
        frame = await asyncio.wait_for(replay.__anext__(), timeout=1.0)
    finally:
        await replay.aclose()
    assert _id_of(frame) == live.id
    assert "p_live" in frame and "p_snap" not in frame


@pytest.mark.asyncio
async def test_window_overflow_rebuilds_via_snapshot_not_silent_truncation() -> None:
    """A44: an id older than the retained window triggers an explicit
    snapshot rebuild instead of silently dropping the missing events."""
    broadcaster = RuntimeEventBroadcaster(maxlen=2)
    first = await broadcaster.publish(_event("p1"))
    await broadcaster.publish(_event("p2"))
    await broadcaster.publish(_event("p3"))
    await broadcaster.publish(_event("p4"))

    calls = 0

    async def provider() -> list[ProfileRuntimeStatusEvent]:
        nonlocal calls
        calls += 1
        return [_event("p_full")]

    generator = broadcaster.subscribe(
        last_event_id=first.id, initial_snapshot_provider=provider
    )
    try:
        frame = await asyncio.wait_for(generator.__anext__(), timeout=1.0)
    finally:
        await generator.aclose()
    assert calls == 1
    assert "p_full" in frame


@pytest.mark.asyncio
async def test_unserviceable_id_without_provider_signals_resync() -> None:
    """A44: with no snapshot provider, an out-of-window id yields an
    explicit resync-required marker rather than a silently cut stream."""
    broadcaster = RuntimeEventBroadcaster(maxlen=2)
    first = await broadcaster.publish(_event("p1"))
    await broadcaster.publish(_event("p2"))
    await broadcaster.publish(_event("p3"))
    await broadcaster.publish(_event("p4"))

    generator = broadcaster.subscribe(last_event_id=first.id)
    try:
        frame = await asyncio.wait_for(generator.__anext__(), timeout=1.0)
    finally:
        await generator.aclose()
    assert frame.startswith(": resync-required")


@pytest.mark.asyncio
async def test_publish_during_snapshot_follows_base_point_without_gap() -> None:
    """A44: a live event published while a snapshot is being built is
    delivered after the snapshot, in order, with a greater sequence."""
    broadcaster = RuntimeEventBroadcaster(maxlen=10)
    base = await broadcaster.publish(_event("p_base"))
    provider_started = asyncio.Event()
    release_provider = asyncio.Event()

    async def provider() -> list[ProfileRuntimeStatusEvent]:
        provider_started.set()
        await release_provider.wait()
        return [_event("p_snap")]

    generator = broadcaster.subscribe(initial_snapshot_provider=provider)
    first_frame_task = asyncio.create_task(generator.__anext__())
    await asyncio.wait_for(provider_started.wait(), timeout=1.0)
    publish_task = asyncio.create_task(broadcaster.publish(_event("p_live")))
    # The provider is blocked on an event only this test releases, so the
    # snapshot holds the ordering lock for the whole window: publish cannot
    # complete no matter how often it is scheduled. Yield repeatedly to
    # give it every chance to run before asserting.
    for _ in range(10):
        await asyncio.sleep(0)
    assert not publish_task.done()  # publish shares the snapshot ordering lock
    release_provider.set()
    snapshot_frame = await asyncio.wait_for(first_frame_task, timeout=1.0)
    live_event = await asyncio.wait_for(publish_task, timeout=1.0)
    live_frame = await asyncio.wait_for(generator.__anext__(), timeout=1.0)
    await generator.aclose()

    assert "p_snap" in snapshot_frame
    assert _id_of(snapshot_frame) == base.id
    assert _id_of(live_frame) == live_event.id
    assert int(live_event.id.rsplit(":", 1)[1]) == int(base.id.rsplit(":", 1)[1]) + 1


@pytest.mark.asyncio
async def test_concurrent_subscribers_do_not_share_snapshot_state() -> None:
    """A44: two simultaneously active subscribers — one rebuilding from a
    snapshot, one replaying live history — never see each other's frames
    and both continue with the same live stream afterwards."""
    broadcaster = RuntimeEventBroadcaster(maxlen=10)
    first = await broadcaster.publish(_event("p_first"))

    async def provider() -> list[ProfileRuntimeStatusEvent]:
        return [_event("p_snapshot_only")]

    snapshot_sub = broadcaster.subscribe(initial_snapshot_provider=provider)
    replay_sub = broadcaster.subscribe(last_event_id=first.id)
    try:
        snapshot_frame = await asyncio.wait_for(
            snapshot_sub.__anext__(), timeout=1.0
        )
        assert "p_snapshot_only" in snapshot_frame

        live = await broadcaster.publish(_event("p_second"))
        live_for_snapshot = await asyncio.wait_for(
            snapshot_sub.__anext__(), timeout=1.0
        )
        live_for_replay = await asyncio.wait_for(
            replay_sub.__anext__(), timeout=1.0
        )
        # The replay subscriber's first frame is the live event itself (the
        # snapshot never entered the shared history); both subscribers now
        # converge on the identical live frame.
        assert _id_of(live_for_replay) == live.id
        assert _id_of(live_for_snapshot) == live.id
        assert "p_snapshot_only" not in live_for_replay
    finally:
        await snapshot_sub.aclose()
        await replay_sub.aclose()
