"""t094: Browser-side egress policy and credential contracts.

The Supervisor-side probe container, helper policy and control route are
retired.  The remaining contracts exercised here are the Browser-side
ones: proxy credential mapping/permissions, fail-closed policy derivation
and loopback mapping on Browser startup.  No helper container is involved.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import docker.errors
import httpx
import pytest
from cbrowser.shared.egress_plan import DOCKER_EMBEDDED_DNS
from cbrowser.supervisor.control_server import create_control_app
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.docker_adapter import (
    DockerAdapter,
    LoopbackMappingError,
)
from cbrowser.supervisor.path_validator import PathValidator

_SHA = "sha256:" + "a" * 64


class _FakeContainer:
    def __init__(self, kind: str, calls: list):
        self.id = f"fake-{kind}-id"
        self.kind = kind
        self.calls = calls
        self.removed = False
        self.name = f"fake-{kind}"
        self.labels: dict = {}
        self.status = "running"

    def start(self):
        self.started = True

    def wait(self, timeout=None):
        return {"StatusCode": 0}

    def remove(self, force=False):
        self.removed = True


class _FakeNetwork:
    def __init__(self, name: str):
        self.name = name
        self.removed = False

    def remove(self):
        self.removed = True


class _FakeContainers:
    def __init__(self, calls: list, fail_create: Exception | None = None):
        self.calls = calls
        self.fail_create = fail_create
        self.created: list[_FakeContainer] = []

    def run(self, image, **kwargs):
        self.calls.append({"run": kwargs})
        entrypoint = kwargs.get("entrypoint") or []
        if any("policy_agent" in str(part) for part in entrypoint):
            container = _FakeContainer("policy-agent", self.calls)
        else:
            if self.fail_create is not None:
                raise self.fail_create
            container = _FakeContainer("browser", self.calls)
        container.name = kwargs.get("name") or container.name
        container.labels = dict(kwargs.get("labels") or {})
        self.created.append(container)
        return container

    def create(self, image, **kwargs):
        return self.run(image, **kwargs)

    def get(self, name):
        for container in self.created:
            if container.name == name and not container.removed:
                return container
        raise docker.errors.NotFound(f"no such container: {name}")

    def list(self, all=False, filters=None):
        return [c for c in self.created if all or not c.removed]


class _FakeNetworks:
    def __init__(self, calls: list):
        self.calls = calls
        self.created: list[_FakeNetwork] = []

    def create(self, name, **kwargs):
        self.calls.append({"network_create": name, **kwargs})
        network = _FakeNetwork(name)
        self.created.append(network)
        return network


class _FakeDockerClient:
    def __init__(self, calls: list, fail_create: Exception | None = None):
        self.calls = calls
        self.containers = _FakeContainers(calls, fail_create=fail_create)
        self.networks = _FakeNetworks(calls)


def _adapter(tmp_path: Path, client=None):
    root = tmp_path / "data"
    engine = root / "engine_cache"
    engine.mkdir(parents=True)
    (engine / "geoip").mkdir(parents=True)
    calls: list = []
    fake = client if client is not None else _FakeDockerClient(calls)
    adapter = DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=engine,
        docker_client=fake,
        browser_image=_SHA,
        stream_image=_SHA,
        policy_image=_SHA,
        deployment_instance_id="dep-test",
    )
    from tests.unit.policy_agent_test_support import PolicyAgentTestRig

    rig = PolicyAgentTestRig()
    rig.executor.resolutions.update(
        {
            "proxy.example.com": ["93.184.216.34"],
            "host.docker.internal": ["192.168.65.254"],
        }
    )
    rig.install_on(adapter)
    adapter._test_rig = rig  # type: ignore[attr-defined]
    return adapter, fake, calls, root


def _browser_policy(adapter, creds: dict | None, *, has_proxy: bool = True):
    rig = adapter._test_rig
    rig.stub_ensure(adapter)
    container = SimpleNamespace(id="cid-browser-policy")
    adapter.ensure_policy_agent(
        container,
        profile_id="p1",
        instance_id="inst",
        config_version=1,
        role="browser",
    )
    secret_dir = adapter.validator.get_secret_dir("p1")
    secret_dir.mkdir(parents=True, exist_ok=True)
    creds_file = secret_dir / "proxy_credentials.json"
    if creds is None:
        creds_file.unlink(missing_ok=True)
    else:
        creds_file.write_text(json.dumps(creds), encoding="utf-8")
    spec = adapter._browser_egress_policy(
        container, has_proxy=has_proxy, creds_file=creds_file
    )
    return spec, rig, creds_file


def test_browser_policy_allows_only_mapped_proxy_for_loopback(tmp_path):
    """Browser policy permits only the mapped gateway address + proxy port."""
    adapter, _fake, _calls, _root = _adapter(tmp_path)
    spec, _rig, _creds_file = _browser_policy(
        adapter,
        {
            "scheme": "http",
            "host": "host.docker.internal",
            "port": 7890,
            "credential_revision": 1,
        },
    )
    assert spec["role"] == "browser"
    assert spec["proxy_enforced"] is True
    assert spec["allowed_tcp"] == [("192.168.65.254", 7890)]
    assert spec["allowed_udp"] == [DOCKER_EMBEDDED_DNS]


def test_browser_policy_fails_closed_on_missing_credentials(tmp_path):
    adapter, _fake, _calls, _root = _adapter(tmp_path)
    spec, _rig, _creds_file = _browser_policy(adapter, None)
    assert spec["proxy_enforced"] is True
    assert spec["allowed_tcp"] == []
    assert spec["allowed_udp"] == []


def test_browser_policy_direct_mode_allows_no_egress(tmp_path):
    adapter, _fake, _calls, _root = _adapter(tmp_path)
    spec, _rig, _creds_file = _browser_policy(adapter, None, has_proxy=False)
    assert spec["proxy_enforced"] is False
    assert spec["allowed_tcp"] == []
    assert spec["allowed_udp"] == []


def test_browser_policy_reuses_frozen_spec_for_unchanged_upstream(tmp_path):
    adapter, _fake, _calls, _root = _adapter(tmp_path)
    creds = {
        "scheme": "http",
        "host": "proxy.example.com",
        "port": 8080,
        "credential_revision": 1,
    }
    first, rig, creds_file = _browser_policy(adapter, creds)
    second = adapter._browser_egress_policy(
        SimpleNamespace(id="cid-browser-policy"),
        has_proxy=True,
        creds_file=creds_file,
    )
    assert first == second
    assert len(rig.executor.installed) == 1


def test_browser_policy_refreshes_when_upstream_changes(tmp_path):
    adapter, _fake, _calls, _root = _adapter(tmp_path)
    creds = {
        "scheme": "http",
        "host": "proxy.example.com",
        "port": 8080,
        "credential_revision": 1,
    }
    spec, rig, creds_file = _browser_policy(adapter, creds)
    assert spec["allowed_tcp"] == [("93.184.216.34", 8080)]

    changed = dict(creds, host="host.docker.internal", port=7890)
    creds_file.write_text(json.dumps(changed), encoding="utf-8")
    refreshed = adapter._browser_egress_policy(
        SimpleNamespace(id="cid-browser-policy"),
        has_proxy=True,
        creds_file=creds_file,
    )
    assert refreshed["allowed_tcp"] == [("192.168.65.254", 7890)]
    assert len(rig.executor.installed) == 2


# ---- Browser start: extra_hosts + loopback failure (AC-010/AC-011) ---------


def _stage_browser(adapter, tmp_path, creds: dict):
    adapter._test_rig.stub_ensure(adapter)  # type: ignore[attr-defined]
    adapter.remember_profile_number("p1", 1)
    dirs = adapter.prepare_profile_directories("p1")
    snapshot_path = dirs["runtime"] / "snapshot.json"
    snapshot_path.write_text(
        json.dumps({"version": 1, "config": {"proxy_id": "px-1"}}),
        encoding="utf-8",
    )
    secret_dir = adapter.validator.get_secret_dir("p1")
    secret_dir.mkdir(parents=True, exist_ok=True)
    creds_file = secret_dir / "proxy_credentials.json"
    creds_file.write_text(json.dumps(creds), encoding="utf-8")
    creds_file.chmod(0o600)
    return dirs, snapshot_path


@pytest.mark.asyncio
async def test_browser_start_adds_extra_hosts_for_mapped_loopback(tmp_path):
    adapter, _fake, _calls, _root = _adapter(tmp_path)
    mock_client = MagicMock()
    adapter.client = mock_client
    browser_container = MagicMock()
    browser_container.id = "cid-browser"
    mock_client.containers.run.return_value = browser_container
    adapter.create_browser_network = AsyncMock()
    adapter.ensure_runtime_cache = AsyncMock()
    adapter.setup_x11_permissions = MagicMock()
    adapter.cleanup_container_by_name = MagicMock()
    adapter._prepare_policy_gate = MagicMock(return_value=tmp_path / "data" / "control" / "gates" / "p1" / "inst" / "gate")
    adapter._validate_cache_paths = MagicMock()
    adapter._install_network_policy = MagicMock()
    _dirs, snapshot_path = _stage_browser(
        adapter,
        tmp_path,
        {
            "scheme": "http",
            "host": "host.docker.internal",
            "port": 7890,
            "username": None,
            "password": None,
            "credential_revision": 1,
        },
    )
    await adapter.start_browser_container(
        profile_id="p1",
        runtime_instance_id="inst_1",
        snapshot_json_path=snapshot_path,
    )
    kwargs = mock_client.containers.run.call_args.kwargs
    assert kwargs["extra_hosts"] == {"host.docker.internal": "host-gateway"}


@pytest.mark.asyncio
async def test_browser_start_no_extra_hosts_for_public_proxy(tmp_path):
    adapter, _fake, _calls, _root = _adapter(tmp_path)
    mock_client = MagicMock()
    adapter.client = mock_client
    browser_container = MagicMock()
    browser_container.id = "cid-browser"
    mock_client.containers.run.return_value = browser_container
    adapter.create_browser_network = AsyncMock()
    adapter.ensure_runtime_cache = AsyncMock()
    adapter.setup_x11_permissions = MagicMock()
    adapter.cleanup_container_by_name = MagicMock()
    adapter._prepare_policy_gate = MagicMock(return_value=tmp_path / "data" / "control" / "gates" / "p1" / "inst" / "gate")
    adapter._validate_cache_paths = MagicMock()
    adapter._install_network_policy = MagicMock()
    _dirs, snapshot_path = _stage_browser(
        adapter,
        tmp_path,
        {
            "scheme": "http",
            "host": "proxy.example.com",
            "port": 8080,
            "username": None,
            "password": None,
            "credential_revision": 1,
        },
    )
    await adapter.start_browser_container(
        profile_id="p1",
        runtime_instance_id="inst_1",
        snapshot_json_path=snapshot_path,
    )
    kwargs = mock_client.containers.run.call_args.kwargs
    assert kwargs["extra_hosts"] is None


@pytest.mark.asyncio
async def test_browser_start_loopback_mapping_failure_is_explicit(tmp_path):
    adapter, _fake, _calls, _root = _adapter(tmp_path)
    mock_client = MagicMock()
    adapter.client = mock_client
    mock_client.containers.run.side_effect = docker.errors.APIError(
        "extra_hosts host-gateway is not supported by this daemon"
    )
    adapter.create_browser_network = AsyncMock()
    adapter.ensure_runtime_cache = AsyncMock()
    adapter.setup_x11_permissions = MagicMock()
    adapter.cleanup_container_by_name = MagicMock()
    adapter._prepare_policy_gate = MagicMock(return_value=tmp_path / "data" / "control" / "gates" / "p1" / "inst" / "gate")
    adapter._validate_cache_paths = MagicMock()
    adapter._resolved_endpoint = MagicMock(return_value=[])
    adapter._install_network_policy = MagicMock()
    _dirs, snapshot_path = _stage_browser(
        adapter,
        tmp_path,
        {
            "scheme": "http",
            "host": "host.docker.internal",
            "port": 7890,
            "username": None,
            "password": None,
            "credential_revision": 1,
        },
    )
    with pytest.raises(LoopbackMappingError) as excinfo:
        await adapter.start_browser_container(
            profile_id="p1",
            runtime_instance_id="inst_1",
            snapshot_json_path=snapshot_path,
        )
    assert "Loopback proxy mapping failed" in str(excinfo.value)


# ---- core._write_proxy_credentials (Browser credential hand-off) ----------


def _write_core_credentials(core, tmp_path: Path, creds: dict) -> Path:
    target = tmp_path / "proxy_credentials.json"
    core._write_proxy_credentials(target, creds)
    return target


def test_write_proxy_credentials_maps_loopback_host(tmp_path):
    core = SupervisorCore.__new__(SupervisorCore)
    core.docker = SimpleNamespace(manage_ownership=False)
    target = _write_core_credentials(
        core,
        tmp_path,
        {
            "scheme": "http",
            "host": "127.0.0.1",
            "port": 7890,
            "username": "user",
            "password": "pw",
            "credential_revision": 1,
        },
    )
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["host"] == "host.docker.internal"
    assert written["port"] == 7890
    assert written["password"] == "pw"
    assert (target.stat().st_mode & 0o777) == 0o600

    _write_core_credentials(
        core,
        tmp_path,
        {
            "scheme": "http",
            "host": "proxy.example.com",
            "port": 8080,
            "username": None,
            "password": None,
            "credential_revision": 1,
        },
    )
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["host"] == "proxy.example.com"


def test_write_proxy_credentials_preserves_special_chars_privately(tmp_path):
    core = SupervisorCore.__new__(SupervisorCore)
    core.docker = SimpleNamespace(manage_ownership=False)
    password = "p@ss:w=rd%1!/#?"
    target = _write_core_credentials(
        core,
        tmp_path,
        {
            "scheme": "socks5",
            "host": "proxy.example.com",
            "port": 1080,
            "username": "u@domain",
            "password": password,
            "credential_revision": 4,
        },
    )
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["password"] == password
    assert written["username"] == "u@domain"
    assert (target.stat().st_mode & 0o777) == 0o600


def test_write_proxy_credentials_keeps_invalid_endpoint_unmapped(tmp_path):
    core = SupervisorCore.__new__(SupervisorCore)
    core.docker = SimpleNamespace(manage_ownership=False)
    target = _write_core_credentials(
        core,
        tmp_path,
        {
            "scheme": "http",
            "host": "bad@host",
            "port": 8080,
            "username": None,
            "password": None,
            "credential_revision": 1,
        },
    )
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["host"] == "bad@host"
    assert (target.stat().st_mode & 0o777) == 0o600


# ---- control server: removed probe route + retained auth ------------------


@pytest.mark.asyncio
async def test_removed_probe_route_is_absent_and_auth_still_enforced(tmp_path):
    token = secrets.token_urlsafe(32)
    key = tmp_path / "key"
    key.write_text(token)
    key.chmod(0o600)
    app = create_control_app(SimpleNamespace(), key)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://supervisor"
    ) as client:
        denied = await client.post(
            "/supervisor/v1/proxies/px-1/probe", json={"proxy_id": "px-1"}
        )
        assert denied.status_code == 404

        no_auth = await client.get("/supervisor/v1/health")
        assert no_auth.status_code == 401

        allowed = await client.get(
            "/supervisor/v1/health",
            headers={"Authorization": "Bearer " + token},
        )
        assert allowed.status_code == 200
