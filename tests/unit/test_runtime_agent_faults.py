"""Real file and loopback protocol faults at the Agent boundary."""

import asyncio
import json
import logging
import os
import shutil
import socket
import tempfile
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


@pytest.fixture
def short_socket_dir():
    """Short AF_UNIX base: pytest tmp_path can exceed sun_path on macOS."""
    base = Path("/tmp") if Path("/tmp").is_dir() else Path(tempfile.gettempdir())
    root = Path(tempfile.mkdtemp(prefix="cbx", dir=base))
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


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


@pytest.mark.asyncio
async def test_cdp_reconnect_rearm_error_ack_keeps_unhealthy(
    tmp_path: Path, monkeypatch
) -> None:
    """A3: a reconnect rearm answered with a CDP error must not report healthy."""
    _inject_clock(monkeypatch)
    connections = {"count": 0}
    error_sent = asyncio.Event()
    holder: dict[str, object] = {}

    async def error_on_second(connection):
        connections["count"] += 1
        holder["ws"] = connection
        async for raw in connection:
            message = json.loads(raw)
            if "id" not in message:
                continue
            if connections["count"] >= 2 and (
                message.get("method") == "Browser.setDownloadBehavior"
            ):
                await connection.send(
                    json.dumps(
                        {"id": message["id"], "error": {"code": -32000, "message": "x"}}
                    )
                )
                error_sent.set()
            else:
                await connection.send(json.dumps({"id": message["id"], "result": {}}))

    async with websockets.serve(error_on_second, "127.0.0.1", 0) as server:
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
            assert manager.capture_alive is True
            await holder["ws"].close()
            await asyncio.wait_for(error_sent.wait(), timeout=3.0)
            await _wait_until(lambda: manager._rearm_pending_id is None)
            assert manager.capture_alive is False
            assert manager.rearm_count == 1
        finally:
            await manager.close()


@pytest.mark.asyncio
async def test_cdp_reconnect_rearm_without_ack_keeps_unhealthy(
    tmp_path: Path, monkeypatch
) -> None:
    """A3: a reconnect rearm that is never ACKed must not report healthy."""
    _inject_clock(monkeypatch)
    connections = {"count": 0}
    rearm_seen = asyncio.Event()
    holder: dict[str, object] = {}

    async def silent_rearm_on_second(connection):
        connections["count"] += 1
        holder["ws"] = connection
        async for raw in connection:
            message = json.loads(raw)
            if "id" not in message:
                continue
            if connections["count"] >= 2 and (
                message.get("method") == "Browser.setDownloadBehavior"
            ):
                rearm_seen.set()
                continue
            await connection.send(json.dumps({"id": message["id"], "result": {}}))

    async with websockets.serve(silent_rearm_on_second, "127.0.0.1", 0) as server:
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
            await asyncio.wait_for(rearm_seen.wait(), timeout=3.0)
            # Give the listener ample loop turns; health must remain unproven.
            for _ in range(20):
                await asyncio.sleep(0)
            assert manager.capture_alive is False
            assert manager.rearm_count == 1
        finally:
            await manager.close()


@pytest.mark.asyncio
async def test_agent_startup_rejects_metadata_missing_profile_id(
    tmp_path: Path,
) -> None:
    """A13: non-empty metadata missing a required field fails with a safe error."""
    from cbrowser.runtime_agent.agent import run_uds_agent
    from cbrowser.runtime_agent.event_storage import StorageError

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "runner_info.json").write_text(
        json.dumps(
            {
                "browser_ws_url": "ws://127.0.0.1:9222/devtools/browser/x",
                "runtime_instance_id": "instance_a",
                "config_version": 1,
            }
        )
    )
    with pytest.raises(StorageError):
        await run_uds_agent(run_dir, tmp_path / "downloads")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metadata",
    [
        {"profile_id": "profile_a", "runtime_instance_id": "instance_a"},
        {
            "profile_id": 123,
            "runtime_instance_id": "instance_a",
            "browser_ws_url": "ws://127.0.0.1:9222/x",
        },
        {
            "profile_id": "profile_a",
            "runtime_instance_id": "instance_a",
            "browser_ws_url": "http://127.0.0.1:9222/x",
        },
        {
            "profile_id": "profile_a",
            "runtime_instance_id": "instance_a",
            "browser_ws_url": "ws://127.0.0.1:9222/x",
            "cdp_port": "9222",
        },
    ],
)
async def test_agent_startup_metadata_validation(metadata: dict) -> None:
    """A13: missing fields and wrong types are rejected before CDP construction."""
    from cbrowser.runtime_agent.agent import _validated_runner_info
    from cbrowser.runtime_agent.event_storage import StorageError

    with pytest.raises(StorageError):
        _validated_runner_info(metadata)


