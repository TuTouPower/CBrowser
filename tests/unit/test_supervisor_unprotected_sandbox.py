"""Unprotected sandboxes are torn down fail-closed after a grace period."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import httpx
import pytest
import cbrowser.supervisor.core as core_module
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator


class _Docker:
    def __init__(self, data_root, policy_ready: bool) -> None:
        self.validator = PathValidator(data_root)
        self.policy_ready = policy_ready
        self.teardown_calls = 0

    def scan_active_containers(self):
        return [
            {
                "id": f"{role}-id",
                "status": "running",
                "profile_id": "p1",
                "instance_id": "inst1",
                "role": role,
                "config_version": 1,
                "policy_ready": self.policy_ready,
            }
            for role in ("browser", "stream")
        ]

    async def teardown_profile(self, profile_id: str) -> None:
        self.teardown_calls += 1


async def _core(tmp_path, docker):
    observed: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/observed"):
            observed.append(json.loads(request.content))
            return httpx.Response(200, json={})
        return httpx.Response(
            200,
            json={
                "profile_id": "p1",
                "desired_state": "running",
                "observed_state": "running",
                "runtime_instance_id": "inst1",
                "config_version": 1,
            },
        )

    api = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://api",
        trust_env=False,
    )
    core = SupervisorCore(
        docker,
        PortAllocator(),
        EventForwarder("http://api", tmp_path / "spool", client=api),
        api,
    )
    await core.ports.allocate("p1")
    return core, observed


@pytest.mark.asyncio
async def test_unprotected_sandbox_is_torn_down_after_grace(
    tmp_path, monkeypatch
) -> None:
    docker = _Docker(tmp_path, policy_ready=False)
    core, observed = await _core(tmp_path, docker)
    monkeypatch.setattr(core_module, "UNPROTECTED_SANDBOX_GRACE_SEC", 0.0)

    await core.scan_and_reconcile_existing()

    assert docker.teardown_calls == 1
    assert core.ports.get_port("p1") is None
    assert observed and observed[-1]["observed_state"] == "error"
    assert observed[-1]["reason"] == "unprotected_sandbox"
    await core.api.aclose()


@pytest.mark.asyncio
async def test_unprotected_sandbox_is_retained_during_grace(
    tmp_path, monkeypatch
) -> None:
    docker = _Docker(tmp_path, policy_ready=False)
    core, _observed = await _core(tmp_path, docker)
    monkeypatch.setattr(core_module, "UNPROTECTED_SANDBOX_GRACE_SEC", 60.0)

    await core.scan_and_reconcile_existing()
    await core.scan_and_reconcile_existing()
    assert docker.teardown_calls == 0

    core._unprotected_since["p1"] = time.monotonic() - 61.0
    await core.scan_and_reconcile_existing()
    assert docker.teardown_calls == 1
    assert core.ports.get_port("p1") is None
    await core.api.aclose()
