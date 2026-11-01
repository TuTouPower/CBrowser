"""Supervisor must reject unusable credentials before serving any route."""

import secrets
from types import SimpleNamespace

import httpx
import pytest
from cbrowser.supervisor.control_server import create_control_app


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
