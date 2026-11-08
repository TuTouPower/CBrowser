"""A3: port ownership follows resource lifetime, not session lifetime."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from cbrowser.domain.models import ProfileConfig
from cbrowser.supervisor.core import ActiveSession, SupervisorCore
from cbrowser.supervisor.docker_adapter import DockerSandboxError
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import (
    PortAllocationBlockedError,
    PortAllocator,
)
from docker.errors import DockerException


class _FakeDocker:
    def __init__(self, root):
        self.validator = PathValidator(root)
        self.containers = []
        self.teardown_error = None
        self.teardown_calls = 0
        self.create_network_error = None
        self.inspect_error_ids = set()
        self.bindings = {}
        self.clear_on_teardown = True
        self.manage_ownership = False
        self.client = SimpleNamespace(
            api=SimpleNamespace(inspect_container=self._inspect)
        )

    def scan_active_containers(self):
        return list(self.containers)

    def _inspect(self, cid):
        if cid in self.inspect_error_ids:
            raise DockerException("inspect failed")
        port = self.bindings.get(cid)
        if port is None:
            return {"HostConfig": {"PortBindings": {}}}
        return {
            "HostConfig": {
                "PortBindings": {f"{port}/udp": [{"HostPort": str(port)}]}
            }
        }

    async def teardown_profile(self, pid):
        self.teardown_calls += 1
        if self.teardown_error is not None:
            raise self.teardown_error
        if self.clear_on_teardown:
            self.containers = [
                item for item in self.containers if item["profile_id"] != pid
            ]

    async def create_profile_network(self, pid):
        if self.create_network_error is not None:
            raise self.create_network_error

    def prepare_profile_directories(self, pid):
        runtime = self.validator.get_runtime_dir(pid)
        runtime.mkdir(parents=True, exist_ok=True)
        return {"runtime": runtime}


def _pair(profile_id, instance_id, *, policy_ready=True, status="running"):
    return [
        {
            "id": f"{role}-{profile_id}",
            "name": f"{role}-{profile_id}",
            "status": status,
            "profile_id": profile_id,
            "instance_id": instance_id,
            "role": role,
            "config_version": "1",
            "policy_ready": policy_ready,
        }
        for role in ("browser", "stream")
    ]


def _runtime_json(profile_id, *, desired="running", instance="inst1", version=1):
    return {
        "profile_id": profile_id,
        "desired_state": desired,
        "observed_state": "running",
        "runtime_instance_id": instance,
        "config_version": version,
        "failure_count": 0,
        "restart_blocked": False,
    }


def _make_core(tmp_path, docker, *, status=200, json_body=None):
    def handler(request):
        return httpx.Response(status, json=json_body or _runtime_json("profile"))

    api = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://api",
        trust_env=False,
    )
    events = EventForwarder("http://api", tmp_path / "spool", client=api)
    core = SupervisorCore(docker, PortAllocator(), events, api)
    return core, api


@pytest.mark.asyncio
async def test_stop_teardown_failure_retains_port_until_retry_confirms_removal(
    tmp_path,
):
    docker = _FakeDocker(tmp_path / "data")
    core, api = _make_core(tmp_path, docker)
    await core.ports.allocate("profile")
    core._sessions["profile"] = ActiveSession(
        "profile", "inst1", 1, 30000, "b", "s"
    )
    docker.teardown_error = DockerException("daemon down")

    with pytest.raises(DockerSandboxError):
        await core.stop_profile("profile", operation_id="op-stop")
    assert core.ports.get_port("profile") == 30000
    assert core.get_session("profile") is not None

    docker.teardown_error = None
    result = await core.stop_profile("profile", operation_id="op-stop")
    assert result["status"] == "stopped"
    assert core.ports.get_port("profile") is None
    assert core.get_session("profile") is None
    await api.aclose()


@pytest.mark.asyncio
async def test_unprotected_cleanup_failure_retains_port_until_retry(
    tmp_path, monkeypatch
):
    import cbrowser.supervisor.core as core_module

    monkeypatch.setattr(core_module, "UNPROTECTED_SANDBOX_GRACE_SEC", 0.0)
    docker = _FakeDocker(tmp_path / "data")
    docker.containers = _pair("profile", "inst1", policy_ready=False)
    core, api = _make_core(tmp_path, docker)
    await core.ports.allocate("profile")
    docker.teardown_error = DockerException("daemon down")

    await core.scan_and_reconcile_existing()
    assert core.ports.get_port("profile") == 30000

    docker.teardown_error = None
    await core.scan_and_reconcile_existing()
    assert core.ports.get_port("profile") is None
    await api.aclose()


@pytest.mark.asyncio
async def test_startup_failure_cleanup_retains_port_when_removal_unverified(
    tmp_path,
):
    docker = _FakeDocker(tmp_path / "data")
    core, api = _make_core(tmp_path, docker)
    core.agent_credentials = SimpleNamespace()
    docker.containers = _pair("profile", "inst1")
    docker.create_network_error = RuntimeError("network create failed")
    docker.teardown_error = DockerException("daemon down")

    with pytest.raises(RuntimeError):
        await core.start_profile("profile", ProfileConfig(name="x"))
    assert core.ports.get_port("profile") == 30000
    await api.aclose()


@pytest.mark.asyncio
async def test_startup_failure_cleanup_releases_port_only_after_confirmed_removal(
    tmp_path,
):
    docker = _FakeDocker(tmp_path / "data")
    core, api = _make_core(tmp_path, docker)
    core.agent_credentials = SimpleNamespace()
    docker.containers = _pair("profile", "inst1")
    docker.create_network_error = RuntimeError("network create failed")

    with pytest.raises(RuntimeError):
        await core.start_profile("profile", ProfileConfig(name="x"))
    assert core.ports.get_port("profile") is None
    await api.aclose()


@pytest.mark.asyncio
async def test_startup_scan_reserves_portbindings_without_session_and_blocks_reuse(
    tmp_path,
):
    docker = _FakeDocker(tmp_path / "data")
    docker.containers = _pair("A", "instA", policy_ready=True)
    docker.bindings["stream-A"] = 30000
    core, api = _make_core(tmp_path, docker, status=503)

    await core.scan_and_reconcile_existing()
    assert core.get_session("A") is None
    assert core.ports.get_port("A") == 30000
    assert await core.ports.allocate("B") != 30000
    await api.aclose()


@pytest.mark.asyncio
async def test_restart_scan_isolates_inspect_errors_and_preserves_unknown_identity(
    tmp_path,
):
    docker = _FakeDocker(tmp_path / "data")
    docker.containers = _pair("good", "instG", policy_ready=True) + _pair(
        "broken", "instB", policy_ready=True
    )
    docker.containers.append(
        {
            "id": "ghost",
            "name": "ghost",
            "status": "running",
            "profile_id": "good",
            "instance_id": "instG",
            "role": "unknown",
            "config_version": "1",
            "policy_ready": True,
        }
    )
    docker.bindings["stream-good"] = 30001
    docker.inspect_error_ids.add("stream-broken")
    core, api = _make_core(tmp_path, docker, status=503)

    await core.scan_and_reconcile_existing()
    assert core.ports.get_port("good") == 30001
    assert docker.teardown_calls == 0
    assert any(item["id"] == "ghost" for item in docker.containers)
    assert any(item["id"] == "stream-broken" for item in docker.containers)
    await api.aclose()


@pytest.mark.asyncio
async def test_restart_scan_unverifiable_stream_port_blocks_reuse(tmp_path):
    docker = _FakeDocker(tmp_path / "data")
    docker.containers = _pair("good", "instG", policy_ready=True) + _pair(
        "broken", "instB", policy_ready=True
    )
    docker.bindings["stream-good"] = 30001
    docker.bindings["stream-broken"] = 30000
    docker.inspect_error_ids.add("stream-broken")
    core, api = _make_core(tmp_path, docker, status=503)

    await core.scan_and_reconcile_existing()
    assert core.ports.get_port("good") == 30001
    with pytest.raises(PortAllocationBlockedError):
        await core.ports.allocate("C")
    await api.aclose()
