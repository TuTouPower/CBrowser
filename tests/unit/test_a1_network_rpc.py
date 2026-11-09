"""A1: network RPC client and authentication wiring.

The production app injects the RuntimeCoordinator into
NetworkService.supervisor_client. These tests drive the real coordinator
RPC methods (never replaced or mocked) against a controlled local HTTP
Supervisor, and the formally assembled NetworkService chain.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api_auth import create_auth_context
from cbrowser.adapters.database.models import Base
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.api.app import create_app
from cbrowser.api.runtime_coordinator import RuntimeCoordinator
from cbrowser.domain.models import NetworkAccessConfig, NetworkApplyPhase
from cbrowser.services.network_service import NetworkService
from cbrowser.supervisor.protocol import ConvergeStreamsRequest, RebuildEdgeRequest


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode() or "{}")
        except ValueError:
            body = {}
        sup = self.server.sup
        sup.requests.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "body": body,
            }
        )
        plan = sup.plans.pop(0) if sup.plans else {"status": 200, "body": {"status": "ok", "rebuilt": True}}
        if sup.expected_token is not None:
            expected = f"Bearer {sup.expected_token}"
            if self.headers.get("Authorization") != expected:
                plan = {"status": 401, "body": {"detail": "invalid bearer"}}
        if plan.get("delay"):
            time.sleep(plan["delay"])
        if plan.get("drop"):
            try:
                self.connection.close()
            except OSError:
                pass
            return
        payload = json.dumps(plan.get("body", {})).encode()
        try:
            self.send_response(plan.get("status", 200))
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *args):
        pass


class _ControlledSupervisor:
    def __init__(self, expected_token: str | None):
        self.expected_token = expected_token
        self.requests: list[dict] = []
        self.plans: list[dict] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.sup = self
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> "_ControlledSupervisor":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


@pytest.fixture
def supervisor_token() -> str:
    return secrets.token_urlsafe(32)


def _coordinator(url: str, token: str, **kwargs) -> RuntimeCoordinator:
    return RuntimeCoordinator(
        supervisor_url=url,
        supervisor_token=SecretStr(token),
        profile_service=MagicMock(),
        **kwargs,
    )


@pytest_asyncio.fixture
async def network_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield ProfileRepository(maker), maker
    await engine.dispose()


def _auth_stub() -> MagicMock:
    auth = MagicMock()
    auth.verify_admin_password = AsyncMock(return_value=True)
    return auth


async def _run_apply(
    coordinator: RuntimeCoordinator, repo: ProfileRepository, tmp_path: Path
) -> object:
    svc = NetworkService(
        repo=repo,
        auth_service=_auth_stub(),
        supervisor_client=coordinator,
        export_dir=tmp_path / "network",
    )
    await svc.update_pending_config(
        NetworkAccessConfig(lan_access_enabled=True, lan_advertised_ip="192.168.31.76")
    )
    op = await svc.apply_configuration("password")
    return await svc.wait_for_operation(op.operation_id, timeout=5.0)


@pytest.mark.asyncio
async def test_rebuild_edge_uses_shared_client_with_auth_and_exact_model(
    supervisor_token,
):
    sup = _ControlledSupervisor(supervisor_token).start()
    coord = _coordinator(sup.url, supervisor_token)
    try:
        assert coord.is_enabled() is True
        result = await coord.rebuild_edge(
            target_version=7,
            bind_host="0.0.0.0",
            https_port=56661,
            caddyfile_path="Caddyfile.staging.op",
        )
        assert result == {"status": "ok", "rebuilt": True}
        assert len(sup.requests) == 1
        req = sup.requests[0]
        assert req["path"] == "/supervisor/v1/network/rebuild-edge"
        assert req["authorization"] == f"Bearer {supervisor_token}"
        RebuildEdgeRequest.model_validate(req["body"])
        assert req["body"] == {
            "target_version": 7,
            "bind_host": "0.0.0.0",
            "https_port": 56661,
            "caddyfile_path": "Caddyfile.staging.op",
        }
        assert not hasattr(coord, "client")
        assert coord._client is not None
    finally:
        await coord.stop()
        sup.stop()


@pytest.mark.asyncio
async def test_converge_network_streams_uses_shared_client_with_auth_and_exact_model(
    supervisor_token,
):
    sup = _ControlledSupervisor(supervisor_token).start()
    coord = _coordinator(sup.url, supervisor_token)
    try:
        result = await coord.converge_network_streams(
            target_version=7, bind_host="0.0.0.0", advertised_ip="192.168.31.76"
        )
        assert result == {"status": "ok", "rebuilt": True}
        assert len(sup.requests) == 1
        req = sup.requests[0]
        assert req["path"] == "/supervisor/v1/network/converge-streams"
        assert req["authorization"] == f"Bearer {supervisor_token}"
        ConvergeStreamsRequest.model_validate(req["body"])
        assert req["body"] == {
            "target_version": 7,
            "bind_host": "0.0.0.0",
            "advertised_ip": "192.168.31.76",
        }
        assert not hasattr(coord, "client")
        assert coord._client is not None
    finally:
        await coord.stop()
        sup.stop()


@pytest.mark.asyncio
async def test_disabled_coordinator_does_not_emit_http(supervisor_token):
    sup = _ControlledSupervisor(supervisor_token).start()
    coord = _coordinator(None, supervisor_token)
    try:
        assert coord.is_enabled() is False
        edge = await coord.rebuild_edge(
            target_version=1,
            bind_host="127.0.0.1",
            https_port=443,
            caddyfile_path="Caddyfile.staging.x",
        )
        streams = await coord.converge_network_streams(
            target_version=1, bind_host="127.0.0.1", advertised_ip="127.0.0.1"
        )
        assert edge == {"status": "ok", "mock": True, "rebuilt": True}
        assert streams == {"status": "ok", "rebuilt_streams": 0}
        assert sup.requests == []
    finally:
        await coord.stop()
        sup.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("plan", [
    {"status": 401, "body": {"detail": "unauthorized"}},
    {"status": 500, "body": {"detail": "boom"}},
    {"delay": 0.4, "status": 200, "body": {"status": "ok"}},
])
async def test_rpc_http_failures_propagate_to_apply_failed(
    supervisor_token, network_db, tmp_path, plan
):
    sup = _ControlledSupervisor(supervisor_token).start()
    sup.plans = [plan]
    coord = _coordinator(sup.url, supervisor_token)
    coord._client = httpx.AsyncClient(timeout=0.1, trust_env=False)
    repo, _ = network_db
    try:
        op = await _run_apply(coord, repo, tmp_path)
        assert op.phase == NetworkApplyPhase.FAILED
        assert op.error_reason
        assert "AttributeError" not in op.error_reason
        settings = await repo.get_network_access_settings()
        assert settings.applied_version.version == 1
        assert len(sup.requests) >= 1
    finally:
        await coord.stop()
        sup.stop()


@pytest.mark.asyncio
async def test_formal_app_network_apply_reaches_controlled_supervisor(
    supervisor_token, tmp_path
):
    sup = _ControlledSupervisor(supervisor_token).start()
    ctx = create_auth_context(tmp_path)
    token_file = tmp_path / "supervisor_token.txt"
    token_file.write_text(supervisor_token, encoding="utf-8")
    token_file.chmod(0o600)
    app = create_app(
        db_path=tmp_path / "a1.db",
        admin_password_file=ctx.admin_password_file,
        artifacts_root=tmp_path / "artifacts",
        supervisor_url=sup.url,
        supervisor_token_file=token_file,
    )
    try:
        with TestClient(app, base_url=ctx.allowed_origin) as client:
            login = client.post(
                "/api/v1/auth/login", json={"password": ctx.admin_password}
            )
            assert login.status_code == 200
            csrf = login.json()["csrf_token"]
            headers = {
                "X-CSRF-Token": csrf,
                "Origin": ctx.allowed_origin,
            }
            pending = client.put(
                "/api/v1/network/settings",
                json={"lan_access_enabled": True, "lan_advertised_ip": "192.168.31.76"},
                headers=headers,
            )
            assert pending.status_code == 200
            apply_resp = client.post(
                "/api/v1/network/apply",
                json={"admin_password": ctx.admin_password},
                headers=headers,
            )
            assert apply_resp.status_code == 202
            op_id = apply_resp.json()["operation_id"]
            terminal = None
            for _ in range(100):
                op_resp = client.get(f"/api/v1/network/operations/{op_id}")
                assert op_resp.status_code == 200
                terminal = op_resp.json()
                if terminal["phase"] in ("completed", "failed"):
                    break
                time.sleep(0.05)
            assert terminal["phase"] == "completed", terminal
            assert len(sup.requests) == 2
            assert sup.requests[0]["path"] == "/supervisor/v1/network/rebuild-edge"
            assert sup.requests[1]["path"] == "/supervisor/v1/network/converge-streams"
            assert all(
                r["authorization"] == f"Bearer {supervisor_token}"
                for r in sup.requests
            )
            RebuildEdgeRequest.model_validate(sup.requests[0]["body"])
            ConvergeStreamsRequest.model_validate(sup.requests[1]["body"])
    finally:
        sup.stop()
