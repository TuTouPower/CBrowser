"""Instance-scoped facts must survive stale writes from another generation."""

import json
from pathlib import Path

import httpx
import pytest
from cbrowser.runtime_agent.agent import create_agent_app
from cbrowser.runtime_agent.event_storage import CorruptStateError, EventStorage
from cbrowser.runtime_agent.protocol import RuntimeEventRecord, RuntimeStateRecord


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
