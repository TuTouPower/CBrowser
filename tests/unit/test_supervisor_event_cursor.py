"""Disk journals are consumed once per instance cursor and archived."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from cbrowser.runtime_agent.event_storage import (
    MAX_RUNTIME_EVENTS_PER_INSTANCE,
    EventStorage,
)
from cbrowser.runtime_agent.protocol import RuntimeEventRecord
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator


def _event(storage: EventStorage, event_id: str, instance: str = "inst_1") -> None:
    storage.save_runtime_event(
        RuntimeEventRecord(
            event_id=event_id,
            profile_id="p1",
            runtime_instance_id=instance,
            event_type="lifecycle",
            exit_reason="process_observation_lost",
            config_version=1,
        )
    )


async def _core(tmp_path) -> tuple[SupervisorCore, AsyncMock]:
    events = AsyncMock()
    # t022/A8: disk consumption uses the explicit three-state outcome; the
    # stub now models a delivered outcome instead of the old boolean.
    events.emit_event_with_outcome = AsyncMock(return_value="delivered")
    events.emit_event = AsyncMock(return_value=True)
    async with httpx.AsyncClient(base_url="http://127.0.0.1:1", trust_env=False) as api:
        core = SupervisorCore(
            SimpleNamespace(validator=PathValidator(tmp_path)),
            PortAllocator(),
            events,
            api,
        )
    return core, events


@pytest.mark.asyncio
async def test_cursor_processes_each_journal_once_and_archives(tmp_path) -> None:
    storage = EventStorage(tmp_path / "runtime-events" / "p1")
    _event(storage, "e1")
    _event(storage, "e2")

    core, events = await _core(tmp_path)
    assert await core.consume_disk_events() == 2
    assert events.emit_event_with_outcome.await_count == 2

    assert await core.consume_disk_events() == 0
    assert events.emit_event_with_outcome.await_count == 2

    archive = tmp_path / "runtime-events" / "p1" / "archive" / "inst_1"
    assert {p.name for p in archive.glob("*.json")} == {"e1.json", "e2.json"}
    cursors = json.loads((tmp_path / "control" / "event_cursors.json").read_text())
    assert cursors["p1"]["inst_1"][1] in {"e1.json", "e2.json"}

    # A restarted Supervisor rebuilds the cursor and does not replay archives.
    restarted, restarted_events = await _core(tmp_path)
    assert await restarted.consume_disk_events() == 0
    assert restarted_events.emit_event_with_outcome.await_count == 0


@pytest.mark.asyncio
async def test_new_journal_after_cursor_is_processed(tmp_path) -> None:
    storage = EventStorage(tmp_path / "runtime-events" / "p1")
    _event(storage, "e1")
    core, events = await _core(tmp_path)
    assert await core.consume_disk_events() == 1

    _event(storage, "e2")
    assert await core.consume_disk_events() == 1
    consumed = [call.kwargs["event_id"] for call in events.emit_event_with_outcome.await_args_list]
    assert consumed == ["e1", "e2"]


def test_agent_keeps_only_latest_events_per_instance(tmp_path) -> None:
    storage = EventStorage(tmp_path / "runtime-events" / "p1")
    for index in range(MAX_RUNTIME_EVENTS_PER_INSTANCE + 5):
        _event(storage, f"e{index:04d}")
    files = list(
        (tmp_path / "runtime-events" / "p1" / "events" / "runtime" / "inst_1")
        .glob("*.json")
    )
    assert len(files) == MAX_RUNTIME_EVENTS_PER_INSTANCE
    names = {p.stem for p in files}
    assert "e0000" not in names
    assert f"e{MAX_RUNTIME_EVENTS_PER_INSTANCE + 4:04d}" in names


@pytest.mark.asyncio
async def test_permanent_rejection_dead_letters_once_and_advances_cursor(
    tmp_path,
) -> None:
    """A8: a permanently rejected journal is quarantined exactly once, the
    persisted cursor moves past it, and it is never re-delivered."""
    storage = EventStorage(tmp_path / "runtime-events" / "p1")
    _event(storage, "e1")
    core, events = await _core(tmp_path)
    events.emit_event_with_outcome = AsyncMock(return_value="rejected")

    assert await core.consume_disk_events() == 0
    quarantined = list(
        (tmp_path / "quarantine" / "runtime-events" / "p1" / "inst_1").glob("*.json")
    )
    assert [p.name for p in quarantined] == ["e1.json"]
    cursors = json.loads((tmp_path / "control" / "event_cursors.json").read_text())
    assert cursors["p1"]["inst_1"][1] == "e1.json"

    # Restart: the persisted cursor prevents any re-delivery attempt.
    restarted, restarted_events = await _core(tmp_path)
    assert await restarted.consume_disk_events() == 0
    assert restarted_events.emit_event_with_outcome.await_count == 0


@pytest.mark.asyncio
async def test_unavailable_keeps_journal_pending_until_delivery(tmp_path) -> None:
    """A8: a temporarily unavailable API leaves the journal and cursor
    untouched; a later success forwards it exactly once."""
    storage = EventStorage(tmp_path / "runtime-events" / "p1")
    _event(storage, "e1")
    core, events = await _core(tmp_path)
    events.emit_event_with_outcome = AsyncMock(return_value="unavailable")

    assert await core.consume_disk_events() == 0
    journal = tmp_path / "runtime-events" / "p1" / "events" / "runtime" / "inst_1"
    assert [p.name for p in journal.glob("*.json")] == ["e1.json"]
    assert not (tmp_path / "control" / "event_cursors.json").exists()

    events.emit_event_with_outcome = AsyncMock(return_value="delivered")
    assert await core.consume_disk_events() == 1
    assert not list(journal.glob("*.json"))
