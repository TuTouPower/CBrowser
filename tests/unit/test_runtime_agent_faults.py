"""Real file and loopback protocol faults at the Agent boundary."""

import asyncio
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


async def _wait_until(predicate, timeout: float = 3.0) -> None:
    """Yield to the loop until predicate is true, without fixed sleeps."""

    async def poll() -> None:
        while not predicate():
            await asyncio.sleep(0)

    await asyncio.wait_for(poll(), timeout)


class ManualClock:
    """Deterministic sleep seam injected into the CDP proxy module."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def sleep(self, delay: float) -> None:
        self.delays.append(delay)
        await asyncio.sleep(0)


class _ClockAsyncio:
    def __init__(self, clock: ManualClock) -> None:
        self._clock = clock

    def __getattr__(self, name: str):
        return getattr(asyncio, name)

    async def sleep(self, delay: float) -> None:
        await self._clock.sleep(delay)


def _inject_clock(monkeypatch) -> ManualClock:
    import cbrowser.runtime_agent.cdp_proxy as cdp_module

    clock = ManualClock()
    monkeypatch.setattr(cdp_module, "asyncio", _ClockAsyncio(clock))
    return clock


async def _responsive_peer(connection, holder, on_open=None):
    """Answers CDP commands like Chrome and exposes the socket for test frames."""
    holder["ws"] = connection
    if on_open is not None:
        await on_open(connection)
    async for raw in connection:
        message = json.loads(raw)
        if "id" in message:
            await connection.send(
                json.dumps({"id": message["id"], "result": {}})
            )


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
    async def silent_after_setup(connection):
        async for raw in connection:
            message = json.loads(raw)
            if message.get("method") == "Browser.setDownloadBehavior":
                await connection.send(
                    json.dumps({"id": message["id"], "result": {}})
                )

    async with websockets.serve(silent_after_setup, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        manager = CdpProxyManager(
            f"ws://127.0.0.1:{port}",
            tmp_path / "downloads",
            "profile_a",
            "instance_a",
            EventStorage(tmp_path / "events"),
        )
        await manager.start()
        try:
            with pytest.raises(TimeoutError):
                await manager.send_command("Browser.getVersion", timeout=0.02)
            assert manager.pending_cmd_futures == {}
            assert manager.capture_alive is True
        finally:
            await manager.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("inside", [True, False])
async def test_completed_download_path_reflects_actual_capture_boundary(
    tmp_path: Path, inside: bool
) -> None:
    downloads = tmp_path / "downloads"
    target = (downloads if inside else tmp_path / "external") / "download_a"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"data")
    storage = EventStorage(tmp_path / "events")
    holder: dict[str, object] = {}

    async with websockets.serve(
        lambda connection: _responsive_peer(connection, holder),
        "127.0.0.1",
        0,
    ) as server:
        port = server.sockets[0].getsockname()[1]
        manager = CdpProxyManager(
            f"ws://127.0.0.1:{port}",
            downloads,
            "profile_a",
            "instance_a",
            storage,
        )
        await manager.start()
        try:
            await holder["ws"].send(
                json.dumps(
                    {
                        "method": "Browser.downloadWillBegin",
                        "params": {
                            "guid": "download_a",
                            "url": "https://fixture.test/file",
                            "suggestedFilename": "result.txt",
                        },
                    }
                )
            )
            await holder["ws"].send(
                json.dumps(
                    {
                        "method": "Browser.downloadProgress",
                        "params": {
                            "guid": "download_a",
                            "state": "completed",
                            "receivedBytes": 4,
                            "totalBytes": 4,
                            "filePath": str(target),
                        },
                    }
                )
            )
            # The listener answers in order, so this response proves both
            # preceding event frames were fully handled.
            await manager.send_command("Fixture.sync")
        finally:
            await manager.close()

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
                await _wait_until(lambda: server.started)
                with caplog.at_level(logging.ERROR):
                    async with websockets.connect(
                        f"ws://127.0.0.1:{port}/cdp"
                    ) as client:
                        await client.send('{"id":1,"method":"Browser.getVersion"}')
                        assert json.loads(await client.recv())["id"] == 1
                        await client.close(reason=canary)
                    # A later tunnel proves the previous close was handled and
                    # did not take the listener down.
                    async with websockets.connect(
                        f"ws://127.0.0.1:{port}/cdp"
                    ) as followup:
                        await followup.send(
                            '{"id":2,"method":"Browser.getVersion"}'
                        )
                        assert json.loads(await followup.recv())["id"] == 2
                        await followup.close()
            assert canary not in caplog.text
        finally:
            server.should_exit = True
            await asyncio.wait_for(serving, 5)
            listener.close()


@pytest.mark.asyncio
async def test_listener_isolates_malformed_frame_and_keeps_running(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    canary = "private_protocol_canary_621"
    holder: dict[str, object] = {}

    async def malformed_on_open(connection):
        await connection.send(
            json.dumps(
                {
                    "method": "Browser.downloadProgress",
                    "params": {"guid": "download_a", "receivedBytes": canary},
                }
            )
        )
        await connection.send(
            json.dumps(
                {
                    "method": "Browser.downloadWillBegin",
                    "params": {
                        "guid": "download_after_bad",
                        "url": "https://example.test/file",
                        "suggestedFilename": "file.bin",
                    },
                }
            )
        )

    async with websockets.serve(
        lambda connection: _responsive_peer(
            connection, holder, on_open=malformed_on_open
        ),
        "127.0.0.1",
        0,
    ) as server:
        port = server.sockets[0].getsockname()[1]
        manager = CdpProxyManager(
            f"ws://127.0.0.1:{port}",
            tmp_path / "downloads",
            "profile_a",
            "instance_a",
            EventStorage(tmp_path / "events"),
        )
        with caplog.at_level(logging.ERROR):
            await manager.start()
            try:
                await manager.send_command("Fixture.sync")
                assert canary not in caplog.text
                assert manager.capture_alive is True
                assert "download_after_bad" in manager.active_downloads
            finally:
                await manager.close()


@pytest.mark.asyncio
async def test_cdp_listener_reconnects_and_rearms_after_disconnect(
    tmp_path: Path, monkeypatch
) -> None:
    clock = _inject_clock(monkeypatch)
    connections = {"count": 0}
    second_connection = asyncio.Event()
    holder: dict[str, object] = {}

    async def reconnecting_peer(connection):
        connections["count"] += 1
        if connections["count"] >= 2:
            second_connection.set()
        await _responsive_peer(connection, holder)

    async with websockets.serve(reconnecting_peer, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        manager = CdpProxyManager(
            f"ws://127.0.0.1:{port}",
            tmp_path / "downloads",
            "profile_a",
            "instance_a",
            EventStorage(tmp_path / "events"),
        )
        await manager.start()
        try:
            assert manager.rearm_count == 1
            await holder["ws"].close()
            await asyncio.wait_for(second_connection.wait(), timeout=3.0)
            await _wait_until(
                lambda: manager.rearm_count >= 2 and manager.capture_alive
            )
            assert manager.rearm_count >= 2
            assert clock.delays and clock.delays[0] == 1.0
        finally:
            await manager.close()
