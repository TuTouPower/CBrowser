"""Automation endpoint authorization and Supervisor UDS CDP forwarding."""

from __future__ import annotations

import asyncio
import secrets
import shutil
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
import websockets
from cbrowser.supervisor.control_server import create_control_app
from cbrowser.supervisor.path_validator import PathValidator
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


class _UnixEchoServer:
    def __init__(self, path: Path):
        self.path = path
        self.ready = threading.Event()
        self.stop = threading.Event()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    async def _handler(self, websocket):
        async for message in websocket:
            await websocket.send(message)

    async def _serve(self):
        async with websockets.unix_serve(self._handler, self.path):
            self.ready.set()
            await asyncio.to_thread(self.stop.wait)

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._serve())
        finally:
            self.loop.close()

    def start(self):
        self.thread.start()
        assert self.ready.wait(5)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=5)


def _short_root(tmp_path: Path) -> Path:
    # AF_UNIX paths are capped near 104 bytes; pytest tmp paths exceed it here.
    root = Path(".scratch/t008_uds") / tmp_path.name[-8:] / "data"
    shutil.rmtree(root.parent, ignore_errors=True)
    return root


def test_supervisor_cdp_websocket_forwards_to_agent_uds(tmp_path: Path) -> None:
    root = _short_root(tmp_path)
    runtime = root / "runtime" / "p1"
    runtime.mkdir(parents=True)
    sock = runtime / "agent.sock"
    server = _UnixEchoServer(sock)
    server.start()
    token = secrets.token_urlsafe(32)
    token_file = root.parent / "token"
    token_file.write_text(token, encoding="utf-8")
    token_file.chmod(0o600)

    core = SimpleNamespace(
        _token_file=token_file,
        _sessions={
            "p1": SimpleNamespace(runtime_instance_id="i1", observed_state="running")
        },
        docker=SimpleNamespace(validator=PathValidator(root)),
    )
    app = create_control_app(core=core, token_file=token_file)
    try:
        with TestClient(app, base_url="http://supervisor") as client:
            with client.websocket_connect(
                "/supervisor/v1/profiles/p1/cdp",
                headers={"Authorization": f"bearer {token}"},
            ) as websocket:
                websocket.send_text('{"id":1,"method":"Browser.getVersion"}')
                assert websocket.receive_text() == (
                    '{"id":1,"method":"Browser.getVersion"}'
                )
    finally:
        server.close()


def test_supervisor_cdp_rejects_missing_or_foreign_token(tmp_path: Path) -> None:
    root = _short_root(tmp_path)
    (root / "runtime" / "p1").mkdir(parents=True)
    token = secrets.token_urlsafe(32)
    token_file = root.parent / "token"
    token_file.write_text(token, encoding="utf-8")
    token_file.chmod(0o600)
    core = SimpleNamespace(
        _token_file=token_file,
        _sessions={},
        docker=SimpleNamespace(validator=PathValidator(root)),
    )
    app = create_control_app(core=core, token_file=token_file)
    with TestClient(app, base_url="http://supervisor") as client:
        for auth in (None, f"Bearer {secrets.token_urlsafe(32)}"):
            headers = {"Authorization": auth} if auth else {}
            with client.websocket_connect(
                "/supervisor/v1/profiles/p1/cdp", headers=headers
            ) as websocket:
                with pytest.raises(WebSocketDisconnect) as close:
                    websocket.receive_text()
            assert close.value.code == 4401
