"""t065: forwarder lifecycle proofs (test f004).

``_replace_proxy_forwarder_only`` had zero tests anywhere in the repo:
reconcile rebuilding only the forwarder (missing or exited), the
replacement budget, a failed create leaving no orphan, stop/teardown
removing the forwarder, readiness flagging a missing forwarder, and
the no-proxy mode creating none. Core-level tests use a fake adapter;
adapter-level tests use the real DockerAdapter against a faked Docker
client. The Browser and Stream containers are never touched by the
forwarder-only path — the fake adapter has no start/stop methods for
them, so any such call would fail the test outright.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import docker
import httpx
import pytest

from cbrowser.runtime_agent.runner import PROXY_FORWARDER_FILENAME
from cbrowser.supervisor.core import ActiveSession, SupervisorCore
from cbrowser.supervisor.docker_adapter import DockerAdapter, DockerSandboxError
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator

IMAGE = "sha256:" + "a" * 64
PROFILE = "p1"
INSTANCE = "i1"


# ---------------------------------------------------------------------------
# Core-level harness (fake adapter)
# ---------------------------------------------------------------------------


class _LifecycleAdapter:
    """Minimal fake adapter for the core reconcile/readiness seams."""

    def __init__(self, root: Path) -> None:
        self.validator = PathValidator(root)
        self.create_proxy_forwarder = AsyncMock()
        self.scan_results: list[dict] = []
        self.profile_containers: dict[str, Any] = {}
        self.media = {
            "exists": True,
            "conforms": True,
            "gateway_attached_id": "gw",
            "plan": SimpleNamespace(),
        }

    def scan_active_containers(self) -> list[dict]:
        return list(self.scan_results)

    def get_profile_containers(self, profile_id: str) -> dict[str, Any]:
        return dict(self.profile_containers)

    def inspect_media_network(self, profile_id: str) -> dict:
        return dict(self.media)

    def resolve_gateway_container_id(self) -> str | None:
        return "gw"

    def get_proxy_forwarder_container_name(self, profile_id: str) -> str:
        return "cbrowser-t005-0001-proxy-forwarder"

    def stream_policy_spec(
        self, plan, gateway_port: int, udp_mux_port: int
    ) -> dict:
        return {"role": "stream"}

    def browser_policy_spec(self, profile_id: str, container) -> dict:
        return {"role": "browser"}

    def proxy_forwarder_policy_spec(self, profile_id: str, container) -> dict:
        return {"role": "proxy-forwarder"}

    def verify_container_policy(self, container, spec) -> bool:
        return True


def _api_client(runtime: dict) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(f"/profiles/{PROFILE}/runtime"):
            return httpx.Response(200, json=runtime)
        return httpx.Response(200, json={})

    return httpx.AsyncClient(
        base_url="http://api.invalid", transport=httpx.MockTransport(handler)
    )


def _api_404() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="http://api.invalid",
        transport=httpx.MockTransport(lambda r: httpx.Response(404)),
    )


def _core(tmp_path: Path, adapter, api: httpx.AsyncClient) -> SupervisorCore:
    return SupervisorCore(
        adapter,
        PortAllocator(),
        EventForwarder("http://api.invalid", tmp_path / "spool", client=_api_404()),
        api,
    )


def _session(*, observed_state: str = "running") -> ActiveSession:
    return ActiveSession(
        PROFILE, INSTANCE, 1, 0, "c_browser", "c_stream",
        observed_state=observed_state,
    )


def _roles(*, forwarder: dict | None = None) -> dict:
    roles = {
        "browser": {
            "id": "c_browser",
            "status": "running",
            "instance_id": INSTANCE,
            "profile_id": PROFILE,
            "config_version": 1,
            "policy_ready": True,
        },
        "stream": {
            "id": "c_stream",
            "status": "running",
            "instance_id": INSTANCE,
            "profile_id": PROFILE,
            "config_version": 1,
            "policy_ready": True,
        },
    }
    if forwarder is not None:
        roles["proxy-forwarder"] = forwarder
    return roles


def _runtime(*, observed_state: str = "starting") -> dict:
    return {
        "profile_id": PROFILE,
        "desired_state": "running",
        "observed_state": observed_state,
        "runtime_instance_id": INSTANCE,
        "config_version": 1,
    }


def _write_endpoint(adapter: _LifecycleAdapter) -> Path:
    runtime_dir = adapter.validator.get_runtime_dir(PROFILE)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    endpoint = runtime_dir / PROXY_FORWARDER_FILENAME
    endpoint.write_text(
        json.dumps(
            {
                "scheme": "http",
                "host": "cbrowser-t005-0001-proxy-forwarder",
                "port": 18080,
                "credential_revision": 2,
            }
        ),
        encoding="utf-8",
    )
    return endpoint


# ---------------------------------------------------------------------------
# Reconcile: rebuild only the forwarder
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "forwarder",
    [
        None,  # forwarder container gone entirely
        {
            "id": "c_fw",
            "status": "exited",  # forwarder exited (restart recovery)
            "instance_id": INSTANCE,
            "profile_id": PROFILE,
        },
    ],
)
async def test_reconcile_rebuilds_only_missing_or_exited_forwarder(
    tmp_path: Path, forwarder: dict | None
) -> None:
    """A proxy Profile whose forwarder is missing or exited is repaired
    by rebuilding only the forwarder: the Browser and Stream keep
    running untouched and reconnect to the same deterministic name."""
    adapter = _LifecycleAdapter(tmp_path / "data")
    _write_endpoint(adapter)
    core = _core(tmp_path, adapter, _api_client(_runtime()))
    core._sessions[PROFILE] = _session()
    await core._reconcile_profile(PROFILE, _roles(forwarder=forwarder))
    adapter.create_proxy_forwarder.assert_awaited_once_with(PROFILE, INSTANCE, 1)
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "ready"
    assert observation.last_error is None
    assert len(core._forwarder_replace_attempts[f"{PROFILE}:{INSTANCE}"]) == 1


@pytest.mark.asyncio
async def test_reconcile_forwarder_missing_budget_exhausted(
    tmp_path: Path,
) -> None:
    """Three forwarder replacements inside 300s exhaust the budget:
    reconcile reports proxy_forwarder_missing_budget_exhausted and
    does not create another forwarder."""
    adapter = _LifecycleAdapter(tmp_path / "data")
    _write_endpoint(adapter)
    core = _core(tmp_path, adapter, _api_client(_runtime()))
    core._sessions[PROFILE] = _session()
    core._forwarder_replace_attempts[f"{PROFILE}:{INSTANCE}"] = [
        time.monotonic()
    ] * 3
    await core._reconcile_profile(PROFILE, _roles())
    adapter.create_proxy_forwarder.assert_not_awaited()
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "failed"
    assert (
        observation.last_error == "proxy_forwarder_missing_budget_exhausted"
    )


@pytest.mark.asyncio
async def test_replace_forwarder_create_failure_returns_false(
    tmp_path: Path,
) -> None:
    """A failed forwarder create reports failure (transport failed)
    and returns False; the adapter-side reclaim owns orphan removal
    (test_failed_forwarder_create_removes_orphan below)."""
    adapter = _LifecycleAdapter(tmp_path / "data")
    adapter.create_proxy_forwarder = AsyncMock(
        side_effect=DockerSandboxError("forwarder start failed")
    )
    core = _core(tmp_path, adapter, _api_client(_runtime()))
    assert await core._replace_proxy_forwarder_only(PROFILE, _session()) is False
    observation = core.get_transport_observation(PROFILE)
    assert observation.transport_state == "failed"
    assert (observation.last_error or "").startswith(
        "proxy_forwarder_replacement_failed:DockerSandboxError"
    )


@pytest.mark.asyncio
async def test_reconcile_no_endpoint_file_creates_no_forwarder(
    tmp_path: Path, monkeypatch
) -> None:
    """No-proxy mode: without an endpoint file the forwarder branch
    never fires — reconcile must not invent a forwarder for a Profile
    that never had a proxy."""
    adapter = _LifecycleAdapter(tmp_path / "data")
    core = _core(tmp_path, adapter, _api_client(_runtime()))
    core._sessions[PROFILE] = _session(observed_state="starting")

    async def _no_health(profile_id: str):
        return None

    monkeypatch.setattr(core, "_query_agent_health", _no_health)
    await core._reconcile_profile(PROFILE, _roles())
    adapter.create_proxy_forwarder.assert_not_awaited()
    assert core.get_transport_observation(PROFILE).last_error is None


# ---------------------------------------------------------------------------
# Readiness: the forwarder counts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_readiness_flags_missing_forwarder(tmp_path: Path) -> None:
    """A proxy Profile whose forwarder is not running is not ready:
    the readiness check names proxy_forwarder_not_running."""
    adapter = _LifecycleAdapter(tmp_path / "data")
    _write_endpoint(adapter)
    adapter.profile_containers = {
        "browser": SimpleNamespace(status="running"),
        "stream": SimpleNamespace(status="running"),
    }
    core = _core(tmp_path, adapter, _api_client(_runtime()))
    core._sessions[PROFILE] = _session()
    readiness = await core._profile_readiness(PROFILE, _runtime())
    assert readiness.checks["proxy-forwarder"] is False
    assert "proxy_forwarder_not_running" in readiness.diagnostics
    assert readiness.ready is False


@pytest.mark.asyncio
async def test_readiness_vacuous_without_endpoint(tmp_path: Path) -> None:
    """A Profile without an endpoint file has no forwarder to check:
    the proxy-forwarder check passes vacuously."""
    adapter = _LifecycleAdapter(tmp_path / "data")
    adapter.profile_containers = {
        "browser": SimpleNamespace(status="running"),
        "stream": SimpleNamespace(status="running"),
    }
    core = _core(tmp_path, adapter, _api_client(_runtime()))
    core._sessions[PROFILE] = _session()
    readiness = await core._profile_readiness(PROFILE, _runtime())
    assert readiness.checks["proxy-forwarder"] is True
    assert "proxy_forwarder_not_running" not in readiness.diagnostics


@pytest.mark.asyncio
async def test_readiness_passes_with_running_forwarder(tmp_path: Path) -> None:
    """A proxy Profile whose forwarder runs passes the forwarder check."""
    adapter = _LifecycleAdapter(tmp_path / "data")
    _write_endpoint(adapter)
    adapter.profile_containers = {
        "browser": SimpleNamespace(status="running"),
        "stream": SimpleNamespace(status="running"),
        "proxy-forwarder": SimpleNamespace(status="running"),
    }
    core = _core(tmp_path, adapter, _api_client(_runtime()))
    core._sessions[PROFILE] = _session()
    readiness = await core._profile_readiness(PROFILE, _runtime())
    assert readiness.checks["proxy-forwarder"] is True
    assert "proxy_forwarder_not_running" not in readiness.diagnostics


# ---------------------------------------------------------------------------
# Stop/teardown: the forwarder counts as sandbox residue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_sandbox_gone_counts_forwarder(tmp_path: Path) -> None:
    """The sandbox is not gone while a proxy-forwarder container for
    the Profile still shows in the scan — teardown must remove it."""
    adapter = _LifecycleAdapter(tmp_path / "data")
    adapter.scan_results = [
        {"profile_id": PROFILE, "role": "browser"},
        {"profile_id": PROFILE, "role": "stream"},
        {"profile_id": PROFILE, "role": "proxy-forwarder"},
    ]
    core = _core(tmp_path, adapter, _api_client(_runtime()))
    assert await core._confirm_sandbox_gone(PROFILE) is False
    adapter.scan_results = [
        {"profile_id": PROFILE, "role": "browser"},
        {"profile_id": PROFILE, "role": "stream"},
    ]
    assert await core._confirm_sandbox_gone(PROFILE) is False
    adapter.scan_results = []
    assert await core._confirm_sandbox_gone(PROFILE) is True


# ---------------------------------------------------------------------------
# Adapter-level: failed create leaves no orphan; teardown removes all
# ---------------------------------------------------------------------------


def _real_adapter(tmp_path: Path) -> tuple[DockerAdapter, Path]:
    data_root = tmp_path / "data"
    (data_root / "engine_cache" / "geoip").mkdir(parents=True)
    validator = PathValidator(data_root)
    adapter = DockerAdapter(
        path_validator=validator,
        engine_cache_dir=data_root / "engine_cache",
        docker_client=MagicMock(),
        browser_image=IMAGE,
        stream_image=IMAGE,
        proxy_forwarder_image=IMAGE,
        policy_image=IMAGE,
        deployment_instance_id="dep-1",
    )
    adapter.remember_profile_number(PROFILE, 1)
    return adapter, data_root


def _stage_creds(adapter: DockerAdapter, host: str, port: int) -> Path:
    secret_dir = adapter.validator.get_secret_dir(PROFILE)
    secret_dir.mkdir(parents=True, exist_ok=True)
    creds = secret_dir / "proxy_credentials.json"
    creds.write_text(
        json.dumps(
            {
                "scheme": "http",
                "host": host,
                "port": port,
                "username": "u",
                "password": "s3cr3t",
                "credential_revision": 2,
            }
        ),
        encoding="utf-8",
    )
    creds.chmod(0o600)
    return creds


@pytest.mark.asyncio
async def test_failed_forwarder_create_removes_orphan(tmp_path: Path) -> None:
    """A forwarder container that was created but whose policy install
    fails (DNS resolution inside the container errors) is removed by
    the reclaim — no half-created forwarder is left behind."""
    adapter, _data_root = _real_adapter(tmp_path)
    creds = _stage_creds(adapter, "proxy.example.com", 8080)
    container = MagicMock()
    container.id = "cid"

    def _exec_run(cmd, user=None, **kwargs):
        joined = " ".join(str(part) for part in cmd)
        if "getaddrinfo" in joined:
            return SimpleNamespace(exit_code=1, output=b"dns failure")
        return SimpleNamespace(exit_code=0, output=b"")

    container.exec_run = MagicMock(side_effect=_exec_run)
    adapter.client.containers.get = MagicMock(
        side_effect=docker.errors.NotFound("no such container")
    )
    adapter.client.containers.run = MagicMock(return_value=container)
    with pytest.raises(DockerSandboxError, match="DNS resolution failed"):
        await adapter.create_proxy_forwarder(
            profile_id=PROFILE,
            runtime_instance_id=INSTANCE,
            creds_file=creds,
            config_version="1",
        )
    container.remove.assert_called_once_with(force=True)


def _labeled_container(role: str) -> MagicMock:
    container = MagicMock()
    container.name = f"cbrowser-t005-0001-{role}"
    container.labels = {
        "com.cbrowser.prefix": "cbrowser-t005",
        "com.cbrowser.managed-by": "supervisor",
        "com.cbrowser.role": role,
        "com.cbrowser.profile-id": PROFILE,
        "com.cbrowser.profile-number": "0001",
    }
    return container


def test_teardown_removes_forwarder_container(tmp_path: Path) -> None:
    """Teardown removes the forwarder alongside the Browser and the
    Stream — a stopped Profile leaves no forwarder container behind."""
    adapter, _data_root = _real_adapter(tmp_path)
    containers = {
        f"cbrowser-t005-0001-{role}": _labeled_container(role)
        for role in ("stream", "browser", "proxy-forwarder")
    }
    adapter.client.containers.get = MagicMock(
        side_effect=lambda name: containers[name]
    )
    adapter.client.networks.get = MagicMock(
        side_effect=docker.errors.NotFound("no such network")
    )
    adapter._teardown_profile_sync(PROFILE)
    for container in containers.values():
        container.remove.assert_called_once_with(force=True)
