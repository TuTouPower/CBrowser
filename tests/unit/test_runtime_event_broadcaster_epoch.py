"""SSE broadcaster event-id epoch semantics (t007_code_f001)."""

from __future__ import annotations

import asyncio

import pytest
from cbrowser.api.runtime_coordinator import RuntimeEventBroadcaster
from cbrowser.domain.models import ProfileRuntimeStatusEvent


def _event(profile_id: str) -> ProfileRuntimeStatusEvent:
    return ProfileRuntimeStatusEvent(
        profile_id=profile_id,
        desired_state="running",
        observed_state="running",
        updated_at="2026-10-31T00:00:00Z",
    )


def _split(event_id: str) -> tuple[str, int]:
    epoch, seq = event_id.rsplit(":", 1)
    return epoch, int(seq)


@pytest.mark.asyncio
async def test_event_ids_share_process_epoch_and_keep_monotonic_sequence() -> None:
    broadcaster = RuntimeEventBroadcaster(maxlen=10)
    first = await broadcaster.publish(_event("p1"))
    second = await broadcaster.publish(_event("p2"))

    epoch, seq_first = _split(first.id)
    epoch_second, seq_second = _split(second.id)

    assert epoch == epoch_second
    assert seq_second == seq_first + 1
    assert first.event == "runtime_state"
    assert first.data.profile_id == "p1"


@pytest.mark.asyncio
async def test_same_epoch_reconnect_replays_only_missing_events() -> None:
    broadcaster = RuntimeEventBroadcaster(maxlen=10)
    first = await broadcaster.publish(_event("p1"))
    second = await broadcaster.publish(_event("p2"))
    third = await broadcaster.publish(_event("p3"))

    generator = broadcaster.subscribe(last_event_id=first.id)
    try:
        chunk_one = await asyncio.wait_for(generator.__anext__(), timeout=1.0)
        chunk_two = await asyncio.wait_for(generator.__anext__(), timeout=1.0)
    finally:
        await generator.aclose()

    assert f"id: {second.id}" in chunk_one
    assert "p2" in chunk_one
    assert f"id: {third.id}" in chunk_two
    assert "p3" in chunk_two


@pytest.mark.asyncio
async def test_foreign_epoch_last_event_id_receives_full_snapshot() -> None:
    old_broadcaster = RuntimeEventBroadcaster(maxlen=10)
    old_event = await old_broadcaster.publish(_event("p_old"))

    new_broadcaster = RuntimeEventBroadcaster(maxlen=10)
    await new_broadcaster.publish(_event("p_new"))

    snapshot_calls = 0

    async def snapshot_provider() -> list[ProfileRuntimeStatusEvent]:
        nonlocal snapshot_calls
        snapshot_calls += 1
        return [_event("p_snapshot")]

    generator = new_broadcaster.subscribe(
        last_event_id=old_event.id,
        initial_snapshot_provider=snapshot_provider,
    )
    try:
        chunk = await asyncio.wait_for(generator.__anext__(), timeout=1.0)
    finally:
        await generator.aclose()

    assert snapshot_calls == 1
    assert "p_snapshot" in chunk
    assert "p_new" not in chunk


@pytest.mark.asyncio
async def test_legacy_numeric_last_event_id_receives_full_snapshot() -> None:
    broadcaster = RuntimeEventBroadcaster(maxlen=10)
    for index in range(1, 4):
        await broadcaster.publish(_event(f"p{index}"))

    snapshot_calls = 0

    async def snapshot_provider() -> list[ProfileRuntimeStatusEvent]:
        nonlocal snapshot_calls
        snapshot_calls += 1
        return [_event("p_snapshot")]

    generator = broadcaster.subscribe(
        last_event_id="500",
        initial_snapshot_provider=snapshot_provider,
    )
    try:
        chunk = await asyncio.wait_for(generator.__anext__(), timeout=1.0)
    finally:
        await generator.aclose()

    assert snapshot_calls == 1
    assert "p_snapshot" in chunk


@pytest.mark.asyncio
async def test_future_sequence_in_same_epoch_receives_full_snapshot() -> None:
    broadcaster = RuntimeEventBroadcaster(maxlen=10)
    first = await broadcaster.publish(_event("p1"))
    epoch, seq = _split(first.id)

    snapshot_calls = 0

    async def snapshot_provider() -> list[ProfileRuntimeStatusEvent]:
        nonlocal snapshot_calls
        snapshot_calls += 1
        return [_event("p_snapshot")]

    generator = broadcaster.subscribe(
        last_event_id=f"{epoch}:{seq + 100}",
        initial_snapshot_provider=snapshot_provider,
    )
    try:
        chunk = await asyncio.wait_for(generator.__anext__(), timeout=1.0)
    finally:
        await generator.aclose()

    assert snapshot_calls == 1
    assert "p_snapshot" in chunk


@pytest.mark.asyncio
async def test_snapshot_events_use_unique_event_ids() -> None:
    broadcaster = RuntimeEventBroadcaster(maxlen=10)

    async def snapshot_provider():
        return [_event("p1"), _event("p2"), _event("p3")]

    generator = broadcaster.subscribe(initial_snapshot_provider=snapshot_provider)
    try:
        chunks = [
            await asyncio.wait_for(generator.__anext__(), timeout=1.0)
            for _ in range(3)
        ]
    finally:
        await generator.aclose()

    ids = [
        line.removeprefix("id: ")
        for chunk in chunks
        for line in chunk.splitlines()
        if line.startswith("id: ")
    ]
    assert len(ids) == len(set(ids)) == 3
