"""A42: automation tunnel registration keeps the authenticated token_id subject."""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import socket
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import websockets
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.websockets import WebSocketDisconnect

from api_auth import create_auth_context
from cbrowser.api.app import create_app
from cbrowser.api.v1.automation_router import automation_router
from cbrowser.services.tunnel_registry import AutomationTunnelRegistry


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _SupervisorWs:
    def __init__(self, port: int):
        self.port = port
        self.ready = threading.Event()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    async def _handler(self, websocket):
        async for message in websocket:
            await websocket.send(message)

    async def _serve(self):
        async with websockets.serve(self._handler, "127.0.0.1", self.port):
            self.ready.set()
            await asyncio.to_thread(self.stop.wait)

    def _run(self):
        asyncio.run(self._serve())

    def start(self) -> "_SupervisorWs":
        self.thread.start()
        assert self.ready.wait(5)
        return self

    def close(self) -> None:
        self.stop.set()
        self.thread.join(timeout=5)


@pytest.fixture
def supervisor_ws():
    server = _SupervisorWs(_free_port()).start()
    yield server
    server.close()


@pytest.fixture
def live_app(tmp_path: Path, supervisor_ws):
    ctx = create_auth_context(tmp_path)
    token = secrets.token_urlsafe(32)
    token_file = tmp_path / "supervisor_token.txt"
    token_file.write_text(token, encoding="utf-8")
    token_file.chmod(0o600)
    gateway_file = tmp_path / "gateway_token.txt"
    gateway_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    gateway_file.chmod(0o600)
    app = create_app(
        db_path=tmp_path / "a42.db",
        admin_password_file=ctx.admin_password_file,
        artifacts_root=tmp_path / "artifacts",
        supervisor_url=f"http://127.0.0.1:{supervisor_ws.port}",
        supervisor_token_file=token_file,
        gateway_token_file=gateway_file,
    )
    return app, ctx, token


def _login(client: TestClient, ctx) -> dict[str, str]:
    login = client.post("/api/v1/auth/login", json={"password": ctx.admin_password})
    assert login.status_code == 200
    return {
        "X-CSRF-Token": login.json()["csrf_token"],
        "Origin": ctx.allowed_origin,
    }


