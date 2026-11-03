"""Blocking Docker SDK work must not stall the Supervisor event loop."""

from __future__ import annotations

import asyncio
import threading
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
    started = threading.Event()
    release = threading.Event()

    def blocking_teardown(_pid: str) -> None:
        started.set()
        release.wait(2)

    adapter._teardown_profile_sync = blocking_teardown

    state = {"done": False, "unblocked_while_running": False}

    async def unblock() -> int:
        await asyncio.to_thread(started.wait, 2)
        state["unblocked_while_running"] = not state["done"]
        release.set()
        return 1

    task = asyncio.create_task(adapter.teardown_profile("p1"))
    task.add_done_callback(lambda _: state.update(done=True))
    ticks = await unblock()
    await task
    assert ticks == 1
    assert state["unblocked_while_running"] is True


@pytest.mark.asyncio
async def test_scan_inspect_offloads_blocking_docker_call(tmp_path) -> None:
    inspect_started = threading.Event()
    release_inspect = threading.Event()

    class _Api:
        def inspect_container(self, _cid):
            inspect_started.set()
            release_inspect.wait(2)
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
        state = {"done": False, "unblocked_while_running": False}

        async def unblock() -> int:
            await asyncio.to_thread(inspect_started.wait, 2)
            state["unblocked_while_running"] = not state["done"]
            release_inspect.set()
            return 1

        scan_task = asyncio.create_task(core.scan_and_reconcile_existing())
        scan_task.add_done_callback(lambda _: state.update(done=True))
        ticks = await unblock()
        await scan_task

    assert ticks == 1
    assert state["unblocked_while_running"] is True
    assert core.get_session("p1").udp_mux_port == 30000


def async_none(value):
    async def _call(*_args, **_kwargs):
        return value

    return _call
