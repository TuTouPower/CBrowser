"""Reconciliation cannot adopt an in-flight or unprotected runtime as running."""

from types import SimpleNamespace

import httpx
import pytest
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator


@pytest.mark.asyncio
@pytest.mark.parametrize("in_flight,policy_ready", [(True, True), (False, False)])
async def test_reconcile_does_not_publish_inflight_or_unprotected_pair(
    tmp_path, in_flight, policy_ready
):
    pair = [
        {
            "profile_id": "p",
            "instance_id": "i",
            "role": role,
            "id": role,
            "status": "running",
            "policy_ready": policy_ready,
        }
        for role in ("browser", "stream")
    ]
    api = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "desired_state": "running",
                    "runtime_instance_id": "i",
                    "config_version": 1,
                    "failure_count": 0,
                    "restart_blocked": False,
                },
            )
        ),
        base_url="http://api",
        trust_env=False,
    )
    adapter = SimpleNamespace(
        validator=PathValidator(tmp_path),
        scan_active_containers=lambda: pair,
        client=SimpleNamespace(
            api=SimpleNamespace(
                inspect_container=lambda _: {
                    "HostConfig": {
                        "PortBindings": {"30000/udp": [{"HostPort": "30000"}]}
                    }
                }
            )
        ),
    )
    core = SupervisorCore(adapter, PortAllocator(), None, api)
    lock = core._get_profile_lock("p")
    if in_flight:
        await lock.acquire()
    try:
        await core.scan_and_reconcile_existing()
        assert "p" not in core._sessions
    finally:
        if in_flight:
            lock.release()
        await api.aclose()