def _make_profile(client: TestClient, headers, name: str) -> str:
    resp = client.post("/api/v1/profiles", json={"name": name}, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


def _make_token(client: TestClient, headers, name: str, profile_ids) -> dict:
    resp = client.post(
        "/api/v1/automation/tokens",
        json={"name": name, "profile_ids": profile_ids},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()


def _wait_for(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_tunnel_records_authenticated_token_id(live_app) -> None:
    app, ctx, _ = live_app
    with TestClient(app, base_url=ctx.allowed_origin) as client:
        headers = _login(client, ctx)
        pid = _make_profile(client, headers, "p1")
        token = _make_token(client, headers, "bot", [pid])
        registry = app.state.automation_tunnels
        with client.websocket_connect(
            f"/api/v1/automation/profiles/{pid}/cdp",
            headers={"Authorization": f"Bearer {token['token']}"},
        ):
            assert _wait_for(lambda: len(registry.list_for_profile(pid)) == 1)
            records = registry.list_for_profile(pid)
            assert len(records) == 1
            record = records[0]
            assert record.agent_instance_id == token["id"]
            assert record.agent_session_id is None
            control = client.get(f"/api/v1/profiles/{pid}/control").json()
            assert control["agent_instance_id"] == token["id"]
            assert record.generation == control["generation"]
            data = json.dumps(record.to_data())
            assert token["token"] not in data
            assert hashlib.sha256(token["token"].encode()).hexdigest() not in data
            assert ctx.admin_password not in data


def test_two_tokens_and_multiple_profiles_keep_identity(live_app) -> None:
    app, ctx, _ = live_app
    with TestClient(app, base_url=ctx.allowed_origin) as client:
        headers = _login(client, ctx)
        p1 = _make_profile(client, headers, "p1")
        p2 = _make_profile(client, headers, "p2")
        token_a = _make_token(client, headers, "bot-a", [p1, p2])
        token_b = _make_token(client, headers, "bot-b", [p1, p2])
        registry = app.state.automation_tunnels
        with client.websocket_connect(
            f"/api/v1/automation/profiles/{p1}/cdp",
            headers={"Authorization": f"Bearer {token_a['token']}"},
        ):
            assert _wait_for(lambda: len(registry.list_for_profile(p1)) == 1)
            assert registry.list_for_profile(p1)[0].agent_instance_id == token_a["id"]
            with pytest.raises(WebSocketDisconnect) as second:
                with client.websocket_connect(
                    f"/api/v1/automation/profiles/{p1}/cdp",
                    headers={"Authorization": f"Bearer {token_b['token']}"},
                ):
                    pass
            assert second.value.code == 4403
            assert len(registry.list_for_profile(p1)) == 1
            with client.websocket_connect(
                f"/api/v1/automation/profiles/{p2}/cdp",
                headers={"Authorization": f"Bearer {token_a['token']}"},
            ):
                assert _wait_for(lambda: len(registry.list_for_profile(p2)) == 1)
                assert registry.list_for_profile(p2)[0].agent_instance_id == token_a["id"]
                assert registry.list_for_profile(p2)[0].agent_session_id is None


def test_handoff_closes_and_clears_registered_tunnel(live_app) -> None:
    app, ctx, _ = live_app
    with TestClient(app, base_url=ctx.allowed_origin) as client:
        headers = _login(client, ctx)
        pid = _make_profile(client, headers, "p1")
        token = _make_token(client, headers, "bot", [pid])
        registry = app.state.automation_tunnels
        with client.websocket_connect(
            f"/api/v1/automation/profiles/{pid}/cdp",
            headers={"Authorization": f"Bearer {token['token']}"},
        ) as ws:
            assert _wait_for(lambda: len(registry.list_for_profile(pid)) == 1)
            handoff = client.post(
                f"/api/v1/profiles/{pid}/control/handoff",
                json={"reason": "cli_handoff"},
                headers={"Authorization": f"Bearer {token['token']}"},
            )
            assert handoff.status_code == 200
            assert _wait_for(lambda: len(registry.list_for_profile(pid)) == 0)
            with pytest.raises(WebSocketDisconnect):
                ws.receive_text()


def test_takeover_closes_tunnel_and_keeps_identity_consistent(live_app) -> None:
    app, ctx, _ = live_app
    with TestClient(app, base_url=ctx.allowed_origin) as client:
        headers = _login(client, ctx)
        pid = _make_profile(client, headers, "p1")
        token = _make_token(client, headers, "bot", [pid])
        registry = app.state.automation_tunnels
        gateway_token = app.state.gateway_token.get_secret_value()
        with client.websocket_connect(
            f"/api/v1/automation/profiles/{pid}/cdp",
            headers={"Authorization": f"Bearer {token['token']}"},
        ) as ws:
            assert _wait_for(lambda: len(registry.list_for_profile(pid)) == 1)
            assert registry.list_for_profile(pid)[0].agent_instance_id == token["id"]
            takeover = client.post(
                f"/api/v1/internal/gateway/profiles/{pid}/control/takeover",
                json={"source": "gateway", "conn_id": "conn-1", "input_kind": "key"},
                headers={"Authorization": f"Bearer {gateway_token}"},
            )
            assert takeover.status_code == 200
            assert takeover.json()["owner"] == "user"
            assert _wait_for(lambda: len(registry.list_for_profile(pid)) == 0)
            with pytest.raises(WebSocketDisconnect):
                ws.receive_text()


def test_auth_failure_and_missing_identity_do_not_register(
    live_app, caplog
) -> None:
    app, ctx, _ = live_app
    with TestClient(app, base_url=ctx.allowed_origin) as client:
        headers = _login(client, ctx)
        pid = _make_profile(client, headers, "p1")
        token = _make_token(client, headers, "bot", [pid])
        registry = app.state.automation_tunnels
        for auth in ({}, {"Authorization": "Bearer cbat_wrong"}):
            with pytest.raises(WebSocketDisconnect) as closed:
                with client.websocket_connect(
                    f"/api/v1/automation/profiles/{pid}/cdp", headers=auth
                ):
                    pass
            assert closed.value.code == 4401
        assert registry.list_for_profile(pid) == []
        revoke = client.delete(
            f"/api/v1/automation/tokens/{token['id']}", headers=headers
        )
        assert revoke.status_code == 204
        with pytest.raises(WebSocketDisconnect) as revoked:
            with client.websocket_connect(
                f"/api/v1/automation/profiles/{pid}/cdp",
                headers={"Authorization": f"Bearer {token['token']}"},
            ):
                pass
        assert revoked.value.code == 4401
        assert registry.list_for_profile(pid) == []
        assert token["token"] not in caplog.text
        assert ctx.admin_password not in caplog.text


def test_degraded_path_without_control_service_still_resolves_token_id(
    supervisor_ws,
) -> None:
    token_id = "tid-degraded"
    auth = MagicMock()
    auth.authorize_automation = AsyncMock(return_value=(True, None))
    auth.resolve_automation_token_id = AsyncMock(return_value=token_id)
    coordinator = SimpleNamespace(
        supervisor_url=f"http://127.0.0.1:{supervisor_ws.port}",
        is_enabled=lambda: True,
    )
    app = FastAPI()
    app.state.auth_service = auth
    app.state.coordinator = coordinator
    app.state.supervisor_token = SecretStr(secrets.token_urlsafe(32))
    app.state.automation_tunnels = AutomationTunnelRegistry(layer="api")
    app.state.trusted_proxy_cidrs = []
    app.include_router(automation_router)
    with TestClient(app) as client:
        with client.websocket_connect(
            "/api/v1/automation/profiles/degraded/cdp",
            headers={"Authorization": "Bearer cbat_degraded"},
        ):
            assert _wait_for(
                lambda: len(app.state.automation_tunnels.list_for_profile("degraded")) == 1
            )
            record = app.state.automation_tunnels.list_for_profile("degraded")[0]
            assert record.agent_instance_id == token_id
            assert record.agent_session_id is None
            assert record.generation is None


def test_missing_token_id_even_with_control_service_does_not_register(
    supervisor_ws,
) -> None:
    auth = MagicMock()
    auth.authorize_automation = AsyncMock(return_value=(True, None))
    auth.resolve_automation_token_id = AsyncMock(return_value=None)
    control = MagicMock()
    control.claim = AsyncMock(return_value=(SimpleNamespace(generation=1), False))
    coordinator = SimpleNamespace(
        supervisor_url=f"http://127.0.0.1:{supervisor_ws.port}",
        is_enabled=lambda: True,
    )
    app = FastAPI()
    app.state.auth_service = auth
    app.state.coordinator = coordinator
    app.state.supervisor_token = SecretStr(secrets.token_urlsafe(32))
    app.state.control_service = control
    app.state.automation_tunnels = AutomationTunnelRegistry(layer="api")
    app.state.trusted_proxy_cidrs = []
    app.include_router(automation_router)
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as closed:
            with client.websocket_connect(
                "/api/v1/automation/profiles/missing/cdp",
                headers={"Authorization": "Bearer cbat_missing"},
            ):
                pass
        assert closed.value.code == 4401
        control.claim.assert_not_awaited()
        assert app.state.automation_tunnels.list_for_profile("missing") == []
