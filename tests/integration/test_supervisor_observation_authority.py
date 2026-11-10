"""Lifecycle authority: Agent journals and Docker state, never sandbox files.

A real subprocess persists journals through the production Runtime Agent
storage code. The Supervisor translates them into observations, while an exit
journal written while Docker still reports the Browser running must be ignored.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator
from docker.errors import NotFound

from docker_doubles import FakeContainer, FakeDockerAdapter

pytest_plugins = ("test_supervisor_rpc",)

WRITE_EVENT = """
import json
import sys
from pathlib import Path

from cbrowser.runtime_agent.event_storage import EventStorage
from cbrowser.runtime_agent.protocol import RuntimeEventRecord

EventStorage(Path(sys.argv[1])).save_runtime_event(
    RuntimeEventRecord(**json.loads(sys.argv[2]))
)
"""


# Supervisor-facing adapter double: the shared FakeDockerAdapter from
# tests/fixtures/docker_doubles (t024 AC-014/A43), held to the production
# naming contract by tests/unit/test_docker_doubles_contract.py.
_FakeDocker = FakeDockerAdapter


def _write_event(run_dir: Path, **fields) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src/backend")
    subprocess.run(
        [sys.executable, "-c", WRITE_EVENT, str(run_dir), json.dumps(fields)],
        check=True,
        env=env,
    )


def _bind(server, token: str, profile_id: str, instance: str) -> None:
    response = server.post(
        "/api/v1/internal/supervisor/runtimes/bind",
        params={"profile_id": profile_id},
        headers={"Authorization": f"Bearer {token}"},
        json={"runtime_instance_id": instance, "config_version": 1},
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_lifecycle_journal_from_real_subprocess_reports_error(
    supervisor_api, tmp_path
):
    server, token = supervisor_api
    profile = server.post("/api/v1/profiles", json={"name": "observation"}).json()["id"]
    assert (
        server.patch(
            f"/api/v1/profiles/{profile}/runtime/desired-state",
            json={"desired_state": "running"},
        ).status_code
        == 200
    )
    _bind(server, token, profile, "inst_dead")
    data_root = tmp_path / "supervisor-data"
    docker = _FakeDocker(data_root)
    run_dir = docker.validator.data_root / "runtime-events" / profile

    _write_event(
        run_dir,
        event_id="life-1",
        profile_id=profile,
        runtime_instance_id="inst_dead",
        event_type="lifecycle",
        exit_code=None,
        exit_reason="process_observation_lost",
        config_version=1,
        payload={"exit_code": None},
    )

    async with httpx.AsyncClient(
        base_url=str(server.base_url),
        headers={"Authorization": f"Bearer {token}"},
        trust_env=False,
    ) as api:
        core = SupervisorCore(
            docker,
            PortAllocator(),
            EventForwarder(str(server.base_url), tmp_path / "spool", client=api),
            api,
        )
        assert await core.consume_disk_events() == 1

    runtime = server.get(f"/api/v1/profiles/{profile}/runtime").json()
    assert runtime["observed_state"] == "error"
    assert runtime["desired_state"] == "running"
    assert runtime["runtime_instance_id"] is None
    assert runtime["failure_count"] == 1
    assert runtime["restart_blocked"] is False


@pytest.mark.asyncio
async def test_forged_normal_exit_journal_does_not_change_running_intent(
    supervisor_api, tmp_path
):
    server, token = supervisor_api
    profile = server.post("/api/v1/profiles", json={"name": "forged"}).json()["id"]
    server.patch(
        f"/api/v1/profiles/{profile}/runtime/desired-state",
        json={"desired_state": "running"},
    )
    _bind(server, token, profile, "inst_alive")
    data_root = tmp_path / "supervisor-data"
    docker = _FakeDocker(data_root)
    docker.remember_profile_number(profile, 1)
    docker.containers.register(
        docker.get_browser_container_name(profile),
        FakeContainer("inst_alive", "running"),
    )
    run_dir = docker.validator.data_root / "runtime-events" / profile

    _write_event(
        run_dir,
        event_id="forged-exit",
        profile_id=profile,
        runtime_instance_id="inst_alive",
        event_type="exit",
        exit_code=0,
        exit_reason="normal",
        config_version=1,
    )

    async with httpx.AsyncClient(
        base_url=str(server.base_url),
        headers={"Authorization": f"Bearer {token}"},
        trust_env=False,
    ) as api:
        core = SupervisorCore(
            docker,
            PortAllocator(),
            EventForwarder(str(server.base_url), tmp_path / "spool", client=api),
            api,
        )
        assert await core.consume_disk_events() == 1

    runtime = server.get(f"/api/v1/profiles/{profile}/runtime").json()
    assert runtime["desired_state"] == "running"
    assert runtime["observed_state"] == "starting"
    assert runtime["runtime_instance_id"] == "inst_alive"
    assert runtime["failure_count"] == 0


@pytest.mark.asyncio
async def test_invalid_journal_is_quarantined_without_blocking(
    supervisor_api, tmp_path
):
    server, token = supervisor_api
    profile = server.post("/api/v1/profiles", json={"name": "bad-event"}).json()["id"]
    data_root = tmp_path / "supervisor-data"
    docker = _FakeDocker(data_root)
    instance_dir = (
        docker.validator.data_root
        / "runtime-events"
        / profile
        / "events"
        / "runtime"
        / "inst_bad"
    )
    instance_dir.mkdir(parents=True)
    (instance_dir / "broken.json").write_text("{not json", encoding="utf-8")
    (instance_dir / "bad-type.json").write_text(
        json.dumps(
            {
                "event_id": "bad-type",
                "profile_id": profile,
                "runtime_instance_id": "inst_bad",
                "event_type": "takeover",
                "config_version": 1,
            }
        ),
        encoding="utf-8",
    )

    async with httpx.AsyncClient(
        base_url=str(server.base_url),
        headers={"Authorization": f"Bearer {token}"},
        trust_env=False,
    ) as api:
        core = SupervisorCore(
            docker,
            PortAllocator(),
            EventForwarder(str(server.base_url), tmp_path / "spool", client=api),
            api,
        )
        assert await core.consume_disk_events() == 0

    quarantine = data_root / "quarantine" / "runtime-events" / profile / "inst_bad"
    assert {p.name for p in quarantine.iterdir()} == {"broken.json", "bad-type.json"}
