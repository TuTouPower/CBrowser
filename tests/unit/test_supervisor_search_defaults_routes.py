"""Search-defaults status/retry routes on the supervisor control plane (A55)."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from cbrowser.runtime_agent.protocol import SearchDefaultsStatus
from cbrowser.supervisor.control_server import create_control_app
from cbrowser.supervisor.core import (
    LifecycleConflictError,
    RuntimeUnavailableError,
)

TOKEN = "unit-test-supervisor-token-" + "0123456789abcdef"


def _core(*, retry_error: Exception | None = None) -> SimpleNamespace:
    async def get_search_defaults(_profile_id: str):
        return "inst_1", SearchDefaultsStatus(
            state="failed",
            error_kind="timeout",
            runtime_instance_id="inst_1",
            request_id=None,
            updated_at="2026-11-04T00:00:00+00:00",
        )

    async def retry_search_defaults(_pid, _iid, _rid):
        if retry_error is not None:
            raise retry_error

    return SimpleNamespace(
        get_search_defaults=get_search_defaults,
        retry_search_defaults=retry_search_defaults,
    )


def _client(tmp_path, core) -> httpx.AsyncClient:
    key = tmp_path / "control_token"
    key.write_text(TOKEN)
    key.chmod(0o600)
    app = create_control_app(core, key)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://supervisor"
    )


@pytest.mark.asyncio
async def test_search_defaults_status_route_returns_typed_status(tmp_path) -> None:
    async with _client(tmp_path, _core()) as client:
        response = await client.get(
            "/supervisor/v1/profiles/profile_a/search-defaults",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["runtime_instance_id"] == "inst_1"
    assert body["search_defaults"]["state"] == "failed"
    assert body["search_defaults"]["error_kind"] == "timeout"


@pytest.mark.asyncio
async def test_search_defaults_routes_require_token(tmp_path) -> None:
    async with _client(tmp_path, _core()) as client:
        response = await client.get(
            "/supervisor/v1/profiles/profile_a/search-defaults"
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_retry_route_maps_conflict_and_unavailable(tmp_path) -> None:
    payload = {
        "profile_id": "profile_a",
        "runtime_instance_id": "inst_1",
        "request_id": "req-1",
    }
    async with _client(
        tmp_path, _core(retry_error=LifecycleConflictError("fence"))
    ) as client:
        response = await client.post(
            "/supervisor/v1/profiles/search-defaults/retry",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json=payload,
        )
    assert response.status_code == 409

    async with _client(
        tmp_path, _core(retry_error=RuntimeUnavailableError("down"))
    ) as client:
        response = await client.post(
            "/supervisor/v1/profiles/search-defaults/retry",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json=payload,
        )
    assert response.status_code == 503

    async with _client(tmp_path, _core()) as client:
        response = await client.post(
            "/supervisor/v1/profiles/search-defaults/retry",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json=payload,
        )
    assert response.status_code == 200
