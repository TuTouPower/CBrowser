"""Reconciliation cannot adopt an in-flight or unprotected runtime as running."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from cbrowser.runtime_agent.protocol import HealthResponse
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
    lock = core.profile_lock("p")
    if in_flight:
        await lock.acquire()
    try:
        await core.scan_and_reconcile_existing()
        assert core.get_session("p") is None
    finally:
        if in_flight:
            lock.release()
        await api.aclose()


@pytest.mark.asyncio
async def test_one_profile_failure_does_not_block_another_restore(
    tmp_path, monkeypatch
):
    pair = []
    for profile_id, instance_id in (("bad", "i-bad"), ("good", "i-good")):
        for role in ("browser", "stream"):
            pair.append(
                {
                    "profile_id": profile_id,
                    "instance_id": instance_id,
                    "role": role,
                    "id": f"{role}-{profile_id}",
                    "status": "running",
                    "policy_ready": True,
                }
            )

    def inspect(container_id):
        if container_id == "stream-bad":
            return {"HostConfig": {"PortBindings": {}}}
        return {
            "HostConfig": {"PortBindings": {"30001/udp": [{"HostPort": "30001"}]}}
        }

    def runtime_response(request: httpx.Request) -> httpx.Response:
        # t083: intent is read through the minimal batch snapshot,
        # which carries every profile in one response.
        if request.url.path.endswith("/state/snapshot"):
            states = [
                {
                    "profile_id": pid,
                    "display_number": 1,
                    "desired_state": "running",
                    "observed_state": "running",
                    "runtime_instance_id": f"i-{pid}",
                    "config_version": 1,
                    "failure_count": 0,
                    "restart_blocked": False,
                    "last_exit_event_id": None,
                    "backoff_started_at": None,
                    "next_retry_at": None,
                    "updated_at": "2026-01-01T00:00:00+00:00",
                    "state_revision": 1,
                }
                for pid in ("bad", "good")
            ]
            return httpx.Response(
                200,
                json={
                    "api_epoch": "fences-test-epoch",
                    "profiles": states,
                    "next_cursor": None,
                },
            )
        profile_id = request.url.path.split("/")[6]
        return httpx.Response(
            200,
            json={
                "profile_id": profile_id,
                "desired_state": "running",
                "observed_state": "running",
                "runtime_instance_id": f"i-{profile_id}",
                "config_version": 1,
                "failure_count": 0,
                "restart_blocked": False,
            },
        )

    api = httpx.AsyncClient(
        transport=httpx.MockTransport(runtime_response),
        base_url="http://api",
        trust_env=False,
    )
    adapter = SimpleNamespace(
        validator=PathValidator(tmp_path),
        scan_active_containers=lambda: pair,
        client=SimpleNamespace(
            api=SimpleNamespace(inspect_container=inspect)
        ),
    )
    core = SupervisorCore(
        adapter,
        PortAllocator(),
        None,
        api,
        gateway_control=SimpleNamespace(
            has_foreground_viewers=AsyncMock(return_value=True)
        ),
    )

    async def health(profile_id: str) -> HealthResponse:
        return HealthResponse(
            status="ok",
            ready=True,
            display_ready=True,
            browser_ready=True,
            audio_ready=True,
            cdp_ready=True,
            profile_id=profile_id,
            runtime_instance_id=f"i-{profile_id}",
            config_version=1,
        )

    monkeypatch.setattr(core, "_query_agent_health", health)
    try:
        await core.scan_and_reconcile_existing()
        assert core.get_session("good").udp_mux_port == 30001
        assert core.get_session("bad") is None
    finally:
        await api.aclose()