def test_agent_startup_metadata_validation_accepts_complete() -> None:
    from cbrowser.runtime_agent.agent import _validated_runner_info

    info = _validated_runner_info(
        {
            "profile_id": "profile_a",
            "runtime_instance_id": "instance_a",
            "browser_ws_url": "ws://127.0.0.1:9222/x",
            "config_version": 3,
            "cdp_port": 9222,
        }
    )
    assert info["profile_id"] == "profile_a"


def test_x11_lock_with_live_pid_is_kept(tmp_path: Path) -> None:
    """A14: a lock owned by a live process is never removed."""
    from cbrowser.runtime_agent.runner import BrowserRunner

    lock = tmp_path / ".X99-lock"
    sock = tmp_path / "X99"
    lock.write_text(str(os.getpid()))
    sock.touch()
    with pytest.raises(RuntimeError):
        BrowserRunner._clear_stale_x11_state(lock, sock)
    assert lock.exists()
    assert sock.exists()


def test_x11_lock_with_dead_pid_is_cleared(tmp_path: Path) -> None:
    """A14: only a parseable lock whose owner is gone is cleaned up."""
    import subprocess
    import sys

    from cbrowser.runtime_agent.runner import BrowserRunner

    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    lock = tmp_path / ".X99-lock"
    sock = tmp_path / "X99"
    lock.write_text(str(proc.pid))
    sock.touch()
    BrowserRunner._clear_stale_x11_state(lock, sock)
    assert not lock.exists()
    assert not sock.exists()


def test_x11_corrupt_lock_is_kept_with_explicit_error(tmp_path: Path) -> None:
    """A14: an unparseable lock cannot prove staleness; lock and socket stay."""
    from cbrowser.runtime_agent.runner import BrowserRunner

    lock = tmp_path / ".X99-lock"
    sock = tmp_path / "X99"
    lock.write_text("not-a-pid")
    sock.touch()
    with pytest.raises(RuntimeError):
        BrowserRunner._clear_stale_x11_state(lock, sock)
    assert lock.exists()
    assert sock.exists()


def test_x11_unreadable_lock_is_kept_with_explicit_error(tmp_path: Path) -> None:
    """A14: a lock that cannot be read cannot prove staleness either."""
    from cbrowser.runtime_agent.runner import BrowserRunner

    lock = tmp_path / ".X99-lock"
    lock.mkdir()  # a directory makes read_text fail with an OSError
    sock = tmp_path / "X99"
    sock.touch()
    with pytest.raises(RuntimeError):
        BrowserRunner._clear_stale_x11_state(lock, sock)
    assert lock.exists()
    assert sock.exists()


@pytest.mark.asyncio
async def test_agent_search_defaults_retry_fenced_and_idempotent(
    tmp_path: Path,
) -> None:
    """A55: retry requires the exact live identity; repeats are accepted
    without changing the recorded request."""
    (tmp_path / "runner_info.json").write_text(
        json.dumps(
            {
                "profile_id": "profile_a",
                "runtime_instance_id": "instance_a",
                "config_version": 1,
            }
        )
    )
    app = create_agent_app(tmp_path, tmp_path / "downloads")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://agent"
    ) as client:
        ok = await client.post(
            "/control",
            json={
                "action": "retry_search_defaults",
                "params": {
                    "profile_id": "profile_a",
                    "runtime_instance_id": "instance_a",
                    "request_id": "req-1",
                },
            },
        )
        assert ok.status_code == 200
        request_file = tmp_path / "search_defaults_retry.json"
        assert json.loads(request_file.read_text())["request_id"] == "req-1"

        stale = await client.post(
            "/control",
            json={
                "action": "retry_search_defaults",
                "params": {
                    "profile_id": "profile_a",
                    "runtime_instance_id": "instance_old",
                    "request_id": "req-2",
                },
            },
        )
        assert stale.status_code == 403
        assert json.loads(request_file.read_text())["request_id"] == "req-1"

        repeat = await client.post(
            "/control",
            json={
                "action": "retry_search_defaults",
                "params": {
                    "profile_id": "profile_a",
                    "runtime_instance_id": "instance_a",
                    "request_id": "req-1",
                },
            },
        )
        assert repeat.status_code == 200


@pytest.mark.asyncio
async def test_agent_health_exposes_search_defaults_status(tmp_path: Path) -> None:
    """A55: health carries the typed independent search-defaults status."""
    from cbrowser.runtime_agent.profile_defaults import write_search_defaults_status

    (tmp_path / "runner_info.json").write_text(
        json.dumps(
            {
                "profile_id": "profile_a",
                "runtime_instance_id": "instance_a",
                "config_version": 1,
            }
        )
    )
    write_search_defaults_status(
        tmp_path,
        state="failed",
        runtime_instance_id="instance_a",
        error_kind="ProfileDefaultsError",
    )
    app = create_agent_app(tmp_path, tmp_path / "downloads")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://agent"
    ) as client:
        response = await client.get("/health")
    body = response.json()
    assert body["search_defaults"]["state"] == "failed"
    assert body["search_defaults"]["error_kind"] == "ProfileDefaultsError"


