"""Supervisor must reject unusable credentials before serving any route."""

import secrets
from types import SimpleNamespace

import httpx
import pytest
from cbrowser.supervisor.control_server import create_control_app
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


@pytest.mark.parametrize("content", ["", "short"])
def test_unusable_service_key_prevents_startup(tmp_path, content):
    key = tmp_path / "key"
    key.write_text(content)
    key.chmod(0o600)
    with pytest.raises(ValueError, match="32 bytes"):
        create_control_app(SimpleNamespace(), key)


@pytest.mark.asyncio
async def test_control_authentication_rejects_empty_and_foreign_tokens(tmp_path):
    token = secrets.token_urlsafe(32)
    key = tmp_path / "key"
    key.write_text(token)
    key.chmod(0o600)
    app = create_control_app(SimpleNamespace(), key)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://supervisor"
    ) as client:
        for value in ("Bearer ", "Bearer " + secrets.token_urlsafe(32)):
            denied = await client.get(
                "/supervisor/v1/health", headers={"Authorization": value}
            )
            assert denied.status_code == 401
            assert token not in denied.text
        allowed = await client.get(
            "/supervisor/v1/health", headers={"Authorization": "Bearer " + token}
        )
        assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_status_maps_malformed_api_payload_to_503(tmp_path):
    token = secrets.token_urlsafe(32)
    key = tmp_path / "key"
    key.write_text(token)
    key.chmod(0o600)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    api = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://api"
    )
    core = SimpleNamespace(
        _sessions={}, _auth_headers=lambda: {}, api=api
    )
    app = create_control_app(core, key)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://supervisor"
        ) as client:
            response = await client.get(
                "/supervisor/v1/profiles/p/status",
                headers={"Authorization": "Bearer " + token},
            )
            assert response.status_code == 503
    finally:
        await api.aclose()


def test_cdp_websocket_authenticates_before_accept(tmp_path):
    token = secrets.token_urlsafe(32)
    key = tmp_path / "key"
    key.write_text(token)
    key.chmod(0o600)
    app = create_control_app(SimpleNamespace(), key)

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect(
                "/supervisor/v1/profiles/p/cdp",
                headers={"Authorization": "Bearer wrong"},
            ):
                pass
    assert excinfo.value.code == 4401
