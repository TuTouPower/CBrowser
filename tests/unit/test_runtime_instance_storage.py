"""Instance-scoped facts must survive stale writes from another generation."""

import json
from pathlib import Path

import httpx
import pytest
from cbrowser.runtime_agent.agent import create_agent_app
from cbrowser.runtime_agent.event_storage import (
    MAX_DOWNLOAD_EVENTS_PER_INSTANCE,
    CorruptStateError,
    EventStorage,
)
from cbrowser.runtime_agent.protocol import (
    DownloadEventRecord,
    RuntimeEventRecord,
    RuntimeStateRecord,
)


def state(instance: str, status: str, version: int) -> RuntimeStateRecord:
    return RuntimeStateRecord(
        profile_id="profile_a",
        runtime_instance_id=instance,
        config_version=version,
        state=status,
    )


def test_late_old_state_does_not_replace_current_instance(tmp_path: Path) -> None:
    storage = EventStorage(tmp_path)
    storage.save_state(state("instance_b", "running", 2))
    storage.save_state(state("instance_a", "stopped", 1))
    current = storage.get_instance_state("profile_a", "instance_b")
    assert current.state == "running"
    assert current.config_version == 2


def test_terminal_replay_wins_over_uncommitted_running_cache(tmp_path: Path) -> None:
    storage = EventStorage(tmp_path)
    storage.save_state(state("instance_a", "running", 1))
    storage.save_runtime_event(
        RuntimeEventRecord(
            event_id="unique_terminal_event",
            profile_id="profile_a",
            runtime_instance_id="instance_a",
            config_version=1,
            event_type="exit",
            exit_code=0,
            exit_reason="normal",
        )
    )
    terminal = storage.get_instance_state(
        "profile_a", "instance_a", recover_terminal=True
    )
    assert terminal.state == "stopped"
    assert terminal.exit_code == 0


def test_corrupt_instance_state_is_not_treated_as_fresh(tmp_path: Path) -> None:
    storage = EventStorage(tmp_path)
    storage.save_state(state("instance_a", "running", 1))
    path = tmp_path / "instances" / "instance_a" / "state.json"
    path.write_text("{broken")
    with pytest.raises(CorruptStateError):
        storage.get_instance_state("profile_a", "instance_a", recover_terminal=True)


@pytest.mark.asyncio
async def test_health_does_not_report_old_generation_as_current_stop(
    tmp_path: Path,
) -> None:
    storage = EventStorage(tmp_path)
    storage.save_state(state("instance_b", "running", 2))
    storage.save_state(state("instance_a", "stopped", 1))
    (tmp_path / "runner_info.json").write_text(
        json.dumps(
            {
                "profile_id": "profile_a",
                "runtime_instance_id": "instance_b",
                "config_version": 2,
            }
        )
    )
    app = create_agent_app(tmp_path, tmp_path / "downloads")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://agent"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["runtime_instance_id"] == "instance_b"
    assert response.json()["details"].get("state") != "stopped"


def _download_event(event_id: str, instance: str, index: int) -> DownloadEventRecord:
    return DownloadEventRecord(
        event_id=event_id,
        profile_id="profile_a",
        runtime_instance_id=instance,
        guid=event_id,
        state="completed",
        created_at=f"2026-01-01T00:00:00.{index:06d}+00:00",
    )


def test_download_events_are_bounded_per_instance_and_remain_reachable(
    tmp_path: Path,
) -> None:
    storage = EventStorage(tmp_path)
    total = MAX_DOWNLOAD_EVENTS_PER_INSTANCE + 5
    for index in range(total):
        storage.save_download_event(
            _download_event(f"dl_{index:04d}", "instance_a", index)
        )
    storage.save_download_event(_download_event("dl_other", "instance_b", total))

    events = storage.get_download_events()
    assert len(events) == MAX_DOWNLOAD_EVENTS_PER_INSTANCE + 1
    assert events[0].event_id == "dl_0005"
    assert events[-1].event_id == "dl_other"
    assert len(list(storage.download_events_dir.glob("*.json"))) == (
        MAX_DOWNLOAD_EVENTS_PER_INSTANCE + 1
    )
    assert storage.download_index_file.is_file()

    page = storage.get_download_events(limit=10, offset=5)
    assert [event.event_id for event in page] == [
        f"dl_{index:04d}" for index in range(10, 20)
    ]


def test_download_event_index_recovers_files_written_outside_the_index(
    tmp_path: Path,
) -> None:
    storage = EventStorage(tmp_path)
    first = _download_event("dl_first", "instance_a", 0)
    storage.save_download_event(first)
    extra = _download_event("dl_extra", "instance_a", 1)
    (storage.download_events_dir / f"{extra.event_id}.json").write_text(
        extra.model_dump_json(), encoding="utf-8"
    )

    events = storage.get_download_events()
    assert [event.event_id for event in events] == ["dl_first", "dl_extra"]


def test_saving_the_same_download_event_twice_does_not_duplicate(tmp_path: Path) -> None:
    storage = EventStorage(tmp_path)
    event = _download_event("dl_same", "instance_a", 0)
    storage.save_download_event(event)
    storage.save_download_event(event)

    assert [item.event_id for item in storage.get_download_events()] == ["dl_same"]
    assert len(list(storage.download_events_dir.glob("*.json"))) == 1


def test_corrupt_download_event_is_quarantined_and_does_not_block_new_events(
    tmp_path: Path,
) -> None:
    storage = EventStorage(tmp_path)
    corrupt = tmp_path / "events" / "downloads"
    corrupt.mkdir(parents=True, exist_ok=True)
    (corrupt / "corrupt.json").write_text("{not-json", encoding="utf-8")
    event = _download_event("dl_after_corrupt", "instance_a", 3)
    storage.save_download_event(event)
    assert (corrupt / "quarantine" / "corrupt.json").is_file()
    assert event.event_id in {item.event_id for item in storage.get_download_events()}