@pytest.mark.asyncio
async def test_rearm_timeout_keeps_capture_unhealthy(
    tmp_path: Path, monkeypatch
) -> None:
    """A3: a rearm whose ACK never arrives within the timeout raises, does
    not count as a rearm, and a later successful rearm still recovers."""
    _inject_clock(monkeypatch)
    silent = {"enabled": False}

    async def answering(connection):
        async for raw in connection:
            message = json.loads(raw)
            if "id" not in message:
                continue
            if silent["enabled"] and (
                message.get("method") == "Browser.setDownloadBehavior"
            ):
                continue
            await connection.send(json.dumps({"id": message["id"], "result": {}}))

    async with websockets.serve(answering, "127.0.0.1", 0) as server:
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
            silent["enabled"] = True
            with pytest.raises(TimeoutError):
                await manager.rearm_download_capture(timeout=0.3)
            assert manager.rearm_count == 1
            silent["enabled"] = False
            await manager.rearm_download_capture(timeout=2.0)
            assert manager.rearm_count == 2
        finally:
            await manager.close()


@pytest.mark.asyncio
async def test_reconnect_rearm_late_ack_does_not_restore_health(
    tmp_path: Path, monkeypatch
) -> None:
    """A3/f008: a rearm ACK arriving after the ACK window closed is
    ignored — it must not resurrect health for a stale rearm."""
    _inject_clock(monkeypatch)
    connections = {"count": 0}
    holder: dict[str, object] = {}

    async def late_ack_on_second(connection):
        connections["count"] += 1
        holder["ws"] = connection
        async for raw in connection:
            message = json.loads(raw)
            if "id" not in message:
                continue
            if connections["count"] >= 2 and (
                message.get("method") == "Browser.setDownloadBehavior"
            ):
                await asyncio.sleep(0.6)
                await connection.send(
                    json.dumps({"id": message["id"], "result": {}})
                )
            else:
                await connection.send(json.dumps({"id": message["id"], "result": {}}))

    async with websockets.serve(late_ack_on_second, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        manager = CdpProxyManager(
            f"ws://127.0.0.1:{port}",
            tmp_path / "downloads",
            "profile_a",
            "instance_a",
            EventStorage(tmp_path / "events"),
        )
        manager._rearm_ack_timeout_s = 0.3
        await manager.start()
        try:
            assert manager.rearm_count == 1
            await holder["ws"].close()
            # The late ACK (0.6s > 0.3s window) arrives and is ignored.
            await _wait_until(lambda: manager._rearm_pending_id is None)
            await asyncio.sleep(0.8)
            assert manager.capture_alive is False
            assert manager.rearm_count == 1
        finally:
            await manager.close()


def test_x11_socket_without_lock_and_dead_server_is_cleared(
    short_socket_dir: Path,
) -> None:
    """A14/f012: no lock file — the socket alone is probed; a socket that
    refuses connections is proven stale and removed."""
    import socket as _socket

    from cbrowser.runtime_agent.runner import BrowserRunner

    sock = short_socket_dir / "X0"
    server = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    server.bind(str(sock))
    server.close()  # bound-then-closed leaves a refusing socket file
    lock = short_socket_dir / "X0-lock"
    BrowserRunner._clear_stale_x11_state(lock, sock)
    assert not sock.exists()


def test_x11_socket_without_lock_and_live_server_is_kept(
    short_socket_dir: Path,
) -> None:
    """A14/f012: no lock file but a live server accepts connections — the
    socket must be kept and the conflict reported, never deleted."""
    import socket as _socket

    from cbrowser.runtime_agent.runner import BrowserRunner

    sock = short_socket_dir / "X0"
    server = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    server.bind(str(sock))
    server.listen(1)
    lock = short_socket_dir / "X0-lock"
    try:
        with pytest.raises(RuntimeError):
            BrowserRunner._clear_stale_x11_state(lock, sock)
        assert sock.exists()
    finally:
        server.close()


@pytest.mark.asyncio
async def test_rearm_id_allocation_is_shared_with_send_command(
    tmp_path: Path, monkeypatch
) -> None:
    """A3/f008: command IDs come from one allocator, so the reconnect
    rearm can never collide with a concurrent send_command."""
    _inject_clock(monkeypatch)

    async def answering(connection):
        async for raw in connection:
            message = json.loads(raw)
            if "id" in message:
                await connection.send(json.dumps({"id": message["id"], "result": {}}))

    async with websockets.serve(answering, "127.0.0.1", 0) as server:
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
            first = manager._allocate_cmd_id()
            resp = await manager.send_command("Browser.getVersion")
            assert resp["result"] == {}
            second = manager._allocate_cmd_id()
            assert len({first, second}) == 2
            assert second > first
        finally:
            await manager.close()
