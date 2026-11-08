"""A8: terminal observation trusts the instance-native exit journal."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from cbrowser.supervisor.core import ActiveSession, SupervisorCore
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator
from cbrowser.supervisor.recovery_coordinator import RecoveryCoordinator
from docker.errors import NotFound


class _FakeContainer:
    def __init__(self, instance_id, status, config_version=1):
        self.labels = {
            "com.cbrowser.instance-id": instance_id,
            "com.cbrowser.config-version": str(config_version),
        }
        self.status = status
        self.id = f"c_{instance_id}"


class _FakeContainers:
    def __init__(self):
        self._c = {}

    def set(self, name, container):
        if container is None:
            self._c.pop(name, None)
        else:
            self._c[name] = container

    def get(self, name):
        if name not in self._c:
            raise NotFound("no such container")
        return self._c[name]


class _FakeDocker:
    def __init__(self, data_root, container_status):
        self.validator = PathValidator(data_root)
        self.containers = _FakeContainers()
        if container_status is not None:
            self.containers.set(
                "cbrowser-browser-p", _FakeContainer("inst1", container_status)
            )
        self.client = SimpleNamespace(
            containers=self.containers,
            api=SimpleNamespace(
                inspect_container=lambda cid: {
                    "HostConfig": {
                        "PortBindings": {"30000/udp": [{"HostPort": "30001"}]}
                    }
                }
            ),
        )

    def get_browser_container_name(self, profile_id):
        return f"cbrowser-browser-{profile_id}"

    def get_stream_container_name(self, profile_id):
        return f"cbrowser-stream-{profile_id}"

    def scan_active_containers(self):
        return []

    def prepare_profile_directories(self, profile_id):
        runtime = self.validator.get_runtime_dir(profile_id)
        runtime.mkdir(parents=True, exist_ok=True)
        return {"runtime": runtime}


def _write_journal(
    data_root, *, etype="exit", exit_code=0, reason="normal", event_id="evt1"
):
    directory = (
        data_root / "runtime-events" / "p" / "events" / "runtime" / "inst1"
    )
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{event_id}.json").write_text(
        json.dumps(
            {
                "event_id": event_id,
                "profile_id": "p",
                "runtime_instance_id": "inst1",
                "event_type": etype,
                "exit_code": exit_code,
                "exit_reason": reason,
                "config_version": 1,
            }
        ),
        encoding="utf-8",
    )


def _make(tmp_path, *, container_status, deliver_first=True, runtime_desired="stopped"):
    data_root = tmp_path / "data"
    docker = _FakeDocker(data_root, container_status)
    observed = []
    state = {"events": 0}

    def handler(request):
        path = request.url.path
        if path.endswith("/runtimes/events"):
            state["events"] += 1
            if state["events"] == 1 and not deliver_first:
                return httpx.Response(503, json={"detail": "unavailable"})
            return httpx.Response(
                200, json={"status": "ok", "outcome": "applied"}
            )
        if path.endswith("/runtimes/observed"):
            observed.append(json.loads(request.content))
            return httpx.Response(200, json={})
        if path == "/api/v1/internal/supervisor/profiles":
            return httpx.Response(
                200,
                json=[{"id": "p", "name": "p", "current_config_version": 1}],
            )
        if path.endswith("/runtime"):
            return httpx.Response(
                200,
                json={
                    "profile_id": "p",
                    "desired_state": runtime_desired,
                    "observed_state": runtime_desired,
                    "runtime_instance_id": "inst1",
                    "config_version": 1,
                    "failure_count": 0,
                    "restart_blocked": False,
                    "last_exit_event_id": None,
                },
            )
        return httpx.Response(200, json={})

    api = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://api",
        trust_env=False,
    )
    events = EventForwarder("http://api", tmp_path / "spool", client=api)
    core = SupervisorCore(docker, PortAllocator(), events, api)
    return core, api, docker, observed, state


def _terminal(observed):
    return [
        item
        for item in observed
        if item["observed_state"] in ("stopped", "error")
    ]


@pytest.mark.asyncio
async def test_normal_journal_with_exited_container_reports_stopped(tmp_path):
    core, api, _docker, observed, _state = _make(
        tmp_path, container_status="exited"
    )
    _write_journal(tmp_path / "data")

    assert await core.consume_disk_events() == 1
    terminal = _terminal(observed)
    assert terminal and terminal[-1]["observed_state"] == "stopped"
    assert terminal[-1]["reason"] == "normal_exit"
    await api.aclose()


@pytest.mark.asyncio
async def test_api_unavailable_then_replay_still_classifies_normal_exit(tmp_path):
    core, api, _docker, observed, _state = _make(
        tmp_path, container_status="exited", deliver_first=False
    )
    _write_journal(tmp_path / "data")

    assert await core.consume_disk_events() == 0
    assert not _terminal(observed)
    assert core.has_native_exit("p", "inst1", 1) is True

    await core.consume_disk_events()
    terminal = _terminal(observed)
    assert terminal and terminal[-1]["observed_state"] == "stopped"
    assert terminal[-1]["reason"] == "normal_exit"
    await api.aclose()


@pytest.mark.asyncio
async def test_terminal_ack_dedup_blocks_synthetic_error_override(tmp_path):
    core, api, _docker, observed, _state = _make(
        tmp_path, container_status="exited"
    )
    _write_journal(tmp_path / "data")

    await core.consume_disk_events()
    assert len(_terminal(observed)) == 1
    assert _terminal(observed)[0]["observed_state"] == "stopped"

    synthetic = await core.report_terminal_observation(
        "p", "inst1", 1, observed_state="error", reason="container_exit"
    )
    assert synthetic is False
    again = await core._reconcile_instance_observation(
        "p", "inst1", 1, container_status="exited"
    )
    assert again is None
    assert len(_terminal(observed)) == 1
    await api.aclose()


@pytest.mark.asyncio
async def test_wrong_instance_or_version_is_not_treated_as_normal_exit(tmp_path):
    core, api, _docker, observed, _state = _make(
        tmp_path, container_status="exited"
    )
    _write_journal(tmp_path / "data")
    await core.consume_disk_events()

    wrong_instance = await core._reconcile_instance_observation(
        "p", "inst_other", 1, container_status="exited"
    )
    wrong_version = await core._reconcile_instance_observation(
        "p", "inst1", 2, container_status="exited"
    )
    assert wrong_instance == "error"
    assert wrong_version == "error"
    states = {item["observed_state"] for item in _terminal(observed)}
    assert "stopped" in states
    await api.aclose()


@pytest.mark.asyncio
async def test_owner_loss_and_zero_exit_code_are_not_normal_exits(tmp_path):
    owner, api_a, _d, observed_a, _s = _make(
        tmp_path / "owner", container_status="exited"
    )
    _write_journal(
        tmp_path / "owner" / "data",
        etype="lifecycle",
        exit_code=None,
        reason="process_observation_lost",
    )
    await owner.consume_disk_events()
    assert _terminal(observed_a)[-1]["observed_state"] == "error"
    await api_a.aclose()

    forged, api_b, _d2, observed_b, _s2 = _make(
        tmp_path / "forged", container_status="exited"
    )
    _write_journal(
        tmp_path / "forged" / "data",
        exit_code=0,
        reason="process_observation_lost",
    )
    await forged.consume_disk_events()
    assert _terminal(observed_b)[-1]["observed_state"] == "error"
    await api_b.aclose()


@pytest.mark.asyncio
async def test_normal_shutdown_disables_automatic_recovery(tmp_path):
    core, api, _docker, observed, _state = _make(
        tmp_path, container_status="exited", runtime_desired="stopped"
    )
    core._sessions["p"] = ActiveSession(
        "p", "inst1", 1, 30000, "b", "s",
        desired_state="running", observed_state="running",
    )
    _write_journal(tmp_path / "data")

    await core.consume_disk_events()
    assert core.get_session("p").desired_state == "stopped"

    core.start_profile = AsyncMock()
    coordinator = RecoveryCoordinator(core)
    await coordinator.tick(containers=[])
    core.start_profile.assert_not_awaited()
    await api.aclose()
