"""Blocking Docker SDK work must not stall the Supervisor event loop."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import httpx
import pytest
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator

BROWSER = "sha256:f2a8d42810c13c8480b83e4308669c754e86b0fe4a24c6215159e43a8d1f5346"
STREAM = "sha256:072e86762d2f1810e86a2d20169d4be451b5a19e0ebabc880e882de63ac0d531"


async def _ticker(stop: asyncio.Event) -> int:
    ticks = 0
    while not stop.is_set():
        await asyncio.sleep(0.01)
        ticks += 1
    return ticks


def _adapter(tmp_path):
    root = tmp_path / "data"
    engine = root / "engine_cache"
    engine.mkdir(parents=True)
    (engine / "geoip").mkdir(parents=True)
    return DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=engine,
        docker_client=object(),
        browser_image=BROWSER,
        stream_image=STREAM,
        policy_image=BROWSER,
    )


@pytest.mark.asyncio
async def test_teardown_offloads_blocking_docker_cleanup(tmp_path) -> None:
    adapter = _adapter(tmp_path)
    adapter._teardown_profile_sync = lambda _pid: time.sleep(0.3)

    stop = asyncio.Event()
    ticker = asyncio.create_task(_ticker(stop))
    started = time.monotonic()
    await adapter.teardown_profile("p1")
    elapsed = time.monotonic() - started
    stop.set()
    ticks = await ticker

    assert elapsed >= 0.25
    assert ticks >= 5


@pytest.mark.asyncio
async def test_scan_inspect_offloads_blocking_docker_call(tmp_path) -> None:
    class _Api:
        def inspect_container(self, _cid):
            time.sleep(0.3)
            return {
                "HostConfig": {
                    "PortBindings": {"30000/udp": [{"HostPort": "30000"}]}
                }
            }

    docker = SimpleNamespace(
        validator=PathValidator(tmp_path),
        client=SimpleNamespace(api=_Api()),
        scan_active_containers=lambda: [
            {
                "id": "b1",
                "status": "running",
                "profile_id": "p1",
                "instance_id": "inst1",
                "role": "browser",
                "config_version": 1,
                "policy_ready": True,
            },
            {
                "id": "s1",
                "status": "running",
                "profile_id": "p1",
                "instance_id": "inst1",
                "role": "stream",
                "config_version": 1,
                "policy_ready": True,
            },
        ],
    )

    async def handler(request: httpx.Request) -> httpx.Response:
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

    gateway = SimpleNamespace(
        has_foreground_viewers=async_none(True),
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://api",
        trust_env=False,
    ) as api:
        core = SupervisorCore(
            docker,
            PortAllocator(),
            EventForwarder(str(api.base_url), tmp_path / "spool", client=api),
            api,
            gateway_control=gateway,
        )
        stop = asyncio.Event()
        ticker = asyncio.create_task(_ticker(stop))
        started = time.monotonic()
        await core.scan_and_reconcile_existing()
        elapsed = time.monotonic() - started
        stop.set()
        ticks = await ticker

    assert elapsed >= 0.25
    assert ticks >= 5
    assert core.get_session("p1").udp_mux_port == 30000


def async_none(value):
    async def _call(*_args, **_kwargs):
        return value

    return _call
