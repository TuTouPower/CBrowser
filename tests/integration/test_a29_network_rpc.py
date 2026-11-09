"""A29: real Coordinator -> Supervisor RPC integration coverage.

Keeps the existing SQLite NetworkService tests intact and adds production
RuntimeCoordinator RPC execution against a controlled local HTTP
Supervisor. The RPC methods themselves are never replaced or mocked.
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
        if sup.expected_token is not None and self.headers.get("Authorization") != (
            f"Bearer {sup.expected_token}"
        ):
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


def _coordinator(url: str, token: str) -> RuntimeCoordinator:
    return RuntimeCoordinator(
        supervisor_url=url,
        supervisor_token=SecretStr(token),
        profile_service=MagicMock(),
    )


@pytest_asyncio.fixture
async def network_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield ProfileRepository(maker)
    await engine.dispose()


@pytest.mark.asyncio
async def test_direct_rpc_exercises_real_client_url_auth_and_model(supervisor_token):
    sup = _ControlledSupervisor(supervisor_token).start()
    coord = _coordinator(sup.url, supervisor_token)
    try:
        assert coord.is_enabled()
        assert not hasattr(coord, "client")
        edge = await coord.rebuild_edge(
            target_version=4,
            bind_host="127.0.0.1",
            https_port=443,
            caddyfile_path="Caddyfile.staging.4",
        )
        streams = await coord.converge_network_streams(
            target_version=4, bind_host="127.0.0.1", advertised_ip="127.0.0.1"
        )
        assert edge == {"status": "ok", "rebuilt": True}
        assert streams == {"status": "ok", "rebuilt": True}
        assert coord._client is not None
        assert len(sup.requests) == 2
        edge_req, stream_req = sup.requests
        assert edge_req["path"] == "/supervisor/v1/network/rebuild-edge"
        assert stream_req["path"] == "/supervisor/v1/network/converge-streams"
        assert edge_req["authorization"] == f"Bearer {supervisor_token}"
        assert stream_req["authorization"] == f"Bearer {supervisor_token}"
        assert RebuildEdgeRequest.model_validate(edge_req["body"]).target_version == 4
        assert ConvergeStreamsRequest.model_validate(stream_req["body"]).target_version == 4
    finally:
        await coord.stop()
        sup.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "plan",
    [
        {"status": 401, "body": {"detail": "unauthorized"}},
        {"status": 503, "body": {"detail": "unavailable"}},
        {"drop": True},
    ],
)
async def test_http_errors_fail_operation_not_mock_success(
    supervisor_token, network_db, tmp_path: Path, plan
):
    sup = _ControlledSupervisor(supervisor_token).start()
    sup.plans = [plan]
    coord = _coordinator(sup.url, supervisor_token)
    repo = network_db
    auth = MagicMock()
    auth.verify_admin_password = AsyncMock(return_value=True)
    svc = NetworkService(
        repo=repo,
        auth_service=auth,
        supervisor_client=coord,
        export_dir=tmp_path / "network",
    )
    try:
        await svc.update_pending_config(
            NetworkAccessConfig(lan_access_enabled=True, lan_advertised_ip="192.168.31.76")
        )
        op = await svc.apply_configuration("password")
        final = await svc.wait_for_operation(op.operation_id, timeout=5.0)
        assert final.phase == NetworkApplyPhase.FAILED
        assert final.error_reason is not None
        assert "AttributeError" not in final.error_reason
        assert final.phase != NetworkApplyPhase.COMPLETED
        settings = await repo.get_network_access_settings()
        assert settings.applied_version.version == 1
    finally:
        await coord.stop()
        sup.stop()


@pytest.mark.asyncio
async def test_formal_app_route_reaches_real_coordinator_rpc(
    supervisor_token, tmp_path: Path
):
    sup = _ControlledSupervisor(supervisor_token).start()
    ctx = create_auth_context(tmp_path)
    token_file = tmp_path / "supervisor_token.txt"
    token_file.write_text(supervisor_token, encoding="utf-8")
    token_file.chmod(0o600)
    app = create_app(
        db_path=tmp_path / "a29.db",
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
            headers = {
                "X-CSRF-Token": login.json()["csrf_token"],
                "Origin": ctx.allowed_origin,
            }
            assert client.get("/network/apply").status_code == 404
            assert client.post("/network/apply", json={}, headers=headers).status_code == 404
            resp = client.post(
                "/api/v1/network/apply",
                json={"admin_password": ctx.admin_password},
                headers=headers,
            )
            assert resp.status_code == 202
            terminal = None
            for _ in range(100):
                op = client.get(
                    f"/api/v1/network/operations/{resp.json()['operation_id']}"
                ).json()
                if op["phase"] in ("completed", "failed"):
                    terminal = op
                    break
                time.sleep(0.05)
            assert terminal["phase"] == "completed", terminal
            assert len(sup.requests) == 2
    finally:
        sup.stop()
