"""t082 adapter lifecycle: one hardened Policy Agent per target netns.

A faithful in-memory Docker double plus the in-process Policy Agent
rig drive the real ``DockerAdapter``: starting a Browser creates
exactly one Agent (policy image, NET_ADMIN only, read-only root,
target netns, only its own socket directory), repeated verification
creates nothing and execs nothing, resolution is frozen until the
upstream changes, refresh failure keeps the old frozen spec, a second
adapter adopts the running Agent, and orphan Agents are collected
only when their target is gone.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from cbrowser.supervisor.docker_adapter import DockerAdapter, DockerSandboxError
from cbrowser.supervisor.path_validator import PathValidator
from docker.errors import NotFound
from tests.unit.policy_agent_test_support import (
    FakePolicyAgentExecutor,
    PolicyAgentTestRig,
)


def _make_rig() -> PolicyAgentTestRig:
    executor = FakePolicyAgentExecutor()
    executor.resolutions = dict(RESOLUTIONS)
    rig = PolicyAgentTestRig(executor)
    calls: list[tuple[str, int]] = []
    original = executor.resolve

    def counting(hostname: str, port: int) -> list[str]:
        calls.append((hostname, port))
        return original(hostname, port)

    executor.resolve = counting  # type: ignore[method-assign]
    rig.resolve_calls = calls  # type: ignore[attr-defined]
    return rig

pytestmark = pytest.mark.serial

BROWSER = "sha256:" + "a" * 64
STREAM = "sha256:" + "b" * 64
POLICY = "sha256:" + "c" * 64
RESOLUTIONS = {
    "proxy.example.com": ["203.0.113.7"],
    "other.example.com": ["203.0.113.9"],
    "host.docker.internal": ["192.168.65.2"],
}


class _FakeContainer:
    def __init__(self, client: "_FakeClient", name: str, kwargs: dict) -> None:
        self._client = client
        self.name = name
        self.id = f"id-{name}"
        self.status = "running"
        self.labels = dict(kwargs.get("labels") or {})
        env = kwargs.get("environment") or {}
        if isinstance(env, dict):
            env = [f"{k}={v}" for k, v in env.items()]
        self.attrs = {
            "Config": {"Env": list(env), "Entrypoint": kwargs.get("entrypoint")},
            "NetworkSettings": {"Networks": {}},
        }
        self.removed = False

    def reload(self) -> None:
        pass

    def start(self) -> None:
        self.status = "running"

    def stop(self, timeout: int = 10) -> None:
        self.status = "exited"

    def pause(self) -> None:
        self.status = "paused"

    def unpause(self) -> None:
        self.status = "running"

    def remove(self, force: bool = False, v: bool = False) -> None:
        self.removed = True
        self._client.containers_by_name.pop(self.name, None)

    def exec_run(self, *args, **kwargs):  # pragma: no cover - tripwire
        raise AssertionError("steady-state verification must not exec")


class _FakeContainers:
    def __init__(self, client: "_FakeClient") -> None:
        self._client = client

    def run(self, image, **kwargs):
        return self._client.create(image, kwargs)

    def create(self, image, **kwargs):
        return self._client.create(image, kwargs)

    def get(self, key):
        for container in self._client.containers_by_name.values():
            if container.name == key or container.id == key:
                return container
        raise NotFound(f"no such container: {key}")

    def list(self, all: bool = False, filters=None):
        items = list(self._client.containers_by_name.values())
        wanted = (filters or {}).get("label") or []
        for label in wanted:
            key, _, value = label.partition("=")
            items = [c for c in items if c.labels.get(key) == value]
        return items


class _FakeNetworks:
    def create(self, name, **kwargs):
        return MagicMock(name=name)


class _FakeClient:
    def __init__(self) -> None:
        self.containers_by_name: dict[str, _FakeContainer] = {}
        self.containers = _FakeContainers(self)
        self.networks = _FakeNetworks()
        self.created: list[tuple[str, dict]] = []
        self.api = MagicMock()
        self.api.inspect_network.return_value = {"Containers": {}}

    def create(self, image, kwargs):
        name = kwargs.get("name") or f"anon-{len(self.created)}"
        container = _FakeContainer(self, name, kwargs)
        self.containers_by_name[name] = container
        self.created.append((image, kwargs))
        return container


def _adapter(tmp_path: Path, client: _FakeClient) -> DockerAdapter:
    root = (tmp_path / "data").resolve()
    (root / "engine_cache" / "geoip").mkdir(parents=True, exist_ok=True)
    adapter = DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=root / "engine_cache",
        docker_client=client,
        browser_image=BROWSER,
        stream_image=STREAM,
        policy_image=POLICY,
        deployment_instance_id="dep-test",
    )
    adapter.create_browser_network = AsyncMock()
    adapter.ensure_runtime_cache = AsyncMock()
    adapter.setup_x11_permissions = MagicMock()
    adapter.cleanup_container_by_name = MagicMock()
    adapter._validate_cache_paths = MagicMock()
    return adapter


def _write_proxy_profile(adapter: DockerAdapter, host: str = "proxy.example.com"):
    adapter.remember_profile_number("p1", 1)
    dirs = adapter.prepare_profile_directories("p1")
    (dirs["runtime"] / "snapshot.json").write_text(
        json.dumps({"version": 3, "config": {"proxy_id": "px1", "geoip": False}}),
        encoding="utf-8",
    )
    secret_dir = adapter.validator.get_secret_dir("p1")
    secret_dir.mkdir(parents=True, exist_ok=True)
    creds = secret_dir / "proxy_credentials.json"
    creds.write_text(
        json.dumps(
            {
                "scheme": "socks5",
                "host": host,
                "port": 8080,
                "username": "user",
                "password": "s3cr3t",
                "credential_revision": 1,
            }
        ),
        encoding="utf-8",
    )
    creds.chmod(0o600)
    return dirs


async def _start_browser(tmp_path: Path):
    client = _FakeClient()
    adapter = _adapter(tmp_path, client)
    rig = _make_rig()
    rig.install_on(adapter)
    dirs = _write_proxy_profile(adapter)
    container = await adapter.start_browser_container(
        profile_id="p1",
        runtime_instance_id="inst_1",
        snapshot_json_path=dirs["runtime"] / "snapshot.json",
    )
    return adapter, client, rig, container


@pytest.mark.asyncio
async def test_start_browser_creates_one_hardened_policy_agent(tmp_path):
    adapter, client, rig, container = await _start_browser(tmp_path)

    agent_creates = [
        (image, kwargs)
        for image, kwargs in client.created
        if (kwargs.get("labels") or {}).get("com.cbrowser.role")
        == "network-policy-agent"
    ]
    assert len(agent_creates) == 1
    image, kwargs = agent_creates[0]
    assert image == POLICY
    assert kwargs["cap_add"] == ["NET_ADMIN"]
    assert kwargs["read_only"] is True
    assert kwargs["network_mode"] == f"container:{container.id}"
    mounts = kwargs["mounts"]
    assert len(mounts) == 1
    assert mounts[0]["Target"] == "/run/cbrowser_policy_agent"
    env = kwargs["environment"]
    assert env["CBROWSER_POLICY_AGENT_PROFILE_ID"] == "p1"
    assert env["CBROWSER_POLICY_AGENT_ROLE"] == "browser"
    assert env["CBROWSER_POLICY_AGENT_TARGET_CONTAINER_ID"] == container.id
    # The policy was installed through the Agent, revision 1.
    assert len(rig.executor.installed) == 1
    spec, replace = rig.executor.installed[0]
    assert replace is False
    assert spec.allowed_tcp == [("203.0.113.7", 8080)]
    assert adapter._policy_agents[container.id].revision == 1


@pytest.mark.asyncio
async def test_repeated_verification_creates_and_execs_nothing(tmp_path):
    adapter, client, rig, container = await _start_browser(tmp_path)
    created_before = len(client.created)
    resolutions_before = len(rig.resolve_calls)

    for _ in range(5):
        spec = adapter.browser_policy_spec("p1", container)
        assert adapter.verify_container_policy(container, spec) is True

    assert len(client.created) == created_before
    # Frozen derivation: the upstream was resolved exactly once, at
    # install time; verification never resolves again.
    assert len(rig.resolve_calls) == resolutions_before == 1


@pytest.mark.asyncio
async def test_upstream_change_refreshes_with_replace(tmp_path):
    adapter, client, rig, container = await _start_browser(tmp_path)
    _write_proxy_profile(adapter, host="other.example.com")

    spec = adapter.browser_policy_spec("p1", container)

    assert spec["allowed_tcp"] == [("203.0.113.9", 8080)]
    spec_obj, replace = rig.executor.installed[-1]
    assert replace is True
    handle = adapter._policy_agents[container.id]
    assert handle.revision == 2


@pytest.mark.asyncio
async def test_refresh_failure_keeps_old_frozen_spec(tmp_path):
    adapter, client, rig, container = await _start_browser(tmp_path)
    _write_proxy_profile(adapter, host="other.example.com")
    rig.executor.fail_install = True

    with pytest.raises(DockerSandboxError):
        adapter.browser_policy_spec("p1", container)

    handle = adapter._policy_agents[container.id]
    assert handle.revision == 1
    assert handle.spec is not None
    assert handle.spec.allowed_tcp == [("203.0.113.7", 8080)]
    rig.executor.fail_install = False
    # The old frozen spec still verifies.
    assert adapter.verify_container_policy(container, handle.spec.model_dump())


@pytest.mark.asyncio
async def test_second_adapter_adopts_running_agent(tmp_path):
    adapter, client, rig, container = await _start_browser(tmp_path)
    created_before = len(client.created)

    # A restarted Supervisor has empty memory but reaches the SAME
    # Agent process through its socket: share the rig, not the adapter.
    adapter2 = _adapter(tmp_path, client)
    rig.install_on(adapter2)
    spec = adapter.browser_policy_spec("p1", container)
    assert adapter2.verify_container_policy(container, spec) is True
    assert len(client.created) == created_before  # adopted, not created
    assert container.id in adapter2._policy_agents


@pytest.mark.asyncio
async def test_orphan_agent_removed_only_when_target_gone(tmp_path):
    adapter, client, rig, container = await _start_browser(tmp_path)
    agent = next(
        c
        for c in client.containers_by_name.values()
        if c.labels.get("com.cbrowser.role") == "network-policy-agent"
    )

    adapter._cleanup_orphan_policy_agents()
    assert agent.removed is False  # live target: left for the core

    client.containers_by_name.pop(container.name)
    adapter._cleanup_orphan_policy_agents()
    assert agent.removed is True


@pytest.mark.asyncio
async def test_teardown_removes_profile_agents(tmp_path):
    adapter, client, rig, container = await _start_browser(tmp_path)
    agent = next(
        c
        for c in client.containers_by_name.values()
        if c.labels.get("com.cbrowser.role") == "network-policy-agent"
    )
    adapter._remove_policy_agents_for_profile("p1")
    assert agent.removed is True
    assert adapter._policy_agents == {}


@pytest.mark.asyncio
async def test_fail_close_unconfirmed_raises(tmp_path):
    adapter, client, rig, container = await _start_browser(tmp_path)
    rig.executor.fail_close_confirmed = False
    with pytest.raises(DockerSandboxError):
        adapter.fail_close_container(container)


@pytest.mark.asyncio
async def test_pause_unpause_delegate_to_target(tmp_path):
    adapter, client, rig, container = await _start_browser(tmp_path)
    paused: list[str] = []
    container.pause = lambda: paused.append("pause")  # type: ignore[attr-defined]
    container.unpause = lambda: paused.append("unpause")  # type: ignore[attr-defined]
    adapter.pause_container(container)
    adapter.unpause_container(container)
    assert paused == ["pause", "unpause"]


@pytest.mark.asyncio
async def test_policy_image_required_for_agent_creation(tmp_path):
    client = _FakeClient()
    adapter = _adapter(tmp_path, client)
    adapter.policy_image = None
    rig = _make_rig()
    rig.install_on(adapter)
    dirs = _write_proxy_profile(adapter)
    with pytest.raises(DockerSandboxError):
        await adapter.start_browser_container(
            profile_id="p1",
            runtime_instance_id="inst_1",
            snapshot_json_path=dirs["runtime"] / "snapshot.json",
        )


@pytest.mark.asyncio
async def test_install_writes_ready_marker_only_after_agent_success(tmp_path):
    # test f001 / AC-001: the startup gate's ready marker is written
    # only after the Agent has applied the policy; a failed install
    # raises and leaves the gate closed.
    adapter, client, rig, container = await _start_browser(tmp_path)
    spec = adapter.browser_policy_spec("p1", container)
    config_version = adapter._policy_agents[container.id].identity.config_version

    gate = tmp_path / "gate-ok"
    gate.mkdir()
    adapter._install_network_policy(
        container, spec, gate, "inst_1", "browser",
        profile_id="p1", config_version=config_version,
    )
    marker = json.loads((gate / "ready.json").read_text(encoding="utf-8"))
    assert marker == {
        "instance_id": "inst_1",
        "role": "browser",
        "status": "ready",
    }

    rig.executor.fail_install = True
    changed = dict(spec)
    changed["allowed_tcp"] = [("203.0.113.7", 9999)]
    gate_fail = tmp_path / "gate-fail"
    gate_fail.mkdir()
    with pytest.raises(DockerSandboxError):
        adapter._install_network_policy(
            container, changed, gate_fail, "inst_1", "browser",
            profile_id="p1", config_version=config_version,
        )
    assert not (gate_fail / "ready.json").exists()
