"""t026 AC-009/AC-010: Supervisor control plane additions.

reconcile/readiness/transport ride the existing authenticated control
API — no new port, no proxy route — and readiness exits through the
same JSON the host-side CLI consumes.
"""

import secrets
from pathlib import Path

import httpx
import pytest
from cbrowser.supervisor.control_server import create_control_app
from cbrowser.supervisor.protocol import (
    ReadinessResponse,
    ReconcileAllResponse,
    TransportObservation,
)


class _StubCore:
    def __init__(self) -> None:
        self.reconcile_calls = 0

    def get_transport_observation(self, profile_id: str) -> TransportObservation:
        return TransportObservation(
            profile_id=profile_id,
            runtime_instance_id="inst_1",
            browser_state="running",
            stream_state="running",
            transport_state="recovering",
            gateway_endpoint="10.251.7.254",
            last_error="gateway_missing",
        )

    async def reconcile_all(self) -> ReconcileAllResponse:
        self.reconcile_calls += 1
        return ReconcileAllResponse(scanned=2, profiles=["p1", "p2"])

    async def readiness(self) -> ReadinessResponse:
        return ReadinessResponse(ready=False, reason="api_unavailable:ConnectError")


@pytest.fixture
def _app(tmp_path: Path):
    key = tmp_path / "control_key"
    key.write_text(secrets.token_urlsafe(32))
    key.chmod(0o600)
    core = _StubCore()
    app = create_control_app(core, key)
    return app, core, key.read_text()


@pytest.mark.asyncio
async def test_new_endpoints_require_control_auth(_app):
    app, _core, _token = _app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://supervisor"
    ) as client:
        for method, path in (
            ("GET", "/supervisor/v1/readiness"),
            ("POST", "/supervisor/v1/reconcile"),
            ("GET", "/supervisor/v1/profiles/p1/transport"),
        ):
            response = await client.request(method, path)
            assert response.status_code == 401, path


@pytest.mark.asyncio
async def test_transport_reconcile_readiness_round_trip(_app):
    app, core, token = _app
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://supervisor",
        headers=headers,
    ) as client:
        transport = await client.get("/supervisor/v1/profiles/p1/transport")
        assert transport.status_code == 200
        body = transport.json()
        assert body["runtime_instance_id"] == "inst_1"
        assert body["transport"]["transport_state"] == "recovering"
        assert body["transport"]["gateway_endpoint"] == "10.251.7.254"

        reconcile = await client.post("/supervisor/v1/reconcile")
        assert reconcile.status_code == 200
        assert reconcile.json() == {"scanned": 2, "profiles": ["p1", "p2"]}
        assert core.reconcile_calls == 1

        readiness = await client.get("/supervisor/v1/readiness")
        assert readiness.status_code == 200
        assert readiness.json()["ready"] is False
        assert readiness.json()["reason"].startswith("api_unavailable")
