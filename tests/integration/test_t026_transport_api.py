"""t026 AC-010: transport observation through the API surface.

The runtime response carries the Supervisor's layered observation,
fenced to the bound instance exactly like search-defaults: another
instance's state must surface as null, and the coordinator cache only
accepts payloads whose fenced instance matches.
"""

from __future__ import annotations

import asyncio
import secrets
from pathlib import Path

import httpx
import pytest
import uvicorn
from cbrowser.api.app import create_app
from cbrowser.api.runtime_coordinator import RuntimeCoordinator
from cbrowser.domain.models import TransportObservationData


@pytest.fixture
async def api_server(tmp_path: Path):
    admin_pwd_file = tmp_path / "admin_pwd.txt"
    admin_pwd = secrets.token_urlsafe(32)
    admin_pwd_file.write_text(admin_pwd, encoding="utf-8")
    origin = "https://app.cbrowser.local"
    app = create_app(
        db_path=tmp_path / "api.db",
        admin_password_file=admin_pwd_file,
        allowed_origins=[origin],
    )
    config = uvicorn.Config(app=app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield {
            "base_url": f"http://127.0.0.1:{port}",
            "origin": origin,
            "admin_pwd": admin_pwd,
            "app": app,
        }
    finally:
        server.should_exit = True
        await task


def _observation(instance_id: str = "inst_1", state: str = "recovering"):
    return TransportObservationData(
        profile_id="placeholder",
        runtime_instance_id=instance_id,
        browser_state="running",
        stream_state="running",
        transport_state=state,
        gateway_endpoint="10.251.7.254",
        last_error="gateway_missing" if state == "recovering" else None,
    )


class _StubCoordinator:
    def __init__(self, observation: TransportObservationData | None) -> None:
        self.observation = observation

    def get_last_error(self, _profile_id: str):
        return None

    def get_search_defaults(self, _profile_id: str):
        return None

    async def refresh_search_defaults(self, _profile_id: str):
        return None

    def get_transport(self, profile_id: str):
        if self.observation is None:
            return None
        return self.observation.model_copy(update={"profile_id": profile_id})

    async def refresh_transport(self, profile_id: str):
        return self.get_transport(profile_id)


async def _logged_in_client(api_server, instance_id: str = "inst_1"):
    client = httpx.AsyncClient(base_url=api_server["base_url"], trust_env=False)
    login = await client.post(
        "/api/v1/auth/login", json={"password": api_server["admin_pwd"]}
    )
    assert login.status_code == 200
    body = login.json()
    session_cookie = login.cookies.get("cbrowser_session")
    headers = {
        "Origin": api_server["origin"],
        "X-CSRF-Token": body["csrf_token"],
        "Cookie": f"cbrowser_session={session_cookie}",
    }
    created = await client.post(
        "/api/v1/profiles", json={"name": "transport_profile"}, headers=headers
    )
    assert created.status_code == 201
    profile_id = created.json()["id"]
    from cbrowser.api.v1.router import get_profile_service

    service = api_server["app"].dependency_overrides[get_profile_service]()
    await service.bind_runtime_instance(profile_id, instance_id, config_version=1)
    return client, headers, profile_id


@pytest.mark.asyncio
async def test_runtime_response_carries_fenced_transport(api_server) -> None:
    client, headers, profile_id = await _logged_in_client(api_server)
    api_server["app"].state.coordinator = _StubCoordinator(_observation())
    try:
        resp = await client.get(
            f"/api/v1/profiles/{profile_id}/runtime", headers=headers
        )
        assert resp.status_code == 200
        transport = resp.json()["transport"]
        assert transport is not None
        assert transport["transport_state"] == "recovering"
        assert transport["browser_state"] == "running"
        assert transport["gateway_endpoint"] == "10.251.7.254"
        assert transport["last_error"] == "gateway_missing"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_runtime_response_hides_other_instance_transport(api_server) -> None:
    client, headers, profile_id = await _logged_in_client(api_server)
    api_server["app"].state.coordinator = _StubCoordinator(
        _observation(instance_id="inst_other")
    )
    try:
        resp = await client.get(
            f"/api/v1/profiles/{profile_id}/runtime", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["transport"] is None
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_coordinator_refresh_transport_fences_payload(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "profile_id": "p1",
                "runtime_instance_id": "inst_1",
                "transport": {
                    "profile_id": "p1",
                    "runtime_instance_id": "inst_1",
                    "browser_state": "running",
                    "stream_state": "running",
                    "transport_state": "ready",
                },
            },
        )

    from cbrowser.services.profile_service import ProfileService

    coordinator = RuntimeCoordinator(
        supervisor_url="http://supervisor.invalid",
        supervisor_token="t" * 40,
        profile_service=ProfileService.__new__(ProfileService),
        transport=httpx.MockTransport(handler),
    )
    observation = await coordinator.refresh_transport("p1")
    assert observation is not None
    assert observation.transport_state == "ready"
    assert coordinator.fenced_transport("p1", "inst_1") is observation
    assert coordinator.fenced_transport("p1", "inst_2") is None


@pytest.mark.asyncio
async def test_fresh_coordinator_reports_transport_unknown(tmp_path) -> None:
    # AC-010 / test f005: transport observations are memory-only. A
    # restarted API process starts with an empty cache, so every
    # Profile reads unknown (fenced out) until the Supervisor reports
    # again — never a stale ready.
    from cbrowser.services.profile_service import ProfileService

    coordinator = RuntimeCoordinator(
        supervisor_url="http://supervisor.invalid",
        supervisor_token="t" * 40,
        profile_service=ProfileService.__new__(ProfileService),
        transport=httpx.MockTransport(lambda request: httpx.Response(503)),
    )
    assert coordinator.get_transport("p1") is None
    assert coordinator.fenced_transport("p1", "inst_1") is None
