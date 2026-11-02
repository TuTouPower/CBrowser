"""Real file and loopback protocol faults at the Agent boundary."""

import asyncio
import gc
import json
import logging
import os
import socket
from pathlib import Path

import httpx
import pytest
import uvicorn
import websockets
from cbrowser.runtime_agent.agent import create_agent_app
from cbrowser.runtime_agent.cdp_proxy import CdpProxyManager
from cbrowser.runtime_agent.event_storage import EventStorage


@pytest.mark.asyncio
async def test_uninitialized_health_does_not_invent_applied_version(
    tmp_path: Path,
) -> None:
    app = create_agent_app(tmp_path, tmp_path / "downloads")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://agent"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["/health", "/config_version", "/cdp/version"])
async def test_corrupt_private_metadata_returns_safe_fault(
    tmp_path: Path, route: str
) -> None:
    canary = "private_metadata_canary_912"
    (tmp_path / "runner_info.json").write_text(
        json.dumps(
            {
                "profile_id": "profile_a",
                "runtime_instance_id": "instance_a",
                "config_version": canary,
            }
        )
    )
    app = create_agent_app(tmp_path, tmp_path / "downloads")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://agent"
    ) as client:
        response = await client.get(route)
    assert response.status_code == 503
    assert canary not in response.text


@pytest.mark.asyncio
async def test_command_timeout_releases_pending_request(tmp_path: Path) -> None:
    # An actual loopback WebSocket peer deliberately withholds its response.
    # This checks protocol cleanup, not real Chrome behavior.
    async def silent_peer(connection):
        async for _message in connection:
            pass

    async with websockets.serve(silent_peer, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        manager = CdpProxyManager(
            f"ws://127.0.0.1:{port}",
            tmp_path / "downloads",
            "profile_a",
            "instance_a",
            EventStorage(tmp_path / "events"),
        )
        manager.agent_ws = await websockets.connect(manager.browser_ws_url)
        manager._event_listener_task = asyncio.create_task(manager._listen_events())
        try:
            with pytest.raises(TimeoutError):
                await manager.send_command("Browser.getVersion", timeout=0.02)
            assert manager.pending_cmd_futures == {}
        finally:
            await manager.close()


@pytest.mark.parametrize("inside", [True, False])
@pytest.mark.asyncio
async def test_completed_download_path_reflects_actual_capture_boundary(
    tmp_path: Path, inside: bool
) -> None:
    downloads = tmp_path / "downloads"
    target = (downloads if inside else tmp_path / "external") / "download_a"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"data")
    storage = EventStorage(tmp_path / "events")
    manager = CdpProxyManager(
        "ws://unused", downloads, "profile_a", "instance_a", storage
    )
    manager._handle_download_will_begin(
        {
            "guid": "download_a",
            "url": "https://fixture.test/file",
            "suggestedFilename": "result.txt",
        }
    )
    await manager._handle_download_progress(
        {
            "guid": "download_a",
            "state": "completed",
            "receivedBytes": 4,
            "totalBytes": 4,
            "filePath": str(target),
        }
    )
    completed = [
        event for event in storage.get_download_events() if event.state == "completed"
    ]
    assert len(completed) == 1
    assert completed[0].download_path == (str(target) if inside else None)


@pytest.mark.asyncio
async def test_tunnel_disconnect_drains_tasks_without_logging_close_payload(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    canary = "private_close_reason_391"

    async def echo_peer(connection):
        async for message in connection:
            await connection.send(message)

    async with websockets.serve(echo_peer, "127.0.0.1", 0) as upstream:
        upstream_port = upstream.sockets[0].getsockname()[1]
        (tmp_path / "runner_info.json").write_text(
            json.dumps(
                {
                    "profile_id": "profile_a",
                    "runtime_instance_id": "instance_a",
                    "config_version": 1,
                    "cdp_port": upstream_port,
                    "browser_pid": os.getpid(),
                    "browser_ws_url": f"ws://127.0.0.1:{upstream_port}",
                }
            )
        )
        app = create_agent_app(tmp_path, tmp_path / "downloads")
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        server = uvicorn.Server(
            uvicorn.Config(app, log_config=None, access_log=False, lifespan="off")
        )
        serving = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(5):
                while not server.started:
                    await asyncio.sleep(0.01)
                with caplog.at_level(logging.ERROR):
                    async with websockets.connect(
                        f"ws://127.0.0.1:{port}/cdp"
                    ) as client:
                        await client.send('{"id":1,"method":"Browser.getVersion"}')
                        assert json.loads(await client.recv())["id"] == 1
                        await client.close(reason=canary)
                    await asyncio.sleep(0.1)
                    gc.collect()
                    await asyncio.sleep(0)
            assert canary not in caplog.text
        finally:
            server.should_exit = True
            await asyncio.wait_for(serving, 5)
            listener.close()


@pytest.mark.asyncio
async def test_listener_fault_is_not_healthy_and_does_not_log_payload(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    canary = "private_protocol_canary_621"

    async def malformed_peer(connection):
        await connection.send(
            json.dumps(
                {
                    "method": "Browser.downloadProgress",
                    "params": {"guid": "download_a", "receivedBytes": canary},
                }
            )
        )
        await connection.wait_closed()

    async with websockets.serve(malformed_peer, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        manager = CdpProxyManager(
            f"ws://127.0.0.1:{port}",
            tmp_path / "downloads",
            "profile_a",
            "instance_a",
            EventStorage(tmp_path / "events"),
        )
        manager.agent_ws = await websockets.connect(manager.browser_ws_url)
        try:
            with caplog.at_level(logging.ERROR):
                manager._event_listener_task = asyncio.create_task(
                    manager._listen_events()
                )
                await asyncio.wait_for(manager._event_listener_task, timeout=2)
            assert canary not in caplog.text
            assert not manager.capture_alive
        finally:
            await manager.close()
