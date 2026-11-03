"""Stopping never depends on the signaling plane or on teardown success."""

import httpx
import pytest
from cbrowser.supervisor.core import ActiveSession, SupervisorCore
from cbrowser.supervisor.docker_adapter import DockerSandboxError
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator


class _Docker:
    def __init__(self, data_root, *, teardown_fails: bool = False) -> None:
        self.validator = PathValidator(data_root)
        self.teardown_fails = teardown_fails
        self.teardown_calls = 0

    async def teardown_profile(self, profile_id: str) -> None:
        self.teardown_calls += 1
        if self.teardown_fails:
            raise RuntimeError("docker daemon unavailable")

    def scan_active_containers(self):
        return []


def _core(tmp_path, docker, gateway):
    return SupervisorCore(
        docker,
        PortAllocator(),
        EventForwarder(str(tmp_path / "unused"), tmp_path / "spool"),
        httpx.AsyncClient(base_url="http://127.0.0.1:1", trust_env=False),
        gateway_control=gateway,
        gateway_container_id=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("gateway_error", ["status", "transport", "timeout"])
async def test_stop_continues_after_gateway_disconnect_failure(
    tmp_path, gateway_error
):
    class _Gateway:
        async def disconnect_viewers(self, profile_id, instance):
            if gateway_error == "status":
                raise httpx.HTTPStatusError(
                    "503",
                    request=httpx.Request("POST", "http://gateway"),
                    response=httpx.Response(503, request=httpx.Request("POST", "http://gateway")),
                )
            if gateway_error == "transport":
                raise httpx.TransportError("connection refused")
            raise TimeoutError("gateway hung")

    docker = _Docker(tmp_path / "data")
    core = _core(tmp_path, docker, _Gateway())
    await core.ports.allocate("profile")
    core._sessions["profile"] = ActiveSession(
        "profile", "inst", 1, 30000, "browser", "stream"
    )
    result = await core.stop_profile("profile")
    await core.api.aclose()

    assert result == {
        "profile_id": "profile",
        "runtime_instance_id": "inst",
        "status": "stopped",
    }
    assert docker.teardown_calls == 1
    assert core.ports.get_port("profile") is None
    assert core.get_session("profile") is None


@pytest.mark.asyncio
async def test_teardown_failure_still_releases_port_and_reports_error(tmp_path):
    class _Gateway:
        async def disconnect_viewers(self, profile_id, instance):
            return None

    docker = _Docker(tmp_path / "data", teardown_fails=True)
    core = _core(tmp_path, docker, _Gateway())
    await core.ports.allocate("profile")
    core._sessions["profile"] = ActiveSession(
        "profile", "inst", 1, 30001, "browser", "stream"
    )

    with pytest.raises(DockerSandboxError):
        await core.stop_profile("profile")
    await core.api.aclose()

    assert docker.teardown_calls == 1
    assert core.ports.get_port("profile") is None
    assert core.get_session("profile") is None


@pytest.mark.asyncio
async def test_stop_of_superseded_instance_is_noop_and_protects_replacement(
    tmp_path,
):
    """A45: stopping a superseded instance returns superseded_noop, never
    touches the replacement session, and replays the same command result."""
    docker = _Docker(tmp_path / "data")
    core = _core(tmp_path, docker, gateway=None)
    core._sessions["profile"] = ActiveSession(
        "profile", "inst_new", 1, 30000, "browser", "stream"
    )
    result = await core.stop_profile(
        "profile", expected_instance="inst_old", operation_id="op-supersede"
    )
    assert result == {
        "profile_id": "profile",
        "runtime_instance_id": "inst_old",
        "status": "superseded_noop",
    }
    assert docker.teardown_calls == 0
    session = core.get_session("profile")
    assert session is not None and session.runtime_instance_id == "inst_new"

    replay = await core.stop_profile(
        "profile", expected_instance="inst_old", operation_id="op-supersede"
    )
    assert replay == result
    await core.api.aclose()


@pytest.mark.asyncio
async def test_stop_without_any_instance_reports_already_absent(tmp_path):
    """A45: a stop whose target provably does not exist is already_absent,
    not a claim that this command stopped something."""
    docker = _Docker(tmp_path / "data")
    core = _core(tmp_path, docker, gateway=None)
    result = await core.stop_profile(
        "profile", expected_instance="inst_gone", operation_id="op-absent"
    )
    assert result == {
        "profile_id": "profile",
        "runtime_instance_id": "inst_gone",
        "status": "already_absent",
    }
    assert docker.teardown_calls == 0
    replay = await core.stop_profile(
        "profile", expected_instance="inst_gone", operation_id="op-absent"
    )
    assert replay == result
    await core.api.aclose()
