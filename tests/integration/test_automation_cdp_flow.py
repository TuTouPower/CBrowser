"""End-to-end API -> Supervisor control -> Agent UDS WebSocket forwarding."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import tempfile
import shutil
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import uvicorn
import websockets
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.api.app import create_app
from cbrowser.domain.models import ProfileConfig
from cbrowser.runtime_agent.agent import create_agent_app
from cbrowser.supervisor.control_server import create_control_app
from cbrowser.supervisor.path_validator import PathValidator
from fastapi.testclient import TestClient


def _free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _UvicornThread:
    def __init__(self, app, port: int):
        self.server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self):
        self.thread.start()
        for _ in range(100):
            if self.server.started:
                return
            time.sleep(0.05)
        raise RuntimeError("uvicorn did not start")

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=10)


class _UnixEchoServer:
    def __init__(self, path: Path):
        self.path = path
        self.ready = threading.Event()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    async def _handler(self, websocket):
        async for message in websocket:
            await websocket.send(message)

    async def _serve(self):
        async with websockets.unix_serve(self._handler, self.path):
            self.ready.set()
            await asyncio.to_thread(self.stop.wait)

    def _run(self):
        asyncio.run(self._serve())

    def start(self):
        self.thread.start()
        assert self.ready.wait(5)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=5)


@pytest.mark.asyncio
async def test_automation_token_reaches_agent_uds_through_supervisor() -> None:
    short = Path(tempfile.mkdtemp(prefix="cbrowser-t008-uds-", dir="/tmp"))
    shutil.rmtree(short, ignore_errors=True)
    log_path = short / "supervisor.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    supervisor_log = logging.getLogger("cbrowser.supervisor.control_server")
    supervisor_log.setLevel(logging.DEBUG)
    supervisor_log.addHandler(logging.FileHandler(log_path))
    root = short / "data"
    root.mkdir(parents=True)
    supervisor_token = secrets.token_urlsafe(32)
    supervisor_token_file = short / "supervisor_token"
    supervisor_token_file.write_text(supervisor_token, encoding="utf-8")
    supervisor_token_file.chmod(0o600)
    supervisor_port = _free_port()

    db_file = short / "api.db"
    run_database_migrations(db_file)
    engine, session_maker = create_engine_and_maker(db_file)
    await ProfileRepository(session_maker).create_profile(
        ProfileConfig(name="p1", fingerprint_seed=1), profile_id="p1"
    )
    await engine.dispose()
    profile_id = "p1"

    admin_password = secrets.token_urlsafe(32)
    admin_file = short / "admin"
    admin_file.write_text(admin_password, encoding="utf-8")
    admin_file.chmod(0o600)
    origin = "http://127.0.0.1"
    api = _UvicornThread(
        create_app(
            db_path=db_file,
            admin_password_file=admin_file,
            allowed_origins=[origin],
            artifacts_root=short / "artifacts",
            supervisor_url=f"http://127.0.0.1:{supervisor_port}",
            supervisor_token_file=supervisor_token_file,
        ),
        _free_port(),
    )
    api_port = api.server.config.port
    api.start()
    supervisor = None
    echo = None

    try:
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{api_port}",
            timeout=10.0,
            trust_env=False,
        ) as client:
            login = await client.post(
                "/api/v1/auth/login", json={"password": admin_password}
            )
            login.raise_for_status()
            csrf = login.json()["csrf_token"]
            session = login.cookies.get("cbrowser_session")
            headers = {
                "X-CSRF-Token": csrf,
                "Origin": origin,
                "Cookie": f"cbrowser_session={session}",
            }
            profile = await client.get(
                f"/api/v1/profiles/{profile_id}", headers=headers
            )
            profile.raise_for_status()
            token_response = await client.post(
                "/api/v1/automation/tokens",
                json={"name": "bot", "profile_ids": [profile_id]},
                headers=headers,
            )
            token_response.raise_for_status()
            raw_token = token_response.json()["token"]

        runtime = root / "runtime" / profile_id
        runtime.mkdir(parents=True)
        echo = _UnixEchoServer(runtime / "agent.sock")
        echo.start()
        core = SimpleNamespace(
            _token_file=supervisor_token_file,
            _sessions={
                profile_id: SimpleNamespace(
                    runtime_instance_id="i1", observed_state="running"
                )
            },
            docker=SimpleNamespace(validator=PathValidator(root)),
        )
        supervisor = _UvicornThread(
            create_control_app(core, supervisor_token_file), supervisor_port
        )
        supervisor.start()

        websocket = await asyncio.wait_for(
            websockets.connect(
                f"ws://127.0.0.1:{api_port}/api/v1/automation/profiles/"
                f"{profile_id}/cdp",
                additional_headers=[("Authorization", f"Bearer {raw_token}")],
                proxy=None,
            ),
            timeout=10,
        )
        async with websocket:
            await websocket.send("CDP-PING")
            try:
                assert await asyncio.wait_for(websocket.recv(), timeout=5) == "CDP-PING"
            except Exception as exc:  # noqa: BLE001
                raise AssertionError(log_path.read_text(encoding="utf-8")) from exc
    finally:
        api.stop()
        if supervisor is not None:
            supervisor.stop()
        if echo is not None:
            echo.close()
        shutil.rmtree(short, ignore_errors=True)


class _TcpChromeServer:
    def __init__(self, port: int):
        self.port = port
        self.ready = threading.Event()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    async def _handler(self, websocket):
        async for message in websocket:
            request = json.loads(message)
            await websocket.send(
                json.dumps(
                    {
                        "id": request.get("id"),
                        "result": {"product": "Chrome/123.0 E2E"},
                    }
                )
            )

    async def _serve(self):
        async with websockets.serve(self._handler, "127.0.0.1", self.port):
            self.ready.set()
            await asyncio.to_thread(self.stop.wait)

    def _run(self):
        asyncio.run(self._serve())

    def start(self):
        self.thread.start()
        assert self.ready.wait(5)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=5)


def test_supervisor_cdp_reaches_real_agent_app_and_fake_chrome() -> None:
    """Supervisor control WS -> real Agent app -> Chrome loopback WebSocket."""
    import secrets

    short = Path(tempfile.mkdtemp(prefix="cbrowser-t008-agent-", dir="/tmp"))
    data_root = short / "data"
    run_dir = data_root / "runtime" / "p1"
    run_dir.mkdir(parents=True)
    events_dir = data_root / "runtime-events" / "p1"
    events_dir.mkdir(parents=True)

    chrome_port = _free_port()
    chrome = _TcpChromeServer(chrome_port)
    chrome.start()
    runner_info = {
        "profile_id": "p1",
        "runtime_instance_id": "i1",
        "config_version": 1,
        "cdp_port": chrome_port,
        "browser_ws_url": f"ws://127.0.0.1:{chrome_port}",
        "browser_pid": 123,
        "runner_pid": 123,
    }
    (run_dir / "runner_info.json").write_text(json.dumps(runner_info), encoding="utf-8")

    agent_sock = run_dir / "agent.sock"
    agent_app = create_agent_app(
        run_dir=run_dir,
        default_download_dir=data_root / "downloads",
        events_dir=events_dir,
        cdp_proxy=None,
    )
    agent_server = uvicorn.Server(
        uvicorn.Config(agent_app, uds=str(agent_sock), log_level="warning")
    )
    agent_thread = threading.Thread(target=agent_server.run, daemon=True)

    token = secrets.token_urlsafe(32)
    token_file = short / "supervisor.token"
    token_file.write_text(token, encoding="utf-8")
    token_file.chmod(0o600)
    core = SimpleNamespace(
        _sessions={
            "p1": SimpleNamespace(runtime_instance_id="i1", observed_state="running")
        },
        docker=SimpleNamespace(validator=PathValidator(data_root)),
    )
    control_app = create_control_app(core, token_file)

    try:
        agent_thread.start()
        for _ in range(100):
            if agent_sock.is_socket():
                break
            time.sleep(0.05)
        else:
            raise RuntimeError("Agent UDS did not start")

        with TestClient(control_app, base_url="http://supervisor") as client:
            with client.websocket_connect(
                "/supervisor/v1/profiles/p1/cdp",
                headers={"Authorization": f"Bearer {token}"},
            ) as websocket:
                websocket.send_text('{"id":1,"method":"Browser.getVersion"}')
                response = json.loads(websocket.receive_text())
                assert response["id"] == 1
                assert response["result"]["product"] == "Chrome/123.0 E2E"
    finally:
        agent_server.should_exit = True
        agent_thread.join(timeout=10)
        chrome.close()
        shutil.rmtree(short, ignore_errors=True)
