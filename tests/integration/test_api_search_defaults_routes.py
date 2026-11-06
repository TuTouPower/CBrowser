"""HTTP route layer for the search-defaults retry endpoint (t022 A55).

Real uvicorn + real session/CSRF wiring; the coordinator is replaced with
a stub so the route's status mapping and idempotency-key passthrough are
tested at the layer where they live.
"""

from __future__ import annotations

import asyncio
import secrets
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import uvicorn
from cbrowser.api.app import create_app
from cbrowser.api.runtime_coordinator import (
    SearchDefaultsConflictError,
    SearchDefaultsUnavailableError,
)
from cbrowser.domain.models import SearchDefaultsStatusData


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


class _StubCoordinator:
    def __init__(self, behavior: str) -> None:
        self.behavior = behavior
        self.seen_request_ids: list[str | None] = []

    def get_last_error(self, _profile_id: str, runtime=None):
        return None

    def get_search_defaults(self, _profile_id: str):
        if self.behavior == "ok":
            return SearchDefaultsStatusData(
                state="failed",
                error_kind="timeout",
                runtime_instance_id="inst_1",
                request_id=None,
                updated_at="2026-11-04T00:00:00+00:00",
            )
        if self.behavior == "mismatch":
            return SearchDefaultsStatusData(
                state="failed",
                error_kind="timeout",
                runtime_instance_id="inst_other",
                request_id=None,
                updated_at="2026-11-04T00:00:00+00:00",
            )
        return None

    async def refresh_search_defaults(self, _profile_id: str):
        return self.get_search_defaults(_profile_id)

    async def retry_search_defaults(self, profile_id: str, request_id=None):
        self.seen_request_ids.append(request_id)
        if self.behavior == "conflict":
            raise SearchDefaultsConflictError("stale instance")
        if self.behavior == "unavailable":
            raise SearchDefaultsUnavailableError("runtime down")
        return self.get_search_defaults(profile_id)


async def _logged_in_client(api_server) -> tuple[httpx.AsyncClient, dict, str]:
    client = httpx.AsyncClient(base_url=api_server["base_url"], trust_env=False)
    login = await client.post(
        "/api/v1/auth/login", json={"password": api_server["admin_pwd"]}
    )
    assert login.status_code == 200
    body = login.json()
    session_cookie = login.cookies.get("cbrowser_session")
    assert session_cookie
    headers = {
        "Origin": api_server["origin"],
        "X-CSRF-Token": body["csrf_token"],
        "Cookie": f"cbrowser_session={session_cookie}",
    }
    created = await client.post(
        "/api/v1/profiles", json={"name": "sd_profile"}, headers=headers
    )
    assert created.status_code == 201
    profile_id = created.json()["id"]
    # The stub coordinator reports a status for instance inst_1; the
    # runtime response fences statuses by the bound instance (t022), so
    # the fixture must bind the profile to that same instance — an
    # unbound profile correctly surfaces search_defaults=null.
    from cbrowser.api.v1.router import get_profile_service

    service = api_server["app"].dependency_overrides[get_profile_service]()
    await service.bind_runtime_instance(profile_id, "inst_1", config_version=1)
    return client, headers, profile_id


@pytest.mark.asyncio
async def test_retry_route_requires_csrf_and_maps_outcomes(api_server) -> None:
    client, headers, profile_id = await _logged_in_client(api_server)
    stub = _StubCoordinator("ok")
    api_server["app"].state.coordinator = stub
    url = f"/api/v1/profiles/{profile_id}/runtime/search-defaults/retry"
    try:
        # Missing CSRF header: the router-level dependency rejects first.
        no_csrf = {k: v for k, v in headers.items() if k != "X-CSRF-Token"}
        resp = await client.post(url, headers=no_csrf)
        assert resp.status_code == 403

        resp = await client.post(
            url, headers={**headers, "Idempotency-Key": "sd-key-42"}
        )
        assert resp.status_code == 200
        assert resp.json()["search_defaults"]["state"] == "failed"
        # The caller's idempotency key reaches the coordinator unchanged.
        assert stub.seen_request_ids == ["sd-key-42"]

        stub.behavior = "conflict"
        resp = await client.post(url, headers=headers)
        assert resp.status_code == 409

        stub.behavior = "unavailable"
        resp = await client.post(url, headers=headers)
        assert resp.status_code == 503
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_runtime_view_hides_status_from_another_instance(api_server) -> None:
    """Instance fence (t026 AC-001 negative case): a search-defaults
    status recorded for a different instance than the bound one must
    surface as search_defaults=null, never as the current outcome."""
    client, headers, profile_id = await _logged_in_client(api_server)
    api_server["app"].state.coordinator = _StubCoordinator("mismatch")
    try:
        resp = await client.get(
            f"/api/v1/profiles/{profile_id}/runtime", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["runtime_instance_id"] == "inst_1"
        assert resp.json()["search_defaults"] is None
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_retry_route_without_coordinator_is_503(api_server) -> None:
    client, headers, profile_id = await _logged_in_client(api_server)
    api_server["app"].state.coordinator = None
    try:
        resp = await client.post(
            f"/api/v1/profiles/{profile_id}/runtime/search-defaults/retry",
            headers=headers,
        )
        assert resp.status_code == 503
    finally:
        await client.aclose()
