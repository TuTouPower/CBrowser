"""A36: control_server CDP WebSocket tunnel connects over the bounded UDS root."""

from __future__ import annotations

import secrets
import shutil
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from cbrowser.runtime_agent import socket_root as sr
from cbrowser.supervisor.control_server import create_control_app
from cbrowser.supervisor.core import ActiveSession, SupervisorCore
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator

PROFILE = "prof_a36_ws"
INSTANCE = "inst_a36_ws"


@pytest.fixture
def short_root():
    root = Path(tempfile.mkdtemp(prefix="a36ws-", dir="/tmp")).resolve()
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _upstream_app() -> FastAPI:
    app = FastAPI()

    @app.websocket("/cdp")
    async def cdp(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                msg = await ws.receive_text()
                await ws.send_text("echo:" + msg)
        except Exception:
            pass

    return app


@contextmanager
def _uds_server(sock: Path):
    config = uvicorn.Config(
        _upstream_app(), uds=str(sock), log_level="error", lifespan="off"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not sock.is_socket() and time.monotonic() < deadline:
        time.sleep(0.02)
    if not sock.is_socket():
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("UDS CDP server did not bind")
    try:
        yield server
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.unlink(missing_ok=True)


def _build(socket_root: Path):
    validator = PathValidator(socket_root / "data", socket_root=socket_root)
    docker = SimpleNamespace(
        validator=validator,
        client=SimpleNamespace(containers=SimpleNamespace(get=lambda name: None)),
    )
    core = SupervisorCore(
        docker_adapter=docker,
        port_allocator=PortAllocator(),
        event_forwarder=MagicMock(spec=EventForwarder),
        api_client=AsyncMock(spec=httpx.AsyncClient),
    )
    core.socket_root = socket_root
    token = secrets.token_urlsafe(32)
    token_file = socket_root / "supervisor_token"
    token_file.write_text(token, encoding="utf-8")
    token_file.chmod(0o600)
    app = create_control_app(core, token_file)
    core._sessions[PROFILE] = ActiveSession(
        profile_id=PROFILE,
        runtime_instance_id=INSTANCE,
        config_version=1,
        udp_mux_port=30001,
        browser_container_id="b_a36",
        stream_container_id="s_a36",
        observed_state="running",
    )
    return app, token


def test_cdp_websocket_proxy_uses_new_root_uds(short_root: Path) -> None:
    socket_root = short_root / "socks"
    sr.prepare_socket_dir(socket_root, PROFILE, INSTANCE)
    sock = sr.agent_socket_path(socket_root, PROFILE, INSTANCE)
    app, token = _build(socket_root)
    with _uds_server(sock):
        with TestClient(app) as client:
            with client.websocket_connect(
                f"/supervisor/v1/profiles/{PROFILE}/cdp",
                headers={"Authorization": f"Bearer {token}"},
            ) as ws:
                ws.send_text("a36")
                assert ws.receive_text() == "echo:a36"


def test_cdp_websocket_closes_without_new_root_socket(short_root: Path) -> None:
    socket_root = short_root / "socks"
    app, token = _build(socket_root)
    with TestClient(app) as client:
        with pytest.raises(Exception):
            with client.websocket_connect(
                f"/supervisor/v1/profiles/{PROFILE}/cdp",
                headers={"Authorization": f"Bearer {token}"},
            ) as ws:
                ws.receive_text()
