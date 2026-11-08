"""A9: the creator reclaims a Stream container when initialization fails."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import docker.errors
import httpx
import pytest
from cbrowser.supervisor.core import ActiveSession, SupervisorCore
from cbrowser.supervisor.docker_adapter import DockerAdapter, DockerSandboxError
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator
from cbrowser.supervisor.selkies_tokens import SelkiesTokens

BROWSER = "sha256:f2a8d42810c13c8480b83e4308669c754e86b0fe4a24c6215159e43a8d1f5346"
STREAM = "sha256:072e86762d2f1810e86a2d20169d4be451b5a19e0ebabc880e882de63ac0d531"


def _adapter(tmp_path):
    root = tmp_path / "data"
    engine = root / "engine_cache"
    engine.mkdir(parents=True)
    (engine / "geoip").mkdir(parents=True)
    mock_client = MagicMock()
    adapter = DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=engine,
        docker_client=mock_client,
        browser_image=BROWSER,
        stream_image=STREAM,
        policy_image=BROWSER,
    )
    return adapter, mock_client


def _stage(adapter, mock_client, tmp_path):
    dirs = adapter.prepare_profile_directories("p1")
    (dirs["x11"] / "X99").touch()
    (dirs["runtime"] / "Xauthority").touch()
    secret_dir = adapter.validator.get_secret_dir("p1")
    secret_dir.mkdir(parents=True, exist_ok=True)
    agent_secret = secret_dir / "agent_secret.txt"
    agent_secret.write_text("agent_secret_test", encoding="utf-8")
    agent_secret.chmod(0o600)
    tokens_path = secret_dir / "selkies_tokens.json"
    SelkiesTokens.generate().write_credentials_file(tokens_path)
    mock_client.api.inspect_container.return_value = {
        "Config": {
            "Hostname": "b-host",
            "Labels": {"com.cbrowser.config-version": "1"},
        }
    }
    adapter.cleanup_container_by_name = MagicMock()
    adapter._prepare_policy_gate = MagicMock(
        return_value=tmp_path / "stream_gate"
    )
    adapter._resolved_endpoint = MagicMock(
        return_value=[("127.0.0.1", 18097)]
    )
    adapter._install_network_policy = MagicMock()
    return agent_secret, tokens_path


def _stream_container(adapter, *, remove_error=None):
    container = MagicMock()
    container.id = "stream-container-id"
    container.name = adapter.get_stream_container_name("p1")
    container.labels = {
        "com.cbrowser.prefix": adapter.resource_prefix,
        "com.cbrowser.managed-by": "supervisor",
        "com.cbrowser.role": "stream",
        "com.cbrowser.profile-id": "p1",
        "com.cbrowser.instance-id": "inst_1",
    }
    if remove_error is not None:
        container.remove.side_effect = remove_error
    return container


async def _call(adapter, agent_secret, tokens_path):
    return await adapter.start_stream_container(
        profile_id="p1",
        runtime_instance_id="inst_1",
        browser_container_name="cbrowser-p1-browser",
        udp_mux_port=30006,
        agent_secret_path=agent_secret,
        selkies_tokens_path=tokens_path,
    )


@pytest.mark.asyncio
async def test_policy_install_failure_reclaims_this_stream_container(tmp_path):
    adapter, mock_client = _adapter(tmp_path)
    agent_secret, tokens_path = _stage(adapter, mock_client, tmp_path)
    container = _stream_container(adapter)
    mock_client.containers.run.return_value = container
    adapter._install_network_policy = MagicMock(
        side_effect=DockerSandboxError("policy failed")
    )

    with pytest.raises(DockerSandboxError):
        await _call(adapter, agent_secret, tokens_path)
    container.remove.assert_called_once_with(force=True)


@pytest.mark.asyncio
async def test_address_resolution_failure_reclaims_this_stream_container(
    tmp_path,
):
    adapter, mock_client = _adapter(tmp_path)
    agent_secret, tokens_path = _stage(adapter, mock_client, tmp_path)
    container = _stream_container(adapter)
    mock_client.containers.run.return_value = container
    adapter._resolved_endpoint = MagicMock(
        side_effect=DockerSandboxError("dns failed")
    )

    with pytest.raises(DockerSandboxError):
        await _call(adapter, agent_secret, tokens_path)
    container.remove.assert_called_once_with(force=True)


@pytest.mark.asyncio
async def test_gate_readiness_failure_reclaims_this_stream_container(tmp_path):
    adapter, mock_client = _adapter(tmp_path)
    agent_secret, tokens_path = _stage(adapter, mock_client, tmp_path)
    container = _stream_container(adapter)
    mock_client.containers.run.return_value = container
    adapter._install_network_policy = MagicMock(
        side_effect=OSError("gate write failed")
    )

    with pytest.raises(DockerSandboxError):
        await _call(adapter, agent_secret, tokens_path)
    container.remove.assert_called_once_with(force=True)


@pytest.mark.asyncio
async def test_unknown_identity_container_is_not_deleted(tmp_path):
    adapter, mock_client = _adapter(tmp_path)
    agent_secret, tokens_path = _stage(adapter, mock_client, tmp_path)
    container = _stream_container(adapter)
    container.labels["com.cbrowser.instance-id"] = "different_instance"
    mock_client.containers.run.return_value = container
    adapter._install_network_policy = MagicMock(
        side_effect=DockerSandboxError("policy failed")
    )

    with pytest.raises(DockerSandboxError):
        await _call(adapter, agent_secret, tokens_path)
    container.remove.assert_not_called()


@pytest.mark.asyncio
async def test_reclaim_failure_returns_typed_pending_residue(tmp_path):
    from cbrowser.supervisor.docker_adapter import (
        StreamContainerResidueError,
        StreamResidue,
    )

    adapter, mock_client = _adapter(tmp_path)
    agent_secret, tokens_path = _stage(adapter, mock_client, tmp_path)
    container = _stream_container(
        adapter, remove_error=docker.errors.DockerException("daemon gone")
    )
    mock_client.containers.run.return_value = container
    adapter._install_network_policy = MagicMock(
        side_effect=DockerSandboxError("policy failed")
    )

    with pytest.raises(StreamContainerResidueError) as caught:
        await _call(adapter, agent_secret, tokens_path)
    residue = caught.value.residue
    assert isinstance(residue, StreamResidue)
    assert residue.profile_id == "p1"
    assert residue.runtime_instance_id == "inst_1"
    assert residue.container_id == "stream-container-id"
    assert residue.container_name == adapter.get_stream_container_name("p1")


class _FakeAdapter:
    def __init__(self, root):
        self.validator = PathValidator(root)
        self.start_error = None
        self.residue_cleanup_result = True
        self.cleanup_residue_calls = []
        self.cleanup_container_calls = []
        self.browser = SimpleNamespace(name="cbrowser-browser-p", id="b-id")
        runtime = self.validator.get_runtime_dir("p")
        secret = self.validator.get_secret_dir("p")
        runtime.mkdir(parents=True, exist_ok=True)
        secret.mkdir(parents=True, exist_ok=True)
        (secret / "agent_secret.txt").touch()
        self.client = SimpleNamespace()

    def get_stream_container_name(self, profile_id):
        return f"cbrowser-stream-{profile_id}"

    def cleanup_container_by_name(self, name):
        self.cleanup_container_calls.append(name)

    def get_profile_containers(self, profile_id):
        return {"browser": self.browser, "stream": None}

    def attach_profile_infrastructure(self, profile_id, gateway_id, gateway_port=None):
        return {"gateway_ip": "10.0.0.1", "gateway_url": "ws://10.0.0.1:8443"}

    def inspect_media_network(self, profile_id):
        return {"exists": True, "conforms": True}

    def rebuild_media_network(self, profile_id):
        return None

    async def start_stream_container(self, **kwargs):
        if self.start_error is not None:
            raise self.start_error
        return SimpleNamespace(id="new-stream-id")

    def cleanup_stream_residue(self, residue):
        self.cleanup_residue_calls.append(residue)
        return self.residue_cleanup_result


def _make_core(tmp_path, adapter):
    api = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
        base_url="http://api",
        trust_env=False,
    )
    events = EventForwarder("http://api", tmp_path / "spool", client=api)
    core = SupervisorCore(
        adapter,
        PortAllocator(),
        events,
        api,
        gateway_container_id="gw1",
    )
    return core, api


@pytest.mark.asyncio
async def test_replacement_failure_records_residue_and_keeps_port(tmp_path):
    from cbrowser.supervisor.docker_adapter import (
        StreamContainerResidueError,
        StreamResidue,
    )

    adapter = _FakeAdapter(tmp_path / "data")
    residue = StreamResidue("p", "inst1", "cid-stream", "cbrowser-stream-p")
    adapter.start_error = StreamContainerResidueError(
        residue, "DockerSandboxError"
    )
    core, api = _make_core(tmp_path, adapter)
    await core.ports.allocate("p")
    session = ActiveSession("p", "inst1", 1, 30000, "b", "s")
    core._sessions["p"] = session

    result = await core._replace_stream_only(
        "p", session, rebuild_network=False
    )
    assert result is False
    assert core._pending_stream_residue["p"] is residue
    assert core.ports.get_port("p") == 30000
    assert adapter.cleanup_container_calls == ["cbrowser-stream-p"]
    await api.aclose()


@pytest.mark.asyncio
async def test_next_replacement_cleans_residue_before_starting(tmp_path):
    from cbrowser.supervisor.docker_adapter import (
        StreamContainerResidueError,
        StreamResidue,
    )

    adapter = _FakeAdapter(tmp_path / "data")
    residue = StreamResidue("p", "inst1", "cid-stream", "cbrowser-stream-p")
    adapter.start_error = StreamContainerResidueError(
        residue, "DockerSandboxError"
    )
    core, api = _make_core(tmp_path, adapter)
    await core.ports.allocate("p")
    session = ActiveSession("p", "inst1", 1, 30000, "b", "s")
    core._sessions["p"] = session

    await core._replace_stream_only("p", session, rebuild_network=False)
    adapter.start_error = None
    adapter.start_stream_container = AsyncMock(
        return_value=SimpleNamespace(id="new-stream-id")
    )

    result = await core._replace_stream_only(
        "p", session, rebuild_network=False
    )
    assert result is True
    assert adapter.cleanup_residue_calls == [residue]
    assert core._pending_stream_residue.get("p") is None
    assert core.ports.get_port("p") == 30000
    await api.aclose()


@pytest.mark.asyncio
async def test_new_generation_residue_is_discarded_not_deleted(tmp_path):
    from cbrowser.supervisor.docker_adapter import (
        StreamContainerResidueError,
        StreamResidue,
    )

    adapter = _FakeAdapter(tmp_path / "data")
    residue = StreamResidue("p", "inst1", "cid-stream", "cbrowser-stream-p")
    adapter.start_error = StreamContainerResidueError(
        residue, "DockerSandboxError"
    )
    core, api = _make_core(tmp_path, adapter)
    await core.ports.allocate("p")
    old = ActiveSession("p", "inst1", 1, 30000, "b", "s")
    core._sessions["p"] = old
    await core._replace_stream_only("p", old, rebuild_network=False)

    newer = ActiveSession("p", "inst2", 1, 30000, "b", "s")
    core._sessions["p"] = newer
    adapter.start_error = None
    adapter.start_stream_container = AsyncMock(
        return_value=SimpleNamespace(id="new-stream-id")
    )

    await core._replace_stream_only("p", newer, rebuild_network=False)
    assert adapter.cleanup_residue_calls == []
    assert core._pending_stream_residue.get("p") is None
    await api.aclose()
